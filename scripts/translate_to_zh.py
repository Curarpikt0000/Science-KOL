#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全站中文化：给 KOL 观点与文献补中文标题 + 中文摘要。

★ Chao 铁律（2026-09-13）：面板上所有展开层内容必须是中文，不能是英文。
  原状：观点 180 条全英文、文献展示层 794 条标题全英文（仅 146 条有中文摘要）。

设计要点：
  · 幂等：已有 title_zh + summary_zh 的条目直接跳过，重跑不烧配额。
  · 串行 + 间隔：本机 genai proxy 并发会 429（见 skill llm-batch-via-local-proxy）。
  · 只翻【面板实际展示】的条目，不翻全量 963 条文献——省配额且够用。
  · 译不出来就留空并标记，绝不塞英文原文冒充中文，也绝不编造。
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

INTERVAL = 1.5          # 串行间隔，防 429
MODEL = "gpt-4o-mini"


def has_cn(s: str | None) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", s or ""))


def llm(prompt: str, retries: int = 3) -> str:
    if not PROXY:
        return ""
    body = json.dumps({"model": MODEL,
                       "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0.2, "max_tokens": 700}).encode()
    for att in range(retries):
        try:
            req = urllib.request.Request(
                PROXY.rstrip("/") + "/v1/chat/completions", data=body,
                headers={"Content-Type": "application/json",
                         "Authorization": "Bearer " + os.environ.get("GENAI_KEY", "local")})
            r = json.loads(urllib.request.urlopen(req, timeout=90).read())
            return r["choices"][0]["message"]["content"].strip()
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


def parse(out: str) -> tuple[str, str]:
    """解析「标题：… 摘要：…」，容忍全角/半角冒号与 markdown 粗体。"""
    t = re.search(r"标题[:：]\s*\**(.+?)\**\s*(?:\n|$)", out)
    s = re.search(r"摘要[:：]\s*\**(.+)", out, re.S)
    title = (t.group(1).strip() if t else "")
    summ = (s.group(1).strip().replace("**", "") if s else "")
    # 防御：模型偶尔把英文原样吐回来
    if title and not has_cn(title):
        title = ""
    if summ and not has_cn(summ):
        summ = ""
    return title, summ


PROMPT_STMT = """把下面这篇科学家观点文章译成中文，供中文读者速读。

标题：{title}
正文：{body}

严格按此格式输出，不要任何额外说明：
标题：<中文标题，25字以内，准确不夸张>
摘要：<150-250字中文，说清：评述的具体对象、核心论点、关键证据或数据、结论指向。\
保留专业术语的中文规范译名，首次出现时可括注英文原词。若正文信息不足，就只写标题能支撑的内容，不要编造>"""

PROMPT_LIT = """把下面这篇科学论文译成中文，供中文读者速读。

标题：{title}
摘要：{body}

严格按此格式输出，不要任何额外说明：
标题：<中文标题，25字以内，准确>
摘要：<120-200字中文，说清：研究对象、方法要点、关键数据或发现、结论。\
保留专业术语的中文规范译名。若信息不足就只写能支撑的内容，不要编造>"""


def translate_rows(rows: list[dict], prompt_tpl: str, body_key: str,
                   label: str, limit: int) -> int:
    todo = [r for r in rows
            if not (has_cn(r.get("title_zh")) and has_cn(r.get("summary_zh")))]
    todo = todo[:limit]
    if not todo:
        print(f"  {label}: 全部已中文化，跳过")
        return 0
    print(f"  {label}: 待译 {len(todo)} 条")
    ok = 0
    for i, r in enumerate(todo, 1):
        body = (r.get(body_key) or "")[:1400]
        out = llm(prompt_tpl.format(title=r.get("title", ""), body=body))
        t, s = parse(out)
        if t:
            r["title_zh"] = t
        if s:
            r["summary_zh"] = s
        if t or s:
            ok += 1
        else:
            r["zh_status"] = "翻译失败"
        if i % 20 == 0:
            print(f"    {i}/{len(todo)} 完成 {ok}", flush=True)
        time.sleep(INTERVAL)
    print(f"  {label}: 成功 {ok}/{len(todo)}")
    return ok


def main() -> int:
    if not PROXY:
        print("[ERR] GENAI_PROXY 未配置，无法翻译。中止（不产出半成品）。")
        return 1
    scope = sys.argv[1] if len(sys.argv) > 1 else "all"
    lim = int(os.environ.get("SK_ZH_LIMIT", "400"))

    if scope in ("all", "stmt"):
        f = ROOT / "data" / "statements" / "2026-09-13.json"
        # 取最新一天的文件（按文件名排序）
        cands = sorted((ROOT / "data" / "statements").glob("*.json"))
        if cands:
            f = cands[-1]
        rows = json.loads(f.read_text(encoding="utf-8"))
        print(f"[观点] {f.name} {len(rows)} 条")
        translate_rows(rows, PROMPT_STMT, "body", "观点", lim)
        f.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    if scope in ("all", "lit"):
        # 只翻面板实际展示的条目：从三层里取 URL 集合
        lay_f = ROOT / "data" / "layers" / "literature_layers.json"
        shown_urls = set()
        if lay_f.exists():
            lay = json.loads(lay_f.read_text(encoding="utf-8"))
            for L in ("daily", "monthly", "yearly"):
                for b in (lay.get(L) or {}).values():
                    for it in (b.get("items") or b.get("top_items") or []):
                        if isinstance(it, dict) and it.get("url"):
                            shown_urls.add(it["url"])
        lf = sorted((ROOT / "data" / "literature").glob("*.json"))[-1]
        data = json.loads(lf.read_text(encoding="utf-8"))
        items = data.get("items") if isinstance(data, dict) else data
        target = [r for r in items if r.get("url") in shown_urls] if shown_urls else items
        print(f"[文献] {lf.name} 展示层 {len(target)} 条")
        translate_rows(target, PROMPT_LIT, "abstract", "文献", lim)
        lf.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    print("完成。下一步需重建三层与面板才会生效。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
