"""Exa web search for sourcing (docs/next/PLAN.md, phase 1). No database.

Exa's `people` category searches public profiles (LinkedIn and the wider web). Each result comes with its page text
and, at no extra cost, structured data: name, location, work and education history. Only public data is kept, and a
result's photo is never read or stored. The `company` category finds companies for a role's market map; `news`, with a
start date, finds recent news about companies for the talent-release radar.

A search costs about $0.007 for up to 10 results with their text (Exa's figure is recorded per call). Queries name
roles, companies and places, never a person (owner's rule: sourcing finds people, it does not dig on someone).

Phase 1b: `fetch` reads pages by address or Exa id (`/contents`, about $0.001 a page): a company's Exa profile costs a
tenth of a cent. A company profile lists executives and emails: those lines are removed before anything is kept,
recordings included (`clean`). (Exa's find-similar matched companies on their names in a test, so peers come from
descriptive company searches instead: `strategy.peer_queries`.)
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

from maindscout.intelligence.llm import NETWORK_ERRORS

EXA_URL = "https://api.exa.ai/search"
CONTENTS_URL = "https://api.exa.ai/contents"
MAX_FETCH = 100  # Exa reads at most 100 pages per /contents call
COMPANY_KEYS = ("name", "foundedYear", "description", "workforce", "headquarters", "financials")  # never `research`
# (it lists researchers by name)
CATEGORIES = ("people", "company", "news", "publication", "personal site")
MAX_RESULTS = 100  # Exa's own limit; a search's size is chosen by its caller (strategy.results_for)
PERSON_KEYS = ("name", "firstName", "lastName", "location", "workHistory", "educationHistory")  # all we keep of a profile


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
    summary: Any = None  # Exa's structured summary, when asked for (news: the companies an article is about)
    entity_id: str | None = None  # Exa's id for the person or company (a company's is the same in work histories)
    company: dict[str, Any] | None = None  # a company's structured data (COMPANY_KEYS)


@dataclass
class Results:
    query: str
    category: str
    found: list[Found] = field(default_factory=list)
    usd: float = 0.0


class Caller(Protocol):
    model: str

    def call(self, body: dict[str, Any]) -> dict[str, Any]: ...

    def contents(self, body: dict[str, Any]) -> dict[str, Any]: ...


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
        return self._post(EXA_URL, body)

    def contents(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post(CONTENTS_URL, body)

    def _post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST",
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
            except NETWORK_ERRORS as error:
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise ExaError(f"Exa could not be reached: {error}") from error
        raise ExaError("Exa could not be reached")


def request(query: str, category: str | None, *, num_results: int = 10, country: str | None = None,
            text_chars: int = 12000, since: str | None = None, summary: dict[str, Any] | None = None,
            exclude_domains: list[str] | None = None) -> dict[str, Any]:
    """The search body. `category` None searches the whole web (a company's adverts, a person's public work for an
    evidence check). `country` (ISO code) is Exa's location hint: results lean to it, nothing is excluded by it,
    so the coverage gate still decides who is in the role's countries. `since` (YYYY-MM-DD) keeps pages published
    from that day; `summary` ({query, schema}) asks Exa for a structured summary of each page; `exclude_domains`
    leaves sites out (an evidence check already has the person's LinkedIn page)."""
    if category is not None and category not in CATEGORIES:
        raise ValueError(f"category must be one of {CATEGORIES} or None")
    query = " ".join(query.split())
    if not query:
        raise ValueError("an empty query")
    body: dict[str, Any] = {"query": query, "numResults": max(1, min(num_results, MAX_RESULTS)),
                            "contents": {"text": {"maxCharacters": text_chars}}}
    if category is not None:
        body["category"] = category
    if exclude_domains:
        body["excludeDomains"] = list(exclude_domains)
    if country:
        body["userLocation"] = country.upper()
    if since:
        body["startPublishedDate"] = f"{since}T00:00:00.000Z"
    if summary:
        body["contents"]["summary"] = summary
    return body


def fetch(caller: Caller, urls: list[str], text_chars: int = 8000) -> Results:
    """Pages by address or Exa id (a company's profile: `https://exa.ai/library/organization/...`), at most 100."""
    urls = list(dict.fromkeys(u for u in urls if u))[:MAX_FETCH]
    if not urls:
        return Results("", "contents")
    return parse(caller.contents({"urls": urls, "text": {"maxCharacters": text_chars}}), "", "contents")


def search(caller: Caller, query: str, category: str | None, *, num_results: int = 10, country: str | None = None,
           text_chars: int = 12000, since: str | None = None, summary: dict[str, Any] | None = None,
           exclude_domains: list[str] | None = None) -> Results:
    body = request(query, category, num_results=num_results, country=country, text_chars=text_chars, since=since,
                   summary=summary, exclude_domains=exclude_domains)
    return parse(caller.call(body), body["query"], category or "web")


def _summary(value: Any) -> Any:
    """Exa returns a structured summary as JSON text; anything unreadable is dropped."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value if isinstance(value, dict) else None


def parse(raw: dict[str, Any], query: str, category: str) -> Results:
    out = Results(query, category, usd=float((raw.get("costDollars") or {}).get("total") or 0))
    for item in raw.get("results") or []:
        url = (item.get("url") or "").strip()
        if not url:
            continue
        person = company = entity_id = None
        for entity in item.get("entities") or []:
            props = entity.get("properties") or {}
            if entity.get("type") == "person" or "workHistory" in props:
                person, entity_id = {k: props.get(k) for k in PERSON_KEYS}, entity.get("id")
                break
            if entity.get("type") == "company":
                company, entity_id = {k: props.get(k) for k in COMPANY_KEYS}, entity.get("id")
                break
        out.found.append(Found(url=url, title=(item.get("title") or "").strip(), text=clean(item.get("text") or ""),
                               person=person, published=item.get("publishedDate"), summary=_summary(item.get("summary")),
                               entity_id=entity_id, company=company))
    return out


_DROP_BLOCK = re.compile(r"^\s*-\s*(key executives|executives|leadership|founders)\s*:\s*$", re.I)
_DROP_LINE = re.compile(r"^\s*-\s*(emails?|phones?|phone numbers?|key executives|linkedin followers)\s*:", re.I)
_DROP_SECTION = re.compile(r"^##\s*(reviews|people|team|employees|leadership)\b", re.I)


def clean(text: str) -> str:
    """A company profile without the parts about people: executives (a list of names and roles), emails, phones,
    employee reviews. Everything else is kept as written."""
    if "## " not in text:
        return text
    out: list[str] = []
    skip_indent: int | None = None
    in_dropped_section = False
    for line in text.split("\n"):
        if line.startswith("## "):
            in_dropped_section = bool(_DROP_SECTION.match(line))
            skip_indent = None
        if in_dropped_section:
            continue
        indent = len(line) - len(line.lstrip())
        if skip_indent is not None:
            if line.strip() and indent > skip_indent:
                continue
            skip_indent = None
        if _DROP_BLOCK.match(line):
            skip_indent = indent
            continue
        if _DROP_LINE.match(line):
            continue
        out.append(line)
    return "\n".join(out)


def slim(raw: dict[str, Any]) -> dict[str, Any]:
    """Only what `parse` reads, for a recording: never a photo's address, never the people parts of a company page."""
    results = []
    for item in raw.get("results") or []:
        entities = []
        for e in item.get("entities") or []:
            keep = COMPANY_KEYS if e.get("type") == "company" else PERSON_KEYS
            entities.append({"id": e.get("id"), "type": e.get("type"),
                             "properties": {k: v for k, v in (e.get("properties") or {}).items() if k in keep}})
        kept = {k: item[k] for k in ("url", "title", "text", "publishedDate", "summary") if k in item}
        if "text" in kept:
            kept["text"] = clean(kept["text"] or "")
        results.append(kept | {"entities": entities})
    return {"results": results, "costDollars": raw.get("costDollars") or {}}
