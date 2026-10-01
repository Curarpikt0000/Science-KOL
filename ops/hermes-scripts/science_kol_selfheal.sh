#!/bin/bash
# Science-KOL 自愈 watchdog（每小时，no_agent）。
# 检查今日产物是否存在且新鲜；异常则自愈一次。正常静默不推送。
set -uo pipefail
PROJ="<PROJECT_ROOT>"
TODAY=$(date +%F)
LIT="$PROJ/data/literature/$TODAY.json"
DASH="$PROJ/dashboard/index.html"
LOCK="$PROJ/logs/.daily.lock"
HOUR=$(date +%-H)

# 每日 06:45 跑，早于此不检查（避免凌晨误报）
[ "$HOUR" -lt 8 ] && exit 0

# 正在跑就不打扰
if [ -f "$LOCK" ]; then
  PID=$(cat "$LOCK" 2>/dev/null)
  [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null && exit 0
fi

PROBLEM=""
[ -f "$LIT" ] || PROBLEM="今日文献文件缺失"
if [ -f "$DASH" ]; then
  AGE=$(( ($(date +%s) - $(stat -c %Y "$DASH")) / 3600 ))
  [ "$AGE" -gt 26 ] && PROBLEM="${PROBLEM:+$PROBLEM; }面板已 ${AGE}h 未更新"
else
  PROBLEM="${PROBLEM:+$PROBLEM; }面板文件缺失"
fi

[ -z "$PROBLEM" ] && exit 0   # 本地产物正常

# ── 公网可达性（Chao 2026-09-21 加）────────────────────────────
# ★ 事故：GitHub 账号级 Pages 故障，公网 404 了 7 天，而本 watchdog 每小时跑一次
#   却从没报警——因为它【只看本地产物】，本地一切正常。
#   ⇒ 健康判据必须包含「用户真正打开的那个地址」。
# 判据是 HTTP 码而非内容：内容比对留给 publish_cf_pages.sh 的 sha 闸。
# 两条公网通道【都】不可达才算故障（单条挂掉由另一条兜住，不吵醒人）。
PUB_BAD=""
PUB_DOWN=0
for U in "https://science-kol.pages.dev/" \
         "https://curarpikt0000.github.io/Science-KOL/"; do
  CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 25 "$U?cb=$RANDOM" 2>/dev/null)
  if [ "$CODE" != "200" ]; then
    PUB_DOWN=$((PUB_DOWN + 1))
    PUB_BAD="${PUB_BAD:+$PUB_BAD, }${U} → ${CODE:-超时}"
  fi
done
# 只有【全部 2 条】都挂才升级为 PROBLEM（单条挂由另一条兜住，不吵醒人）
# ★ 别用 `grep -c` 数 PUB_BAD：它是单行拼接串，按行计数永远 ≤1 → 警报器永不响。
if [ "$PUB_DOWN" -ge 2 ]; then
  PROBLEM="公网全部不可达：$PUB_BAD"
fi

[ -z "$PROBLEM" ] && exit 0   # 一切正常，静默

# 自愈一次
# ★ 按故障类型选动作：公网挂了只需重发布，不该重抓一遍文献（浪费 40 分钟 + LLM 配额）。
HEAL="$PROJ/logs/selfheal_$(date +%F_%H%M).log"
if [ "${PUB_DOWN:-0}" -ge 2 ] && [ -f "$DASH" ]; then
  ACTION="重新发布"
  CMD="$PROJ/scripts/publish.sh"
else
  ACTION="重建"
  CMD="$PROJ/scripts/daily_chain.sh"
fi
if bash "$CMD" > "$HEAL" 2>&1; then
  T=$(grep -oE '总计 [0-9]+' "$HEAL" | tail -1 | grep -oE '[0-9]+')
  echo "Science-KOL 自愈成功：$PROBLEM → 已${ACTION}${T:+，${T} 条文献}"
else
  echo "Science-KOL 自愈失败：$PROBLEM（尝试${ACTION}）"
  tail -12 "$HEAL"
fi
