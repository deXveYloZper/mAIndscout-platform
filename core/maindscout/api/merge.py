"""Same person: two records of one person made one, on a human's word. Never automatic (a wrong merge is worse than a
duplicate). The older record is kept; everything of the other moves onto it: facts (a fact both had is kept once),
documents, jobs (on a job both were on, the history of both is kept on one), Brief questions, notes, tags, blocks,
messages, call reviews. Every move is recorded on a `person_merge` row, so the merge can be undone exactly.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from maindscout.db.models import (
    Activity,
    BriefItem,
    CallReview,
    Candidate,
    CandidateJob,
    CandidateTag,
    Claim,
    ClientBlock,
    Decision,
    DocumentSubject,
    ImportRow,
    Message,
    NotSame,
    PairEvent,
    PersonMerge,
    Score,
)

LIVE = ("proposed", "approved")
PAIR_FIELDS = ("triage_band", "triage_reason", "band_overridden_by", "pair_state", "outcome", "match_tier", "match", "version")
STATE_RANK = {s: i for i, s in enumerate(("new", "seen", "contacted", "screened", "submitted", "interviewing", "offer", "placed"))}


class MergeError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _person(session: Session, org_id, cid) -> Candidate:
    p = session.get(Candidate, cid)
    if p is None or p.org_id != org_id:
        raise LookupError(f"No candidate {cid}")
    if p.merged_into_id is not None:
        raise MergeError("This record was already merged into another person")
    return p


def _ids(rows) -> list[str]:
    return [str(r.id) for r in rows]


def merge(session: Session, org_id, a_id: uuid.UUID, b_id: uuid.UUID, actor: str) -> PersonMerge:
    """Make two records one. The older record is kept. Re-matches the person once at the end."""
    from maindscout.api import profiles
    from maindscout.api.process import natural_key

    if a_id == b_id:
        raise MergeError("That is the same record")
    a, b = _person(session, org_id, a_id), _person(session, org_id, b_id)
    keep, drop = sorted((a, b), key=lambda p: (p.created_at, str(p.id)))
    lo, hi = sorted((keep.id, drop.id), key=str)
    if session.get(NotSame, (lo, hi)) is not None:
        raise MergeError("A person said these are different people")
    moved: dict[str, Any] = {"name_variants": list(drop.name_variants or [])}

    # Facts: each moves; one the kept record already has (same natural key) is kept once, the copy superseded.
    claims = []
    for c in session.scalars(select(Claim).where(Claim.subject_id == drop.id).order_by(Claim.created_at)):
        entry = {"id": str(c.id), "natural_key": c.natural_key, "status": c.status,
                 "superseded_by": str(c.superseded_by) if c.superseded_by else None}
        try:
            key = natural_key(keep.id, c.claim_type, c.approved_view or c.payload, *(
                (d.isoformat() if d else None) for d in (c.valid_from, c.valid_to)))
        except (ValueError, KeyError):
            key = c.natural_key.replace(str(drop.id), str(keep.id))
        c.subject_id, c.natural_key = keep.id, key
        if c.status in LIVE:
            twin = session.scalar(select(Claim).where(Claim.subject_id == keep.id, Claim.claim_type == c.claim_type,
                                                      Claim.natural_key == key, Claim.id != c.id, Claim.status.in_(LIVE)))
            if twin is not None:
                if c.status == "approved" and twin.status == "proposed":
                    twin_entry = {"id": str(twin.id), "status": twin.status, "superseded_by": None}
                    moved.setdefault("kept_claims", []).append(twin_entry)
                    twin.status, twin.superseded_by = "superseded", c.id
                else:
                    c.status, c.superseded_by = "superseded", twin.id
        claims.append(entry)
    moved["claims"] = claims

    docs = list(session.scalars(select(DocumentSubject).where(DocumentSubject.subject_id == drop.id)))
    moved["documents"] = [str(d.document_id) for d in docs]
    for d in docs:
        if session.get(DocumentSubject, (d.document_id, d.subject_type, keep.id)) is None:
            session.execute(update(DocumentSubject).where(DocumentSubject.document_id == d.document_id,
                                                          DocumentSubject.subject_id == drop.id).values(subject_id=keep.id))

    # Jobs. On a job both were on, the kept pair stays and takes the further stage; the other pair's history moves
    # onto it, and that pair row (now empty) goes. Its fields are recorded so undo can bring it back.
    pairs, folded = [], []
    for p in list(session.scalars(select(CandidateJob).where(CandidateJob.candidate_id == drop.id))):
        mine = session.scalar(select(CandidateJob).where(CandidateJob.candidate_id == keep.id, CandidateJob.job_id == p.job_id))
        if mine is None:
            p.candidate_id = keep.id
            pairs.append(str(p.id))
            continue
        events = list(session.scalars(select(PairEvent.id).where(PairEvent.pair_id == p.id)))
        folded.append({"id": str(p.id), "job_id": str(p.job_id), "created_at": p.created_at.isoformat(),
                       "fields": {f: getattr(p, f) for f in PAIR_FIELDS}, "events": [str(e) for e in events],
                       "kept_pair": str(mine.id), "kept_fields": {f: getattr(mine, f) for f in PAIR_FIELDS}})
        if STATE_RANK.get(p.pair_state, -1) > STATE_RANK.get(mine.pair_state, -1):
            mine.pair_state, mine.outcome = p.pair_state, p.outcome
        session.execute(update(PairEvent).where(PairEvent.pair_id == p.id).values(pair_id=mine.id))
        session.flush()
        session.execute(text("SET LOCAL maindscout.erasure = 'on'"))  # the one other place a pair row may go
        session.delete(p)
        session.flush()
        session.execute(text("SET LOCAL maindscout.erasure = 'off'"))
    moved["pairs"], moved["folded_pairs"] = pairs, folded

    # Brief questions: an open one the kept record also has is set aside (answers always move as they are).
    briefs = []
    have = {(b.job_id, b.source_key) for b in session.scalars(select(BriefItem).where(BriefItem.candidate_id == keep.id))}
    for item in session.scalars(select(BriefItem).where(BriefItem.candidate_id == drop.id)):
        briefs.append({"id": str(item.id), "status": item.status})
        if (item.job_id, item.source_key) in have and item.status in ("open", "asked"):
            item.status = "dismissed"
        item.candidate_id = keep.id
    moved["brief_items"] = briefs

    tags_have = set(session.scalars(select(CandidateTag.tag).where(CandidateTag.candidate_id == keep.id)))
    tags, dropped_tags = [], []
    for t in list(session.scalars(select(CandidateTag).where(CandidateTag.candidate_id == drop.id))):
        if t.tag in tags_have:
            dropped_tags.append(t.tag)
            session.delete(t)
        else:
            t.candidate_id = keep.id
            tags.append(str(t.id))
    moved["tags"], moved["dropped_tags"] = tags, dropped_tags

    def move(model, column, name: str) -> None:
        rows = list(session.scalars(select(model).where(getattr(model, column) == drop.id)))
        for r in rows:
            setattr(r, column, keep.id)
        moved[name] = _ids(rows)

    move(Activity, "subject_id", "activities")  # only person activities carry a person's id
    move(ClientBlock, "candidate_id", "client_blocks")
    move(Message, "candidate_id", "messages")
    move(Message, "about_candidate_id", "messages_about")
    move(CallReview, "candidate_id", "call_reviews")
    move(ImportRow, "candidate_id", "import_rows")
    move(Score, "candidate_id", "scores")
    move(Decision, "subject_id", "decisions")

    # The question that asked who this is: answered.
    sealed = []
    for d in session.scalars(select(Decision).where(Decision.org_id == org_id, Decision.type == "identity_note",
                                                    Decision.sealed_at.is_(None), Decision.subject_id == keep.id)):
        ids = set(d.context.get("candidate_ids", []))
        if ids and ids <= {str(drop.id), str(keep.id)}:  # it asked only about these two
            d.sealed_at, d.resolution = _now(), {"action": "merged", "by": actor, "kept": str(keep.id), "merged": str(drop.id)}
            sealed.append(str(d.id))
    moved["sealed_decisions"] = sealed

    keep.name_variants = list(dict.fromkeys([*(keep.name_variants or []), *(drop.name_variants or [])]))
    drop.merged_into_id = keep.id
    row = PersonMerge(org_id=org_id, keep_id=keep.id, drop_id=drop.id, moved=moved, merged_by=actor)
    session.add(row)
    session.flush()

    from maindscout.api import coverage, relationship
    from maindscout.api.process import retriage_candidate

    profiles.build(session, org_id, keep.id)
    coverage.evaluate(session, org_id, keep.id, {"act": "merge", "merge_id": str(row.id)}, actor)
    retriage_candidate(session, org_id, keep.id, {"act": "merge", "merge_id": str(row.id)}, actor)
    relationship.log(session, org_id, "candidate", keep.id, "note", "Two records of this person merged into one", actor)
    return row


def undo(session: Session, org_id, merge_id: uuid.UUID, actor: str) -> PersonMerge:
    """Put everything back where it was before the merge. Changes made since then to moved rows stay with them."""
    from maindscout.api import profiles
    from maindscout.api.process import retriage_candidate

    row = session.get(PersonMerge, merge_id)
    if row is None or row.org_id != org_id:
        raise LookupError(f"No merge {merge_id}")
    if row.undone_at is not None:
        raise MergeError("This merge was already undone")
    keep, drop = session.get(Candidate, row.keep_id), session.get(Candidate, row.drop_id)
    m = row.moved
    U = uuid.UUID

    for e in m.get("claims", []):
        c = session.get(Claim, U(e["id"]))
        if c is not None:
            c.subject_id, c.natural_key = drop.id, e["natural_key"]
            if c.status == "superseded" and e["status"] in LIVE:
                c.status, c.superseded_by = e["status"], U(e["superseded_by"]) if e["superseded_by"] else None
    for e in m.get("kept_claims", []):
        c = session.get(Claim, U(e["id"]))
        if c is not None and c.status == "superseded":
            c.status, c.superseded_by = e["status"], None
    for doc in m.get("documents", []):
        session.execute(update(DocumentSubject).where(DocumentSubject.document_id == U(doc),
                                                      DocumentSubject.subject_id == keep.id).values(subject_id=drop.id))
    for pid in m.get("pairs", []):
        p = session.get(CandidateJob, U(pid))
        if p is not None:
            p.candidate_id = drop.id
    for f in m.get("folded_pairs", []):
        p = CandidateJob(id=U(f["id"]), org_id=org_id, candidate_id=drop.id, job_id=U(f["job_id"]),
                         created_at=datetime.fromisoformat(f["created_at"]), **f["fields"])
        session.add(p)
        session.flush()
        session.execute(update(PairEvent).where(PairEvent.id.in_([U(e) for e in f["events"]])).values(pair_id=p.id))
        mine = session.get(CandidateJob, U(f["kept_pair"]))
        if mine is not None:
            mine.pair_state, mine.outcome = f["kept_fields"]["pair_state"], f["kept_fields"]["outcome"]
    for e in m.get("brief_items", []):
        b = session.get(BriefItem, U(e["id"]))
        if b is not None:
            b.candidate_id = drop.id
            if b.status == "dismissed" and e["status"] != "dismissed":
                b.status = e["status"]
    for tid in m.get("tags", []):
        t = session.get(CandidateTag, U(tid))
        if t is not None:
            t.candidate_id = drop.id
    for tag in m.get("dropped_tags", []):
        session.add(CandidateTag(org_id=org_id, candidate_id=drop.id, tag=tag, created_by=actor))
    for name, model, column in (("activities", Activity, "subject_id"), ("client_blocks", ClientBlock, "candidate_id"),
                                ("messages", Message, "candidate_id"), ("messages_about", Message, "about_candidate_id"),
                                ("call_reviews", CallReview, "candidate_id"), ("import_rows", ImportRow, "candidate_id"),
                                ("scores", Score, "candidate_id"), ("decisions", Decision, "subject_id")):
        for rid in m.get(name, []):
            r = session.get(model, U(rid))
            if r is not None:
                setattr(r, column, drop.id)
    for did in m.get("sealed_decisions", []):
        d = session.get(Decision, U(did))
        if d is not None:
            d.sealed_at, d.resolution = None, None

    keep.name_variants = [n for n in keep.name_variants or [] if n not in m.get("name_variants", [])] or keep.name_variants
    drop.merged_into_id = None
    row.undone_by, row.undone_at = actor, _now()
    session.flush()
    for person in (keep, drop):
        profiles.build(session, org_id, person.id)
        retriage_candidate(session, org_id, person.id, {"act": "unmerge", "merge_id": str(row.id)}, actor)
    return row


def as_dict(row: PersonMerge) -> dict[str, Any]:
    return {"id": str(row.id), "keep_id": str(row.keep_id), "drop_id": str(row.drop_id), "merged_by": row.merged_by,
            "merged_at": row.merged_at.isoformat() if row.merged_at else None, "undone_at": row.undone_at.isoformat() if row.undone_at else None,
            "facts": len(row.moved.get("claims", [])), "documents": len(row.moved.get("documents", [])),
            "jobs": len(row.moved.get("pairs", [])) + len(row.moved.get("folded_pairs", []))}


def merges_of(session: Session, org_id, candidate_id) -> list[PersonMerge]:
    return list(session.scalars(select(PersonMerge).where(PersonMerge.org_id == org_id, PersonMerge.keep_id == candidate_id,
                                                          PersonMerge.undone_at.is_(None)).order_by(PersonMerge.merged_at.desc())))
