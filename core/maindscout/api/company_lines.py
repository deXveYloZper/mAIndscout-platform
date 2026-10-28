"""Company lines of business, stored and used (owner, 2026-10-26). See intelligence/company_lines.py for what a line is.

Used to add, order and explain, never to leave a company out by default:
- a role's talent pools reuse every known company whose lines match a pool (industry, positioning, market), for free;
- within a tier, the companies closest to the role's own line are searched first;
- a role can be narrowed on demand (a focus: "luxury apparel"), shown on its plan and undone with one click.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from maindscout.api import costs, writer
from maindscout.db.models import PUBLIC_ORG_ID, Claim, ClaimObservation, Company, Evidence
from maindscout.intelligence import company_lines as engine

LIVE = ("proposed", "approved")
CLAIM = "CompanyLineClaim"
_STOP = {"and", "the", "of", "for", "with", "in", "to", "a", "an", "other", "products", "services", "solutions", "goods",
         "companies", "company", "brands", "brand", "makers", "maker", "manufacturers", "manufacturer", "houses", "house"}


def stems(text: str | None) -> set[str]:
    words = re.findall(r"[a-z]+", (text or "").lower().replace("&", " and "))
    return {w[:-1] if len(w) > 4 and w.endswith("s") else w for w in words if w not in _STOP and len(w) > 2}


def of_company(session: Session, company_id: uuid.UUID) -> list[dict[str, Any]]:
    """The company's lines (through every record merged into it), main line first."""
    from maindscout.api import memo
    from maindscout.api.companies import _ids_for, canonical

    def read() -> list[dict[str, Any]]:
        company = canonical(session, session.get(Company, company_id))
        if company is None:
            return []
        ids = [uuid.UUID(i) for i in _ids_for(session, company)]
        rows = session.scalars(select(Claim).where(Claim.org_id == PUBLIC_ORG_ID, Claim.subject_id.in_(ids),
                                                   Claim.claim_type == CLAIM, Claim.status.in_(LIVE)).order_by(Claim.created_at))
        return [dict(c.approved_view or c.payload) for c in rows]
    return memo.cached(session, ("company_lines", company_id), read)


def prefetch(session: Session, companies_: list[Company]) -> None:
    """Inside a page's memo: `of_company` of every company given, in one query for all of them (a role's map lists some
    170 companies; two queries each took a second on Ferrari's CRM role, 2026-10-28). A company whose lines share a time
    (read at once: 81 of 3,041 that day) is left to its own read, which alone says which of them comes first, as before."""
    from maindscout.api import memo
    from maindscout.api.companies import _ids_for, canonical, prefetch_ids

    if session.info.get("memo") is None or not companies_:
        return
    roots = {c.id: canonical(session, c) for c in companies_}
    prefetch_ids(session, [r for r in roots.values() if r is not None])
    owner = {uuid.UUID(i): r.id for r in roots.values() if r is not None for i in _ids_for(session, r)}
    found: dict[uuid.UUID, list[Claim]] = {}
    for c in session.scalars(select(Claim).where(Claim.org_id == PUBLIC_ORG_ID, Claim.subject_id.in_(list(owner) or [None]),
                                                 Claim.claim_type == CLAIM, Claim.status.in_(LIVE)).order_by(Claim.created_at)):
        found.setdefault(owner[c.subject_id], []).append(c)
    for company_id, root in roots.items():
        lines = found.get(root.id, []) if root is not None else []
        if len({c.created_at for c in lines}) == len(lines):  # each at its own time: in time order, as its own read gives
            memo.put(session, ("company_lines", company_id), [dict(c.approved_view or c.payload) for c in lines])


def classified(session: Session, company_id: uuid.UUID) -> bool:
    return session.scalar(select(func.count()).select_from(Claim).where(
        Claim.org_id == PUBLIC_ORG_ID, Claim.subject_id == company_id, Claim.claim_type == CLAIM)) > 0


def classify(session: Session, org_id: uuid.UUID, companies_: list[Company], client, task_id=None,
             extra: dict[uuid.UUID, list[str]] | None = None, again: bool = False) -> dict[str, int]:
    """Read the lines of these companies (those with something to read), in batches; store each line with its basis.
    `extra`: more text for a company (a hiring company's lines of business, as its research found them). Skips
    companies already classified unless `again`."""
    todo = [c for c in companies_ if c is not None and (c.exa_profile or (extra or {}).get(c.id))
            and (again or not classified(session, c.id))]
    stats = {"companies": len(todo), "lines": 0, "rejected": 0}
    for start in range(0, len(todo), engine.BATCH):
        batch = todo[start:start + engine.BATCH]
        blocks = [(i + 1, engine.text_block(i + 1, c.name, c.exa_profile, (extra or {}).get(c.id))) for i, c in enumerate(batch)]
        costs.ensure_budget(session, org_id)
        outcome = engine.classify(blocks, client)
        costs.record(session, org_id, "company_lines", outcome.cost, subject_type="company", subject_id=None, task_id=task_id)
        stats["rejected"] += len(outcome.rejected)
        for i, company in enumerate(batch):
            for line in outcome.lines.get(i + 1, []):
                stats["lines"] += _write(session, company, line)
        session.flush()
    return stats


