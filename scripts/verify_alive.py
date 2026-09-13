#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在世状态核验：剔除已故研究者。

★ 为什么必须有这一步：OpenAlex 不提供在世状态，已故研究者仍带近年发表记录
  （其实是遗作/合作署名）。实测 John Q. Trojanowski（2022 年去世）进了医学样板。
  「最新观点追踪」收录已故者是硬错误。

判定只用可追溯证据，不猜：
  1. Wikipedia 摘要里的 "(born ... – died ...)" / "was an American ..." 过去式
  2. Wikipedia 的 death date 结构化字段
判不出来的标 alive=None 留在册内并在面板标注，绝不擅自删人（名册只增不减铁律）。
"""
from __future__ import annotations

import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROSTER = ROOT / "data" / "kol_registry.json"
DECEASED = ROOT / "data" / "deceased_removed.json"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122"
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def fetch(url: str, timeout: int = 25, retries: int = 3):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            return urllib.request.urlopen(req, timeout=timeout, context=_CTX).read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(1.5 * (i + 1))
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


def _variants(name: str) -> list[str]:
    n = (name.replace("\u2010", "-").replace("\u2011", "-").replace("\u2013", "-"))
    n = re.sub(r"\s+", " ", n).strip()
    out = [n]
    s = re.sub(r"\s+[A-Z]\.(?:[-\u2010][A-Z]\.)?\s+", " ", n)
    if s != n:
        out.append(s)
    p = re.sub(r"\b[A-Z]\.\s*", "", n).strip()
    p = re.sub(r"\s+", " ", p)
    if p and p not in out:
        out.append(p)
    return out


DEATH_PAT = [
    re.compile(r"\(\s*(?:born\s+)?[^)]*?\d{4}\s*[–\-—]\s*\d{1,2}\s+\w+\s+(\d{4})\s*\)", re.I),
    re.compile(r"\(\s*[^)]*?\d{4}\s*[–\-—]\s*(\d{4})\s*\)"),
    re.compile(r"\bdied\b[^.]{0,60}?(\d{4})", re.I),
]
PAST_TENSE = re.compile(
    r"\bwas an?\s+(?:\w+\s+){0,3}"
    r"(scientist|researcher|professor|physician|biologist|chemist|physicist|"
    r"neuroscientist|neurologist|psychologist|pathologist|epidemiologist|"
    r"immunologist|geneticist|mathematician|academic)", re.I)


def check_alive(name: str) -> dict:
    for v in _variants(name):
        blob = fetch("https://en.wikipedia.org/api/rest_v1/page/summary/"
                     + urllib.parse.quote(v.replace(" ", "_")))
        if not blob:
            continue
        try:
            j = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if j.get("type") == "disambiguation" or "missing" in j:
            continue
        extract = j.get("extract") or ""
        desc = j.get("description") or ""
        # 同名闸：必须是科学从业者的词条才采信
        if not re.search(r"scien|research|profess|physic|biolog|chem|neuro|"
                         r"medic|psych|patholog|epidemi|immunolog|genetic|"
                         r"mathemat|academic|doctor", (desc + extract).lower()):
            continue
        for pat in DEATH_PAT:
            m = pat.search(extract)
            if m:
                return {"alive": False, "death_year": m.group(1),
                        "evidence": extract[:200], "matched": v}
        if PAST_TENSE.search(extract):
            return {"alive": False, "death_year": "",
                    "evidence": "词条用过去式表述：" + extract[:180], "matched": v}
        return {"alive": True, "evidence": extract[:150], "matched": v}
    return {"alive": None, "evidence": "未找到可采信的维基词条"}


def main() -> int:
    apply = "--apply" in sys.argv
    roster = json.loads(ROSTER.read_text(encoding="utf-8"))
    people = roster["people"]
    targets = [p for p in people if p.get("alive") is None]
    print(f"待核验 {len(targets)} 人（alive=None）\n")

    dead, alive_n, unknown = [], 0, 0
    for i, p in enumerate(targets, 1):
        name = p.get("name_en") or p.get("name_zh")
        r = check_alive(name)
        p["alive"] = r["alive"]
        p["alive_checked_on"] = date.today().isoformat()
        p["alive_evidence"] = r.get("evidence", "")[:200]
        if r["alive"] is False:
            dead.append(p)
            print(f"  {i:2d}. ✗ 已故 {name}（{r.get('death_year') or '年份未提取'}）")
            print(f"        {r['evidence'][:100]}")
        elif r["alive"] is True:
            alive_n += 1
        else:
            unknown += 1
        time.sleep(0.7)

    print(f"\n在世 {alive_n} | 已故 {len(dead)} | 无法判定 {unknown}")

    if dead and apply:
        # 已故者不删除记录，改为 active=False 并移出展示（名册只增不减）
        for p in dead:
            p["active"] = False
            p["inactive_reason"] = "已核实为已故，不适合「最新观点追踪」"
        old = json.loads(DECEASED.read_text(encoding="utf-8")) if DECEASED.exists() else []
        old.extend([{"id": p["id"], "name_en": p.get("name_en"),
                     "field": p.get("field"), "evidence": p.get("alive_evidence"),
                     "marked_on": date.today().isoformat()} for p in dead])
        DECEASED.write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")

    if apply:
        roster["active_count"] = sum(1 for p in people if p.get("active"))
        ROSTER.write_text(json.dumps(roster, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"已写回名册：总 {roster['count']} 人 / active {roster['active_count']}")
    else:
        print("（未加 --apply，仅预览，未写回）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
