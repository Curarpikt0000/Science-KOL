# Science-KOL 交接文档（HANDOVER）

> 写给接手的 agent：`git pull` 之后读完本文件即可接手每天的自动化，不需要原 agent 在场。
> 本文所有数字、路径、行为均为 **2026-10-01** 在原机器上实测所得，不是设计稿。
> 与旧 `README.md` 冲突时**以本文为准**（README 的「已知待办」两条已过时，见 §9）。

> **本文是公网版**：已去掉内网域名、内网仓库名、内网镜像与 Notion 同步的实现细节。内网版放在公司内网仓库里，两版结构相同。

---

## 1. 这个项目是什么

科学界 KOL（意见领袖）观点追踪 + 主流科学文献每日扫描，合并为一个单文件网页面板，每天自动更新。

- **名册**：126 人入过库，**53 人在册**（73 人已归档，归档不物理删除），分 8 个门类：
  医学健康 9 / 生命科学 12 / AI计算机 4 / 物理天文 1 / 化学材料 9 / 神经认知 9 / 地球气候 7 / 数学基础理论 2。
  星级 1★8 / 2★11 / 3★14 / 4★13 / 5★7。
- **观点流**（statements）：53 人全部有观点，最新一天 240 条，来源 5 个渠道：
  EuropePMC 140 / The Conversation 42 / 媒体采访 36 / 播客 18 / 署名文章 4。
- **文献流**：每天抓 17 个源（顶刊 RSS + arXiv/bioRxiv/medRxiv/chemRxiv + 开放获取），规则分流到 8 门类，
  LLM 出中文一句话摘要，展示层累计 **2733 条**（其中 136 条尚缺中文标题，见 §9 P4）。
- **面板**：`index.html`（约 8MB 单文件）。结构是「filter 按钮 + 卡片四层展开」，目标是**全中文**（观点 240/240 已全中文；文献有缺口）。

**公网入口**：<https://science-kol.pages.dev/>（Cloudflare Pages，主入口）。
GitHub Pages 入口 `curarpikt0000.github.io/Science-KOL/` 自 2026-09-21 起 **账号级 404**（名下所有 Pages 站点同时 404，
构建请求返回成功但从不执行），截至 2026-10-01 未恢复。**这不是本项目的 bug，别花时间修它**——Cloudflare 已兜底。

---

## 2. 一图看懂：日链 10 步

每天 06:45 由 cron 启动 `scripts/daily_chain.sh`（后台跑，见 §4），顺序**不可调换**：

| 步 | 脚本 | 做什么 | 失败时 |
|---|---|---|---|
| 1 | `fetch_literature.py` | 抓 17 个文献源 → `data/literature/YYYY-MM-DD.json` | **中止整条链** |
| 2 | `classify_literature.py` | 规则分流 8 门类 + LLM 中文摘要 | **中止整条链** |
| 3 | `fetch_statements.py` | EuropePMC + The Conversation + **新闻媒体采访** | 只警告，沿用上一轮 |
| 3b | `fetch_podcasts.py` | **播客**（本机转写，每天限 4 集） | 只警告，跳过 |
| 4 | `translate_to_zh.py` | 全站中文化，单轮 400 条，最多循环 6 轮 | 只警告 |
| 5 | `build_four_layers.py` + `refetch_l3.py` | 生成四层内容（一句话/总结/原文翻译） | 只警告 |
| 6 | `build_literature_layers.py` | 文献日/月/年三层聚合 | **中止整条链** |
| 7 | `build_statement_layers.py` | 观点三层聚合 | **中止整条链** |
| 8 | `build_dashboard.py` | 建面板 + `check_zh_coverage.py` 中文门禁 | 建面板失败**中止**；门禁只警告 |
| 9 | `notion_sync.py` | 同步到 Notion 5 个库（**见 §6，公网版不含此脚本**） | 只警告 |
| 10 | `publish.sh` | 红线扫描 → 多通道发布 | 只警告，退出码不变 |

