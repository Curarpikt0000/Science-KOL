#!/bin/bash
# Science-KOL 每日链路：抓文献 → 分流+摘要 → 分层 → 建面板 → 发布
# 供 cron 调用。任一步失败即中止，不带着坏数据往下走。
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"
PY="$ROOT/.venv/bin/python3"
[ -x "$PY" ] || PY="python3"

# ★ 代理地址属本机实现细节，不进公网仓库。
#   从 .env.local（gitignored）读取；没有就跳过 LLM 摘要（规则分流不受影响）。
[ -f "$ROOT/.env.local" ] && . "$ROOT/.env.local"
export SK_LLM_TOPN="${SK_LLM_TOPN:-60}"

echo "=== Science-KOL 日链 $(date '+%F %T %Z') ==="

echo "[1/6] 抓取文献"
$PY scripts/fetch_literature.py || { echo "抓取失败"; exit 1; }

echo "[2/6] 分流 + 中文摘要"
$PY scripts/classify_literature.py || { echo "分流失败"; exit 1; }

echo "[3/6] 日/月/年分层"
$PY scripts/build_literature_layers.py || { echo "分层失败"; exit 1; }

echo "[4/6] KOL 观点抓取"
# 只抓 active 且有 ORCID 的人；失败不阻断整条链（文献侧仍要出面板）
$PY scripts/fetch_statements.py || echo "[WARN] 言论抓取失败，沿用上一轮数据"

echo "[5/6] 建面板"
$PY scripts/build_dashboard.py || { echo "建面板失败"; exit 1; }

echo "[6/6] Notion 同步"
# 幂等 upsert + 去重兜底；失败不阻断（面板与 GitHub 仍应发布）
$PY scripts/notion_sync.py || echo "[WARN] Notion 同步失败，下轮重试"

echo "=== 完成 $(date '+%F %T') ==="
