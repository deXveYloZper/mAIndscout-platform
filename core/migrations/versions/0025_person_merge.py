"""person merge: two records of one person made one, with what moved (so it can be undone)

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-06 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0025'
down_revision: Union[str, Sequence[str], None] = '0024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'person_merge',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('org_id', sa.UUID(), nullable=False),
        sa.Column('keep_id', sa.UUID(), nullable=False),
        sa.Column('drop_id', sa.UUID(), nullable=False),
        sa.Column('moved', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('merged_by', sa.String(), nullable=False),
        sa.Column('merged_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('undone_by', sa.String(), nullable=True),
        sa.Column('undone_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['keep_id'], ['candidate.id']),
        sa.ForeignKeyConstraint(['drop_id'], ['candidate.id']),
        sa.ForeignKeyConstraint(['org_id'], ['org.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_person_merge_keep', 'person_merge', ['keep_id'])


def downgrade() -> None:
    op.drop_index('ix_person_merge_keep', table_name='person_merge')
    op.drop_table('person_merge')