**顺序铁律（都是踩过的）**：
- **先翻译（4）再建三层（6、7）**。翻译写回的是源文件，三层是快照；反过来中文不会出现在面板上。
- **新闻/播客（3、3b）必须在翻译（4）之前**，否则当天新言论没有中文标题。
- 步 4 的翻译循环是**必需**的：日增量常超过 400 条上限，曾积压到 803 条无中文。

**典型耗时**：06:45 启动，近 6 天完成时刻依次为 09-26 08:17 → 09-27 08:02 → 09-28 07:55 → **09-29 09:12 → 09-30 09:03 → 10-01 09:05**。
**09-29 起明显变慢**（比之前晚 1 小时以上），正是新闻源和播客接入的那天。耗时主要被**文献翻译**（每天待译 300-400 条，要 3 轮）和**播客转写**（4 集约 12 分钟）拉长。

---

## 3. 数据口径（改任何抓取/展示代码前先读）

这些是用户（Chao）定的硬规矩，接手方**不得放宽**：

1. **按实际发表日分档，不按抓取日**。发表日取不到就留空并标 `date_status=unverified`，**绝不用抓取日顶替**。
2. **名册只增不减**。清理无观点者用 `active=false` 归档，不物理删除；渲染层和 Notion 同步都必须过滤 `active`。
3. **入库必须抓到正文 + LLM 抽五要素，无五要素不入库**。源失败只警告跳过，**绝不伪造条目**。
4. **同名闸两道**：①正文含「名+姓」全名；②LLM 判定是同一人（学科/机构对得上）。有 ORCID 的人用 ORCID 锚定。
5. **论断必须锚定具名数据 + 可追溯出处**。detail 只把 summary 换句话说 = 不合格。
6. **看板风格**：人类网站风，禁 emoji 标题，标题 ≤ 8 字，每个 section 一行说明，每图单独 title，忌自夸词，四层**全中文**。
7. **言论太少先查上游，别降门槛**。
8. **超心理学/遥视/术数类人物归 Forecast-Checker 项目**，不进本项目。
9. **cron prompt 里绝不写死人数**（名册会变）。
10. 所有时间按 **东京时间（Asia/Tokyo）** 表述。

### 观点来源与四道闸（新闻/播客是 2026-09-25 新增）

| 渠道 | 怎么取 | 闸门 |
|---|---|---|
| EuropePMC | 按 ORCID 查论文摘要，近 18 个月 | 摘要 ≥120 字 + ORCID 作者匹配 |
| The Conversation | 按作者名抓科普专栏 | 作者署名匹配 |
| 媒体采访/署名文章 | Google News RSS 按全名搜近 60 天 → 解出原文直链 → 抓正文 | 闸1 正文含全名 → 闸2 LLM 同人核验 → 闸3 有本人原话+明确论点 → **闸4 论点方向独立复核** |
| 播客 | Apple Podcasts 搜剧集 → 下 mp3 → **本机** faster-whisper 转写 → 分段抽取 | 闸0 元数据排除同名他人 → 闸2 转写含姓 → 闸3 嘉宾是本人 → 闸4a 引文逐字可在转写里找到 → 闸4b 说话人+论点+实质性复核 |

**为什么要第 4 道「论点方向复核」**（这是实测踩出来的，别删）：
- Venki Ramakrishnan 在 nautil.us 文章里先用设问句开场（「为什么我们不能一直修复身体、永远活下去？」），
  然后论证这做不到。抽取模型把设问当论点，写成「理论上可以永生」——**方向完全写反**。只改提示词无效，必须加独立复核。
- 复核时必须把**所有提到他的段落**交给模型，不能只给前几个窗口：真正的结论段落在后面，截断了模型就只看到设问。
- 本人署名文章（正文里不会出现自己的名字）要先识别作者署名，再把全文交给模型，否则被「无本人原话」误拒。

