"""evidence for strong matches (owner, 2026-10-17): pages read about a person are documents of their own kind, and a
company remembers when its tools and methods were last read from its job adverts

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-17 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0030'
down_revision: Union[str, Sequence[str], None] = '0029'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('document_doc_type', 'document', type_='check')
    op.create_check_constraint('document_doc_type', 'document',
                               "doc_type IN ('cv', 'jd', 'transcript', 'web_profile', 'web_page', 'other')")
    op.add_column('company', sa.Column('practices_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('company', 'practices_at')
    op.execute("DELETE FROM document WHERE doc_type = 'web_page'")
    op.drop_constraint('document_doc_type', 'document', type_='check')
    op.create_check_constraint('document_doc_type', 'document', "doc_type IN ('cv', 'jd', 'transcript', 'web_profile', 'other')")
