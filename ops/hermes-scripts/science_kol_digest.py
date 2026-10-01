#!/usr/bin/env python3
"""Science-KOL 每日日报（Chao 2026-09-25 要求：每次跑完把当天拿到的重要 KOL 言论发到对话里）。

no_agent 模式：stdout 原样投递到 Telegram 话题。纯数据格式化，不调 LLM。

口径（重要）：
  data/statements/<日期>.json 是 18 个月窗口的【全量快照】，每条都标当天抓取，
  所以「当天拿到的」= 今天快照里、之前任何一天快照都没出现过的 URL。
  绝不把全量快照当新增报（那样天天报 180 条同样的东西）。

日链没跑完 / 失败时如实报状态，绝不拿旧数据冒充今日产出。
"""
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path("<PROJECT_ROOT>")
S_DIR = ROOT / "data" / "statements"
L_DIR = ROOT / "data" / "literature"
MAX_STMT = 8        # 言论最多列几条（Telegram 单条 4096 字符上限）
WINDOW_DAYS = 7     # 言论窗口：近 N 天发表或首次入库（Chao 2026-09-25 批 B 方案）
MAX_LIT = 5         # 文献要闻条数
SITE = "https://science-kol.pages.dev/"


def load(p: Path):
    d = json.loads(p.read_text(encoding="utf-8"))
    return d if isinstance(d, list) else d.get("items", [])


