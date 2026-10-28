# AGENT_GUIDE — 给后续开发 Agent 的接续说明

> 新对话开始时：先读本文件，再读 `PROJECT_STATUS.md`（进度/已知问题/测试结果）与 `ARCHITECTURE.md`（设计细节）。
> 然后以**实际代码**为准核对现状；文档与代码不一致时，修正文档。**不要重新规划或推翻现有架构，不要重复实现已有功能。**

## 1. 项目目标

个人 AI 论文阅读与推荐工具。用户（中文研究者，不审查代码、不做测试）每天打开工具点一个按钮，获得几篇与研究方向相关的近期论文；需要时主动触发全文翻译、总结、关键模块分析、创新点提取。所有开发、测试、验证由 Agent 独立完成。

## 2. 不可破坏的设计原则

1. **AI 只在用户明确点击后调用。** 打开页面、打开论文、切换标签、自动获取推荐都不能调用 AI（DeepSeek / Gemini）。`mode="auto"` 的推荐永不使用 AI 精排。功能开关只控制按钮是否显示，不等于自动运行。
2. **不重复消耗**：已有结果直接返回（`force` 才重新生成）；同一 (任务类型, 论文) 同时只允许一个任务（`jobs.py` 去重）；翻译逐块保存、可续传。
3. **不伪造**：没有依据的质量信号不打分（中性 0.5）；摘要生成的结果必须标明「仅基于摘要」；摘要翻译不能冒充全文翻译；作者声明 / 内容归纳 / AI 推断必须分开；引用要核验。
4. **论文来源是固定的可信列表**（`sources/__init__.py` 注册表），不爬取任意网站，只获取合法开放的全文。
5. **时间窗口决定候选资格，freshness 只影响排序**；使用首次发布日期（arXiv v1），不用更新/收录日期。
6. **API Key 安全**：只存于 `secrets_store`（系统凭据管理器 / DPAPI），绝不写入设置、数据库、日志、备份或返回给前端（只返回打码形式）。
7. **普通用户零技术操作**：所有配置都能在 UI 完成；错误信息用中文写清原因和解决办法（`AppError(message, code)`）。
8. **UI 质量是核心要求**：保持现有设计语言（`frontend/src/index.css` 的 CSS 变量 + Tailwind 主题色、`components/ui/*` 组件），支持深色模式与手机宽度（390px 无横向溢出）。

## 3. 技术架构速览

- 后端 `backend/paperlook/`：FastAPI + SQLite（`data/paperlook.db`）。入口 `python -m paperlook`（需 `PYTHONPATH=backend`，start.bat 已设置）。
- 前端 `frontend/`：React 19 + TypeScript + Tailwind v4 + React Query + KaTeX。**构建产物提交在 `backend/paperlook/static/`**，用户无需 Node.js。
- 关键流程：推荐 `recommend/engine.py`；全文 `fulltext/fetcher.py`；翻译 `ai/translate.py`；分析 `ai/analyze.py`；AI 客户端 `ai/client.py`（`DeepSeekClient` / `GeminiClient`，接口相同，`get_client()` 按 `settings.ai.provider` 选择）；提示词 `ai/prompts.py`。
- 桌面应用：`desktop.py`（pywebview 窗口 + 后台 uvicorn）；打包 `packaging/`（PyInstaller spec、Inno Setup 安装脚本、`build_windows.ps1`）。安装版（`config.FROZEN`）数据目录为 `%LOCALAPPDATA%\PaperLook`。
- CI/CD：`.github/workflows/ci.yml`（三平台测试、前端构建产物一致性、启动脚本冒烟测试）、`release.yml`（`v*` 标签 → 打包 → 发布 Release）。
- 详见 `ARCHITECTURE.md`（模块表、数据流、表结构、排序公式、DeepSeek 参数、安全、决策理由）。

## 4. 运行与测试

