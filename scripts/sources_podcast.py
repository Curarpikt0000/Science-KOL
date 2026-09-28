"""Science-KOL 播客源（Chao 2026-09-25 批「可以」试样板）。

链路：Apple Podcasts 搜索（按人名，剧集标题/简介须含全名）
      → 下载 mp3（RSS 公开直链）→ faster-whisper 本机转写（不经任何网关）
      → LLM 从转写里抽「嘉宾本人」的观点 → 独立复核（说话人 + 论点方向）

为什么不用 YouTube：2026-09-25 实测 VM 被判机器人，20 个视频 19 个「Sign in to confirm
you're not a bot」，换两份 cookies、无 cookies 结果相同。播客 RSS 是公开 mp3，无此问题。

★ 转写没有说话人标注，主持人和嘉宾的话混在一起——这是本源最大的风险。
  对策：①抽取时要求逐字引用 + 给出时间戳 ②复核时把引文前后 90 秒的原始转写交给独立调用，
  判断这段话是嘉宾说的还是主持人说的 ③引文必须能在转写里逐字找到（防模型改写/编造）。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.parse
from pathlib import Path

import sources_extra as sx  # 复用 _get / llm / _has_fullname / _row / LLM_SLEEP

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "scratch" / "podcast"
WHISPER_PY = os.environ.get(
    "SK_WHISPER_PY", "/home/user/Projects/AI-Blog-Generator/.venv/bin/python")
WHISPER_CACHE = os.environ.get(
    "SK_WHISPER_CACHE", "/home/user/Projects/AI-Blog-Generator/.cache/whisper")
MIN_MIN, MAX_MIN = 15, 150        # 太短多是摘要/书评朗读，太长转写成本高
# 书籍摘要类频道：不是本人发言，是别人朗读/总结他的书
SUMMARY_RE = re.compile(r"summary|summaries|zusammenfass|audiobook|สรุป|書房|book review", re.I)


def search_episodes(person: dict, days: int = 60, limit: int = 40) -> list[dict]:
    name = person.get("name_en") or ""
    q = urllib.parse.quote(name)
    s, b, _ = sx._get("https://itunes.apple.com/search?term="
                      f"{q}&media=podcast&entity=podcastEpisode&limit={limit}", timeout=30)
    if s != 200:
        return []
    try:
        rows = json.loads(b).get("results", [])
    except json.JSONDecodeError:
        return []
    lo = time.strftime("%Y-%m-%d", time.gmtime(time.time() - days * 86400))
    out = []
    for r in rows:
        title = r.get("trackName") or ""
        desc = r.get("description") or r.get("shortDescription") or ""
        pub = (r.get("releaseDate") or "")[:10]
        mins = (r.get("trackTimeMillis") or 0) / 60000
        if pub < lo or not r.get("episodeUrl"):
            continue
        # 同名闸1：剧集标题或简介必须出现名+姓全名
        if not (sx._has_fullname(title, name) or sx._has_fullname(desc, name)):
            continue
        if SUMMARY_RE.search(title + " " + (r.get("collectionName") or "")):
            continue
        if not (MIN_MIN <= mins <= MAX_MIN):
            continue
        # ★ 旧节目重新上架：上架日期 ≠ 实际发表日。实测 2026-09-25「The Art Bell Archive |
        #   September 22, 2015: Climate Change - Dr. Trenberth」上架日在 60 天内，内容是 2015 年的。
        #   按实际发表日分档的规矩，这类一律不收（取不到真实日期就不收，绝不用上架日顶替）。
        years = [int(y) for y in re.findall(r"\b(19[5-9]\d|20[0-2]\d)\b", title)]
        if years and min(years) < int(pub[:4]) - 1:
            continue
        if re.search(r"\barchive|rerun|re-?release|classic episode|best of\b", title + " " + (r.get("collectionName") or ""), re.I):
            continue
        out.append({"title": title, "show": r.get("collectionName") or "",
                    "published": pub, "minutes": round(mins),
                    "audio": r["episodeUrl"], "page": r.get("trackViewUrl") or r["episodeUrl"],
                    "desc": sx._strip(desc)[:800]})
    return out


def transcribe(ep: dict) -> list[dict]:
    """下载 + 本机转写；结果按音频链接哈希缓存，重跑不重复烧 CPU。"""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = re.sub(r"[^a-zA-Z0-9]", "", ep["audio"])[-40:]
    tj = CACHE / f"{key}.json"
    if tj.exists():
        return json.loads(tj.read_text(encoding="utf-8"))
    mp3 = CACHE / f"{key}.mp3"
    r = subprocess.run(["curl", "-sSL", "--max-time", "600", "-A", "Mozilla/5.0",
                        "-o", str(mp3), ep["audio"]], capture_output=True, text=True)
    if r.returncode != 0 or not mp3.exists() or mp3.stat().st_size < 500_000:
        return []
    code = (
        "import json,sys\n"
        "from faster_whisper import WhisperModel\n"
        f"m=WhisperModel('small',device='cpu',compute_type='int8',download_root={WHISPER_CACHE!r})\n"
        f"segs,_=m.transcribe({str(mp3)!r},language='en',beam_size=1,vad_filter=True)\n"
        "out=[{'s':round(s.start,1),'t':s.text.strip()} for s in segs]\n"
        f"json.dump(out,open({str(tj)!r},'w'),ensure_ascii=False)\n")
    r = subprocess.run([WHISPER_PY, "-c", code], capture_output=True, text=True, timeout=1800)
    mp3.unlink(missing_ok=True)          # 音频不留盘（单集 40-100MB）
    if r.returncode != 0 or not tj.exists():
        return []
    return json.loads(tj.read_text(encoding="utf-8"))


def _mmss(sec: float) -> str:
    return f"{int(sec // 60)}:{int(sec % 60):02d}"


EXTRACT = """下面是一期播客的机器转写（无说话人标注，主持人和嘉宾的话混在一起）。
嘉宾：{name}（{field}；{aff}）
节目：{show}｜剧集：{title}
剧集简介：{desc}

