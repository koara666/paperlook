# PaperLook

个人 AI 论文推荐与阅读工具（FastAPI + SQLite 后端，React 前端预构建在 `backend/paperlook/static/`）。

**继续开发前必须先读 `AGENT_GUIDE.md`**（设计原则、运行与测试方法、开发规则、完成标准），再读 `PROJECT_STATUS.md` 与 `ARCHITECTURE.md`。

最重要的规则：AI（DeepSeek）只能在用户点击后调用；API Key 只经 `secrets_store` 保存且永不返回前端；改前端后执行 `cd frontend && npm run build`；改后端后执行 `.venv/Scripts/python -m pytest backend/tests`；测试时使用 `PAPERLOOK_DATA_DIR=<临时目录>` 与 `backend/tests/mock_deepseek.py`，不要污染用户的 `data/`。
