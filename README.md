# Science KOL

科学界 KOL 观点追踪 + 主流科学文献每日扫描。

## 做什么

两条并行管道，一个面板：

1. **KOL 追踪** —— 按 8 个科学门类（医学健康 / 生命科学 / AI计算机 / 物理天文 /
   化学材料 / 神经认知 / 地球气候 / 数学基础理论）维护科学家名册，追踪其公开观点。
2. **文献扫描** —— 每日抓 17 个文献源（主流顶刊 + 预印本 + 开放获取），
   规则分流到门类，LLM 生成中文一句话摘要，按日 / 月 / 年三层展示。

## 快速开始

```bash
# 完整日链（抓取 → 分流 → 分层 → 建面板），约 80 秒
bash scripts/daily_chain.sh

# 单步
.venv/bin/python3 scripts/fetch_literature.py        # 抓文献
.venv/bin/python3 scripts/classify_literature.py     # 分流 + 中文摘要
.venv/bin/python3 scripts/build_literature_layers.py # 日/月/年分层
.venv/bin/python3 scripts/build_dashboard.py         # 建面板

# 名册相关
.venv/bin/python3 scripts/build_candidates.py 医学健康     # 拉候选
.venv/bin/python3 scripts/probe_public_voice.py 医学健康 24 # 实测公共表达度
.venv/bin/python3 scripts/score_and_admit.py 医学健康      # 四维打分入册
```

环境变量：`GENAI_PROXY`（LLM 代理，不设则跳过中文摘要）、`SK_LLM_TOPN`（每日 LLM 条数，默认 60）、
`SK_WINDOW_DAYS`（文献发表日窗口，默认 60 天）。

## 文献源

| 层级 | 源 | 取得方式 |
|---|---|---|
| 主流顶刊 | Nature, Science, Cell, NEJM, Lancet, PNAS, JAMA | RSS |
| 预印本 | arXiv（16 个分类）, bioRxiv, medRxiv | RSS / 官方 API |
| 预印本 | chemRxiv | Crossref（直连 403） |
| 开放获取 | PLOS, eLife, Frontiers | RSS |
| 开放获取 | MDPI | Crossref（直连 403） |
| 摘要回填 | OpenAlex | 按 DOI 批量 |

## 数据口径

- **按论文实际发表日分层**，不是抓取日。发表日取不到的标 `date_status=unverified`
  单列，不用抓取日顶替。
- 只收发表日在 60 天窗口内的条目，避免旧刊重新索引混入「每日更新」。
- **KOL 四维评分**：A 学术根基 30% / B 一手性 25% / C 公共表达 30% / D 方法透明 15%，
  星级取名册内百分位而非绝对切点。近 12 个月无可追溯公开发声者不入册。
- **绝不编造**：抓不到就标状态，不臆造内容 / 日期 / 出处。

## 目录

```
scripts/sources.py                  17 源抓取层（含三条 403/429 绕过路径）
scripts/fetch_literature.py         日抓取 → data/literature/YYYY-MM-DD.json
scripts/classify_literature.py      规则分流 8 门类 + LLM 中文摘要
scripts/build_literature_layers.py  日/月/年三层聚合
scripts/roster.py                   名册 SSOT + 四维评分定义
scripts/build_candidates.py         OpenAlex 候选池
scripts/probe_public_voice.py       C 维公共表达度实测（含同名闸）
scripts/score_and_admit.py          打分入册（3★ 门槛）
scripts/migrate_from_fc.py          从 Forecast-Checker 迁入
scripts/build_dashboard.py          单文件面板
scripts/daily_chain.sh              日链
scripts/publish.sh                  红线扫描 + 双端发布
```

## 已知待办

- 名册仅医学健康门类完成样板（11 人）+ 从 Forecast-Checker 迁入 10 人，其余 7 门类待建。
- OpenAlex 的机构字段存在错误值，在世状态该库不提供 —— 面板已逐条标注待核验。
- KOL 言论抓取（statements）尚未实现，当前名册只有档案没有观点流。
