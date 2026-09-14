#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建 Science-KOL 单文件 dashboard。

设计遵循 Chao 的看板规矩：
  - 人类网站风，不是 AI 味：禁 emoji 标题、标题 <=8 字、每 section 一行说明、
    每图单独 title、菜单宽松、忌「真实/强大」类自夸词
  - 三层信息结构：一句话 → 100-300 字结构化详情 → 原始出处链接
  - 本机无 emoji 字体（headless 渲染成 □），故用 CSS 色块代替图标
  - 左侧固定导航 + 滚动高亮
"""
from __future__ import annotations

import html
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROSTER = ROOT / "data" / "kol_registry.json"
LAYERS = ROOT / "data" / "layers" / "literature_layers.json"
STMT_DIR = ROOT / "data" / "statements"
STMT_LAYERS = ROOT / "data" / "layers" / "statement_layers.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dash_filter import (FIELD_COLOR_FB, FILTER_CSS,  # noqa: E402
                         FILTER_JS, filter_bar, four_layer_body)
OUT = ROOT / "dashboard" / "index.html"
OUT.parent.mkdir(parents=True, exist_ok=True)

FIELDS = ["医学健康", "生命科学", "AI计算机", "物理天文",
          "化学材料", "神经认知", "地球气候", "数学基础理论"]
FIELD_COLOR = {
    "医学健康": "#c0392b", "生命科学": "#27856a", "AI计算机": "#2c5f9e",
    "物理天文": "#5b4b8a", "化学材料": "#b06c1f", "神经认知": "#8a4b6b",
    "地球气候": "#1f7a6c", "数学基础理论": "#4a5568",
}


def esc(s) -> str:
    return html.escape(str(s or ""))


def zh_title(r: dict) -> str:
    """标题一律中文优先。Chao 铁律：展开层不能是英文。"""
    return (r.get("title_zh") or "").strip() or (r.get("title") or "").strip()


def zh_body(r: dict) -> str:
    """正文一律中文优先：summary_zh > abstract_zh > 原文。"""
    for k in ("summary_zh", "abstract_zh"):
        v = (r.get(k) or "").strip()
        if v:
            return v
    return (r.get("body") or r.get("abstract") or "").strip()


def stars(n: int) -> str:
    n = int(n or 0)
    return (("<span class='st on'>●</span>" * n)
            + ("<span class='st'>●</span>" * (5 - n))
            + f"<span class='num'>{n}/5</span>")


def build() -> str:
    roster = json.loads(ROSTER.read_text(encoding="utf-8")) if ROSTER.exists() else {"people": []}
    # 言论：合并全部日份，按人归集（最新在前）
    stmts_by_person: dict[str, list] = {}
    all_stmts: list[dict] = []
    if STMT_DIR.exists():
        seen_urls = set()
        for f in sorted(STMT_DIR.glob("*.json"), reverse=True):
            try:
                for r in json.loads(f.read_text(encoding="utf-8")):
                    k = (r.get("doi") or r.get("url") or "").lower()
                    if k and k in seen_urls:
                        continue
                    seen_urls.add(k)
                    all_stmts.append(r)
                    stmts_by_person.setdefault(r.get("person_id", ""), []).append(r)
            except json.JSONDecodeError:
                continue
        for v in stmts_by_person.values():
            v.sort(key=lambda x: x.get("published") or "", reverse=True)
    slayers = (json.loads(STMT_LAYERS.read_text(encoding="utf-8"))
               if STMT_LAYERS.exists() else {})
    layers = json.loads(LAYERS.read_text(encoding="utf-8")) if LAYERS.exists() else {}
    people = roster.get("people", [])
    daily = layers.get("daily", {})
    monthly = layers.get("monthly", {})
    yearly = layers.get("yearly", {})
    meta = layers.get("_meta", {})

    by_field: dict[str, list] = {f: [] for f in FIELDS}
    for p in people:
        by_field.setdefault(p.get("field", "其他"), []).append(p)

    days = sorted(daily, reverse=True)
    months = sorted(monthly, reverse=True)
    years = sorted(yearly, reverse=True)

    # ── KOL 区 ──────────────────────────────────────────────
    kol_html = []
    for f in FIELDS:
        grp = sorted(by_field.get(f, []), key=lambda x: -(x.get("weighted_score") or 0))
        if not grp:
            kol_html.append(
                f"<section id='kol-{esc(f)}'><h3>{esc(f)}</h3>"
                f"<p class='note'>该门类名册尚未建立，等待名单定稿。</p></section>")
            continue
        cards = []
        for p in grp:
            ev = p.get("public_voice_evidence") or {}
            warns = []
            if p.get("origin") == "openalex-candidate":
                aff = p.get("affiliation", "")
                # ★ 明显错误（公司名当机构）能自动抓；但「看着像机构却张冠李戴」抓不到
                #   （实测 Luigi Ferrucci 实为 NIH/NIA 却挂 University of Oxford）。
                #   故一律标未核实，不假装规则能判准——宁可多标，不可漏标。
                if not aff or aff.split(" (")[0] in ("Twitter", "Bloomberg", "Facebook"):
                    warns.append(("err", "机构字段明显有误，待人工核验"))
                elif not p.get("affiliation_verified"):
                    warns.append(("err", "机构来自自动抓取，未经人工核验"))
                if p.get("alive") is None:
                    warns.append(("info", "在世状态该数据源不提供，未核实"))
            warn_html = "".join(
                f"<div class='warn {lv}'>{esc(t)}</div>" for lv, t in warns)
            links = []
            if ev.get("wiki_url"):
                links.append(f"<a href='{esc(ev['wiki_url'])}' target='_blank'>维基词条</a>")
            if p.get("openalex_url"):
                links.append(f"<a href='{esc(p['openalex_url'])}' target='_blank'>OpenAlex</a>")
            if p.get("orcid"):
                links.append(f"<a href='https://orcid.org/{esc(p['orcid'])}' target='_blank'>ORCID</a>")
            if p.get("official_url"):
                links.append(f"<a href='{esc(p['official_url'])}' target='_blank'>主页</a>")

            mine = stmts_by_person.get(p.get("id", ""), [])
            if mine:
                srows = []
                for st in mine[:5]:
                    d = st.get("published") or "日期未核实"
                    body = zh_body(st)[:700]
                    tail = (f"<details><summary>观点详情</summary>"
                            f"<p class='abs'>{esc(body)}</p>"
                            f"<p class='links'><a href='{esc(st.get('url'))}' target='_blank'>原文出处</a>"
                            f"<span class='attr'>{esc(st.get('attribution_note') or '')}</span></p>"
                            f"</details>") if body else (
                            f"<p class='links'><a href='{esc(st.get('url'))}' target='_blank'>原文出处</a></p>")
                    srows.append(
                        "<li class='stmt'>"
                        f"<span class='sd'>{esc(d)}</span>"
                        f"<span class='sj'>{esc((st.get('journal') or '')[:26])}</span>"
                        f"<div class='stt'>{esc(zh_title(st))}</div>"
                        f"{tail}</li>")
                more = (f"<div class='more'>另有 {len(mine) - 5} 条</div>"
                        if len(mine) > 5 else "")
                voice_html = (f"<div class='voice'><b>最新观点 · {len(mine)} 条</b>"
                              f"<ul class='stmts'>{''.join(srows)}</ul>{more}</div>")
            else:
                reason = ("无 ORCID，无法精确归属"
                          if not p.get("orcid") else "近 18 个月无观点型发表")
                voice_html = f"<div class='voice none'>暂无可追踪观点（{esc(reason)}）</div>"

            detail = p.get("bio") or ev.get("wiki_extract") or ""
            metrics = ""
            if p.get("h_index"):
                metrics = (f"<span class='m'>h-index {p['h_index']}</span>"
                           f"<span class='m'>引用 {p.get('cited_by_count', 0):,}</span>"
                           f"<span class='m'>近3年 {p.get('recent_works_3y', 0)} 篇</span>")
            cards.append(f"""
