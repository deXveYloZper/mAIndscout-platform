"""Hiring profiles (I4): the job's requirements, completed from its ad and from the recruiter's intake notes, plus
what public research says about the hiring company and who we know at the target companies.

Requirements read by the model are proposed (with their quote); the recruiter approves, rejects or changes them.
What the hiring manager said (intake) beats what the ad says: an intake item with the same subject as an ad item
replaces it.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.api import companies, costs, writer
from maindscout.db.models import (PUBLIC_ORG_ID, Claim, ClaimObservation, Company, Evidence, ExtractionArtifact, Job,
                                  JobIntake)
from maindscout.intelligence import hiring as engine
from maindscout.intelligence.llm import LLMClient

LIVE = ("proposed", "approved")
VALUE_FIELDS = ("role_family", "level", "min_years", "employer_kinds", "domains", "employment", "normalized_token", "mobility",
                "cities", "relocation", "min_staff", "max_staff", "recent_months")
CATEGORY = {"role": "role", "employer": "employer", "domain": "domain", "target_company": "target_company",
            "employment": "employment", "skill": "skill", "other": "other", "location": "location"}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def key_for(job_id, p: dict[str, Any]) -> str:
    """One requirement per subject: the same subject read again (or from the intake) is the same requirement."""
    cat = p["category"]
    if cat == "role":
        part = "role"  # a job has one role
    elif cat == "employer":
        size = f"|{p.get('min_staff') or ''}-{p.get('max_staff') or ''}" if p.get("min_staff") or p.get("max_staff") else ""
        part = ",".join(sorted(p.get("employer_kinds") or [])) + size + f"|{'anti' if p['strength'] == 'anti' else 'want'}"
    elif cat == "domain":
        part = ",".join(sorted(p.get("domains") or [])) + f"|{'anti' if p['strength'] == 'anti' else 'want'}"
    elif cat == "target_company":
        part = ",".join(sorted(_norm(c["name"]) for c in p.get("companies") or [])) + f"|{'anti' if p['strength'] == 'anti' else 'want'}"
    elif cat == "employment":
        part = "employment"
    elif cat == "location" and (p.get("mobility") or {}).get("facet") == "residence":
        part = "residence"  # one "must live in" per job: the hiring manager's word replaces the ad's
    elif cat == "skill":
        part = p.get("normalized_token") or _norm(p["text_raw"])
    else:
        part = _norm(p["text_raw"])
    return f"{job_id}|{cat}|{part}"


def _payload(session: Session, item: engine.Item, source: str) -> dict[str, Any]:
    p: dict[str, Any] = {"text_raw": item.text, "category": CATEGORY[item.kind], "strength": item.strength,
                         "distinctive": False, "source": source}
    f = dict(item.fields)
    if item.kind == "skill":
        p["normalized_token"] = f.pop("skill_token", None)
    if item.kind == "location":  # the same shape as the ad's "live in or work from", so coverage and sourcing read it
        p["mobility"] = {"facet": "residence", "countries": f.pop("countries")}
        p["normalized_token"] = "residence"
        if not f.get("cities"):
            f.pop("cities", None)
        if not f.get("relocation"):
            f.pop("relocation", None)
    if item.kind == "target_company":
        out = []
        for name in f.pop("companies", []):
            company, _ = companies.resolve(session, name, "intake")
            out.append({"name": name, "company_id": str(company.id) if company else None})
            if company is not None and item.strength != "anti":
                _research(session, company, "named on a role as a company to source from")
        p["companies"] = out
    p.update({k: v for k, v in f.items() if v is not None})
    return p


def _write(session: Session, job: Job, items: list[engine.Item], source: str, evidence: dict[str, Any]) -> dict[str, int]:
    written = replaced = seen = 0
    today = date.today()
    for item in items:
        p = _payload(session, item, source)
        key = key_for(job.id, p)
        live = session.scalar(select(Claim).where(Claim.org_id == job.org_id, Claim.subject_id == job.id,
                                                  Claim.claim_type == "JobRequirementClaim", Claim.natural_key == key,
                                                  Claim.status.in_(LIVE)))
        if live is not None:
            old = live.approved_view or live.payload
            same = {k: v for k, v in old.items() if k != "source"} == {k: v for k, v in p.items() if k != "source"} or (
                old.get("strength") == p["strength"] and {k: old.get(k) for k in VALUE_FIELDS} == {k: p.get(k) for k in VALUE_FIELDS})
            if same or source == "ad" or live.status == "approved":
                seen += 1  # nothing new, or a person already decided this one
                continue
            live.status = "superseded"  # the hiring manager's word beats the ad's
            replaced += 1
        claim = writer.add_claim(session, org_id=job.org_id, subject_type="job", subject_id=job.id,
                                 claim_type="JobRequirementClaim", payload=p, natural_key=key, status="proposed",
                                 observed_as_of=today)
        if live is not None:
            live.superseded_by = claim.id
        ev = Evidence(org_id=job.org_id, claim_id=claim.id, evidence_type=evidence["type"], document_id=evidence.get("document_id"),
                      locator={**evidence["locator"], "char_start": item.start, "char_end": item.end}, snippet=item.quote,
                      source_authority=evidence["authority"], origin=evidence["origin"], observed_as_of=today,
                      span_validation={"tier": "typed", "result": "pass", "metric_bucket": "none",
                                       "detail": f"quote found in the {source} ({engine.HIRING_PROMPT_VERSION})"})
        session.add(ev)
        session.flush()
        session.add(ClaimObservation(org_id=job.org_id, claim_id=claim.id, attribute_path=".", value=p, evidence_id=ev.id,
                                     source_authority=evidence["authority"], origin=evidence["origin"], observed_as_of=today))
        written += 1
    session.flush()
    from maindscout.api.process import rematch_job

    rematch_job(session, job.org_id, job.id, {"act": f"hiring_profile_{source}"}, "system")
    return {"written": written, "replaced": replaced, "seen": seen}


def from_ad(session: Session, job_id: uuid.UUID, client: LLMClient, force: bool = False, task_id=None) -> dict[str, Any]:
    """Read the role, employment and any background, industry or company asks from the job's ad (once)."""
    job = session.get(Job, job_id)
    if job is None or job.source_document_id is None:
        return {"skipped": "no ad"}
    done = session.scalar(select(Claim.id).where(Claim.subject_id == job.id, Claim.claim_type == "JobRequirementClaim",
                                                 Claim.payload["source"].astext == "ad").limit(1))
    if done and not force:
        return {"skipped": "already read"}
    artifact = session.scalar(select(ExtractionArtifact).where(ExtractionArtifact.document_id == job.source_document_id,
                                                               ExtractionArtifact.method == "text_layer"))
    if artifact is None:
        return {"skipped": "no text"}
    costs.ensure_budget(session, job.org_id)
    outcome = engine.read(artifact.content, client, "ad")
    costs.record(session, job.org_id, "hiring_profile", outcome.cost, subject_type="job", subject_id=job.id, task_id=task_id)
    result = _write(session, job, outcome.items, "ad", {
        "type": "document_span", "document_id": job.source_document_id, "locator": {"artifact_id": str(artifact.id)},
        "authority": "employer_authored", "origin": "employer"})
    return {**result, "rejected": len(outcome.rejected), "usd": outcome.cost.get("usd", 0)}


