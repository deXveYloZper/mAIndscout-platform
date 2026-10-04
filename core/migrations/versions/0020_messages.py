"""messages and mailboxes

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-05 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0020'
down_revision: Union[str, Sequence[str], None] = '0019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'mailbox',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('org_id', sa.UUID(), nullable=False),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('account', sa.String(), nullable=True),
        sa.Column('token_enc', sa.Text(), nullable=False),
        sa.Column('connected_by', sa.String(), nullable=False),
        sa.Column('connected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.CheckConstraint("provider IN ('google', 'microsoft')", name='mailbox_provider'),
        sa.ForeignKeyConstraint(['org_id'], ['org.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'message',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('org_id', sa.UUID(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('candidate_id', sa.UUID(), nullable=True),
        sa.Column('contact_id', sa.UUID(), nullable=True),
        sa.Column('company_id', sa.UUID(), nullable=True),
        sa.Column('job_id', sa.UUID(), nullable=True),
        sa.Column('about_candidate_id', sa.UUID(), nullable=True),
        sa.Column('to_address', sa.String(), nullable=False),
        sa.Column('subject', sa.String(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('provider', sa.String(), nullable=True),
        sa.Column('provider_draft_id', sa.String(), nullable=True),
        sa.Column('provider_thread_id', sa.String(), nullable=True),
        sa.Column('follow_up_of', sa.UUID(), nullable=True),
        sa.Column('follow_up_due', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('replied_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('candidate_outreach', 'follow_up', 'client_submission', 'interview_confirm', 'decline')", name='message_kind'),
        sa.CheckConstraint("status IN ('draft', 'in_mailbox', 'sent', 'replied', 'cancelled')", name='message_status'),
        sa.ForeignKeyConstraint(['about_candidate_id'], ['candidate.id']),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidate.id']),
        sa.ForeignKeyConstraint(['company_id'], ['company.id']),
        sa.ForeignKeyConstraint(['contact_id'], ['client_contact.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['follow_up_of'], ['message.id']),
        sa.ForeignKeyConstraint(['job_id'], ['job.id']),
        sa.ForeignKeyConstraint(['org_id'], ['org.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_message_candidate', 'message', ['org_id', 'candidate_id'])


def downgrade() -> None:
    op.drop_index('ix_message_candidate', table_name='message')
    op.drop_table('message')
    op.drop_table('mailbox')
