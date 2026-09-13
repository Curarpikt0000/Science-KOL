#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中文覆盖率门禁：面板展开层若出现英文正文即报警。

★ Chao 铁律（2026-09-13）：所有展开层内容必须是中文。
  写成门禁而非文档，因为靠人记得检查迟早会破例。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CN = re.compile(r"[\u4e00-\u9fff]")


def has_cn(s):
    return bool(CN.search(s or ""))


def main() -> int:
    bad = []

    sf = sorted((ROOT / "data" / "statements").glob("*.json"))
    if sf:
        rows = json.loads(sf[-1].read_text(encoding="utf-8"))
        no_t = [r for r in rows if not has_cn(r.get("title_zh"))]
        no_b = [r for r in rows if not has_cn(r.get("summary_zh"))]
        print(f"观点 {len(rows)} 条：中文标题 {len(rows)-len(no_t)} | "
              f"中文摘要 {len(rows)-len(no_b)}")
        if no_t:
            bad.append(f"观点缺中文标题 {len(no_t)} 条")
        if no_b:
            bad.append(f"观点缺中文摘要 {len(no_b)} 条")

    lay = ROOT / "data" / "layers" / "literature_layers.json"
    if lay.exists():
        L = json.loads(lay.read_text(encoding="utf-8"))
        shown = []
        for k in ("daily", "monthly", "yearly"):
            for b in (L.get(k) or {}).values():
                shown += (b.get("items") or b.get("top_items") or [])
        uniq = {i.get("url"): i for i in shown if isinstance(i, dict)}.values()
        no_t = [r for r in uniq if not has_cn(r.get("title_zh"))]
        no_s = [r for r in uniq if not has_cn(r.get("summary_zh"))]
        print(f"文献展示 {len(uniq)} 条：中文标题 {len(uniq)-len(no_t)} | "
              f"中文摘要 {len(uniq)-len(no_s)}")
        if no_t:
            bad.append(f"文献缺中文标题 {len(no_t)} 条")
        if no_s:
            bad.append(f"文献缺中文摘要 {len(no_s)} 条")

    if bad:
        print("\n未达标：")
        for b in bad:
            print("  -", b)
        print("修复：.venv/bin/python3 scripts/translate_to_zh.py all")
        return 1
    print("\n全部展开层均为中文 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
