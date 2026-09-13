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

echo "[1/8] 抓取文献"
$PY scripts/fetch_literature.py || { echo "抓取失败"; exit 1; }

echo "[2/8] 分流 + 中文摘要"
$PY scripts/classify_literature.py || { echo "分流失败"; exit 1; }

echo "[3/8] KOL 观点抓取"
# 只抓 active 且有 ORCID 的人；失败不阻断整条链（文献侧仍要出面板）
$PY scripts/fetch_statements.py || echo "[WARN] 言论抓取失败，沿用上一轮数据"

echo "[4/8] 全站中文化"
# ★ 顺序铁律：翻译写回【源文件】，三层是快照 —— 必须先翻译再重建三层，
#   否则中文不会出现在面板上（2026-09-13 实测踩过）。
$PY scripts/translate_to_zh.py all || echo "[WARN] 翻译失败，沿用上一轮中文"

echo "[5/8] 文献三层重建（吃进新译文）"
$PY scripts/build_literature_layers.py || { echo "文献分层失败"; exit 1; }

echo "[6/8] 观点三层聚合"
$PY scripts/build_statement_layers.py || { echo "观点分层失败"; exit 1; }

echo "[7/8] 建面板"
$PY scripts/build_dashboard.py || { echo "建面板失败"; exit 1; }
# 中文覆盖率门禁：不达标只警告不中断（数据仍可用），但日志留痕便于追查
$PY scripts/check_zh_coverage.py || echo "[WARN] 存在未中文化条目，见上方明细"

echo "[8/8] Notion 同步"
# 幂等 upsert + 去重兜底；失败不阻断（面板与 GitHub 仍应发布）
$PY scripts/notion_sync.py || echo "[WARN] Notion 同步失败，下轮重试"

echo "=== 完成 $(date '+%F %T') ==="
