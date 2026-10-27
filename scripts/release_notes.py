"""Print the CHANGELOG.md section for one version (used as the GitHub Release body).

    python scripts/release_notes.py 1.1.0 > notes.md
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

INSTALL = """
---

### 下载安装（Windows 10/11）

- **`PaperLook-{v}-Windows-Setup.exe`**（推荐）：双击安装，不需要管理员权限，也不需要安装 Python。安装后从开始菜单或桌面图标打开。升级时直接安装新版本即可，数据会保留。
- `PaperLook-{v}-Windows-Portable.zip`：免安装版，解压后双击 `PaperLook.exe`。

安装包没有数字签名，Windows 可能提示「Windows 已保护你的电脑」：点击「更多信息」→「仍要运行」。

数据保存在 `%LOCALAPPDATA%\\PaperLook`。从源码版（`start.bat`）迁移：在旧版「设置 → 数据与系统」导出备份，在新版导入即可；API Key 保存在系统凭据管理器中，两个版本共用。
macOS / Linux 请使用源码版（`./start.sh`），见 README。
"""


def section(version: str, text: str) -> str | None:
    m = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|^\[[^\]]+\]: |\Z)", text, re.S | re.M)
    return m.group(1).strip() if m else None


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    version = sys.argv[1].removeprefix("v")
    body = section(version, (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    if not body:
        print(f"CHANGELOG.md 中没有 [{version}] 的内容", file=sys.stderr)
        return 1
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    print(body)
    print(INSTALL.format(v=version))
    return 0


if __name__ == "__main__":
    sys.exit(main())
