"""Calls: a call transcript becomes one Call review that a recruiter approves in bulk.

Add a transcript (paste or file) -> it is stored as the person's document (doc_type 'transcript', kept as evidence
until erasure) -> read once in the background (intelligence/calls.py) -> a Call review with every line ticked,
except corrections and disputes of facts a person already approved -> "Approve all" writes approved facts whose
evidence is the candidate's own words in the transcript, answers the Brief, and re-matches once.

No consent step: the call tools (Zoom, Teams, Meet notetakers) already obtain it (owner, 2026-10-06).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.api import brief, costs, review
from maindscout.api.documents import extract_document, upload_document
from maindscout.db.models import BriefItem, CallReview, Candidate, Claim, Document, DocumentSubject, ExtractionArtifact, Job
from maindscout.domain import geo
from maindscout.domain.preferences import describe as describe_preference
from maindscout.ingestion import transcript
from maindscout.intelligence import calls as reader
from maindscout.intelligence.llm import LLMClient
from maindscout.storage import BlobStore

LIVE = ("proposed", "approved")
FACT_TYPES = ("ContactClaim", "LocationClaim", "CareerStepClaim", "EducationClaim", "SkillClaim")
SECTIONS = [("brief_answer", "Brief answers"), ("confirm", "Confirmed"), ("correct", "Corrected"), ("dispute", "Disputed"),
            ("new_fact", "New facts"), ("preference", "What they want"), ("ask", "Ask next time")]


class CallError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _person(session: Session, org_id, candidate_id) -> Candidate:
    person = session.get(Candidate, candidate_id)
    if person is None or person.org_id != org_id:
        raise LookupError(f"No candidate {candidate_id}")
    return person


def _review(session: Session, org_id, review_id) -> CallReview:
    row = session.get(CallReview, review_id)
    if row is None or row.org_id != org_id:
        raise LookupError(f"No call review {review_id}")
    return row


def add_transcript(session: Session, blobs: BlobStore, org_id, candidate_id: uuid.UUID, data: bytes, filename: str | None,
                   actor: str, job_id: uuid.UUID | None = None) -> CallReview:
    """Store the transcript as the person's document and queue its reading. The same transcript twice is one review."""
    from maindscout.api import tasks

    person = _person(session, org_id, candidate_id)
    if person.archived_at is not None:
        raise CallError("This person is archived as outside coverage: bring them back first.")
    if job_id is not None:
        job = session.get(Job, job_id)
        if job is None or job.org_id != org_id:
            raise LookupError(f"No job {job_id}")
    try:
        text = transcript.to_text(data, filename)
    except transcript.TranscriptError as error:
        raise CallError(str(error)) from error
    base = (filename or "call transcript").rsplit(".", 1)[0] if (filename or "").lower().endswith(transcript.EXTENSIONS) else (filename or "call transcript")
    name = f"{base}.txt"  # stored as the plain text that was read (timings and markup removed)
    document, reused = upload_document(session, blobs, org_id=org_id, data=text.encode("utf-8"), filename=name,
                                       media_type="text/plain; charset=utf-8", doc_type_hint="transcript")
    if reused:
        owner = session.scalar(select(DocumentSubject).where(DocumentSubject.document_id == document.id))
        if document.doc_type != "transcript" or (owner and owner.subject_id != candidate_id):
            raise CallError("This file is already on the desk as something else")
        existing = session.scalar(select(CallReview).where(CallReview.document_id == document.id).order_by(CallReview.created_at.desc()))
        if existing is not None:
            return existing
    else:
        session.add(DocumentSubject(document_id=document.id, subject_type="candidate", subject_id=candidate_id, org_id=org_id,
                                    established_by=f"call transcript added by {actor}"))
    extract_document(session, blobs, document.id)
    row = CallReview(org_id=org_id, candidate_id=candidate_id, document_id=document.id, job_id=job_id, status="reading",
                     findings=[], created_by=actor)
    session.add(row)
    session.flush()
    tasks.enqueue(session, org_id, "read_transcript", {"review_id": str(row.id), "candidate_id": str(candidate_id),
                                                       "document_id": str(document.id)}, priority=20,
                  dedupe_key=f"read_transcript:{row.id}")
    return row


