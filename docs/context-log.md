# Science-KOL 上下文归档

> 每日由 `science-kol-context-distill`（cron 05:40 JST）追加。
> 只记真实发生的事与真实数字，不臆造。

---

## 2026-09-13（项目从零建成：文献管道 + 126 人名册 + 观点流 + 双端发布 + 全站中文化）

### 决策

1. **立项四条要求（Chao 原话）**：
   - 「把我们之前 Focus Checker 里面属于科学界的人，都移到这个 KOL checklist 里面」
   - 「对标 Focus Checker 做一套完整的功能：包括 Dashboard、Notion、两边的 GitHub 以及每天的 crawling」
   - 「针对不同科学领域（比如医学、AI、物理学、化学等主要科学门类）分别做 KOL tracking」
   - 「在面板上增加主要科学类文献的扫描……按日、月、年等维度分层展示」
   - 口径澄清：「Focus Checker」= **Forecast-Checker**（语音之误，按实名处理）。
2. **名册规模**：每门类 **10 人**方案；后改为「**自动展开 8 门类到 70-90 人，你事后删**」——
   即**不要我替他圈人**，先全量建出来由他删减。
3. **重心**：「**两者并重**」→ 名册建完立刻接言论抓取，不只做档案。
4. **FC 侧摘除**：**不动**（不可逆，等他点头）。Ramakrishnan 与 Tyson 两人「**都搬**，FC 侧保留」。
   - 附带口径：Ramakrishnan 的「鲸鱼鲨鱼能活几百年」需存 `interpretation_caveat`、
     其自陈中立理由存 `self_declared_neutrality`；Tyson 「**不可只摘万亿富翁金句**」。
5. **观点交叉模块**（Ramakrishnan × Faggin 从相反路径得出「意识上传不可行」同一结论）：**暂缓**。
6. **Notion**：「https://app.notion.com/p/Science-3da47eb5fd3c809abf43e4315417b007 **用这个吧，然后其他都可以**」
   —— 指定父页 + 一次性授权 GitHub 两端。
7. **公网发布**：问「**发布了公网html了么**」；得知 force push 抹不掉旧 commit 后，对
   「删仓重建 → public → 开 Pages」回复「**跑**」＝授权执行不可逆操作。
8. **新增要求（当日追加）**：「**K O L 言论也需要有日月年的一个 dashboard**」。
9. **语言铁律（当日追加）**：「**我们所有的四层展开结构都需要是中文的，不能是英文或其他文字的**」。

### 做了什么

**文献管道（17 源全通）**
- `scripts/sources.py` / `fetch_literature.py`：实跑 **962 条新论文、96% 带摘要、80 秒**。
- 三条实测绕过路径：chemRxiv 走 Crossref DOI 前缀 `10.26434`、MDPI 走 member `1968`、
  arXiv 走分类 RSS（export API 对本 VM 持续 429）。
- 8 门类规则分流，未分类率压到 **4.3%**（109 → 39 条，剩余基本是科研政策/八卦新闻，本就该排除）。
- 三层聚合 `literature_layers.json`：磁盘核实 `_meta` = **total 962 / undated 20 / days 28 / months 3 / years 1**。

**名册（8 门类 126 人）**
- 磁盘核实 `kol_registry.json`：**count 126 / active_count 122**。
- 门类分布：神经认知 18、物理天文 18、生命科学 17、医学健康 16、AI计算机 16、地球气候 16、
  化学材料 15、数学基础理论 10。
- 四维评分为科学界**重新设计**（A 学术根基 / B 一手性 / C 公共表达 / D 方法透明），
  未硬套 War-KOL 的「预测命中率」维度。最高分 Ramakrishnan **5★ 8.90**。
- 从 Forecast-Checker 迁入 10 位科学从业者（Radin / Mossbridge / Krippner / Dossey / Faggin /
  Puthoff / Targ / Schwartz / Brown / Jaynes），**FC 侧一条未删**；后追加 Ramakrishnan（生命科学 5★）
  与 Tyson（物理天文 4★），并快照 FC 侧 7 条预言。
- 留痕：候选落选 115、已故剔除 9、言论剔除 133（`candidates_rejected.json` / `deceased_removed.json` /
  `statements_rejected.json`）。

**观点流（ORCID 铁锚）**
- `fetch_statements.py`：初版 262 条 → 清洗后**磁盘核实 180 条**，`statement_layers._meta` =
  **total 180 / dated 180 / undated 0**（发表日覆盖 53% → **100%**），176 条有正文。
- 归属错误 **18 人 → 0 人**（逐人核对 slug）。

**Dashboard / 发布 / Notion**
- 单文件 HTML，无头 Chrome 实测：126 张 KOL 卡片、6 板块、scrollspy、三层展开、无横向溢出。
- 新增「观点时序」组：按日 14 桶 / 按月 12 桶 / 按年 11 年，每桶先给「谁在发声」排行（105 个标签）
  —— 刻意**不照搬文献层**（文献主角是论文，观点主角是人）。
