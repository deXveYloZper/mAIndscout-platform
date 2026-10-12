"""Exa web search for sourcing (docs/next/PLAN.md, phase 1). No database.

Exa's `people` category searches public profiles (LinkedIn and the wider web). Each result comes with its page text
and, at no extra cost, structured data: name, location, work and education history. Only public data is kept, and a
result's photo is never read or stored. The `company` category finds companies for a role's market map.

A search costs about $0.007 for up to 10 results with their text (Exa's figure is recorded per call). Queries name
roles, companies and places, never a person (owner's rule: sourcing finds people, it does not dig on someone).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

EXA_URL = "https://api.exa.ai/search"
CATEGORIES = ("people", "company", "news", "publication", "personal site")
MAX_RESULTS = 25  # Exa allows 100; a run never needs more than this from one query


class ExaError(RuntimeError):
    permanent = False  # the task runner retries network trouble


class ExaKeyMissing(ExaError):
    permanent = True

    def __init__(self) -> None:
        super().__init__("EXA_API_KEY is not set in core/.env")


@dataclass
class Found:
    """One result: a page, its text, and (for a person) the structured profile Exa read from it."""

    url: str
    title: str
    text: str
    person: dict[str, Any] | None = None  # name, location, workHistory, educationHistory
    published: str | None = None


@dataclass
class Results:
    query: str
    category: str
    found: list[Found] = field(default_factory=list)
    usd: float = 0.0


class Caller(Protocol):
    model: str

    def call(self, body: dict[str, Any]) -> dict[str, Any]: ...


class ExaClient:
    """The real API. `call` sends one search request and returns Exa's JSON."""

    model = "exa"

    def __init__(self, key: str | None = None, timeout: int = 60):
        if key is None:
            from maindscout.settings import env

            key = env("EXA_API_KEY")
        if not key:
            raise ExaKeyMissing()
        self._key, self.timeout = key, timeout

    def call(self, body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(EXA_URL, data=json.dumps(body).encode("utf-8"), method="POST",
                                         headers={"x-api-key": self._key, "Content-Type": "application/json"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read())
            except urllib.error.HTTPError as error:
                detail = error.read().decode("utf-8", "replace")[:300]
                if error.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                failure = ExaError(f"Exa search failed ({error.code}): {detail}")
                failure.permanent = error.code in (400, 401, 402, 403)  # a bad request or key will not fix itself
                raise failure from error
            except (urllib.error.URLError, TimeoutError) as error:
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise ExaError(f"Exa could not be reached: {error}") from error
        raise ExaError("Exa could not be reached")


def request(query: str, category: str, *, num_results: int = 10, country: str | None = None,
            text_chars: int = 12000) -> dict[str, Any]:
    """The search body. `country` (ISO code) is Exa's location hint: results lean to it, nothing is excluded by it,
    so the coverage gate still decides who is in the role's countries."""
    if category not in CATEGORIES:
        raise ValueError(f"category must be one of {CATEGORIES}")
    query = " ".join(query.split())
    if not query:
        raise ValueError("an empty query")
    body: dict[str, Any] = {"query": query, "category": category, "numResults": max(1, min(num_results, MAX_RESULTS)),
                            "contents": {"text": {"maxCharacters": text_chars}}}
    if country:
        body["userLocation"] = country.upper()
    return body


def search(caller: Caller, query: str, category: str, *, num_results: int = 10, country: str | None = None,
           text_chars: int = 12000) -> Results:
    body = request(query, category, num_results=num_results, country=country, text_chars=text_chars)
    return parse(caller.call(body), body["query"], category)


def parse(raw: dict[str, Any], query: str, category: str) -> Results:
    out = Results(query, category, usd=float((raw.get("costDollars") or {}).get("total") or 0))
    for item in raw.get("results") or []:
        url = (item.get("url") or "").strip()
        if not url:
            continue
        person = None
        for entity in item.get("entities") or []:
            props = entity.get("properties") or {}
            if entity.get("type") == "person" or "workHistory" in props:
                person = {k: props.get(k) for k in ("name", "firstName", "lastName", "location", "workHistory",
                                                     "educationHistory")}
                break
        out.found.append(Found(url=url, title=(item.get("title") or "").strip(), text=item.get("text") or "",
                               person=person, published=item.get("publishedDate")))
    return out
