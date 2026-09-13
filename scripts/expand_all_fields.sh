#!/bin/bash
# 全量展开 8 门类名册：拉候选 → 探测公共表达 → 四维打分入册 → 核验在世。
# 分门类串行，每类独立落盘，中途失败可从任一门类续跑。
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
PY="$(pwd)/.venv/bin/python3"
[ -x "$PY" ] || PY="python3"

FIELDS=("医学健康" "生命科学" "AI计算机" "物理天文" "化学材料" "神经认知" "地球气候" "数学基础理论")
PROBE_N="${PROBE_N:-30}"   # 每门类探测前 N 个候选

for f in "${FIELDS[@]}"; do
  echo "################ $f ################"
  # 已探测过的门类跳过候选拉取（幂等）
  $PY scripts/build_candidates.py "$f" 2>&1 | tail -3
  $PY scripts/probe_public_voice.py "$f" "$PROBE_N" 2>&1 | tail -4
  $PY scripts/score_and_admit.py "$f" 2>&1 | tail -18
  echo
done

echo "################ 在世核验 ################"
$PY scripts/verify_alive.py --apply 2>&1 | tail -12

echo "################ 重算星级 + 建面板 ################"
$PY -c "
import sys, json
sys.path.insert(0,'scripts')
from roster import load_roster, save_roster, assign_stars
r = load_roster()
assign_stars(r['people'])
save_roster(r)
import collections
print('名册', r['count'], '人 / active', r['active_count'])
for k,v in sorted(collections.Counter(p['field'] for p in r['people']).items(), key=lambda x:-x[1]):
    print(f'  {k}: {v}')
"
$PY scripts/build_dashboard.py
