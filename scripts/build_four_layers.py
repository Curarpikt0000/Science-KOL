#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成四层钻取内容（对齐 War-KOL 2026-09-07 拍板的规格）。

四层定义（与 War-KOL scripts/build_dashboard.py::layerBody 完全一致）：
  L1 一句话导语（35-55 字）
  L2 总结（300-600 字，论点/论证/论据/数据并入行文）
  L3 原文全文翻译（有多少译多少；拿不到全文就如实标注，绝不用摘要冒充）
  L4 出处链接 + 元信息

★ 纪律：
  · L3 只对真正拿到全文的条目生成。文献源头多数只有 abstract，
    这类标 l3_status="abstract_only"，面板如实显示「仅有摘要，无全文可译」。
  · 任何一层生成失败都留空 + 标状态，绝不用上一层内容顶替。
  · 幂等：已有该层内容的条目跳过，重跑不烧配额。
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENVF = ROOT / ".env.local"

PROXY = os.environ.get("GENAI_PROXY", "")
if not PROXY and ENVF.exists():
    for line in ENVF.read_text(encoding="utf-8").splitlines():
        if "GENAI_PROXY" in line:
            PROXY = line.split("=", 1)[1].strip().strip('"').strip("'")

INTERVAL = 1.5
MODEL = "gpt-4o-mini"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122"


def has_cn(s) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", s or ""))


