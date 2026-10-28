"""A memo for one read-only page (2026-10-20: the marketing role's Sourcing tab ran 903 queries in about 7 s, most of
them the same per-person checks asked again and again). Inside `reading`, a check asked twice about the same person
answers from the memo; outside it, nothing is cached, so writes always see fresh facts."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable

from sqlalchemy.orm import Session


@contextmanager
def reading(session: Session):
    if session.info.get("memo") is not None:  # already inside one
        yield
        return
    session.info["memo"] = {}
    try:
        yield
    finally:
        session.info.pop("memo", None)


def cached(session: Session, key: tuple, compute: Callable[[], Any]) -> Any:
    memo = session.info.get("memo")
    if memo is None:
        return compute()
    if key not in memo:
        memo[key] = compute()
    return memo[key]


def put(session: Session, key: tuple, value: Any) -> None:
    """Fill the memo ahead (one query for everyone instead of one per person)."""
    memo = session.info.get("memo")
    if memo is not None:
        memo[key] = value


FACT_TYPES = ("LocationClaim", "CareerStepClaim")


def _query(session: Session, org_id, ids: list):
    from sqlalchemy import select

    from maindscout.db.models import Claim

    return session.scalars(select(Claim).where(Claim.org_id == org_id, Claim.subject_id.in_(ids or [None]),
                                               Claim.status.in_(("proposed", "approved")), Claim.claim_type.in_(FACT_TYPES))
                           .order_by(Claim.created_at))


def places_and_steps(session: Session, org_id, candidate_id) -> list:
    """A person's live places and career steps, oldest first (what coverage, current employers and reaches read)."""
    return cached(session, ("facts", candidate_id), lambda: list(_query(session, org_id, [candidate_id])))


def prefetch_places_and_steps(session: Session, org_id, ids: list) -> None:
    if session.info.get("memo") is None or not ids:
        return
    out: dict = {i: [] for i in ids}
    for c in _query(session, org_id, list(ids)):
        out[c.subject_id].append(c)
    for i, claims in out.items():
        put(session, ("facts", i), claims)


def prefetch_employers(session: Session, org_id, ids: list) -> None:
    """After `prefetch_places_and_steps`: the companies of everyone's current jobs in one query, held for the page, so
    each read of one by id (`session.get`: where they work for the country check, the card's employer) asks nothing."""
    import uuid

    from sqlalchemy import select

    from maindscout.db.models import Company

    if session.info.get("memo") is None or not ids:
        return
    wanted = set()
    for i in ids:
        for c in places_and_steps(session, org_id, i):
            if c.claim_type != "CareerStepClaim" or c.valid_to is not None:
                continue
            for p in (c.payload, c.approved_view or {}):  # the country check reads the payload, the card the approved view
                try:
                    wanted.add(uuid.UUID((p.get("company") or {}).get("company_id") or ""))
                except ValueError:
                    pass
    put(session, ("employers",), list(session.scalars(select(Company).where(Company.id.in_(list(wanted) or [None])))))
