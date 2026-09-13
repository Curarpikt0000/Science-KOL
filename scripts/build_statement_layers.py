#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KOL 观点日/月/年三层聚合。

与文献三层的区别（刻意不照搬）：
  文献层的主角是【论文】，聚合看的是数量与主题分布；
  观点层的主角是【人】，聚合要回答「这段时间谁在发声、都在说什么」，
  所以每个时间桶里必须带上发声人排行与门类分布，而不只是计数。

时间口径铁律：
  · 一律按【实际发表日】分档，绝不用抓取日顶替。
  · 发表日取不到的条目单独归入 undated 桶，在面板上如实显示，不塞进任一时间桶。
"""
from __future__ import annotations

import collections
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STMT_DIR = ROOT / "data" / "statements"
REGISTRY = ROOT / "data" / "kol_registry.json"
OUT = ROOT / "data" / "layers" / "statement_layers.json"


def load_statements() -> list[dict]:
    rows, seen = [], set()
    if not STMT_DIR.exists():
        return rows
    for f in sorted(STMT_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for r in data:
            k = (r.get("doi") or r.get("url") or "").lower()
            if not k or k in seen:
                continue
            seen.add(k)
            rows.append(r)
    return rows


def bucket(rows: list[dict], fmap: dict, star: dict, key_len: int) -> dict:
    """按 published 前 key_len 位分桶（10=日, 7=月, 4=年）。"""
    out: dict[str, dict] = {}
    for r in rows:
        pub = r.get("published") or ""
        if len(pub) < key_len:
            continue
        k = pub[:key_len]
        b = out.setdefault(k, {"count": 0, "by_field": {}, "by_channel": {},
                               "by_person": {}, "items": []})
        b["count"] += 1
        fld = fmap.get(r.get("person_id")) or "未归类"
        b["by_field"][fld] = b["by_field"].get(fld, 0) + 1
        ch = r.get("channel") or "未知"
        b["by_channel"][ch] = b["by_channel"].get(ch, 0) + 1
        nm = r.get("person_name") or "?"
        b["by_person"][nm] = b["by_person"].get(nm, 0) + 1
        b["items"].append(r)

    for k, b in out.items():
        # 发声人排行：条数优先，同条数时星级高者在前
        b["top_persons"] = sorted(
            b["by_person"].items(),
            key=lambda x: (-x[1], -star.get(x[0], 0), x[0]))[:8]
        # 代表条目：星级高 + 正文长（有实质内容）优先
        b["items"].sort(
            key=lambda r: (-star.get(r.get("person_name"), 0),
                           -len(r.get("body") or ""),
                           r.get("published") or ""),
            reverse=False)
        keep = 40 if k.count("-") == 2 else 60
        b["items"] = b["items"][:keep]
        b.pop("by_person", None)
    return out


def main() -> int:
    rows = load_statements()
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    fmap = {p["id"]: p.get("field") for p in reg["people"]}
    star = {}
    for p in reg["people"]:
        nm = p.get("name_en") or p.get("name_zh") or ""
        star[nm] = int(p.get("rating") or 0)
        if p.get("name_zh"):
            star[p["name_zh"]] = star[nm]

    dated = [r for r in rows if r.get("published")]
    undated = [r for r in rows if not r.get("published")]

    layers = {
        "_meta": {
            "total": len(rows),
            "dated": len(dated),
            "undated": len(undated),
            "built_on": date.today().isoformat(),
            "note": "按实际发表日分档；发表日缺失者归入 undated，不塞进时间桶",
        },
        "daily": bucket(dated, fmap, star, 10),
        "monthly": bucket(dated, fmap, star, 7),
        "yearly": bucket(dated, fmap, star, 4),
        "undated": {
            "count": len(undated),
            "by_channel": dict(collections.Counter(
                r.get("channel") or "未知" for r in undated)),
            "items": undated[:40],
        },
    }

    # 年层补门类月度走势（看某门类是否在升温）
    for y, b in layers["yearly"].items():
        trend: dict[str, dict[str, int]] = {}
        for r in dated:
            if (r.get("published") or "")[:4] != y:
                continue
            fld = fmap.get(r.get("person_id")) or "未归类"
            m = r["published"][:7]
            trend.setdefault(fld, {})[m] = trend.setdefault(fld, {}).get(m, 0) + 1
        b["field_trend"] = trend

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(layers, ensure_ascii=False, indent=1), encoding="utf-8")
    m = layers["_meta"]
    print(f"写出 {OUT}")
    print(f"  总 {m['total']} 条 | 有发表日 {m['dated']} | 无发表日 {m['undated']}")
    print(f"  日 {len(layers['daily'])} / 月 {len(layers['monthly'])} "
          f"/ 年 {len(layers['yearly'])}")
    for mk in sorted(layers["monthly"], reverse=True)[:5]:
        b = layers["monthly"][mk]
        top = "、".join(f"{n}({c})" for n, c in b["top_persons"][:3])
        print(f"  {mk}: {b['count']} 条 | {top}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