**两个已验证无效的来源，别再试**：
- **YouTube**：本机 IP 被判机器人，20 个视频 19 个「Sign in to confirm you're not a bot」，换 cookies 也一样。已改用播客 RSS 公开 mp3。
- **Crossref 按 ORCID 查期刊评论栏目**：53 人 18 个月只剩 5 条、有正文 2 条，不值得接（代码在 `sources_extra.py`，未接入日链）。

---

## 4. 定时任务（4 个）

完整定义见 `ops/cron-jobs.json`（含真实 prompt）。路径已替换为占位符 `<PROJECT_ROOT>`、`<HERMES_SCRIPTS>`。

| 名称 | 时刻（JST） | 类型 | 脚本 | 作用 |
|---|---|---|---|---|
| `science-kol-daily` | 每天 06:45 | no_agent | `science_kol_daily.sh` | **只启动**后台日链，立即返回 |
| `science-kol-selfheal` | 每小时 :25 | no_agent | `science_kol_selfheal.sh` | 检查产物与公网，异常自愈一次，正常静默 |
| `science-kol-digest` | 每天 09:00 | no_agent | `science_kol_digest.py` | 把近 7 天重要言论 + 文献要闻发到对话 |
| `science-kol-context-distill` | 每天 05:40 | **agent** | `collect_topic_conversation.py` | 把当天对话压缩进 `docs/context-log.md` |

### 必须知道的 4 件事

**① daily 必须是「后台启动 + 立即返回」，不能同步等**。Hermes 的 no_agent cron 有 120 秒硬上限，日链要 1-2 小时。
所以 `science_kol_daily.sh` 用 `nohup` 起后台任务，结果由**下一次 tick** 汇报上一轮。接手方若「简化」成同步调用，第一天就会被杀在第 1 步。

**② selfheal 的判据有三条，缺一不可**（每条都对应一次事故）：
- 今日文献文件存在 + 面板 ≤26 小时 → 本地产物健康
- **公网两个入口都探测**，**两条都挂才报警**（单条挂由另一条兜住，不吵醒人）
- 按故障类型选动作：公网挂 → 只重发布（`publish.sh`）；本地产物缺 → 重跑整条日链。**别在公网挂时重抓文献**，浪费 40 分钟和 LLM 配额。
- 教训：2026-09-21 GitHub Pages 挂了 7 天，selfheal 每小时跑却从不报警，因为它只看本地产物。**健康判据必须包含用户真正打开的那个地址**。
- 教训：别用 `grep -c` 数单行拼接串（按行计数永远 ≤1，警报器永不响）。用计数器变量。

**③ digest 的时刻问题（已知，未修）**：09:00 触发，但近 3 天日链实际完成在 09:03-09:12，
所以**近 3 天的日报全是「今日日链还没跑完」**。脚本会如实报状态、不拿旧数据顶替，但这等于没有日报。
- 建议修法（二选一）：把 digest 改到 **10:00**；或让日链末尾直接触发 digest。
- 根因是日链变慢（文献翻译积压 + 播客转写）。**这是接手后第一件要处理的事。**

**④ 连锁故障案例（务必读，selfheal 的存在意义）**：2026-09-24 日链第 2 步崩溃
（`classify_literature.py`：LLM 返回合法 JSON 但元素是 int 不是 dict，`rec.get()` 抛 AttributeError，原代码只捕 `JSONDecodeError`）
→ 日链 exit 1 → 面板停更 → selfheal 每小时判定「面板超 26h」→ 每小时重跑整条日链 → 每次崩在同一处 → cron 超时报警。
**修了两层**：非 dict 元素跳过；**LLM 摘要只是锦上添花，异常只警告不掀翻整条链**（规则分流在崩溃前已完成）。

---

## 5. 模型与成本

只有 `context-distill` 一个 cron 调模型（`claude-sonnet-5-5`）。其余三个 cron 是纯脚本，**不花 token**。

