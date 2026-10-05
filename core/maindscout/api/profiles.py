"""Career profiles (I3): classify each career step once (one model call per CV), then build the profile by code from
the person's facts and the public company facts, and keep a snapshot whenever those facts change.

Only for people in coverage ([coverage.py](coverage.py)); archived people get nothing.
Classifications are inferred claims (proposed); a recruiter's correction replaces them and wins.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.api import costs, writer
from maindscout.db.models import (PUBLIC_ORG_ID, Candidate, CareerProfile, Claim, ClaimObservation, Company, Document,
                                  DocumentSubject, Evidence, ExtractionArtifact)
from maindscout.domain import profile as rubric
from maindscout.domain.companies import normalize
from maindscout.intelligence import classify as engine
from maindscout.intelligence.llm import LLMClient

LIVE = ("proposed", "approved")


def _live(session: Session, org_id, candidate_id, claim_type: str) -> list[Claim]:
    return list(session.scalars(select(Claim).where(Claim.org_id == org_id, Claim.subject_id == candidate_id,
                                                    Claim.claim_type == claim_type, Claim.status.in_(LIVE))
                                .order_by(Claim.valid_from.desc().nulls_last(), Claim.created_at)))


def _view(c: Claim) -> dict[str, Any]:
    """The official view, with the company link (bookkeeping, set after approval too) taken from the payload."""
    view = c.approved_view or c.payload
    link = ((c.payload or {}).get("company") or {}).get("company_id")
    if c.approved_view and link and isinstance(view.get("company"), dict) and view["company"].get("company_id") != link:
        view = {**view, "company": {**view["company"], "company_id": link}}
    return view


def _cv_text(session: Session, org_id, candidate_id) -> tuple[str, ExtractionArtifact | None]:
    rows = session.execute(select(ExtractionArtifact, Document).join(Document, Document.id == ExtractionArtifact.document_id)
                           .join(DocumentSubject, DocumentSubject.document_id == Document.id)
                           .where(DocumentSubject.subject_id == candidate_id, DocumentSubject.org_id == org_id,
                                  ExtractionArtifact.method == "text_layer")
                           .order_by(Document.created_at.desc())).all()
    if not rows:
        return "", None
    return "\n\n".join(a.content for a, _ in rows), rows[0][0]


def classifications(session: Session, org_id, candidate_id) -> dict[str, Claim]:
    """career claim id -> the classification that counts (a person's correction beats the machine's reading)."""
    out: dict[str, Claim] = {}
    for c in _live(session, org_id, candidate_id, "StepClassificationClaim"):
        key = c.payload["career_claim_id"]
        if key not in out or (c.status == "approved" and out[key].status != "approved"):
            out[key] = c
    return out


def _known(session: Session, payload: dict[str, Any]) -> str | None:
    """What public research says about a step's company, as a hint for the industry (kind and domains only)."""
    company_id = (payload.get("company") or {}).get("company_id")
    company = session.get(Company, uuid.UUID(company_id)) if company_id else None
    facts = company_facts(session, company)
    if facts is None:
        return None
    return ", ".join(([facts.kind] if facts.kind else []) + facts.domains[:4]) or None


def labels_view(session: Session, org_id, candidate_id) -> dict[str, dict[str, Any]]:
    """How each career step is read, as the profile uses it: the level from the title unless a person corrected it."""
    out = {}
    for key, c in classifications(session, org_id, candidate_id).items():
        view = dict(_view(c))
        career = session.get(Claim, uuid.UUID(key))
        if c.status != "approved" and career is not None:
            view["level"] = engine.title_level(_view(career)["title_raw"])
        out[key] = {"claim_id": str(c.id), "status": c.status, **view}
    return out


