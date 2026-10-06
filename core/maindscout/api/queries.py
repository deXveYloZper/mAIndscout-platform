"""Read models for the cockpit. Reads only; no writes here."""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import String, func, select
from sqlalchemy.orm import Session

from maindscout.api import coverage, freshness, hiring, messages, pipeline, profiles, relationship
from maindscout.db.models import (
    Company,
    Candidate,
    CandidateJob,
    Claim,
    Decision,
    DecisionItem,
    Document,
    DocumentSubject,
    Evidence,
    Job,
)

LIVE = ("proposed", "approved")
BANDS = ("priority", "review_later", "do_not_submit")
BLOCKING = ("identity_note", "ocr_contact")


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def names(session: Session, candidate_ids: list[uuid.UUID]) -> dict[uuid.UUID, str | None]:
    """Approved name if there is one, else the first proposed name."""
    out: dict[uuid.UUID, str | None] = {cid: None for cid in candidate_ids}
    if not candidate_ids:
        return out
    rows = session.scalars(select(Claim).where(
        Claim.claim_type == "IdentityClaim", Claim.subject_id.in_(candidate_ids), Claim.status.in_(LIVE)
    ).order_by(Claim.created_at))
    for claim in rows:
        current = out.get(claim.subject_id)
        if current is None or claim.status == "approved":
            out[claim.subject_id] = (claim.approved_view or claim.payload)["full_name"]
    return out


def evidence_for(session: Session, claim_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict[str, Any]]]:
    out: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
    if not claim_ids:
        return out
    rows = session.execute(
        select(Evidence, Document.filename).outerjoin(Document, Document.id == Evidence.document_id)
        .where(Evidence.claim_id.in_(claim_ids)).order_by(Evidence.created_at))
    for ev, filename in rows:
        out[ev.claim_id].append({
            "type": ev.evidence_type, "document_id": str(ev.document_id) if ev.document_id else None,
            "filename": filename, "page": (ev.locator or {}).get("page"), "snippet": ev.snippet,
            "origin": ev.origin, "source_authority": ev.source_authority, "observed_as_of": _iso(ev.observed_as_of),
            "note": (ev.span_validation or {}).get("detail"),
        })
    return out


def claim_view(claim: Claim, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": str(claim.id), "claim_type": claim.claim_type, "status": claim.status, "payload": claim.payload,
        "approved_view": claim.approved_view, "flags": claim.flags, "valid_from": _iso(claim.valid_from),
        "valid_to": _iso(claim.valid_to), "temporal_precision": claim.temporal_precision, "evidence": evidence,
    }


def list_jobs(session: Session, org_id: uuid.UUID) -> list[dict[str, Any]]:
    counts: dict[uuid.UUID, dict[str, int]] = defaultdict(lambda: {b: 0 for b in BANDS})
    archived: dict[uuid.UUID, int] = defaultdict(int)
    for job_id, band, gone, n in session.execute(
            select(CandidateJob.job_id, CandidateJob.triage_band, Candidate.archived_at.is_not(None), func.count())
            .join(Candidate, Candidate.id == CandidateJob.candidate_id).where(CandidateJob.org_id == org_id)
            .group_by(CandidateJob.job_id, CandidateJob.triage_band, Candidate.archived_at.is_not(None))):
        if gone:
            archived[job_id] += n
        elif band in BANDS:
            counts[job_id][band] += n
    jobs = list(session.scalars(select(Job).where(Job.org_id == org_id).order_by(Job.created_at.desc())))
    # "To review" per job = the job's priority inbox. Built once for the desk and counted per job, not once per job.
    priority: dict[uuid.UUID, set[str]] = defaultdict(set)
    for job_id, cid in session.execute(select(CandidateJob.job_id, CandidateJob.candidate_id)
                                       .join(Candidate, Candidate.id == CandidateJob.candidate_id)
                                       .where(CandidateJob.org_id == org_id, CandidateJob.triage_band == "priority",
                                              Candidate.archived_at.is_(None))):
        priority[job_id].add(str(cid))
    items = inbox(session, org_id, None, "all") if priority else []
    return [{"id": str(j.id), "title": j.title, "hiring_company": j.hiring_company, "state": j.state,
             "created_at": _iso(j.created_at), "bands": counts[j.id], "archived": archived[j.id],
             "to_review": sum(1 for i in items if (i.get("subject") or {}).get("id") in priority[j.id])} for j in jobs]


