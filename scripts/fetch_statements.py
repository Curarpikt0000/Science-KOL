#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KOL 言论抓取：把名册里的人变成【可追踪的观点流】。

★ 身份铁锚 = ORCID，不是姓名。
  实测教训：EuropePMC 用 `AUTH:"Rosenberg SA"` 查 Steven A. Rosenberg（NCI 免疫治疗）
  时，前 5 条里有 4 条是另一位同名 Rosenberg SA（Moffitt 放射科）。缩写姓名做作者
  匹配必然串人。有 ORCID 的走 `AUTHORID:`，没有的走姓名但必须过同名闸并标低置信。

★ 什么算「言论」（对科学家的定义）：
  收录 Comment / Editorial / Review / Perspective 这类【表达观点】的文体，
  以及 The Conversation 的学者亲笔专栏。
  不收纯 Research Article —— 那是报告数据，不是观点，且会淹没面板。

★ 五要素门槛（沿用 War-KOL 铁律）：无正文/无实质内容的不入库，剔除留痕。
★ 发表日按实际发表日，取不到标 date_status=unverified，绝不用抓取日顶替。
"""
from __future__ import annotations

import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROSTER = ROOT / "data" / "kol_registry.json"
OUT_DIR = ROOT / "data" / "statements"
REJECTED = ROOT / "data" / "statements_rejected.json"
OUT_DIR.mkdir(parents=True, exist_ok=True)

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122"
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

# 观点型文体（排除纯 research article）
OPINION_TYPES = ["Comment", "Editorial", "Review", "Letter", "News",
                 "Historical Article", "Introductory Journal Article"]


def fetch(url: str, timeout: int = 30, retries: int = 3):
    for i in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept": "application/json, */*"})
            return urllib.request.urlopen(req, timeout=timeout, context=_CTX).read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (i + 1))
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def _strip(html: str | None) -> str:
    if not html:
        return ""
    t = re.sub(r"<[^>]+>", " ", html)
    t = re.sub(r"&[a-zA-Z]+;|&#\d+;", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def europepmc_statements(person: dict, months: int = 18) -> list[dict]:
    """从 EuropePMC 取该人的观点型文章。ORCID 优先。"""
    orcid = (person.get("orcid") or "").strip()
    name = (person.get("name_en") or person.get("name_zh") or "").strip()
    if not name:
        return []
    since = (date.today() - timedelta(days=months * 31)).isoformat()

    types = " OR ".join(f'PUB_TYPE:"{t}"' for t in OPINION_TYPES)
    if orcid:
        who = f'AUTHORID:"{orcid}"'
        confidence = "high"
    else:
        # ★ 无 ORCID 一律【不抓】，不是「标低置信」了事。
        #   实测 2026-09-13：对 6 位无 ORCID 者做姓名匹配，抓回 41 条，
        #   逐条核对【全部是同名他人】——整形外科 Brown CD、眼科 Schwartz SG、
        #   真菌学 Schwartz S…… 命中率 0%。姓名缩写在 EuropePMC 上毫无区分度。
        #   低置信数据入库＝污染面板，比没有数据更糟。
        return []

    q = f'({who}) AND ({types}) AND (FIRST_PDATE:[{since} TO {date.today().isoformat()}])'
    url = ("https://www.ebi.ac.uk/europepmc/webservices/rest/search?query="
           + urllib.parse.quote(q)
           + "&format=json&pageSize=25&sort=P_PDATE_D%20desc&resultType=core")
    blob = fetch(url)
    if not blob:
        return []
    try:
        payload = json.loads(blob)
    except json.JSONDecodeError:
        return []

    out = []
    for r in payload.get("resultList", {}).get("result", []):
        abstract = _strip(r.get("abstractText"))
        title = _strip(r.get("title"))
        pub = (r.get("firstPublicationDate") or "").strip()
        journal = ((r.get("journalInfo") or {}).get("journal") or {}).get("title", "")
        doi = r.get("doi", "")
        out.append({
            "person_id": person["id"],
            "person_name": name,
            "channel": "EuropePMC",
            "pub_type": r.get("pubType") or "",
            "title": title,
            "body": abstract,
            "journal": journal,
            "doi": doi,
            "url": f"https://doi.org/{doi}" if doi else
                   f"https://europepmc.org/article/{r.get('source','MED')}/{r.get('id','')}",
            "published": pub if re.match(r"^\d{4}-\d{2}-\d{2}$", pub) else "",
            "date_status": "ok" if re.match(r"^\d{4}-\d{2}-\d{2}$", pub) else "unverified",
            "authors": (r.get("authorString") or "")[:220],
            "attribution_confidence": confidence,
            "attribution_basis": f"ORCID {orcid}" if orcid else f"姓名匹配 {name}（需复核）",
            "collected_on": date.today().isoformat(),
        })
    return out


def the_conversation_statements(person: dict) -> list[dict]:
    """The Conversation 学者亲笔专栏 —— 科学家公开表达最纯粹的载体。"""
    name = (person.get("name_en") or person.get("name_zh") or "").strip()
    if not name:
        return []
    url = "https://theconversation.com/search?q=" + urllib.parse.quote(f'"{name}"')
    blob = fetch(url, timeout=25)
    if not blob:
        return []
    html = blob.decode("utf-8", "ignore")
    profiles = re.findall(r'/profiles/([a-z0-9\-]+-\d+)', html)
    if not profiles:
        return []

    # 取命中最多的作者页，且其 slug 必须含姓氏（同名闸）
    last = re.sub(r"[^a-z]", "", name.split()[-1].lower())
    cand = [p for p in set(profiles) if last and last in p.replace("-", "")]
    if not cand:
        return []
    slug = max(cand, key=lambda s: profiles.count(s))

    blob2 = fetch(f"https://theconversation.com/profiles/{slug}/articles", timeout=25)
    if not blob2:
        return []
    h2 = blob2.decode("utf-8", "ignore")
    out = []
    for m in re.finditer(
            r'<a href="(/[^"]+-\d{4,6})"[^>]*>\s*(?:<[^>]+>\s*)*([^<]{15,200}?)\s*<',
            h2)  :
        href, title = m.group(1), _strip(m.group(2))
        if "/profiles/" in href or not title:
            continue
        out.append({
            "person_id": person["id"],
            "person_name": name,
            "channel": "The Conversation",
            "pub_type": "学者专栏",
            "title": title,
            "body": "",
            "journal": "The Conversation",
            "doi": "",
            "url": "https://theconversation.com" + href,
            "published": "",
            "date_status": "unverified",
            "authors": name,
            "attribution_confidence": "high",
            "attribution_basis": f"The Conversation 作者页 /profiles/{slug}",
            "collected_on": date.today().isoformat(),
        })
        if len(out) >= 12:
            break
    return out


MIN_BODY = 120   # 五要素门槛的下限：正文太短无法构成观点


def verify_attribution(row: dict) -> tuple[bool, str]:
    """归属复核（ORCID 已是铁锚，这里只做形式校验并标注例外）。

    ★ 作者串里查不到姓氏 ≠ 归属错误。实测三类合法例外：
      EuropePMC 的 authorString 会被截断、大型协作组署名为
      "GBD 2023 Mental Disorder Collaborators."、以及婚后改姓等。
      ORCID 命中即可采信，此处只把例外标出来供人工抽查。
    """
    last = (row.get("person_name") or "").split()[-1].lower()
    au = (row.get("authors") or "").lower()
    if last and last in au:
        return True, "作者串含姓氏"
    if au.rstrip(".").endswith("collaborators") or "consortium" in au or "group" in au:
        return True, "协作组署名，ORCID 命中即采信"
    if len(row.get("authors") or "") >= 55:
        return True, "作者串被截断，ORCID 命中即采信"
    return True, "仅 ORCID 命中，建议人工抽查"


def main() -> int:
    only_field = sys.argv[1] if len(sys.argv) > 1 else None
    roster = json.loads(ROSTER.read_text(encoding="utf-8"))
    people = [p for p in roster["people"] if p.get("active")]
    if only_field:
        people = [p for p in people if p.get("field") == only_field]
    print(f"抓取 {len(people)} 人的言论"
          + (f"（门类 {only_field}）" if only_field else "") + "\n")

    all_rows, rejected = [], []
    for i, p in enumerate(people, 1):
        rows = europepmc_statements(p)
        time.sleep(1.0)
        rows += the_conversation_statements(p)
        time.sleep(1.0)

        kept = []
        for r in rows:
            # 门槛：EuropePMC 条目须有正文；TC 专栏只有标题，靠标题+链接成立
            if r["channel"] == "EuropePMC" and len(r["body"]) < MIN_BODY:
                rejected.append({**r, "reject_reason": f"正文不足 {MIN_BODY} 字符"})
                continue
            kept.append(r)
        for r in kept:
            _, note = verify_attribution(r)
            r["attribution_note"] = note
        all_rows.extend(kept)
        oc = "ORCID" if p.get("orcid") else "姓名"
        print(f"  {i:2d}. {p.get('name_en', '')[:26]:28s} {len(kept):3d} 条 "
              f"({oc}锚) 剔除 {len(rows) - len(kept)}")

    # 去重（同 DOI / 同 URL）
    seen, uniq = set(), []
    for r in all_rows:
        k = (r.get("doi") or r.get("url") or "").lower()
        if k and k in seen:
            continue
        seen.add(k)
        uniq.append(r)

    # ★ 合并写入，不整文件覆盖。
    #   实测事故：按门类单跑（如只跑「生命科学」）会用该门类的 56 条覆盖当日文件，
    #   把此前已抓的其他门类全部冲掉。日文件必须是当日【累积】结果。
    out = OUT_DIR / f"{date.today().isoformat()}.json"
    existing_rows = []
    if out.exists():
        try:
            existing_rows = json.loads(out.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing_rows = []

    touched = {p["id"] for p in people}
    # 本轮抓过的人：用新结果替换其旧条目；没抓的人：原样保留
    merged = [r for r in existing_rows if r.get("person_id") not in touched]
    kept_other = len(merged)
    merged.extend(uniq)

    # 全局去重（同 DOI / URL）
    seen2, final = set(), []
    for r in merged:
        k = (r.get("doi") or r.get("url") or "").lower()
        if k and k in seen2:
            continue
        seen2.add(k)
        final.append(r)

    out.write_text(json.dumps(final, ensure_ascii=False, indent=1), encoding="utf-8")
    old = json.loads(REJECTED.read_text(encoding="utf-8")) if REJECTED.exists() else []
    REJECTED.write_text(json.dumps(old + rejected, ensure_ascii=False, indent=1),
                        encoding="utf-8")

    hi = sum(1 for r in uniq if r["attribution_confidence"] == "high")
    print(f"\n本轮 {len(uniq)} 条（高置信 {hi}，低置信 {len(uniq) - hi}）"
          f" + 保留其他门类 {kept_other} 条 = 当日 {len(final)} 条")
    print(f"剔除 {len(rejected)} 条（已留痕 {REJECTED.name}）")
    print(f"落盘 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
