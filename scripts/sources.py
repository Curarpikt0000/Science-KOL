#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Science-KOL 文献源定义 + 统一抓取层。

★ 三个实测绕过路径（2026-09-13 实跑验证，勿擅改）：
  1. chemRxiv 官方 API 直连 403  → 走 Crossref DOI 前缀 10.26434（自带摘要）
  2. MDPI RSS 直连 403           → 走 Crossref member 1968（自带摘要）
  3. arXiv export API 触发 429   → 走 OAI-PMH 端点（单次 800+ 条带摘要，稳定）

★ 摘要来源分层（实测：顶刊 RSS 普遍不带摘要）：
  - RSS 自带 description 的（Cell/Lancet/eLife/Science）直接用
  - 不带的（Nature/JAMA/PLOS/PNAS）→ OpenAlex 按 ISSN 回填
  - ★ Nature 日更主体是新闻稿（DOI 前缀 d41586），Crossref/OpenAlex/EuropePMC
    三家都查不到其摘要；真正带摘要的是研究论文（s41586）。
    故必须按 DOI 前缀区分 news / article，不能一锅端。
"""
from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122 Safari/537.36")
MAILTO = "science-kol-bot@example.com"  # Crossref/OpenAlex 礼貌池，非真实邮箱不外发

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

# ── 门类（Chao 2026-09-13 拍板的 8 类）──────────────────────────────
FIELDS = [
    "医学健康", "生命科学", "AI计算机", "物理天文",
    "化学材料", "神经认知", "地球气候", "数学基础理论",
]

# ── 源清单 ────────────────────────────────────────────────────────
# tier: mainstream=主流顶刊 / preprint=预印本 / alt=非主流开放获取
JOURNAL_RSS = [
    # name, url, tier, issn(用于 OpenAlex 回填摘要), rss_has_abstract
    ("Nature",    "https://www.nature.com/nature.rss",                                    "mainstream", "0028-0836", False),
    ("Science",   "https://www.science.org/rss/news_current.xml",                          "mainstream", "0036-8075", True),
    ("Cell",      "https://www.cell.com/cell/current.rss",                                 "mainstream", "0092-8674", True),
    ("NEJM",      "https://www.nejm.org/action/showFeed?jc=nejm&type=etoc&feed=rss",        "mainstream", "0028-4793", True),
    ("Lancet",    "https://www.thelancet.com/rssfeed/lancet_current.xml",                   "mainstream", "0140-6736", True),
    ("PNAS",      "https://www.pnas.org/action/showFeed?type=etoc&feed=rss&jc=pnas",        "mainstream", "0027-8424", False),
    ("JAMA",      "https://jamanetwork.com/rss/site_3/67.xml",                              "mainstream", "0098-7484", False),
    ("PLOS ONE",  "https://journals.plos.org/plosone/feed/atom",                            "alt",        "1932-6203", False),
    ("eLife",     "https://elifesciences.org/rss/recent.xml",                               "alt",        "2050-084X", True),
    ("Frontiers", "https://www.frontiersin.org/journals/medicine/rss",                      "alt",        None,       True),
]

# 预印本：bioRxiv / medRxiv 官方 API（带摘要，稳定）
PREPRINT_API = [
    ("bioRxiv", "https://api.biorxiv.org/details/biorxiv/{d}/{d}", "preprint"),
    ("medRxiv", "https://api.medrxiv.org/details/medrxiv/{d}/{d}", "preprint"),
]

# arXiv 分类 RSS（rss.arxiv.org）
# ★ 2026-09-13 实测定论，三条路都走过了，勿再换回去：
#   - export API (export.arxiv.org/api/query)：本 VM 出口 IP 被持续 429，退避到 20s 仍失败
#   - OAI-PMH：能拿数据，但 `from` 过滤的是【元数据更新日】不是发表日，
#     拉回 835 条全是 2014-2016 年的老论文只因最近改过元数据 —— 用来做「今日新论文」是错的
#   - rss.arxiv.org/rss/<cat>：当日新论文 + 带摘要 + 不限流 ← 采用
# ★ arXiv 周末不发布：周六日各分类 RSS 均返回 0 条且 lastBuildDate 相同，
#   这是正常现象不是故障，selfheal 不要据此告警。
ARXIV_RSS_CATS = [
    ("cs.AI", "AI计算机"), ("cs.LG", "AI计算机"), ("cs.CL", "AI计算机"),
    ("physics.gen-ph", "物理天文"), ("astro-ph.GA", "物理天文"), ("quant-ph", "物理天文"),
    ("q-bio.NC", "神经认知"), ("q-bio.BM", "生命科学"), ("q-bio.GN", "生命科学"),
    ("math.PR", "数学基础理论"), ("math.NT", "数学基础理论"), ("stat.ME", "数学基础理论"),
    ("physics.chem-ph", "化学材料"), ("cond-mat.mtrl-sci", "化学材料"),
    ("physics.ao-ph", "地球气候"), ("physics.geo-ph", "地球气候"),
]

# Crossref 绕过路径：403 源
CROSSREF_BYPASS = [
    # name, crossref_path, tier, default_field
    ("chemRxiv", "prefixes/10.26434/works", "preprint", "化学材料"),
    ("MDPI",     "members/1968/works",      "alt",      None),
]

_XMLNS = {
    "rss": "http://purl.org/rss/1.0/",
    "atom": "http://www.w3.org/2005/Atom",
    "dc": "http://purl.org/dc/elements/1.1/",
    "prism": "http://prismstandard.org/namespaces/basic/2.0/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "oai": "http://www.openarchives.org/OAI/2.0/",
    "oai_dc": "http://www.openarchives.org/OAI/2.0/oai_dc/",
}


def fetch(url: str, timeout: int = 45, retries: int = 3, sleep: float = 2.0) -> bytes | None:
    """带退避重试的 GET。失败返回 None（绝不伪造数据）。"""
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            return urllib.request.urlopen(req, timeout=timeout, context=_CTX).read()
        except urllib.error.HTTPError as e:
            if e.code == 429:          # 限流：指数退避
                time.sleep(sleep * (2 ** i) + 3)
                continue
            if e.code in (403, 404):   # 无重试价值
                return None
            time.sleep(sleep * (i + 1))
        except Exception:
            time.sleep(sleep * (i + 1))
    return None


def _strip(html: str | None) -> str:
    if not html:
        return ""
    txt = re.sub(r"<[^>]+>", " ", html)
    txt = re.sub(r"&[a-zA-Z]+;|&#\d+;", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()


def _norm_date(raw: str) -> str:
    """各源日期格式统一成 YYYY-MM-DD；解析不出来返回空串（绝不用抓取日顶替）。"""
    if not raw:
        return ""
    raw = raw.strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        return m.group(0)
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z",
                "%a, %d %b %Y", "%d %b %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw[:31].strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def _txt(elem, tags) -> str:
    for t in tags:
        node = elem.find(t, _XMLNS)
        if node is not None and (node.text or "").strip():
            return node.text.strip()
    return ""


def parse_rss(name: str, blob: bytes, tier: str, issn: str | None) -> list[dict]:
    """解析 RSS/RDF/Atom。返回统一 schema。"""
    try:
        root = ET.fromstring(blob)
    except ET.ParseError:
        return []
    items = (root.findall(".//item") or root.findall(".//rss:item", _XMLNS)
             or root.findall(".//atom:entry", _XMLNS))
    out = []
    for it in items:
        title = _strip(_txt(it, ["title", "rss:title", "atom:title"]))
        if not title:
            continue
        link = _txt(it, ["link", "rss:link"])
        if not link:
            node = it.find("atom:link", _XMLNS)
            link = node.get("href") if node is not None else ""
        doi = _txt(it, ["prism:doi", "dc:identifier"])
        if doi:
            doi = doi.replace("doi:", "").strip()
        elif link and "/doi/" in link:
            m = re.search(r"/doi/(?:abs/|full/)?(10\.\S+)", link)
            doi = m.group(1) if m else ""
        abstract = _strip(_txt(it, ["description", "rss:description", "dc:description",
                                    "atom:summary", "content:encoded"]))
        pub = _norm_date(_txt(it, ["pubDate", "dc:date", "prism:publicationDate",
                                   "atom:published", "atom:updated"]))
        out.append({
            "source": name, "tier": tier, "issn": issn,
            "title": title, "url": link, "doi": doi,
            "abstract": abstract, "published": pub,
            "authors": _strip(_txt(it, ["dc:creator"])),
            "category_raw": "", "field": None, "abstract_source": "rss" if abstract else "",
        })
    return out


def fetch_journals() -> list[dict]:
    rows = []
    for name, url, tier, issn, _has_abs in JOURNAL_RSS:
        blob = fetch(url)
        if not blob:
            print(f"  [WARN] {name} 抓取失败（跳过，不伪造）")
            continue
        got = parse_rss(name, blob, tier, issn)
        rows.extend(got)
        print(f"  {name:10s} {len(got):3d} 条")
        time.sleep(1.0)
    return rows


def fetch_preprints(day: str) -> list[dict]:
    rows = []
    for name, tpl, tier in PREPRINT_API:
        blob = fetch(tpl.format(d=day))
        if not blob:
            print(f"  [WARN] {name} 抓取失败")
            continue
        try:
            payload = json.loads(blob)
        except json.JSONDecodeError:
            print(f"  [WARN] {name} 返回非 JSON")
            continue
        coll = payload.get("collection") or []
        for c in coll:
            rows.append({
                "source": name, "tier": tier, "issn": None,
                "title": _strip(c.get("title")),
                "url": f"https://doi.org/{c.get('doi')}" if c.get("doi") else "",
                "doi": c.get("doi", ""),
                "abstract": _strip(c.get("abstract")),
                "published": _norm_date(c.get("date", "")),
                "authors": c.get("authors", ""),
                "category_raw": c.get("category", ""),
                "field": None, "abstract_source": "api",
            })
        print(f"  {name:10s} {len(coll):3d} 条")
        time.sleep(1.5)
    return rows


def fetch_arxiv(today: str | None = None) -> list[dict]:
    """arXiv 当日新论文，走 rss.arxiv.org 分类 RSS（见 ARXIV_RSS_CATS 上方的选型说明）。

    RSS 只给「今日批次」，不接受日期参数；today 仅用于回填 published 字段。
    周末返回 0 条属正常（arXiv 不在周末发布）。
    """
    today = today or date.today().isoformat()
    rows, empty = [], 0
    for cat, default_field in ARXIV_RSS_CATS:
        blob = fetch(f"https://rss.arxiv.org/rss/{cat}", timeout=45)
        if not blob:
            print(f"  [WARN] arXiv:{cat} 抓取失败")
            continue
        try:
            root = ET.fromstring(blob)
        except ET.ParseError:
            print(f"  [WARN] arXiv:{cat} XML 解析失败")
            continue
        items = root.findall(".//item")
        if not items:
            empty += 1
        n = 0
        for it in items:
            title = _strip(_txt(it, ["title"]))
            if not title:
                continue
            desc = _txt(it, ["description"])
            # arXiv RSS 的 description 形如 "arXiv:2509.xxxxx Announce Type: new \nAbstract: ..."
            abstract = _strip(re.sub(r"^.*?Abstract:\s*", "", desc, flags=re.S)) if "Abstract:" in desc else _strip(desc)
            link = _txt(it, ["link"])
            m = re.search(r"(\d{4}\.\d{4,5})", link or "") or re.search(r"arXiv:(\d{4}\.\d{4,5})", desc or "")
            arxiv_id = m.group(1) if m else ""
            rows.append({
                "source": f"arXiv:{cat}", "tier": "preprint", "issn": None,
                "title": title, "url": link,
                "doi": f"10.48550/arXiv.{arxiv_id}" if arxiv_id else "",
                "abstract": abstract,
                "published": _norm_date(_txt(it, ["pubDate", "dc:date"])) or today,
                "authors": _strip(_txt(it, ["dc:creator"])),
                "category_raw": cat,
                "field": default_field, "abstract_source": "rss",
            })
            n += 1
        print(f"  arXiv:{cat:18s} {n:4d} 条")
        time.sleep(1.2)
    if empty == len(ARXIV_RSS_CATS):
        wd = datetime.strptime(today, "%Y-%m-%d").weekday()
        note = "（周末，arXiv 不发布，属正常）" if wd >= 5 else "（工作日却全空，值得排查）"
        print(f"  [INFO] arXiv 全部分类 0 条 {note}")
    return rows


def fetch_crossref_bypass(since: str, max_age_days: int = 45) -> list[dict]:
    """chemRxiv / MDPI 的 403 绕过；Crossref 自带摘要。

    ★ 2026-09-13 实测踩坑 1：不能用 `from-created-date` 过滤——Crossref 的 created
      日期滞后约 2 天，按「昨天」过滤会稳定返回 0 条（看起来像源挂了，其实是过滤器空转）。
      改用 `from-index-date`（入库日，实时更新）。
    ★ 实测踩坑 2：index-date 新 ≠ 论文新。`from-index-date` 拉回的 MDPI 结果
      100% 是 2012-2025 年旧论文被重新索引（实测 200 条无一新论文），chemRxiv 也有
      69% 是改版旧稿。正解是按【发表日】直查 `from-pub-date`（实测 MDPI 2162 条、
      chemRxiv 212 条真新论文且带摘要），index-date 那条路是死路，勿再走。
    ★ 注意 Crossref 存在脏日期（见过 [[2103, 12]] 这种未来年份），故仍保留
      max_age_days 上下界二次校验。
    """
    rows = []
    cutoff = (date.today() - timedelta(days=max_age_days)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    for name, path, tier, default_field in CROSSREF_BYPASS:
        url = (f"https://api.crossref.org/{path}?"
               f"filter=from-pub-date:{cutoff}&rows=200"
               f"&sort=published&order=desc&mailto={MAILTO}")
        blob = fetch(url, timeout=60)
        if not blob:
            print(f"  [WARN] {name} (Crossref) 抓取失败")
            continue
        try:
            items = json.loads(blob)["message"]["items"]
        except (json.JSONDecodeError, KeyError):
            print(f"  [WARN] {name} (Crossref) 返回异常")
            continue
        kept = 0
        for it in items:
            # ★ 发表日优先级：published > issued > posted > created(兜底)
            #   只用 created 会把「Crossref 入库日」当成发表日，与「按实际发表日分档」纪律冲突。
            parts = []
            for key in ("published", "issued", "posted", "published-online", "published-print"):
                node = it.get(key) or {}
                cand = (node.get("date-parts") or [[]])[0]
                if cand and cand[0]:
                    parts = cand
                    break
            if not parts:
                parts = (it.get("created", {}).get("date-parts") or [[]])[0]
            pub = ""
            if parts and parts[0]:
                y = parts[0]
                m = parts[1] if len(parts) > 1 else 1
                d = parts[2] if len(parts) > 2 else 1
                pub = f"{y:04d}-{m:02d}-{d:02d}"
            if pub and (pub < cutoff or pub > tomorrow):
                continue          # 老论文 / 脏未来日期，不进每日批次
            kept += 1
            rows.append({
                "source": name, "tier": tier, "issn": (it.get("ISSN") or [None])[0],
                "title": _strip((it.get("title") or [""])[0]),
                "url": it.get("URL", ""), "doi": it.get("DOI", ""),
                "abstract": _strip(it.get("abstract")),
                "published": _norm_date(pub),
                "authors": ", ".join(
                    f"{a.get('given','')} {a.get('family','')}".strip()
                    for a in (it.get("author") or [])[:6]),
                "category_raw": (it.get("container-title") or [""])[0],
                "field": default_field, "abstract_source": "crossref",
            })
        print(f"  {name:10s} {kept:3d} 条 (Crossref 绕过，已滤掉 {len(items) - kept} 条旧论文)")
        time.sleep(1.5)
    return rows


def backfill_abstracts_openalex(rows: list[dict], limit: int = 400) -> int:
    """给缺摘要的条目按 DOI 批量回填（OpenAlex）。

    ★ Nature 新闻稿(d41586) 三家库都无摘要 → 直接标记 news，不浪费请求。
    """
    def inv2txt(inv):
        if not inv:
            return ""
        pos = {}
        for w, idxs in inv.items():
            for i in idxs:
                pos[i] = w
        return " ".join(pos[k] for k in sorted(pos))

    need = []
    for r in rows:
        if r["abstract"]:
            continue
        doi = (r.get("doi") or "").lower()
        if doi.startswith("10.1038/d41586") or "/d41586-" in doi:
            r["doc_type"] = "news"          # Nature 新闻稿，无摘要是其固有属性
            continue
        if doi:
            need.append(r)
    need = need[:limit]
    filled = 0
    for i in range(0, len(need), 40):          # OpenAlex 支持 DOI 批量 OR 过滤
        chunk = need[i:i + 40]
        dois = "|".join(f"https://doi.org/{r['doi']}" for r in chunk)
        url = (f"https://api.openalex.org/works?filter=doi:{urllib.parse.quote(dois, safe='|:/.')}"
               f"&per-page=40&mailto={MAILTO}")
        blob = fetch(url, timeout=60)
        if not blob:
            continue
        try:
            results = json.loads(blob).get("results", [])
        except json.JSONDecodeError:
            continue
        by_doi = {(w.get("doi") or "").replace("https://doi.org/", "").lower(): w for w in results}
        for r in chunk:
            w = by_doi.get(r["doi"].lower())
            if not w:
                continue
            ab = inv2txt(w.get("abstract_inverted_index"))
            if ab:
                r["abstract"] = ab
                r["abstract_source"] = "openalex"
                filled += 1
            if not r.get("published") and w.get("publication_date"):
                r["published"] = w["publication_date"]
        time.sleep(1.0)
    return filled


def dedupe(rows: list[dict]) -> list[dict]:
    """按 DOI 优先、标题兜底去重（同一论文常同时出现在预印本与顶刊）。"""
    seen_doi, seen_title, out = set(), set(), []
    for r in rows:
        doi = (r.get("doi") or "").strip().lower()
        key_t = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", (r.get("title") or "").lower())[:90]
        if doi and doi in seen_doi:
            continue
        if not doi and key_t and key_t in seen_title:
            continue
        if doi:
            seen_doi.add(doi)
        if key_t:
            seen_title.add(key_t)
        out.append(r)
    return out