def _rematching(session: Session, job_id) -> bool:
    from maindscout.api.process import rematching

    return rematching(session, job_id)


def job_page(session: Session, org_id: uuid.UUID, job_id: uuid.UUID) -> dict[str, Any]:
    job = session.get(Job, job_id)
    if job is None or job.org_id != org_id:
        raise LookupError(f"No job {job_id}")
    reqs = list(session.scalars(select(Claim).where(Claim.subject_id == job.id, Claim.claim_type == "JobRequirementClaim",
                                                    Claim.status.in_(LIVE)).order_by(Claim.created_at)))
    ev = evidence_for(session, [c.id for c in reqs])
    pairs = list(session.scalars(select(CandidateJob).where(CandidateJob.job_id == job.id).order_by(CandidateJob.created_at)))
    who = names(session, [p.candidate_id for p in pairs])
    open_counts = dict(session.execute(
        select(Decision.subject_id, func.count()).where(Decision.org_id == org_id, Decision.sealed_at.is_(None))
        .group_by(Decision.subject_id)).all())
    people: dict[str, list[dict[str, Any]]] = {b: [] for b in BANDS}
    blocked = pipeline.blocked_ids_for_job(session, org_id, job)
    gone = {c.id: c.archived_reason for c in session.scalars(select(Candidate).where(
        Candidate.id.in_([p.candidate_id for p in pairs] or [None]), Candidate.archived_at.is_not(None)))}
    archived = []
    gap_rows = _gap_rows_many(session, org_id, job, [p.candidate_id for p in pairs if p.candidate_id not in gone])
    for p in pairs:
        if p.candidate_id in gone:
            archived.append({"candidate_id": str(p.candidate_id), "name": who.get(p.candidate_id),
                             "reason": (gone[p.candidate_id] or {}).get("text")})
            continue
        people.setdefault(p.triage_band, []).append({
            "candidate_id": str(p.candidate_id), "name": who.get(p.candidate_id), "band": p.triage_band,
            "reason": p.triage_reason, "overridden_by": p.band_overridden_by, "open_decisions": open_counts.get(p.candidate_id, 0),
            **_gap_summary(gap_rows[p.candidate_id]),
            "state": p.pair_state, "outcome": p.outcome, "match_tier": p.match_tier, "blocked": p.candidate_id in blocked,
        })
    return {
        "id": str(job.id), "title": job.title, "hiring_company": job.hiring_company, "state": job.state,
        "source_document_id": str(job.source_document_id) if job.source_document_id else None,
        "requirements": [claim_view(c, ev[c.id]) for c in reqs],
        "process_stale": any(c.flags.get("job_process_stale") for c in reqs),
        "rematching": _rematching(session, job.id),
        "people": people,
        "archived": archived,
        "stages": pipeline.stage_counts(session, job.id),
        "coverage": coverage.summary(session, job),
        "hiring": {"company": hiring.company_summary(session, session.get(Company, job.hiring_company_id) if job.hiring_company_id else None),
                   "intakes": hiring.intakes(session, job.id), "targets": hiring.targets(session, org_id, reqs)},
    }


