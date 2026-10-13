"""phase 1b: company identity keys and profiles; a staged search (talent DNA, tiers, rules, progress per company)

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-13 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0028'
down_revision: Union[str, Sequence[str], None] = '0027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    # Identity keys: a company is found by its website, its Exa company id or its LinkedIn page before its name.
    op.add_column('company', sa.Column('domain', sa.String(), nullable=True))
    op.add_column('company', sa.Column('exa_id', sa.String(), nullable=True))
    op.add_column('company', sa.Column('linkedin', sa.String(), nullable=True))
    op.add_column('company', sa.Column('exa_profile', JSONB, nullable=True))
    op.add_column('company', sa.Column('profiled_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_company_domain', 'company', ['domain'])
    op.create_unique_constraint('company_exa_id', 'company', ['exa_id'])
    op.create_unique_constraint('company_linkedin', 'company', ['linkedin'])
    op.execute(r"""UPDATE company SET domain = lower(regexp_replace(regexp_replace(website, '^\s*(https?://)?(www\.)?', ''), '[/?#:].*$', ''))
                   WHERE website IS NOT NULL AND website <> ''""")

    # The staged search: the talent DNA of the hiring company, the rules that decide exhaustion and widening, and the
    # tiers open for searching.
    op.add_column('sourcing_plan', sa.Column('dna', JSONB, nullable=True))
    op.add_column('sourcing_plan', sa.Column('rules', JSONB, server_default='{}', nullable=False))
    op.add_column('sourcing_plan', sa.Column('open_tiers', JSONB, server_default='["A", "B"]', nullable=False))

    # Progress per company: which company a search aimed at, and what it brought.
    op.add_column('sourcing_query', sa.Column('company_id', sa.UUID(), nullable=True))
    op.add_column('sourcing_query', sa.Column('relevant', sa.Integer(), server_default='0', nullable=False))
    op.add_column('sourcing_query', sa.Column('known', sa.Integer(), server_default='0', nullable=False))
    op.create_index('ix_sourcing_query_company', 'sourcing_query', ['job_id', 'company_id'])


def downgrade() -> None:
    op.drop_index('ix_sourcing_query_company', table_name='sourcing_query')
    op.drop_column('sourcing_query', 'known')
    op.drop_column('sourcing_query', 'relevant')
    op.drop_column('sourcing_query', 'company_id')
    op.drop_column('sourcing_plan', 'open_tiers')
    op.drop_column('sourcing_plan', 'rules')
    op.drop_column('sourcing_plan', 'dna')
    op.drop_constraint('company_linkedin', 'company', type_='unique')
    op.drop_constraint('company_exa_id', 'company', type_='unique')
    op.drop_index('ix_company_domain', table_name='company')
    op.drop_column('company', 'profiled_at')
    op.drop_column('company', 'exa_profile')
    op.drop_column('company', 'linkedin')
    op.drop_column('company', 'exa_id')
    op.drop_column('company', 'domain')
