"""Evidence checks on strong matches (owner, 2026-10-17: "automatic on strong matches, name + company allowed").

- **When:** someone found on the web becomes a strong match (band priority) on a role, by the rules or by the owner's
  choice: one check, in the background (`maybe_queue`, called by matching). Again only after 90 days. "Check deeper"
  on any suggestion runs one by hand. Off with EVIDENCE_AUTO=false.
- **What it reads:** the links on their own profile, and a web search for their name with their current company
  (`intelligence/evidence.py` decides which pages are about them and reads them against the role's requirements).
- **What it keeps:** only pages that support or weaken the match, stored as the person's `web_page` documents (erased
  with them). A supported skill becomes a proposed `SkillClaim` quoted from the page, so the ordinary rules re-judge
  the match; nothing is believed until a person approves it. What weakens the match is never turned into a band by
  the machine: it is shown on the card for the owner to decide. The findings, the pages looked at and the cost are
  the task's result (also erased with the person).
- **Cost:** about 1-3 cents a person (a search, a page or two, one model call), inside the role's sourcing budget.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.api import costs, documents
from maindscout.db.models import (
    Candidate,
    CandidateJob,
    Claim,
    Document,
    DocumentSubject,
    ExtractionArtifact,
    IntelligenceRun,
    Job,
    SourcingHit,
    Task,
)
from maindscout.intelligence import evidence as engine
from maindscout.intelligence import exa, spans

LIVE = ("proposed", "approved")
KIND = "evidence_check"
PURPOSE = "sourcing_evidence_check"
RECHECK_AFTER = timedelta(days=90)
COST_ESTIMATE = 0.03
SEARCH_RESULTS = 6
# What a public page can show: skills, and the industry, background and concrete asks that matter. The kind of work,
# the level, years, education, employment and places are the matching rules' (over the career profile) or the call's.
CHECKED = {"skill": None, "domain": ("must", "deal_breaker", "strong_plus"), "employer": ("must", "deal_breaker", "strong_plus"),
           "other": ("must", "deal_breaker", "strong_plus")}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def key(job_id, candidate_id) -> str:
    return f"evidence:{job_id}:{candidate_id}"


def _auto() -> bool:
    from maindscout.settings import env

    return (env("EVIDENCE_AUTO", "true") or "").lower() not in ("0", "false", "no", "off")


def latest(session: Session, job_id, candidate_id) -> Task | None:
    return session.scalar(select(Task).where(Task.kind == KIND, Task.dedupe_key == key(job_id, candidate_id))
                          .order_by(Task.created_at.desc()).limit(1))


def due(session: Session, job_id, candidate_id, now: datetime | None = None) -> bool:
    t = latest(session, job_id, candidate_id)
    if t is None:
        return True
    if t.status in ("queued", "running"):
        return False
    return (t.finished_at or t.created_at) < (now or _now()) - RECHECK_AFTER


def found_on_the_web(session: Session, job_id, candidate_id) -> bool:
    return session.scalar(select(SourcingHit.id).where(SourcingHit.job_id == job_id, SourcingHit.candidate_id == candidate_id,
                                                       SourcingHit.channel == "exa_people").limit(1)) is not None


def queue(session: Session, org_id: uuid.UUID, job_id, candidate_id, actor: str = "system") -> Task:
    from maindscout.api import tasks

    return tasks.enqueue(session, org_id, KIND, {"job_id": str(job_id), "candidate_id": str(candidate_id), "actor": actor},
                         priority=130, dedupe_key=key(job_id, candidate_id))


def maybe_queue(session: Session, pair: CandidateJob, band: str) -> bool:
    """A strong match found on the web gets its check, once per 90 days (called from matching, so it stays cheap)."""
    if band != "priority" or not _auto():
        return False
    if not found_on_the_web(session, pair.job_id, pair.candidate_id) or not due(session, pair.job_id, pair.candidate_id):
        return False
    queue(session, pair.org_id, pair.job_id, pair.candidate_id)
    return True


# --- the check -------------------------------------------------------------------------------------------------------


def _name(session: Session, cid: uuid.UUID) -> str | None:
    c = session.scalar(select(Claim).where(Claim.subject_id == cid, Claim.claim_type == "IdentityClaim", Claim.status.in_(LIVE))
                       .order_by(Claim.status.asc(), Claim.created_at.desc()).limit(1))  # approved before proposed
    return (c.approved_view or c.payload).get("full_name") if c else None


def _career(session: Session, org_id: uuid.UUID, cid: uuid.UUID) -> tuple[list[str], str | None]:
    """(their employers, current first; their current title)."""
    steps = list(session.scalars(select(Claim).where(Claim.org_id == org_id, Claim.subject_id == cid,
                                                     Claim.claim_type == "CareerStepClaim", Claim.status.in_(LIVE))))
    steps.sort(key=lambda c: (c.valid_to is not None, -(c.valid_from or date.min).toordinal()))
    names = [((c.approved_view or c.payload).get("company") or {}).get("raw_name") for c in steps]
    current = next(((c.approved_view or c.payload).get("title_raw") for c in steps if c.valid_to is None), None)
    return [n for n in dict.fromkeys(names) if n], current


def _profile_text(session: Session, cid: uuid.UUID) -> str:
    row = session.scalar(select(ExtractionArtifact.content).join(Document, Document.id == ExtractionArtifact.document_id)
                         .join(DocumentSubject, DocumentSubject.document_id == Document.id)
                         .where(DocumentSubject.subject_id == cid, Document.doc_type == "web_profile")
                         .order_by(Document.created_at.desc()).limit(1))
    return row or ""


def _requirements(session: Session, job: Job) -> list[dict[str, Any]]:
    from maindscout.api.queries import live_requirements

    out = []
    for c in live_requirements(session, job.id):
        p = c.approved_view or c.payload
        cat = p.get("category")
        if cat not in CHECKED or p.get("mobility") or (CHECKED[cat] and p.get("strength") not in CHECKED[cat]):
            continue
        out.append({"id": str(c.id), "text": p.get("text_raw") or "", "strength": p.get("strength") or "unknown",
                    "category": p.get("category"), "token": p.get("normalized_token") if p.get("category") == "skill" else None})
    order = {"must": 0, "deal_breaker": 0, "strong_plus": 1, "nice": 2}
    out.sort(key=lambda r: (order.get(r["strength"], 3), r["category"] != "skill"))
    return out


def _store(session: Session, blobs, org_id: uuid.UUID, cid: uuid.UUID, page: engine.Page) -> tuple[Document, ExtractionArtifact]:
    """A page that says something about their work, kept as their document (erased with them)."""
    text = page.text.strip()
    label = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in page.url.split("://", 1)[-1])[:80].strip("-")
    # Each person keeps their own copy (a team page about two people is two documents), so erasing one never waits on
    # the other; the text layer is the page itself.
    data = f"Read for an evidence check of {cid}\n{page.url}\n\n{text}".encode("utf-8")
    doc, reused = documents.upload_document(session, blobs, org_id=org_id, data=data, filename=f"{label}.txt",
                                            media_type="text/plain", doc_type_hint="web_page")
    artifact = session.scalar(select(ExtractionArtifact).where(ExtractionArtifact.document_id == doc.id).limit(1))
    if artifact is None:
        doc.source_authority, doc.transformed_by_third_party = "third_party_assertion", True
        artifact = ExtractionArtifact(org_id=org_id, document_id=doc.id, method="text_layer", content=text,
                                      annotations=[{"page": 1, "kind": "link", "uri": page.url}],
                                      content_sha=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                                      produced_with={"name": "exa", "reader": engine.READER_VERSION, "url": page.url,
                                                     "published": page.published})
        session.add(artifact)
        doc.as_of, doc.as_of_basis, doc.status = date.today(), "upload_time", "processed"
        session.flush()
    if session.get(DocumentSubject, (doc.id, "candidate", cid)) is None:
        session.add(DocumentSubject(document_id=doc.id, subject_type="candidate", subject_id=cid, org_id=org_id,
                                    established_by="evidence_check"))
        session.flush()
    return doc, artifact


def run(session: Session, blobs, org_id: uuid.UUID, job_id: uuid.UUID, candidate_id: uuid.UUID, caller, client,
        task_id=None) -> dict[str, Any]:
    from maindscout.api import autosource, process

    job, person = session.get(Job, job_id), session.get(Candidate, candidate_id)
    if job is None or job.org_id != org_id or person is None or person.org_id != org_id:
        return {"status": "skipped", "reason": "no such role or person"}
    if person.do_not_contact_at is not None:
        return {"status": "skipped", "reason": "they asked not to be contacted"}
    plan = autosource.current_plan(session, job.id)
    if plan is not None and (why := autosource._budget_left(session, org_id, job, plan, COST_ESTIMATE)):
        return {"status": "skipped", "reason": "the role's sourcing budget is used up" if why == "budget" else "the desk's sourcing budget is used up"}
    name = _name(session, candidate_id)
    if not name:
        return {"status": "skipped", "reason": "no name to search for"}
    employers, title = _career(session, org_id, candidate_id)
    pages: list[engine.Page] = []
    spent = 0.0
    links = engine.profile_links(_profile_text(session, candidate_id))
    if links:
        got = exa.fetch(caller, links, text_chars=engine.PAGE_CHARS)
        spent += got.usd
        pages += [engine.Page(f.url, f.title, f.text, True, f.published) for f in got.found if f.text.strip()]
    found = exa.search(caller, engine.search_query(name, employers[0] if employers else None), None, num_results=SEARCH_RESULTS,
                       text_chars=engine.PAGE_CHARS, exclude_domains=list(engine.PROFILE_COPIES))
    spent += found.usd
    have = {p.url for p in pages}
    pages += [engine.Page(f.url, f.title, f.text, False, f.published) for f in found.found
              if f.url not in have and f.text.strip() and not engine.profile_copy(f.url)]
    costs.record(session, org_id, PURPOSE, {"model": "exa", "usd": spent, "sources": len(pages)},
                 subject_type="job", subject_id=job.id, task_id=task_id)
    looked = [{"url": p.url, "title": (p.title or "")[:120], "theirs": engine.same_person(p, name, employers),
               "from_profile": p.from_profile} for p in pages]
    accepted = [p for p in pages if engine.same_person(p, name, employers)][:engine.MAX_PAGES]
    base = {"status": "done", "query": engine.search_query(name, employers[0] if employers else None), "pages": looked,
            "findings": [], "facts_added": 0}
    if not accepted:
        return base | {"outcome": "nothing_found", "why": "no public page about them beyond their profile",
                       "usd": round(spent, 4)}
    reqs = _requirements(session, job)
    who = f"{name}, {title} at {employers[0]}" if title and employers else name
    reading = engine.read(accepted, who, reqs, client)
    costs.record(session, org_id, PURPOSE, reading.cost, subject_type="job", subject_id=job.id, task_id=task_id)
    by_id = {r["id"]: r for r in reqs}
    stored: dict[int, tuple[Document, ExtractionArtifact, IntelligenceRun]] = {}
    added = 0
    findings = []
    for f in reading.findings:
        page = accepted[f.page]
        if f.page not in stored:
            doc, artifact = _store(session, blobs, org_id, candidate_id, page)
            run_ = IntelligenceRun(org_id=org_id, document_id=doc.id, trigger=KIND, status="committed", committed_at=_now(),
                                   version_manifest={"reader": engine.READER_VERSION, "model": reading.cost.get("model"),
                                                     "job_id": str(job.id)})
            session.add(run_)
            session.flush()
            stored[f.page] = (doc, artifact, run_)
        doc, artifact, run_ = stored[f.page]
        if f.effect == "supports" and f.skill:
            where = spans.locate(artifact.content, f.quote)
            span = {"artifact_id": str(artifact.id), "page": where.page, "char_start": where.char_start,
                    "char_end": where.char_end, "snippet": where.snippet} if where else None
            seen = (page.published or "")[:10] or None
            payload = {"raw_label": f.skill, "normalized_skill": f.skill, "last_evidenced_as_of": seen}
            _, created = process._write_claim(session, doc, run_, "candidate", candidate_id, "SkillClaim", payload,
                                              process.natural_key(candidate_id, "SkillClaim", payload), span,
                                              origin="independent_web", authority="third_party_assertion")
            added += created
        findings.append({"requirement": by_id[f.requirement_id]["text"], "strength": by_id[f.requirement_id]["strength"],
                         "effect": f.effect, "because": f.because, "text": f.text, "quote": f.quote, "url": page.url,
                         "skill": f.skill})
    pair = session.scalar(select(CandidateJob).where(CandidateJob.job_id == job.id, CandidateJob.candidate_id == candidate_id))
    before = pair.triage_band if pair else None
    if added:
        process.retriage_candidate(session, org_id, candidate_id, {"act": "evidence_check"}, "evidence check")
    outcome = engine.outcome(reading.findings, {r["id"]: r["strength"] for r in reqs})
    return base | {"outcome": outcome, "findings": findings, "facts_added": added, "band_before": before,
                   "band_after": pair.triage_band if pair else None,
                   "usd": round(spent + float(reading.cost.get("usd") or 0), 4), "rejected": len(reading.rejected)}


# --- for the Sourcing tab ----------------------------------------------------------------------------------------------


def summaries(session: Session, job_id: uuid.UUID, candidate_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, Any]]:
    """The latest check of each person on this role, as the card shows it."""
    if not candidate_ids:
        return {}
    wanted = {key(job_id, c): c for c in candidate_ids}
    out: dict[uuid.UUID, dict[str, Any]] = {}
    for t in session.scalars(select(Task).where(Task.kind == KIND, Task.dedupe_key.in_(list(wanted))).order_by(Task.created_at)):
        r = t.result or {}
        out[wanted[t.dedupe_key]] = {"status": t.status if t.status != "done" else r.get("status", "done"),
                                     "at": (t.finished_at or t.created_at).isoformat() if (t.finished_at or t.created_at) else None,
                                     "outcome": r.get("outcome"), "reason": r.get("reason") or r.get("why"),
                                     "findings": (r.get("findings") or [])[:4],
                                     "pages": sum(1 for p in r.get("pages") or [] if p.get("theirs")),
                                     "looked": len(r.get("pages") or []), "facts_added": r.get("facts_added", 0),
                                     "usd": r.get("usd"), "error": (t.error or "")[:200] if t.status == "failed" else None}
    return out
