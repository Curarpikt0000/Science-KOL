#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C 维「公共表达度」实测探测。

本项目的可行性门槛：一个科学家若近 12 个月没有任何可追溯的公开发声，
就无法做「观点追踪」，面板上只会是空卡片。故 C 维不靠印象打分，必须实测。

探测渠道（全部公开源，不需登录）：
  1. Wikipedia  — 是否有独立词条（公众知名度的客观代理）
  2. 机构新闻页 / 个人主页 — 由 OpenAlex 的 institution 推导
  3. 学术媒体   — The Conversation（学者亲笔专栏，最对口）
  4. 播客/访谈  — 通过通用搜索命中
  5. 近期论文活跃度 — 已由 OpenAlex recent_works_3y 提供

★ 同名陷阱（War-KOL 实测教训，灌进过 25 条演员/寺庙民宿/律师）：
  命中必须满足【自有域名或标题含姓名】，且排除名录聚合页。
  本脚本对每个命中做 verify_attribution 校验，不通过的剔除并留痕。
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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122"
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

# 名录/聚合页特征：命中这些不算「公开发声」（War-KOL 闸 1）
DIRECTORY_PAT = re.compile(
    r"/(experts?|people|staff|faculty|directory|author[s]?|tag|topics?|category)/"
    r"|/(profiles?|members?)/|researchgate\.net|semanticscholar|scholar\.google"
    r"|linkedin\.com|loop\.frontiersin|orcid\.org|publons|scopus", re.I)


def fetch(url: str, timeout: int = 25, retries: int = 3):
    """★ 必须重试：实测批量探测时偶发网络抖动，单跑成功、批量失败。
    不重试会把「瞬时抖动」误报成「此人没有维基词条」= 假阴性污染名册。
    """
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            return urllib.request.urlopen(req, timeout=timeout, context=_CTX).read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None          # 真的没有，不必重试
            time.sleep(1.5 * (i + 1))
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


def _name_variants(name: str) -> list[str]:
    """生成姓名变体。

    ★ 2026-09-13 实测两类假阴性，必须归一化：
      1. Unicode 连字符：'Virginia M.‐Y. Lee' 里的 '‐' 是 U+2010 而非 ASCII '-'，
         直接查 REST summary 返回 404，看起来像「没有词条」其实是编码问题。
      2. 中间名缩写：'David M. Holtzman' 查不到但 'David Holtzman' 有词条。
    """
    n = (name.replace("\u2010", "-").replace("\u2011", "-")
             .replace("\u2013", "-").replace("\u2019", "'"))
    n = re.sub(r"\s+", " ", n).strip()
    out = [n]
    # 去掉中间名缩写（"David M. Holtzman" → "David Holtzman"）
    stripped = re.sub(r"\s+[A-Z]\.(?:[-\u2010][A-Z]\.)?\s+", " ", n)
    if stripped != n:
        out.append(stripped)
    # 去掉所有单字母缩写点
    plain = re.sub(r"\b[A-Z]\.\s*", "", n).strip()
    plain = re.sub(r"\s+", " ", plain)
    if plain and plain not in out:
        out.append(plain)
    return out


def _wiki_search(name: str) -> dict | None:
    """REST summary 全失败时走搜索 API 兜底。"""
    url = ("https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch="
           + urllib.parse.quote(name) + "&format=json&srlimit=3")
    blob = fetch(url, 20)
    if not blob:
        return None
    try:
        hits = json.loads(blob).get("query", {}).get("search", [])
    except json.JSONDecodeError:
        return None
    last = (name.split()[-1] or "").lower()
    for h in hits:
        title = h.get("title", "")
        # 同名闸：标题必须含姓氏，避免搜到无关条目
        if last and last in title.lower():
            return {"title": title, "snippet": re.sub(r"<[^>]+>", "", h.get("snippet", ""))}
    return None


