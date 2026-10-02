"""Static guards for the architecture rules in docs/build/ARCHITECTURE.md."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "maindscout"
WRITE_CALLS = re.compile(r"\.(add|add_all|merge|delete|execute|flush|commit)\(")


def _files(package: str):
    return list((ROOT / package).rglob("*.py")) if (ROOT / package).exists() else []


def test_intelligence_and_ingestion_never_touch_the_database():
    for path in _files("intelligence") + _files("ingestion"):
        text = path.read_text(encoding="utf-8")
        assert "sqlalchemy" not in text and "maindscout.db" not in text, path


def test_only_api_writes_to_the_database():
    for package in ("domain", "intelligence", "ingestion"):
        for path in _files(package):
            assert not WRITE_CALLS.search(path.read_text(encoding="utf-8")), path