- 公网：**https://curarpikt0000.github.io/Science-KOL/** ，实测 HTTP 200、791,690 bytes、
  md5 与本地一致（最终 `63a9288c`）。内网 monorepo 已同步（本地 commit，**未 push**）。
- Notion 5 表建成并回读校验：Science KOL List 126 / KOL Statements 262 / Literature Daily 28 /
  Monthly 3 / Yearly 1，幂等重跑无重复。

**全站中文化**
- 翻译 **827 条**（观点 180 + 文献 647），成功率 100%，约 3.2 秒/条。
- 线上实测：**文献标题 390/390、观点标题 260/260、展开正文 655/655 全中文**，
  英文原文降为可折叠副层（391 处）。术语按「铁死亡（Ferroptosis）」式括注原词。

**自动化**
- 日链最终 **8 步**：抓文献 → 分流+摘要 → 观点抓取 → 翻译 → 重建文献三层 → 重建观点三层 →
  建面板 → Notion 同步。
- cron 三个：`science-kol-daily` 06:45、`science-kol-selfheal` 每小时 :25、
  `science-kol-context-distill` 05:40。均 `enabled=scheduled`。

### 踩坑与教训

**数据源类**
1. **Crossref `created` 滞后约 2 天** → 按「昨天」过滤稳定返回 0 条。
2. **`from-index-date` 拉回的 MDPI 100% 是 2012-2025 旧论文重索引**，真新论文一条没有 →
   必须用 `from-pub-date`（切换后 MDPI 2162 / chemRxiv 212 条真新论文）。
3. **OAI-PMH 的 `from` 是元数据更新日，不是发表日** —— 拉回 835 条全是 2014-2016 年老论文。
   `dc:date` 多值时最后一个才是最新版本日期。
4. **arXiv 周末不发布**（lastBuildDate 全部相同、全分类 0 条）＝源健康，不是故障。
   为不等到周一，用 **Wayback 工作日快照**验证解析器：245/245 全字段命中。
5. **Nature 日更主体是新闻稿**（DOI 前缀 `d41586`，三家库都查不到摘要），研究论文才是 `s41586` →
   必须按 DOI 前缀区分 news/article。
6. 兜底关键词 `learning` 把教育学论文误判成神经认知 → 移除泛词。

**归属与身份（本项目最贵的教训，同一个错误犯了两次）**
7. **EuropePMC 姓名缩写匹配 41 条全军覆没** —— 对 6 位无 ORCID 者按 `AUTH:"Brown CD"` 抓，
   逐条核对**命中率 0%**（整形外科 Brown CD、眼科 Schwartz SG、真菌学 Schwartz S）。
   → 改为**硬门禁：无 ORCID 一律不抓**，不是「标低置信」糊弄过去；41 条已清除留痕。
8. **The Conversation 抓取器只校验姓氏 → 39 人里 18 人抓错人**
   （`Paul M. Thompson`→campbell-thompson、`Meng Chen`→justin-meyer、`Wang Jun`→yuxuan-wu）。
   ★ **我在新通道上重犯了第 7 条同一个错误**——门禁立在旧通道，换数据源又只验姓氏。
   → 改名+姓双命中强匹配，归属错误归零。
9. OpenAlex 数据脏：机构字段错（Kroemer 挂「Twitter」、Ferrucci 挂 Oxford 实为 NIH）、
   **不提供在世状态**（Trojanowski 2022 已故仍在库）。→ 全部 OpenAlex 机构标「未经人工核验」，
   另跑 `verify_alive.py` 剔除 9 位已故者。
10. **纯靠引用量排名选不出 KOL**：聚合端点被灌水账号污染（某「双语音标有声读物」5688 篇排第二），
    且 **高引用 ≠ 能追踪**（h-index 260+ 者近半数无可 track 的观点流）→ C 维（公共表达）
    实测探测才是入池门槛。
11. 探测器假阴性两种：Unicode 连字符 `‐`(U+2010) 导致 wiki 404；**瞬时网络抖动被 `fetch` 静默吞掉**
    → 加姓名归一化 + 搜索兜底 + 失败重试，可追踪数 12 → 19/24。

**工程与流程类**
12. ★ **我误诊了 cron 超时，被通知回执打脸**：先断言「首跑被 no_agent 120 秒硬上限截断」，
    实际记录是 **Duration 64.04s / Result=ok**。真因是**我手动跑的进程与 cron 进程抢写同一日志文件**
    `daily_2026-09-13.log`，我 cat 到了中间态。这正撞上既有铁律「平台侧故障的判据是拿同一输入重跑」，
    我没重跑就改了架构。**改动保留但理由更正**：64 秒是周日数据（arXiv 零产出），工作日多 16 个分类
    必然逼近上限；后台+PID 锁顺带根除并发写日志。
    → 新铁律：**先查 cron 运行记录的 duration/exit，再下超时结论**。
