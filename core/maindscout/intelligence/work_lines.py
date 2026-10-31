"""A role's work, line by line, for the core-work reader (owner, 2026-10-27: "yes build the reader"). One model call per
role, from the role's own material: the ad, the role brief and the requirements. No database.

- **Work lines** (four to six): each one thing the hire will actually do, in plain words; the ones that make this job
  what it is are marked central.
- **Not this work** (two to four): work that shares the role's words (its tools, its platform, its field) and so
  looks like it to a keyword search, but is a different job done by different people. For a CRM platform role:
  running CRM email campaigns; configuring the platform from IT.

The desk proposes them; a person confirms or changes them before any reading uses them (a model's guesses at the
look-alikes change from run to run: measured on Ferrari, 2026-10-27). Never a personal quality, a requirement such
as years or a degree, or a person's name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from maindscout.intelligence.hiring import NOT_CRITERIA
from maindscout.intelligence.llm import LLMClient

LINES_PROMPT_VERSION = "2026-10-27.1"
MAX_WORK, MAX_NOT = 6, 4
MIN_WORDS, MAX_CHARS = 3, 240

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["lines", "not_lines"],
    "properties": {
        "lines": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["line", "central"],
            "properties": {"line": {"type": "string"}, "central": {"type": "boolean"}}}},
        "not_lines": {"type": "array", "items": {"type": "string"}},
    },
}

SYSTEM = (
    "You write the core work of a role for a recruiter: four to six lines, each one thing the person will actually do "
    "in this job, in plain words, from the ad, the role brief and the recruiter's notes. The work itself: never a "
    "personal quality (communication, passion), never a requirement like years or a degree. Mark central the lines "
    "that make this job what it is, as opposed to work any similar job has. Then two to four lines of NOT this work: "
    "work that shares this job's words (its tools, its platform, its field) and so looks like it to a keyword search, "
    "but is a different job, done by different people. Plain words, from the role's own material, each one thing a "
    "person might do all day. Never a person's name.")


@dataclass
class Line:
    kind: str  # "work" | "not"
    words: str
    central: bool | None = None


@dataclass
class Lines:
    lines: list[Line]
    rejected: list[dict[str, str]] = field(default_factory=list)
    cost: dict[str, Any] = field(default_factory=dict)

    @property
    def work(self) -> list[Line]:
        return [x for x in self.lines if x.kind == "work"]

    @property
    def not_work(self) -> list[Line]:
        return [x for x in self.lines if x.kind == "not"]


def user_text(title: str, company: str | None, brief: list[dict[str, Any]], requirements: list[dict[str, Any]], ad: str) -> str:
    """The role's own material: its title, the brief's lines, the requirements and the ad."""
    out = [f"Title: {title}" + (f", {company}" if company else "")]
    if brief:
        out.append("Role brief:\n" + "\n".join(f"- {b.get('facet')}: {b.get('words')}" for b in brief))
    if requirements:
        out.append("Requirements and the recruiter's notes:\n"
                   + "\n".join(f"- ({r.get('strength')}) {r.get('text_raw')}" for r in requirements))
    if ad:
        out.append(f"The ad:\n{ad[:6000]}")
    return "\n\n".join(out)


def clean(words: str) -> str:
    return " ".join((words or "").split()).strip(" .;")[:MAX_CHARS]


def read(title: str, company: str | None, brief: list[dict[str, Any]], requirements: list[dict[str, Any]], ad: str,
         client: LLMClient) -> Lines:
    result = client.complete_json(SYSTEM, user_text(title, company, brief, requirements, ad), SCHEMA, "core_work_lines")
    seen: set[str] = set()
    out: list[Line] = []
    rejected: list[dict[str, str]] = []
    raw = [("work", x.get("line"), bool(x.get("central"))) for x in result.data.get("lines", [])]
    raw += [("not", x, None) for x in result.data.get("not_lines", [])]
    for kind, words, central in raw:
        words = clean(words if isinstance(words, str) else "")
        if len(words.split()) < MIN_WORDS:
            rejected.append({"line": words, "reason": "too short to be one thing a person does"})
        elif NOT_CRITERIA.search(words):
            rejected.append({"line": words, "reason": "personality, culture or fit is never a line of the work"})
        elif words.lower() in seen:
            rejected.append({"line": words, "reason": "said twice"})
        elif sum(1 for x in out if x.kind == kind) >= (MAX_WORK if kind == "work" else MAX_NOT):
            rejected.append({"line": words, "reason": f"at most {MAX_WORK} work lines and {MAX_NOT} not-this-work lines"})
        else:
            seen.add(words.lower())
            out.append(Line(kind, words, central))
    cost = {"model": result.model, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens, "usd": result.usd}
    return Lines(out, rejected, cost)


# --- the role's own titles (owner, 2026-10-30: "we cannot hard code every job family there is ... why our platform
# doesn't generate this itself, when it understands the company and the role?") ------------------------------------
# One more call after the lines: the titles people doing this work carry, the titles of its look-alikes, and the work
# in a word for one broad search at a small company. They replace the shared family table's titles ("embedded software
# engineer" for an avionics electronics role, 2026-10-30), and a person confirms them with the lines.
TITLES_PROMPT_VERSION = "2026-10-30.1"
MAX_TITLES, MAX_LOOK_ALIKES, MAX_TITLE_WORDS, MAX_WORD_WORDS = 8, 5, 8, 4
SENIORITY = re.compile(r"^(senior|sr\.?|staff|junior|jr\.?|lead|principal)\s+", re.I)

TITLES_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["titles", "look_alike_titles", "word"],
    "properties": {"titles": {"type": "array", "items": {"type": "string"}},
                   "look_alike_titles": {"type": "array", "items": {"type": "string"}},
                   "word": {"type": "string"}},
}

TITLES_SYSTEM = (
    "You write, for a recruiter, the job titles under which people who do this role's work appear on their public "
    "profiles, so a search finds them and a person can be recognised by a title. From the role's own material: its ad, "
    "brief, lines of work and, when given, the titles of the client's own people in this work. titles: four to eight "
    "titles people doing exactly this work carry, the most common first, without seniority words (senior, staff, lead, "
    "junior) and without company names; add the usual titles in the languages of the countries where people must live "
    "when they differ from English. look_alike_titles: two to five titles of jobs that share this role's words but are "
    "different work done by different people. word: the work itself in one to three words, as people write it on a "
    "profile, for one broad search at a small company. Never a person's name.")


@dataclass
class Titles:
    titles: list[str]
    look_alikes: list[str]
    word: str | None
    rejected: list[dict[str, str]] = field(default_factory=list)
    cost: dict[str, Any] = field(default_factory=dict)


def clean_title(words: str) -> str:
    """A title as a search sends it: one line, no seniority word in front ("Senior GNC Engineer" -> "GNC Engineer")."""
    text = " ".join((words or "").split()).strip(" .;,")
    while SENIORITY.match(text) and len(text.split()) > 2:
        text = SENIORITY.sub("", text, count=1)
    return text[:80]


def titles_text(title: str, company: str | None, brief: list[dict[str, Any]], requirements: list[dict[str, Any]], ad: str,
                lines: list[Line], countries: list[str], own_titles: list[str]) -> str:
    out = [user_text(title, company, brief, requirements, ad)]
    if lines:
        out.append("Lines of work:\n" + "\n".join(f"- ({'not this work' if x.kind == 'not' else 'work'}) {x.words}" for x in lines))
    if countries:
        out.append("People must live in: " + ", ".join(countries))
    if own_titles:
        out.append("Titles of the client's own people in this work: " + "; ".join(own_titles[:12]))
    return "\n\n".join(out)


def read_titles(title: str, company: str | None, brief: list[dict[str, Any]], requirements: list[dict[str, Any]], ad: str,
                lines: list[Line], countries: list[str], own_titles: list[str], client: LLMClient) -> Titles:
    result = client.complete_json(TITLES_SYSTEM, titles_text(title, company, brief, requirements, ad, lines, countries, own_titles),
                                  TITLES_SCHEMA, "role_titles")
    rejected: list[dict[str, str]] = []

    def keep(raw: Any, most: int, limit: int, seen: set[str]) -> list[str]:
        out: list[str] = []
        for x in raw if isinstance(raw, list) else []:
            words = clean_title(x if isinstance(x, str) else "")
            if not words or len(words.split()) > most:
                rejected.append({"title": words, "reason": f"a title in one to {most} words"})
            elif NOT_CRITERIA.search(words):
                rejected.append({"title": words, "reason": "personality, culture or fit is never a title"})
            elif words.lower() in seen:
                continue
            elif len(out) < limit:
                seen.add(words.lower())
                out.append(words)
        return out

    seen: set[str] = set()
    titles = keep(result.data.get("titles"), MAX_TITLE_WORDS, MAX_TITLES, seen)
    look_alikes = keep(result.data.get("look_alike_titles"), MAX_TITLE_WORDS, MAX_LOOK_ALIKES, seen)  # never one of its own
    word = keep([result.data.get("word")], MAX_WORD_WORDS, 1, set())
    cost = {"model": result.model, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens, "usd": result.usd}
    return Titles(titles, look_alikes, word[0] if word else None, rejected, cost)
