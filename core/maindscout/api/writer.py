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
    known_flags = set(session.scalars(select(FlagTypeRegistry.key)))
    reg.validate_flags(flags, known_flags)

    type_row = session.get(ClaimTypeRegistry, claim_type)
    if type_row is None:
        raise reg.UnknownClaimTypeError(f"Unknown claim type: {claim_type}")
    if subject_type not in type_row.subject_types:
        raise reg.UnknownClaimTypeError(f"{claim_type} cannot describe a {subject_type}")

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
