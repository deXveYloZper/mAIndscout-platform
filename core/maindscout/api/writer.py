"""The only writer. Everything that changes the database goes through here.

Milestone B provides seeding and the guarded claim write. Later milestones add document,
process, decision and erasure writes to this package.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.db.models import Claim, ClaimTypeRegistry, FlagTypeRegistry, Org
from maindscout.domain import registry as reg


def seed_registries(session: Session) -> None:
    """Idempotently load the claim and flag registries from slice0/registry."""
    for key, row in reg.load_claim_registry().items():
        session.merge(
            ClaimTypeRegistry(
                key=key,
                claim_class=row["class"],
                subject_types=row["subject_types"],
                natural_key=row.get("natural_key"),
                volatility=row.get("volatility"),
                default_review=row.get("default_review"),
                payload_schema=row.get("payload_schema"),
            )
        )
    for key, row in reg.load_flag_registry().items():
        session.merge(
            FlagTypeRegistry(
                key=key,
                default_severity=row["default_severity"],
                brief_template=row.get("brief_template"),
                blocks_auto_approval=row.get("blocks_auto_approval", False),
                blocks_matching=row.get("blocks_matching", False),
                valid_subject_types=row["valid_subject_types"],
            )
        )
    session.flush()


def create_org(session: Session, name: str) -> Org:
    org = Org(name=name)
    session.add(org)
    session.flush()
    return org


def _check_flags(session: Session, flags: dict[str, Any], subject_type: str) -> None:
    flag_rows = {row.key: row for row in session.scalars(select(FlagTypeRegistry))}
    reg.validate_flags(flags, set(flag_rows))
    for path in reg.flag_paths(flags, set(flag_rows)):
        if subject_type not in flag_rows[path].valid_subject_types:
            raise reg.UnknownFlagError([f"{path} (not valid on a {subject_type})"])


def set_flags(session: Session, claim: Claim, flags: dict[str, Any]) -> None:
    """Replace a claim's flags, with the same checks as a new claim. Flags never touch the approved view."""
    _check_flags(session, flags, claim.subject_type)
    claim.flags = flags


def add_claim(
    session: Session,
    *,
    org_id: uuid.UUID,
    subject_type: str,
    subject_id: uuid.UUID,
    claim_type: str,
    payload: dict[str, Any],
    flags: dict[str, Any] | None = None,
    **fields: Any,
) -> Claim:
    """Write one claim. Rejects unknown flag keys, unknown claim types and wrong subject types."""
    flags = flags or {}
    _check_flags(session, flags, subject_type)

    type_row = session.get(ClaimTypeRegistry, claim_type)
    if type_row is None:
        raise reg.UnknownClaimTypeError(f"Unknown claim type: {claim_type}")
    if subject_type not in type_row.subject_types:
        raise reg.UnknownClaimTypeError(f"{claim_type} cannot describe a {subject_type}")
    reg.validate_payload(claim_type, type_row.payload_schema, payload)

    claim = Claim(
        org_id=org_id,
        subject_type=subject_type,
        subject_id=subject_id,
        claim_type=claim_type,
        payload=payload,
        flags=flags,
        **fields,
    )
    session.add(claim)
    session.flush()
    return claim
