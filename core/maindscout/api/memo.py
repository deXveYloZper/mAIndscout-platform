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
