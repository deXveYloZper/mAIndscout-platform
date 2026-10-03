"""matching v2 on pairs

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-04 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0015'
down_revision: Union[str, Sequence[str], None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('candidate_job', sa.Column('match_tier', sa.String(), nullable=True))
    op.add_column('candidate_job', sa.Column('match', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_check_constraint('pair_match_tier', 'candidate_job',
                               "match_tier IS NULL OR match_tier IN ('strong', 'possible', 'unlikely', 'unclear')")


def downgrade() -> None:
    op.drop_constraint('pair_match_tier', 'candidate_job', type_='check')
    op.drop_column('candidate_job', 'match')
    op.drop_column('candidate_job', 'match_tier')
