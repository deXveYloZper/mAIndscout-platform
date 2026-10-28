"""desk log (the activity log) (owner, 2026-10-22: "add logs that are easy to track, what buttons do, what is happening, so errors
are easier to read ... what is searched, what prompts do we ask xAI"): one row per button, task, search, model call
and error, readable on the desk

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-22 22:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0031'
down_revision: Union[str, Sequence[str], None] = '0030'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'desk_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), nullable=True),  # no key: written outside the work's transaction
        sa.Column('at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('level', sa.String(), nullable=False, server_default='info'),
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('actor', sa.String(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('detail', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.CheckConstraint("kind IN ('button', 'task', 'search', 'model', 'error', 'step')", name='desk_log_kind'),
        sa.CheckConstraint("level IN ('info', 'warn', 'error')", name='desk_log_level'),
    )
    op.create_index('ix_desk_log_org_at', 'desk_log', ['org_id', 'at'])
    op.create_index('ix_desk_log_job_at', 'desk_log', ['job_id', 'at'])


def downgrade() -> None:
    op.drop_table('desk_log')