日链内部的 LLM 调用（经本机代理 `GENAI_PROXY`）：

| 位置 | 模型 | 用途 |
|---|---|---|
| `classify_literature.py` | `claude-haiku-4-5`（环境变量 `SK_MODEL` 可覆盖） | 文献一句话摘要 + 门类，每天约 60 条 |
| `translate_to_zh.py` | `gpt-4o-mini` | 翻译，每天 300-400 条 |
| `build_four_layers.py` | `gpt-4o-mini` | 四层内容生成，每天约 200 条 |
| `sources_extra.py`（新闻抽取+复核） | `gpt-4o-mini`（`SK_LLM_MODEL` 可覆盖） | 新闻言论抽取 + 论点方向复核 |
| `sources_podcast.py`（播客抽取+复核） | 同上 | 播客观点抽取 + 说话人/论点复核 |

**2026-09-28 的改动**：`classify_literature.py` 原默认是 `claude-opus-4-8`（项目里唯一最贵的一档），改成 haiku。
同一批 16 篇真实文献对比，haiku / sonnet-5-5 / gpt-4o-mini 摘要都 16/16 返回，质量持平。**不要把翻译和四层也换成 haiku**：gpt-4o-mini 已经更便宜。

**未决**：新闻/播客的「论点方向复核」要不要升到 sonnet-5-5。理由：这步错了是把反方向观点写进别人名下，代价大于摘要；
目前 gpt-4o-mini 只在 Venki 一个陷阱题上验证过。用户尚未拍板。

**换模型的坑**：`gpt-5-mini`、`gemini-3.5-flash` 在现有代码里摘要返回 0/16——它们先「思考」占掉 token，`max_tokens` 太小。
不是模型不行，是代码不适配，要用得改 `max_tokens`。

**LLM 调用纪律**：**串行 + 每次间隔 1.5 秒**。并发会撞上游 429；客户端报 `RemoteDisconnected` 多半是上游 429 被代理 log 掩盖，退避重试。

---

## 6. 两个仓库、三个发布通道

### 仓库（用户要求两边都放本文档）

| | 公网仓库 | 内网仓库 |
|---|---|---|
| 位置 | 个人 GitHub `Curarpikt0000/Science-KOL`，分支 `main` | 公司内网 monorepo 的 `Science-KOL/` 子目录，**rsync 整目录同步**，不是独立 git 仓库 |
| 放什么 | 脚本、数据、面板、README | 同上，**外加**公网不能放的东西（见下） |
| 不放什么 | Notion 脚本、内网镜像脚本、`.env.local`、`logs/`、`scratch/`、`data/raw/` | `.venv`、`.git`、`scratch`、`__pycache__`、`data/notion_ids.json`、`.env` |

**公网仓库的红线**（都违反过，有代价）：
- 绝不能出现：内网域名、内网仓库名、公司用户名、内网 git 地址、Notion 页面 id、任何 token。
- 红线扫描正则在 `publish.sh`。**扫描清单必须与 `git add` 清单同步**——只加 add 忘了加扫描 = 新文件绕过安全门。
- **含敏感信息的 commit，force push 永远不够**（旧 commit 仍可通过 SHA 访问）。必须**删仓重建**。
  2026-09-21 在 War-KOL（姐妹项目）实际执行过一次：第一次重建因 `git add -A` 带上了 `logs/`，预演扫的是 `git ls-files` 而实际推的是 `git add -A`，**清单不一致**，被迫删了第二次。
  教训：**红线扫描的对象必须是实际待推清单**。

**公网版 vs 内网版的区别**：本文档同时放进两个仓库，内容略有不同——公网版去掉了内网域名、内网仓库名、
内网镜像的完整做法，只保留「有这么一个内网通道」的事实；内网版保留全部机制。两版的 `ops/` 与脚本也按同样规则处理。

### 发布通道（`publish.sh` 末尾，2026-09-21 起三通道冗余）