def classify(session: Session, org_id, candidate_id, client: LLMClient, task_id: uuid.UUID | None = None) -> dict[str, Any]:
    """Label the career steps that have no classification yet. Nothing to do (and nothing paid) when all have one."""
    careers = _live(session, org_id, candidate_id, "CareerStepClaim")
    done = classifications(session, org_id, candidate_id)
    # CV order: current jobs first, then by when they ended.
    todo = sorted((c for c in careers if str(c.id) not in done),
                  key=lambda c: (c.valid_to is not None, -(c.valid_to or date.max).toordinal(), -(c.valid_from or date.min).toordinal()))
    if not todo:
        return {"classified": 0, "skipped": "nothing new"}
    text, artifact = _cv_text(session, org_id, candidate_id)
    if not text:
        return {"classified": 0, "skipped": "no CV text"}
    costs.ensure_budget(session, org_id)
    steps = [{"claim_id": str(c.id), "company": _view(c)["company"]["raw_name"], "title": _view(c)["title_raw"],
              "start": c.valid_from.isoformat()[:7] if c.valid_from else None,
              "end": c.valid_to.isoformat()[:7] if c.valid_to else None,
              "employment_type": _view(c).get("employment_type"), "company_known": _known(session, _view(c))} for c in todo]  # newest first, as CVs are written
    outcome = engine.classify_steps(text, steps, client)
    costs.record(session, org_id, "classify_steps", outcome.cost, subject_type="candidate", subject_id=candidate_id, task_id=task_id)
    today = date.today()
    by_id = {str(c.id): c for c in todo}
    for label in outcome.labels:
        career = by_id[label.claim_id]
        payload = {"career_claim_id": label.claim_id, "role_family": label.role_family, "level": label.level,
                   "domains": label.domains, "signals": label.signals}
        claim = writer.add_claim(session, org_id=org_id, subject_type="candidate", subject_id=candidate_id,
                                 claim_type="StepClassificationClaim", payload=payload, natural_key=f"{label.claim_id}|class",
                                 claim_class="inferred", status="proposed", valid_from=career.valid_from, valid_to=career.valid_to,
                                 temporal_precision=career.temporal_precision, observed_as_of=today)
        quotes = "; ".join(f"{k}: “{q}”" for k, q in label.quotes.items())
        ev = Evidence(org_id=org_id, claim_id=claim.id, evidence_type="inference",
                      document_id=artifact.document_id if artifact else None,
                      locator={"artifact_id": str(artifact.id)} if artifact else {},
                      snippet=quotes or f"{_view(career)['title_raw']} at {_view(career)['company']['raw_name']}",
                      source_authority="candidate_authored", origin="candidate", observed_as_of=today,
                      span_validation={"tier": "paraphrase", "result": "pass", "metric_bucket": "none",
                                       "detail": f"classified by {outcome.cost.get('model')} ({engine.CLASSIFY_PROMPT_VERSION})"})
        session.add(ev)
        session.flush()
        session.add(ClaimObservation(org_id=org_id, claim_id=claim.id, attribute_path=".", value=payload, evidence_id=ev.id,
                                     source_authority="candidate_authored", origin="candidate", observed_as_of=today))
    session.flush()
    return {"classified": len(outcome.labels), "rejected": len(outcome.rejected), "usd": outcome.cost.get("usd", 0)}


# --- inputs for the rubric ------------------------------------------------------------------------


def _d(text: str | None) -> date | None:
    if not text:
        return None
    parts = [int(p) for p in str(text)[:10].split("-") if p.isdigit()]
    if not parts:
        return None
    return date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)


def company_facts(session: Session, company: Company | None) -> rubric.CompanyFacts | None:
    if company is None:
        return None
    return company_facts_many(session, [company]).get(company.id)


def company_facts_many(session: Session, companies: list[Company]) -> dict[uuid.UUID, rubric.CompanyFacts | None]:
    """Public facts of several companies (each with the ones merged into it): two queries, not two per company."""
    wanted = {c.id for c in companies}
    owner = {c: c for c in wanted}
    for child, parent in session.execute(select(Company.id, Company.merged_into_id).where(Company.merged_into_id.in_(wanted or [None]))):
        owner[child] = parent
    claims: dict[uuid.UUID, list[Claim]] = {c: [] for c in wanted}
    for c in session.scalars(select(Claim).where(Claim.org_id == PUBLIC_ORG_ID, Claim.subject_id.in_(list(owner) or [None]),
                                                 Claim.status.in_(LIVE))):
        claims[owner[c.subject_id]].append(c)
    return {cid: _facts_from(rows) for cid, rows in claims.items()}


def _facts_from(rows: list[Claim]) -> rubric.CompanyFacts | None:
    facts = rubric.CompanyFacts()
    seen = False
    for c in rows:
        p, seen = _view(c), True
        if c.claim_type == "CompanyTypeClaim":
            facts.kind = p["type"]
        elif c.claim_type == "CompanyFoundedClaim":
            facts.founded = _d(p["founded"])
        elif c.claim_type == "FundingRoundClaim":
            facts.rounds.append((p["stage"], _d(p.get("date"))))
        elif c.claim_type == "TeamSizeClaim" and p.get("min") is not None:
            facts.team_min = p["min"]
        elif c.claim_type == "CompanyStatusClaim":
            facts.status = p["status"]
        elif c.claim_type == "CompanyDomainClaim":
            facts.domains = p.get("domains", [])
    return facts if seen else None


