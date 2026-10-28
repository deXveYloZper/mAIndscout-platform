"""The core-work reader (owner, 2026-10-27: "yes build the reader, test on Ferrari and Bonaventura"): a person's own
words read against a role's confirmed work lines. One model call per person and role. No database.

For each work line the model says shown, partly or not shown, quoting their exact words; for each "not this work"
line, whether that is their main work, some of it, or not shown. Checked by code: every piece of a quote is literally
in their words, and one piece of at least four words is not a job title, a heading or a skills list. Told to the model
as well: a phrase about a quality, an attitude or a wish ("understand my counterpart's needs") is never evidence
(owner: "very vague and we should not include such things"). What the model writes about the person in its own words
is never kept.

It only orders people within a band (`order_key`), never changes a rating: first those whose own words show the
work, then those whose words show nothing either way, then those whose main work is a look-alike. Measured on
Ferrari's CRM role before it was built ([evals](../../../docs/evals/2026-10-27-core-work-reader-ferrari.md)).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from maindscout.intelligence import spans
from maindscout.intelligence.llm import LLMClient

READER_VERSION = "2026-10-27.1"
MIN_QUOTE_WORDS = 4
PROFILE_CHARS, CV_CHARS = 6000, 9000
GROUPS = ("shows", "nothing", "looks_like")

VERDICT = {"type": "string", "enum": ["shown", "partly", "not_shown"]}
MAIN = {"type": "string", "enum": ["main", "some", "no"]}


def _items(verdict: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["number", "verdict", "quote"],
                                       "properties": {"number": {"type": "integer"}, "verdict": verdict, "quote": {"type": "string"}}}}


SCHEMA = {"type": "object", "additionalProperties": False, "required": ["lines", "not_lines", "summary"],
          "properties": {"lines": _items(VERDICT), "not_lines": _items(MAIN), "summary": {"type": "string"}}}

SYSTEM = (
    "You check a person's own words against the work of a role, for a recruiter. For each numbered work line: shown "
    "when their own words say they have done that work; partly when they say they did something close or a part of "
    "it; not_shown when they do not say (absence is not proof they cannot do it). For shown or partly, quote their "
    "EXACT words that describe the work they did, in the language they wrote them: a phrase or sentence saying what "
    "they did. A job title, a heading, a skills list or a single word is never evidence: a profile that shows only "
    "titles shows nothing, not_shown. Nor is a phrase about a quality, an attitude or a wish (\"understand my "
    "counterpart's needs\", \"become a point of reference for him\"): evidence names the work itself, what they did "
    "and with what or for whom. Judge the work, not the words: the same tool, platform or field in a different job is "
    "not this work. Then, for each numbered NOT-this-work line: main when their own words show that is most of their "
    "work; some when they did it among other work; no otherwise. Quote as above, never a title. Last, one sentence "
    "on what their work actually is.")

BOILERPLATE = re.compile(r"\b(is an? [^.]{0,80}company|employees \(|headquartered in|annual revenue|market cap|founded in \d{4})", re.I)
SKILLS_LINE = re.compile(r"(skills|top skills|competenze|competencies)\s*:", re.I)
LIST_SECTIONS = ("skills", "top skills", "languages", "certifications", "licenses & certifications")  # lists, never work


@dataclass
class Verdict:
    line: int  # 1-based, in the order the lines were given
    verdict: str
    quote: str


@dataclass
class Reading:
    work: list[Verdict] = field(default_factory=list)  # only the lines their words show, each with a checked quote
    not_work: list[Verdict] = field(default_factory=list)  # only the look-alikes their words show
    rejected: int = 0  # quotes that failed the checks
    cost: dict[str, Any] = field(default_factory=dict)


def own_words(md: str) -> tuple[str, list[str]]:
    """A public profile's own words for reading (summary, skills, each job; no company boilerplate), and the lines
    that are titles or lists, never evidence: the headline, each job's heading and title, each skills line."""
    keep: list[str] = []
    titles: list[str] = []
    section: str | None = None
    headline_seen = False
    for raw in (md or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# ") and section is None:
            continue  # their name
        if line.startswith("## "):
            section = line[3:].strip().lower()
            continue
        if section is None:
            if not headline_seen:  # the headline under the name
                titles.append(line)
                headline_seen = True
            continue
        if BOILERPLATE.search(line) or section in ("education", "social"):
            continue
        if section == "experience" and line.startswith("### "):
            line = "Company: " + re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line[4:]).strip()
            titles.append(line)  # with one job at a company, its title is on this line ("Analyst at Company")
        elif line.startswith("#### "):
            titles.append(line[5:])
        elif SKILLS_LINE.match(line) or section in LIST_SECTIONS:
            titles.append(line)
        keep.append(line.lstrip("#").strip())
    return "\n".join(keep)[:PROFILE_CHARS], titles


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split()).strip(" .'\"“”")


