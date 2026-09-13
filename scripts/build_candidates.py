#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按门类生成 KOL 候选池（OpenAlex 学术数据 + 公开表达度校验）。

★ 为什么不用「LLM 凭印象列名单」：Chao 的硬规矩是【论断锚具名数据 + 可追溯出处】。
  本脚本的 A/B 维直接来自 OpenAlex 的客观指标（h-index、引用数、近年产出），
  C/D 维需实际探测公开表达渠道，绝不靠模型记忆编造。

★ 高引用 ≠ 能 track：C 维（公共表达）是本项目的可行性门槛——
  一个从不对外发声的诺奖得主，学术上再顶尖也无法做「观点追踪」。
  故候选必须实测到公开表达渠道才能进池。

★ OpenAlex 机构字段有脏值（实测见过 Grätzel 挂 "Nankai University"、
  Kroemer 挂 "Twitter"），故机构需交叉校验后再写入名册。
"""
from __future__ import annotations

import json
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "candidates_raw.json"
MAILTO = "science-kol-bot@example.com"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122"
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

# 门类 → OpenAlex 过滤表达式
# ★ 2026-09-13 实测：authors 端点【不支持】 topics.field.id（返回 400），
#   也不支持 x_concepts.id（返回 0）。可用的是 topics.id（具体 topic）。
#   故改用「先按 field 聚合出高产 topic → 再按 topic 拉作者」两步法。
#   另：直接按 works 聚合 authorships 会灌进垃圾账号
#   （实测 "叶兴阳双语音标有声读物" 5988 篇排第二），故不用那条路。
FIELD_ID = {
    "医学健康": "27",       # Medicine
    "生命科学": "13",       # Biochemistry, Genetics and Molecular Biology
    "AI计算机": "17",       # Computer Science
    "物理天文": "31",       # Physics and Astronomy
    "化学材料": "16",       # Chemistry
    "神经认知": "28",       # Neuroscience
    "地球气候": "19",       # Earth and Planetary Sciences
    "数学基础理论": "26",   # Mathematics
}
FIELD_QUERY = FIELD_ID  # 兼容旧引用


def fetch(url: str, timeout: int = 60, retries: int = 3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return urllib.request.urlopen(req, timeout=timeout, context=_CTX).read()
        except Exception:
            time.sleep(3 * (i + 1))
    return None


def top_topics(field: str, n: int = 6) -> list[str]:
    """先找该 field 下近两年最高产的 topic（两步法第一步）。"""
    fid = FIELD_ID[field]
    url = ("https://api.openalex.org/works?"
           f"filter=primary_topic.field.id:fields/{fid},publication_year:2025-2026"
           f"&group_by=primary_topic.id&per-page=50&mailto={MAILTO}")
    blob = fetch(url)
    if not blob:
        return []
    try:
        groups = json.loads(blob).get("group_by", [])
    except json.JSONDecodeError:
        return []
    return [g["key"].split("/")[-1] for g in groups[:n]]


def candidates_for(field: str, n: int = 40, min_h: int = 60) -> list[dict]:
    """拉该门类高影响力且近年仍活跃的学者（两步法第二步）。"""
    topics = top_topics(field)
    if not topics:
        print(f"  [WARN] {field} 取不到 topic")
        return []
    print(f"  topic: {', '.join(topics)}")
    seen: dict[str, dict] = {}
    for t in topics:
        url = ("https://api.openalex.org/authors?"
               f"filter=topics.id:{t},summary_stats.h_index:>{min_h}"
               f"&sort=summary_stats.h_index:desc&per-page={n}&mailto={MAILTO}")
        blob = fetch(url)
        if not blob:
            continue
        try:
            results = json.loads(blob).get("results", [])
        except json.JSONDecodeError:
            continue
        for a in results:
            aid = a.get("id", "").split("/")[-1]
            if aid in seen:
                continue
            seen[aid] = a
        time.sleep(1.0)

    out = []
    for aid, a in seen.items():
        st = a.get("summary_stats", {})
        insts = a.get("last_known_institutions") or []
        counts = {c["year"]: c["works_count"] for c in (a.get("counts_by_year") or [])}
        recent = sum(counts.get(y, 0) for y in (2024, 2025, 2026))
        # 灌水账号过滤：年产出高得离谱的多为机构合集/爬虫账号
        if recent > 400:
            continue
        out.append({
            "openalex_id": aid,
            "name_en": a.get("display_name", ""),
            "orcid": (a.get("orcid") or "").replace("https://orcid.org/", ""),
            "field": field,
            "h_index": st.get("h_index", 0),
            "i10": st.get("i10_index", 0),
            "cited_by_count": a.get("cited_by_count", 0),
            "works_count": a.get("works_count", 0),
            "recent_works_3y": recent,
            "institution_raw": insts[0].get("display_name", "") if insts else "",
            "country": insts[0].get("country_code", "") if insts else "",
            "topics": [t.get("display_name", "") for t in (a.get("topics") or [])[:4]],
            "openalex_url": a.get("id", ""),
            "_source": "openalex/authors (two-step topic)",
            "_fetched": time.strftime("%Y-%m-%d"),
        })
    out.sort(key=lambda x: -x["h_index"])
    return out


def main() -> int:
    fields = sys.argv[1:] or list(FIELD_QUERY)
    pool: dict[str, list] = {}
    if OUT.exists():
        pool = json.loads(OUT.read_text(encoding="utf-8"))
    for f in fields:
        if f not in FIELD_QUERY:
            print(f"未知门类 {f}，可选：{list(FIELD_QUERY)}")
            continue
        print(f"=== {f} ===")
        got = candidates_for(f)
        active = [c for c in got if c["recent_works_3y"] >= 3]
        pool[f] = active
        print(f"  拉到 {len(got)} 人，近3年仍活跃 {len(active)} 人")
        for c in active[:8]:
            print(f"    h={c['h_index']:3d} 近3年{c['recent_works_3y']:4d}篇 "
                  f"{c['name_en'][:26]:28s} {c['institution_raw'][:26]}")
        time.sleep(1.2)

    OUT.write_text(json.dumps(pool, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n写出 {OUT}（{sum(len(v) for v in pool.values())} 人）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