```bash
# 启动（Windows 双击 start.bat；或）
set PYTHONPATH=backend && .venv\Scripts\python -m paperlook --port 8765        # 加 --no-browser 不打开浏览器
# 用临时数据目录测试，避免污染用户数据：
set PAPERLOOK_DATA_DIR=<临时目录>  &&  set PAPERLOOK_DISABLE_KEYRING=1

# 后端测试（必须全部通过）
.venv\Scripts\python -m pytest backend/tests

# 模拟 DeepSeek 与 Gemini（无需真实 Key/额度）：
.venv\Scripts\python backend/tests/mock_deepseek.py 8790
#   DeepSeek：PATCH /api/ai/config {"base_url":"http://127.0.0.1:8790"}，PUT /api/ai/key {"api_key":"sk-mock-ok-123456"}
#     特殊 Key：sk-mock-401… / sk-mock-402… / sk-mock-429…（首次 429） / sk-mock-500…
#   Gemini：PATCH /api/ai/config {"provider":"gemini","gemini_base_url":"http://127.0.0.1:8790"}，
#     PUT /api/ai/key {"api_key":"AIza-mock-ok-123456","provider":"gemini"}
#     特殊 Key：AIza-mock-invalid… / -region… / -daily…（当天额度用完） / -zero… / -rpm…（首次每分钟限流） / -strict…（不支持系统指令与 minimal 思考）
#   backend/tests/test_gemini.py 会在随机端口自动启动这个模拟服务。

# 前端
cd frontend && npm install          # 首次
npm run dev                         # 开发（5173，代理 /api 到 8765）
npm run build                       # tsc 类型检查 + 构建到 backend/paperlook/static —— 改了前端必须重新构建
```

UI 验证：开发依赖 `requirements-dev.txt`（pytest、playwright、pillow）。用 Playwright `chromium.launch(channel="msedge")` 截图检查（本机有 Edge，无需下载浏览器）。在 Git Bash 里传 URL 参数时设置 `MSYS_NO_PATHCONV=1`。Windows 控制台为 GBK，运行 Python 时设置 `PYTHONUTF8=1`。

## 5. 开发规则