1. **GitHub**（+ 内网 monorepo rsync 推送）→ GitHub Pages。**目前 404（账号级），见 §1。**
2. **Cloudflare Pages**（`science-kol.pages.dev`）→ **当前主入口**。通用脚本 `publish_cf_pages.sh`（10 个项目共用，在 `ops/repo-scripts/`）。
   **成功判据是它自己做的「匿名取回 + sha256 逐字节比对」，不是 HTTP 200**：`*.pages.dev` 是全球共享命名空间，200 可能是别人的站。
3. **内网镜像** → 仅公司内网可见，实现细节在内网版文档里，**不进公网仓库**。公网版 `publish.sh` 已去掉这一段。

**后两条备用通道失败只告警，不改变 `publish.sh` 的退出码。**

**教训：日链曾没有发布步骤**。2026-09-21 发现数据天天更新，公网却停在 09-14，整整 7 天，靠用户问「今天 cron 跑了么」才发现。
**发布必须是日链的一环，不能靠人记得手动跑**。

---

## 7. 环境准备（接手方第一步）

### 密钥（只列变量名，**绝不写值，绝不进 git**）

| 变量 | 放哪 | 用途 |
|---|---|---|
| `GENAI_PROXY` | 项目根 `.env.local`（`chmod 600`，已 gitignore） | LLM 代理地址；不设则跳过 LLM 摘要（规则分流不受影响）。**手动跑脚本前必须先 `source .env.local`**——日链会自动加载，手动跑不会 |
| `NOTION_API_KEY` / `NOTION_TOKEN` | `~/.hermes/.env` | Notion 同步（内网版才需要） |
| `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` | `~/.hermes/.env` | Cloudflare Pages 发布 |

> ⚠️ **跨项目耦合（已知坑）**：`notion_sync.py` 当前硬编码从**另一个项目 War-KOL 的 `.env`** 读 Notion token
> （一个姐妹项目目录下的 `.env`，绝对路径写死在脚本里）。接手方机器上没有这个路径就会失败。要么复制该文件，要么改 `notion_sync.py` 读自己的 `.env`。

### Python 环境

`.venv/` 里只有 8 个包：`requests feedparser feedparser-sgmllib urllib3 certifi charset-normalizer idna setuptools`。
没有 `requirements.txt`——接手方用 `pip install requests feedparser` 即可。

### 系统依赖
`ffmpeg`、`flock`、`rsync`、`curl`、`wrangler`（Cloudflare CLI）。

### 播客转写的额外依赖（易漏）
- `faster-whisper`：**不在本项目 `.venv` 里**，复用了另一个项目（`AI-Blog-Generator`）的环境，路径写在 `sources_podcast.py` 顶部，
  可用环境变量 `SK_WHISPER_PY`、`SK_WHISPER_CACHE` 覆盖。接手方要自己装一个，或改这两个变量。
- 模型 `small`（约 464MB，首次运行自动下载）。CPU `int8` 模式，约 3.6 秒/分钟音频（48 分钟节目约 3 分钟）。
- 音频下载后立即删除（单集 40-100MB），转写结果缓存在 `scratch/podcast/`，重跑不重复烧 CPU。

---

## 8. 接手步骤（按顺序执行）

