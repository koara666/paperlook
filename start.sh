#!/usr/bin/env bash
# PaperLook launcher for macOS / Linux:  ./start.sh
set -e
cd "$(dirname "$0")"
export PYTHONUTF8=1

# An environment copied from another computer or left behind after a Python upgrade: rebuild it.
if [ -x ".venv/bin/python" ] && ! .venv/bin/python -c "import sys" >/dev/null 2>&1; then
  echo "[PaperLook] The Python environment is broken, rebuilding it..."
  rm -rf .venv
fi

if [ ! -x ".venv/bin/python" ]; then
  PY=""
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
      PY="$c"; break
    fi
  done
  if [ -z "$PY" ]; then
    echo "[PaperLook] Python 3.11 or newer was not found. Install it from https://www.python.org/downloads/ and run ./start.sh again."
    exit 1
  fi
  echo "[PaperLook] First start: creating the Python environment..."
  "$PY" -m venv .venv || {
    rm -rf .venv
    echo "[PaperLook] Could not create the environment. On Debian/Ubuntu run: sudo apt install python3-venv"
    exit 1
  }
fi

.venv/bin/python scripts/ensure_deps.py
PYTHONPATH="$(pwd)/backend" exec .venv/bin/python -m paperlook "$@"
