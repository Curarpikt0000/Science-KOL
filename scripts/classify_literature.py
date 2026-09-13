#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文献分流 + LLM 中文摘要。

两段式，理由是成本：全量 900+ 条逐条 LLM = 每天 25 分钟以上串行调用
（见 skill llm-batch-via-local-proxy：本机必须串行 + 1.5s 间隔），
且会与其他同配额 job 抢资源。所以：

  第一段（规则，零成本，全量）：期刊/分类映射 + 关键词打分 → 8 门类归属 + 重要度
  第二段（LLM，只对 Top-N）：中文一句话摘要 + 门类复核

规则先行还有一个好处：门类归属可解释、可审计，不是黑箱。
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIT_DIR = ROOT / "data" / "literature"

FIELDS = ["医学健康", "生命科学", "AI计算机", "物理天文",
          "化学材料", "神经认知", "地球气候", "数学基础理论"]

# ── 期刊 / arXiv 分类 → 门类的强映射（命中即定，不再看关键词）──────────
SOURCE_FIELD = {
    "NEJM": "医学健康", "Lancet": "医学健康", "JAMA": "医学健康",
    "medRxiv": "医学健康", "Cell": "生命科学", "bioRxiv": "生命科学",
    "eLife": "生命科学", "chemRxiv": "化学材料",
}

# ── 关键词表（弱信号，加权打分）───────────────────────────────────
# ★ 红线词误杀教训（War-KOL 踩过）：短词用 \b 边界，不要直接删词。
KEYWORDS: dict[str, list[str]] = {
    "医学健康": [r"\bclinical\b", r"\bpatient", r"\btherap", r"\btrial\b", r"\bdisease",
                r"\bcancer\b", r"\btumou?r", r"\bvaccine", r"\bdiagnos", r"\btreatment",
                r"\bmortality\b", r"\bepidemi", r"\bsurgery\b", r"\bdrug\b", r"\bcohort\b"],
    "生命科学": [r"\bgene\b", r"\bgenom", r"\bprotein", r"\bcell\b", r"\bcellular\b",
                r"\bRNA\b", r"\bDNA\b", r"\benzyme", r"\bmicrobio", r"\bevolution",
                r"\bCRISPR\b", r"\bimmun", r"\bmetabol", r"\bstem cell"],
    "AI计算机": [r"\bneural network", r"\bdeep learning", r"\bmachine learning",
                r"\bLLM\b", r"\blarge language model", r"\btransformer\b", r"\balgorithm",
                r"\bAI\b", r"\bartificial intelligence", r"\bcomputer vision", r"\brobot"],
    "物理天文": [r"\bquantum\b", r"\bparticle\b", r"\bgalax", r"\bcosmolog", r"\bastro",
                r"\bblack hole", r"\bphoton", r"\brelativ", r"\bsupernova", r"\btelescope",
                r"\bspintronic", r"\bsuperconduct"],
    "化学材料": [r"\bcataly", r"\bmolecul", r"\bsynthesis\b", r"\bpolymer", r"\bcrystal",
                r"\bnanomaterial", r"\bchemical\b", r"\belectrochem", r"\balloy\b",
                r"\bperovskite", r"\bligand\b"],
    "神经认知": [r"\bneuro", r"\bbrain\b", r"\bcortex\b", r"\bcognit", r"\bsynap",
                r"\bmemory\b", r"\bconscious", r"\bneuron", r"\bEEG\b", r"\bfMRI\b",
                r"\bbehavio[u]?r"],
    "地球气候": [r"\bclimate\b", r"\bcarbon\b", r"\bemission", r"\bocean\b", r"\bearthquake",
                r"\bglacier", r"\batmospher", r"\bbiodiversity", r"\becosystem",
                r"\bwarming\b", r"\bseismic", r"\bpollut"],
    "数学基础理论": [r"\btheorem\b", r"\bconjecture\b", r"\bmanifold\b", r"\btopolog",
                  r"\balgebra", r"\bstochastic", r"\bBayesian\b", r"\bstatistical inference",
                  r"\bprobabilit", r"\bnumber theory", r"\bgeometr"],
}
_COMPILED = {f: [re.compile(p, re.I) for p in pats] for f, pats in KEYWORDS.items()}

