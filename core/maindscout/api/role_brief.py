"""The role brief on a job (step B of understanding the hire, owner 2026-10-19): read from the ad, the hiring manager's
notes and public research on the hiring company. Each line is a RoleScopeClaim with its evidence: the ad's span, the
notes, the research line, or (for our reading) the reading itself. A new reading replaces the machine's older lines,
never a line a person approved or corrected. Questions for whoever uploaded the job ride on the lines they settle.
Read on request for now: it runs by itself once the owner has reviewed its first readings.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.api import costs, writer
from maindscout.db.models import Claim, ClaimObservation, Company, CompanySignal, Evidence, ExtractionArtifact, Job, JobIntake
from maindscout.intelligence import role_brief as engine
from maindscout.intelligence.llm import LLMClient

PURPOSE = "role_brief"
LIVE = ("proposed", "approved")
CLAIM = "RoleScopeClaim"


def inputs(session: Session, job: Job) -> dict[str, Any]:
    """The three texts a brief is read from, and what their quotes point back to."""
    from maindscout.api import profiles

    art = session.scalar(select(ExtractionArtifact).where(ExtractionArtifact.document_id == job.source_document_id,
                                                          ExtractionArtifact.method == "text_layer")
                         .order_by(ExtractionArtifact.created_at.desc()).limit(1)) if job.source_document_id else None
    intakes = list(session.scalars(select(JobIntake).where(JobIntake.job_id == job.id).order_by(JobIntake.created_at)))
    company = session.get(Company, job.hiring_company_id) if job.hiring_company_id else None
    research = ""
    if company is not None:
        signals = [{"quote": s.quote} for s in session.scalars(select(CompanySignal).where(CompanySignal.company_id == company.id)
                                                                 .order_by(CompanySignal.created_at.desc()).limit(3))]
        research = engine.research_text(company.name, company.exa_profile, profiles.company_facts(session, company), signals)
    return {"ad": art.content if art else "", "artifact": art, "intakes": intakes,
            "notes": "\n\n".join(i.text for i in intakes), "company": company, "research": research}


def _evidence(session: Session, job: Job, claim: Claim, f: engine.Facet, src: dict[str, Any], model: str) -> Evidence:
    today = date.today()
    check = {"tier": "quote" if f.quote else "paraphrase", "result": "pass", "metric_bucket": "none",
             "detail": f"role brief read by {model} ({engine.ROLE_BRIEF_PROMPT_VERSION})"}
    if f.basis == "ad" and src["artifact"] is not None:
        return Evidence(org_id=job.org_id, claim_id=claim.id, evidence_type="document_span", document_id=job.source_document_id,
                        locator={"artifact_id": str(src["artifact"].id), "char_start": f.start, "char_end": f.end},
                        snippet=f.quote, source_authority="employer_authored", origin="employer", observed_as_of=today,
                        span_validation=check)
    if f.basis == "notes":
        intake = next((i for i in src["intakes"] if f.quote and f.quote.lower()[:40] in i.text.lower()), None)
        return Evidence(org_id=job.org_id, claim_id=claim.id, evidence_type="intake_note",
                        locator={"intake_id": str(intake.id)} if intake else {}, snippet=f.quote,
                        source_authority="human_assertion", origin="relayed", observed_as_of=today, span_validation=check)
    if f.basis == "research":
        return Evidence(org_id=job.org_id, claim_id=claim.id, evidence_type="research_result",
                        locator={"company_id": str(src["company"].id)} if src["company"] else {}, snippet=f.quote,
                        source_authority="web_inference", origin="independent_web", observed_as_of=today, span_validation=check)
    return Evidence(org_id=job.org_id, claim_id=claim.id, evidence_type="inference", locator={}, snippet=f.words,
                    source_authority="employer_authored", origin="employer", observed_as_of=today, span_validation=check)


def read(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, client: LLMClient, task_id: uuid.UUID | None = None) -> dict[str, Any]:
    """Read the role's brief (one model call, about a cent) and keep each line with its evidence."""
    job = session.get(Job, job_id)
    if job is None or job.org_id != org_id:
        raise LookupError(f"No job {job_id}")
    src = inputs(session, job)
    if not (src["ad"] or src["notes"]):
        return {"skipped": "no ad and no notes to read"}
    costs.ensure_budget(session, org_id)
    brief = engine.read(src["ad"], src["notes"], src["research"], client)
    costs.record(session, org_id, PURPOSE, brief.cost, subject_type="job", subject_id=job.id, task_id=task_id)
    written, kept = 0, 0
    seen = set()
    for f in brief.facets:
        key = f"{job.id}|scope|{f.facet}"
        seen.add(key)
        payload = {"facet": f.facet, "value": f.value, "words": f.words, "basis": f.basis, "question": f.question, "why": f.why}
        live = session.scalar(select(Claim).where(Claim.subject_id == job.id, Claim.claim_type == CLAIM, Claim.natural_key == key,
                                                  Claim.status.in_(LIVE)))
        if live is not None and (live.status == "approved" or live.payload == payload):
            kept += 1  # a person decided this line, or nothing changed
            continue
        claim = writer.add_claim(session, org_id=org_id, subject_type="job", subject_id=job.id, claim_type=CLAIM, payload=payload,
                                 natural_key=key, claim_class="inferred", status="proposed", observed_as_of=date.today())
        if live is not None:
            live.status, live.superseded_by = "superseded", claim.id
        ev = _evidence(session, job, claim, f, src, brief.cost.get("model") or "the model")
        session.add(ev)
        session.flush()
        session.add(ClaimObservation(org_id=org_id, claim_id=claim.id, attribute_path=".", value=payload, evidence_id=ev.id,
                                     source_authority=ev.source_authority, origin=ev.origin, observed_as_of=date.today()))
        written += 1
    for old in session.scalars(select(Claim).where(Claim.subject_id == job.id, Claim.claim_type == CLAIM, Claim.status == "proposed")):
        if old.natural_key not in seen:  # a machine line the new reading no longer gives
            old.status = "superseded"
    session.flush()
    return {"written": written, "kept": kept, "lines": len(brief.facets), "questions": len(brief.questions()),
            "rejected": brief.rejected, "usd": brief.cost.get("usd", 0)}


