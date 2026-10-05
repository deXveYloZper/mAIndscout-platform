"""indexes for the read paths found by perf-check

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-05 23:30:00

Postgres does not index foreign keys by itself. On a 3,000-person desk, looking up one fact's evidence scanned all
42,000 evidence rows (about 90 ms each, so 17 s for the all-jobs inbox). Each index below serves a lookup the API makes
on a hot path; columns only filtered in rare admin work are left alone (every index costs a little on each write).
"""
from typing import Sequence, Union

from alembic import op


revision: str = '0023'
down_revision: Union[str, Sequence[str], None] = '0022'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEXES = [
    # A fact's evidence and readings: person page, gap page, inbox, review, erasure.
    ("ix_evidence_claim", "evidence", "(claim_id)"),
    ("ix_evidence_document", "evidence", "(document_id)"),
    ("ix_claim_observation_claim", "claim_observation", "(claim_id)"),
    # A person's (or job's) facts by subject alone: the older index starts with org and subject type.
    ("ix_claim_subject_type", "claim", "(subject_id, claim_type)"),
    # People on a job: job page, inbox, re-matching a job, sourcing.
    ("ix_candidate_job_job", "candidate_job", "(job_id)"),
    # Review cards and their items.
    ("ix_decision_subject", "decision", "(subject_id)"),
    ("ix_decision_item_decision", "decision_item", "(decision_id)"),
    ("ix_decision_item_claim", "decision_item", "(claim_id)"),
    # Which documents are about a person (CV link, last verified, erasure).
    ("ix_document_subject_subject", "document_subject", "(subject_id)"),
    # Checked on every match and on every person page.
    ("ix_client_block_candidate", "client_block", "(candidate_id)"),
    ("ix_message_candidate", "message", "(candidate_id)"),
    ("ix_message_about_candidate", "message", "(about_candidate_id)"),
    ("ix_company_alias_company", "company_alias", "(company_id)"),
    ("ix_extraction_artifact_document", "extraction_artifact", "(document_id)"),
]


def upgrade() -> None:
    for name, table, cols in INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} {cols}")
    # Enqueue checks for an equal task still waiting or running: finished tasks pile up and must not be scanned.
    op.execute("CREATE INDEX IF NOT EXISTS ix_task_dedupe_open ON task (dedupe_key) WHERE status IN ('queued', 'running')")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_task_dedupe_open")
    for name, _, _ in reversed(INDEXES):
        op.execute(f"DROP INDEX IF EXISTS {name}")