# ── 兜底关键词（第二轮，仅对首轮未命中的条目启用）─────────────────
# ★ 2026-09-13 实测必要性：Nature RSS 摘要仅 150-250 字符，主表命不中，
#   导致 `base editing at PCSK9`、`generative sampling of conformational transitions`
#   这类真论文落入「未分类」。兜底表用更宽的词根，宁可弱命中也别丢论文。
FALLBACK_KEYWORDS: dict[str, list[str]] = {
    "生命科学": [r"\bediting\b", r"\bembryo", r"\bancestry\b", r"\bspecies\b", r"\bmutation",
                r"\bphenotyp", r"\btranscript", r"\bmolecular\b", r"\bbiolog", r"\borganism",
                r"\bPCSK9\b", r"\bCRISPR", r"\bplant\b", r"\bbacteri"],
    "医学健康": [r"\bhealth\b", r"\bmedic", r"\bdose\b", r"\brisk\b", r"\bsymptom",
                r"\binfection", r"\bvirus\b", r"\bpublic health"],
    "AI计算机": [r"\bgenerative\b", r"\bmodel(?:ling|ing)?\b", r"\bsampling\b", r"\bcomput",
                r"\bdata[- ]driven\b", r"\bsimulation", r"\bpredict", r"\bsatellite-derived\b"],
    "物理天文": [r"\bphysic", r"\batom", r"\bmagnet", r"\benergy\b", r"\blaser\b",
                r"\bspin\b", r"\borbit"],
    "化学材料": [r"\bconformational\b", r"\bcompound", r"\breaction", r"\bsurface\b",
                r"\bmaterial", r"\bbond(?:ing)?\b", r"\bsolvent"],
    "神经认知": [r"\bmental\b", r"\bpsych", r"\bsleep\b", r"\bemotion"],
    "地球气候": [r"\benvironment", r"\bwater\b", r"\bsoil\b", r"\bspecies loss",
                r"\bconflict research\b", r"\bsustainab", r"\bagricultur"],
    "数学基础理论": [r"\bproof\b", r"\bequation", r"\boptimiz", r"\bmatrix\b", r"\bgraph\b"],
}
_FALLBACK = {f: [re.compile(p, re.I) for p in pats]
             for f, pats in FALLBACK_KEYWORDS.items() if pats}

# 重要度加分：顶刊 > 开放获取 > 预印本
TIER_WEIGHT = {"mainstream": 6, "alt": 2, "preprint": 1}


def classify(item: dict) -> tuple[str | None, float, dict]:
    """返回 (门类, 相关度分, 各门类得分明细)。纯规则、可解释。"""
    text = f"{item.get('title', '')} {item.get('abstract', '')}"
    scores = {f: 0.0 for f in FIELDS}

    # 1) 源强映射
    src = (item.get("source") or "").split(":")[0]
    if src in SOURCE_FIELD:
        scores[SOURCE_FIELD[src]] += 5.0
    # 2) arXiv 分类自带门类（抓取层已填 field）
    if item.get("field") in scores:
        scores[item["field"]] += 5.0
    # 3) 关键词命中（标题权重 2x）
    title = item.get("title", "")
    for f, pats in _COMPILED.items():
        for p in pats:
            n_all = len(p.findall(text))
            if n_all:
                scores[f] += min(n_all, 4) * 1.0
                if p.search(title):
                    scores[f] += 2.0

    best = max(scores, key=lambda k: scores[k])
    if scores[best] > 0:
        return best, scores[best], scores

    # 兜底轮：主表全未命中时启用宽词根（多见于 Nature 等短摘要源）
    for f, pats in _FALLBACK.items():
        for p in pats:
            if p.search(text):
                scores[f] += 0.6
                if p.search(title):
                    scores[f] += 0.6
    best = max(scores, key=lambda k: scores[k])
    if scores[best] <= 0:
        return None, 0.0, scores
    return best, scores[best], scores


def importance(item: dict, field_score: float) -> float:
    """排序用重要度：期刊层级 + 门类契合度 + 摘要完整度。"""
    s = TIER_WEIGHT.get(item.get("tier", ""), 0) + min(field_score, 12) * 0.5
    if len(item.get("abstract") or "") > 400:
        s += 1.5
    if item.get("doc_type") == "news":
        s -= 3.0
    return round(s, 2)


# ── LLM（本机 genai proxy，串行 + 间隔，见 skill llm-batch-via-local-proxy）──
# ★ 代理地址只从环境变量读，代码里不留默认值：硬编码回环地址会被 publish.sh
#   的红线扫描拦下（它属于本机实现细节，不进公网仓库）。
API = os.environ.get("GENAI_PROXY", "").rstrip("/") + "/v1/chat/completions"
MODEL = os.environ.get("SK_MODEL", "claude-opus-4-8")
SLEEP = 1.5