13. **分门类跑会整文件覆盖**：跑「生命科学」时用 56 条冲掉了此前医学的 55 条 → 改幂等 upsert 合并写入。
14. **Notion 多出 18 行重复**：第一次运行写入途中崩溃，第二次回读时那批行还没落库 → 判定「不存在」重写。
    Notion 无唯一约束兜不住。→ 去重**固化进同步脚本最后一步**，不靠我记得手动跑。
15. **红线扫描清单必须与 git add 清单同步**（War-KOL AGENTS.md 已记的坑，**我又踩了一次**）：
    新建的 `daily_chain.sh` 不在扫描清单，把本机代理地址 `…:8800` 带进了公网仓库。
    → 地址移到 gitignored `.env.local`(0600)，扫描新增 4 个模式（IP:端口 / localhost:端口 / 10.x / Bearer）并实测拦截。
16. **force push 抹不掉 GitHub 的 unreachable commit** —— 强推后旧 SHA 仍能通过 API 取到。
    唯一彻底办法是**删仓重建**（前提核实：本地 22 文件完整 / 内网有副本 / `.git` 已备份 / gh 有 delete_repo 权限）。
    执行后逐个查 API 确认 `238f01e8`、`3cbd640d`、`da63239a` 全部 Not Found。
17. 红线扫描命中 4 处 `uber` **全是 tuberculosis（结核病）** → 加词边界（同 `presto` 撞 `preston` 教训）。
18. **翻译写回源文件但三层是快照** —— 不重建三层，中文根本不出现在面板上；
    且 `build_literature_layers.py` 字段白名单**漏了 `title_zh`**（`summary_zh` 在），
    表面「译好 647 条」实际标题一个没生效。**两个 bug 都是 `check_zh_coverage.py` 门禁抓出来的，
    不是我自己发现的**——再次印证「标准写成硬门禁比写进文档可靠」，以及「子进程自报 exit 0 ≠ 结果正确」。
19. publish.sh 两个自制 bug：硬编码 `origin main`（内网 monorepo 当前分支不是 main，导致一次 push 失败）；
    `data/statements/*.json` 不在 add 清单导致 `git diff --cached --quiet` 判断错位。
20. 非 terminal 环境 commit 失败真因是 **Uber git hook 中间件缺 `SSH_AUTH_SOCK`**，不是脚本问题。
21. 我自己的操作失误：一次 `terminal` 调用 420 秒超时被杀，**连带杀掉其子进程树里的前台扩招任务**
    （名册跑到神经认知中断）→ 长任务必须 setsid 真后台。

### 待办

- [ ] **61 位无观点者是否清理**（名册 126 人，抓到观点约 65 人）—— 等 Chao 看面板后定。
      主因是无 ORCID 或近 18 个月无观点型发表，属真实情况不是抓漏。
- [ ] **FC 侧摘除科学家** —— 不可逆，Chao 明确「先不动」。
- [ ] **内网 monorepo push** —— 本地 commit 已生成，按规矩等 Chao 确认。
- [ ] **观点交叉模块**（跨门类同结论对照）—— Chao 说暂缓。
- [ ] **Notion KOL Statements 表仍是清洗前的 262 行**，本地已降至 180 —— 需确认次日 cron 同步会否自动对齐。
- [ ] **AGENTS.md 未写** —— protected 文件需审批，按协议攒批等 Chao 在场时一次性提交。
- [ ] git 第三态：`data/candidates_raw.json`、`candidates_rejected.json`、`deceased_removed.json`、
      `statements_rejected.json`、`scripts/{diag_notion_dups,notion_dedupe,go_public,publish}.*` 仍未纳管。

---

## 2026-09-14（归档器自身修复）

### 做了什么
- 本项目此前**不在 `~/.hermes/project_topic_map.json`**，`science-kol-context-distill` 首次运行
  即 `NO_TOPIC_RESOLVED (UNMAPPED_PROJECT)`，零产出。已补录
  `"-1003988268482:64611": "Science-KOL"`。
- 三条同向证据：① thread 64611 消息内路径频次 `Projects/Science-KOL`=354，次位 War-KOL=30；
  ② 该 topic 唯一 session `20260913_144721_627b052b` 标题 *Build Science KOL tracking system*（931 条消息）；
  ③ 三个 `science-kol-*` cron 的 `origin.thread_id` 全为 64611，其中 context-distill 的
  workdir=`/home/user/Projects/Science-KOL`。
- 回退备份：`~/.hermes/project_topic_map.json.bak-20260914-054121-sciencekol`。
- 补录后重跑采集器成功：`via=cwd sessions=1 window=26.0h`，故 2026-09-13 一节为补写。

### 踩坑与教训
- **新项目建完必须同步补 topic map**，否则 context-distill 会静默零产出（已是第 5 个同类案例：
  Book-club / Task-1-User-Fee / Data-Science / Profile-builder / Science-KOL）。
  判据不能只看路径频次（覆盖悬崖会漏），要三证同向：频次 + session 标题 + cron origin.thread_id。