转写（[分:秒] 文本）：
{text}

任务：找出嘉宾 {name} 本人在这段转写里表达的【最重要的 0-2 个观点】（这是整期节目的第 {part} 段）。
规则：
- 只要嘉宾的观点。主持人的提问、主持人的总结、嘉宾转述的别人观点都不算。
- 判断依据：提问句多来自主持人；长段、第一人称、讲自己研究/书/经历的，多来自嘉宾。拿不准就不要。
- 闲聊、寒暄、自我描述（年龄、外貌、经历趣事）不是观点，不要。观点 = 对科学/技术/社会问题的判断。
- ★ 他常先抛出一个说法再自己限定或推翻（"没有物理定律限制寿命……但这并不说明什么"）。
  这种情况 claim 必须写他的【最终立场】，quote 选表达最终立场的那句，不要只截前半句。
- quote 必须从转写里【逐字复制】一段连续原文（15-60 个英文词），不许改写、不许拼接。
- claim 要具体（写出对象/机制/数字），不要泛泛的「科学很重要」。
- weight：这个观点有多重要、多有信息量（1-5；5=明确、有争议或可检验的判断）。
- 这段里没有合格观点就返回空数组，不要凑数。
只输出 JSON：
{{"is_guest": true/false,        // 这期的嘉宾确实是 {name} 本人（而非只是谈论他/他的书）？
 "points": [{{"ts": "分:秒", "quote": "逐字原文", "topic": "中文主题", "claim": "中文论点（最终立场）", "evidence": "中文论据或空", "weight": 1-5}}]}}"""

VERIFY = """核对播客转写中的一段话是不是嘉宾本人说的，以及论点概括是否忠实。

嘉宾：{name}
被认定为嘉宾说的原话：「{quote}」
概括的论点：{claim}

原话前后约 90 秒的原始转写（无说话人标注）：
{window}

问题：
1) 这段原话是嘉宾 {name} 说的，而不是主持人说的？（看上下文：前面是不是主持人在提问、这段是不是在回答）
2) 概括的论点与他的【最终立场】方向一致？★ 特别检查：原话之后他有没有紧接着自己限定、反转或推翻
   （如"但这并不说明什么""不过我不这么认为"）——有的话，只截前半句的概括算不一致。
