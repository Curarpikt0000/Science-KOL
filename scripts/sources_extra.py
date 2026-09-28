"""Science-KOL 扩源（Chao 2026-09-25 批准方案 A）。

背景：原来只有 EuropePMC + The Conversation 两个渠道，53 人合计每月只有 3-10 条言论，
      日报大部分天都是「今日无新增」。科学家主要的公开发言场所基本没覆盖。

新增两个源（按实测性价比排序，数字均为 2026-09-25 实测）：

① 期刊评论栏目 —— Crossref，按 ORCID 精确查
   53 人近 6 个月 Crossref 作品 1573 篇，标题带评论特征的 84 篇，其中 82 篇现有库未收。
   ORCID 是铁锚，没有同名问题。Crossref 没有「文体」字段，所以靠标题/栏目特征筛评论类，
   再用 EuropePMC/Crossref 摘要补正文；无正文的不入库（五要素门禁）。

② 媒体采访原话 —— Google News RSS 按全名搜 + LLM 抽原话
   Venki Ramakrishnan 近 90 天 9 条，John Morris 近 30 天 8 条。
   ★ 同名风险高，三道闸：
     闸1 标题或正文必须含【名+姓】全名（只含姓不算）
     闸2 正文须能取到（≥600 字符），取不到不入库
     闸3 LLM 必须抽到【本人直接说的话】+ 他的判断/论点，且确认是同一人（学科/机构对得上）；
         只是被提到、或文章里没有他的原话 → 拒收
   原文链接由 Google News 加密跳转解码得到（batchexecute），解不出直链的不入库。

所有产出沿用 fetch_statements.py 的行结构，下游四层生成/面板/日报零改动。
"""
from __future__ import annotations

import html as _html
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122 Safari/537.36")
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

PROXY = os.environ.get("GENAI_PROXY", "")
MODEL = os.environ.get("SK_LLM_MODEL", "gpt-4o-mini")
LLM_SLEEP = 1.5          # 代理串行 + 1.5s 间隔（配额纪律）

# 评论类栏目的标题特征（Crossref 无文体字段，只能靠这个）
# ★ 只留强标记。实测 2026-09-25 宽松版误收：Stein「Examining the psychometric properties of
#   the flexible interview for...」因含 interview 被当成采访——其实是量表研究论文。
#   should / lessons / rethink / why we 这类词在研究论文标题里同样常见，全部拿掉。
OPINION_RE = re.compile(
    r"(\b(comment|commentary|perspective|viewpoint|editorial|opinion|world view|"
    r"essay|correspondence|policy forum|news & views|point of view)\b"
    r"|\ban interview with\b|\bin conversation with\b|\bq&a\b)", re.I)
# Nature 旗下杂志栏目（Comment / World View / News & Views / Q&A）DOI 统一前缀 d41586，
# 标题里往往不带栏目名，靠前缀识别。
NATURE_MAG = re.compile(r"^10\.1038/d41586-", re.I)


# ─────────────────────────── 通用 ───────────────────────────
def _get(url: str, timeout: int = 25, data: bytes | None = None,
         headers: dict | None = None) -> tuple[int, str, str]:
    h = {"User-Agent": UA, "Accept": "text/html,application/json,*/*",
         "Accept-Language": "en-US,en;q=0.9"}
    if headers:
        h.update(headers)
    for att in range(3):
        try:
            req = urllib.request.Request(url, headers=h, data=data)
            with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
                return r.status, r.read().decode("utf-8", "ignore"), r.geturl()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410):
                return e.code, "", url
            time.sleep(2 * (att + 1))
        except Exception:  # noqa: BLE001
            time.sleep(2 * (att + 1))
    return -1, "", url


