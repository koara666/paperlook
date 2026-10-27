# PaperLook 架构说明

## 1. 总体结构

```
┌───────────────────────── 浏览器 (http://127.0.0.1:8765) ─────────────────────────┐
│ React + TS + Tailwind（frontend/，构建产物在 backend/paperlook/static/）          │
│  今日推荐 · 论文库 · 论文详情（概览/全文·翻译/总结/模块/创新点）· 设置            │
│  React Query 轮询后台任务状态（job），不直接接触任何密钥                          │
└───────────────────────────────┬──────────────────────────────────────────────────┘
                                │ JSON /api/*（仅 127.0.0.1，Host/Origin 校验）
┌───────────────────────────────▼──────────────────────────────────────────────────┐
│ FastAPI 应用 backend/paperlook/main.py                                            │
│  api/  system · settings · recommend · papers · data   （薄路由层）               │
│  jobs.py  进程内任务管理（线程池 + 状态持久化；同类任务去重 → 双击不会重复扣费）  │
│                                                                                    │
│  recommend/  engine → sources/* → dedupe → 时间过滤 → 去已推荐 → 信号增强          │
│              → relevance / quality / freshness → ranker(配额选择) → 持久化         │
│  fulltext/   fetcher → arxiv_html（LaTeXML 解析）| pdf（PyMuPDF4LLM）→ 统一文档模型 │
│  ai/         client(DeepSeek) · prompts · translate · analyze · rerank            │
│  settings_store · directions · papers(仓储) · secrets_store · export · db(SQLite)  │
└───────────────┬─────────────────────────────┬─────────────────────────────────────┘
                │                             │
     arXiv / OpenAlex / S2 / PubMed      DeepSeek API（仅在用户点击后调用）
     / Hugging Face Daily Papers          https://api.deepseek.com
```

单进程、单机、单用户。`python -m paperlook`（由 start.bat/start.sh 调用）启动 uvicorn，并在就绪后打开浏览器。

## 2. 目录与模块

| 路径 | 职责 |
| --- | --- |
| `backend/paperlook/__main__.py` | 启动入口：端口探测、已运行实例检测、打开浏览器 |
| `main.py` | FastAPI 工厂、本地访问安全中间件、错误处理、SPA 静态文件 |
| `config.py` | 路径常量（`DATA_DIR` 可用环境变量 `PAPERLOOK_DATA_DIR` 覆盖） |
| `db.py` | SQLite（WAL，线程级连接）、版本化迁移 `MIGRATIONS`、kv 缓存 |
| `settings_store.py` | 用户设置（单个 JSON 文档）、默认值、校验、排序预设 |
| `secrets_store.py` | API Key：keyring → Windows DPAPI 加密文件 → 仅限本人可读文件 |
| `directions.py` | 研究方向 CRUD、9 个预设、arXiv 分类表 |
| `papers.py` | 论文仓储：合并写入、用户状态、已推荐身份集合 |
| `jobs.py` | 后台任务：进度、取消、重启后标记中断、同 (kind, paper) 去重 |
| `sources/` | `base.py`（RawPaper、HTTP 重试、限速）+ arxiv / openalex / semantic_scholar / pubmed / hf_daily；注册表在 `sources/__init__.py` |
| `recommend/` | `engine`（流程编排）、`dedupe`、`relevance`、`quality`、`venues`（顶会/期刊表）、`freshness`、`ranker` |
| `fulltext/` | `model`（文档结构与可翻译单元）、`arxiv_html`、`pdf`、`fetcher`（来源选择与缓存） |
| `ai/` | `client`（DeepSeek 调用、错误映射、用量记录）、`prompts`、`translate`、`analyze`、`rerank` |
| `export.py` | 译文/AI 分析导出为 Markdown |
| `api/` | HTTP 路由 |
| `backend/tests/` | pytest 测试 + `mock_deepseek.py`（本地模拟 DeepSeek，用于无额度测试） |
| `frontend/src/` | `api/`（类型、请求、hooks）、`components/`（ui、layout、papers）、`pages/`（Today、Library、Paper、Settings 及子组件）、`lib/`（KaTeX 渲染、格式化、主题） |

## 3. 数据流

### 3.1 每日推荐（`POST /api/recommend/run` → job "recommend"）

1. 读取启用的方向与来源；检索时间窗口 `[今天 - N 天, 今天]`。
2. **检索**：各来源并行、来源内按方向串行（arXiv 遵守 3 秒/请求）。每个方向自动生成查询：
   - arXiv：`(cat:A OR cat:B) AND (ti:"kw" OR abs:"kw" …) AND submittedDate:[…]`，按相关度取前 200。
   - OpenAlex：`title_and_abstract.search:"kw" OR …`，过滤发布日期、排除 repository（arXiv 已直接检索）。
   - Semantic Scholar（bulk search，布尔查询）/ PubMed（esearch + efetch）。
   - 候选池缓存 2 小时（`kv_cache` 的 `pool:*`），「再推荐几篇」无需重新检索。
