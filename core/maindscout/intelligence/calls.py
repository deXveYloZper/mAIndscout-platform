"""Calls: what one call transcript says about the candidate, read once. No database.

One model call per transcript. It is given what the desk already knows (facts, open Brief questions, preferences)
and says, line by line: which questions were answered, which facts were confirmed, corrected or disputed, which new
facts came up, what the candidate wants next, and what is still worth asking. Every line quotes the candidate's own
words (checked: the quote is in the transcript, in a line the candidate said, and typed values are in the quote).
Nothing about other people on the call; never personality, culture or fit (owner's rule).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from maindscout.domain.profile import LEVELS, ROLE_FAMILIES
from maindscout.ingestion import transcript
from maindscout.intelligence.hiring import EMPLOYER_KINDS, NOT_CRITERIA
from maindscout.intelligence.llm import LLMClient
from maindscout.intelligence.spans import locate

CALLS_PROMPT_VERSION = "2026-10-06.1"
KINDS = ["brief_answer", "confirm", "correct", "dispute", "new_fact", "preference", "ask"]
FACT_TYPES = ["skill", "location", "contact", "career_step"]
CONTACT_KINDS = ["email", "phone", "linkedin"]
FACETS = ["company_size", "employer_kind", "setting", "places", "work", "employment"]
SETTINGS = ["onsite", "hybrid", "remote"]
EMPLOYMENT = ["permanent", "contract"]
OUTCOMES = ["confirmed", "not_met", "noted"]

_S = {"type": ["string", "null"]}
SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["candidate_speaker", "findings"],
    "properties": {
        "candidate_speaker": {"type": ["string", "null"], "description": "the speaker label the candidate has in the transcript"},
        "findings": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["kind", "ref", "outcome", "text", "quote", "fact_type", "value", "company", "title", "start_year",
                         "end_year", "contact_kind", "facet", "strength", "min", "max", "want", "avoid", "level"],
            "properties": {
                "kind": {"type": "string", "enum": KINDS},
                "ref": {**_S, "description": "B<n> for a question answered, F<n> for a fact confirmed, corrected or disputed"},
                "outcome": {"type": ["string", "null"], "enum": OUTCOMES + [None]},
                "text": {"type": "string", "description": "what they said, in a few plain words"},
                "quote": {"type": "string", "description": "short EXACT quote of the candidate's own words"},
                "fact_type": {"type": ["string", "null"], "enum": FACT_TYPES + [None]},
                "value": {**_S, "description": "skill, place, contact value, or the corrected value"},
                "company": _S, "title": _S,
                "start_year": {"type": ["integer", "null"]}, "end_year": {"type": ["integer", "null"]},
                "contact_kind": {"type": ["string", "null"], "enum": CONTACT_KINDS + [None]},
                "facet": {"type": ["string", "null"], "enum": FACETS + [None]},
                "strength": {"type": ["string", "null"], "enum": ["must", "prefer", None]},
                "min": {"type": ["integer", "null"]}, "max": {"type": ["integer", "null"]},
                "want": {"type": "array", "items": {"type": "string"}},
                "avoid": {"type": "array", "items": {"type": "string"}},
                "level": {"type": ["string", "null"], "enum": LEVELS + [None]},
            }}},
    },
}

SYSTEM = (
    "You read the transcript of a recruiter's call with a candidate, for the recruiting desk. You are given what the "
    "desk already knows: FACTS (F1, F2, ...), open QUESTIONS (B1, B2, ...) and known PREFERENCES. Report only what the "
    "CANDIDATE said about themselves, one finding per point:\n"
    "- brief_answer: a question Bn was answered. outcome confirmed (yes / meets it), not_met (no / does not meet it) or "
    "noted (an answer that is neither).\n"
    "- confirm: they confirmed fact Fn. correct: they said fact Fn is different; give the new value (and fact_type). "
    "dispute: they said fact Fn is wrong, with no new value.\n"
    "- new_fact: a fact not in FACTS. fact_type skill (value = the skill), location (value = where they live now), "
    "contact (contact_kind and value), career_step (company, title, start_year, end_year if said).\n"
    "- preference: what they want in their next job. facet company_size (min / max people), employer_kind (want / avoid "
    "from: " + ", ".join(EMPLOYER_KINDS) + "), setting (want from: onsite, hybrid, remote), places (want / avoid as ISO "
    "country codes), work (want / avoid role families from the list, level), employment (want from: permanent, "
    "contract). strength must when they will not consider anything else ('only', 'never', 'won't', 'nothing under'), "
    "prefer when they would rather ('ideally', 'prefer', 'tired of').\n"
    "- ask: something still worth asking next time (text = the question; quote may be empty).\n"
    "Every finding except ask quotes the candidate's own words exactly. Never anything the recruiter said, never "
    "anything about other people (colleagues, managers, other candidates), never personality, attitude, culture or "
    "fit, never salary guesses. Never guess: leave out what was not said. Role families: " + ", ".join(ROLE_FAMILIES) + "."
)

_NUMBER_WORDS = {"ten": 10, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
                 "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000}
_UNITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "a": 1}


@dataclass
class Finding:
    kind: str
    text: str
    quote: str
    start: int | None
    end: int | None
    ref: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class CallOutcome:
    candidate_speaker: str | None
    findings: list[Finding]
    rejected: list[dict[str, str]]
    cost: dict[str, Any]


def _number_said(n: int, quote: str) -> bool:
    """The number is written in the quote: as digits (200, 1,000, 1k) or in words (two hundred, a thousand)."""
    q = quote.lower()
    digits = {m.replace(",", "").replace(".", "").replace(" ", "") for m in re.findall(r"\d[\d,. ]*\d|\d", q)}
    if str(n) in digits or (n % 1000 == 0 and re.search(rf"\b{n // 1000}\s*k\b", q)):
        return True
    words = re.findall(r"[a-z]+", q)
    for i, w in enumerate(words):
        if w in _NUMBER_WORDS:
            base = _NUMBER_WORDS[w]
            prev = _UNITS.get(words[i - 1]) if i else None
            if (prev or 1) * base == n or base == n:
                return True
    return False


def _candidate_speaker(text: str, name: str | None, said: str | None) -> str | None:
    """Who the candidate is in the transcript: the label that matches their name, else the model's pick if it is a
    real label. None when the transcript has no labels (then every line counts)."""
    labels = transcript.speakers(text)
    if not labels:
        return None
    parts = {p.lower() for p in (name or "").split() if len(p) > 1}
    overlap = sorted(((len(parts & set(label.lower().split())), label) for label in labels), reverse=True)
    if overlap and overlap[0][0] and (len(overlap) == 1 or overlap[1][0] < overlap[0][0]):
        return overlap[0][1]  # the one label that shares most of their name
    for label in labels:
        if said and said.strip().lower() == label.lower():
            return label
    return ""


def _in_candidate_line(text: str, start: int, end: int, speaker: str | None) -> bool:
    if speaker is None:
        return True
    for t in transcript.turns(text):
        if t.start <= start and end <= t.end + 1:
            return t.speaker == speaker
    return False


def read(text: str, client: LLMClient, *, name: str | None, facts: list[dict[str, Any]], questions: list[dict[str, Any]],
         preferences: list[dict[str, Any]]) -> CallOutcome:
    """`facts`: [{ref, kind, text}], `questions`: [{ref, question}], `preferences`: [{facet, text}]."""
    def block(title: str, lines: list[str]) -> list[str]:
        return [title, *(lines or ["(none)"])]

    context = "\n".join([*block("FACTS:", [f"{f['ref']} [{f['kind']}] {f['text']}" for f in facts]),
                         *block("QUESTIONS:", [f"{q['ref']} {q['question']}" for q in questions]),
                         *block("PREFERENCES:", [f"- {p['facet']}: {p['text']}" for p in preferences]),
                         f"CANDIDATE: {name or 'name not known'}", "TRANSCRIPT:", text[:transcript.MAX_CHARS]])
    result = client.complete_json(SYSTEM, context, SCHEMA, "call_findings")
    speaker = _candidate_speaker(text, name, result.data.get("candidate_speaker"))
    fact_refs = {f["ref"] for f in facts}
    question_refs = {q["ref"] for q in questions}
    findings, rejected = [], []
    for raw in result.data.get("findings", []):
        kind, quote, words = raw.get("kind"), (raw.get("quote") or "").strip(), (raw.get("text") or "").strip()

        def no(why: str) -> None:
            rejected.append({"item": (words or quote)[:80], "reason": why})

        if kind not in KINDS:
            no("unknown kind")
            continue
        if NOT_CRITERIA.search(f"{words} {quote}"):
            no("personality, culture or fit is never recorded")
            continue
        where = locate(text, quote) if quote else None
        if kind != "ask":
            if where is None:
                no("the quote is not in the transcript")
                continue
            if speaker == "":
                no("could not tell which speaker is the candidate")
                continue
            if not _in_candidate_line(text, where.char_start, where.char_end, speaker):
                no("the quote is not the candidate's own words")
                continue
        elif not words:
            no("an empty question")
            continue
        fields: dict[str, Any] = {}
        ref = raw.get("ref")
        if kind == "brief_answer":
            if ref not in question_refs or raw.get("outcome") not in OUTCOMES:
                no("no such question, or no outcome")
                continue
            fields = {"outcome": raw["outcome"]}
        elif kind in ("confirm", "correct", "dispute"):
            if ref not in fact_refs:
                no("no such fact")
                continue
            if kind == "correct":
                value = (raw.get("value") or "").strip()
                if not value or value.lower() not in quote.lower():
                    no("the corrected value is not in their words")
                    continue
                fields = {"value": value}
        elif kind == "new_fact":
            fields = _new_fact(raw, quote)
            if isinstance(fields, str):
                no(fields)
                continue
        elif kind == "preference":
            fields = _preference(raw, quote)
            if isinstance(fields, str):
                no(fields)
                continue
        else:
            ref = None
        findings.append(Finding(kind, words[:300] or quote[:200], quote[:400], where.char_start if where else None,
                                where.char_end if where else None, ref, fields))
    cost = {"model": result.model, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens, "usd": result.usd}
    return CallOutcome(speaker or None, findings, rejected, cost)


def _new_fact(raw: dict[str, Any], quote: str) -> dict[str, Any] | str:
    ft, value, q = raw.get("fact_type"), (raw.get("value") or "").strip(), quote.lower()
    if ft == "skill":
        return {"fact_type": ft, "value": value} if value and value.lower() in q else "the skill is not in their words"
    if ft == "location":
        return {"fact_type": ft, "value": value} if value and value.lower() in q else "the place is not in their words"
    if ft == "contact":
        kind = raw.get("contact_kind")
        if kind not in CONTACT_KINDS or not value:
            return "a contact needs a kind and a value"
        said = re.sub(r"\D", "", value) in re.sub(r"\D", "", q) if kind == "phone" else value.lower() in q
        return {"fact_type": ft, "contact_kind": kind, "value": value} if said else "the contact is not in their words"
    if ft == "career_step":
        company, title = (raw.get("company") or "").strip(), (raw.get("title") or "").strip()
        if not company or company.lower() not in q:
            return "the company is not in their words"
        years = {k: raw.get(k) for k in ("start_year", "end_year") if raw.get(k)}
        if any(str(y) not in q and f"'{str(y)[-2:]}" not in q for y in years.values()):
            return "a year is not in their words"
        return {"fact_type": ft, "company": company, "title": title or None, **years}
    return "unknown kind of fact"


def _preference(raw: dict[str, Any], quote: str) -> dict[str, Any] | str:
    facet, strength = raw.get("facet"), raw.get("strength")
    if facet not in FACETS or strength not in ("must", "prefer"):
        return "a preference needs a facet and must or prefer"
    want, avoid = list(dict.fromkeys(raw.get("want") or [])), list(dict.fromkeys(raw.get("avoid") or []))
    out: dict[str, Any] = {"facet": facet, "strength": strength}
    if facet == "company_size":
        lo, hi = raw.get("min"), raw.get("max")
        if lo is None and hi is None:
            return "a company size needs a number"
        if any(n is not None and not _number_said(n, quote) for n in (lo, hi)):
            return "the number is not in their words"
        return {**out, "min": lo, "max": hi}
    allowed = {"employer_kind": EMPLOYER_KINDS, "setting": SETTINGS, "employment": EMPLOYMENT, "work": ROLE_FAMILIES}.get(facet)
    if facet == "places":
        want = [c.upper() for c in want if re.fullmatch(r"[A-Za-z]{2}", c)]
        avoid = [c.upper() for c in avoid if re.fullmatch(r"[A-Za-z]{2}", c)]
    elif allowed is not None:
        want, avoid = [w for w in want if w in allowed], [a for a in avoid if a in allowed]
    level = raw.get("level") if facet == "work" and raw.get("level") in LEVELS else None
    if not want and not avoid and not level:
        return "nothing usable from the lists"
    return {**out, "want": want, "avoid": avoid, **({"level": level} if level else {})}
