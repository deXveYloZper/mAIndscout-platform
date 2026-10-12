"""the talent-release radar: news that a company is releasing talent, with the sentence that says so

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-12 23:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0027'
down_revision: Union[str, Sequence[str], None] = '0026'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KINDS = ("layoffs", "insolvency", "shutdown", "office_closure", "acquisition", "restructuring", "hiring_freeze",
         "funding_trouble")


def upgrade() -> None:
    op.create_table(
        'company_signal',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('org_id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('quote', sa.Text(), nullable=False),
        sa.Column('url', sa.String(), nullable=False),
        sa.Column('published', sa.Date(), nullable=True),
        sa.Column('job_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['org.id']),
        sa.ForeignKeyConstraint(['company_id'], ['company.id']),
        sa.ForeignKeyConstraint(['job_id'], ['job.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("kind IN (" + ", ".join(f"'{k}'" for k in KINDS) + ")", name='company_signal_kind'),
        sa.UniqueConstraint('org_id', 'company_id', 'url', 'kind', name='company_signal_once'),
    )
    op.create_index('ix_company_signal_company_id', 'company_signal', ['company_id'])


def downgrade() -> None:
    op.drop_index('ix_company_signal_company_id', table_name='company_signal')
    op.drop_table('company_signal')
