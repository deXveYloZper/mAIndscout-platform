"""brief items

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-04 21:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0016'
down_revision: Union[str, Sequence[str], None] = '0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'brief_item',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('org_id', sa.UUID(), nullable=False),
        sa.Column('candidate_id', sa.UUID(), nullable=False),
        sa.Column('job_id', sa.UUID(), nullable=True),
        sa.Column('source_key', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('why', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('outcome', sa.String(), nullable=True),
        sa.Column('answer', sa.Text(), nullable=True),
        sa.Column('answer_claim_id', sa.UUID(), nullable=True),
        sa.Column('answered_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('open', 'asked', 'answered', 'dismissed', 'expired')", name='brief_status'),
        sa.ForeignKeyConstraint(['answer_claim_id'], ['claim.id']),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidate.id']),
        sa.ForeignKeyConstraint(['job_id'], ['job.id']),
        sa.ForeignKeyConstraint(['org_id'], ['org.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_brief_candidate', 'brief_item', ['candidate_id'])
    # One item per source per scope (a NULL job means the person-wide scope).
    op.execute("CREATE UNIQUE INDEX ux_brief_source ON brief_item (candidate_id, COALESCE(job_id, '00000000-0000-0000-0000-000000000000'::uuid), source_key)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_brief_source")
    op.drop_index('ix_brief_candidate', table_name='brief_item')
    op.drop_table('brief_item')