def add_intake(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, text: str, actor: str, client: LLMClient) -> dict[str, Any]:
    """Keep the recruiter's notes as written and read requirements from them (each with its quote)."""
    job = session.get(Job, job_id)
    if job is None or job.org_id != org_id:
        raise LookupError(f"No job {job_id}")
    text = text.strip()
    if len(text) < 20:
        raise ValueError("Paste the notes from the call (a few sentences at least).")
    costs.ensure_budget(session, org_id)
    intake = JobIntake(org_id=org_id, job_id=job.id, text=text[:20000], created_by=actor)
    session.add(intake)
    session.flush()
    outcome = engine.read(intake.text, client, "intake")
    costs.record(session, org_id, "hiring_intake", outcome.cost, subject_type="job", subject_id=job.id)
    # Who is hiring is a fact about the job, not a requirement: an anonymised ad names nobody, the notes do.
    hiring_company = None
    for item in [i for i in outcome.items if i.kind == "hiring_company"]:
        hiring_company = set_hiring_company(session, org_id, job.id, item.fields["companies"][0], actor, source="intake").name
    items = [i for i in outcome.items if i.kind != "hiring_company"]
    result = _write(session, job, items, "intake", {
        "type": "intake_note", "locator": {"intake_id": str(intake.id)}, "authority": "human_assertion", "origin": "relayed"})
    return {"intake_id": str(intake.id), **result, "hiring_company": hiring_company, "rejected": outcome.rejected,
            "usd": outcome.cost.get("usd", 0)}


def residence(session: Session, job: Job) -> list[Claim]:
    """The role's live "must live in" requirements (normally one)."""
    return [c for c in session.scalars(select(Claim).where(Claim.subject_id == job.id, Claim.claim_type == "JobRequirementClaim",
                                                          Claim.status.in_(LIVE)).order_by(Claim.created_at.desc()))
            if ((c.approved_view or c.payload).get("mobility") or {}).get("facet") == "residence"]


