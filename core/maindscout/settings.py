"""Configuration from the environment, falling back to core/.env (git-ignored)."""

from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def env(name: str, default: str | None = None) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            key, _, value = line.strip().partition("=")
            if key == name and value:
                return value
    except OSError:
        pass
    return default
