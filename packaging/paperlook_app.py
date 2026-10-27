"""Entry point of the packaged desktop app (PyInstaller). See packaging/README.md."""
import os
import sys

# A windowed (no console) app has no stdout/stderr; logging and print() must not fail.
for _name in ("stdout", "stderr"):
    if getattr(sys, _name) is None:
        setattr(sys, _name, open(os.devnull, "w", encoding="utf-8"))

from paperlook.desktop import main  # noqa: E402

if __name__ == "__main__":
    main()