- 改后端：补/改 `backend/tests` 中的测试，跑通 `pytest`。涉及 AI 流程时用模拟服务做端到端验证。
- 改前端：`npm run build` 必须通过（含 `tsc`）；用浏览器实际查看受影响页面（浅色+深色，桌面+390px 手机）。
- 数据库结构变更：在 `db.MIGRATIONS` **末尾追加**新迁移，绝不修改已有迁移。
- 新设置项：加到 `settings_store.DEFAULT_SETTINGS` 并在 `_validate` 中校验；前端 `api/types.ts` 同步类型。
- 新论文来源：继承 `sources/base.Source`，实现 `search()`，在 `sources/__init__.py` 注册并设置 `PRIORITY`；在 `settings_store.DEFAULT_SETTINGS["sources"]` 加默认开关；`recommend/engine.PER_DIRECTION_MAX` 设上限。
- 新 AI 功能：提示词放 `ai/prompts.py`（要求 JSON 输出）；任务通过 `jobs.manager.submit` 运行；结果写 `ai_results`；前端用 `AiPanel` 包装以复用状态处理；默认需要用户点击。只用 `BaseClient` 的公共接口（`chat` / `chat_json`），两个服务都要能用；新的错误码若应终止整个翻译任务，加入 `translate.FATAL_CODES`。界面文字不要写死「DeepSeek」，用 `useAiLabel()`。
- 新 AI 服务：在 `ai/client.py` 实现 `BaseClient` 子类（`_send`、`list_models`、错误映射为中文 `AIError`），注册到 `PROVIDERS` 与 `make_client`，Key 名加到 `secrets_store`，设置加到 `settings_store`（`ai.<provider>`），并扩展模拟服务与测试。
- 改了打包相关代码（`desktop.py`、`config.py`、`packaging/`、新增依赖）：本地运行 `packaging/build_windows.ps1 -SmokeTest` 确认 exe 能启动；新依赖若靠动态导入或入口点加载，要在 `paperlook.spec` 补 `hiddenimports` / `copy_metadata`。
- 不要提交 `data/`、`.venv/`、`node_modules/`、任何 Key（见 `.gitignore`）。
- 模型的 JSON 输出由 `client.parse_json` 读取，它会修正 Gemini 常见的错误（未转义的 LaTeX 反斜杠、用错的结束括号）；改动它时跑 `backend/tests/test_ai_json.py`，并确认正确的 JSON 读取结果不变。
- 含反斜杠的文件内容（测试、提示词、LaTeX）用编辑工具写入，不要用 Git Bash 的 heredoc：`\\` 可能被折叠成 `\`。
- 用户可见文字使用简体中文。
- 完成一轮工作后更新 `PROJECT_STATUS.md`（已完成/未完成/已知问题/测试结果/日期），必要时更新 `ARCHITECTURE.md` 与 `README.md`。

## 6. 版本与发布

- 版本号只在两处：`backend/paperlook/__init__.py` 的 `__version__` 与 `frontend/package.json`（`cd frontend && npm version X.Y.Z --no-git-tag-version`），测试会检查二者与 `CHANGELOG.md` 一致。
- 规则（见 `CHANGELOG.md` 开头）：数据不兼容或删除功能 → 主版本；新功能 → 次版本；只修问题 → 修订号。
- 平时把改动记到 `CHANGELOG.md` 的「未发布」下面；发布时把它改成 `## [X.Y.Z] - 日期`，更新文件末尾的比较链接，改版本号，提交并推送 main，等 CI 通过后 `git tag -a vX.Y.Z -m "PaperLook X.Y.Z" && git push origin vX.Y.Z`。`release.yml` 会校验标签与版本号一致、跑测试、打包、冒烟测试、发布 Release（说明取自 CHANGELOG + 安装说明）。
- 已发布的标签不要移动或删除；发布出错就修复后发下一个修订号。
- 没有 `gh` 命令时，用 `curl -s https://api.github.com/repos/koara666/paperlook/actions/runs?per_page=5` 查看 CI 结果（公开仓库无需登录）。作业日志需要登录才能下载，所以失败的步骤会用 `scripts/ci_annotate.py` 把日志末尾和错误行写成注释：先取 `runs/<run id>/jobs` 中失败作业的 `check_run_url`，再读 `<check_run_url>/annotations` 即可看到原因。打包时安装包使用的语言文件也会以 notice 注释输出。
- CI 的 Windows 机器装的是 Inno Setup 6（简体中文不是官方语言），所以 `packaging/ChineseSimplified.isl` 随仓库提供；Inno Setup 7 自带的官方文件优先。

## 7. 如何避免重复实现

动手前用 grep 确认功能是否已存在。常见功能位置：

