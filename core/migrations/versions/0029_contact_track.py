"""phase 1c: the contact track of a person on a role (contacted how and when, their reply, the call)

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-13 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0029'
down_revision: Union[str, Sequence[str], None] = '0028'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('candidate_job', sa.Column('contact', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('candidate_job', 'contact')
