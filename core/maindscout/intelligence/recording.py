"""Record model answers once, replay them for free (tests, e2e, the golden eval).

`LLM_REPLAY` picks the mode (default `off`: the real model, nothing recorded):
- `record`: call the real model and save every answer;
- `replay`: answer only from recordings; a request never recorded fails loudly (nothing is spent);
- `auto`: replay when recorded, otherwise call the real model and save the answer.

A recording is keyed by the exact request (instructions, input, model, schema), so a changed prompt or a changed
document is a new request and is never answered with an old reply. Recordings hold real CV content: they live in
`LLM_RECORDINGS` (default `core/.llm-recordings`, git-ignored) and never leave the machine.

Replayed answers carry the recorded token counts and cost, so the cost ledger looks as it did when recorded; nothing
is actually spent.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from maindscout.intelligence.llm import DEFAULT_MODEL, LLMError, LLMResult

MODES = ("off", "record", "replay", "auto")
DEFAULT_FOLDER = Path(__file__).resolve().parents[2] / ".llm-recordings"
_write_lock = threading.Lock()


class NotRecorded(LLMError):
    """Replay asked for an answer that was never recorded."""

    permanent = True  # the task runner does not retry it


def mode() -> str:
    from maindscout.settings import env

    value = (env("LLM_REPLAY", "off") or "off").strip().lower()
    if value not in MODES:
        raise LLMError(f"LLM_REPLAY must be one of {MODES}")
    return value


def folder() -> Path:
    from maindscout.settings import env

    return Path(env("LLM_RECORDINGS") or DEFAULT_FOLDER)


def request_key(kind: str, model: str, system: str, user: str, schema: dict[str, Any], name: str) -> str:
    blob = json.dumps({"kind": kind, "model": model, "system": system, "user": user, "schema": schema, "name": name},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class _Store:
    def __init__(self, root: Path, kind: str, name: str):
        self.dir = root / kind / name

    def path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def load(self, key: str) -> dict[str, Any] | None:
        p = self.path(key)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def save(self, key: str, record: dict[str, Any]) -> None:
        with _write_lock:
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = self.path(key).with_suffix(".tmp")
            tmp.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.path(key))


class RecordingClient:
    """An LLMClient that records or replays `complete_json` (see module doc)."""

    def __init__(self, make_real: Callable[[], Any], how: str, root: Path | None = None, model: str = DEFAULT_MODEL):
        self.make_real, self.how, self.root, self.model = make_real, how, root or folder(), model
        self._real = None

    def _client(self):
        if self._real is None:
            self._real = self.make_real()
            self.model = getattr(self._real, "model", self.model)
        return self._real

    def complete_json(self, system: str, user: str, schema: dict[str, Any], name: str) -> LLMResult:
        key = request_key("chat", self.model, system, user, schema, name)
        store = _Store(self.root, "chat", name)
        if self.how in ("replay", "auto"):
            saved = store.load(key)
            if saved is not None:
                return LLMResult(saved["data"], saved["model"], saved["input_tokens"], saved["output_tokens"], saved["usd"])
            if self.how == "replay":
                raise NotRecorded(f"No recorded answer for this {name} request ({key[:12]}). Record it once with "
                                  "LLM_REPLAY=auto (or record) while model credits are available.")
        result = self._client().complete_json(system, user, schema, name)
        store.save(key, {"name": name, "model": result.model, "data": result.data, "input_tokens": result.input_tokens,
                         "output_tokens": result.output_tokens, "usd": result.usd,
                         "recorded_at": datetime.now(timezone.utc).isoformat()})
        return result


class RecordingSearchClient:
    """The same for web-search calls (`search_json`)."""

    def __init__(self, make_real: Callable[[], Any], how: str, root: Path | None = None, model: str = DEFAULT_MODEL):
        self.make_real, self.how, self.root, self.model = make_real, how, root or folder(), model
        self._real = None

    def _client(self):
        if self._real is None:
            self._real = self.make_real()
            self.model = getattr(self._real, "model", self.model)
        return self._real

    def search_json(self, system: str, user: str, schema: dict, name: str) -> tuple[dict, list[str], dict]:
        key = request_key("search", self.model, system, user, schema, name)
        store = _Store(self.root, "search", name)
        if self.how in ("replay", "auto"):
            saved = store.load(key)
            if saved is not None:
                return saved["data"], saved["urls"], saved["cost"]
            if self.how == "replay":
                raise NotRecorded(f"No recorded answer for this {name} search ({key[:12]}). Record it once with "
                                  "LLM_REPLAY=auto (or record) while model credits are available.")
        data, urls, cost = self._client().search_json(system, user, schema, name)
        store.save(key, {"name": name, "data": data, "urls": urls, "cost": cost,
                         "recorded_at": datetime.now(timezone.utc).isoformat()})
        return data, urls, cost


def wrap_chat(make_real: Callable[[], Any]):
    """The client to use: the real one (mode off), or a recording/replaying one."""
    how = mode()
    return make_real() if how == "off" else RecordingClient(make_real, how)


def wrap_search(make_real: Callable[[], Any]):
    how = mode()
    return make_real() if how == "off" else RecordingSearchClient(make_real, how)
