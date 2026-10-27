"""Desktop mode: the same local server, shown in its own window instead of a browser tab.

    python -m paperlook --window        (from source; needs `pip install pywebview`)
    PaperLook.exe                       (packaged app, see packaging/)

The window is pywebview on the system web engine (WebView2 on Windows, preinstalled on Windows
10/11). Closing the window stops the server. Starting PaperLook again while it is running brings
the existing window to the front. Without a usable web engine it falls back to the browser.
"""
from __future__ import annotations

import json
import logging
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from . import config

log = logging.getLogger(__name__)
WINDOW_TITLE = config.APP_NAME


def _status(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1.5) as r:
            data = json.loads(r.read().decode())
            return data if data.get("app") == config.APP_NAME else None
    except Exception:
        return None


def _same_data_dir(st: dict) -> bool:
    try:
        return Path(st.get("data_dir") or "").resolve() == config.DATA_DIR.resolve()
    except OSError:
        return False


def _focus_existing_window() -> bool:
    if sys.platform != "win32":
        return False
    import ctypes

    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, WINDOW_TITLE)
    if not hwnd:
        return False
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    return True


def _message(text: str) -> None:
    """Blocking notice. In a windowed app there is no console, so use a native message box."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, config.APP_NAME, 0x40)  # MB_ICONINFORMATION
    else:
        print(text)
        try:
            input()
        except EOFError:
            while True:
                time.sleep(3600)


def _pick_port(start: int) -> tuple[int, bool]:
    """(port, already_running): reuse an instance on the same data directory, else find a free port."""
    from .__main__ import _port_free

    for port in range(start, start + 20):
        st = _status(port)
        if st and _same_data_dir(st):
            return port, True
        if not st and _port_free(port):
            return port, False
    raise SystemExit(f"端口 {start}-{start + 19} 都被占用，无法启动 PaperLook。")


def main(port: int = config.DEFAULT_PORT) -> None:
    port, running = _pick_port(port)
    url = f"http://127.0.0.1:{port}"
    if running:
        if not _focus_existing_window():
            webbrowser.open(url)
        return

    import uvicorn

    from .main import create_app, setup_logging

    setup_logging()
    log.info("PaperLook %s desktop mode, data dir %s", config.VERSION, config.DATA_DIR)
    server = uvicorn.Server(uvicorn.Config(create_app(), host=config.DEFAULT_HOST, port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, name="server", daemon=True)
    thread.start()
    for _ in range(200):
        if server.started or not thread.is_alive():
            break
        time.sleep(0.05)
    if not server.started:
        _message("PaperLook 启动失败，详细原因见日志：\n" + str(config.log_dir() / "paperlook.log"))
        raise SystemExit(1)

    try:
        _run_window(url)
    except Exception:
        log.exception("could not open the app window, falling back to the browser")
        webbrowser.open(url)
        _message(f"PaperLook 已在浏览器中打开（{url}）。\n\n本机缺少内置浏览器组件 WebView2，所以没有使用独立窗口。"
                 "\n点击「确定」将退出 PaperLook。")
    finally:
        server.should_exit = True
        thread.join(10)


def _run_window(url: str) -> None:
    import webview  # pywebview

    webview.settings["ALLOW_DOWNLOADS"] = True  # exports and backups
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True  # arXiv / PDF / AI Studio links
    width, height = 1360, 900
    try:  # stay inside small / highly scaled screens (e.g. 1080p at 150% = 1280x720)
        screen = webview.screens[0]
        width, height = min(width, int(screen.width * 0.92)), min(height, int(screen.height * 0.9))
    except Exception:
        pass
    webview.create_window(WINDOW_TITLE, url, width=width, height=height, min_size=(400, 560), text_select=True)
    storage = config.DATA_DIR / "webview"  # keep the page's local storage (theme etc.) between runs
    storage.mkdir(parents=True, exist_ok=True)
    webview.start(private_mode=False, storage_path=str(storage),
                  localization={"windows.fileFilter.allFiles": "所有文件"})  # "Save as" dialog of downloads