| 需求 | 已有实现 |
| --- | --- |
| 推荐流程/排序/去重 | `recommend/engine.py`, `ranker.py`, `dedupe.py`, `relevance.py`, `quality.py`, `venues.py`, `freshness.py` |
| 论文读写与状态 | `papers.py`（`upsert`, `set_state`, `seen_identity_keys`, `card`） |
| 后台任务/进度/取消 | `jobs.py`（`manager.submit`, `Job.update/advance/finish/check_cancelled`） |
| 全文与文档模型 | `fulltext/model.py`（`units`, `plain_text`）、`arxiv_html.py`、`pdf.py`、`fetcher.py` |
| 翻译状态/译文 | `ai/translate.py`（`status`, `translated_map`, `get_glossary`） |
| AI 结果读取 | `ai/analyze.get_result` |
| AI 服务选择 / Key / 用量 | `ai/client.py`（`get_client`、`make_client`、`active_provider`、`gemini_requests_today`）、`api/settings.py`（`/ai/*`） |
| 桌面窗口 / 单实例 / 安装版数据目录 | `desktop.py`、`config._default_data_dir` |
| Markdown 导出 | `export.py` |
| 引用（BibTeX / GB/T 7714） | `cite.py`、`GET /papers/{id}/cite`、`GET /library/bibtex` |
| 用户反馈偏好（排序微调） | `recommend/feedback.py`（`preferences`、`reason`），在 `engine.run` 中按 `settings.personalize` 应用 |
| 阅读笔记 | 后端 `paper_state.note`（`PATCH /papers/{id}/state`）；前端 `pages/paper/NoteCard.tsx` |
| 复制到剪贴板 | `frontend/src/lib/clipboard.ts`（`copyText`，桌面 WebView 兼容） |
| 设置/方向/来源/AI 配置 API | `api/settings.py` |
| 前端数据请求 | `frontend/src/api/hooks.ts`（React Query hooks）、`api/types.ts` |
| 前端通用组件 | `components/ui/primitives.tsx`（Button/Badge/Card/Switch/Input/Segmented/Notice/…）、`overlay.tsx`（Dialog/Confirm/Toast/Popover/Menu/Tooltip）、`ChipInput.tsx` |
| 数学渲染 | `frontend/src/lib/math.tsx`（`MathText` 处理 `$…$`，`MathBlock` 独立公式，`MathWrap` 窄卡片内可换行公式） |

## 8. 如何继续下一阶段

1. 读 `PROJECT_STATUS.md` 的「尚未实现」「已知问题」「下一步建议」。
2. 启动应用（临时数据目录）确认当前可用；跑 `pytest`。
3. 选定任务 → 小步实现 → 测试 → 浏览器验证 → 更新文档。
4. 真实 DeepSeek（deepseek-flash）已于 2026-10-27、真实 Gemini（gemini-3.5-flash-lite，免费档）已于 2026-10-28 验证通过。安装版的数据在 `%LOCALAPPDATA%\PaperLook`：需要用户的真实论文时，用 sqlite 只读备份到临时目录再启动测试实例，不要直接操作安装版的数据或正在运行的窗口。用户的 Key 在系统凭据管理器中：用临时数据目录启动测试实例（不设 `PAPERLOOK_DISABLE_KEYRING`）即可复用该 Key 做真实验证，但会消耗用户余额，只在必要时少量使用；日常开发用模拟服务。
5. 仓库已发布在 <https://github.com/koara666/paperlook>（作者身份 koara666 <luoyu6867@gmail.com>）。提交前确认 `data/`、`.venv/`、密钥不在提交中（`.gitignore` 已覆盖）；改了 `start.bat` 等脚本要保持 CRLF（`.gitattributes` 已约束）。推送失败提示连不上 `127.0.0.1:7897` 时，是全局 git 代理没在运行，可用 `git -c http.proxy= -c https.proxy= push` 直连。

## 9. 「完整可用」的判定清单

- [ ] 无 Key 首次启动：显示引导，可选方向并获得推荐；AI 区域提示配置而不报错
- [ ] 设置 Key → 测试连接三步全部通过；错误 Key 有清晰提示；Key 不出现在任何响应/日志
- [ ] 推荐：时间范围、数量、方向修改即时生效；结果有理由与评分构成；再次获取不重复；来源失败有提示
- [ ] 论文详情：全文自动加载；翻译可开始/停止/继续/单节重译/导出；三项分析可生成、缓存、重新生成
- [ ] 打开论文、切换标签不产生任何 AI 调用（`/api/usage` 计数不变）
- [ ] 重启应用后：推荐历史、已读/收藏、全文、译文、AI 结果、设置全部仍在
- [ ] `pytest` 全部通过；`npm run build` 通过；浅色/深色、桌面/手机截图无明显问题
- [ ] GitHub Actions 的 CI 全绿；发布版本时 Release 工作流生成安装包且冒烟测试通过
- [ ] 文档与代码一致
