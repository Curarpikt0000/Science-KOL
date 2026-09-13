#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文献日抓取：全源 → 去重 → 摘要回填 → 落盘 data/literature/YYYY-MM-DD.json

只做采集，不做 LLM 加工（分流/摘要交给 classify_literature.py）。
纪律：任何源失败只警告并跳过，绝不伪造条目；发表日取不到就留空，绝不用抓取日顶替。
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sources as S  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "literature"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main() -> int:
    today = date.today().isoformat()
    # 预印本 API 与 Crossref 索引都有滞后，回看 2 天再按日期筛，避免空转
    lookback = (date.today() - timedelta(days=2)).isoformat()
    t0 = time.time()
    print(f"=== Science-KOL 文献抓取 {today} (回看起点 {lookback}) ===")

    rows: list[dict] = []
    print("[1/4] 顶刊 / 开放获取 RSS")
    rows += S.fetch_journals()
    print("[2/4] 预印本 API (bioRxiv / medRxiv)")
    for d in [(date.today() - timedelta(days=i)).isoformat() for i in (1, 2)]:
        rows += S.fetch_preprints(d)
    print("[3/4] arXiv 分类 RSS")
    rows += S.fetch_arxiv(today)
    print("[4/4] Crossref 绕过 (chemRxiv / MDPI)")
    rows += S.fetch_crossref_bypass(lookback)

    raw_n = len(rows)
    rows = S.dedupe(rows)
    print(f"\n去重: {raw_n} → {len(rows)}")

    # ★ 统一发表日窗口过滤（默认 60 天）。
    #   顶刊 RSS 的 current issue 会含数周前的文章、Crossref 会回捞改版旧稿，
    #   不滤会让「每日更新」面板混入历史论文（实测 916 条里 316 条早于 2026-08）。
    #   发表日取不到的条目【保留】并标 undated，绝不因取不到就丢弃或用抓取日顶替。
    window_days = int(os.environ.get("SK_WINDOW_DAYS", "60"))
    cutoff = (date.today() - timedelta(days=window_days)).isoformat()
    before = len(rows)
    kept, dropped_old, undated = [], 0, 0
    for r in rows:
        p = (r.get("published") or "").strip()
        if not p:
            undated += 1
            r["date_status"] = "unverified"
            kept.append(r)
        elif p < cutoff:
            dropped_old += 1
        else:
            r["date_status"] = "ok"
            kept.append(r)
    rows = kept
    print(f"发表日窗口({window_days}天, >={cutoff}): {before} → {len(rows)} "
          f"（滤除旧论文 {dropped_old}，无发表日保留 {undated}）")

    miss = sum(1 for r in rows if not r["abstract"])
    if miss:
        print(f"缺摘要 {miss} 条，OpenAlex 回填中…")
        filled = S.backfill_abstracts_openalex(rows)
        print(f"  回填成功 {filled} 条")

    for r in rows:
        r.setdefault("doc_type", "article")
        r["collected_on"] = today

    stats = {
        "date": today,
        "total": len(rows),
        "with_abstract": sum(1 for r in rows if r["abstract"]),
        "with_doi": sum(1 for r in rows if r["doi"]),
        "with_pubdate": sum(1 for r in rows if r["published"]),
        "by_tier": {},
        "by_source": {},
        "elapsed_s": round(time.time() - t0, 1),
    }
    for r in rows:
        stats["by_tier"][r["tier"]] = stats["by_tier"].get(r["tier"], 0) + 1
        stats["by_source"][r["source"]] = stats["by_source"].get(r["source"], 0) + 1

    out = OUT_DIR / f"{today}.json"
    out.write_text(json.dumps({"_stats": stats, "items": rows}, ensure_ascii=False, indent=1),
                   encoding="utf-8")

    print(f"\n落盘: {out}")
    print(f"  总计 {stats['total']} | 带摘要 {stats['with_abstract']} "
          f"({stats['with_abstract'] * 100 // max(stats['total'], 1)}%) "
          f"| 带DOI {stats['with_doi']} | 带发表日 {stats['with_pubdate']}")
    print(f"  分层: {stats['by_tier']}")
    print(f"  耗时 {stats['elapsed_s']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