# --- reading ------------------------------------------------------------------------------------------------------


def _fact_text(c: Claim) -> tuple[str, str]:
    p = c.approved_view or c.payload
    years = "–".join(str(d.year) for d in (c.valid_from, c.valid_to) if d) or ("from " + str(c.valid_from.year) if c.valid_from else "")
    if c.claim_type == "ContactClaim":
        return "contact", f"{p.get('kind')}: {p.get('value')}"
    if c.claim_type == "LocationClaim":
        return "location", f"lives in {p.get('place_raw')}" if (p.get("kind") or "current") == "current" else f"{p.get('kind')}: {p.get('place_raw')}"
    if c.claim_type == "CareerStepClaim":
        return "career", f"{p.get('title_raw')} at {(p.get('company') or {}).get('raw_name')}" + (f" ({years})" if years else "")
    if c.claim_type == "EducationClaim":
        return "education", f"{p.get('degree_raw') or 'studied'} at {p.get('institution_raw')}" + (f" ({years})" if years else "")
    return "skill", str(p.get("raw_label") or p.get("normalized_skill"))


def _context(session: Session, org_id, review: CallReview) -> dict[str, Any]:
    """What the desk knows, with short refs the model can point at, and the map back to ids."""
    person = session.get(Candidate, review.candidate_id)
    try:  # the standard questions exist even for someone never briefed before
        brief.build_person(session, org_id, review.candidate_id)
    except brief.BriefError:
        pass
    claims = list(session.scalars(select(Claim).where(
        Claim.org_id == org_id, Claim.subject_id == review.candidate_id, Claim.claim_type.in_(FACT_TYPES),
        Claim.status.in_(LIVE)).order_by(Claim.claim_type, Claim.valid_from.desc().nulls_last())))
    facts, fact_ids = [], {}
    for i, c in enumerate(claims, 1):
        kind, text = _fact_text(c)
        facts.append({"ref": f"F{i}", "kind": kind, "text": text + ("" if c.status == "approved" else " (not yet approved)")})
        fact_ids[f"F{i}"] = c
    scope = (BriefItem.job_id.is_(None) | (BriefItem.job_id == review.job_id)) if review.job_id else BriefItem.job_id.is_(None)
    items = list(session.scalars(select(BriefItem).where(BriefItem.candidate_id == review.candidate_id, scope,
                                                         BriefItem.status.in_(brief.ALIVE)).order_by(BriefItem.created_at)))
    questions = [{"ref": f"B{i}", "question": b.question} for i, b in enumerate(items, 1)]
    prefs = [{"facet": c.payload["facet"], "text": describe_preference(c.payload)} for c in preferences_of(session, org_id, review.candidate_id)]
    names = [c.payload.get("full_name") for c in session.scalars(select(Claim).where(
        Claim.subject_id == review.candidate_id, Claim.claim_type == "IdentityClaim", Claim.status.in_(LIVE)))]
    name = next((n for n in names if n), None) or ((person.name_variants or [None])[0])
    return {"name": name, "facts": facts, "fact_ids": fact_ids, "questions": questions,
            "question_ids": {q["ref"]: b for q, b in zip(questions, items)}, "preferences": prefs}


