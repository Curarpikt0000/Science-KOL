#!/bin/bash
# Science-KOL 发布：重建 → IP 红线扫描 → 双端 push。
# 幂等：无变更则静默跳过。供每日 cron 末尾调用。
# （公网安全版：由交接包导出，已移除内网同步与内网镜像段。）
#
# ⚠️ 红线扫描清单必须与 git add 清单保持同步
#    （Forecast-Checker 2026-08-24 踩过：只加 git add 忘了加扫描 = 新文件绕过安全门）
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
# ★ 从脚本自身位置推导，不用 $(pwd)：cron / 自愈 watchdog 可能从任意 cwd 调用
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

# ★ 与翻译/分层进程互斥（Chao 2026-09-21 实测）：
#   publish.sh 开头会重建三层，若此时 translate_to_zh.py 正在写同一批
#   data/literature/*.json，两者并发写同一文件 → 翻译进程被打断（实测停在 60/201）。
#   日链里是顺序执行不会撞，但手动/自愈并行调用时会。等而不是抢。
exec 8>"$ROOT/logs/.pipeline.lock" 2>/dev/null || true
flock -w 1800 8 2>/dev/null || echo "[WARN] 等待管道锁超时，继续执行" >&2
PY="python3"
[ -x "$ROOT/.venv/bin/python3" ] && PY="$ROOT/.venv/bin/python3"

# 1. 重建 dashboard（数据层由 cron 的抓取步骤先跑完）
$PY scripts/build_literature_layers.py || { echo "文献分层失败"; exit 1; }
$PY scripts/build_dashboard.py || { echo "build 失败"; exit 1; }
cp dashboard/index.html index.html   # Pages 入口是根目录 index.html

# 2. IP 红线扫描（个人端安全）——清单与下面 git add 同步
# ★ 扫描要排除【本脚本自身】和【正常英文内容】，否则全是误报：
#   - publish.sh 里写着模式串本身会自我命中
#   - 论文标题里的普通英文词会撞上红线词的子串 → 用 \b 词边界而非删词
#     （War-KOL 教训：红线词误杀加 \b，不是删词）
#   - LLM 代理地址是本机回环，属实现细节不是内网标识，但仍不进公网 → 单列白名单外
SCAN_LIST="README.md scripts/sources.py scripts/fetch_literature.py \
scripts/classify_literature.py scripts/build_literature_layers.py \
scripts/build_dashboard.py scripts/roster.py scripts/build_candidates.py \
scripts/probe_public_voice.py scripts/score_and_admit.py scripts/migrate_from_fc.py \
scripts/migrate_batch2.py scripts/fetch_statements.py scripts/verify_alive.py \
scripts/daily_chain.sh scripts/expand_all_fields.sh scripts/finish_expand.sh \
scripts/build_statement_layers.py scripts/translate_to_zh.py scripts/check_zh_coverage.py \
scripts/build_four_layers.py scripts/refetch_l3.py scripts/dash_filter.py scripts/prune_silent.py \
scripts/sources_extra.py scripts/sources_podcast.py scripts/fetch_podcasts.py \
dashboard/index.html index.html \
data/kol_registry.json data/layers/literature_layers.json \
data/layers/statement_layers.json"

# ★ notion_sync.py / notion_probe.py 【故意不进公网】：内含 Notion 页面 id 与
#   token 读取路径，属凭证相关实现细节。

# ★ 2026-09-13 补：daily_chain.sh 曾硬编码本机代理地址溢出到公网（当时该文件不在扫描清单）。
#   新增：回环/内网 IP+端口、Bearer 字面量。
# ★ uber 系列词必须加 \b 词边界：医学论文摘要里的 tuberculosis（结核病）
#   含红线词子串，2026-09-13 实测误报 4 处（同样用 \b 词边界解决）。
# 内网专有词由接手方通过环境变量 REDLINE_EXTRA_REGEX 注入（例如 "内网域名|用户名|仓库名"），不写进公网文件。
EXTRA="${REDLINE_EXTRA_REGEX:-__never_matches__}"
HITS=$(grep -rniE "${EXTRA}|\bpresto\b|ntn_[A-Za-z0-9]{15}|secret_[A-Za-z0-9]{15}|127\.0\.0\.1:[0-9]+|localhost:[0-9]+|10\.[0-9]+\.[0-9]+\.[0-9]+|Bearer [A-Za-z0-9_-]{4,}" \
   $SCAN_LIST 2>/dev/null | grep -v notion_ids)
if [ -n "$HITS" ]; then
  echo "RED-LINE HIT — 中止个人端 push"
  echo "$HITS" | head -10
  exit 2
fi

# 3. 个人端 push（公网）
if git remote get-url origin >/dev/null 2>&1; then
  git add $SCAN_LIST data/literature/*.json data/statements/*.json 2>/dev/null
  if ! git diff --cached --quiet; then
    git -c commit.gpgsign=false commit -q -m "Daily update: literature scan and dashboard $(date +%F)" || {
      echo "个人端 commit 失败"; exit 3; }
    git push -q origin main 2>&1 | grep -vE "duplicate proto" || true
    # 读回 remote 校验，避免假阳性
    LOCAL=$(git rev-parse HEAD)
    REMOTE=$(git ls-remote origin -h refs/heads/main 2>/dev/null | cut -f1)
    if [ "$LOCAL" = "$REMOTE" ]; then echo "个人端 push 已校验 ${LOCAL:0:8}"
    else echo "警告：个人端 remote 未对齐 local=${LOCAL:0:8} remote=${REMOTE:0:8}"; fi
  else
    echo "个人端无变更"
  fi
else
  echo "个人端 remote 未配置，跳过"
fi

# （内网 monorepo 同步段已在公网版移除；有内网仓库的接手方自行补回）

# ─────────────────────────────────────────────────────────────
# 三通道冗余发布（Chao 2026-09-21 批准）
#
# ★ 事故教训：本项目原本只有 GitHub Pages 一条公网通道。2026-09-21 GitHub 出现
#   【账号级】Pages 故障（名下全部站点 + 根域一起 404，构建请求返回成功却从不执行），
#   Science-KOL 因此彻底无入口，而同账号下靠多通道发布的姐妹项目不受影响。
#   ⇒ 从此本项目也走多通道：GitHub Pages（上方已推）+ Cloudflare Pages（+ 可选的内网镜像）。
#
# 两条备用通道都【不阻塞】主发布：失败只告警，不改变 publish.sh 的退出码。
# ─────────────────────────────────────────────────────────────

# ② Cloudflare Pages —— 公网主力备份，免登录、不依赖 GitHub
#    通用脚本 10 个项目共用；成功判据是它自己做的「匿名取回 + sha256 逐字节比对」，
#    不是 HTTP 200（*.pages.dev 是全球共享命名空间，200 可能是别人的站）。
CF="$HOME/.hermes/scripts/publish_cf_pages.sh"
if [ -x "$CF" ]; then
  # ★ 必须传绝对路径：publish.sh 前面 cd 进过内网 monorepo，cwd 已不是项目根
  #   （实测 2026-09-21：相对路径 → cf 报 SOURCE MISSING index.html）
  if bash "$CF" science-kol "$ROOT/index.html"; then
    echo "Cloudflare: https://science-kol.pages.dev/"
  else
    echo "[WARN] Cloudflare 发布失败 rc=$? — 不阻塞主发布，下次重试" >&2
  fi
else
  echo "[WARN] 未找到 $CF，跳过 Cloudflare" >&2
fi
