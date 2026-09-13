#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 Forecast-Checker 迁入 10 位科学从业者（Chao 2026-09-13 拍板的方案一）。

★ 只【复制】不删：FC 侧的摘除须经 Chao 明确确认后再单独执行，
  避免「两边都没有」的窗口期。迁入者标 origin=forecast-checker 可追溯。
★ AI 界（Kurzweil/Goertzel/Amodei/Kevin Kelly）按 Chao 决定【不迁】，
  理由：与已在跑的 AI-News KOL 项目重复。
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from roster import assign_stars, load_roster, save_roster, weighted  # noqa: E402

FC = Path("/home/user/Projects/Forecast-Checker/data/backfill_full.json")

# FC display_name 关键字 → (门类, 四维分, 迁入理由)
# 四维：A 学术根基 / B 一手性 / C 公共表达 / D 方法透明
MIGRATE = {
    "Dean Radin": ("神经认知", {"A": 7, "B": 8, "C": 8, "D": 6},
                   "IONS 首席科学家，超心理学元分析与预感实验的主要一手研究者"),
    "Julia Mossbridge": ("神经认知", {"A": 7, "B": 8, "C": 7, "D": 7},
                         "神经科学家，预感生理反应（presentiment）实验与元分析作者"),
    "Stanley": ("神经认知", {"A": 8, "B": 8, "C": 5, "D": 6},
                "心理学教授，主持梦心灵感应与预知梦经典实验（高龄，在世状态需复核）"),
    "Larry Dossey": ("医学健康", {"A": 6, "B": 5, "C": 7, "D": 5},
                     "医师、作家，意识与健康交叉领域公共表达者"),
    "Federico Faggin": ("物理天文", {"A": 9, "B": 7, "C": 8, "D": 6},
                        "物理学博士，Intel 4004 首款商用微处理器设计者，转向意识理论研究"),
    "Puthoff": ("物理天文", {"A": 8, "B": 8, "C": 6, "D": 5},
                "物理学家，SRI 遥视研究项目负责人，激光与零点能领域发表者"),
    "Russell Targ": ("物理天文", {"A": 8, "B": 8, "C": 7, "D": 5},
                     "激光物理学家，SRI 遥视研究共同创始人，'remote viewing' 一词创造者"),
    "Stephan A. Schwartz": ("神经认知", {"A": 6, "B": 8, "C": 8, "D": 6},
                            "意识科学研究者，将遥视方法应用于考古学的一手实践者"),
    "Courtney Brown": ("神经认知", {"A": 6, "B": 6, "C": 7, "D": 4},
                       "埃默里大学副教授，Farsight Institute 创始人（方法受科学界质疑，如实标注）"),
    "Julian Jaynes": ("神经认知", {"A": 9, "B": 7, "C": 6, "D": 5},
                      "耶鲁/普林斯顿心理学家，二分心智假说提出者（已故，列为经典档）"),
}

CONTROVERSY = {
    "Courtney Brown": "遥视方法与公开主张长期受主流科学界质疑，结论未获同行评审复现",
    "Dean Radin": "超心理学元分析结论受统计方法争议；主流心理学界对效应量存疑",
    "Puthoff": "SRI 遥视项目的实验设计曾被批评存在信息泄漏（sensory leakage）",
}


def main() -> int:
    if not FC.exists():
        print(f"找不到 {FC}")
        return 1
    src = json.loads(FC.read_text(encoding="utf-8"))
    fc_people = src if isinstance(src, list) else src["people"]

    roster = load_roster()
    existing = {p["id"] for p in roster["people"]}
    added, missed = [], []

    for key, (field, scores, reason) in MIGRATE.items():
        hit = next((p for p in fc_people
                    if key.lower() in (p.get("display_name") or "").lower()), None)
        if not hit:
            missed.append(key)
            continue
        pid = hit["id"]
        if pid in existing:
            continue
        person = {
            "id": pid,
            "name_zh": hit.get("display_name", ""),
            "name_en": hit.get("display_name", ""),
            "field": field,
            "bio": hit.get("bio", ""),
            "affiliation": "",
            "alive": hit.get("alive", True),
            "active": True,
            "origin": "forecast-checker",
            "origin_note": reason,
            "migrated_on": date.today().isoformat(),
            "official_url": hit.get("official_url", ""),
            "search_terms": [hit.get("display_name", "")],
            "score_A": scores["A"], "score_B": scores["B"],
            "score_C": scores["C"], "score_D": scores["D"],
            "weighted_score": weighted(scores),
            "controversies": CONTROVERSY.get(key, ""),
            "statements": [],
            "fc_prediction_count": len(hit.get("predictions", [])),
        }
        roster["people"].append(person)
        added.append(person)

    if added:
        assign_stars(roster["people"])
        roster["_migrated_from_fc"] = {
            "on": date.today().isoformat(),
            "count": len(added),
            "note": "只复制未删除；FC 侧摘除需 Chao 单独确认",
        }
        save_roster(roster)

    print(f"迁入 {len(added)} 人：")
    for p in sorted(added, key=lambda x: -x["weighted_score"]):
        print(f"  {'★' * p['rating']:5s} {p['weighted_score']:5.2f} [{p['field']:6s}] "
              f"{p['name_zh'][:28]:30s} FC预言{p['fc_prediction_count']}条")
    if missed:
        print(f"\n未在 FC 找到（需人工核对）: {missed}")
    print(f"\n名册现有 {roster['count']} 人")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
