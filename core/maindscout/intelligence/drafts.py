"""Draft a message from what may be said outward. No database.

Outward projection (blueprint E-i12): a draft is written only from facts the desk approved about the recipient, the
job's public details, answers from the call, and the thread so far. Bands, match tiers, flags, internal reasons and
other people are never given to the writer, so they cannot appear. A last mechanical check refuses any draft that
still mentions internal words; the plain template is used instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from maindscout.intelligence.llm import LLMClient

DRAFT_PROMPT_VERSION = "2026-10-05.1"
KINDS = ("candidate_outreach", "follow_up", "client_submission", "interview_confirm", "decline")

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["subject", "body"],
          "properties": {"subject": {"type": "string"}, "body": {"type": "string"}}}

SYSTEM = (
    "You write one short, warm, professional email for a recruiter, in plain English, using ONLY the facts given. "
    "Never invent facts, numbers, companies or promises. Never mention assessments, scores, rankings, bands, tiers, "
    "flags, matching, other candidates or how the recruiter found the person. No emojis. Sign off with the "
    "recruiter's name if given, else 'Best regards'. Keep it under 140 words."
)
PURPOSE = {
    "candidate_outreach": "First contact with a candidate about a role: why they came to mind (from their own facts) and ask for a short call.",
    "follow_up": "A brief, friendly follow-up to the earlier message that got no reply. Do not repeat it; offer an easy way to say no.",
    "client_submission": "Introduce a candidate to the client's hiring contact for the role: why they fit, from their facts and what they said on the call.",
    "interview_confirm": "Confirm an interview the recruiter arranged; ask the recipient to confirm.",
    "decline": "Tell the candidate kindly that this role will not go ahead for them, and that you would like to stay in touch.",
}

# Words that must never reach a recipient (internal judgements and machinery).
INTERNAL = re.compile(r"\b(tier|score|scored|scoring|band|banded|flag|flagged|do not submit|unlikely|review later|priority list|"
                      r"match(?:ing)? (?:rule|engine)|archived|coverage|brief item|internal|percent)\b|\d+\s*%", re.I)


@dataclass
class Projection:
    """Everything the writer may use. Built by api/messages.py from approved facts only."""

    kind: str
    recipient_name: str | None
    recruiter_name: str | None = None
    job: dict[str, Any] = field(default_factory=dict)  # title, company (unless confidential), places, must-haves
    facts: list[str] = field(default_factory=list)  # approved facts about the person (or the candidate, for a submission)
    call_answers: list[str] = field(default_factory=list)  # what they said on the call (Brief answers)
    thread: list[dict[str, str]] = field(default_factory=list)  # earlier messages in this thread
    note: str | None = None  # the recruiter's own line (e.g. interview time)

    def as_text(self) -> str:
        lines = [f"Purpose: {PURPOSE[self.kind]}", f"Recipient's first name: {self.recipient_name or 'unknown'}"]
        if self.recruiter_name:
            lines.append(f"Recruiter's name: {self.recruiter_name}")
        if self.job:
            lines.append("Role: " + "; ".join(f"{k}: {v}" for k, v in self.job.items() if v))
        if self.facts:
            lines.append("Facts you may use: " + "; ".join(self.facts))
        if self.call_answers:
            lines.append("Said on the call: " + "; ".join(self.call_answers))
        if self.note:
            lines.append(f"Recruiter's note to include: {self.note}")
        for m in self.thread[-2:]:
            lines.append(f"Earlier message ({m.get('subject')}): {m.get('body', '')[:600]}")
        return "\n".join(lines)


def template(p: Projection) -> tuple[str, str]:
    """The plain version, used when no model is available or the model's draft fails the check."""
    hi = f"Hi {p.recipient_name}," if p.recipient_name else "Hello,"
    sign = f"\n\nBest regards,\n{p.recruiter_name}" if p.recruiter_name else "\n\nBest regards"
    role = p.job.get("title") or "a role"
    at = f" at {p.job['company']}" if p.job.get("company") else ""
    why = f" Your background ({p.facts[0]}) stood out." if p.facts else ""
    if p.kind == "candidate_outreach":
        return f"{role}{at}", f"{hi}\n\nI'm working on {role}{at} and thought of you.{why} Would you be open to a short call this week?{sign}"
    if p.kind == "follow_up":
        subject = (p.thread[-1]["subject"] if p.thread else role)
        return f"Re: {subject}", f"{hi}\n\nJust checking whether you saw my note. If now isn't the right time, a quick no is completely fine.{sign}"
    if p.kind == "client_submission":
        facts = "".join(f"\n- {f}" for f in p.facts[:5])
        said = "".join(f"\n- {a}" for a in p.call_answers[:4])
        return (f"Candidate for {role}", f"{hi}\n\nI'd like to introduce a candidate for {role}.{facts}" +
                (f"\n\nFrom our call:{said}" if said else "") + f"\n\nHappy to arrange a conversation.{sign}")
    if p.kind == "interview_confirm":
        return f"Interview: {role}", f"{hi}\n\nConfirming the interview for {role}{at}.{(' ' + p.note) if p.note else ''} Could you confirm this works for you?{sign}"
    return f"{role}{at}", f"{hi}\n\nThank you for your time on {role}{at}. It won't go ahead for you this time, but I'd very much like to stay in touch.{sign}"


@dataclass
class DraftOutcome:
    subject: str
    body: str
    written_by: str  # model | template
    refused: str | None = None
    cost: dict[str, Any] = field(default_factory=dict)


def write(p: Projection, client: LLMClient | None) -> DraftOutcome:
    if p.kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if client is not None:
        try:
            result = client.complete_json(SYSTEM, p.as_text(), SCHEMA, "draft_message")
            subject, body = (result.data.get("subject") or "").strip(), (result.data.get("body") or "").strip()
            cost = {"model": result.model, "input_tokens": result.input_tokens, "output_tokens": result.output_tokens, "usd": result.usd}
            bad = INTERNAL.search(subject + "\n" + body)
            if subject and body and not bad:
                return DraftOutcome(subject[:200], body[:5000], "model", cost=cost)
            subject_t, body_t = template(p)
            return DraftOutcome(subject_t, body_t, "template", refused=f"the model's draft mentioned {bad.group(0)!r}" if bad else "empty draft", cost=cost)
        except Exception as error:  # noqa: BLE001 - a draft must never fail the recruiter: fall back to the template
            subject_t, body_t = template(p)
            return DraftOutcome(subject_t, body_t, "template", refused=f"model unavailable: {type(error).__name__}")
    subject_t, body_t = template(p)
    return DraftOutcome(subject_t, body_t, "template")