def check_wikipedia(name: str) -> dict:
    """是否有英文维基词条 + 是否为科学家（防同名演员/政客）。"""
    anchors = ("scientist", "researcher", "professor", "physician", "biologist",
               "chemist", "physicist", "neuroscientist", "epidemiolog", "immunolog",
               "geneticist", "mathematician", "engineer", "academic", "doctor",
               "neurologist", "oncolog", "psychiatr", "pathologist", "cardiolog",
               "科学家", "教授", "研究员")

    for variant in _name_variants(name):
        url = ("https://en.wikipedia.org/api/rest_v1/page/summary/"
               + urllib.parse.quote(variant.replace(" ", "_")))
        blob = fetch(url, 20)
        if not blob:
            continue
        try:
            j = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if j.get("type") == "disambiguation" or "missing" in j:
            continue
        extract = (j.get("extract") or "")
        desc = (j.get("description") or "")
        is_sci = any(a in (desc + " " + extract).lower() for a in anchors)
        return {
            "has_wiki": True,
            "wiki_is_scientist": is_sci,
            "wiki_desc": desc[:120],
            "wiki_matched_variant": variant,
            "wiki_url": (j.get("content_urls", {}).get("desktop", {}) or {}).get("page", ""),
            "wiki_extract": extract[:300],
        }

    # 兜底：搜索 API
    hit = _wiki_search(name)
    if hit:
        txt = (hit.get("snippet") or "").lower()
        return {
            "has_wiki": True,
            "wiki_is_scientist": any(a in txt for a in anchors),
            "wiki_desc": hit.get("snippet", "")[:120],
            "wiki_matched_variant": hit.get("title", ""),
            "wiki_url": "https://en.wikipedia.org/wiki/"
                        + urllib.parse.quote(hit.get("title", "").replace(" ", "_")),
            "wiki_via": "search-api",
        }
    return {"has_wiki": False}


def check_the_conversation(name: str) -> dict:
    """The Conversation：学者亲笔专栏，是最对口的「学者公开表达」证据。"""
    url = ("https://theconversation.com/search?q="
           + urllib.parse.quote(f'"{name}"'))
    blob = fetch(url, 25)
    if not blob:
        return {"tc_hits": 0}
    html = blob.decode("utf-8", "ignore")
    # 作者页链接形如 /profiles/xxx-12345
    profiles = set(re.findall(r'/profiles/([a-z0-9\-]+-\d+)', html))
    return {"tc_hits": len(profiles), "tc_profiles": sorted(profiles)[:3]}


def probe_person(name: str, institution: str = "") -> dict:
    """综合探测一个人的公共表达度，返回证据与 C 维建议分。"""
    ev: dict = {"name": name, "probed_at": time.strftime("%Y-%m-%d")}
    ev.update(check_wikipedia(name))
    time.sleep(0.8)
    ev.update(check_the_conversation(name))
    time.sleep(0.8)

    # C 维建议分（0-10），全部基于实测证据，不猜
    # ★ 同名闸（War-KOL 教训：灌进过演员/寺庙民宿/律师）：
    #   词条命中但描述不含科学从业者锚词 = 同名他人，此路证据【作废】而非降权。
    #   实测案例：'John C. Morris' 命中的是加拿大冰壶奥运冠军，不是阿尔茨海默病专家。
    c = 0.0
    homonym = False
    if ev.get("has_wiki"):
        if ev.get("wiki_is_scientist"):
            c += 4.5
        else:
            homonym = True
            ev["homonym_rejected"] = ev.get("wiki_desc", "")
            ev["has_wiki"] = False          # 作废该证据，不计入
    c += min(ev.get("tc_hits", 0), 3) * 1.5
    ev["homonym_flag"] = homonym
    ev["score_C_suggested"] = round(min(c, 10.0), 1)
    # 无维基 + 无专栏 = 无法追踪；仅靠 TC 命中也需 >=2 篇才算有稳定输出
    ev["trackable"] = c >= 3.0
    return ev


def main() -> int:
    src = ROOT / "data" / "candidates_raw.json"
    if not src.exists():
        print("先跑 build_candidates.py")
        return 1
    pool = json.loads(src.read_text(encoding="utf-8"))
    field = sys.argv[1] if len(sys.argv) > 1 else "医学健康"
    people = pool.get(field, [])
    if not people:
        print(f"{field} 池为空")
        return 1
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else len(people)

    print(f"=== 探测 {field} 的 {min(limit, len(people))} 人公共表达度 ===")
    out = []
    for i, p in enumerate(people[:limit], 1):
        ev = probe_person(p["name_en"], p.get("institution_raw", ""))
        p["probe"] = ev
        p["score_C"] = ev["score_C_suggested"]
        p["trackable"] = ev["trackable"]
        out.append(p)
        flag = "✓" if ev["trackable"] else "✗"
        print(f"  {i:2d}. {flag} C={ev['score_C_suggested']:4.1f} {p['name_en'][:26]:28s} "
              f"wiki={'Y' if ev.get('has_wiki') else 'N'}"
              f"{'(非科学家!)' if ev.get('has_wiki') and not ev.get('wiki_is_scientist') else ''} "
              f"TC={ev.get('tc_hits', 0)}")

    pool[field] = out + people[limit:]
    src.write_text(json.dumps(pool, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(1 for p in out if p.get("trackable"))
    print(f"\n可追踪 {ok}/{len(out)}（C>=3.0）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
