"""coverage gate and light research

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-03 23:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('candidate', sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('candidate', sa.Column('archived_reason', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('candidate', sa.Column('coverage_override', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('job', sa.Column('open_countries', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False))
    op.add_column('company', sa.Column('research_depth', sa.String(), server_default='full', nullable=False))


def downgrade() -> None:
    op.drop_column('company', 'research_depth')
    op.drop_column('job', 'open_countries')
    op.drop_column('candidate', 'coverage_override')
    op.drop_column('candidate', 'archived_reason')
    op.drop_column('candidate', 'archived_at')
