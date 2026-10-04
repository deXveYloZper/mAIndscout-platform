"""review fixes: erasure file keys, company merge audit, contact lookup index

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-05 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0021'
down_revision: Union[str, Sequence[str], None] = '0020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The stored file keys of an erasure, so a later verify can still look for an original that failed to delete.
    op.add_column('erasure', sa.Column('file_keys', postgresql.JSONB(), nullable=False, server_default='[]'))
    # Companies are shared by every desk: a merge records who did it, from which desk, and when.
    op.add_column('company', sa.Column('merged_by', sa.String(), nullable=True))
    op.add_column('company', sa.Column('merged_by_org', sa.UUID(), nullable=True))
    op.add_column('company', sa.Column('merged_at', sa.DateTime(timezone=True), nullable=True))
    # Identity lookup on every CV: a contact by kind and normalized value, without scanning every claim.
    op.execute(
        "CREATE INDEX ix_claim_contact_value ON claim (org_id, (payload->>'kind'), (payload->>'normalized')) "
        "WHERE claim_type = 'ContactClaim'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_claim_contact_value")
    op.drop_column('company', 'merged_at')
    op.drop_column('company', 'merged_by_org')
    op.drop_column('company', 'merged_by')
    op.drop_column('erasure', 'file_keys')