<article class='card' data-field='{esc(f)}'>
  <div class='chead'>
    <span class='dot' style='background:{FIELD_COLOR.get(f, "#666")}'></span>
    <b>{esc(p.get('name_zh') or p.get('name_en'))}</b>
    <span class='rate'>{stars(p.get('rating', 0))}</span>
    <span class='score'>{float(p.get('weighted_score') or 0):.2f}</span>
  </div>
  <div class='aff'>{esc(p.get('affiliation') or p.get('origin_note') or '')}</div>
  {metrics}
  <div class='dims'>
    <span title='学术根基'>A {float(p.get('score_A') or 0):.1f}</span>
    <span title='一手性'>B {float(p.get('score_B') or 0):.1f}</span>
    <span title='公共表达'>C {float(p.get('score_C') or 0):.1f}</span>
    <span title='方法透明'>D {float(p.get('score_D') or 0):.1f}</span>
  </div>
  {warn_html}
  {voice_html}
  <details><summary>档案</summary>
    <p>{esc(detail[:600])}</p>
    {"<p class='ctr'>争议：" + esc(p['controversies']) + "</p>" if p.get('controversies') else ""}
    <p class='links'>{' · '.join(links) or '暂无公开链接'}</p>
  </details>
</article>""")
        kol_html.append(
            f"<section id='kol-{esc(f)}'><h3>{esc(f)}"
            f"<span class='cnt'>{len(grp)} 人</span></h3>"
            f"<div class='grid'>{''.join(cards)}</div></section>")

    # ── 文献：日 ────────────────────────────────────────────
    def lit_items(items: list[dict], limit: int = 40) -> str:
        rows = []
        for it in items[:limit]:
            f = it.get("field") or "未分类"
            zh = (it.get("summary_zh") or "").strip()
            en_abs = (it.get("abstract") or "").strip()
            # ★ 展开层一律中文优先（Chao 铁律）。英文原文降为二级折叠，
            #   仅在有中文时提供；没有中文摘要时才直接展示英文并标注。
            if zh:
                detail = (f"<p class='abs'>{esc(zh)}</p>"
                          + (f"<details class='sub'><summary>英文原文摘要</summary>"
                             f"<p class='abs en'>{esc(en_abs[:900])}</p></details>"
                             if en_abs else ""))
            else:
                detail = (f"<p class='abs en'>{esc(en_abs[:900])}</p>"
                          f"<p class='note-i'>该条暂无中文摘要</p>" if en_abs else "")
            rows.append(f"""