def _write(session: Session, company: Company, line: engine.Line) -> int:
    payload = {"line": line.line, "industry": line.industry, "market": line.market, "positioning": line.positioning,
               "customers": line.customers}
    key = f"{company.id}|line|{line.industry}|{' '.join(sorted(stems(line.market)))}"
    claim = session.scalar(select(Claim).where(Claim.org_id == PUBLIC_ORG_ID, Claim.subject_id == company.id,
                                               Claim.claim_type == CLAIM, Claim.natural_key == key, Claim.status.in_(LIVE)))
    made = 0
    today = date.today()
    if claim is None:
        claim = writer.add_claim(session, org_id=PUBLIC_ORG_ID, subject_type="company", subject_id=company.id,
                                 claim_type=CLAIM, payload=payload, natural_key=key, status="proposed",
                                 observed_as_of=today, temporal_precision="unknown")
        made = 1
    ev = Evidence(org_id=PUBLIC_ORG_ID, claim_id=claim.id, evidence_type="research_result", document_id=None,
                  locator={"source": "company profile"}, snippet=line.basis, source_authority="web_inference",
                  origin="independent_web", observed_as_of=today,
                  span_validation={"tier": "typed", "result": "pass", "metric_bucket": "none",
                                   "detail": f"company lines {engine.LINES_PROMPT_VERSION}"})
    session.add(ev)
    session.flush()
    session.add(ClaimObservation(org_id=PUBLIC_ORG_ID, claim_id=claim.id, attribute_path=".", value=payload,
                                 evidence_id=ev.id, source_authority="web_inference", origin="independent_web", observed_as_of=today))
    return made


# --- using them -------------------------------------------------------------------------------------------------------


def line_matches(line: dict[str, Any], want: dict[str, Any]) -> bool:
    """Does a company's line fit a pool or a role's line? The same industry; the same positioning when both say one;
    and, when the pool names a market, a word of it in the company's market."""
    if want.get("industry") and line.get("industry") != want["industry"]:
        return False
    a, b = line.get("positioning"), want.get("positioning")
    if a and b and "unknown" not in (a, b) and a != b:
        return False
    market = stems(want.get("market"))
    return not market or bool(market & stems(line.get("market")))


def closeness(lines: list[dict[str, Any]], role_line: dict[str, Any] | None) -> int:
    """How many dimensions the company's closest line shares with the role's line (0 to 4): for ordering only."""
    if not role_line or not lines:
        return 0
    def score(line: dict[str, Any]) -> int:
        return (int(line.get("industry") == role_line.get("industry"))
                + int(bool(stems(line.get("market")) & stems(role_line.get("market"))))
                + int(line.get("positioning") not in (None, "unknown") and line.get("positioning") == role_line.get("positioning"))
                + int(line.get("customers") not in (None, "unknown") and line.get("customers") == role_line.get("customers")))
    return max(score(line) for line in lines)


def members(session: Session, want: dict[str, Any], limit: int = 300) -> list[Company]:
    """Known companies with a line that fits `want` (a pool's industry, market, positioning), as they stand today."""
    from maindscout.api.companies import canonical

    q = select(Claim).where(Claim.org_id == PUBLIC_ORG_ID, Claim.claim_type == CLAIM, Claim.status.in_(LIVE))
    if want.get("industry"):
        q = q.where(Claim.payload["industry"].astext == want["industry"])
    out: dict[uuid.UUID, Company] = {}
    for c in session.scalars(q):
        if line_matches(c.approved_view or c.payload, want):
            company = canonical(session, session.get(Company, c.subject_id))
            if company is not None:
                out[company.id] = company
        if len(out) >= limit:
            break
    return list(out.values())


def focus_text(session: Session, company: Company) -> set[str]:
    """Every word that describes the company, for a focus the owner chose ("luxury apparel")."""
    from maindscout.api import segments

    words = stems(company.name) | stems((company.exa_profile or {}).get("offering"))
    for line in of_company(session, company.id):
        words |= stems(line.get("market")) | stems(line.get("industry")) | stems(line.get("line"))
        if line.get("positioning") not in (None, "unknown"):
            words |= stems(line["positioning"])
    for seg in segments.of_company(session, company.id):
        words |= stems(seg)
    return words


def in_focus(session: Session, company: Company | None, focus: dict[str, Any] | None) -> bool:
    """With no focus, everyone is in. With one, a company is in when every word of the focus describes it."""
    if not focus or not focus.get("stems"):
        return True
    return company is not None and set(focus["stems"]) <= focus_text(session, company)
