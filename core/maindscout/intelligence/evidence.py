"""A deeper look at a strong match (owner, 2026-10-17): their public work, to support or discard the desk's opinion.
No database.

"We do need to dig deeper once we believe someone is a strong match ... and look for more evidence to support or
discard that opinion based on their publicly available info" (the owner). Discovery still never names a person; this
check runs only on someone already judged a strong match, and may search their name with their company.

- **Pages:** the links on their own profile (GitHub, their projects), and a web search for their name with their
  current company (LinkedIn left out: the desk has their profile already).
- **Same person:** a page counts only if it is linked from their own profile, or names them in full (first and last
  name as words, close together) together with one of their employers. A namesake never lends evidence.
- **Reading:** one model call over at most four pages, against the role's requirements: what each page shows about
  THEIR work, supporting or weakening the match, each finding quoted exactly. Code checks every quote is on its page,
  and that a skill a finding supports is named in its quote. Nothing about their private life is ever asked or kept.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse, urlunparse

from maindscout.intelligence import spans
from maindscout.intelligence.exa import Found
from maindscout.intelligence.llm import LLMClient
from maindscout.intelligence.triage import canon, supports

READER_VERSION = "evidence-2026-10-17.2"
MAX_PAGES = 4
PAGE_CHARS = 5000
MAX_REQUIREMENTS = 12
# The only reasons a page counts against a match: the opposite of the requirement, never other work.
AGAINST = ("left_the_field", "works_elsewhere_now", "says_otherwise")
# Sites that only copy their profile: the desk has it already (seen on the first real checks, 2026-10-17: Exa's own
# library page of each person came back first, and every "finding" re-read the profile).
PROFILE_COPIES = ("linkedin.com", "exa.ai")
# "Not mentioned" is never evidence against anyone (the first real checks called a missing word "weakens").
_ABSENCE = re.compile(r"\b(no|not|nothing|never)\b[^.]{0,80}\b(mention|mentioned|shown|stated|listed|explicit|evidence|reference)|"
                      r"\bdoes(n't| not) (mention|show|say|list)|\bwithout (any )?mention", re.I)
# Exa writes a blurb about each employer under the person's job ("Tacto is a Software Development company ... has 100-150
# employees (+10% YoY), founded in 2020"): about the company, never their work. Only markers a person never uses of
# themselves ("a software engineer" must still pass).
_COMPANY_BLURB = re.compile(r"\bis an? [^.]{0,80}\b(company|organi[sz]ation|institution)\b|\bhas \d[\d,]*-\d[\d,]* employees|"
                            r"\bemployees \(|\bYoY\b|\bfounded in \d{4}|\bheadquartered in\b|\btotal funding\b|"
                            r"\bfunding rounds?\b|\bannual revenue\b|\bthey offer\b", re.I)
_GITHUB = re.compile(r"https?://(?:www\.)?github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))(?=[)/\s?#]|$)")
_PROJECT = re.compile(r"\[Project Link\]\((https?://[^)\s]+)\)")
NOT_A_USER = {"orgs", "topics", "features", "about", "pricing", "enterprise", "sponsors", "login", "join", "explore"}

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["pages", "findings"],
    "properties": {
        "pages": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["page", "about_person", "why"],
            "properties": {"page": {"type": "integer"}, "about_person": {"type": "boolean"},
                           "why": {"type": "string", "description": "a few words: why it is or is not about this person"}}}},
        "findings": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["page", "requirement", "effect", "weakens_because", "skill_token", "text", "quote"],
            "properties": {
                "page": {"type": "integer"},
                "requirement": {"type": "string", "description": "the requirement's id, e.g. R1"},
                "effect": {"type": "string", "enum": ["supports", "weakens"]},
                "weakens_because": {"type": ["string", "null"], "enum": [*AGAINST, None],
                                    "description": "weakens only: which of the three reasons; null for supports"},
                "skill_token": {"type": ["string", "null"], "description": "for a skill requirement: the lowercase skill the page shows"},
                "text": {"type": "string", "description": "what the page shows, in a few plain words"},
                "quote": {"type": "string", "description": "short EXACT quote from that page"},
            }}},
    },
}

SYSTEM = (
    "You read public web pages for a recruiting desk, to check what the desk believes about ONE person's work "
    "against a role's requirements. First decide, for each page, whether it is about this person (their own profile, "
    "their code, their talk, their article, their team page): a different person with a similar name is not. Then, "
    "only from pages about them, report what a page shows about THEIR OWN work for each requirement listed: "
    "'supports' when it shows they have or do it (a skill they use, work they did). 'weakens' ONLY for one of three "
    "reasons, named in weakens_because: left_the_field (the page shows they no longer do this kind of work, e.g. they "
    "moved into sales or into managing managers), works_elsewhere_now (the page shows they have since moved to another "
    "employer), says_otherwise (they say themselves they do not do or want it). Other work, other projects, other "
    "technologies, another background or a small side project never weaken anything: people do many things. "
    "Something a page does not mention is NEVER a finding: no 'weakens' for absence. A technology merely mentioned "
    "near their name is not their work, and a description of a company (what it does, its size, when it was founded) "
    "is not their work either: never quote one. For a skill requirement give the "
    "skill the page shows as skill_token. Every finding quotes its page exactly and names its requirement. Never "
    "report anything that is not about their work: not their private life, opinions, health, family, politics, "
    "religion, appearance, age or nationality, and nothing about other people. Never guess: no finding is better "
    "than a weak one."
)


@dataclass
class Page:
    url: str
    title: str
    text: str
    from_profile: bool  # linked from their own profile
    published: str | None = None


@dataclass
class Finding:
    page: int
    requirement_id: str
    effect: str  # supports | weakens
    text: str
    quote: str
    skill: str | None = None  # the skill token a supporting finding shows (one of the requirement's alternatives)
    because: str | None = None  # weakens: left_the_field | works_elsewhere_now | says_otherwise


@dataclass
class Reading:
    findings: list[Finding]
    about: dict[int, tuple[bool, str]]  # page -> (about them, why)
    rejected: list[dict[str, str]]
    cost: dict[str, Any] = field(default_factory=dict)


def _plain(text: str) -> str:
    """Lowercase, accents off ("Kämmerling" reads "kammerling")."""
    return "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)).lower()


def profile_copy(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in PROFILE_COPIES)


def profile_links(profile_text: str) -> list[str]:
    """Their GitHub page and their project links, from their own profile. Tracking parameters are dropped."""
    out: list[str] = []
    for m in _GITHUB.finditer(profile_text or ""):
        if m.group(1).lower() not in NOT_A_USER:
            out.append(f"https://github.com/{m.group(1)}")
    for m in _PROJECT.finditer(profile_text or ""):
        u = urlparse(m.group(1))
        if u.hostname and "linkedin.com" not in u.hostname:
            out.append(urlunparse((u.scheme, u.netloc, u.path, "", "", "")))
    return list(dict.fromkeys(out))[:2]


def names_them(text: str, full_name: str) -> bool:
    """Their first and last name as words, within a few words of each other (a middle name may sit between)."""
    parts = [p for p in re.split(r"[\s\-]+", _plain(full_name)) if len(p) > 1]
    if len(parts) < 2:
        return False
    first, last = re.escape(parts[0]), re.escape(parts[-1])
    return bool(re.search(rf"(?<![a-z]){first}(?![a-z])[^\n]{{0,30}}?(?<![a-z]){last}(?![a-z])", _plain(text)))


def same_person(page: Page, full_name: str, employers: list[str]) -> bool:
    if profile_copy(page.url):
        return False  # a copy of the profile the desk already has: nothing new
    if page.from_profile:
        return True
    if not names_them(page.text, full_name):
        return False
    plain = _plain(page.text)
    return any(len(e) >= 3 and re.search(rf"(?<![a-z0-9]){re.escape(_plain(e))}(?![a-z0-9])", plain) for e in employers)


def search_query(full_name: str, company: str | None) -> str:
    return " ".join(f"{full_name} {company or ''}".split())


def read(pages: list[Page], person: str, requirements: list[dict[str, Any]], client: LLMClient) -> Reading:
    """`person`: their name and current role, as the profile says ("Ada Testperson, InSAR Engineer at Orbital").
    `requirements`: [{id, text, strength, token, category}] of the role."""
    pages = pages[:MAX_PAGES]
    reqs = {f"R{i}": r for i, r in enumerate(requirements[:MAX_REQUIREMENTS], 1)}
    if not pages or not reqs:
        return Reading([], {}, [])
    listed = "\n".join(f"{k}: {r['text']} ({r['strength']}{', skill ' + r['token'] if r.get('token') else ''})" for k, r in reqs.items())
    blocks = [f"Page {i}: {p.url}{' (linked from their own profile)' if p.from_profile else ''}\n{p.title}\n\n{p.text[:PAGE_CHARS]}"
              for i, p in enumerate(pages, 1)]
    user = f"Person: {person}\n\nRequirements:\n{listed}\n\n" + "\n\n---\n\n".join(blocks)
    result = client.complete_json(SYSTEM, user, SCHEMA, "evidence_check")
    about: dict[int, tuple[bool, str]] = {}
    for a in result.data.get("pages", []):
        if isinstance(a.get("page"), int) and 1 <= a["page"] <= len(pages):
            about[a["page"] - 1] = (bool(a.get("about_person")), (a.get("why") or "")[:160])
    findings: list[Finding] = []
    rejected: list[dict[str, str]] = []
    for f in result.data.get("findings", []):
        page, req = f.get("page"), reqs.get(f.get("requirement") or "")
        quote, why, skill = f.get("quote") or "", None, None
        if not isinstance(page, int) or not 1 <= page <= len(pages):
            why = "no such page"
        elif req is None:
            why = "no such requirement"
        elif not about.get(page - 1, (False, ""))[0]:
            why = "the page is not about them"
        elif f.get("effect") not in ("supports", "weakens"):
            why = "unknown effect"
        elif spans.locate(pages[page - 1].text[:PAGE_CHARS], quote) is None:
            why = "the quote is not on the page"
        elif _COMPANY_BLURB.search(quote):
            why = "the quote describes a company, not their work"
        elif f["effect"] == "weakens" and _ABSENCE.search(f"{f.get('text') or ''} {quote}"):
            why = "something not mentioned is not evidence against them"
        elif f["effect"] == "weakens" and f.get("weakens_because") not in AGAINST:
            # The second real checks (2026-10-17) called a few Google Apps Script repositories evidence against
            # React, and years at BMW evidence against procurement: other work is not the opposite.
            why = "other work is not evidence against them"
        elif f["effect"] == "supports" and req.get("token"):
            # A skill is supported only when the quote names one of the requirement's alternatives.
            named = [t for t in req["token"].split("/") if t.strip() and supports(t, [], [quote])]
            if not named:
                why = "the quote does not name the skill"
            else:
                wanted = canon((f.get("skill_token") or "").strip())
                skill = next((t for t in named if canon(t) == wanted), named[0])
        if why:
            rejected.append({"finding": (f.get("text") or "")[:80], "reason": why})
            continue
        findings.append(Finding(page - 1, next(k for k, v in reqs.items() if v is req), f["effect"],
                                (f.get("text") or "").strip()[:200], quote.strip()[:400], skill,
                                f.get("weakens_because") if f["effect"] == "weakens" else None))
    # Requirement keys back to the caller's ids.
    for x in findings:
        x.requirement_id = reqs[x.requirement_id]["id"]
    cost = {"model": result.model, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens, "usd": result.usd}
    return Reading(findings, about, rejected, cost)


def outcome(findings: list[Finding], strengths: dict[str, str]) -> str:
    """confirmed | mixed | weakened | nothing_found, from the findings alone (never the model's overall view).
    `strengths`: requirement id -> strength; a confirmation needs support for something that matters."""
    matters = ("must", "deal_breaker", "strong_plus")
    support = any(f.effect == "supports" and strengths.get(f.requirement_id) in matters for f in findings)
    against = any(f.effect == "weakens" for f in findings)
    if support and against:
        return "mixed"
    if against:
        return "weakened"
    return "confirmed" if support else "nothing_found"