def inputs(session: Session, org_id, candidate_id) -> tuple[list[rubric.Stint], list[rubric.Education]]:
    labels = classifications(session, org_id, candidate_id)
    steps = _live(session, org_id, candidate_id, "CareerStepClaim")
    ids = {uuid.UUID(cid) for c in steps if (cid := ((_view(c).get("company") or {}).get("company_id")))}
    known = {c.id: c for c in session.scalars(select(Company).where(Company.id.in_(ids or [None])))}  # one query
    stints, companies_of = [], []  # the resolved company of each stint, for one facts lookup below
    for c in steps:
        p = _view(c)
        label_claim = labels.get(str(c.id))
        label = _view(label_claim) if label_claim else {}
        # The level is read from the title by code at build time, so title rules can change without a new model call;
        # a recruiter's correction (approved) wins.
        level = label.get("level") if label_claim and label_claim.status == "approved" else (engine.title_level(p["title_raw"]) if label_claim else None)
        company_id = (p.get("company") or {}).get("company_id")
        company = known.get(uuid.UUID(company_id)) if company_id else None
        while company is not None and company.merged_into_id:
            company = session.get(Company, company.merged_into_id)
        companies_of.append(company)
        stints.append(rubric.Stint(
            id=str(c.id), company=p["company"]["raw_name"], title=p["title_raw"], start=c.valid_from, end=c.valid_to,
            employment=p.get("employment_type") or "unknown", company_key=str(company.id) if company else p["company"]["raw_name"].lower(),
            family=label.get("role_family"), level=level, domains=label.get("domains") or [],
            signals=label.get("signals") or [],
            facts=None,  # filled below: every company's facts are read at once
            self_employed=normalize(p["company"]["raw_name"]).kind == "self_employed",
            precise=c.temporal_precision in ("month", "exact")))
    distinct = list({c.id: c for c in companies_of if c is not None}.values())
    facts_map = company_facts_many(session, distinct) if distinct else {}
    for stint, company in zip(stints, companies_of):
        stint.facts = facts_map.get(company.id) if company is not None else None
    edu = []
    for c in _live(session, org_id, candidate_id, "EducationClaim"):
        p = _view(c)
        rank = institution_rank(session, p.get("institution_raw"))
        edu.append(rubric.Education(str(c.id), p["institution_raw"], p.get("level"), p.get("field"), c.valid_to, **rank))
    return stints, edu


def institution_rank(session: Session, raw: str | None) -> dict[str, Any]:
    from maindscout.api import institutions

    return institutions.rank_of(session, raw)


DEGREES = ("bachelor", "master", "doctorate")


def research_institutions(session: Session, org_id, candidate_id, client_factory, task_id: uuid.UUID | None = None) -> int:
    """Look up the QS rank of each university this person has a degree from, once per institution (shared)."""
    from maindscout.api import institutions
    from maindscout.settings import env

    if (env("RESEARCH_AUTO", "true") or "").lower() in ("0", "false", "no", "off"):
        return 0
    done = 0
    for c in _live(session, org_id, candidate_id, "EducationClaim"):
        p = _view(c)
        if p.get("level") not in DEGREES:
            continue
        inst = institutions.resolve(session, p["institution_raw"])
        if institutions.due(inst):
            institutions.research(session, inst, client_factory(), task_id)
            done += 1
    return done