def read(session: Session, org_id, review_id: uuid.UUID, llm: LLMClient, task_id: uuid.UUID | None = None) -> dict[str, Any]:
    """The one model call: turn the transcript into review lines."""
    row = _review(session, org_id, review_id)
    if row.status != "reading":
        return {"status": row.status}
    costs.ensure_budget(session, org_id)
    artifact = session.scalar(select(ExtractionArtifact).where(ExtractionArtifact.document_id == row.document_id))
    ctx = _context(session, org_id, row)
    out = reader.read(artifact.content, llm, name=ctx["name"], facts=ctx["facts"], questions=ctx["questions"],
                      preferences=ctx["preferences"])
    costs.record(session, org_id, "read_transcript", out.cost, subject_type="candidate", subject_id=row.candidate_id, task_id=task_id)
    current = {c.payload["facet"]: c for c in preferences_of(session, org_id, row.candidate_id)}
    lines = []
    for n, f in enumerate(out.findings, 1):
        line: dict[str, Any] = {"id": str(n), "kind": f.kind, "text": f.text, "quote": f.quote, "char_start": f.start,
                                "char_end": f.end, "artifact_id": str(artifact.id), "ticked": True, **f.fields}
        if f.kind == "brief_answer":
            item = ctx["question_ids"][f.ref]
            line |= {"brief_item_id": str(item.id), "question": item.question}
        elif f.kind in ("confirm", "correct", "dispute"):
            claim = ctx["fact_ids"][f.ref]
            line |= {"claim_id": str(claim.id), "claim_type": claim.claim_type, "current": _fact_text(claim)[1],
                     "current_status": claim.status}
            if f.kind == "confirm" and claim.status == "approved":
                line["note"] = "already approved: nothing changes"
            elif f.kind != "confirm" and claim.status == "approved":
                # An approved fact is only overturned on purpose: these start unticked (owner, 2026-10-06).
                line |= {"ticked": False, "note": "this fact was approved by a person: tick to change it"}
        elif f.kind == "preference":
            line["summary"] = describe_preference(f.fields)
            old = current.get(f.fields["facet"])
            if old is not None:
                line |= {"replaces_claim_id": str(old.id), "replaces": describe_preference(old.payload)}
        lines.append(line)
    row.findings, row.status = lines, "pending"
    if not lines:
        row.error = "Nothing about the candidate was found in this transcript" + (
            " (could not tell which speaker is the candidate)" if any("which speaker" in r["reason"] for r in out.rejected) else "")
    session.flush()
    return {"status": row.status, "lines": len(lines), "rejected": len(out.rejected), "usd": out.cost.get("usd", 0)}


def fail(session: Session, review_id: uuid.UUID, error: str) -> None:
    row = session.get(CallReview, review_id)
    if row is not None and row.status == "reading":
        row.status, row.error = "failed", error[:500]


# --- applying -----------------------------------------------------------------------------------------------------


def _said(row: CallReview, line: dict[str, Any]) -> dict[str, Any]:
    return {"document_id": row.document_id, "artifact_id": line.get("artifact_id"), "char_start": line.get("char_start"),
            "char_end": line.get("char_end"), "snippet": line.get("quote"), "origin": "candidate", "authority": "candidate_authored"}


def _contact(kind: str, value: str) -> dict[str, Any]:
    v = value.strip()
    if kind == "email":
        normalized = v.lower()
    elif kind == "phone":
        normalized = ("+" if v.startswith("+") else "") + "".join(ch for ch in v if ch.isdigit())
    else:
        normalized = v.lower().split("?")[0].removeprefix("https://").removeprefix("http://").removeprefix("www.").rstrip("/")
    return {"kind": kind, "value": v, "normalized": normalized}


