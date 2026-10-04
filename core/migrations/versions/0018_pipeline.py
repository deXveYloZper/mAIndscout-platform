"""full pipeline and client blocks

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-05 09:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0018'
down_revision: Union[str, Sequence[str], None] = '0017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW = ('new', 'seen', 'contacted', 'screened', 'submitted', 'interviewing', 'offer', 'placed', 'we_passed', 'withdrawn', 'client_rejected')
OLD = ('new', 'seen', 'submitted', 'we_passed')


def _in(values):
    return "pair_state IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.drop_constraint('pair_state', 'candidate_job', type_='check')
    op.create_check_constraint('pair_state', 'candidate_job', _in(NEW))
    op.create_table(
        'client_block',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('org_id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('candidate_id', sa.UUID(), nullable=False),
        sa.Column('job_id', sa.UUID(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('lifted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('lifted_by', sa.String(), nullable=True),
        sa.Column('lift_note', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidate.id']),
        sa.ForeignKeyConstraint(['company_id'], ['company.id']),
        sa.ForeignKeyConstraint(['job_id'], ['job.id']),
        sa.ForeignKeyConstraint(['org_id'], ['org.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_client_block', 'client_block', ['org_id', 'company_id', 'candidate_id'])


def downgrade() -> None:
    op.drop_index('ix_client_block', table_name='client_block')
    op.drop_table('client_block')
    op.execute("UPDATE candidate_job SET pair_state = 'seen' WHERE pair_state IN ('contacted', 'screened')")
    op.execute("UPDATE candidate_job SET pair_state = 'submitted' WHERE pair_state IN ('interviewing', 'offer', 'placed')")
    op.execute("UPDATE candidate_job SET pair_state = 'we_passed' WHERE pair_state IN ('withdrawn', 'client_rejected')")
    op.drop_constraint('pair_state', 'candidate_job', type_='check')
    op.create_check_constraint('pair_state', 'candidate_job', _in(OLD))
