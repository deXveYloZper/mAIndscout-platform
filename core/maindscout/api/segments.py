"""Company segments: what part of the market a company belongs to, kept on the company itself (owner, 2026-10-26: "yes
start with company tags"). A role's talent-map research finds pools of companies ("luxury jewellery and watches");
each company it keeps is tagged with its pool's segment, as a public-tier fact with the research's page and quote as
evidence. The knowledge builds up across roles: a later role's talent map is told the segments already known and
starts from their companies for free, so its research only has to find the ones we do not know yet.

A segment never names the client or the role it was found for (public facts are shared by every desk).
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from maindscout.api import writer
from maindscout.db.models import PUBLIC_ORG_ID, Claim, ClaimObservation, Company, Evidence

LIVE = ("proposed", "approved")
CLAIM = "CompanySegmentClaim"


def normalize(name: str) -> str:
    """One way to write a segment: "Luxury Jewellery & Watches" -> "luxury jewellery and watches"."""
    text = re.sub(r"\s+", " ", (name or "").replace("&", " and ").replace("/", " and ")).strip().lower()
    return re.sub(r"[^\w\s,'-]", "", text)[:80]


def tag(session: Session, company: Company, segment: str, url: str | None = None, quote: str | None = None,
        client_name: str | None = None) -> Claim | None:
    """Tag a company with a segment (or add this research as one more source of the same tag). None when the segment
    is empty or names the client (a pool like "Ferrari's direct rivals" is about one role, not the market)."""
    seg = normalize(segment)
    if len(seg) < 3 or (client_name and client_name.lower() in seg):
        return None
    key = f"{company.id}|segment|{seg}"
    claim = session.scalar(select(Claim).where(Claim.org_id == PUBLIC_ORG_ID, Claim.subject_id == company.id,
                                               Claim.claim_type == CLAIM, Claim.natural_key == key, Claim.status.in_(LIVE)))
    today = date.today()
    if claim is None:
        claim = writer.add_claim(session, org_id=PUBLIC_ORG_ID, subject_type="company", subject_id=company.id,
                                 claim_type=CLAIM, payload={"segment": seg}, natural_key=key, status="proposed",
                                 observed_as_of=today, temporal_precision="unknown")
    elif url and session.scalar(select(func.count()).select_from(Evidence).where(
            Evidence.claim_id == claim.id, Evidence.locator["url"].astext == url)):
        return claim  # the same page again: nothing new
    if url or quote:
        ev = Evidence(org_id=PUBLIC_ORG_ID, claim_id=claim.id, evidence_type="research_result", document_id=None,
                      locator={"url": url} if url else {}, snippet=(quote or "")[:300], source_authority="web_inference",
                      origin="independent_web", observed_as_of=today,
                      span_validation={"tier": "typed", "result": "pass", "metric_bucket": "none", "detail": "talent-map research"})
        session.add(ev)
        session.flush()
        session.add(ClaimObservation(org_id=PUBLIC_ORG_ID, claim_id=claim.id, attribute_path=".", value={"segment": seg},
                                     evidence_id=ev.id, source_authority="web_inference", origin="independent_web",
                                     observed_as_of=today))
    session.flush()
    return claim


_STOP = {"and", "the", "of", "for", "with", "in", "to", "a", "an", "companies", "company", "brands", "brand", "makers",
         "maker", "manufacturers", "manufacturer", "groups", "group", "houses", "house", "players", "other", "global"}


def _stems(text: str) -> set[str]:
    return {w.rstrip("s") for w in re.findall(r"[a-z]+", normalize(text)) if w not in _STOP and len(w) > 2}


def best_pool(line: str | None, pools: list[dict[str, Any]]) -> str | None:
    """The role's pool a direct competitor's line belongs to ("luxury sports cars" -> "Luxury sports car manufacturers"):
    two shared words or more, the most shared; None when no pool fits."""
    words = _stems(line or "")
    best, score = None, 1
    for p in pools:
        shared = len(words & _stems(p["name"]))
        if shared > score:
            best, score = p["name"], shared
    return best


def of_company(session: Session, company_id: uuid.UUID) -> list[str]:
    """The segments a company is tagged with (through every record merged into it)."""
    from maindscout.api import memo
    from maindscout.api.companies import _ids_for, canonical

    def read() -> list[str]:
        company = canonical(session, session.get(Company, company_id))
        if company is None:
            return []
        ids = [uuid.UUID(i) for i in _ids_for(session, company)]
        return sorted({(c.approved_view or c.payload)["segment"] for c in session.scalars(select(Claim).where(
            Claim.org_id == PUBLIC_ORG_ID, Claim.subject_id.in_(ids), Claim.claim_type == CLAIM, Claim.status.in_(LIVE)))})
    return memo.cached(session, ("segments", company_id), read)


def says_luxury(session: Session, company: Company | None) -> bool:
    """Research put the company in a luxury segment: luxury is luxury, whatever the industry (owner, 2026-10-23)."""
    return company is not None and any("luxury" in s or "high-end" in s for s in of_company(session, company.id))


def known(session: Session, limit: int = 40) -> list[tuple[str, int]]:
    """The segments we know, most companies first: [(segment, companies)]."""
    seg = Claim.payload["segment"].astext
    n = func.count(func.distinct(Claim.subject_id))
    rows = session.execute(select(seg, n).where(Claim.org_id == PUBLIC_ORG_ID, Claim.claim_type == CLAIM, Claim.status.in_(LIVE))
                           .group_by(seg).order_by(n.desc(), seg).limit(limit)).all()
    return [(seg, n) for seg, n in rows]


def members(session: Session, segment: str) -> list[Company]:
    """The companies tagged with a segment, each as it stands today (merged records followed)."""
    from maindscout.api.companies import canonical

    seg = normalize(segment)
    out: dict[uuid.UUID, Company] = {}
    for cid in session.scalars(select(Claim.subject_id).where(Claim.org_id == PUBLIC_ORG_ID, Claim.claim_type == CLAIM,
                                                              Claim.status.in_(LIVE), Claim.payload["segment"].astext == seg)):
        company = canonical(session, session.get(Company, cid))
        if company is not None:
            out[company.id] = company
    return list(out.values())


def summary(session: Session, company_id: uuid.UUID) -> list[dict[str, Any]]:
    """For the company page: each segment with how many pages name it there."""
    from maindscout.api.companies import _ids_for, canonical

    company = canonical(session, session.get(Company, company_id))
    if company is None:
        return []
    ids = [uuid.UUID(i) for i in _ids_for(session, company)]
    out = []
    for c in session.scalars(select(Claim).where(Claim.org_id == PUBLIC_ORG_ID, Claim.subject_id.in_(ids),
                                                 Claim.claim_type == CLAIM, Claim.status.in_(LIVE))):
        ev = session.scalars(select(Evidence).where(Evidence.claim_id == c.id).order_by(Evidence.created_at)).all()
        out.append({"segment": (c.approved_view or c.payload)["segment"], "sources": len(ev),
                    "first": {"url": (ev[0].locator or {}).get("url"), "quote": ev[0].snippet} if ev else None})
    return sorted(out, key=lambda r: r["segment"])
