#!/bin/bash
# 续跑剩余门类（幂等：已入册的人不会重复添加，名册只增不减）
set -uo pipefail
cd /home/user/Projects/Science-KOL || exit 1
PY="/home/user/Projects/Science-KOL/.venv/bin/python3"

for f in "神经认知" "地球气候" "数学基础理论"; do
  echo "################ $f ################"
  $PY scripts/build_candidates.py "$f" 2>&1 | tail -2
  $PY scripts/probe_public_voice.py "$f" 30 2>&1 | tail -3
  $PY scripts/score_and_admit.py "$f" 2>&1 | tail -16
  echo
done

echo "################ 在世核验 ################"
$PY scripts/verify_alive.py --apply 2>&1 | tail -10

echo "################ 重算星级 ################"
$PY -c "
import sys, json, collections
sys.path.insert(0,'scripts')
from roster import load_roster, save_roster, assign_stars
r = load_roster(); assign_stars(r['people']); save_roster(r)
print('名册', r['count'], '人 / active', r['active_count'])
for k,v in sorted(collections.Counter(p['field'] for p in r['people']).items(), key=lambda x:-x[1]):
    print(f'  {k}: {v}')
"
echo "################ 全量言论抓取 ################"
$PY scripts/fetch_statements.py 2>&1 | tail -8
$PY scripts/build_dashboard.py
echo "ALL DONE $(date '+%F %T')"
