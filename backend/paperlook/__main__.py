"""Start PaperLook:  python -m paperlook [--port 8765] [--no-browser] [--window]

If an instance is already running on the port, just opens the browser.
--window shows the app in its own window instead of a browser tab (see desktop.py).
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

from . import config


def _running_instance(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1.5) as r:
            return json.loads(r.read().decode()).get("app") == config.APP_NAME
    except Exception:
        return False


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((config.DEFAULT_HOST, port))
            return True
        except OSError:
            return False


def main() -> None:
    parser = argparse.ArgumentParser(prog="paperlook")
    parser.add_argument("--port", type=int, default=config.DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--window", action="store_true", help="open in a desktop window (needs pywebview)")
    args = parser.parse_args()

    # Make console output safe on Windows terminals that are not UTF-8.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass

    if args.window:
        from .desktop import main as desktop_main

        desktop_main(args.port)
        return

    port = args.port
    if _running_instance(port):
        print(f"PaperLook 已在运行：http://127.0.0.1:{port}")
        if not args.no_browser:
            webbrowser.open(f"http://127.0.0.1:{port}")
        return
    while not _port_free(port) and port < args.port + 20:
        port += 1

    import uvicorn

    from .main import create_app, setup_logging

    setup_logging()
    app = create_app()
    url = f"http://127.0.0.1:{port}"
    print(f"\n  PaperLook {config.VERSION} 已启动：{url}\n  数据目录：{config.DATA_DIR}\n  关闭此窗口即可退出。\n")

    if not args.no_browser:
        def _open() -> None:
            for _ in range(50):
                if _running_instance(port):
                    webbrowser.open(url)
                    return
                time.sleep(0.2)
        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=config.DEFAULT_HOST, port=port, log_level="warning")


if __name__ == "__main__":
    main()
