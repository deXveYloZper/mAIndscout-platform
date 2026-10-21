"""Dates the recruiter tells the desk about a role (owner, 2026-10-21: "the next hackathon is happening on the 21st
and 22nd of November, in London and Germany"): read against the role's own dated events, so a new edition replaces
the passed one. Each date must be quoted from the recruiter's words. No database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from maindscout.intelligence.llm import LLMClient

DATES_PROMPT_VERSION = "2026-10-21.1"
MONTHS = r"jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|june?|july?|aug(ust)?|sep(t|tember)?|oct(ober)?|nov(ember)?|dec(ember)?"
_MENTIONS = re.compile(rf"\b({MONTHS})\b|\b\d{{1,2}}[./-]\d{{1,2}}([./-]\d{{2,4}})?\b|\b\d{{4}}-\d{{2}}-\d{{2}}\b", re.I)

SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["dates"],
    "properties": {"dates": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["event", "replaces", "date", "quote"],
        "properties": {
            "event": {"type": "string", "description": "the event in a few words, e.g. 'Hackathon London'"},
            "replaces": {"type": ["integer", "null"],
                         "description": "the number of the role's listed event this is the new date of (the same event, "
                                        "e.g. the next hackathon in the same city or country), or null for a new event"},
            "date": {"type": "string", "description": "YYYY-MM-DD"},
            "quote": {"type": "string", "description": "the EXACT words of the text that give this date"}}}}}}

SYSTEM = (
    "You read what a recruiter says about the dates of a job's process: interview days, hackathons, assessment days, "
    "a start date, a closing date. For each dated event in the text give: the event in a few words (with its place "
    "when the text gives one); the date as YYYY-MM-DD (when the year is not written, the first such date on or after "
    "today); the exact words of the text that give the date; and which of the role's listed events it is the new date "
    "of (same kind of event; a city and its country count as the same place, e.g. Berlin and Germany), or null. Only "
    "dates written in the text: never invent or guess a date.")


@dataclass
class Dated:
    event: str
    when: str  # YYYY-MM-DD
    replaces: int | None  # index into the events given
    quote: str


@dataclass
class DatesOutcome:
    dates: list[Dated] = field(default_factory=list)
    rejected: list[dict[str, str]] = field(default_factory=list)
    cost: dict[str, Any] = field(default_factory=dict)


def mentions_date(text: str) -> bool:
    """Is there a date in the words at all? Only then is the model asked (most notes have none)."""
    return bool(_MENTIONS.search(text or ""))


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def read(text: str, events: list[tuple[str, str]], today: date, client: LLMClient) -> DatesOutcome:
    """`events`: the role's dated events now, as (label, YYYY-MM-DD)."""
    listed = "\n".join(f"{i}. {label}: {when}" for i, (label, when) in enumerate(events)) or "(none)"
    user = f"Today: {today.isoformat()}\nThe role's listed events:\n{listed}\n\nWhat the recruiter said:\n{text[:4000]}"
    result = client.complete_json(SYSTEM, user, SCHEMA, "process_dates")
    out = DatesOutcome(cost={"model": result.model, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
                             "usd": result.usd})
    said = _norm(text)
    for raw in (result.data or {}).get("dates") or []:
        quote, when, event = (raw.get("quote") or "").strip(), (raw.get("date") or "").strip(), (raw.get("event") or "").strip()
        try:
            day = date.fromisoformat(when)
        except ValueError:
            out.rejected.append({"item": event, "reason": f"not a date: {when}"})
            continue
        if not quote or _norm(quote) not in said:
            out.rejected.append({"item": event, "reason": "the date is not in the words"})
            continue
        if str(day.day) not in quote and day.strftime("%d") not in quote:
            out.rejected.append({"item": event, "reason": "the quote does not give that day"})
            continue
        replaces = raw.get("replaces")
        if not isinstance(replaces, int) or not 0 <= replaces < len(events):
            replaces = None
        out.dates.append(Dated(event or "Date", day.isoformat(), replaces, quote))
    return out