def _hash(stints, edu, as_of: date) -> str:
    def plain(o):
        return {k: (v.isoformat() if isinstance(v, date) else plain(v) if hasattr(v, "__dataclass_fields__") else v)
                for k, v in o.__dict__.items()}
    raw = json.dumps([[plain(s) for s in stints], [plain(e) for e in edu], as_of.isoformat()[:7], rubric.RUBRIC_VERSION],
                     sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def build(session: Session, org_id, candidate_id, as_of: date | None = None) -> CareerProfile | None:
    """Compute the profile from today's facts; store a snapshot only when its inputs changed. Archived: nothing."""
    person = session.get(Candidate, candidate_id)
    if person is None or person.archived_at is not None:
        return None
    as_of = as_of or date.today()
    stints, edu = inputs(session, org_id, candidate_id)
    digest = _hash(stints, edu, as_of)
    last = latest(session, candidate_id)
    if last is not None and last.inputs_hash == digest:
        return last
    snapshot = CareerProfile(org_id=org_id, candidate_id=candidate_id, profile=rubric.build(stints, edu, as_of),
                             inputs_hash=digest, rubric_version=rubric.RUBRIC_VERSION,
                             # Not the database's now(): that is the transaction start, equal for every snapshot in it.
                             computed_at=datetime.now(timezone.utc))
    session.add(snapshot)
    session.flush()
    from maindscout.api.process import retriage_candidate

    retriage_candidate(session, org_id, candidate_id, {"act": "career_profile_built", "profile_id": str(snapshot.id)}, "system")
    return snapshot


def latest(session: Session, candidate_id) -> CareerProfile | None:
    return session.scalar(select(CareerProfile).where(CareerProfile.candidate_id == candidate_id)
                          .order_by(CareerProfile.computed_at.desc(), CareerProfile.id.desc()).limit(1))


def run(session: Session, org_id, candidate_id, client_factory, task_id: uuid.UUID | None = None,
        search_factory=None) -> dict[str, Any]:
    """The background task: classify what is new (paid, once), then build (free)."""
    person = session.get(Candidate, candidate_id)
    if person is None:
        return {"skipped": "gone"}
    if person.archived_at is not None:
        return {"skipped": "archived: outside coverage"}
    done = classify(session, org_id, candidate_id, client_factory(), task_id) if needs_classifying(session, org_id, candidate_id) else {"classified": 0}
    if search_factory is not None:
        done["institutions_researched"] = research_institutions(session, org_id, candidate_id, search_factory, task_id)
    snap = build(session, org_id, candidate_id)
    return {**done, "profile_id": str(snap.id) if snap else None, "reading": snap.profile["reading"]["label"] if snap else None}


def needs_classifying(session: Session, org_id, candidate_id) -> bool:
    done = classifications(session, org_id, candidate_id)
    return any(str(c.id) not in done for c in _live(session, org_id, candidate_id, "CareerStepClaim"))


def queue(session: Session, org_id, candidate_id) -> None:
    """Queue the profile task (deduplicated). Free when nothing new needs classifying."""
    from maindscout.api import tasks
    from maindscout.settings import env

    if (env("PROFILE_AUTO", "true") or "").lower() in ("0", "false", "no", "off"):
        return
    tasks.enqueue(session, org_id, "profile_candidate", {"candidate_id": str(candidate_id)}, priority=120,
                  dedupe_key=f"profile:{candidate_id}")


def rebuild_all(session: Session, reclassify: bool = False) -> dict[str, int]:
    """Queue every in-coverage person's profile. With `reclassify`, the machine's step labels are superseded first so
    they are read again with the current prompt (a recruiter's corrections are kept)."""
    from maindscout.db.models import Org

    dropped = queued = 0
    if reclassify:
        for c in session.scalars(select(Claim).where(Claim.claim_type == "StepClassificationClaim", Claim.status == "proposed")):
            c.status = "superseded"
            dropped += 1
    for org in session.scalars(select(Org).where(Org.id != PUBLIC_ORG_ID)):
        for person in session.scalars(select(Candidate).where(Candidate.org_id == org.id, Candidate.merged_into_id.is_(None),
                                                              Candidate.archived_at.is_(None))):
            queue(session, org.id, person.id)
            queued += 1
    session.flush()
    return {"labels_superseded": dropped, "queued": queued}


def queue_for_company(session: Session, company_id: uuid.UUID) -> int:
    """New public facts about a company: rebuild the profiles of everyone who worked there (code only)."""
    rows = session.execute(select(Claim.org_id, Claim.subject_id).where(
        Claim.claim_type == "CareerStepClaim", Claim.status.in_(LIVE),
        Claim.payload["company"]["company_id"].astext == str(company_id)).distinct()).all()
    for org_id, cid in rows:
        person = session.get(Candidate, cid)
        if person is not None and person.archived_at is None:
            queue(session, org_id, cid)
    return len(rows)


def as_view(snapshot: CareerProfile | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {**snapshot.profile, "computed_at": snapshot.computed_at.isoformat() if snapshot.computed_at else None}
