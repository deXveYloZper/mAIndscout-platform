"""calls: transcripts as documents, call reviews

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-06 10:00:00

A call transcript is a document (doc_type 'transcript'), read once into a call review that waits for one bulk approval.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0024'
down_revision: Union[str, Sequence[str], None] = '0023'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('document_doc_type', 'document', type_='check')
    op.create_check_constraint('document_doc_type', 'document', "doc_type IN ('cv', 'jd', 'transcript', 'other')")
    op.create_table(
        'call_review',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('org_id', sa.UUID(), nullable=False),
        sa.Column('candidate_id', sa.UUID(), nullable=False),
        sa.Column('document_id', sa.UUID(), nullable=False),
        sa.Column('job_id', sa.UUID(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('findings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('resolved_by', sa.String(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('reading', 'pending', 'applied', 'dismissed', 'failed')", name='call_review_status'),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidate.id']),
        sa.ForeignKeyConstraint(['document_id'], ['document.id']),
        sa.ForeignKeyConstraint(['job_id'], ['job.id']),
        sa.ForeignKeyConstraint(['org_id'], ['org.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_call_review_candidate', 'call_review', ['candidate_id'])


def downgrade() -> None:
    op.drop_index('ix_call_review_candidate', table_name='call_review')
    op.drop_table('call_review')
    op.execute("DELETE FROM document WHERE doc_type = 'transcript'")
    op.drop_constraint('document_doc_type', 'document', type_='check')
    op.create_check_constraint('document_doc_type', 'document', "doc_type IN ('cv', 'jd', 'other')")