```bash
# 1. 拉代码
git clone <本仓库地址> ~/Projects/Science-KOL && cd ~/Projects/Science-KOL

# 2. 建环境
python3 -m venv .venv && .venv/bin/pip install requests feedparser
printf 'export GENAI_PROXY=<你的代理地址>\n' > .env.local && chmod 600 .env.local

# 3. 数据：名册/观点/文献已在仓库里（data/ 被追踪，约 115MB）。
#    名册 SSOT = data/kol_registry.json（顶层 _ssot 字段也写了）。

# 4. 替换交接包里的占位符
#    ops/hermes-scripts/*  和 ops/cron-jobs.json 里的 <PROJECT_ROOT> <HERMES_SCRIPTS>
sed -i "s#<PROJECT_ROOT>#$HOME/Projects/Science-KOL#g; s#<HERMES_SCRIPTS>#$HOME/.hermes/scripts#g" \
    ops/hermes-scripts/* ops/cron-jobs.json
cp ops/hermes-scripts/* ~/.hermes/scripts/ && chmod +x ~/.hermes/scripts/science_kol_*.sh
cp ops/repo-scripts/publish.sh scripts/publish.sh       # 注意：见 §10 第 3 条
cp ops/repo-scripts/publish_cf_pages.sh ~/.hermes/scripts/ && chmod +x ~/.hermes/scripts/publish_cf_pages.sh

# 5. 先冒烟，不发布：单步跑 3 步确认通
set -a; . ./.env.local; set +a
.venv/bin/python3 scripts/classify_literature.py      # 期望：LLM 摘要成功，无 Traceback
.venv/bin/python3 scripts/check_zh_coverage.py        # 期望：「全部展开层均为中文」
```

然后**按 `ops/cron-jobs.json` 建 4 个 cron**（`hermes cron create ...`）：
- `daily` / `selfheal` / `digest` 用 `--no-agent --script <名>`。
- `deliver` 字段原值是 `origin`（=原 Telegram 话题），**接手方必须换成自己的投递目标**，否则日报发给了原 agent 的话题。
- `context-distill` 是 agent 类型，要设 `workdir` 为项目根（带 workdir 的 job 独占目录锁，别的 job 在同目录等满 660 秒就 TimeoutError——排班别重叠）。

### 验证（push exit 0 不是证据）
1. 手动跑一次 `bash scripts/daily_chain.sh > logs/daily_$(date +%F).log 2>&1`，看 `=== 完成` 行和零 Traceback。
2. 打开 Cloudflare 入口，`sha256sum index.html` 与线上比对。
3. 等次日 09:00 看日报是否发出（见 §4③，可能报「未就绪」）。

### 原 agent 何时停手
**不要两边同时跑**：重复抓取 + 双倍烧 LLM 额度 + 抢发布。建议接手方验证通过（至少一次完整日链 + 一次日报）后，
原方逐个**暂停（不删）**4 个 cron；接手失败时恢复即回滚。

---

## 9. 已知问题与未决事项（接手后按优先级处理）

### P1：digest 日报时刻（§4③）
近 3 天日报全是「未就绪」。改到 10:00，或日链末尾触发。

### P2：名册质量
- **机构字段 52/53 人未经核验**（`affiliation_verified=False`）。已知错的：Rob Knight 挂在 Surrey Satellite Technology、
  另一人挂在 Twitter、Jure Leskovec 挂在 Palo Alto University。机构错会诱发同名判定的误拒（播客闸0、新闻闸2 都用它）。
  数据源 OpenAlex 的机构字段本身有错，在世状态该库不提供。
- **在世状态 18/53 人为 `None`（未核实）**，35 人 `True`。
- **门类不均**：物理天文只有 **1 人**，数学基础理论 2 人，AI计算机 4 人，远低于用户定的「每类 8-12 人」。
- **FC 侧 10 人摘除未执行**：这 10 人是从 Forecast-Checker 迁入的，Forecast-Checker 那边还保留着，**等用户发话**才摘除。别擅自动。

### P3：产量
KOL 言论实际很少。新闻+播客接入前，53 人合计每月只有 3-10 条；接入后近 7 天仍只有约 10 条
（播客 6 / 媒体采访 2 / 署名文章 1 / EuropePMC 1）。**产量是数据源决定的，不是代码问题，别为了凑数降闸门。**
- 播客积压 **7 集待处理**（每天 4 集，约 2 天消化完；之后只有新上架的剧集）。
- 拒收留痕累计 1379 条在 `data/statements_rejected.json`，top 原因：正文不足 120 字 672 / 非同一人 131 / 原文 403 128。抽查闸门是否过严看这个文件。

