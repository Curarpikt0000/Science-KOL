#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把候选池中通过 C 维门槛的人打四维分并入册（3★ 及以上才进名册）。

A 学术根基 30%：由 h-index / 引用量在【本门类候选池内的百分位】换算，
                不用绝对切点（理由同星级：h=200 算高算低取决于学科）。
B 一手性   25%：近 3 年产出强度 + 是否有 ORCID（一手研究者的身份锚）
C 公共表达 30%：probe_public_voice.py 实测所得，不可臆造
D 方法透明 15%：ORCID 公开 + 机构可核 + 无同名污点，实测项
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from roster import assign_stars, load_roster, save_roster, weighted  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "candidates_raw.json"
REJECTED = ROOT / "data" / "candidates_rejected.json"


def pct_score(value: float, pool: list[float]) -> float:
    """在池内百分位 → 0-10 分。"""
    if not pool:
        return 0.0
    below = sum(1 for v in pool if v < value)
    return round(below / len(pool) * 10, 1)


def main() -> int:
    field = sys.argv[1] if len(sys.argv) > 1 else "医学健康"
    if not RAW.exists():
        print("先跑 build_candidates.py")
        return 1
    pool_all = json.loads(RAW.read_text(encoding="utf-8"))
    cands = [c for c in pool_all.get(field, []) if "score_C" in c]
    if not cands:
        print(f"{field} 没有已探测的候选，先跑 probe_public_voice.py")
        return 1

    h_pool = [c["h_index"] for c in cands]
    cite_pool = [c["cited_by_count"] for c in cands]
    rec_pool = [c["recent_works_3y"] for c in cands]

    scored = []
    for c in cands:
        a = round((pct_score(c["h_index"], h_pool) * 0.6
                   + pct_score(c["cited_by_count"], cite_pool) * 0.4), 1)
        b = round(pct_score(c["recent_works_3y"], rec_pool) * 0.8
                  + (2.0 if c.get("orcid") else 0.0), 1)
        b = min(b, 10.0)
        d = 0.0
        if c.get("orcid"):
            d += 4.0
        if c.get("institution_raw"):
            d += 3.0
        if not c.get("probe", {}).get("homonym_flag"):
            d += 3.0
        scores = {"A": a, "B": b, "C": c["score_C"], "D": round(d, 1)}
        c["score_A"], c["score_B"], c["score_D"] = a, b, round(d, 1)
        c["weighted_score"] = weighted(scores)
        scored.append(c)

    # 先在候选池内定星，再按 3★ 门槛过滤
    assign_stars(scored)
    passed = [c for c in scored if c["rating"] >= 3 and c.get("trackable")]
    rejected = [c for c in scored if c not in passed]

    roster = load_roster()
    existing = {p["id"] for p in roster["people"]}
    added = 0
    for c in passed:
        pid = f"oa-{c['openalex_id']}"
        if pid in existing:
            continue
        roster["people"].append({
            "id": pid,
            "name_zh": "", "name_en": c["name_en"],
            "field": field,
            "bio": "",
            "affiliation": c.get("institution_raw", ""),
            "affiliation_verified": False,   # OpenAlex 机构字段有脏值，须人工/二次核验
            "country": c.get("country", ""),
            "alive": None,                   # 未核实（OpenAlex 不给在世状态，实测有已故者混入）
            "active": True,
            "origin": "openalex-candidate",
            "orcid": c.get("orcid", ""),
            "openalex_url": c.get("openalex_url", ""),
            "h_index": c["h_index"],
            "cited_by_count": c["cited_by_count"],
            "recent_works_3y": c["recent_works_3y"],
            "topics": c.get("topics", []),
            "search_terms": [c["name_en"]],
            "score_A": c["score_A"], "score_B": c["score_B"],
            "score_C": c["score_C"], "score_D": c["score_D"],
            "weighted_score": c["weighted_score"],
            "public_voice_evidence": c.get("probe", {}),
            "controversies": "",
            "statements": [],
            "added_on": date.today().isoformat(),
        })
        added += 1

    if added:
        assign_stars(roster["people"])
        save_roster(roster)

    # 落选留痕
    old_rej = json.loads(REJECTED.read_text(encoding="utf-8")) if REJECTED.exists() else {}
    old_rej[field] = [{"name_en": c["name_en"], "h_index": c["h_index"],
                       "weighted_score": c["weighted_score"], "rating": c["rating"],
                       "trackable": c.get("trackable"),
                       "reason": "C维不达标(无法追踪)" if not c.get("trackable") else "星级<3",
                       "probe": c.get("probe", {})} for c in rejected]
    REJECTED.write_text(json.dumps(old_rej, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"=== {field} ===")
    print(f"候选 {len(scored)} → 入册 {added} 人，落选 {len(rejected)} 人（已留痕）")
    print(f"\n入册名单（{field}）：")
    for c in sorted(passed, key=lambda x: -x["weighted_score"]):
        print(f"  {'★' * c['rating']:5s} {c['weighted_score']:5.2f} "
              f"A{c['score_A']:4.1f} B{c['score_B']:4.1f} C{c['score_C']:4.1f} D{c['score_D']:4.1f} "
              f"| {c['name_en'][:26]:28s} h={c['h_index']:3d} {c.get('institution_raw', '')[:22]}")
    print(f"\n名册总计 {roster['count']} 人")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
