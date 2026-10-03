"""institutions

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-04 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0013'
down_revision: Union[str, Sequence[str], None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'institution',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('normalized', sa.String(), nullable=False),
        sa.Column('official_name', sa.String(), nullable=True),
        sa.Column('country', sa.String(length=2), nullable=True),
        sa.Column('rank', sa.Integer(), nullable=True),
        sa.Column('rank_text', sa.String(), nullable=True),
        sa.Column('rank_band', sa.String(), nullable=True),
        sa.Column('ranking', sa.String(), nullable=True),
        sa.Column('source_url', sa.String(), nullable=True),
        sa.Column('quote', sa.Text(), nullable=True),
        sa.Column('research_status', sa.String(), nullable=True),
        sa.Column('researched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('normalized'),
    )


def downgrade() -> None:
    op.drop_table('institution')
