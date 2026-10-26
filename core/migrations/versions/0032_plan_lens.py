"""a role's lens on its plan (owner, 2026-10-26: "we shouldn't start our searches from the deepest, but do have an
option if we want to reach more specific person"): the role's own line of business (its industry, market, positioning,
customers), used to order the search, and an optional focus the owner chose to narrow it

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-26 22:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0032'
down_revision: Union[str, Sequence[str], None] = '0031'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('sourcing_plan', sa.Column('lens', postgresql.JSONB(), nullable=False, server_default='{}'))


def downgrade() -> None:
    op.drop_column('sourcing_plan', 'lens')
