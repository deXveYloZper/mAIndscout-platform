"""career profiles

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-04 09:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0012'
down_revision: Union[str, Sequence[str], None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'career_profile',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('org_id', sa.UUID(), nullable=False),
        sa.Column('candidate_id', sa.UUID(), nullable=False),
        sa.Column('profile', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('inputs_hash', sa.String(length=32), nullable=False),
        sa.Column('rubric_version', sa.String(), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidate.id']),
        sa.ForeignKeyConstraint(['org_id'], ['org.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_career_profile_candidate', 'career_profile', ['candidate_id', 'computed_at'])


def downgrade() -> None:
    op.drop_index('ix_career_profile_candidate', table_name='career_profile')
    op.drop_table('career_profile')