3) 这是一个实质观点（对科学/技术/社会问题的判断），而不是闲聊、自我描述或趣事？
只输出 JSON：{{"speaker_is_guest": true/false, "consistent": true/false, "substantive": true/false, "reason": "一句话中文理由"}}"""


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", s.lower())).strip()


PRE = """根据播客元数据判断嘉宾身份。
目标科学家：{name}（学科：{field}）
节目：{show}
剧集：{title}
简介：{desc}

在下面三个选项里选一个：
- "target"：嘉宾就是这位科学家（标题/简介里以嘉宾身份出现，身份描述与其学科相符或至少不矛盾）
- "other"：有明确证据表明是【同名的另一个人】（简介写明他是企业高管/金融分析师/运动员等，与学科明显不符），
           或节目明确只是讨论他/他的书而他本人不在场
- "unsure"：信息不足，无法判断
注意：元数据里的人名都是真实原文，没有被匿名化。机构信息可能过时，不要因为机构对不上就判 other。
只输出 JSON：{{"verdict": "target"|"other"|"unsure", "reason": "一句话中文，other 时必须写出证据"}}"""


def _pre_gate(person: dict, ep: dict) -> tuple[bool, str]:
    """转写前的便宜闸：只拦【有明确证据】的同名他人/本人不在场，省转写 CPU。

    ★ 实测 2026-09-25：二值版（是/否）把 15/21 集判为否，其中多条理由是
      「嘉宾被匿名化，无法确认」——元数据里人名完好（逐字回显验证过），是模型拿不准时的托词。
      Leskovec 那集同一输入连跑 3 次都这么拒。另外名册机构有错（Leskovec 挂 Palo Alto University），
      会进一步诱发误拒。所以改三档：只有 other 拒，unsure 放行给后面的转写闸（闸2/闸3）判。
    """
    raw = sx.llm(PRE.format(name=person.get("name_en"), field=person.get("field", ""),
                            show=ep["show"], title=ep["title"], desc=ep["desc"][:700]),
                 max_tokens=200)
    time.sleep(sx.LLM_SLEEP)
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        js = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        js = {}
    if not isinstance(js, dict):
        js = {}
    if js.get("verdict") == "other":
        return False, str(js.get("reason") or "")[:80]
    return True, str(js.get("verdict") or "无结果→放行")


def podcast_statements(person: dict, days: int = 60, known_urls: set | None = None,
                       max_eps: int = 2, only_episode: dict | None = None) -> tuple[list, list]:
    name = person.get("name_en") or ""
    known = known_urls or set()
    kept, rejected = [], []
    if only_episode is not None:
        eps = [only_episode]
    else:
        eps = [e for e in search_episodes(person, days) if e["page"] not in known][:max_eps]
    for ep in eps:
        base = {"person_id": person["id"], "person_name": name,
                "title": ep["title"], "source": ep["show"], "url": ep["page"]}
        ok, why = _pre_gate(person, ep)
        if not ok:
            rejected.append({**base, "reject_reason": "闸0：元数据判定非本人做客 — " + why})
            continue
        segs = transcribe(ep)
        if not segs:
            rejected.append({**base, "reject_reason": "下载或转写失败"})
            continue
        full = "\n".join(f"[{_mmss(s['s'])}] {s['t']}" for s in segs)
        # 同名闸2：转写里要出现姓（主持人介绍嘉宾时几乎必提）
        last = sx._name_words(name)[1]
        if not re.search(r"\b" + re.escape(last) + r"\b", full, re.I):
            rejected.append({**base, "reject_reason": "闸2：转写中未出现嘉宾姓氏"})
            continue
        # ★ 全文分段抽取，不截首尾。实测 2026-09-25：48 分钟节目转写 41K 字符，
        #   旧做法只送首尾各 12K，中间 14:13 之后约 17K 字符（整整一大段讨论）模型根本没看到。
        CH = 11000
        chunks, cur = [], ""
        for line in full.split("\n"):
            if len(cur) + len(line) > CH and cur:
                chunks.append(cur)
                cur = cur[-800:]            # 段间留 800 字符重叠，防一句话被切断
            cur += line + "\n"
        if cur.strip():
            chunks.append(cur)
        points, guest_votes = [], []
        for ci, text in enumerate(chunks, 1):
            raw = sx.llm(EXTRACT.format(name=name, field=person.get("field", ""),
                                        aff=(person.get("affiliation") or "")[:100],
                                        show=ep["show"], title=ep["title"],
                                        desc=ep["desc"][:500], text=text,
                                        part=f"{ci}/{len(chunks)}"), max_tokens=1200)
            time.sleep(sx.LLM_SLEEP)
            m = re.search(r"\{.*\}", raw, re.S)
            try:
                js = json.loads(m.group(0)) if m else {}
            except json.JSONDecodeError:
                js = {}
            if not isinstance(js, dict):
                continue
            guest_votes.append(js.get("is_guest") is True)
            for pt in js.get("points") or []:
                if isinstance(pt, dict):
                    points.append(pt)
        # 闸3：多数分段判定嘉宾是本人（而非只谈论他/他的书）
        if not guest_votes or sum(guest_votes) * 2 <= len(guest_votes):
            rejected.append({**base, "reject_reason": "闸3：非本人做客（只是谈论他/他的书）或无法判断"})
            continue
        # 按重要度取前几条去复核（复核还会再砍）
        def _w(p):
            try:
                return -int(p.get("weight") or 0)
            except (TypeError, ValueError):
                return 0
        points.sort(key=_w)
        corpus = _norm(" ".join(s["t"] for s in segs))
        n_ok = 0
        for pt in points[:5]:
            if n_ok >= 3:
                break
            q = (pt.get("quote") or "").strip()
            # 闸4a：引文必须能在转写里逐字找到（防改写/编造）
            if len(q.split()) < 8 or _norm(q) not in corpus:
                rejected.append({**base, "reject_reason": "闸4a：引文在转写中找不到原文",
                                 "claim_rejected": pt.get("claim")})
                continue
            # 取引文所在时间点前后 90 秒的原始转写
            head = _norm(q)[:40]
            idx = next((i for i, s in enumerate(segs) if head[:20] in _norm(s["t"])), None)
            if idx is None:
                acc = ""
                for i, s in enumerate(segs):
                    acc += " " + _norm(s["t"])
                    if head in acc:
                        idx = i
                        break
            idx = idx or 0
            t0 = segs[idx]["s"]
            window = "\n".join(f"[{_mmss(s['s'])}] {s['t']}" for s in segs
                               if t0 - 90 <= s["s"] <= t0 + 90)
            v = sx.llm(VERIFY.format(name=name, quote=q, claim=pt.get("claim"),
                                     window=window[:6000]), max_tokens=200)
            time.sleep(sx.LLM_SLEEP)
            vm = re.search(r"\{.*\}", v, re.S)
            try:
                vj = json.loads(vm.group(0)) if vm else {}
            except json.JSONDecodeError:
                vj = {}
            if not (isinstance(vj, dict) and vj.get("speaker_is_guest") is True
                    and vj.get("consistent") is True and vj.get("substantive") is True):
                rejected.append({**base, "reject_reason": "闸4b：说话人/论点/实质性复核不通过 — "
                                 + str(vj.get("reason") or "复核无结果")[:80],
                                 "claim_rejected": pt.get("claim")})
                continue
            n_ok += 1
            ts = _mmss(t0)
            body = (f"原话（{ts}）：“{q}”\n论点：{pt.get('claim')}"
                    + (f"\n论据：{pt['evidence']}" if pt.get("evidence") else ""))
            row = sx._row(person, "播客", "播客/访谈节目", f"{ep['title']}（{ts}）", body,
                          ep["show"], f"{ep['page']}#t={int(t0)}", ep["published"],
                          f"Apple Podcasts 全名命中 + 本机转写 + 引文逐字核对 + 说话人/论点独立复核（{ep['show']}）",
                          extra={"quotes": [q], "topic_zh": pt.get("topic", ""),
                                 "claim_zh": pt.get("claim", ""),
                                 "evidence_zh": pt.get("evidence", ""),
                                 "timestamp": ts, "episode_url": ep["page"]})
            kept.append(row)
    return kept, rejected