### P4：文献中文化缺口
日链步 8 的门禁常报 `[WARN] 存在未中文化条目`（10-01 实测：展示层 2733 条文献里缺 136 条中文标题、133 条中文摘要；观点 240/240 全有）。
原因：门禁在步 8 检查，但翻译在步 4，且日增量超出单轮 400 上限。数据仍可用，次日会补齐。要根治需调大上限或加循环轮数。

### P5：其他
- `README.md` 的「已知待办」两条**已过时**（说名册只有医学健康样板、言论抓取未实现）——实际 53 人 8 门类、言论 5 渠道。以本文为准。
- `.gitignore` 目前**未被 git 追踪**（untracked）。
- `scripts/` 下有几个一次性/试验脚本未追踪：`compare_models.py`（模型对比）、`sample_extra.py` / `trial_news.py`（扩源试跑）、
  `diag_notion_dups.py` / `notion_dedupe.py`（Notion 去重诊断）、`go_public.sh`。留作参考，不是日链的一部分。
- `scripts/publish.sh` **也未被 git 追踪**（公网仓库里原本没有它）——本交接包把公网安全版放进了 `ops/repo-scripts/`。

---

## 10. 铁律清单（每条都有代价）

1. **任何「查不到 X」的结论，先拿必然存在的对照组走同一条查询**。曾因解析器把 503 错误页读成「查无此物」差点下错结论。
2. **长任务看进程死活用 pid 存活 + `/proc/<pid>/wchan`，不看日志时间戳**。日志停更不等于进程死了（可能在等锁）。曾两次因此误杀。
3. **`publish.sh` 与翻译进程用同一把管道锁**（`logs/.pipeline.lock`，flock）。`publish.sh` 开头会重建三层，会与正在写 `data/literature/*.json` 的翻译进程并发写同一文件，曾把翻译打断在 60/201。
4. **subprocess 自报成功 ≠ 结果正确；cron `status=ok` ≠ 产出正确**。必须回读产物验证。
5. **后台通知写「completed normally (exit 0)」要看真实 EXIT 码**。用 `| tee` 的管道，退出码来自 tee 不是你的脚本。
6. **排查时禁用 `>/dev/null 2>&1` 吞 stderr**。脚本已经打印了解法，吞掉就只能猜。
7. **「平台侧故障」的判据是拿同样输入重跑**。别没重跑就甩锅给平台。
8. **标准要写成代码里的硬门禁，不能靠「记得检查」**。例如中文覆盖门禁、红线扫描、论点方向复核，都是代码里会 abort 的函数，不是文档里的提醒。
9. **跨仓库「只读消费」代码是静默抹掉别人提交的元凶**：任何脚本对不属于自己的仓库做 `git reset --hard`，都先改成 `ff-only` + 脏则跳过。
10. **push 是不可逆操作，需用户确认**。删仓同理。

---

## 11. 文件地图

