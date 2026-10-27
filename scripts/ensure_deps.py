"""Called by start.bat / start.sh: install Python dependencies when requirements.txt changed.

Keeps startup instant on normal days (hash check only) while making first-run setup automatic.
If the default package index (PyPI) is unreachable or too slow - common in mainland China - it
retries with well-known mirrors.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQ = ROOT / "requirements.txt"
MARKER = Path(sys.prefix) / ".paperlook-deps"

# None = whatever pip is configured with (PyPI by default, or the user's own pip.ini index).
INDEXES = [
    None,
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "https://mirrors.aliyun.com/pypi/simple/",
]


def pip_install(index: str | None) -> int:
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
           "--timeout", "20", "--retries", "2", "-r", str(REQ)]
    if index:
        cmd += ["-i", index]
    return subprocess.run(cmd).returncode


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            # line_buffering keeps our messages in order with pip's output when redirected to a log
            stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except Exception:
            pass
    if sys.version_info < (3, 10):
        print(f"PaperLook 需要 Python 3.10 或更高版本，当前为 {sys.version.split()[0]}。")
        print("请从 https://www.python.org/downloads/ 安装新版 Python，删除本目录下的 .venv 文件夹后重新启动。")
        return 1
    digest = hashlib.sha256(REQ.read_bytes()).hexdigest()
    if MARKER.exists() and MARKER.read_text().strip() == digest:
        return 0
    print("[PaperLook] 正在安装/更新运行所需的组件（只在首次启动或升级后进行，约 1-3 分钟）…")
    for i, index in enumerate(INDEXES):
        if i:
            print(f"\n[PaperLook] 默认源安装失败，改用镜像 {index} 重试…")
        if pip_install(index) == 0:
            MARKER.write_text(digest)
            print("[PaperLook] 组件安装完成。")
            return 0
    print("\n[PaperLook] 组件安装失败。请检查网络连接后重新运行；如果使用了代理，请确认 pip 可以联网。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
