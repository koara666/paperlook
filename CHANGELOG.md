# 更新日志

本项目遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)（SemVer），格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

PaperLook 是桌面应用而不是代码库，「版本号」对用户的含义约定如下：

- **主版本号（X.0.0）**：升级后旧数据不能自动沿用——数据库无法自动迁移、旧备份无法导入，或删除了已有功能。
- **次版本号（1.X.0）**：新增功能或明显的行为变化，旧数据自动迁移、照常可用。
- **修订号（1.0.X）**：只修复问题，不加新功能。

## [未发布]

### 开发
- GitHub Actions 组件升级到 Node.js 24 版本（checkout / setup-python / setup-node / upload-artifact v7、action-gh-release v3），消除 Node.js 20 弃用警告。

## [1.1.0] - 2026-10-28

### 新增
- **Windows 桌面应用**：安装包 `PaperLook-1.1.0-Windows-Setup.exe`（不需要管理员权限，也不需要安装 Python）和免安装压缩包。界面在独立窗口中运行，关闭窗口即退出；重复打开会切换到已打开的窗口；导出和备份会弹出「另存为」对话框。安装版数据保存在 `%LOCALAPPDATA%\PaperLook`，升级、卸载都会保留。
- **Google Gemini**：可以在「设置 → AI 服务」改用 Gemini（AI Studio 的免费 Key 每天有一定请求额度）。两个服务的 Key 分开保存，随时切换。
  - 「免费档模式」：按模型自动限速，并把全文翻译合并成更少、更大的请求（一篇 1.3 万词的论文约 10 次请求）。
  - 显示今天已用的请求次数（按 Google 的重置时间，北京时间 15:00 / 冬令时 16:00 起算）。
  - 可填写代理地址；地区不支持、当天额度用完、Key 无效、模型不可用等情况都有中文说明和解决办法；额度用完时已完成的翻译会保留，之后可以继续。
- 「设置 → 数据与系统 → 关于」：检查更新（只在点击时访问 GitHub），显示是安装版还是源码版。
- 源码版可以用 `python -m paperlook --window` 在独立窗口中运行（需要 `pip install pywebview`）。

### 变更
- 界面中写死的「DeepSeek」改为当前使用的 AI 服务名称。
- 新增依赖 `httpx[socks]`（Gemini 代理支持 socks5）；源码版下次启动时会自动安装。

### 修复
- 源码版最低 Python 版本改为 3.11：PDF 解析组件 PyMuPDF 2.0 需要 3.11，之前用 3.10 启动会在安装组件时失败（CI 发现）。
- 源码版启动脚本在装有多个 Python 时优先选择 3.14 → 3.11：最新的 Python 3.15 还没有 onnxruntime 安装包，之前会导致首次安装失败；只有 3.15 时给出明确提示（CI 发现）。

### 开发
- 版本号遵循语义化版本，`CHANGELOG.md` 记录每个版本；测试会检查各处版本号一致。
- GitHub Actions：每次提交在 Windows / Linux / macOS 上运行测试、检查前端构建产物与源码一致、用 `start.bat` / `start.sh` 在全新环境中启动冒烟测试；推送 `v*` 标签自动打包、冒烟测试并发布 Release。
- 模拟服务 `backend/tests/mock_deepseek.py` 同时模拟 Gemini（含各种错误）；测试从 34 个增加到 55 个。

## [1.0.0] - 2026-10-27

首个正式版本。

### 新增
- 每日论文推荐：arXiv、OpenAlex（可选 Semantic Scholar、PubMed）检索，跨来源去重，按「相关度 + 质量 + 时效」可解释评分；推荐过的论文不再重复。
- 研究方向：9 个预设 + 自定义关键词、排除词、arXiv 分类、关注程度；AI 推荐关键词。
- 全文阅读：arXiv 结构化 HTML 优先，PDF 兜底；公式、图片、表格、算法、参考文献。
- DeepSeek 驱动的全文翻译（公式保护、术语表、可续传、单节重译、导出 Markdown）、论文总结、关键模块分析、创新点提取（原文引用自动核验）。
- 论文库、收藏/已读/隐藏、备份导出与导入、深色模式、手机宽度适配。
- `start.bat` 一键启动（自动创建环境、国内镜像兜底）。

[未发布]: https://github.com/koara666/paperlook/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/koara666/paperlook/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/koara666/paperlook/releases/tag/v1.0.0
