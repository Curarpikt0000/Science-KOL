#!/bin/bash
# Science-KOL 日链 cron 包装 —— 后台执行版。
#
# ★ 为什么必须后台跑：Hermes no_agent cron 有 120 秒硬上限，
#   而完整日链（963 条文献 + 60 条 LLM 摘要）实测 80-100 秒，余量太小，
#   源站慢一点就被杀在半路（2026-09-13 首次试跑即被截断在第 1 步）。
#   故本包装只【启动】后台任务并立即返回，由下一次 tick 或 watchdog 汇报结果。
set -uo pipefail
PROJ="<PROJECT_ROOT>"
LOG="$PROJ/logs/daily_$(date +%F).log"
LOCK="$PROJ/logs/.daily.lock"
mkdir -p "$PROJ/logs"

# 已在跑则不重复启动（幂等）
if [ -f "$LOCK" ]; then
  PID=$(cat "$LOCK" 2>/dev/null)
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    exit 0    # 静默：上一轮还在跑
  fi
fi

# 先汇报【上一轮】结果（本轮结果由下次 tick 报），避免超时
PREV="$PROJ/logs/last_result.txt"
if [ -f "$PREV" ]; then
  if grep -q "FAILED" "$PREV"; then
    echo "Science-KOL 上一轮日链失败："
    cat "$PREV"
  else
    TOTAL=$(grep -oE "[0-9]+" "$PREV" | head -1)
    if [ -n "$TOTAL" ] && [ "$TOTAL" -lt 100 ]; then
      echo "Science-KOL 上一轮产出偏低：仅 ${TOTAL} 条文献（正常 600-1000+）"
      cat "$PREV"
    fi
  fi
  rm -f "$PREV"
fi

# 启动本轮（后台，不阻塞 cron）
nohup bash -c "
  if bash '$PROJ/scripts/daily_chain.sh' > '$LOG' 2>&1; then
    T=\$(grep -oE '总计 [0-9]+' '$LOG' | tail -1 | grep -oE '[0-9]+')
    echo \"\${T:-0} 条文献，\$(date '+%F %T')\" > '$PREV'
  else
    echo \"FAILED \$(date '+%F %T')\" > '$PREV'
    tail -15 '$LOG' >> '$PREV'
  fi
  rm -f '$LOCK'
" > /dev/null 2>&1 &

echo $! > "$LOCK"
exit 0