def _payload_for(claim_type: str, value: str, old: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """A typed fact from a value said on the call, or None when the type is not one a value can replace."""
    if claim_type == "ContactClaim":
        return _contact((old or {}).get("kind") or "email", value)
    if claim_type == "LocationClaim":
        return {"place_raw": value, "country_code": geo.country_in(value), "basis": "stated", "kind": "current"}
    if claim_type == "SkillClaim":
        return {"raw_label": value, "normalized_skill": value.strip().lower()}
    return None


def _apply_line(session: Session, org_id, row: CallReview, line: dict[str, Any], actor: str) -> str:
    kind, cid = line["kind"], row.candidate_id
    assertion = dict(subject_type="candidate", subject_id=cid, said=_said(row, line))
    if kind == "brief_answer":
        item = session.get(BriefItem, uuid.UUID(line["brief_item_id"]))
        if item is None or item.status not in brief.ALIVE:
            return "skipped: the question was already answered"
        brief.answer(session, org_id, item.id, line["outcome"], line.get("text"), actor)
        return "applied"
    if kind in ("confirm", "correct", "dispute"):
        claim = session.get(Claim, uuid.UUID(line["claim_id"]))
        if claim is None or claim.status not in LIVE:
            return "skipped: the fact changed since the call was read"
        if kind == "confirm":
            if claim.status == "proposed":
                review.approve_claim(session, org_id, claim.id, actor)
            return "applied"
        payload = _payload_for(claim.claim_type, line.get("value") or "", claim.approved_view or claim.payload) if kind == "correct" else None
        if payload is not None:
            review.assert_claim(session, org_id, actor, claim_type=claim.claim_type, payload=payload, replaces=claim.id, **assertion)
        else:  # a disputed fact, or a correction of a career or study step: the old one goes, their words are kept
            review.reject_claim(session, org_id, claim.id, actor, "wrong", f"On the call: {line.get('quote')}"[:500])
            if kind == "correct":
                review.assert_claim(session, org_id, actor, claim_type="BriefAnswerClaim", payload={
                    "topic": f"call:correct:{claim.id}", "question": f"Is this right: {line.get('current')}?", "outcome": "noted",
                    "answer": line.get("text"), "job_id": None, "requirement_id": None}, **assertion)
        return "applied"
    if kind == "new_fact":
        ft, value = line["fact_type"], line.get("value") or ""
        if ft == "skill":
            review.assert_claim(session, org_id, actor, claim_type="SkillClaim", payload=_payload_for("SkillClaim", value), **assertion)
        elif ft == "location":
            review.assert_claim(session, org_id, actor, claim_type="LocationClaim", payload=_payload_for("LocationClaim", value), **assertion)
        elif ft == "contact":
            review.assert_claim(session, org_id, actor, claim_type="ContactClaim", payload=_contact(line["contact_kind"], value), **assertion)
        elif ft == "career_step":
            start, end = line.get("start_year"), line.get("end_year")
            review.assert_claim(session, org_id, actor, claim_type="CareerStepClaim",
                                payload={"company": {"raw_name": line["company"], "provisional": True},
                                         "title_raw": line.get("title") or "role not said"},
                                valid_from=f"{start}-01-01" if start else None, valid_to=f"{end}-12-31" if end else None,
                                precision="year_only" if start else None, **assertion)
        return "applied"
    if kind == "preference":
        payload = {"facet": line["facet"], "strength": line["strength"], "min": line.get("min"), "max": line.get("max"),
                   "want": line.get("want") or [], "avoid": line.get("avoid") or [], "level": line.get("level"),
                   "said": line.get("quote")}
        live = [c for c in preferences_of(session, org_id, cid) if c.payload["facet"] == line["facet"]]  # newer replaces older
        review.assert_claim(session, org_id, actor, claim_type="PreferenceClaim", payload=payload,
                            replaces=live[0].id if live else None, **assertion)
        return "applied"
    if kind == "ask":
        session.add(BriefItem(org_id=org_id, candidate_id=cid, job_id=None, source_key=f"call:{row.id}:{line['id']}", kind="call",
                              question=line["text"], why="Came up on the call", status="open"))
        return "applied"
    return "skipped: unknown line"


def apply(session: Session, org_id, review_id: uuid.UUID, actor: str, ticked: list[str] | None = None) -> CallReview:
    """Approve the ticked lines (all the default ticks when `ticked` is None) in one act; unticked lines are dropped.
    Matching, coverage and the career profile are recomputed once, at the end."""
    from maindscout.api import relationship

    row = _review(session, org_id, review_id)
    if row.status != "pending":
        raise CallError(f"This call review is {row.status}")
    chosen = {line["id"] for line in row.findings if line.get("ticked")} if ticked is None else set(ticked)
    lines = []
    with review.batched(session, org_id, {"act": "call_review", "review_id": str(row.id)}, actor):
        for line in row.findings:
            outcome = _apply_line(session, org_id, row, line, actor) if line["id"] in chosen else "dropped"
            lines.append({**line, "ticked": line["id"] in chosen, "result": outcome})
        applied = sum(1 for line in lines if line["result"] == "applied")
        relationship.log(session, org_id, "candidate", row.candidate_id, "call",
                         f"Call transcript reviewed: {applied} line{'s' if applied != 1 else ''} approved", actor, job_id=row.job_id)
    row.findings, row.status, row.resolved_by, row.resolved_at = lines, "applied", actor, _now()
    session.flush()
    return row


def dismiss(session: Session, org_id, review_id: uuid.UUID, actor: str) -> CallReview:
    """Nothing from this call is used. The transcript stays on the person's documents."""
    row = _review(session, org_id, review_id)
    if row.status not in ("pending", "failed"):
        raise CallError(f"This call review is {row.status}")
    row.status, row.resolved_by, row.resolved_at = "dismissed", actor, _now()
    session.flush()
    return row


def retry(session: Session, org_id, review_id: uuid.UUID) -> CallReview:
    from maindscout.api import tasks

    row = _review(session, org_id, review_id)
    if row.status != "failed":
        raise CallError("Only a failed reading can be tried again")
    row.status, row.error = "reading", None
    tasks.enqueue(session, org_id, "read_transcript", {"review_id": str(row.id), "candidate_id": str(row.candidate_id),
                                                       "document_id": str(row.document_id)}, priority=20)
    session.flush()
    return row


# --- reading back -------------------------------------------------------------------------------------------------


def preferences_of(session: Session, org_id, candidate_id) -> list[Claim]:
    """The person's approved preferences, newest first per facet."""
    rows = session.scalars(select(Claim).where(Claim.org_id == org_id, Claim.subject_id == candidate_id,
                                               Claim.claim_type == "PreferenceClaim", Claim.status == "approved")
                           .order_by(Claim.created_at.desc()))
    seen, out = set(), []
    for c in rows:
        facet = (c.approved_view or c.payload)["facet"]
        if facet not in seen:
            seen.add(facet)
            out.append(c)
    return out


def preferences_view(session: Session, org_id, candidate_id) -> list[dict[str, Any]]:
    """'What they want', for the person page: each preference in words, with their own words and when it was said."""
    out = []
    for c in preferences_of(session, org_id, candidate_id):
        p = c.approved_view or c.payload
        out.append({"claim_id": str(c.id), "facet": p["facet"], "strength": p["strength"], "summary": describe_preference(p),
                    "said": p.get("said"), "as_of": c.created_at.date().isoformat() if c.created_at else None,
                    "stale": bool(c.created_at and (date.today() - c.created_at.date()).days > STALE_DAYS)})
    return out


STALE_DAYS = 183  # preferences older than about six months are asked again in the person's Brief


def as_dict(row: CallReview, session: Session | None = None) -> dict[str, Any]:
    out = {"id": str(row.id), "candidate_id": str(row.candidate_id), "document_id": str(row.document_id),
           "job_id": str(row.job_id) if row.job_id else None, "status": row.status, "error": row.error,
           "created_by": row.created_by, "created_at": row.created_at.isoformat() if row.created_at else None,
           "resolved_by": row.resolved_by, "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
           "sections": [{"kind": k, "title": t, "lines": [line for line in row.findings if line["kind"] == k]}
                        for k, t in SECTIONS if any(line["kind"] == k for line in row.findings)]}
    if session is not None:
        doc = session.get(Document, row.document_id)
        out["filename"] = doc.filename if doc else None
        person = session.get(Candidate, row.candidate_id)
        out["person"] = person and _name(session, person)
    return out


def _name(session: Session, person: Candidate) -> str | None:
    for c in session.scalars(select(Claim).where(Claim.subject_id == person.id, Claim.claim_type == "IdentityClaim",
                                                 Claim.status.in_(LIVE)).order_by(Claim.status)):
        return (c.approved_view or c.payload).get("full_name")
    return (person.name_variants or [None])[0]


def for_person(session: Session, org_id, candidate_id) -> list[CallReview]:
    return list(session.scalars(select(CallReview).where(CallReview.org_id == org_id, CallReview.candidate_id == candidate_id)
                                .order_by(CallReview.created_at.desc())))


def waiting(session: Session, org_id) -> list[CallReview]:
    """Call reviews that wait for a person (the inbox shows them)."""
    return list(session.scalars(select(CallReview).where(CallReview.org_id == org_id, CallReview.status.in_(("pending", "reading", "failed")))
                                .order_by(CallReview.created_at)))