def _strip(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _name_words(name: str) -> tuple[str, str]:
    ws = [re.sub(r"[^a-z]", "", w.lower())
          for w in re.sub(r"[^A-Za-z\s\u00C0-\u024F-]", " ", name).split()]
    ws = [w for w in ws if len(w) >= 2]
    return (ws[0], ws[-1]) if len(ws) >= 2 else ("", "")


def _has_fullname(text: str, name: str) -> bool:
    """闸1：名+姓都出现，且相距不远（防止名和姓分属两个人）。"""
    first, last = _name_words(name)
    if not first or not last:
        return False
    t = re.sub(r"[^a-z\s]", " ", text.lower())
    for m in re.finditer(r"\b" + re.escape(last) + r"\b", t):
        window = t[max(0, m.start() - 40): m.start()]
        if re.search(r"\b" + re.escape(first) + r"\b", window):
            return True
    return False


def llm(prompt: str, max_tokens: int = 900, retries: int = 4) -> str:
    if not PROXY:
        return ""
    body = json.dumps({"model": MODEL,
                       "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0.1, "max_tokens": max_tokens}).encode()
    for att in range(retries):
        try:
            req = urllib.request.Request(
                PROXY.rstrip("/") + "/v1/chat/completions", data=body,
                headers={"Content-Type": "application/json",
                         "Authorization": "Bearer " + os.environ.get("GENAI_KEY", "local")})
            r = json.loads(urllib.request.urlopen(req, timeout=120).read())
            out = (r["choices"][0]["message"]["content"] or "").strip()
            if out:                       # 代理偶发空返回：同输入重跑即成功
                return out
        except urllib.error.HTTPError as e:
            if e.code != 429:
                return ""
        except Exception:  # noqa: BLE001
            pass
        time.sleep(4 * (att + 1))
    return ""


def _row(person, channel, pub_type, title, body, journal, url, published,
         basis, doi="", authors="", extra=None) -> dict:
    ok_date = bool(re.match(r"^\d{4}-\d{2}-\d{2}$", published or ""))
    r = {
        "person_id": person["id"],
        "person_name": person.get("name_en") or person.get("name_zh"),
        "channel": channel, "pub_type": pub_type,
        "title": title, "body": body, "journal": journal,
        "doi": doi, "url": url,
        "published": published if ok_date else "",
        "date_status": "verified" if ok_date else "unverified",
        "authors": authors or (person.get("name_en") or ""),
        "attribution_confidence": "high",
        "attribution_basis": basis,
        "collected_on": date.today().isoformat(),
    }
    if extra:
        r.update(extra)
    return r


# ───────────────────── ① 期刊评论栏目（Crossref × ORCID）─────────────────────
def _abstract_for(doi: str) -> str:
    """补正文：先 EuropePMC（摘要质量高），再 Crossref 自带 abstract。"""
    q = urllib.parse.quote(f'DOI:"{doi}"')
    s, b, _ = _get("https://www.ebi.ac.uk/europepmc/webservices/rest/search?query="
                   f"{q}&format=json&resultType=core&pageSize=1", timeout=20)
    if s == 200:
        try:
            res = json.loads(b).get("resultList", {}).get("result", [])
            if res and res[0].get("abstractText"):
                return _strip(res[0]["abstractText"])
        except json.JSONDecodeError:
            pass
    s, b, _ = _get(f"https://api.crossref.org/works/{urllib.parse.quote(doi)}", timeout=20)
    if s == 200:
        try:
            return _strip(json.loads(b)["message"].get("abstract", ""))
        except (json.JSONDecodeError, KeyError):
            pass
    return ""


def crossref_opinion_statements(person: dict, months: int = 18,
                                known_dois: set | None = None) -> list[dict]:
    orcid = (person.get("orcid") or "").strip().replace("https://orcid.org/", "")
    if not orcid:
        return []                          # 无 ORCID 不抓（同名污染实测 100%）
    since = (date.today() - timedelta(days=months * 31)).isoformat()
    url = ("https://api.crossref.org/works?filter="
           + urllib.parse.quote(f"orcid:{orcid},from-pub-date:{since}")
           + "&rows=200&select=DOI,title,container-title,type,published,author")
    s, b, _ = _get(url, timeout=40,
                   headers={"User-Agent": "Science-KOL/1.0 (research dashboard)"})
    if s != 200:
        return []
    try:
        items = json.loads(b)["message"]["items"]
    except (json.JSONDecodeError, KeyError):
        return []

    known = known_dois or set()
    out = []
    for it in items:
        title = _strip(" ".join(it.get("title") or []))
        doi = (it.get("DOI") or "").lower()
        if not title or not doi or doi in known:
            continue
        if not (OPINION_RE.search(title) or NATURE_MAG.match(doi)):
            continue
        parts = (it.get("published") or {}).get("date-parts", [[None]])[0]
        pub = ""
        if parts and len(parts) >= 3 and all(parts[:3]):
            pub = f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"
        body = _abstract_for(doi)
        time.sleep(0.4)
        au = ", ".join(f"{a.get('given', '')} {a.get('family', '')}".strip()
                       for a in (it.get("author") or [])[:8])
        out.append(_row(person, "期刊评论", "Comment/Perspective", title, body,
                        (it.get("container-title") or [""])[0],
                        f"https://doi.org/{doi}", pub,
                        f"Crossref ORCID {orcid}", doi=doi, authors=au[:220]))
    return out


# ───────────────────── ② 媒体采访原话（Google News）─────────────────────
def _gn_decode(rss_link: str) -> str:
    """Google News 的 RSS 链接是加密跳转；用 batchexecute 解出原文直链。"""
    m = re.search(r"/articles/([^?]+)", rss_link)
    if not m:
        return ""
    aid = m.group(1)
    # ★ 先走 /rss/articles/，失败再回退 /articles/。
    #   实测 2026-09-25：同一 aid，/articles/ 连续请求后开始超时（-1），
    #   /rss/articles/ 仍 200 且带 data-n-a-sg 签名。只走一条路=整批解不出直链。
    sig = ts = None
    for path in ("rss/articles", "articles"):
        s, b, _ = _get(f"https://news.google.com/{path}/{aid}", timeout=20)
        sig = re.search(r'data-n-a-sg="([^"]+)"', b)
        ts = re.search(r'data-n-a-ts="([^"]+)"', b)
        if sig and ts:
            break
    if not (sig and ts):
        return ""
    inner = (f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,'
             f'null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],'
             f'"{aid}",{ts.group(1)},"{sig.group(1)}"]')
    data = ("f.req=" + urllib.parse.quote(json.dumps([[["Fbv4je", inner]]]))).encode()
    s, b, _ = _get("https://news.google.com/_/DotsSplashUi/data/batchexecute",
                   data=data, timeout=20,
                   headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
    mm = re.search(r'\[\\"garturlres\\",\\"(.*?)\\"', b)
    return mm.group(1).replace("\\\\u003d", "=").replace("\\\\u0026", "&") if mm else ""


def _article_text(html: str) -> tuple[str, str]:
    """取正文与发表日。正文优先 <article>，回退全部 <p>。"""
    pub = ""
    for pat in (r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})',
                r'<meta[^>]+(?:article:published_time|pubdate|publish-date)[^>]+content="(\d{4}-\d{2}-\d{2})',
                r'<time[^>]+datetime="(\d{4}-\d{2}-\d{2})'):
        m = re.search(pat, html)
        if m:
            pub = m.group(1)
            break
    art = re.search(r"<article[^>]*>(.*?)</article>", html, re.S | re.I)
    scope = art.group(1) if art else html
    paras = [_strip(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", scope, re.S | re.I)]
    paras = [p for p in paras if len(p) > 40]
    return pub, "\n".join(paras)


EXTRACT_PROMPT = """你在为「科学界 KOL 言论库」审核一篇媒体报道。只收【该科学家本人的观点】。

目标人物：{name}（{field}；{aff}）
文章标题：{title}
文章正文（节选）：
{body}

判断并只输出 JSON：
{{"same_person": true/false,   // 文中此人与目标人物是同一人？学科/机构/身份须对得上；同名他人=false
 "has_quote": true/false,      // 文中有此人【直接说的话】（引号内原话或明确转述其观点）？只是被提到=false
 "quotes": ["原话1", "原话2"],  // 此人的原话，英文原文，最多3句，逐字摘录不许改写；优先选【陈述他立场】的句子，不要选设问/反问句
 "topic": "一句话主题（中文）",
 "claim": "他的核心判断/论点（中文，要具体，写出对象/机制/数字）",
 "evidence": "他给出的论据或数据（中文；没有就空字符串）",
 "stance_check": "一句话说明 claim 为什么代表他本人的最终立场（中文）"}}
★ 设问句、反问句、他转述的别人观点、他要反驳的观点，都【不是】他的论点。
  例：他说“为什么我们不能一直修复身体、永远活下去？”然后论证这做不到——他的论点是“做不到”，不是“能永生”。
  claim 必须与文章里他的结论方向一致；方向拿不准时 has_quote 填 false。
same_person 或 has_quote 任一为 false 时，其余字段留空。"""


VERIFY_PROMPT = """核对一条「科学家观点摘要」是否忠实于原文。

人物：{name}
摘要写的论点：{claim}

原文相关段落：
{ctx}

问题：原文中 {name} 本人的【最终立场】是否与上述论点方向一致？
注意：设问/反问句、他引述后反驳的观点、记者或他人的观点，都不算他的立场。
只输出 JSON：{{"consistent": true/false, "reason": "一句话中文理由"}}"""


def news_quote_statements(person: dict, days: int = 60,
                          known_urls: set | None = None, max_items: int = 6) -> tuple[list, list]:
    """返回 (入库行, 拒收行)。拒收也留痕，便于抽查闸门是否过严。"""
    name = (person.get("name_en") or "").strip()
    if not name or not _name_words(name)[0]:
        return [], []
    q = urllib.parse.quote(f'"{name}"') + f"+when:{days}d"
    s, b, _ = _get(f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en",
                   timeout=25)
    if s != 200:
        return [], []
    known = known_urls or set()
    kept, rejected = [], []
    def _tag(block: str, tag: str) -> str:
        m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
        return m.group(1) if m else ""

    for it in re.findall(r"<item>(.*?)</item>", b, re.S)[: max_items * 2]:
        if len(kept) >= max_items:
            break
        title = _strip(re.sub(r"<!\[CDATA\[|\]\]>", "", _tag(it, "title")))
        link = _tag(it, "link").strip()
        src = _strip(_tag(it, "source"))
        base = {"person_id": person["id"], "person_name": name, "title": title, "source": src}

        url = _gn_decode(link)
        time.sleep(0.8)
        if not url:
            rejected.append({**base, "reject_reason": "Google News 链接解不出原文直链"})
            continue
        if url in known:
            continue
        s2, h2, final = _get(url, timeout=25)
        if s2 != 200 or not h2:
            rejected.append({**base, "url": url, "reject_reason": f"原文取不到 HTTP {s2}"})
            continue
        pub, body = _article_text(h2)
        if len(body) < 600:
            rejected.append({**base, "url": url, "reject_reason": f"正文不足 600 字符（{len(body)}）"})
            continue
        if not _has_fullname(title + " " + body, name):
            rejected.append({**base, "url": url, "reject_reason": "闸1：正文无名+姓全名"})
            continue

        # ★ 上下文 = 【所有】提到他的段落（按段取，不按字符窗口取前几块）。
        #   实测 2026-09-25 nautil.us：旧做法只取前 4 个窗口，Venki 真正的结论段
        #   （第 29 段 "It's just fantasies at this point"）落在后面没进上下文，
        #   抽取和复核两道都只看到开头的设问句，于是一致地写成「理论上可以永生」——方向反了。
        #   复核再严也救不了没给它看的证据。
        # ★ 本人署名文章：全文都是他的观点，但正文里不会出现他自己的名字。
        #   实测 2026-09-25 Scientific American「Will we ever achieve immortality?」
        #   作者就是 Venki，按「提到姓名的段落」取上下文只拿到署名行和简介，
        #   结论段（第 38 段 "true immortality is out of the question"）进不去 → 被闸3 误拒。
        authored = False
        for pat in (r'<meta[^>]+name="author"[^>]+content="([^"]+)"',
                    r'"author"\s*:\s*\[?\s*\{[^}]*"name"\s*:\s*"([^"]+)"'):
            for au in re.findall(pat, h2):
                if _has_fullname(au, name):
                    authored = True
        first, last = _name_words(name)
        paras = [p for p in body.split("\n") if p.strip()]
        if authored:
            # 全文按段编号给模型；过长时保留开头与结尾（结论常在最后）
            numbered = [f"[{j}] {p}" for j, p in enumerate(paras)]
            full = "\n".join(numbered)
            ctx = full if len(full) <= 9000 else "\n".join(numbered[:12] + ["…"] + numbered[-18:])[:9000]
        else:
            hit = [i for i, p in enumerate(paras)
                   if re.search(r"\b" + re.escape(last) + r"\b", p, re.I)]
            # 他说话的段落常用 he/she 续接，把紧邻的下一段也带上
            keep = sorted({j for i in hit for j in (i, i + 1) if j < len(paras)})
            ctx = "\n".join(f"[{j}] {paras[j]}" for j in keep) if keep else body[:6000]
            ctx = ctx[:9000]
        raw = llm(EXTRACT_PROMPT.format(
            name=name, field=person.get("field", ""),
            aff=(person.get("affiliation") or "")[:120],
            title=title + ("（★ 本文作者即该科学家本人，全文均为其观点）" if authored else ""),
            body=ctx), max_tokens=900)
        time.sleep(LLM_SLEEP)
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            js = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            js = {}
        if not isinstance(js, dict) or not js.get("same_person"):
            rejected.append({**base, "url": url, "reject_reason": "闸3：LLM 判定非同一人或无法判断"})
            continue
        quotes = [q for q in (js.get("quotes") or []) if isinstance(q, str) and len(q) > 15]
        # 原话必须真在正文里（防 LLM 编造）：取前 40 字符做子串核对
        quotes = [q for q in quotes if q[:40].lower().strip('"“” ') in body.lower()]
        if not js.get("has_quote") or not quotes or not js.get("claim"):
            rejected.append({**base, "url": url, "reject_reason": "闸3：无本人原话或无明确论点"})
            continue

        text = ("原话：" + " / ".join(f"“{q}”" for q in quotes)
                + f"\n论点：{js.get('claim')}"
                + (f"\n论据：{js['evidence']}" if js.get("evidence") else ""))

        # ★ 闸4：独立复核论点方向（硬门禁，不靠 prompt 自觉）。
        #   实测 2026-09-25：Venki 在 nautil.us 用设问「为什么不能一直修复身体、永远活下去？」
        #   开场，然后论证做不到；抽取模型把设问当成论点，写成「理论上可以永生」——方向完全反了。
        #   仅在抽取 prompt 里加提示后复测仍然错，所以改成第二次独立调用做核对。
        verdict = llm(VERIFY_PROMPT.format(name=name, claim=js.get("claim"),
                                           ctx=ctx), max_tokens=200)
        time.sleep(LLM_SLEEP)
        vm = re.search(r"\{.*\}", verdict, re.S)
        try:
            vj = json.loads(vm.group(0)) if vm else {}
        except json.JSONDecodeError:
            vj = {}
        if not isinstance(vj, dict) or vj.get("consistent") is not True:
            rejected.append({**base, "url": url,
                             "reject_reason": "闸4：论点方向复核不通过 — "
                             + str(vj.get("reason") or "复核无结果")[:80],
                             "claim_rejected": js.get("claim")})
            continue
        kept.append(_row(person, "媒体采访" if not authored else "署名文章",
                         "采访/报道引语" if not authored else "本人署名评论",
                         title, text, src, url, pub,
                         (f"作者署名匹配（{src}）" if authored
                          else f"Google News 全名命中 + LLM 同一人核验（{src}）")
                         + " + 论点方向独立复核",
                         extra={"quotes": quotes, "topic_zh": js.get("topic", ""),
                                "claim_zh": js.get("claim", ""),
                                "evidence_zh": js.get("evidence", ""),
                                "article_body": body[:12000]}))
    return kept, rejected
