#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清理 active 但无可追踪观点的名册成员（Chao 2026-09-14 批准）。

★ 删前已做的核实（不可跳过——名册只增不减是默认纪律，删是例外）：
  1. 抽样 20 人查 EuropePMC，12 人「全时段」有观点型发表 → 一度怀疑抓取漏人；
  2. 再用【与抓取脚本完全相同的查询】（含 18 个月 FIRST_PDATE 窗口）复测，
     van Duijn / Bruce Miller 等均为 0 条，最近观点型发表在 2024-03 与 2022。
  → 结论：不是抓取 bug，是这些人近 18 个月确无观点型发表。可以清理。

处理方式：
  · 不物理删除，置 active=False + removal_reason + removed_on，历史可追溯；
  · 落盘 data/kol_removed_<date>.json 留痕；
  · 日后他们发表新观点，把 active 改回 True 即可，其抓取历史仍在。
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "kol_registry.json"


def main() -> int:
    apply = "--apply" in sys.argv
    reg = json.loads(REG.read_text(encoding="utf-8"))
    people = reg["people"]

    sf = sorted((ROOT / "data" / "statements").glob("*.json"))
    have = set()
    for f in sf:
        for s in json.loads(f.read_text(encoding="utf-8")):
            if s.get("person_id"):
                have.add(s["person_id"])

    targets = [p for p in people if p.get("active") and p["id"] not in have]
    print(f"名册 {len(people)} 人｜有观点 {len(have)} 人｜待清理 {len(targets)} 人")
    by_field: dict[str, int] = {}
    for p in targets:
        f = p.get("field") or "未分类"
        by_field[f] = by_field.get(f, 0) + 1
    print("  按门类：" + "、".join(f"{k} {v}" for k, v in
                                sorted(by_field.items(), key=lambda x: -x[1])))
    print("  无 ORCID：%d｜有 ORCID 但窗口内无观点型发表：%d"
          % (sum(1 for p in targets if not p.get("orcid")),
             sum(1 for p in targets if p.get("orcid"))))

    if not apply:
        print("\n预演模式。确认无误后加 --apply 执行。")
        for p in targets[:8]:
            print(f"    {p.get('name_en'):34s} {p.get('field')}")
        return 0

    shutil.copy(REG, REG.with_suffix(".json.bak"))
    today = date.today().isoformat()
    snap = []
    for p in targets:
        snap.append(dict(p))
        p["active"] = False
        p["removal_reason"] = ("近 18 个月无可追踪的观点型发表"
                               "（已用与抓取脚本相同的查询复核，非抓取遗漏）")
        p["removed_on"] = today
    out = ROOT / "data" / f"kol_removed_{today}.json"
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    REG.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")

    left = [p for p in people if p.get("active")]
    print(f"\n已清理 {len(targets)} 人｜留痕 {out.name}｜备份 kol_registry.json.bak")
    print(f"名册现状：总 {len(people)} 人，active {len(left)} 人")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