def read_at(session: Session, job_id: uuid.UUID) -> str | None:
    """When the brief was last read (its cost entry: written even when the reading changed nothing)."""
    from maindscout.db.models import CostEntry

    at = session.scalar(select(CostEntry.created_at).where(CostEntry.purpose == PURPOSE, CostEntry.subject_id == job_id)
                        .order_by(CostEntry.created_at.desc()).limit(1))
    return at.isoformat() if at else None


def view(session: Session, job_id: uuid.UUID) -> list[dict[str, Any]]:
    """The live brief for the job page, in facet order: each line with where it comes from and its question."""
    order = list(engine.FACETS)
    rows = []
    for c in session.scalars(select(Claim).where(Claim.subject_id == job_id, Claim.claim_type == CLAIM, Claim.status.in_(LIVE))):
        p = c.approved_view or c.payload
        ev = session.scalar(select(Evidence).where(Evidence.claim_id == c.id).order_by(Evidence.created_at.desc()).limit(1))
        rows.append({"id": str(c.id), "facet": p["facet"], "value": p.get("value"), "words": p["words"], "basis": p["basis"],
                     "quote": ev.snippet if ev is not None and p["basis"] != "reading" else None,
                     "question": p.get("question"), "why": p.get("why"), "status": c.status,
                     "at": c.created_at.isoformat() if c.created_at else None})
    return sorted(rows, key=lambda r: order.index(r["facet"]) if r["facet"] in order else 99)


def answer(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, facet: str, text: str, actor: str,
           client: LLMClient) -> dict[str, Any]:
    """The uploader's answer to one of the brief's questions (step E, 2026-10-20): kept with the role's notes and read
    like any notes (each requirement with its quote), then the brief read again, so the answer becomes a line from
    the notes and the question goes. Two model calls, about two cents."""
    from maindscout.api import hiring

    line = next((r for r in view(session, job_id) if r["facet"] == facet and r.get("question")), None)
    if line is None:
        raise LookupError("That question is no longer open: reload the page")
    said = " ".join(text.split())
    if len(said) < 2:
        raise ValueError("Write the answer first.")
    return tell(session, org_id, job_id, f'The desk asked: "{line["question"]}" The answer: {said}', actor, client)


def tell(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, text: str, actor: str, client: LLMClient) -> dict[str, Any]:
    """Anything about the role in the recruiter's own words (owner, 2026-10-20: "why we cant just write and our desk
    understand it?"): a new ask, a correction, what the hiring manager said. Kept with the role's notes and read like
    them (each requirement with its quote, waiting for Confirm all), then the brief read again when the role has
    one. One or two model calls, at most about two cents."""
    from maindscout.api import hiring

    notes = hiring.add_intake(session, org_id, job_id, text, actor, client, shortest=6)
    dated = dates(session, org_id, job_id, text, actor, client)
    has_brief = session.scalar(select(Claim.id).where(Claim.subject_id == job_id, Claim.claim_type == CLAIM,
                                                      Claim.status.in_(LIVE)).limit(1)) is not None
    return {"notes": notes, "dates": dated, **(read(session, org_id, job_id, client) if has_brief else {})}


def dates(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, text: str, actor: str, client: LLMClient) -> list[dict[str, Any]]:
    """Dates in what the recruiter told the desk become the role's process dates, a new edition replacing the old one
    ("the next hackathon is on 21 November in London" replaces August's). Asked only when the words hold a date; one
    small model call."""
    from maindscout.api import review
    from maindscout.intelligence import dates as reader

    if not reader.mentions_date(text):
        return []
    events = [c for c in session.scalars(select(Claim).where(Claim.subject_id == job_id, Claim.claim_type == "JobRequirementClaim",
                                                             Claim.status.in_(LIVE)))
              if (c.approved_view or c.payload).get("category") == "process"]
    events.sort(key=lambda c: (c.approved_view or c.payload).get("normalized_token") or "")
    listed = [((c.approved_view or c.payload).get("text_raw") or "", (c.approved_view or c.payload).get("normalized_token") or "")
              for c in events]
    costs.ensure_budget(session, org_id)
    outcome = reader.read(text, listed, date.today(), client)
    costs.record(session, org_id, "process_dates", outcome.cost, subject_type="job", subject_id=job_id)
    out = []
    for d in outcome.dates:
        old = events[d.replaces] if d.replaces is not None else None
        if old is not None and old.status not in LIVE:
            old = None  # already replaced by an earlier line of the same text
        payload = {"text_raw": d.event, "category": "process", "strength": "unknown", "normalized_token": d.when,
                   "distinctive": False, "source": "intake"}
        if old is not None and (old.approved_view or old.payload).get("normalized_token") == d.when:
            continue  # the same date as before
        review.assert_claim(session, org_id, actor, subject_type="job", subject_id=job_id, claim_type="JobRequirementClaim",
                            payload=payload, replaces=old.id if old is not None else None)
        out.append({"event": d.event, "date": d.when, "replaced": listed[d.replaces] if old is not None else None})
    return out
