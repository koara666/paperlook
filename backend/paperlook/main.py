"""FastAPI application: JSON API under /api, built frontend served from /static."""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config, db
from .errors import AppError
from .jobs import manager

log = logging.getLogger("paperlook")


def setup_logging() -> None:
    config.log_dir().mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if any(getattr(h, "_paperlook", False) for h in root.handlers):
        return
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = logging.handlers.RotatingFileHandler(config.log_dir() / "paperlook.log", maxBytes=2_000_000, backupCount=3,
                                              encoding="utf-8")
    fh.setFormatter(fmt)
    fh._paperlook = True  # type: ignore[attr-defined]
    root.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    sh._paperlook = True  # type: ignore[attr-defined]
    root.addHandler(sh)
    root.setLevel(logging.INFO)
    # httpx logs full URLs at INFO; keep it quiet (and keys are only ever sent in headers anyway).
    for noisy in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def create_app(allowed_ports: set[int] | None = None) -> FastAPI:
    db.configure()
    manager.recover_after_restart()
    app = FastAPI(title="PaperLook", version=config.VERSION, docs_url="/api/docs", openapi_url="/api/openapi.json")

    dev_origins = {o.strip() for o in os.environ.get("PAPERLOOK_DEV_ORIGINS", "").split(",") if o.strip()}

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        # The server binds to 127.0.0.1 only. These checks additionally stop other websites open in
        # the browser from driving this API (DNS rebinding / cross-site requests that could spend tokens).
        host = (request.headers.get("host") or "").split(":")[0].lower()
        if host not in ("127.0.0.1", "localhost", "testserver"):
            return JSONResponse({"detail": "Forbidden host"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and request.method not in ("GET", "HEAD", "OPTIONS"):
            o_host = origin.split("://", 1)[-1].split(":")[0].lower()
            if o_host not in ("127.0.0.1", "localhost") and origin not in dev_origins:
                return JSONResponse({"detail": "Forbidden origin"}, status_code=403)
        return await call_next(request)

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError):
        return JSONResponse({"detail": exc.message, "code": exc.code}, status_code=exc.status_code)

    from .api import data, papers, recommend, settings, system

    for r in (system.router, settings.router, recommend.router, papers.router, data.router):
        app.include_router(r, prefix="/api")

    static = config.STATIC_DIR
    if (static / "index.html").exists():
        assets = static / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str):
            if full_path.startswith("api/"):
                return JSONResponse({"detail": "Not found"}, status_code=404)
            candidate = (static / full_path).resolve()
            if full_path and candidate.is_file() and static.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(static / "index.html", headers={"Cache-Control": "no-cache"})
    else:
        @app.get("/", include_in_schema=False)
        async def no_frontend():
            return JSONResponse({"detail": "前端尚未构建：请在 frontend 目录运行 npm run build"}, status_code=503)

    return app
