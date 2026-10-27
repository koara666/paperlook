"""CI helper: print the tail of log files as GitHub Actions error annotations.

Annotations can be read through the public API without signing in (job logs cannot), which lets
a developer without a GitHub token see why a job failed:
    curl https://api.github.com/repos/koara666/paperlook/check-runs/<job id>/annotations

    python scripts/ci_annotate.py <log file> [...]
"""
from __future__ import annotations

import sys
from pathlib import Path

TAIL = 6000


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    for name in sys.argv[1:]:
        p = Path(name)
        if not p.exists():
            print(f"::error title={p.name}::(file not found)")
            continue
        text = p.read_text(encoding="utf-8", errors="replace").replace("\r", "")
        tail = text[-TAIL:]
        print(f"::error title={p.name}::" + tail.replace("%", "%25").replace("\n", "%0A"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
