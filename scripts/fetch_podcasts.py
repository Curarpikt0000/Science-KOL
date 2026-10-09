#!/usr/bin/env python3
"""播客言论抓取（日链第 3b 步；Chao 2026-09-25 批「可以」）。

在 fetch_statements.py（第 3 步）之后跑：把新抓到的播客言论【追加】进当日观点文件。
  · 每天限量转写（SK_POD_MAX_EPS，默认 4 集），CPU 本机 faster-whisper，约 3.6 秒/分钟音频
  · 处理过的剧集（无论入库还是拒收）记进 data/podcast_seen.json，第二天不重复转写
  · 单集失败只警告，不掀翻日链
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import sources_podcast as sp  # noqa: E402

S_DIR = ROOT / "data" / "statements"
SEEN = ROOT / "data" / "podcast_seen.json"
REJECTED = ROOT / "data" / "statements_rejected.json"
MAX_EPS = int(os.environ.get("SK_POD_MAX_EPS", "4"))
DAYS = int(os.environ.get("SK_POD_DAYS", "60"))


def main() -> int:
    if not os.environ.get("GENAI_PROXY"):
        print("[WARN] 未设置 GENAI_PROXY，播客步骤跳过")
        return 0
    reg = json.loads((ROOT / "data" / "kol_registry.json").read_text(encoding="utf-8"))
    people = [p for p in reg["people"] if p.get("active")]
    only_id = os.environ.get("SK_ONLY_ID")      # 按人单跑/回填；日链不设
    if only_id:
        ids = {x.strip() for x in only_id.split(",") if x.strip()}
        people = [p for p in people if p["id"] in ids]
        assert people, f"SK_ONLY_ID 没匹配到在册的人: {only_id}"
    seen = json.loads(SEEN.read_text(encoding="utf-8")) if SEEN.exists() else {}

    out = S_DIR / f"{date.today().isoformat()}.json"
    today_rows = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
    have = {r.get("url") for r in today_rows}
    have_ep = {r.get("episode_url") for r in today_rows if r.get("episode_url")}

    # 先列候选（便宜），再按上架日新→旧排，限量处理（贵）
    cands = []
    for p in people:
        try:
            for e in sp.search_episodes(p, days=DAYS):
                if e["page"] in seen or e["page"] in have_ep:
                    continue
                cands.append((e["published"], p, e))
        except Exception as ex:  # noqa: BLE001
            print(f"  [WARN] {p.get('name_en')} 搜索失败：{ex}")
        time.sleep(0.4)
    cands.sort(key=lambda x: x[0], reverse=True)
    print(f"候选剧集 {len(cands)} 集（未处理过的），本轮上限 {MAX_EPS} 集")

    added, rejected, done = [], [], 0
    t0 = time.time()
    for _, p, e in cands:
        if done >= MAX_EPS:
            break
        try:
            kept, rej = sp.podcast_statements(p, days=DAYS, known_urls=set(), max_eps=1,
                                              only_episode=e)
        except Exception as ex:  # noqa: BLE001
            print(f"  [WARN] {p.get('name_en')}｜{e['title'][:40]} 处理异常：{ex}")
            continue
        done += 1
        seen[e["page"]] = {"person_id": p["id"], "processed_on": date.today().isoformat(),
                           "kept": len(kept)}
        new = [r for r in kept if r["url"] not in have]
        added += new
        have |= {r["url"] for r in new}
        rejected += rej
        print(f"  {p.get('name_en', '')[:22]:22s}｜{e['show'][:22]:22s}｜入库 {len(new)} 拒收 {len(rej)}"
              f"  ({time.time() - t0:.0f}s)", flush=True)

    if added:
        today_rows.extend(added)
        out.write_text(json.dumps(today_rows, ensure_ascii=False, indent=1), encoding="utf-8")
    SEEN.write_text(json.dumps(seen, ensure_ascii=False, indent=1), encoding="utf-8")
    if rejected:
        old = json.loads(REJECTED.read_text(encoding="utf-8")) if REJECTED.exists() else []
        REJECTED.write_text(json.dumps(old + rejected, ensure_ascii=False, indent=1), encoding="utf-8")
    left = max(0, len(cands) - done)
    print(f"播客本轮：处理 {done} 集，新增言论 {len(added)} 条，剩余待处理 {left} 集")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