def country_codes(countries: list[str]) -> list[str]:
    """Two-letter codes from codes or names ("IT", "Italy", "italia"); an unknown one is refused, never dropped
    (x-ray A1: "Italy" used to vanish, leaving the role with no country limit)."""
    import re as _re

    from maindscout.domain import geo

    codes: list[str] = []
    for raw in countries:
        raw = (raw or "").strip()
        if not raw:
            continue
        code = raw.upper() if _re.fullmatch(r"[A-Za-z]{2}", raw) and raw.upper() in geo.NAMES else geo.country_in(raw)
        if not code:
            raise ValueError(f"Not a country the desk recognises: {raw!r}. Use its name or two-letter code (IT, DE, GB).")
        if code not in codes:
            codes.append(code)
    return codes


def set_residence(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, countries: list[str], actor: str) -> list[str]:
    """Where people must live for this role: the one place the role's countries are kept (x-ray B1, 2026-10-13). The
    hiring profile shows it, sourcing searches and suggests there, and the coverage gate accepts it. An empty list
    means no limit (sourcing then uses the ad's places, or where the client's team works)."""
    from maindscout.api import coverage, review
    from maindscout.domain import geo

    job = session.get(Job, job_id)
    if job is None or job.org_id != org_id:
        raise LookupError(f"No job {job_id}")
    codes = country_codes(countries)
    live = residence(session, job)
    current = [x for c in live[:1] for x in ((c.approved_view or c.payload)["mobility"].get("countries") or [])]
    if codes == current and len(live) <= 1:
        return codes
    old = (live[0].approved_view or live[0].payload) if live else {}
    # The city and "relocation welcome" (from the intake) stay while their country does.
    keep = {k: old[k] for k in ("cities", "relocation") if k in old and set(current) <= set(codes)}
    if codes:
        claim = review.assert_claim(session, org_id, actor, subject_type="job", subject_id=job.id, claim_type="JobRequirementClaim",
                                    payload={"category": "location", "strength": "must", "distinctive": False, "source": "recruiter",
                                             "text_raw": f"Live in or work from: {', '.join(geo.name_of(c) for c in codes)}",
                                             "mobility": {"facet": "residence", "countries": codes},
                                             "normalized_token": "residence", **keep},
                                    replaces=live[0].id if live else None)
        for c in live[1:]:
            c.status, c.superseded_by = "superseded", claim.id
    else:
        for c in live:
            review.reject_claim(session, org_id, c.id, actor, "outdated", "no country limit for this role")
    session.flush()
    coverage.reevaluate_job(session, job, {"act": "job_countries", "job_id": str(job.id)}, actor)
    from maindscout.api import strategy

    strategy.sync(session, org_id, job, actor)
    return codes


def set_hiring_company(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, name: str, actor: str, source: str = "recruiter") -> Company:
    """The company that is hiring, named by a person (intake notes or typed): the role's company from now on, for its
    hiring profile, its strategy (talent DNA, peers) and its off-limits. The ad's own reading never overrides it."""
    job = session.get(Job, job_id)
    if job is None or job.org_id != org_id:
        raise LookupError(f"No job {job_id}")
    name = " ".join((name or "").split())
    if len(name) < 2:
        raise ValueError("Type the hiring company's name.")
    company, _ = companies.resolve(session, name, source)
    company = companies.canonical(session, company) if company is not None else None
    if company is None:
        raise ValueError(f'"{name}" is not a company name the desk can use.')
    job.hiring_company, job.hiring_company_id = name, company.id
    session.flush()
    _research(session, company, f"hiring for '{job.title}' (named by a person)")
    return company


def _research(session: Session, company: Company, context: str) -> None:
    """Grok research (about $0.09) for the companies that matter most: hiring companies and companies named on a role."""
    from maindscout.api import research, tasks
    from maindscout.settings import env

    if research.due(company) and (env("RESEARCH_AUTO", "true") or "").lower() not in ("0", "false", "no", "off"):
        tasks.enqueue(session, None, "research_company", {"company_id": str(company.id), "context": context},
                      priority=80, dedupe_key=f"research:{company.id}")


