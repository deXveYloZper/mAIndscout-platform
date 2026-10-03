"""Company research: one targeted web search for a fixed list of facts, then mechanical checks. No database.

The model is told exactly which facts to find (owner's decision: targeted, never open browsing) and must give,
for every fact, the URL it read and a short quote from that page. A fact is kept only if:
- its URL is one the search actually opened or cited, and
- its typed value is written in its quote (a founding year, a funding amount and date, a headcount number).
Research is about companies only: no person's name or job ever goes into the search.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlparse

from maindscout.intelligence.llm import DEFAULT_MODEL, TICKS_PER_USD, LLMError, load_env_key

RESEARCH_PROMPT_VERSION = "2026-10-03.2"
RESPONSES_URL = "https://api.x.ai/v1/responses"
REGISTRY_HOSTS = ("company-information.service.gov.uk", "find-and-update.company-information.service.gov.uk",
                  "opencorporates.com", "handelsregister.de", "unternehmensregister.de", "northdata.com", "ajpes.si")


def _fact(value_schema: dict) -> dict:
    return {"type": ["object", "null"], "additionalProperties": False, "required": ["value", "source_url", "quote", "as_of"],
            "properties": {"value": value_schema, "source_url": {"type": "string"}, "quote": {"type": "string"},
                           "as_of": {"type": ["string", "null"], "description": "date the page states for this fact, if any"}}}


FUNDING_STAGES = ["pre_seed", "seed", "series_a", "series_b", "series_c", "series_d", "series_e_plus", "growth", "debt",
                  "grant", "ipo", "acquisition", "other"]
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["identified", "website", "domains", "company_type", "founded", "funding_rounds", "headcount", "status", "hq"],
    "properties": {
        "identified": {"type": "boolean", "description": "true only if you are confident this is the company described"},
        "website": {"type": ["string", "null"]},
        "domains": _fact({"type": "array", "items": {"type": "string"}}),
        "company_type": _fact({"type": "string", "enum": ["product", "consultancy", "outsourcing", "agency", "public_sector", "non_profit", "other"]}),
        "founded": _fact({"type": "string", "description": "YYYY, YYYY-MM or YYYY-MM-DD"}),
        "funding_rounds": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["stage", "date", "amount", "investors", "source_url", "quote"],
            "properties": {"stage": {"type": "string", "enum": FUNDING_STAGES}, "date": {"type": ["string", "null"]},
                           "amount": {"type": ["string", "null"], "description": "as written, e.g. $13M or EUR 1.8 million"},
                           "investors": {"type": "array", "items": {"type": "string"}},
                           "source_url": {"type": "string"}, "quote": {"type": "string"}}}},
        "headcount": _fact({"type": "string", "description": "as written, e.g. '51-200 employees' or '42 employees'"}),
        "status": _fact({"type": "string", "enum": ["active", "acquired", "merged", "shut_down", "public"]}),
        "hq": _fact({"type": "string", "description": "city and country"}),
    },
}

SYSTEM = (
    "You research ONE company for a recruiting desk. Find ONLY these facts and nothing else: industry domains "
    "(e.g. fintech, procurement, e-commerce, aerospace); company type (product company, consultancy, outsourcing "
    "provider, agency, public sector, non-profit: what it sells, never its legal form); founding or incorporation date; funding rounds (stage, date, amount, "
    "lead investors; only real rounds, never a running total); headcount and the date it refers to; status (active, acquired, merged, shut down, public, with "
    "date; the quote must state the status itself); headquarters. Prefer, in order: official company registries, the company's own website, reputable startup "
    "databases (Crunchbase, Dealroom, PitchBook, Tracxn), and reputable press. Do not research any person. Do not research technologies, tools or tech stack; domains are industries the "
    "company serves, never technologies. "
    "For every fact give the exact URL of the page you read it on and a short EXACT quote from that page that contains "
    "the fact. If you cannot confirm that the company you found is the one described, set identified=false. "
    "If a fact is not found, use null (or an empty list). Never guess or estimate."
)


@dataclass
class Fact:
    kind: str  # domains | company_type | founded | funding_round | headcount | status | hq
    value: Any
    source_url: str
    quote: str
    as_of: str | None = None
    registry: bool = False  # the source is an official registry


@dataclass
class ResearchOutcome:
    identified: bool
    website: str | None
    facts: list[Fact] = field(default_factory=list)
    rejected: list[dict[str, str]] = field(default_factory=list)
    visited: list[str] = field(default_factory=list)
    cost: dict[str, Any] = field(default_factory=dict)


class SearchClient(Protocol):
    model: str

    def search_json(self, system: str, user: str, schema: dict, name: str) -> tuple[dict, list[str], dict]:
        """Returns (data, urls the search opened or cited, cost)."""


class XaiSearchClient:
    """xAI Responses API with the server-side web_search tool and strict JSON output."""

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL, max_tool_calls: int = 4, timeout: float = 120):
        self.api_key = api_key or load_env_key()
        if not self.api_key:
            raise LLMError("XAI_API_KEY is not set")
        self.model, self.max_tool_calls, self.timeout = model, max_tool_calls, timeout

    def search_json(self, system: str, user: str, schema: dict, name: str) -> tuple[dict, list[str], dict]:
        body = json.dumps({
            "model": self.model, "max_tool_calls": self.max_tool_calls,
            "input": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "tools": [{"type": "web_search"}],
            "text": {"format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}},
        }).encode()
        request = urllib.request.Request(RESPONSES_URL, body, {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        payload, last = None, None
        for attempt in range(2):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.load(response)
                break
            except urllib.error.HTTPError as error:
                last = error
                if error.code not in (429, 500, 502, 503, 504):
                    raise LLMError(f"xAI returned HTTP {error.code}") from error
            except (urllib.error.URLError, TimeoutError) as error:
                last = error
            time.sleep(3 * (attempt + 1))
        if payload is None:
            raise LLMError(f"xAI search failed: {last}")
        text, urls = None, []
        for item in payload.get("output", []):
            if item.get("type") == "web_search_call":
                url = (item.get("action") or {}).get("url")
                if url:
                    urls.append(url)
            elif item.get("type") == "message":
                for part in item.get("content", []):
                    if part.get("type") == "output_text":
                        text = part.get("text")
                    for ann in part.get("annotations") or []:
                        if ann.get("url"):
                            urls.append(ann["url"])
        if text is None:
            raise LLMError("xAI search returned no answer")
        usage = payload.get("usage", {})
        cost = {"model": payload.get("model", self.model), "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0), "sources": usage.get("num_server_side_tools_used", 0),
                "usd": usage.get("cost_in_usd_ticks", 0) / TICKS_PER_USD}
        try:
            return json.loads(text), urls, cost
        except json.JSONDecodeError as error:
            raise LLMError("xAI search returned unreadable output") from error


# --- mechanical checks ---------------------------------------------------------------------------


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _same_page(a: str, b: str) -> bool:
    pa, pb = urlparse(a), urlparse(b)
    return _host(a) == _host(b) and pa.path.rstrip("/") == pb.path.rstrip("/")


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)?", text.replace(",", "")))


def amount_supported(amount: str, quote: str) -> bool:
    """The amount's number must be in the quote ($13M ~ "13 million"; "$170M" is not "$160 million")."""
    wanted = _numbers(amount)
    return bool(wanted) and wanted <= _numbers(quote)