def call_llm(system: str, user: str, max_tokens: int = 900, retries: int = 3) -> str | None:
    if not os.environ.get("GENAI_PROXY"):
        print("    [WARN] 未设置 GENAI_PROXY，跳过 LLM 摘要（规则分流不受影响）")
        return None
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "max_tokens": max_tokens, "temperature": 0.2,
    }).encode()
    for i in range(retries):
        try:
            req = urllib.request.Request(
                API, data=body,
                headers={"Content-Type": "application/json", "Authorization": "Bearer " + os.environ.get("GENAI_KEY", "local")})
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            # ★ 客户端 RemoteDisconnected 多是上游 429 被代理 log 掩盖 → 退避重试
            if e.code in (429, 500, 502, 503):
                time.sleep(8 * (i + 1))
                continue
            return None
        except Exception:
            time.sleep(5 * (i + 1))
    return None


BATCH_SYS = (
    "你是科研文献编辑。给定若干篇论文的标题与摘要，为每篇产出中文一句话摘要与门类归属。\n"
    "规则：\n"
    "1) summary_zh：一句话中文，30-60 字，讲清【做了什么 + 关键发现】，"
    "必须具体（写出对象/机制/数字），禁止『本文研究了某问题』这类空话。\n"
    f"2) field：只能从这 8 个里选一个：{'、'.join(FIELDS)}。\n"
    "3) 摘要信息不足以判断时，summary_zh 填空字符串，不要编造。\n"
    "只输出 JSON 数组，每项 {\"i\": 序号, \"summary_zh\": \"...\", \"field\": \"...\"}，无其他文字。"
)


def llm_summarize(items: list[dict], batch_size: int = 8) -> int:
    """对给定条目批量生成中文摘要。返回成功条数。"""
    done = 0
    for b in range(0, len(items), batch_size):
        chunk = items[b:b + batch_size]
        payload = "\n\n".join(
            f"[{i}] 标题：{it['title']}\n来源：{it['source']}\n摘要：{(it.get('abstract') or '')[:1100]}"
            for i, it in enumerate(chunk))
        out = call_llm(BATCH_SYS, payload)
        if out:
            m = re.search(r"\[.*\]", out, re.S)
            if m:
                try:
                    for rec in json.loads(m.group(0)):
                        idx = rec.get("i")
                        if isinstance(idx, int) and 0 <= idx < len(chunk):
                            s = (rec.get("summary_zh") or "").strip()
                            if s:
                                chunk[idx]["summary_zh"] = s
                                done += 1
                            if rec.get("field") in FIELDS:
                                chunk[idx]["field_llm"] = rec["field"]
                except json.JSONDecodeError:
                    pass
        print(f"    LLM 批 {b // batch_size + 1}/{(len(items) - 1) // batch_size + 1} "
              f"→ 累计 {done}")
        time.sleep(SLEEP)
    return done


def main() -> int:
    day = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    top_n = int(os.environ.get("SK_LLM_TOPN", "60"))
    path = LIT_DIR / f"{day}.json"
    if not path.exists():
        print(f"没有 {path}，先跑 fetch_literature.py")
        return 1

    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload["items"]

    print(f"=== 分流 {len(items)} 条 ===")
    unmatched = 0
    for it in items:
        f, sc, detail = classify(it)
        it["field"] = f
        it["field_score"] = round(sc, 2)
        it["importance"] = importance(it, sc)
        it["field_scores"] = {k: round(v, 1) for k, v in detail.items() if v > 0}
        if f is None:
            unmatched += 1

    dist: dict[str, int] = {}
    for it in items:
        dist[it["field"] or "未分类"] = dist.get(it["field"] or "未分类", 0) + 1
    print("门类分布:")
    for k, v in sorted(dist.items(), key=lambda x: -x[1]):
        print(f"  {k:12s} {v:4d}")
    print(f"未命中任何门类: {unmatched}")

    ranked = sorted([i for i in items if i["field"]],
                    key=lambda x: -x["importance"])[:top_n]
    print(f"\n=== LLM 中文摘要：Top {len(ranked)} 条 ===")
    ok = llm_summarize(ranked)
    print(f"LLM 摘要成功 {ok}/{len(ranked)}")

    payload["_stats"]["field_dist"] = dist
    payload["_stats"]["llm_summarized"] = ok
    payload["_stats"]["classified_at"] = date.today().isoformat()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"写回 {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
