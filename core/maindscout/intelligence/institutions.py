"""University rank: one targeted web search per institution for its place in the QS World University Rankings. No
database. The owner's decision (2026-10-03): rank is merit evidence and may carry weight; keep it simple.

Kept only if the page was opened by the search, the quote contains the rank, and the quote or page is about QS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from maindscout.intelligence.research import SearchClient, _host, _same_page

INSTITUTION_PROMPT_VERSION = "2026-10-04.1"
RANKING = "QS World University Rankings"

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["identified", "official_name", "country_code", "ranked", "rank", "edition", "source_url", "quote"],
    "properties": {
        "identified": {"type": "boolean", "description": "true only if you are sure which institution this is"},
        "official_name": {"type": ["string", "null"]},
        "country_code": {"type": ["string", "null"], "description": "ISO 3166-1 alpha-2"},
        "ranked": {"type": "boolean", "description": "true if it appears in the latest QS World University Rankings"},
        "rank": {"type": ["string", "null"], "description": "as written, e.g. '42', '=58' or '601-650'"},
        "edition": {"type": ["string", "null"], "description": "the ranking year, e.g. '2026'"},
        "source_url": {"type": ["string", "null"]},
        "quote": {"type": ["string", "null"], "description": "short EXACT quote from that page containing the rank"},
    },
}

SYSTEM = (
    f"You look up ONE university or college for a recruiting desk: its position in the latest {RANKING} (overall, "
    "not by subject). Prefer topuniversities.com. Give the exact URL of the page you read it on and a short EXACT "
    "quote from that page containing the rank. If the institution is not in the ranking, set ranked=false. If you are "
    "not sure which institution is meant, set identified=false. Do not research any person. Never guess."
)


@dataclass
class RankOutcome:
    identified: bool
    official_name: str | None = None
    country: str | None = None
    rank: int | None = None  # best position (601-650 -> 601)
    rank_text: str | None = None
    band: str | None = None  # top_50 | 51_100 | 101_200 | 201_500 | 501_plus | not_ranked
    edition: str | None = None
    source_url: str | None = None
    quote: str | None = None
    rejected: list[str] = field(default_factory=list)
    cost: dict[str, Any] = field(default_factory=dict)


def band_of(rank: int | None) -> str:
    if rank is None:
        return "not_ranked"
    return "top_50" if rank <= 50 else "51_100" if rank <= 100 else "101_200" if rank <= 200 else "201_500" if rank <= 500 else "501_plus"


BAND_WORDS = {"top_50": "top 50", "51_100": "51-100", "101_200": "101-200", "201_500": "201-500", "501_plus": "501+",
              "not_ranked": "not ranked"}


def check(data: dict, visited: list[str]) -> RankOutcome:
    out = RankOutcome(bool(data.get("identified")), data.get("official_name"), (data.get("country_code") or "").upper() or None)
    if not out.identified:
        out.rejected.append("not confidently identified")
        return out
    if not data.get("ranked"):
        out.band = "not_ranked"  # absence is weak evidence: kept as "not ranked", never as a demerit
        return out
    url, quote, rank = data.get("source_url") or "", data.get("quote") or "", data.get("rank") or ""
    first = re.search(r"\d+", rank)
    if not url or not quote or not first:
        out.rejected.append("no source, quote or rank")
    elif not any(_same_page(url, v) for v in visited):
        out.rejected.append(f"source was not opened by the search: {url}")
    elif first.group(0) not in re.findall(r"\d+", quote):
        out.rejected.append("the rank is not in the quote")
    elif "qs" not in (quote + " " + url).lower() and "topuniversities" not in _host(url):
        out.rejected.append("the source is not the QS ranking")
    else:
        out.rank, out.rank_text = int(first.group(0)), rank.strip()
        out.band, out.edition, out.source_url, out.quote = band_of(out.rank), data.get("edition"), url, quote.strip()[:400]
    return out


def research_rank(name: str, client: SearchClient) -> RankOutcome:
    data, visited, cost = client.search_json(SYSTEM, f"Institution as written on a CV: {name}", SCHEMA, "institution_rank")
    out = check(data, visited)
    out.cost = cost
    return out