def llm(prompt: str, max_tokens: int = 2200, retries: int = 3) -> str:
    if not PROXY:
        return ""
    body = json.dumps({"model": MODEL,
                       "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0.2, "max_tokens": max_tokens}).encode()
    for att in range(retries):
        try:
            req = urllib.request.Request(
                PROXY.rstrip("/") + "/v1/chat/completions", data=body,
                headers={"Content-Type": "application/json",
                         "Authorization": "Bearer "
                                          + os.environ.get("GENAI_KEY", "local")})
            r = json.loads(urllib.request.urlopen(req, timeout=150).read())
            out = r["choices"][0]["message"]["content"].strip()
            # ★ 空返回也要重试：实测代理会偶发返回空内容（同输入重跑即成功），
            #   直接 return "" 会把偶发故障当成永久失败。
            if out:
                return out
            if att < retries - 1:
                time.sleep(4 * (att + 1))
                continue
            return ""
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(5 * (att + 1))
                continue
            return ""
        except Exception:  # noqa: BLE001
            if att < retries - 1:
                time.sleep(3)
                continue
            return ""
    return ""


def fetch_fulltext(url: str) -> str:
    """只对 The Conversation 这类可取全文的源抓正文。取不到返回空。

    ★ 2026-09-14 实测教训：原先 articleBody 正则要求后面紧跟 </div> 或 <footer>，
      实际页面结构常非如此 → 匹配失败 → 回落到 <p> 兜底只捞到片段
      （某篇实际 1600 字符，整篇远不止），导致「全文翻译」比「总结」还短。
      改为：正文容器用非贪婪但不限定收尾标签，并优先按段落聚合；
      同时校验产出长度，过短视为抓取失败（返回空）而不是交付残篇。
    """
    if not url or "theconversation.com" not in url:
        return ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        return ""

    # 1) 优先锁定正文容器，再从中取全部 <p>
    blob = ""
    for pat in (r'<div[^>]+itemprop="articleBody"[^>]*>(.*)',
                r'<div[^>]+class="[^"]*content-body[^"]*"[^>]*>(.*)',
                r'<article[^>]*>(.*)</article>'):
        m = re.search(pat, html, re.S)
        if m:
            blob = m.group(1)
            break
    if not blob:
        blob = html

    paras = re.findall(r"<p[^>]*>(.*?)</p>", blob, re.S)
    # 丢弃页脚免责声明/订阅号召这类短句
    keep = []
    for p in paras:
        t = re.sub(r"<[^>]+>", "", p)
        t = re.sub(r"&nbsp;", " ", t)
        t = re.sub(r"&[a-z]+;", " ", t).strip()
        if len(t) >= 40:
            keep.append(t)
    txt = "\n\n".join(keep)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    txt = re.sub(r"[ \t]{2,}", " ", txt).strip()
    # 过短 = 抓取残缺，宁可判失败也不交付残篇冒充全文
    return txt if len(txt) > 900 else ""


P_L1 = """用一句中文导语概括下面这篇科学内容的核心结论，35-55 字。
只输出这一句话，不要引号、不要任何前后缀。

标题：{title}
内容：{body}"""

P_L2 = """把下面的科学内容写成一段中文总结，300-600 字。

标题：{title}
内容：{body}

要求：
· 把研究/评述的对象、核心论点、支撑证据、关键数据、结论指向融进行文，不要分小标题罗列
· 出现的数字、比例、样本量等要保留，这是判断价值的依据
· 专业术语用中文规范译名，首次出现括注英文原词
· 只依据给定内容，信息不足就写到哪算哪，绝不编造
只输出总结正文。"""

P_L3 = """把下面的英文原文逐句完整译成中文。

{body}

要求：
· 有多少译多少，不概括、不删减、不压缩
· 保持原文分段（段落之间空一行）
· 专业术语用中文规范译名
只输出译文。"""


def gen_layers(rows: list[dict], limit: int, do_l3: bool) -> tuple[int, int]:
    todo = [r for r in rows if not has_cn(r.get("l2_summary"))][:limit]
    if not todo:
        print("  四层内容已齐备，跳过")
        return 0, 0
    print(f"  待生成 {len(todo)} 条")
    ok = l3n = 0
    for i, r in enumerate(todo, 1):
        title = r.get("title_zh") or r.get("title") or ""
        base = (r.get("summary_zh") or r.get("body") or r.get("abstract") or "")[:2500]
        if not base:
            r["layer_status"] = "无内容可用"
            continue

        if not has_cn(r.get("l1_lead")):
            out = llm(P_L1.format(title=title, body=base), 200)
            if has_cn(out):
                r["l1_lead"] = out.strip().strip("「」\"'")
            time.sleep(INTERVAL)

        out = llm(P_L2.format(title=title, body=base), 1200)
        if has_cn(out):
            r["l2_summary"] = out.strip()
            ok += 1
        else:
            r["layer_status"] = "总结生成失败"
        time.sleep(INTERVAL)

        # L3：只对真能拿到全文的条目做
        if do_l3 and not has_cn(r.get("l3_translation")):
            ft = fetch_fulltext(r.get("url", ""))
            if ft:
                tr = llm(P_L3.format(body=ft[:6000]), 3000)
                if has_cn(tr):
                    r["l3_translation"] = tr.strip()
                    r["l3_status"] = "full"
                    l3n += 1
                else:
                    r["l3_status"] = "translate_failed"
                time.sleep(INTERVAL)
            else:
                r["l3_status"] = "abstract_only"
        elif not r.get("l3_status"):
            r["l3_status"] = "abstract_only"

        if i % 10 == 0:
            print(f"    {i}/{len(todo)} L2成功 {ok} L3全文 {l3n}", flush=True)
    print(f"  L2 成功 {ok}/{len(todo)}｜L3 取到全文 {l3n} 条")
    return ok, l3n


def main() -> int:
    if not PROXY:
        print("[ERR] GENAI_PROXY 未配置，中止（不产出半成品）")
        return 1
    scope = sys.argv[1] if len(sys.argv) > 1 else "all"
    lim = int(os.environ.get("SK_L4_LIMIT", "200"))

    if scope in ("all", "stmt"):
        f = sorted((ROOT / "data" / "statements").glob("*.json"))[-1]
        rows = json.loads(f.read_text(encoding="utf-8"))
        print(f"[观点] {f.name} {len(rows)} 条")
        gen_layers(rows, lim, do_l3=True)
        f.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    if scope in ("all", "lit"):
        lay_f = ROOT / "data" / "layers" / "literature_layers.json"
        shown = set()
        if lay_f.exists():
            lay = json.loads(lay_f.read_text(encoding="utf-8"))
            for L in ("daily", "monthly", "yearly"):
                for b in (lay.get(L) or {}).values():
                    for it in (b.get("items") or b.get("top_items") or []):
                        if isinstance(it, dict) and it.get("url"):
                            shown.add(it["url"])
        lf = sorted((ROOT / "data" / "literature").glob("*.json"))[-1]
        data = json.loads(lf.read_text(encoding="utf-8"))
        items = data.get("items") if isinstance(data, dict) else data
        target = [r for r in items if r.get("url") in shown] if shown else items
        print(f"[文献] 展示层 {len(target)} 条")
        gen_layers(target, lim, do_l3=False)   # 文献源头只有 abstract
        lf.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    print("完成。需重建三层与面板才会生效。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
