"""Static guards for the architecture rules in docs/build/ARCHITECTURE.md."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "maindscout"
WRITE_CALLS = re.compile(r"\.(add|add_all|merge|delete|execute|flush|commit)\(")


def _files(package: str):
    return [p for p in (ROOT / package).rglob("*.py")]


def test_intelligence_never_touches_the_database():
    for path in _files("intelligence") if (ROOT / "intelligence").exists() else []:
        text = path.read_text(encoding="utf-8")
        assert "sqlalchemy" not in text and "maindscout.db" not in text, path


def test_only_api_writes_to_the_database():
    for package in ("domain", "intelligence"):
        if not (ROOT / package).exists():
            continue
        for path in _files(package):
            assert not WRITE_CALLS.search(path.read_text(encoding="utf-8")), path