def evidence(quote: str, text: str, titles: list[str]) -> bool:
    """Every piece of the quote is literally in their words, and one piece of at least four words is not inside a
    title, a heading or a skills list."""
    pieces = [_norm(x) for x in re.split(r"[;\n]|\s[-–]\s|\.\.\.|…", quote or "")]
    pieces = [x for x in pieces if len(x) >= 3]
    if not pieces or any(spans.locate(text, x) is None for x in pieces):
        return False
    heads = [_norm(t) for t in titles]
    return any(len(x.split()) >= MIN_QUOTE_WORDS and not any(x in h for h in heads) for x in pieces)


def user_text(work: list[str], not_work: list[str], text: str) -> str:
    out = "Work of the role:\n" + "\n".join(f"{i}. {w}" for i, w in enumerate(work, 1))
    if not_work:
        out += "\n\nNOT this work:\n" + "\n".join(f"{i}. {w}" for i, w in enumerate(not_work, 1))
    return out + "\n\nTheir own words:\n" + text


def read(work: list[str], not_work: list[str], text: str, titles: list[str], client: LLMClient) -> Reading:
    result = client.complete_json(SYSTEM, user_text(work, not_work, text), SCHEMA, "core_work_check")
    out = Reading(cost={"model": result.model, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
                        "usd": result.usd})
    for key, lines, wanted, target in (("lines", work, ("shown", "partly"), out.work),
                                       ("not_lines", not_work, ("main", "some"), out.not_work)):
        done: set[int] = set()
        for v in result.data.get(key, []):
            n, verdict, quote = v.get("number"), v.get("verdict"), " ".join((v.get("quote") or "").split())
            if not isinstance(n, int) or not 1 <= n <= len(lines) or n in done or verdict not in wanted:
                continue
            done.add(n)
            if evidence(quote, text, titles):
                target.append(Verdict(n, verdict, quote[:300]))
            else:
                out.rejected += 1
    return out


def group(work: list[dict[str, Any]], not_work: list[dict[str, Any]]) -> str:
    """shows: their words show some of the work and no look-alike is their main work; looks_like: a look-alike is their
    main work; nothing: their words show neither."""
    if any(n.get("verdict") == "main" for n in not_work):
        return "looks_like"
    return "shows" if work else "nothing"


def order_key(reading: dict[str, Any] | None) -> tuple[int, int, int]:
    """Within a band: those whose own words show the work first (the more of it, the earlier, its central lines
    counting double), then those whose words show nothing either way (and anyone not read yet), then those whose main
    work is a look-alike. Sorting only: never shown, never stored, never a rating."""
    if not reading or reading.get("group") not in GROUPS:
        return (1, 0, 0)
    shown = sum((2 if w.get("verdict") == "shown" else 1) * (2 if w.get("central") else 1) for w in reading.get("work") or [])
    some = sum(1 for n in reading.get("not") or [] if n.get("verdict") == "some")
    return (GROUPS.index(reading["group"]), -shown, some)
