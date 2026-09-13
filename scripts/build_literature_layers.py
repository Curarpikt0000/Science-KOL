#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文献日/月/年三层聚合 → data/layers/literature_layers.json

分层口径（与 Forecast-Checker 的「按实际发表日而非抓取日」纪律一致）：
  日层：按 published 当日，全量列表（按 importance 排序）
  月层：按门类聚合计数 + 该月 Top 条目 + 高频主题词
  年层：门类月度趋势曲线 + 全年 Top + 源产出分布
发表日取不到的条目单列 undated 桶，绝不用 collected_on 顶替。
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIT_DIR = ROOT / "data" / "literature"
OUT = ROOT / "data" / "layers" / "literature_layers.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

STOP = set("""the a an and or of in on for with to from by at as is are was were be been being
this that these those we our it its their his her they them he she you your i
using use used study studies research paper article results result show shows showed
new novel based via between during into over under more most high higher low lower
can may might could would should will have has had not no than then when where which who
significant significantly associated association effect effects role roles analysis
data method methods approach model models system systems patients patient cells cell
one two three first second also however both such other others due both within without
""".split())


def load_all() -> list[dict]:
    items: list[dict] = []
    for f in sorted(LIT_DIR.glob("*.json")):
        try:
            payload = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  [WARN] {f.name} 解析失败，跳过")
            continue
        items.extend(payload.get("items", []))
    return items


def topic_words(items: list[dict], n: int = 12) -> list[list]:
    c: Counter[str] = Counter()
    for it in items:
        for w in re.findall(r"[A-Za-z][A-Za-z\-]{3,}", it.get("title", "").lower()):
            if w not in STOP and len(w) > 3:
                c[w] += 1
    return [[w, k] for w, k in c.most_common(n)]


def brief(it: dict) -> dict:
    """面板用精简条目（三层信息结构的第一层与第三层：一句话 + 出处）。"""
    return {
        "title": it.get("title", ""),
        "summary_zh": it.get("summary_zh", ""),
        "source": it.get("source", ""),
        "tier": it.get("tier", ""),
        "field": it.get("field_llm") or it.get("field"),
        "url": it.get("url", ""),
        "doi": it.get("doi", ""),
        "published": it.get("published", ""),
        "importance": it.get("importance", 0),
        "abstract": (it.get("abstract") or "")[:1200],
        "authors": (it.get("authors") or "")[:200],
    }


def main() -> int:
    items = load_all()
    print(f"载入 {len(items)} 条文献记录")

    # 去重（跨日文件可能重复收录同一 DOI）
    seen, uniq = set(), []
    for it in items:
        key = (it.get("doi") or "").lower() or re.sub(
            r"[^a-z0-9]", "", (it.get("title") or "").lower())[:80]
        if key and key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    print(f"跨日去重后 {len(uniq)} 条")

    by_day: dict[str, list] = defaultdict(list)
    by_month: dict[str, list] = defaultdict(list)
    by_year: dict[str, list] = defaultdict(list)
    undated = []
    for it in uniq:
        d = (it.get("published") or "").strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
            undated.append(it)
            continue
        by_day[d].append(it)
        by_month[d[:7]].append(it)
        by_year[d[:4]].append(it)

    def field_counts(group: list[dict]) -> dict:
        c: Counter[str] = Counter()
        for x in group:
            c[(x.get("field_llm") or x.get("field")) or "未分类"] += 1
        return dict(c.most_common())

    layers = {
        "_meta": {
            "built_at": date.today().isoformat(),
            "total": len(uniq),
            "undated": len(undated),
            "days": len(by_day), "months": len(by_month), "years": len(by_year),
        },
        "daily": {}, "monthly": {}, "yearly": {},
    }

    for d, group in sorted(by_day.items(), reverse=True):
        ranked = sorted(group, key=lambda x: -x.get("importance", 0))
        layers["daily"][d] = {
            "count": len(group),
            "by_field": field_counts(group),
            "by_tier": dict(Counter(x.get("tier", "") for x in group)),
            "items": [brief(x) for x in ranked[:120]],
        }

    for m, group in sorted(by_month.items(), reverse=True):
        ranked = sorted(group, key=lambda x: -x.get("importance", 0))
        layers["monthly"][m] = {
            "count": len(group),
            "by_field": field_counts(group),
            "by_tier": dict(Counter(x.get("tier", "") for x in group)),
            "topics": topic_words(group, 15),
            "top_items": [brief(x) for x in ranked[:40]],
        }

    for y, group in sorted(by_year.items(), reverse=True):
        ranked = sorted(group, key=lambda x: -x.get("importance", 0))
        trend: dict[str, dict] = defaultdict(dict)
        for m, g in by_month.items():
            if m.startswith(y):
                for f, n in field_counts(g).items():
                    trend[f][m] = n
        layers["yearly"][y] = {
            "count": len(group),
            "by_field": field_counts(group),
            "by_source": dict(Counter(x.get("source", "") for x in group).most_common(25)),
            "field_trend": {k: dict(sorted(v.items())) for k, v in trend.items()},
            "topics": topic_words(group, 25),
            "top_items": [brief(x) for x in ranked[:60]],
        }

    OUT.write_text(json.dumps(layers, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"写出 {OUT}")
    print(f"  日 {len(by_day)} / 月 {len(by_month)} / 年 {len(by_year)} | 无发表日 {len(undated)}")
    for d in sorted(by_day, reverse=True)[:3]:
        print(f"  {d}: {len(by_day[d])} 条 {field_counts(by_day[d])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