<li class='lit'>
  <div class='ltop'>
    <span class='tag' style='background:{FIELD_COLOR.get(f, "#777")}'>{esc(f)}</span>
    <span class='src'>{esc(it.get('source'))}</span>
    <span class='pd'>{esc(it.get('published'))}</span>
  </div>
  <div class='ltitle'>{esc(zh_title(it))}</div>
  {"<div class='zh en-sub'>" + esc(it.get('title') or '') + "</div>" if it.get('title_zh') else ""}
  <details><summary>摘要与出处</summary>
    {detail}
    <p class='links'>
      {"<a href='" + esc(it['url']) + "' target='_blank'>原文</a>" if it.get('url') else ''}
      {" · <a href='https://doi.org/" + esc(it['doi']) + "' target='_blank'>DOI</a>" if it.get('doi') else ''}
    </p>
  </details>
</li>""")
        return "<ul class='litlist'>" + "".join(rows) + "</ul>"

    day_blocks = []
    for d in days[:14]:
        blk = daily[d]
        chips = " ".join(
            f"<span class='chip' style='background:{FIELD_COLOR.get(k, '#777')}'>{esc(k)} {v}</span>"
            for k, v in blk["by_field"].items())
        day_blocks.append(
            f"<details class='daybox' {'open' if d == days[0] else ''}>"
            f"<summary><b>{esc(d)}</b> 共 {blk['count']} 篇 {chips}</summary>"
            f"{lit_items(blk['items'])}</details>")

    month_blocks = []
    for m in months[:12]:
        blk = monthly[m]
        chips = " ".join(
            f"<span class='chip' style='background:{FIELD_COLOR.get(k, '#777')}'>{esc(k)} {v}</span>"
            for k, v in blk["by_field"].items())
        topics = " ".join(f"<span class='tw'>{esc(w)} <i>{n}</i></span>"
                          for w, n in blk.get("topics", [])[:12])
        month_blocks.append(
            f"<details class='daybox' {'open' if m == months[0] else ''}>"
            f"<summary><b>{esc(m)}</b> 共 {blk['count']} 篇 {chips}</summary>"
            f"<div class='topics'>高频主题：{topics or '—'}</div>"
            f"{lit_items(blk.get('top_items', []), 25)}</details>")

    year_blocks = []
    for y in years:
        blk = yearly[y]
        rows = []
        for f, series in sorted(blk.get("field_trend", {}).items()):
            mx = max(series.values()) if series else 1
            bars = "".join(
                f"<span class='bar' title='{esc(mm)}: {n}' "
                f"style='height:{max(3, int(n / mx * 42))}px;background:{FIELD_COLOR.get(f, '#777')}'></span>"
                for mm, n in sorted(series.items()))
            rows.append(f"<div class='trow'><span class='tname'>{esc(f)}</span>"
                        f"<span class='bars'>{bars}</span></div>")
        topics = " ".join(f"<span class='tw'>{esc(w)} <i>{n}</i></span>"
                          for w, n in blk.get("topics", [])[:18])
        year_blocks.append(
            f"<details class='daybox' open><summary><b>{esc(y)} 年</b> 共 {blk['count']} 篇</summary>"
            f"<h4>门类月度趋势</h4><div class='trend'>{''.join(rows) or '<p class=note>数据积累中</p>'}</div>"
            f"<h4>高频主题</h4><div class='topics'>{topics or '—'}</div>"
            f"{lit_items(blk.get('top_items', []), 20)}</details>")

    total_people = len(people)
    lit_total = meta.get("total", 0)
    llm_n = sum(1 for d in daily.values() for i in d["items"] if i.get("summary_zh"))

    # ── 观点三层渲染（主角是人，先给发声人排行，与文献层刻意不同）──
    def stmt_blocks(layer: str, limit: int) -> list:
        out = []
        buckets = (slayers.get(layer) or {})
        for bk in sorted(buckets, reverse=True)[:limit]:
            b = buckets[bk]
            dist = b.get("by_field") or {}
            diststr = "\u3000".join(f"{k} {v}" for k, v in
                                sorted(dist.items(), key=lambda x: -x[1])[:8])
            tops = b.get("top_persons") or []
            topstr = "".join(
                f"<span class='pill'>{esc(n)}<b>{c}</b></span>" for n, c in tops)
            chs = b.get("by_channel") or {}
            chstr = "\u3001".join(f"{k} {v}" for k, v in
                             sorted(chs.items(), key=lambda x: -x[1]))
            rows = []
            for st in (b.get("items") or [])[:14]:
                body = zh_body(st)
                d = st.get("published") or "\u65e5\u671f\u672a\u6838\u5b9e"
                if body:
                    inner = (f"<details><summary>\u89c2\u70b9\u8be6\u60c5</summary>"
                             f"<p class='abs'>{esc(body[:900])}</p>"
                             f"<p class='links'><a href='{esc(st.get('url'))}' target='_blank'>\u539f\u6587\u51fa\u5904</a>"
                             f"<span class='attr'>{esc(st.get('attribution_note') or '')}</span></p></details>")
                else:
                    inner = (f"<p class='links'><a href='{esc(st.get('url'))}' target='_blank'>\u539f\u6587\u51fa\u5904</a></p>")
                rows.append(
                    "<li class='stmt'>"
                    f"<span class='sd'>{esc(d)}</span>"
                    f"<span class='sj'>{esc(st.get('person_name') or '')}</span>"
                    f"<span class='sj'>\u00b7 {esc((st.get('journal') or '')[:24])}</span>"
                    f"<div class='stt'>{esc(zh_title(st))}</div>{inner}</li>")
            trend = ""
            if layer == "yearly" and b.get("field_trend"):
                bars = []
                ft = b["field_trend"]
                months = sorted({m for v in ft.values() for m in v})
                for fld in sorted(ft, key=lambda f: -sum(ft[f].values()))[:6]:
                    cells = "".join(
                        f"<i title='{esc(m)} {ft[fld].get(m, 0)} \u6761' "
                        f"style='height:{min(34, 4 + ft[fld].get(m, 0) * 3)}px'></i>"
                        for m in months)
                    bars.append(f"<div class='tr'><span>{esc(fld)}</span>"
                                f"<div class='bars'>{cells}</div></div>")
                trend = ("<div class='trend'><div class='tt'>\u5404\u95e8\u7c7b\u6708\u5ea6\u53d1\u58f0\u91cf</div>"
                         + "".join(bars) + "</div>")
            out.append(
                f"<section class='bucket'><h3>{esc(bk)}"
                f"<span class='cnt'>{b.get('count', 0)} \u6761</span></h3>"
                f"<p class='dist'>{esc(diststr)}</p>"
                f"<div class='pills'>{topstr}</div>"
                f"<p class='dist small'>\u6765\u6e90\uff1a{esc(chstr)}</p>"
                f"{trend}<ul class='stmts'>{''.join(rows)}</ul></section>")
        return out

    sday = stmt_blocks("daily", 14)
    smon = stmt_blocks("monthly", 12)
    syear = stmt_blocks("yearly", 5)
    sund = slayers.get("undated") or {}
    und_html = ""
    if sund.get("count"):
        _src = "\u3001".join(f"{k} {v}" for k, v in (sund.get("by_channel") or {}).items())
        und_html = (f"<p class='note'>\u53e6\u6709 {sund['count']} \u6761\u672a\u53d6\u5230\u53d1\u8868\u65e5\uff0c"
                    f"\u672a\u8ba1\u5165\u4efb\u4f55\u65f6\u95f4\u6876\uff08\u6765\u6e90\uff1a{_src}\uff09\u3002"
                    f"\u6309\u53e3\u5f84\u4e0d\u7528\u6293\u53d6\u65e5\u9876\u66ff\u3002</p>")

    # ── 卡片网格：一次渲染全部，由 filter 前端过滤（Chao 2026-09-14）──
    fmap_field = {p["id"]: p.get("field") for p in people}
    from datetime import date as _d, timedelta as _td
    _t = _d.today()
    CUTS = {"day": _t.isoformat(),
            "week": (_t - _td(days=7)).isoformat(),
            "month": (_t - _td(days=30)).isoformat(),
            "year": (_t - _td(days=365)).isoformat()}

    def card_grid(rows, scope, who_key, src_key, fields_order):
        cnt = {}
        for r in rows:
            f = r.get("_field") or "未分类"
            cnt[f] = cnt.get(f, 0) + 1
        cards = []
        for i, r in enumerate(rows):
            f = r.get("_field") or "未分类"
            uid = f"{scope}{i}"
            dt = r.get("published") or ""
            meta = [("发表日", esc(dt) if dt else "未核实（按纪律留空，不用抓取日顶替）", False),
                    ("来源", esc(r.get(src_key) or ""), False),
                    ("门类", esc(f), False),
                    ("归属", esc(r.get("attribution_note")
                                 or r.get("abstract_source") or "—"), False)]
            if r.get("doi"):
                meta.append(("DOI", f"<a href='https://doi.org/{esc(r['doi'])}' "
                                    f"target='_blank'>{esc(r['doi'])}</a>", True))
            if r.get("url"):
                meta.append(("原文", f"<a href='{esc(r['url'])}' target='_blank'>"
                                     f"{esc(r['url'][:76])}</a>", True))
            if r.get("title"):
                meta.append(("英文原题", esc(r["title"]), True))
            lead = (r.get("l1_lead") or "").strip()
            if not lead:
                lead = (r.get("summary_zh") or "")[:78]
            cards.append(
                f"<article class='ccard' data-field='{esc(f)}' data-date='{esc(dt)}' "
                f"style='border-top-color:{FIELD_COLOR.get(f, FIELD_COLOR_FB)}'>"
                f"<div class='cc-top'>"
                f"<span class='cc-tag' style='background:"
                f"{FIELD_COLOR.get(f, FIELD_COLOR_FB)}'>{esc(f)}</span>"
                f"<span class='cc-date'>{esc(dt or '日期未核实')}</span></div>"
                f"<div class='cc-who'>{esc(r.get(who_key) or '')}</div>"
                f"<div class='cc-title'>{esc(zh_title(r))}</div>"
                f"<div class='cc-lead'>{esc(lead)}</div>"
                f"<div class='cc-src'>{esc(r.get(src_key) or '')}</div>"
                f"<button type='button' class='cc-open'>展开四层 &#9662;</button>"
                f"<div class='cc-body'>{four_layer_body(r, uid, esc, meta)}</div>"
                f"</article>")
        return cnt, ("<div class='cgrid'>" + "".join(cards) + "</div>"
                     "<div class='fempty' style='display:none'>"
                     "<p class='note'>当前筛选条件下没有条目。放宽时间档或切到「全部」门类。</p>"
                     "</div>")

    # 观点：全部条目
    srows = []
    for r in all_stmts:
        rr = dict(r)
        rr["_field"] = fmap_field.get(r.get("person_id")) or "未归类"
        srows.append(rr)
    srows.sort(key=lambda x: x.get("published") or "", reverse=True)
    scnt, sgrid = card_grid(srows, "s", "person_name", "journal", FIELDS)
    sdist = "、".join(f"{k} {v}" for k, v in
                     sorted(scnt.items(), key=lambda x: -x[1]))
    sstat = (f"<div class='fstat'>当前显示 <b>{len(srows)}</b> / 共 {len(srows)} 条</div>"
             f"<details class='fsum'><summary>门类与来源分布</summary>"
             f"<div class='sline'>门类：{esc(sdist)}</div>"
             f"<div class='sline'>来源：" + esc("、".join(
                 f"{k} {v}" for k, v in sorted(
                     __import__("collections").Counter(
                         r.get("channel") or "未知" for r in srows).items(),
                     key=lambda x: -x[1]))) + "</div></details>")
    stmt_panel = filter_bar("s", FIELDS, scnt, sstat) + sgrid + "</div>"

    # 文献：展示层去重后的全部条目
    lrows_map = {}
    for L in ("daily", "monthly", "yearly"):
        for b in (layers.get(L) or {}).values():
            for it in (b.get("items") or b.get("top_items") or []):
                if isinstance(it, dict) and it.get("url"):
                    lrows_map.setdefault(it["url"], it)
    lrows = []
    for r in lrows_map.values():
        rr = dict(r)
        rr["_field"] = r.get("field") or "未分类"
        lrows.append(rr)
    lrows.sort(key=lambda x: (x.get("published") or "", x.get("importance") or 0),
               reverse=True)
    lcnt, lgrid = card_grid(lrows, "l", "authors", "source", FIELDS)
    ldist = "、".join(f"{k} {v}" for k, v in
                     sorted(lcnt.items(), key=lambda x: -x[1]))
    lstat = (f"<div class='fstat'>当前显示 <b>{len(lrows)}</b> / 共 {len(lrows)} 条</div>"
             f"<details class='fsum'><summary>门类与来源分布</summary>"
             f"<div class='sline'>门类：{esc(ldist)}</div>"
             f"<div class='sline'>来源：" + esc("、".join(
                 f"{k} {v}" for k, v in sorted(
                     __import__("collections").Counter(
                         r.get("source") or "未知" for r in lrows).items(),
                     key=lambda x: -x[1])[:14])) + "</div></details>")
    lit_panel = filter_bar("l", FIELDS, lcnt, lstat) + lgrid + "</div>"

    nav_fields = "".join(
        f"<a href='#kol-{esc(f)}'>{esc(f)}"
        f"<i>{len(by_field.get(f, []))}</i></a>" for f in FIELDS)

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Science KOL</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;font:15px/1.7 -apple-system,"Segoe UI","Noto Sans CJK SC","Source Han Sans SC",sans-serif;
background:#f7f7f5;color:#23262b}}
#side{{position:fixed;left:0;top:0;bottom:0;width:210px;background:#1e2228;color:#c9ced6;
overflow-y:auto;padding:22px 0;scrollbar-width:thin;scrollbar-color:#3a4048 #1e2228}}
#side::-webkit-scrollbar{{width:6px}}
#side::-webkit-scrollbar-track{{background:#1e2228}}
#side::-webkit-scrollbar-thumb{{background:#3a4048;border-radius:3px}}
#side h1{{font-size:17px;margin:0 20px 4px;color:#fff;letter-spacing:.5px}}
#side .sub{{font-size:12px;margin:0 20px 20px;color:#7e858f}}
#side a{{display:block;padding:7px 20px;color:#c9ced6;text-decoration:none;font-size:13px}}
#side a:hover{{background:#2a2f36;color:#fff}}
#side a.act{{background:#2f353d;color:#fff;border-left:3px solid #4d8fdb;padding-left:17px}}
#side a i{{float:right;font-style:normal;color:#6e757f;font-size:11px}}
#side .grp{{margin:16px 20px 6px;font-size:11px;color:#6e757f;letter-spacing:1px}}
main{{margin-left:210px;padding:30px 34px 80px;max-width:1180px}}
h2{{font-size:21px;margin:36px 0 4px;padding-bottom:8px;border-bottom:2px solid #23262b}}
h3{{font-size:16px;margin:24px 0 10px;color:#333}}
h4{{font-size:13px;margin:14px 0 6px;color:#555}}
.note{{color:#777;font-size:13px;margin:4px 0 14px}}
.cnt{{font-size:12px;color:#888;font-weight:400;margin-left:8px}}
.stat{{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin:14px 0 6px}}
.stat div{{background:#fff;border:1px solid #e3e3e0;padding:12px 16px;border-radius:3px}}
.stat b{{display:block;font-size:22px;line-height:1.2}}
.stat span{{font-size:12px;color:#777}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:12px}}
.card{{background:#fff;border:1px solid #e3e3e0;border-radius:3px;padding:13px 15px}}
.chead{{display:flex;align-items:center;gap:7px;flex-wrap:wrap}}
.dot{{width:9px;height:9px;border-radius:50%;display:inline-block;flex:none}}
.rate{{font-size:0}}
.rate .st{{color:#d8d8d4;font-size:10px}}
.rate .num{{font-size:11px;color:#8a929c;margin-left:4px}}
.rate .st.on{{color:#e0a33e}}
.score{{margin-left:auto;font-size:12px;color:#888}}
.aff{{font-size:12px;color:#6a7078;margin:4px 0}}
.m{{display:inline-block;font-size:11px;color:#555;background:#f2f2ef;
border-radius:2px;padding:1px 6px;margin:2px 4px 2px 0}}
.dims{{margin:6px 0 2px}}
.dims span{{display:inline-block;font-size:11px;color:#4a5568;background:#eef1f5;
padding:1px 6px;border-radius:2px;margin-right:4px}}
.warn{{font-size:11px;padding:4px 8px;margin:4px 0;border-left:3px solid}}
.warn.err{{color:#96472f;background:#fbf0ec;border-color:#c0603f}}
.warn.info{{color:#6b6357;background:#f6f4ee;border-color:#b9ae97}}
.legend{{background:#fff;border:1px solid #e3e3e0;padding:10px 14px;margin:10px 0 16px;
border-radius:3px;font-size:12px;color:#5a5f67}}
.legend span{{margin-right:16px;display:inline-block}}
.legend i{{font-style:normal;display:inline-block;width:9px;height:9px;border-radius:50%;
margin-right:4px;vertical-align:middle}}
.ctr{{font-size:12px;color:#96472f;background:#fbf0ec;padding:5px 8px;border-radius:2px}}
.voice{{margin:8px 0 4px;border-top:1px solid #eee;padding-top:7px}}
.voice>b{{font-size:12px;color:#2d5f4a}}
.voice.none{{font-size:11px;color:#9a9a92;font-style:normal}}
.stmts{{list-style:none;padding:0;margin:5px 0 0}}
.stmt{{padding:5px 0;border-bottom:1px dotted #eee}}
.sd{{font-size:11px;color:#8a929c;margin-right:7px}}
.sj{{font-size:11px;color:#6a7078}}
.stt{{font-size:12.5px;color:#1b1e23;margin:2px 0}}
.attr{{font-size:10px;color:#9a9a92;margin-left:8px}}
.more{{font-size:11px;color:#8a929c;margin-top:4px}}
.pills{{margin:6px 0 4px;display:flex;flex-wrap:wrap;gap:5px}}
.pill{{font-size:11.5px;background:#eef1f4;color:#3b444f;padding:2px 7px;
 border-radius:2px;border:1px solid #e2e6ea}}
.pill b{{margin-left:5px;color:#6a7480;font-weight:600}}
.dist.small{{font-size:11px;color:#8a929c}}
.trend{{margin:8px 0;padding:7px 9px;background:#fafbfc;border:1px solid #eceff2}}
.trend .tt{{font-size:11.5px;color:#6a7480;margin-bottom:5px}}
.trend .tr{{display:flex;align-items:flex-end;gap:8px;margin:3px 0}}
.trend .tr>span{{font-size:11px;color:#5a636d;width:78px;flex:none}}
.trend .bars{{display:flex;align-items:flex-end;gap:2px;height:36px}}
.trend .bars i{{width:7px;background:#8fa6b8;display:block}}
.en-sub{{font-size:11px;color:#9aa2ab;font-style:normal;margin-top:1px}}
.abs.en{{color:#6d757e}}
details.sub{{margin-top:6px}}
details.sub summary{{font-size:11.5px;color:#8a929c}}
.note-i{{font-size:11px;color:#96472f;margin-top:4px}}
details{{margin-top:6px}}
summary{{cursor:pointer;font-size:12px;color:#4d7db5;outline:none}}
details p{{font-size:13px;color:#4a4f57;margin:6px 0}}
.links a{{color:#4d7db5;text-decoration:none;font-size:12px}}
.links a:hover{{text-decoration:underline}}
.daybox{{background:#fff;border:1px solid #e3e3e0;border-radius:3px;padding:10px 14px;margin:8px 0}}
.daybox>summary{{font-size:14px;color:#23262b}}
.chip{{display:inline-block;color:#fff;font-size:11px;padding:1px 7px;
border-radius:9px;margin-left:4px}}
.litlist{{list-style:none;padding:0;margin:10px 0 0}}
.lit{{border-top:1px solid #eee;padding:9px 0}}
.ltop{{display:flex;gap:8px;align-items:center;font-size:11px;color:#888}}
.tag{{color:#fff;padding:1px 7px;border-radius:2px}}
.ltitle{{font-size:14px;margin:3px 0;color:#1b1e23}}
.zh{{font-size:13px;color:#2d5f4a;background:#f0f6f3;padding:5px 9px;
border-left:3px solid #27856a;margin:4px 0}}
.abs{{font-size:12px;color:#5a5f67;background:#fafaf8;padding:8px 10px}}
.topics{{margin:6px 0 10px}}
.tw{{display:inline-block;background:#eef1f5;border-radius:2px;padding:2px 7px;
margin:2px 4px 2px 0;font-size:12px;color:#3d4855}}
.tw i{{color:#8a929c;font-style:normal;font-size:11px}}
.trow{{display:flex;align-items:flex-end;gap:10px;margin:5px 0}}
.tname{{width:96px;font-size:12px;color:#555;flex:none}}
.bars{{display:flex;align-items:flex-end;gap:3px;height:46px}}
.bar{{width:11px;display:inline-block;border-radius:1px 1px 0 0}}
footer{{margin-top:50px;padding-top:14px;border-top:1px solid #ddd;font-size:12px;color:#888}}
{FILTER_CSS}
</style></head><body>
<nav id="side">
  <h1>Science KOL</h1>
  <p class="sub">科学界观点与文献追踪</p>
  <div class="grp">主视图</div>
  <a href="#stmt">KOL 观点</a>
  <a href="#lit">科学文献</a>
  <div class="grp">KOL 名册</div>
  <a href="#overview">总览</a>
  {nav_fields}
  <div class="grp">说明</div>
  <a href="#method">口径与方法</a>
</nav>
<main>
<h2 id="stmt">KOL 观点</h2>
<p class="note">按时间档与门类筛选，两排按钮可叠加。每张卡片点开为四层：一句话导语 →
总结 → 原文翻译 → 出处与元信息。归属以 ORCID 或作者主页双命中锚定。</p>
{stmt_panel}

<h2 id="lit">科学文献</h2>
<p class="note">顶刊、预印本与非主流期刊的每日扫描结果，同样支持时间与门类筛选、
四层展开。文献源头多数只提供摘要，原文翻译层会如实标注。</p>
{lit_panel}

<h2 id="overview">总览</h2>
<p class="note">左侧按科学门类浏览 KOL 名册，或按日、月、年查看文献扫描结果。</p>
<div class="stat">
  <div><b>{total_people}</b><span>名册人数</span></div>
  <div><b>{len(all_stmts)}</b><span>KOL 观点</span></div>
  <div><b>{lit_total}</b><span>在库文献</span></div>
  <div><b>{llm_n}</b><span>中文摘要</span></div>
  <div><b>{len(days)}</b><span>覆盖天数</span></div>
  <div><b>{meta.get('built_at', '')}</b><span>更新日期</span></div>
</div>

<h2>KOL 名册</h2>
<p class="note">按科学门类分组。评分为四维加权（A 学术根基 30%、B 一手性 25%、
C 公共表达 30%、D 方法透明 15%），评级取名册内百分位，非绝对切点。</p>
<div class="legend">
  <span>色点表示所属门类</span>
  <span><i style="background:#c0603f"></i>标注为待核验：字段存疑，需人工确认后方可定稿</span>
  <span><i style="background:#b9ae97"></i>标注为未核实：该项数据源不提供，待补</span>
</div>
{''.join(kol_html)}

<h2 id="method">口径与方法</h2>
<p class="note">数据来源与判定口径，供核查。</p>
<div class="daybox" open>
<h4>文献源</h4>
<p class="abs">主流顶刊 Nature、Science、Cell、NEJM、Lancet、PNAS、JAMA；
预印本 arXiv、bioRxiv、medRxiv、chemRxiv；开放获取 PLOS、eLife、Frontiers、MDPI。
chemRxiv 与 MDPI 直连返回 403，经 Crossref 取得；arXiv 经分类 RSS 取得。
缺摘要条目由 OpenAlex 按 DOI 回填。</p>
<h4>时间口径</h4>
<p class="abs">按论文实际发表日分层，非抓取日。发表日取不到的条目标注为未核实并单列，
不以抓取日顶替。仅收录发表日在 60 天窗口内的条目，避免旧刊重新索引混入每日更新。</p>
<h4>KOL 评分</h4>
<p class="abs">A 学术根基取 h-index 与引用量在同门类候选池内的百分位；
B 一手性取近三年产出强度与 ORCID 身份锚；C 公共表达为实测所得，
探测维基词条与 The Conversation 学者专栏，同名者证据作废；
D 方法透明取 ORCID 公开、机构可核、无同名污点。近 12 个月无可追溯公开发声者不入册。</p>
<h4>KOL 观点抓取</h4>
<p class="abs">身份锚定一律用 ORCID，不用姓名。姓名缩写在文献库中毫无区分度：
实测对 6 位无 ORCID 的收录者做姓名匹配，抓回 41 条经逐条核对全部为同名他人
（整形外科、眼科、真菌学等），命中率为零，已全部剔除并留痕。
因此无 ORCID 者显示为暂无观点，而非填入不可信内容。
收录文体限于述评、社论、综述、学者专栏等表达观点的载体，不收纯研究论文。</p>
<h4>已知待核验项</h4>
<p class="abs">OpenAlex 的机构字段存在错误值，卡片上已逐条标注；
在世状态该库不提供，标注为未核实，需人工复核后方可视为定稿。</p>
</div>

<footer>Science KOL · 生成于 {date.today().isoformat()} ·
名册 {total_people} 人 · 文献 {lit_total} 条</footer>
</main>
<script>
var links=[].slice.call(document.querySelectorAll('#side a'));
var secs=links.map(function(a){{return document.querySelector(a.getAttribute('href'));}});
function onScroll(){{
  var y=window.scrollY+120,idx=-1;
  secs.forEach(function(s,i){{if(s&&s.offsetTop<=y)idx=i;}});
  links.forEach(function(a,i){{a.classList.toggle('act',i===idx);}});
}}
window.addEventListener('scroll',onScroll);onScroll();
</script>
<script>{FILTER_JS}
window.__SK_CUT={json.dumps(CUTS)};
window.__skApplyAll&&window.__skApplyAll();</script>
</body></html>"""


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    size = OUT.stat().st_size
    print(f"写出 {OUT} ({size / 1024:.0f} KB)")