def year_supported(value: str | None, quote: str) -> bool:
    year = re.match(r"(\d{4})", value or "")
    return bool(year) and year.group(1) in quote


# Words a quote must contain for a status to be supported by it.
STATUS_WORDS = {
    "active": r"activ|private|operating|trading|live\b",
    "public": r"public|listed|nasdaq|nyse|tsx|\blse\b|stock exchange|\bipo\b",
    "acquired": r"acqui|bought|purchas|übernomm|taken over|merger",
    "merged": r"merg",
    "shut_down": r"shut|defunct|out of business|dissol|liquidat|clos|wind|wound|discontinu|ceased|insolven|administration|bankrupt",
}
# A quote that only gives the legal form says nothing about what the company does.
LEGAL_FORM_ONLY = re.compile(
    r"^\W*(company\s+)?(type\W*)?(privately held|private|public company|public|partnership|sole proprietorship|self-employed|"
    r"(private\s+)?limited( liability)?( company)?|ltd|gmbh|llc|inc\.?|plc|corporation|educational|government agency|nonprofit)\W*$", re.I)
STAGE_WORDS = {"pre_seed": r"pre[- ]?seed", "seed": r"(?<!pre-)(?<!pre )\bseed\b", "series_a": r"series a\b", "series_b": r"series b\b",
               "series_c": r"series c\b", "series_d": r"series d\b", "series_e_plus": r"series [e-k]\b", "ipo": r"\bipo\b",
               "grant": r"\bgrant\b", "debt": r"\bdebt\b"}