```
Science-KOL/
├── HANDOVER.md                本文
├── README.md                  旧文档（部分过时，见 §9 P5）
├── index.html                 面板（根目录；Pages 入口）；dashboard/index.html 是同一份
├── ops/
│   ├── cron-jobs.json         4 个 cron 的真实定义（路径已占位符化）
│   ├── hermes-scripts/        3 个 no_agent 包装脚本 → 拷到 ~/.hermes/scripts/
│   └── repo-scripts/          publish.sh、publish_cf_pages.sh（公网安全版：已去掉内网同步段与内网镜像段，红线正则改为环境变量 REDLINE_EXTRA_REGEX）
├── scripts/
│   ├── daily_chain.sh         日链 10 步
│   ├── fetch_literature.py    步1：17 源抓取（sources.py 是抓取层，含 403/429 绕过路径）
│   ├── classify_literature.py 步2：分流 + 摘要
│   ├── fetch_statements.py    步3：言论（调 sources_extra.py 做新闻）
│   ├── fetch_podcasts.py      步3b：播客（调 sources_podcast.py）
│   ├── translate_to_zh.py     步4：翻译
│   ├── build_four_layers.py   步5：四层生成；refetch_l3.py 补 L3 全文
│   ├── build_*_layers.py      步6、7：三层聚合
│   ├── build_dashboard.py     步8：建面板；dash_filter.py / prune_silent.py 是面板后处理
│   ├── check_zh_coverage.py   中文覆盖门禁
│   ├── roster.py              名册 SSOT + 四维评分定义（A 学术 30% / B 一手 25% / C 公共表达 30% / D 方法 15%）
│   ├── build_candidates.py / probe_public_voice.py / score_and_admit.py   入册三件套
│   ├── migrate_from_fc.py / migrate_batch2.py   从 Forecast-Checker 迁入
│   ├── verify_alive.py        在世状态核验
│   └── notion_sync.py         （Notion 同步脚本：公网仓库不含，只在内部版）
├── data/
│   ├── kol_registry.json      名册 SSOT（126 人，active 标记 53）
│   ├── literature/            文献日文件 YYYY-MM-DD.json（19 个，2026-09-13 起每天一个）
│   ├── statements/            观点日文件（19 个；每个文件的【内容窗口】是近 18 个月的全量快照，不是增量）
│   ├── layers/                展示层：literature_layers.json、statement_layers.json
│   ├── podcast_seen.json      已处理过的播客剧集（防重复转写）
│   ├── statements_rejected.json   闸门拒收留痕（1379 条）
│   └── raw/                   大体积中间产物，gitignore，可重建
├── docs/context-log.md        每日对话归档（context-distill 写，约 590 行）
├── logs/                      日链日志（gitignore）；daily_YYYY-MM-DD.log 是排错第一现场
└── scratch/                   临时（gitignore）；podcast/ 放转写缓存
```

**两个易混的数据概念**：
- `data/statements/YYYY-MM-DD.json` 是 **全量快照**，不是当天新增。「当天新增」= 今天快照里、此前任何一天快照都没出现过的 URL。digest 就是这样算的。
- `data/layers/*.json` 是**展示层**（已翻译、已聚合），面板读它；`data/literature/*.json` 是**源层**。翻译写回源层，所以必须先翻译再重建展示层。

---

## 12. 排错速查

| 现象 | 先看 | 常见真因 |
|---|---|---|
| 面板没更新 | `logs/daily_<今天>.log` 末尾 | 日链在某步崩溃；看最后一个 `[N/10]` 和 Traceback |
| selfheal 每小时报警/超时 | `logs/selfheal_*.log` | 日链每次崩在同一处（§4④）；**先修日链，不是 selfheal** |
| 日报说「还没跑完」 | `ps` 看日链是否真在跑 | 日链慢到 09:00 后才完成（§4③） |
| 公网 404 | `curl -sI https://science-kol.pages.dev/` | GitHub Pages 是账号级故障（§1）；看 Cloudflare 那条 |
| 中文缺失 | `.venv/bin/python3 scripts/check_zh_coverage.py` | 单轮 400 上限；手动 `translate_to_zh.py all` 补，然后**先重建三层再建面板** |
| 新闻言论为 0 | `grep 新闻源 logs/daily_*.log` | Google News 解析被限流（§3 已加备用路径）；看 `statements_rejected.json` 拒因 |
| 播客 `下载或转写失败` | `scratch/podcast/` | faster-whisper 路径不对（§7）；或音频 403 |
| LLM 返回空 | `echo $GENAI_PROXY` | **手动跑没加载 `.env.local`**；代理偶发空返回，同输入重跑即成功 |
| 手动跑和 cron 结果不一样 | 环境变量 | cron 经 `daily_chain.sh` 加载 `.env.local`，手动跑要自己 `set -a; . ./.env.local; set +a` |

---

*本文由 agent-project-handoff 流程生成，数据取自 2026-10-01 原机器实测。*
*公网版：不含内网标识。*
