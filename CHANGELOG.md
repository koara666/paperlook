# 更新日志

本项目遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)（SemVer），格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

PaperLook 是桌面应用而不是代码库，「版本号」对用户的含义约定如下：

- **主版本号（X.0.0）**：升级后旧数据不能自动沿用——数据库无法自动迁移、旧备份无法导入，或删除了已有功能。
- **次版本号（1.X.0）**：新增功能或明显的行为变化，旧数据自动迁移、照常可用。
- **修订号（1.0.X）**：只修复问题，不加新功能。

## [未发布]

## [1.0.0] - 2026-10-27

首个正式版本。

### 新增
- 每日论文推荐：arXiv、OpenAlex（可选 Semantic Scholar、PubMed）检索，跨来源去重，按「相关度 + 质量 + 时效」可解释评分；推荐过的论文不再重复。
- 研究方向：9 个预设 + 自定义关键词、排除词、arXiv 分类、关注程度；AI 推荐关键词。
- 全文阅读：arXiv 结构化 HTML 优先，PDF 兜底；公式、图片、表格、算法、参考文献。
- DeepSeek 驱动的全文翻译（公式保护、术语表、可续传、单节重译、导出 Markdown）、论文总结、关键模块分析、创新点提取（原文引用自动核验）。
- 论文库、收藏/已读/隐藏、备份导出与导入、深色模式、手机宽度适配。
- `start.bat` 一键启动（自动创建环境、国内镜像兜底）。

[未发布]: https://github.com/koara666/paperlook/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/koara666/paperlook/releases/tag/v1.0.0
