#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单独重抓 L3 原文全文翻译（不动已生成的 L1/L2）。

用途：抓取器修好后，只补 L3 这一层，不浪费配额重生成 L1/L2。
判据：有 url 且能取到全文 → 译；取不到 → 如实标 abstract_only。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_four_layers import P_L3, fetch_fulltext, has_cn, llm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    lim = int(os.environ.get("SK_L3_LIMIT", "100"))
    f = sorted((ROOT / "data" / "statements").glob("*.json"))[-1]
    rows = json.loads(f.read_text(encoding="utf-8"))
    todo = [r for r in rows
            if not has_cn(r.get("l3_translation")) and r.get("url")][:lim]
    print(f"[L3] {f.name}：候选 {len(todo)} 条")
    ok = skip = 0
    for i, r in enumerate(todo, 1):
        ft = fetch_fulltext(r.get("url", ""))
        if not ft:
            r["l3_status"] = "abstract_only"
            skip += 1
            continue
        tr = llm(P_L3.format(body=ft[:9000]), 4000, retries=4)
        if has_cn(tr):
            r["l3_translation"] = tr.strip()
            r["l3_status"] = "full"
            ok += 1
        else:
            # ★ 实测（2026-09-14）：同样输入同样参数，一次失败一次成功
            #   → 是代理偶发故障，不是内容或参数问题。多给几次机会，
            #   并落 pending 状态而非 failed，下轮还会重试。
            r["l3_status"] = "pending_retry"
        time.sleep(1.5)
        if ok and ok % 10 == 0:
            print(f"    {i}/{len(todo)} 成功 {ok}", flush=True)
    f.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[L3] 全文译出 {ok} 条｜无全文可取 {skip} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
