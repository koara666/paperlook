"""Print the CHANGELOG.md section for one version (used as the GitHub Release body).

    python scripts/release_notes.py 1.1.0 > notes.md
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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
    return 0


if __name__ == "__main__":
    sys.exit(main())
