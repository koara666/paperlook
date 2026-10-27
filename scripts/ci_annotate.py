"""CI helper: print the tail of log files as GitHub Actions error annotations.

Annotations can be read through the public API without signing in (job logs cannot), which lets
a developer without a GitHub token see why a job failed:
    curl https://api.github.com/repos/koara666/paperlook/check-runs/<job id>/annotations

    python scripts/ci_annotate.py <log file> [...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

TAIL = 2500  # GitHub truncates long annotation messages
ERROR_LINE = re.compile(r"error|exception|traceback|failed|not found|no matching", re.I)


def emit(title: str, text: str) -> None:
    print(f"::error title={title}::" + text.replace("%", "%25").replace("\r", "").replace("\n", "%0A"))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    for name in sys.argv[1:]:
        p = Path(name)
        if not p.exists():
            emit(p.name, "(file not found)")
            continue
        lines = p.read_text(encoding="utf-8", errors="replace").replace("\r", "").splitlines()
        errors = [ln for ln in lines if ERROR_LINE.search(ln)]
        if errors:
            emit(f"{p.name}: error lines", "\n".join(errors[-25:])[-TAIL:])
        emit(f"{p.name}: last lines", "\n".join(lines)[-TAIL:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