def person_page(session: Session, org_id: uuid.UUID, candidate_id: uuid.UUID) -> dict[str, Any]:
    person = session.get(Candidate, candidate_id)
    if person is None or person.org_id != org_id:
        raise LookupError(f"No candidate {candidate_id}")
    # Stable order: newest period first, then by key. Claims from one run share a timestamp, so it cannot break ties.
    claims = list(session.scalars(select(Claim).where(Claim.subject_id == person.id).order_by(
        Claim.valid_from.desc().nulls_last(), Claim.created_at, Claim.natural_key, Claim.id)))
    ev = evidence_for(session, [c.id for c in claims])
    pairs = session.execute(select(CandidateJob, Job).join(Job, Job.id == CandidateJob.job_id).where(CandidateJob.candidate_id == person.id)).all()
    from maindscout.db.models import DocumentSubject

    cited = select(Evidence.document_id).join(Claim, Claim.id == Evidence.claim_id).where(Claim.subject_id == person.id)
    linked = select(DocumentSubject.document_id).where(DocumentSubject.subject_id == person.id)
    documents = session.execute(  # CVs first (the header's CV button opens the first), newest first
        select(Document).where(Document.id.in_(cited) | Document.id.in_(linked))
        .order_by((Document.doc_type != "cv"), Document.created_at.desc()))
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in claims:
        grouped[c.claim_type].append(claim_view(c, ev[c.id]))
    return {
        "id": str(person.id), "name": names(session, [person.id])[person.id],
        "merged_into_id": str(person.merged_into_id) if person.merged_into_id else None,
        "archived": {"at": _iso(person.archived_at), "reason": (person.archived_reason or {}).get("text")} if person.archived_at else None,
        "coverage_override": person.coverage_override,
        "profile": profiles.as_view(profiles.latest(session, person.id)),
        "relationship": relationship.summary_for_person(session, org_id, person.id),
        "blocks": pipeline.blocks_for_person(session, org_id, person.id),
        "freshness": freshness.of_person(session, org_id, person.id),
        "messages": messages.for_person(session, org_id, person.id),
        "client_contacts": messages.contacts_for_jobs(session, org_id, [j for _, j in pairs]),
        "classifications": profiles.labels_view(session, org_id, person.id),
        "claims": grouped,
        "jobs": [{"job_id": str(j.id), "title": j.title, "band": p.triage_band, "reason": p.triage_reason, "state": p.pair_state}
                 for p, j in pairs],
        "documents": [{"id": str(d.id), "filename": d.filename, "doc_type": d.doc_type, "needs_vision": d.needs_vision,
                       "as_of": _iso(d.as_of)} for (d,) in documents],
        "open_decisions": [str(d) for d in session.scalars(select(Decision.id).where(
            Decision.subject_id == person.id, Decision.sealed_at.is_(None)))],
    }


