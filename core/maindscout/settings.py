"""Configuration from the environment, falling back to core/.env (git-ignored)."""

from __future__ import annotations

import os
import threading
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

_lock = threading.Lock()
_cache: tuple[float, dict[str, str]] = (-1.0, {})


def _file_values() -> dict[str, str]:
    """core/.env parsed once, and again only when the file changes (init appends keys to it while running)."""
    global _cache
    try:
        mtime = ENV_FILE.stat().st_mtime
    except OSError:
        return {}
    if _cache[0] == mtime:
        return _cache[1]
    with _lock:
        values: dict[str, str] = {}
        try:
            for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
                key, _, value = line.strip().partition("=")
                if key and value and key not in values:
                    values[key] = value
        except OSError:
            return {}
        _cache = (mtime, values)
        return values


def env(name: str, default: str | None = None) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    return _file_values().get(name) or default
