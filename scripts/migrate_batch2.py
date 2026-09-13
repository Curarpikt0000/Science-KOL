#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第二批从 Forecast-Checker 迁入（Chao 2026-09-13 指定）。

Venki Ramakrishnan → 生命科学：2009 诺贝尔化学奖（核糖体结构）、前英国皇家学会会长。
  其论断是【实证科学判断】而非玄学预测：寿命硬上限 110-120、消除全部老年慢性病
  也只多活约 15 年、意识上传与人体冷冻无科学依据。
  ★ 判定时必须带上他自己给的限定：他明确说过「这不意味着存在物理或化学定律规定
    我们不能活过 110——鲸鱼和鲨鱼能活几百年」。不可当成教条式否定者。
  ★ 他自陈中立的理由：「我研究蛋白质合成，与衰老相关但我本人不研究衰老，
    这让我在意识形态上没那么有偏向。」

Neil deGrasse Tyson → 物理天文：天体物理学家、科普主持人。
  ★ 如实标注：其收录条目偏【商业/产业预测】（小行星采矿造就首位万亿富翁；
    同时警告盈利性太空产业比人们以为的遥远、早期进入者未必获利），
    而非科学论断。两条并存构成张力，不可只摘「万亿富翁」金句造成片面印象。

FC 侧按 Chao 指示【保留不删】。
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from roster import assign_stars, load_roster, save_roster, weighted  # noqa: E402

FC = Path("/home/user/Projects/Forecast-Checker/data/backfill_full.json")

MIGRATE = {
    "Ramakrishnan": {
        "field": "生命科学",
        "scores": {"A": 10.0, "B": 8.0, "C": 9.0, "D": 8.0},
        "orcid": "0000-0002-4699-2194",   # 实查 OpenAlex，MRC 分子生物学实验室，h=87
        "affiliation": "MRC 分子生物学实验室（剑桥）",
        "note": "2009 诺贝尔化学奖（核糖体结构）、前英国皇家学会会长；"
                "《Why We Die》作者，长寿主张的权威反方",
        "stance": "科学界怀疑论者",
        "caveat": "他明确留有口子：「这不意味着存在物理或化学定律规定我们不能活过 110"
                  "——鲸鱼和鲨鱼能活几百年」。判定其预测时须带此限定，勿当教条式否定者。",
        "self_declared_neutrality": "我研究蛋白质合成，与衰老相关但我本人不研究衰老，"
                                    "这让我在意识形态上没那么有偏向。",
    },
    "Tyson": {
        "field": "物理天文",
        "scores": {"A": 7.5, "B": 5.0, "C": 10.0, "D": 6.0},
        "orcid": "",
        "affiliation": "海登天文馆（美国自然历史博物馆）",
        "note": "天体物理学家、科普主持人；收录条目偏产业预测而非科学论断",
        "stance": "科学传播者",
        "caveat": "收录的 2 条为太空产业商业预测，且互为张力："
                  "既预言小行星采矿造就首位万亿富翁，又警告盈利性太空产业比人们以为的"
                  "遥远、早期进入者未必获利。引用时不可只摘前者。",
        "self_declared_neutrality": "",
    },
}


def main() -> int:
    src = json.loads(FC.read_text(encoding="utf-8"))
    fc_people = src if isinstance(src, list) else src["people"]
    roster = load_roster()
    existing = {p["id"] for p in roster["people"]}
    added = []

    for key, cfg in MIGRATE.items():
        hit = next((p for p in fc_people
                    if key.lower() in (p.get("display_name") or "").lower()), None)
        if not hit:
            print(f"[WARN] FC 中找不到 {key}")
            continue
        if hit["id"] in existing:
            print(f"  {key} 已在名册，跳过")
            continue
        person = {
            "id": hit["id"],
            "name_zh": hit.get("display_name", ""),
            "name_en": hit.get("display_name", "").split(" ")[0] + " "
                       + (hit.get("display_name", "").split(" ")[1]
                          if len(hit.get("display_name", "").split(" ")) > 1 else ""),
            "field": cfg["field"],
            "bio": hit.get("bio", ""),
            "affiliation": cfg["affiliation"],
            "affiliation_verified": True,     # 人工填写，非自动抓取
            "alive": True,
            "active": True,
            "origin": "forecast-checker-batch2",
            "origin_note": cfg["note"],
            "stance": cfg["stance"],
            "interpretation_caveat": cfg["caveat"],
            "self_declared_neutrality": cfg["self_declared_neutrality"],
            "orcid": cfg["orcid"],
            "official_url": hit.get("official_url", ""),
            "search_terms": [hit.get("display_name", "").split(" ")[0]],
            "score_A": cfg["scores"]["A"], "score_B": cfg["scores"]["B"],
            "score_C": cfg["scores"]["C"], "score_D": cfg["scores"]["D"],
            "weighted_score": weighted(cfg["scores"]),
            "controversies": "",
            "statements": [],
            "fc_prediction_count": len(hit.get("predictions", [])),
            "fc_predictions_snapshot": [
                {"quote": pr.get("quote", ""), "target": pr.get("target_year")
                 or pr.get("target_date", ""), "source_url": pr.get("source_url", "")}
                for pr in hit.get("predictions", [])
            ],
            "migrated_on": date.today().isoformat(),
        }
        roster["people"].append(person)
        added.append(person)

    if added:
        assign_stars(roster["people"])
        save_roster(roster)
    for p in added:
        print(f"  迁入 {'★' * p['rating']} {p['weighted_score']:.2f} "
              f"[{p['field']}] {p['name_zh']}（FC 预言 {p['fc_prediction_count']} 条已快照）")
    print(f"名册现 {roster['count']} 人 / active {roster['active_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