def fact_problem(kind: str, value: Any, quote: str, url: str = "") -> str | None:
    """Why the quote does not support the typed value, or None. Used on new research and to re-check stored facts."""
    if kind == "founded" and not year_supported(value, quote):
        return "founding year is not in the quote"
    if kind == "headcount" and not (_numbers(str(value)) and _numbers(str(value)) <= _numbers(quote)):
        return "headcount number is not in the quote"
    if kind == "status" and not re.search(STATUS_WORDS.get(value, r"$^"), quote.lower()):
        return f"the quote does not say the company is {value}"
    if kind == "company_type" and LEGAL_FORM_ONLY.match(re.sub(r"\s+", " ", quote)):
        return "the quote gives a legal form, not what the company does"
    if kind == "funding_round":
        if not value.get("amount") and not value.get("date"):
            return "a round needs a date or an amount (a running total is not a round)"
        if value.get("amount") and not amount_supported(value["amount"], quote):
            return "funding amount is not in the quote"
        if value.get("date") and not (year_supported(value["date"], quote) or year_supported(value["date"], urlparse(url).path)):
            return "funding year is not in the quote or the address"
        named = {stage for stage, rx in STAGE_WORDS.items() if re.search(rx, quote.lower())}
        if named and value.get("stage") not in named:
            return f"the quote names {', '.join(sorted(named))}, not {value.get('stage')}"
    return None


def check(data: dict, visited: list[str]) -> tuple[list[Fact], list[dict[str, str]]]:
    """Keep only facts with a real source and a quote that contains the typed value."""
    kept, rejected = [], []

    def accept(kind: str, value: Any, url: str, quote: str, as_of: str | None) -> None:
        problem = None if not url or not quote.strip() else fact_problem(kind, value, quote, url)
        if not url or not quote.strip():
            rejected.append({"fact": kind, "reason": "no source or no quote"})
        elif not any(_same_page(url, v) for v in visited):
            rejected.append({"fact": kind, "reason": f"source was not opened by the search: {url}"})
        elif problem:
            rejected.append({"fact": kind, "reason": problem})
        else:
            kept.append(Fact(kind, value, url, quote.strip()[:500], as_of, registry=_host(url).endswith(REGISTRY_HOSTS)))

    for kind in ("domains", "company_type", "founded", "headcount", "status", "hq"):
        f = data.get(kind)
        if f and f.get("value"):
            accept(kind, f["value"], f["source_url"], f["quote"], f.get("as_of"))
    for r in data.get("funding_rounds") or []:
        accept("funding_round", {k: r.get(k) for k in ("stage", "date", "amount", "investors")}, r["source_url"], r["quote"], r.get("date"))
    return kept, rejected


def research_company(name: str, context: str, client: SearchClient) -> ResearchOutcome:
    """`context` describes the company only (place, industry hints, website): never a person."""
    data, visited, cost = client.search_json(SYSTEM, f"Company: {name}\nWhat we know about it: {context or 'nothing more'}", SCHEMA, "company_facts")
    if not data.get("identified"):
        return ResearchOutcome(False, None, [], [{"fact": "company", "reason": "not confidently identified"}], visited, cost)
    facts, rejected = check(data, visited)
    return ResearchOutcome(True, data.get("website"), facts, rejected, visited, cost)