def company_summary(session: Session, company: Company | None) -> dict[str, Any] | None:
    """What public research says about the hiring company, in plain words, for the job page."""
    if company is None:
        return None
    while company.merged_into_id:
        company = session.get(Company, company.merged_into_id)
    from maindscout.api import profiles

    facts = profiles.company_facts(session, company)
    hq = session.scalar(select(Claim).where(Claim.org_id == PUBLIC_ORG_ID, Claim.subject_id == company.id,
                                            Claim.claim_type == "CompanyLocationClaim", Claim.status.in_(LIVE)))
    team = session.scalar(select(Claim).where(Claim.org_id == PUBLIC_ORG_ID, Claim.subject_id == company.id,
                                              Claim.claim_type == "TeamSizeClaim", Claim.status.in_(LIVE)).order_by(Claim.created_at.desc()))
    out: dict[str, Any] = {"id": str(company.id), "name": company.name, "researched": company.research_status}
    if facts:
        rounds = sorted((r for r in facts.rounds if r[1]), key=lambda r: r[1])
        out.update(kind=facts.kind, founded=facts.founded.isoformat()[:4] if facts.founded else None, status=facts.status,
                   stage=f"{rounds[-1][0].replace('_', ' ')} ({rounds[-1][1].isoformat()[:7]})" if rounds else None,
                   domains=facts.domains[:5])
    if team is not None:
        out["team"] = team.payload.get("raw")
    if hq is not None:
        out["hq"] = hq.payload.get("hq_raw")
    return out


def targets(session: Session, org_id: uuid.UUID, requirements: list[Claim]) -> dict[str, int]:
    """company id -> how many people on this desk have worked there (for target-company requirements)."""
    out: dict[str, int] = {}
    for r in requirements:
        for c in (r.approved_view or r.payload).get("companies") or []:
            if c.get("company_id") and c["company_id"] not in out:
                out[c["company_id"]] = len(companies.people_at(session, org_id, uuid.UUID(c["company_id"])))
    return out


def intakes(session: Session, job_id: uuid.UUID) -> list[dict[str, Any]]:
    return [{"id": str(i.id), "text": i.text, "by": i.created_by, "at": i.created_at.isoformat() if i.created_at else None}
            for i in session.scalars(select(JobIntake).where(JobIntake.job_id == job_id).order_by(JobIntake.created_at.desc()))]


def queue(session: Session, job: Job) -> None:
    from maindscout.api import tasks
    from maindscout.settings import env

    if (env("PROFILE_AUTO", "true") or "").lower() in ("0", "false", "no", "off"):
        return
    tasks.enqueue(session, job.org_id, "profile_job", {"job_id": str(job.id)}, priority=90, dedupe_key=f"hiring:{job.id}")


def add_requirement(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, fields: dict[str, Any], actor: str) -> Claim:
    """A requirement the recruiter types: approved at once, with them as the source."""
    from maindscout.api import review

    p = {k: v for k, v in fields.items() if v not in (None, "", [])}
    if p.get("category") == "employer" and not p.get("employer_kinds") and not (p.get("min_staff") or p.get("max_staff")):
        raise ValueError("Tick a background (start-up, agency, …) or choose a company size. For an industry such as luxury, "
                         "choose Industry instead.")
    if p.get("min_staff") and p.get("max_staff") and p["min_staff"] > p["max_staff"]:
        raise ValueError("The smallest company size is above the largest.")
    if p.get("company_words"):
        p["company_words"] = list(dict.fromkeys(w.strip().lower() for w in p["company_words"] if w and w.strip()))[:12]
    if p.get("category") == "domain" and not p.get("domains") and not p.get("company_words"):
        raise ValueError("Choose the industry from the list, or write it as companies describe themselves (e.g. leather goods, bags).")
    p.setdefault("distinctive", False)
    p["source"] = "recruiter"
    if p.get("category") == "skill" and not p.get("normalized_token"):
        from maindscout.intelligence.extract import skill_name_token

        if token := skill_name_token(p.get("text_raw")):  # "influencer marketing" can be shown by a profile or CV
            p["normalized_token"] = token
    if p.get("category") == "target_company":
        out = []
        for c in p.get("companies") or []:
            name = c["name"] if isinstance(c, dict) else str(c)
            company, _ = companies.resolve(session, name, "recruiter")
            out.append({"name": name, "company_id": str(company.id) if company else None})
            if company is not None and p.get("strength") != "anti":
                _research(session, company, "named on a role as a company to source from")
        p["companies"] = out
    return review.assert_claim(session, org_id, actor, subject_type="job", subject_id=job_id,
                               claim_type="JobRequirementClaim", payload=p)


def set_strength(session: Session, org_id: uuid.UUID, claim_id: uuid.UUID, strength: str, actor: str) -> Claim:
    """Change how much a requirement matters (e.g. the ad says must, the hiring manager says nice)."""
    from maindscout.api import review

    old = session.get(Claim, claim_id)
    if old is None or old.org_id != org_id or old.claim_type != "JobRequirementClaim":
        raise LookupError(f"No requirement {claim_id}")
    p = {**(old.approved_view or old.payload), "strength": strength, "source": "recruiter"}
    return review.assert_claim(session, org_id, actor, subject_type="job", subject_id=old.subject_id,
                               claim_type="JobRequirementClaim", payload=p, replaces=old.id)