3. **去重合并**（dedupe）：arXiv ID / DOI（含 10.48550/arxiv.*）/ PMID / 规范化标题；优先 arXiv 的标题摘要，补齐期刊、DOI、引用等；发布日期取各来源中**最早的精确日期**。
4. **时间过滤**：只保留发布日期在窗口内且日期可靠（exact/approx）的论文；日期未知的排除并计数。
5. **去重复推荐**：已推荐或「不感兴趣」的论文（按身份键）永不再出现。
6. **信号增强**：HF Daily Papers 点赞数（按天缓存）、OpenAlex 期刊/会议统计（30 天缓存）。
7. **评分与选择**（见第 5 节），可选 AI 精排（显式开启；`auto` 模式永不调用 AI）。
8. **持久化**：`rec_batches` + `recommendations`（含评分构成 breakdown 与中文推荐理由），论文写入 `papers`。

### 3.2 全文（`POST /papers/{id}/fulltext` → job "fulltext"，免费，打开标签即自动执行）

`arxiv.org/html/<id>`（LaTeXML）→ 失败则 arXiv PDF → 开放获取 PDF（来源元数据中的 OA 链接）→ 都没有则给出原因。解析结果（统一文档 JSON）存入 `fulltext` 表。

### 3.3 全文翻译（`POST /papers/{id}/translate` → job "translate"）

1. 文档 → 可翻译单元：章节标题、段落、段内标题、列表项、图/表/算法标题。公式、代码、表格正文、参考文献不发送。
2. 行内公式 `$…$` 替换为 `⟦M1⟧` 占位符，返回后还原并校验，缺失则重试一次并标记。
3. 首次翻译先生成术语表（`ai_results.kind = glossary`），每个请求都带上，保证译名一致。
4. 单元按约 4500 字符分块（小章节会合并，最多 40 段），并发（默认 4）调用，JSON 输出 `{"translations":[{id,text}]}` 保证段落一一对应。
5. 每块成功立即写入 `translations`；失败块记录错误，作业状态为 `partial`，「继续翻译」只翻译缺失部分。401/402/模型错误立即终止整个作业。
6. 提示词顺序：固定前缀（system + 标题 + 术语表）在前、可变内容在后，以命中 DeepSeek 前缀缓存。

### 3.4 AI 分析（`POST /papers/{id}/ai/{summary|modules|contributions|abstract_translation}`）

尝试获取全文（`plain_text` ≤ 18 万字符，不含参考文献）→ 失败则用摘要并在结果中记录 `basis.type = abstract` 与原因 → JSON 模式调用（可选深度思考）→ 创新点的作者原文引用用 4-gram 重合度核验（exact/close/partial/not_found）→ 写入 `ai_results`。已有结果时不带 `force` 的请求直接返回 `cached`。

消息顺序为「system（固定）→ 论文信息与全文 → 任务说明」：三项分析共享「system + 论文」长前缀，先后运行时后两项约 96% 的输入命中 DeepSeek 上下文缓存（实测）；任务放在长文档之后也更利于模型遵循指令。文字字段中的数学符号要求用 `$…$` 包裹，前端用 `MathText` 渲染；`key_formula` 用 `MathWrap`（行内 + `\displaystyle`，可在关系符处换行）。

## 4. 数据存储（SQLite：`data/paperlook.db`）

| 表 | 内容 |
| --- | --- |
| `settings` | `key='user'` 的设置 JSON |
| `directions` | 研究方向（关键词、排除词、分类为 JSON 数组） |
| `papers` | 合并后的论文元数据；`signals`（引用、HF 点赞、代码链接、期刊 ID…）与 `sources` 为 JSON |
| `paper_state` | 已读、收藏、不感兴趣、打开时间、笔记（预留） |
| `rec_batches` / `recommendations` | 每次推荐的参数、统计、提示信息；每篇的排名、分数、breakdown、理由、方向、AI 精排结果 |
| `fulltext` | 解析后的文档 JSON |
| `translations` | 按单元保存的译文（unit_id 与文档块 id 对应） |
| `ai_results` | summary / modules / contributions / abstract_translation / glossary 结果、依据、模型、用量 |
| `jobs` | 任务状态（重启时把运行中的标记为 interrupted） |
| `api_usage` | 每次 DeepSeek 调用的 tokens（不含任何内容） |
| `kv_cache` | 候选池、HF 每日列表、期刊统计、模型列表、上次连接测试 |

迁移：在 `db.MIGRATIONS` 末尾追加新脚本（`PRAGMA user_version` 记录版本），**不要修改已发布的脚本**。

## 5. 推荐排序模型

```
score = w_r · relevance + w_q · quality + w_f · freshness        （默认 0.55 / 0.25 / 0.20，和为 1）
```

