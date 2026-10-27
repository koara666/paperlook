"""The version lives in backend/paperlook/__init__.py; everything else must agree with it."""
import json
import re
import sys
from pathlib import Path

from paperlook import __version__

ROOT = Path(__file__).resolve().parents[2]
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")


def test_version_is_semver():
    assert SEMVER.match(__version__), __version__


def test_frontend_version_matches():
    pkg = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    assert pkg["version"] == __version__


def test_changelog_has_current_version():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import release_notes
    finally:
        sys.path.pop(0)
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert release_notes.section(__version__, text), f"CHANGELOG.md 缺少 [{__version__}] 一节"
    assert release_notes.section("0.0.0", text) is None


def test_version_compare():
    from paperlook.api.system import parse_version

    assert parse_version("v1.10.0") > parse_version("1.9.3")
    assert parse_version("1.1.0") > parse_version("1.1.0-beta.1")
    assert parse_version("2.0.0") > parse_version("1.99.99")
    assert parse_version("garbage") is None
