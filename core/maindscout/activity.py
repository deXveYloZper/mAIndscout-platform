"""The activity log: what the desk did, in plain words (owner, 2026-10-22: "add logs that are easy to track, what
buttons do, what is happening, so errors are easier to read and unearthed when they happen and our logics are clear
if they work, what is searched, what prompts do we ask xAI").

One row per button pressed, task run, web search sent, model asked, step of the desk's own logic, and error (with
its trace). Read on the desk's Activity page, per role, or with `python -m maindscout activity`.

- Written in its own short transaction: the story of a task that failed and rolled back is still there.
- A model call carrying a person's text (a CV, a call, their career titles) keeps only its size, never the text;
  a call about a role or a company keeps its prompt, so anyone can see what was asked.
- Never breaks the work it describes: a failure to write is swallowed (and logged to the console).
- Kept 30 days.
"""

from __future__ import annotations

import contextvars
import logging
import random
import traceback
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Iterator

log = logging.getLogger(__name__)

KEEP_DAYS = 30
TEXT = 6000  # characters of a prompt or an answer kept
# Model calls whose input is a person's own text: only its size is kept.
PERSONAL = {"cv_extraction", "call_findings", "step_classification", "evidence_check", "draft_message", "core_work_check"}

_context: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar("activity", default={})


@contextmanager
def about(**values: Any) -> Iterator[None]:
    """Everything noted inside belongs to this org, role, task or actor (a task's run, a button's request)."""
    token = _context.set({**_context.get(), **{k: v for k, v in values.items() if v is not None}})
    try:
        yield
    finally:
        _context.reset(token)


def current() -> dict[str, Any]:
    return dict(_context.get())


@lru_cache
def _factory():
    from maindscout.db.session import make_engine, make_session_factory

    return make_session_factory(make_engine())


def _uuid(value: Any) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def cut(text: Any, limit: int = TEXT) -> str:
    s = text if isinstance(text, str) else str(text)
    return s if len(s) <= limit else s[:limit] + f"… ({len(s) - limit} more characters)"


def note(kind: str, summary: str, detail: dict[str, Any] | None = None, level: str = "info", **context: Any) -> None:
    """Write one line. `context` overrides the current org, job, task and actor."""
    from maindscout.settings import env

    if (env("ACTIVITY_LOG", "on") or "on").lower() == "off":
        return
    ctx = {**_context.get(), **{k: v for k, v in context.items() if v is not None}}
    try:
        from maindscout.db.models import DeskLog

        with _factory()() as session:
            session.add(DeskLog(org_id=_uuid(ctx.get("org_id")), job_id=_uuid(ctx.get("job_id")),
                                 task_id=_uuid(ctx.get("task_id")), actor=ctx.get("actor"), kind=kind, level=level,
                                 summary=cut(summary, 500), detail=_plain(detail or {})))
            if random.random() < 0.002:  # now and then, forget what is older than the keep period
                session.execute(DeskLog.__table__.delete().where(
                    DeskLog.at < datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)))
            session.commit()
    except Exception:  # the log must never break the work it describes
        log.warning("activity log not written: %s", summary, exc_info=True)


def error(summary: str, exc: BaseException | None = None, detail: dict[str, Any] | None = None, **context: Any) -> None:
    trace = "".join(traceback.format_exception(exc)) if exc is not None else None
    note("error", summary, {**(detail or {}), **({"error": f"{type(exc).__name__}: {exc}", "trace": cut(trace, 12000)}
                                                 if exc is not None else {})}, level="error", **context)


def step(summary: str, detail: dict[str, Any] | None = None, **context: Any) -> None:
    """One step of the desk's own logic, said plainly ("Search now: no company list yet, building it first")."""
    note("step", summary, detail, **context)


def _plain(value: Any) -> Any:
    """JSON-safe: ids, dates and anything else become text."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain(v) for v in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


# --- clients: every model and web search, observed -----------------------------------------------------------------


class ObservedChat:
    """A chat model client that notes each call: what for, the prompt (unless personal), the answer, the cost."""

    def __init__(self, inner: Any):
        self.inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def complete_json(self, system: str, user: str, schema: dict[str, Any], name: str):
        started = datetime.now(timezone.utc)
        try:
            result = self.inner.complete_json(system, user, schema, name)
        except Exception as exc:
            error(f"Model call failed: {name}", exc, _prompt(name, system, user))
            raise
        ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        answer = None if name in PERSONAL else cut(_json(result.data))
        note("model", f"Asked {result.model}: {name} (${result.usd:.4f}, {ms / 1000:.1f}s)",
             {**_prompt(name, system, user), "answer": answer, "model": result.model, "usd": result.usd,
              "tokens": {"in": result.input_tokens, "out": result.output_tokens}, "ms": ms})
        return result


class ObservedSearch:
    """The web-search model (Grok): the prompt, the pages it opened, what it answered."""

    def __init__(self, inner: Any):
        self.inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def search_json(self, system: str, user: str, schema: dict, name: str):
        started = datetime.now(timezone.utc)
        try:
            data, visited, cost = self.inner.search_json(system, user, schema, name)
        except Exception as exc:
            error(f"Web research failed: {name}", exc, _prompt(name, system, user))
            raise
        ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        usd = float((cost or {}).get("usd") or 0)
        note("model", f"Researched on the web: {name} ({len(visited)} pages, ${usd:.4f}, {ms / 1000:.0f}s)",
             {**_prompt(name, system, user), "answer": cut(_json(data)), "pages": visited[:60], "model": (cost or {}).get("model"),
              "usd": usd, "ms": ms})
        return data, visited, cost


class ObservedExa:
    """Exa: each search's words, kind, place and how many it returned."""

    def __init__(self, inner: Any):
        self.inner = inner

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)

    def call(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._observed("search", body, lambda: self.inner.call(body))

    def contents(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._observed("contents", body, lambda: self.inner.contents(body))

    def _observed(self, endpoint: str, body: dict[str, Any], run) -> dict[str, Any]:
        query = body.get("query") or ", ".join(str(u) for u in (body.get("urls") or body.get("ids") or [])[:5])
        try:
            out = run()
        except Exception as exc:
            error(f"Exa {endpoint} failed: {cut(query, 120)}", exc, {"request": _plain(body)})
            raise
        results = out.get("results") or []
        usd = ((out.get("costDollars") or {}).get("total")) if isinstance(out.get("costDollars"), dict) else None
        where = body.get("userLocation") or ""
        note("search", f"Exa {endpoint}{' (' + body['category'] + ')' if body.get('category') else ''}: "
                       f"“{cut(query, 140)}”{' in ' + where if where else ''} → {len(results)} results",
             {"request": _plain({k: v for k, v in body.items() if k != "contents"}), "results": len(results), "usd": usd,
              "titles": [cut(r.get("title") or r.get("url") or "", 120) for r in results[:15]]})
        return out


def _prompt(name: str, system: str, user: str) -> dict[str, Any]:
    if name in PERSONAL:
        return {"purpose": name, "system": cut(system, 1500), "input": f"(a person's own text, {len(user)} characters, not kept)"}
    return {"purpose": name, "system": cut(system), "input": cut(user)}


def _json(value: Any) -> str:
    import json

    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)