- **relevance**（relevance.py）：关键词在标题命中计 1.0，仅摘要命中计 0.55–0.8（次数越多越高）；多关键词以 noisy-OR 合并 `1 − Π(1 − 0.6·s_k)`；arXiv 主分类吻合 +0.12、交叉分类 +0.06。连字符/空格/复数不敏感；全大写缩写（RAG、CLIP）区分大小写。排除词按方向生效。**相关度 < 0.3 的论文不进入候选**——质量与时效再高也不会推荐无关论文。开启 AI 精排时：`relevance = 0.4·关键词 + 0.6·AI 评分`。
- **quality**（quality.py + venues.py）：只用可验证信号——venue 0.40（作者注明的接收/发表，排除 submitted/under review/ARR；或 OpenAlex 期刊 2 年平均被引）、citations 0.25（仅发表 ≥30 天的论文，按月均被引或 OpenAlex 百分位）、community 0.20（HF 点赞）、completeness 0.15（开源代码、页数）。按证据量收缩到中性值：`quality = c·observed + (1−c)·0.5`，`c` = 已有信号权重和。没有证据的新论文就是 0.5，不加分也不扣分。
- **freshness**（freshness.py）：`0.2 + 0.8 · 0.5^(age/半衰期)`，半衰期 3/7/21 天（偏好最新/均衡/不太在意）；近似日期 ×0.85。时间窗口只决定能否成为候选，freshness 只影响排序。
- **跨方向选择**（ranker.py）：每篇归入最匹配的方向；名额按「关注程度」权重用最大余数法分配；某方向候选不足时名额让给其他方向的高分论文；最终按总分排序。
- **自定义权重**：归一化后相关度不低于 20%。

## 6. DeepSeek 接入

- OpenAI 兼容 `POST {base_url}/chat/completions`；模型默认 `deepseek-flash`（另有 `deepseek-v4-pro`，列表也从 `GET /models` 获取）。
- 思考模式：请求体 `thinking: {type: enabled|disabled}`（DeepSeek V4 起默认开启）。翻译固定关闭；分析由设置「深度思考」控制。若兼容端点不认识该字段（400/422 含 thinking），自动去掉后重试。
- JSON 模式 `response_format: {type: json_object}`；输出被截断（finish_reason=length）时自动加大 max_tokens 重试；JSON 解析失败重试一次。
- 错误映射：401 Key 无效、402 余额不足、429 限流（退避重试）、400/422 参数或模型不可用、404 服务地址错误、5xx/503 服务异常（重试）、网络/超时。所有消息为中文并带解决方法，前端原样显示。
- 连接测试：`GET /models`（鉴权）→ `GET /user/balance`（余额）→ 8 tokens 的对话调用。
- 用量：每次调用的 prompt/completion/cache-hit tokens 记入 `api_usage`。

## 7. 安全

- 服务只监听 `127.0.0.1`；中间件拒绝非 localhost 的 Host（防 DNS rebinding），拒绝跨站 Origin 的写请求（防止其他网页驱动本地 API 消耗额度）。
- API Key 存于系统凭据管理器（`keyring`，服务名 `PaperLook`）；不可用时 Windows 上用 DPAPI 加密文件 `data/secrets.bin`；其他系统退化为仅本人可读的文件（文档已说明）。
- 前端只能拿到打码后的 Key；日志中不记录请求头和 URL（httpx 日志降到 WARNING；OpenAlex Key 走 Authorization 头而非 URL）。
- 备份导出只包含数据库表，不含 Key。

## 8. 关键技术决策

| 决策 | 原因 |
| --- | --- |
| 本地网页应用（Python 后端 + 浏览器 UI），而非桌面框架 | 无需额外运行时；PDF/HTML 解析生态在 Python 最成熟；浏览器提供最好的排版与数学渲染；一个 start.bat 即可启动 |
| 前端预构建并随代码分发 | 用户不需要安装 Node.js |
| arXiv HTML 优先于 PDF | LaTeXML 保留章节层级、LaTeX 公式、图片、表格与参考文献，翻译质量远高于 PDF 文本 |
| 推荐阶段默认不使用 AI | 传统算法已足够快速、可解释、零成本；AI 精排作为显式开关 |
| 不用向量检索/本地嵌入模型 | 依赖重（torch 等）、收益有限；DeepSeek 不提供嵌入接口；关键词 + 可选 AI 精排更透明 |
| Semantic Scholar 默认关闭 | 匿名访问频繁 429；有免费 Key 时可开启 |
| HF Daily Papers 只作为排序信号 | 它不是学术数据库，但点赞数是真实可验证的社区关注度；未上榜不视为负面 |
| 质量分无证据时取中性 0.5 | 避免虚构评级；新论文不因没有引用而被惩罚 |
| SQLite + JSON 列 | 单用户本地应用的最简单可靠方案，易备份，结构可迁移 |
| 进程内任务 + 前端轮询 | 比 WebSocket/消息队列简单可靠；任务状态写库，重启可恢复已完成部分 |