def clip(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    return s if len(s) <= n else s[:n].rstrip("，。；、 ") + "…"


def stars(r) -> str:
    try:
        n = int(r)
    except (TypeError, ValueError):
        return ""
    return "★" * max(0, min(5, n))


def chain_status(today: str) -> tuple[bool, str]:
    log = ROOT / "logs" / f"daily_{today}.log"
    if not log.exists():
        return False, "今日日链没有日志（06:45 未启动或被跳过）"
    txt = log.read_text(encoding="utf-8", errors="replace")
    if "=== 完成" not in txt:
        last = [l for l in txt.splitlines() if re.match(r"^\[\d+/10\]", l)]
        where = last[-1] if last else "未知步骤"
        if "Traceback" in txt or "失败" in txt:
            return False, f"今日日链失败，停在：{where}"
        return False, f"今日日链还没跑完，当前在：{where}"
    m = re.search(r"=== 完成 (\S+ \S+)", txt)
    fails = re.findall(r"(\d+) 失败", txt)
    nfail = sum(int(x) for x in fails)
    pub = "已发布" if "发布完成" in txt else "发布未确认"
    return True, f"日链 {m.group(1)[11:16] if m else ''} 跑完｜Notion 失败 {nfail}｜{pub}"


def main() -> int:
    today = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    ok, status = chain_status(today)
    out = [f"Science-KOL 日报 {today}", status]

    if not ok:
        out.append("今日产出未就绪，本期不列言论（不拿昨天数据顶替）。")
        print("\n".join(out))
        return 0

    reg = json.loads((ROOT / "data" / "kol_registry.json").read_text(encoding="utf-8"))
    people = {p["id"]: p for p in reg["people"]}
    n_active = sum(1 for p in reg["people"] if p.get("active"))

    # ── KOL 言论：近 7 天（Chao 2026-09-25 批 B 方案）──────────────────
    #   口径：「近 7 天发表」或「近 7 天首次入库」任一即列入。
    #   日文件是 18 个月窗口的全量快照，所以「首次入库日」= 该 URL 第一次出现在哪天的文件里。
    #   ★ 首次入库日只算日文件里的首次出现；发表日取不到的不用抓取日顶替（仍标「日期未核实」）。
    files = sorted(S_DIR.glob("*.json"))
    tf = S_DIR / f"{today}.json"
    if not tf.exists():
        out.append("今日观点文件缺失。")
        print("\n".join(out))
        return 0
    first_seen: dict = {}
    for f in files:
        if f.stem > today:
            continue
        for x in load(f):
            u = x.get("url")
            if u and u not in first_seen:
                first_seen[u] = f.stem
    today_items = load(tf)
    t0 = date.fromisoformat(today)
    lo = (t0 - timedelta(days=WINDOW_DAYS - 1)).isoformat()

    def _in_window(x) -> bool:
        pub = x.get("published") or ""
        fs = first_seen.get(x.get("url"), today)
        return (lo <= pub <= today) or (lo <= fs <= today)

    new = [x for x in today_items if x.get("url") and _in_window(x)]
    n_today = sum(1 for x in new if first_seen.get(x["url"]) == today)
    # 排序：今天首次入库的排前面，其次星级，再按发表日新→旧
    new.sort(key=lambda x: (first_seen.get(x["url"]) != today,
                            -int(people.get(x.get("person_id"), {}).get("rating") or 0),
                            "" if not x.get("published") else
                            "".join(chr(0x10FFFF - ord(c)) for c in x["published"])))

    out.append("")
    out.append(f"一、KOL 言论（在册 {n_active} 人｜近 {WINDOW_DAYS} 天 {len(new)} 条，其中今日新入 {n_today} 条）")
    if not new:
        out.append(f"近 {WINDOW_DAYS} 天无新言论。")
    for x in new[:MAX_STMT]:
        p = people.get(x.get("person_id"), {})
        name = p.get("name_zh") or x.get("person_name") or ""
        en = x.get("person_name") or ""
        who = f"{name}（{en}）" if name and en and name != en else (name or en)
        tag = "【今日新入】" if first_seen.get(x["url"]) == today else ""
        head = (f"{tag}{stars(p.get('rating'))} {who}｜{p.get('field', '')}｜"
                f"{x.get('channel') or ''}｜发表 {x.get('published') or '日期未核实'}")
        out.append("")
        out.append(head.strip())
        out.append(f"《{clip(x.get('title_zh') or x.get('title'), 60)}》")
        lead = x.get("l1_lead") or x.get("claim_zh")
        if lead:
            out.append(f"要点：{clip(lead, 120)}")
        if x.get("quotes"):
            out.append(f"原话：“{clip(x['quotes'][0], 160)}”")
        if x.get("l2_summary"):
            out.append(f"展开：{clip(x['l2_summary'], 200)}")
        out.append(f"来源：{x.get('journal') or x.get('channel') or ''} {x.get('url')}")
    if len(new) > MAX_STMT:
        out.append(f"……另有 {len(new) - MAX_STMT} 条见面板")

    # ── 文献要闻：今天首次出现、重要度最高的 ───────────────────
    lf = L_DIR / f"{today}.json"
    out.append("")
    if lf.exists():
        lit = load(lf)
        prev = sorted(f for f in L_DIR.glob("*.json") if f.stem < today)
        lseen = {x.get("url") for x in load(prev[-1])} if prev else set()
        # ★ 中文取自展示层 layers：当日原始文件只有少数条目带 title_zh（实测 393/2131），
        #   翻译脚本只翻面板实际展示的条目。日报与面板同口径，且保证全中文。
        zh = {}
        lay_f = ROOT / "data" / "layers" / "literature_layers.json"
        if lay_f.exists():
            lay = json.loads(lay_f.read_text(encoding="utf-8"))
            pools = [d.get("items", []) for d in lay.get("daily", {}).values()]
            pools += [d.get("top_items", []) for d in lay.get("monthly", {}).values()]
            pools += [d.get("top_items", []) for d in lay.get("yearly", {}).values()]
            for pool in pools:
                for it in pool:
                    if it.get("url") and it.get("title_zh"):
                        zh[it["url"]] = it
        for x in lit:
            z = zh.get(x.get("url"))
            if z:
                x.setdefault("title_zh", z.get("title_zh"))
                x.setdefault("summary_zh", z.get("summary_zh"))
        lnew = [x for x in lit if x.get("url") not in lseen and x.get("field")
                and re.search(r"[\u4e00-\u9fff]", x.get("title_zh") or "")]
        lnew.sort(key=lambda x: -(x.get("importance") or 0))
        out.append(f"二、文献要闻（今日新入且已中文化 {len(lnew)} 篇，按重要度取前 {min(MAX_LIT, len(lnew))}）")
        for x in lnew[:MAX_LIT]:
            t = clip(x.get("title_zh") or x.get("title"), 50)
            out.append(f"· [{x.get('field')}] {t}｜{x.get('source', '')}")
            if x.get("summary_zh"):
                out.append(f"  {clip(x['summary_zh'], 90)}")
        if not lnew:
            out.append("今日无新入文献。")
    else:
        out.append("二、文献要闻：今日文献文件缺失。")

    out.append("")
    out.append(f"面板：{SITE}")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