def _side(claim: Claim, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    first = evidence[0] if evidence else {}
    return {"claim_id": str(claim.id), "claim_type": claim.claim_type, "status": claim.status, "payload": claim.payload,
            "snippet": first.get("snippet"), "page": first.get("page"), "filename": first.get("filename")}


def inbox(session: Session, org_id: uuid.UUID, job_id: uuid.UUID | None = None, band: str | None = "priority") -> list[dict[str, Any]]:
    """Only the questions the system may not answer itself.

    Scope: people on the given job in the given band (default priority); without a job, everyone.
    Order: blocking items (identity notes, suspect contacts) first, then oldest first. Never by score.
    """
    if job_id:
        q = select(CandidateJob.candidate_id).where(CandidateJob.job_id == job_id, CandidateJob.org_id == org_id)
        if band and band != "all":
            q = q.where(CandidateJob.triage_band == band)
        scope = list(session.scalars(q.join(Candidate, Candidate.id == CandidateJob.candidate_id)
                                     .where(Candidate.archived_at.is_(None))))
    else:
        # Archived people (outside coverage) ask nothing of the recruiter until someone brings them back.
        scope = list(session.scalars(select(Candidate.id).where(Candidate.org_id == org_id, Candidate.archived_at.is_(None))))
    if not scope:
        return []
    who = names(session, scope)
    items: list[dict[str, Any]] = []

    decisions = list(session.scalars(select(Decision).where(
        Decision.org_id == org_id, Decision.sealed_at.is_(None), Decision.subject_id.in_(scope))))
    decisions += list(session.scalars(select(Decision).where(
        Decision.org_id == org_id, Decision.sealed_at.is_(None), Decision.type == "company_same",
        Decision.context["candidate_id"].astext.in_([str(c) for c in scope]))))
    links = defaultdict(list)
    for item in session.scalars(select(DecisionItem).where(DecisionItem.decision_id.in_([d.id for d in decisions] or [None]))):
        links[item.decision_id].append(item)
    claim_ids = [i.claim_id for its in links.values() for i in its]
    claims = {c.id: c for c in session.scalars(select(Claim).where(Claim.id.in_(claim_ids or [None])))}
    ev = evidence_for(session, list(claims))
    # "Who is this?" cards: the possible matches' names and each person's CV, two queries for all cards.
    notes = [d for d in decisions if d.type == "identity_note"]
    note_names = names(session, list({uuid.UUID(i) for d in notes for i in d.context.get("candidate_ids", [])}))
    note_docs = dict(session.execute(
        select(DocumentSubject.subject_id, func.min(func.cast(DocumentSubject.document_id, String)))
        .where(DocumentSubject.subject_id.in_([d.subject_id for d in notes] or [None]))
        .group_by(DocumentSubject.subject_id)).all()) if notes else {}
    for d in decisions:
        sides = [_side(claims[i.claim_id], ev[i.claim_id]) for i in links[d.id]]
        entry = {"id": str(d.id), "kind": d.type, "blocking": d.type in BLOCKING, "created_at": _iso(d.created_at),
                 "subject": {"id": str(d.subject_id), "name": who.get(d.subject_id)}, "context": d.context}
        if d.type == "company_same":
            entry["subject"] = {"id": d.context.get("candidate_id"), "name": who.get(uuid.UUID(d.context["candidate_id"])) if d.context.get("candidate_id") else None}
        if d.type == "identity_note":
            others = [uuid.UUID(i) for i in d.context.get("candidate_ids", [])]
            entry["possibly"] = [{"id": str(i), "name": note_names.get(i)} for i in others]
            doc = note_docs.get(d.subject_id)
            entry["document_id"] = str(doc) if doc else None
        if d.type == "revision_diff":
            old, new = d.context.get("old_view", {}), d.context.get("new_view", {})
            entry.update(claim_id=sides[0]["claim_id"], old_view=old, new_view=new,
                         changed_paths=sorted(k for k in set(old) | set(new) if old.get(k) != new.get(k)))
        elif d.type in ("duplicate_stint", "contradiction") and len(sides) == 2:
            entry.update(left=sides[0], right=sides[1])
        items.append(entry)

    suspect = session.scalars(select(Claim).where(
        Claim.org_id == org_id, Claim.claim_type == "ContactClaim", Claim.status == "proposed",
        Claim.subject_id.in_(scope), Claim.flags["possible_ocr_identifier"].astext == "true"))
    suspect = list(suspect)
    ev_suspect = evidence_for(session, [c.id for c in suspect if c.id not in ev])
    for c in suspect:
        e = ev.get(c.id) or ev_suspect.get(c.id) or []
        items.append({"id": f"contact:{c.id}", "kind": "ocr_contact", "blocking": True, "created_at": _iso(c.created_at),
                      "subject": {"id": str(c.subject_id), "name": who.get(c.subject_id)}, "claim": _side(c, e),
                      "note": (e[0] if e else {}).get("note")})

    items.sort(key=lambda i: (not i["blocking"], i["created_at"] or ""))
    return items


def list_people(session: Session, org_id: uuid.UUID) -> list[dict[str, Any]]:
    """Everyone on the desk, newest first, with the jobs they are on. People on no job are the unassigned pool."""
    people = list(session.scalars(select(Candidate).where(Candidate.org_id == org_id).order_by(Candidate.created_at.desc())))
    who = names(session, [p.id for p in people])
    pairs = defaultdict(list)
    for pair, title in session.execute(select(CandidateJob, Job.title).join(Job, Job.id == CandidateJob.job_id).where(CandidateJob.org_id == org_id)):
        pairs[pair.candidate_id].append({"job_id": str(pair.job_id), "title": title, "band": pair.triage_band, "state": pair.pair_state})
    docs = dict(session.execute(
        select(DocumentSubject.subject_id, func.min(func.cast(DocumentSubject.document_id, String)))
        .where(DocumentSubject.org_id == org_id, DocumentSubject.subject_type == "candidate")
        .group_by(DocumentSubject.subject_id)).all())
    from maindscout.db.models import CandidateTag

    stale = freshness.stale_ids(session, org_id)
    tags: dict = defaultdict(list)
    for cid, tag in session.execute(select(CandidateTag.candidate_id, CandidateTag.tag).where(CandidateTag.org_id == org_id)):
        tags[cid].append(tag)
    return [{"id": str(p.id), "name": who.get(p.id), "created_at": _iso(p.created_at), "jobs": pairs.get(p.id, []),
             "archived": (p.archived_reason or {}).get("text") if p.archived_at else None, "tags": sorted(tags.get(p.id, [])),
             "stale": p.id in stale,
             "document_id": docs.get(p.id)} for p in people]


def _gap_rows(session: Session, org_id: uuid.UUID, job: Job, candidate_id: uuid.UUID):
    return _gap_rows_many(session, org_id, job, [candidate_id])[candidate_id]


def live_requirements(session: Session, job_id: uuid.UUID) -> list[Claim]:
    return list(session.scalars(select(Claim).where(Claim.subject_id == job_id, Claim.claim_type == "JobRequirementClaim",
                                                    Claim.status.in_(LIVE)).order_by(Claim.created_at, Claim.natural_key)))


def _gap_rows_many(session: Session, org_id: uuid.UUID, job: Job, candidate_ids: list[uuid.UUID],
                   with_snippets: bool = True, preloaded: tuple[list, dict] | None = None) -> dict[uuid.UUID, list]:
    """The gap table of each person against one job: one query for the requirements, one for everyone's facts, one
    for their evidence (not three per person). Matching and snapshots never show snippets: they skip the evidence."""
    from maindscout.domain import gaps

    if preloaded is not None:  # (the job's live requirements, {candidate: live claims}), e.g. from process.pair_inputs
        reqs, claims = preloaded[0], {cid: list(preloaded[1].get(cid, [])) for cid in candidate_ids}
    else:
        reqs = live_requirements(session, job.id)
        claims = {cid: [] for cid in candidate_ids}
    requirements = [{"id": str(r.id), "payload": r.payload} for r in reqs]
    if candidate_ids and preloaded is None:
        for c in session.scalars(select(Claim).where(Claim.org_id == org_id, Claim.subject_id.in_(candidate_ids),
                                                     Claim.status.in_(LIVE))):
            claims[c.subject_id].append(c)
    ev = evidence_for(session, [c.id for cs in claims.values() for c in cs]) if with_snippets else defaultdict(list)
    out = {}
    for cid, mine in claims.items():
        facts = [gaps.Fact(str(c.id), c.claim_type, c.approved_view or c.payload, c.status, c.valid_from, c.valid_to,
                           (ev[c.id][-1]["snippet"] if ev[c.id] else None)) for c in mine]  # newest reading
        out[cid] = gaps.gap_table(requirements, facts)
    return out


def gap_counts(session: Session, org_id: uuid.UUID, job: Job, candidate_id: uuid.UUID) -> dict[str, int]:
    from maindscout.domain import gaps

    return gaps.counts(_gap_rows(session, org_id, job, candidate_id))


def gap_page(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, candidate_id: uuid.UUID) -> dict[str, Any]:
    """A person against a job: every requirement as evidence / missing / conflict / question. No number."""
    from maindscout.domain import gaps

    job = session.get(Job, job_id)
    person = session.get(Candidate, candidate_id)
    if job is None or job.org_id != org_id or person is None or person.org_id != org_id:
        raise LookupError("No such job or person")
    pair = session.scalar(select(CandidateJob).where(CandidateJob.job_id == job.id, CandidateJob.candidate_id == person.id))
    if pair is None:
        raise LookupError("This person is not on this job")
    rows = _gap_rows(session, org_id, job, person.id)
    return {
        "job": {"id": str(job.id), "title": job.title, "hiring_company": job.hiring_company},
        "person": {"id": str(person.id), "name": names(session, [person.id])[person.id]},
        "band": pair.triage_band, "reason": pair.triage_reason, "overridden_by": pair.band_overridden_by,
        "state": pair.pair_state, "outcome": pair.outcome, "match": pair.match,
        "counts": gaps.counts(rows),
        "coverage": _coverage(rows),
        "history": pair_history(session, pair.id),
        "rows": [{
            "requirement_id": r.requirement_id, "requirement": r.requirement, "kind": r.kind, "strength": r.strength,
            "distinctive": r.distinctive, "status": r.status, "detail": r.detail, "official": r.official, "token": r.token,
            "facts": [{"id": f.id, "claim_type": f.claim_type, "status": f.status, "snippet": f.snippet} for f in r.facts[:4]],
        } for r in rows],
    }


def pair_history(session: Session, pair_id: uuid.UUID) -> list[dict[str, Any]]:
    """Every change to a pair, oldest first: what changed, why, what caused it, who."""
    from maindscout.db.models import PairEvent

    events = session.scalars(select(PairEvent).where(PairEvent.pair_id == pair_id).order_by(PairEvent.seq))
    return [{"kind": e.kind, "from": e.from_value, "to": e.to_value, "reason": e.reason, "cause": e.cause,
             "actor": e.actor, "at": _iso(e.created_at)} for e in events]


def _coverage(rows) -> dict[str, Any]:
    from maindscout.domain import coverage

    return coverage.coverage(rows).as_dict()


def _gap_summary(rows: list) -> dict[str, Any]:
    from maindscout.domain import gaps

    return {"gaps": gaps.counts(rows), "coverage": _coverage(rows)}
