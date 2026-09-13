#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Science-KOL 名册 SSOT 与四维评分。

★ 为什么不直接照搬 War-KOL 的四维：
  War-KOL 的 C 维是「历史预测命中率」，那是给战争预测者设计的。科学家不靠预测吃饭，
  硬套会把从不做公开预测的诺奖得主评成低分。故本项目重设四维，锚科学界的真实信誉机制
  （同行评审、引用、可复现、利益冲突披露），权重经 Chao 确认前以此为准。

四维（每维 0-10）：
  A 学术根基 30% — 机构任职、同行评审产出、重大奖项（诺奖/图灵/菲尔兹/拉斯克等）
  B 一手性   25% — 是否本人实验室的原创研究；一手数据 vs 转述科普
  C 公共表达 30% — 是否持续对外发表可追溯的实质观点（论文之外的访谈/博客/证词）
                   ——没有公开表达的科学家再牛也无法 track，这是本项目的可行性维度
  D 方法透明 15% — 数据/代码公开、利益冲突披露、公开更正记录

星级 = 群体内百分位（前10%=5★ /10-30%=4★ /30-60%=3★ /60-85%=2★ /其余1★），
不用绝对切点，理由同 War-KOL：绝对分「7 分算好算坏」没有客观答案。

入库门槛：只收 3★ 及以上；低于门槛写 data/candidates_rejected.json 留痕。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROSTER = ROOT / "data" / "kol_registry.json"
REJECTED = ROOT / "data" / "candidates_rejected.json"

FIELDS = ["医学健康", "生命科学", "AI计算机", "物理天文",
          "化学材料", "神经认知", "地球气候", "数学基础理论"]

WEIGHTS = {"A": 0.30, "B": 0.25, "C": 0.30, "D": 0.15}


def weighted(scores: dict) -> float:
    return round(sum(scores.get(k, 0) * w for k, w in WEIGHTS.items()), 2)


def assign_stars(people: list[dict]) -> None:
    """群体内百分位定星。people 需已有 weighted_score。"""
    ranked = sorted(people, key=lambda p: -p.get("weighted_score", 0))
    n = len(ranked)
    for i, p in enumerate(ranked):
        pct = (i + 1) / n
        if pct <= 0.10:
            p["rating"] = 5
        elif pct <= 0.30:
            p["rating"] = 4
        elif pct <= 0.60:
            p["rating"] = 3
        elif pct <= 0.85:
            p["rating"] = 2
        else:
            p["rating"] = 1
        p["rating_pct"] = round(pct * 100, 1)


def load_roster() -> dict:
    if ROSTER.exists():
        return json.loads(ROSTER.read_text(encoding="utf-8"))
    return {"_ssot": "data/kol_registry.json", "count": 0, "people": []}


def save_roster(data: dict) -> None:
    """名册只增不减：写入前校验不会丢人（沿用 Eco/War-KOL 铁律）。"""
    if ROSTER.exists():
        old = json.loads(ROSTER.read_text(encoding="utf-8"))
        old_ids = {p["id"] for p in old.get("people", [])}
        new_ids = {p["id"] for p in data.get("people", [])}
        lost = old_ids - new_ids
        if lost:
            raise SystemExit(f"拒绝写入：会丢失 {len(lost)} 人 {sorted(lost)[:5]}…（名册只增不减）")
    data["count"] = len(data.get("people", []))
    data["active_count"] = sum(1 for p in data["people"] if p.get("active"))
    ROSTER.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    d = load_roster()
    print(f"名册 {d.get('count', 0)} 人 / active {d.get('active_count', 0)}")
    by_field: dict[str, int] = {}
    for p in d.get("people", []):
        by_field[p.get("field", "?")] = by_field.get(p.get("field", "?"), 0) + 1
    for k, v in sorted(by_field.items(), key=lambda x: -x[1]):
        print(f"  {k:12s} {v}")
