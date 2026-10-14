"""sourcing engine: plans, runs, queries, who found whom, off-limits, permissions; web profiles; "stop"; desk settings

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-12 18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0026'
down_revision: Union[str, Sequence[str], None] = '0025'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def _base(name: str, *columns, constraints=()):
    op.create_table(
        name,
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('org_id', sa.UUID(), nullable=False),
        *columns,
        sa.ForeignKeyConstraint(['org_id'], ['org.id']),
        sa.PrimaryKeyConstraint('id'),
        *constraints,
    )


def upgrade() -> None:
    op.drop_constraint('document_doc_type', 'document', type_='check')
    op.create_check_constraint('document_doc_type', 'document', "doc_type IN ('cv', 'jd', 'transcript', 'web_profile', 'other')")
    op.add_column('org', sa.Column('settings', JSONB, server_default='{}', nullable=False))
    op.add_column('candidate', sa.Column('do_not_contact_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('candidate', sa.Column('do_not_contact_note', sa.Text(), nullable=True))

    _base('sourcing_plan',
          sa.Column('job_id', sa.UUID(), sa.ForeignKey('job.id'), nullable=False),
          sa.Column('version', sa.Integer(), nullable=False),
          sa.Column('mode', sa.String(), nullable=False),
          sa.Column('target', sa.Integer(), nullable=False),
          sa.Column('monthly_budget_usd', sa.Numeric(10, 2), nullable=False),
          sa.Column('targets', JSONB, nullable=False),
          sa.Column('role_variants', JSONB, nullable=False),
          sa.Column('countries', JSONB, nullable=False),
          sa.Column('created_by', sa.String(), nullable=False),
          sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
          sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=True),
          constraints=(sa.CheckConstraint("mode IN ('daily', 'weekly', 'continuous', 'paused')", name='sourcing_plan_mode'),
                       sa.UniqueConstraint('job_id', 'version', name='sourcing_plan_job_version')))

    _base('sourcing_run',
          sa.Column('job_id', sa.UUID(), sa.ForeignKey('job.id'), nullable=False),
          sa.Column('plan_id', sa.UUID(), sa.ForeignKey('sourcing_plan.id'), nullable=False),
          sa.Column('trigger', sa.String(), nullable=False),
          sa.Column('status', sa.String(), nullable=False),
          sa.Column('stop_reason', sa.String(), nullable=True),
          sa.Column('found', sa.Integer(), nullable=False),
          sa.Column('new', sa.Integer(), nullable=False),
          sa.Column('known', sa.Integer(), nullable=False),
          sa.Column('refused', sa.Integer(), nullable=False),
          sa.Column('strong', sa.Integer(), nullable=False),
          sa.Column('cost_usd', sa.Numeric(10, 4), nullable=False),
          sa.Column('report', JSONB, nullable=False),
          sa.Column('error', sa.Text(), nullable=True),
          sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
          sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
          constraints=(sa.CheckConstraint("status IN ('running', 'done', 'stopped', 'failed')", name='sourcing_run_status'),))
    op.create_index('ix_sourcing_run_job', 'sourcing_run', ['job_id', 'started_at'])

    _base('sourcing_query',
          sa.Column('job_id', sa.UUID(), sa.ForeignKey('job.id'), nullable=False),
          sa.Column('key', sa.String(), nullable=False),
          sa.Column('channel', sa.String(), nullable=False),
          sa.Column('text', sa.String(), nullable=False),
          sa.Column('target', sa.String(), nullable=True),
          sa.Column('tier', sa.String(), nullable=True),
          sa.Column('country', sa.String(2), nullable=True),
          sa.Column('runs', sa.Integer(), nullable=False),
          sa.Column('results', sa.Integer(), nullable=False),
          sa.Column('new', sa.Integer(), nullable=False),
          sa.Column('cost_usd', sa.Numeric(10, 4), nullable=False),
          sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
          sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
          constraints=(sa.UniqueConstraint('job_id', 'key', name='sourcing_query_job_key'),))

    _base('sourcing_hit',
          sa.Column('job_id', sa.UUID(), sa.ForeignKey('job.id'), nullable=False),
          sa.Column('candidate_id', sa.UUID(), sa.ForeignKey('candidate.id'), nullable=False),
          sa.Column('run_id', sa.UUID(), sa.ForeignKey('sourcing_run.id'), nullable=False),
          sa.Column('query_id', sa.UUID(), sa.ForeignKey('sourcing_query.id'), nullable=True),
          sa.Column('channel', sa.String(), nullable=False),
          sa.Column('target', sa.String(), nullable=True),
          sa.Column('tier', sa.String(), nullable=True),
          sa.Column('new_to_desk', sa.Boolean(), nullable=False),
          sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
          constraints=(sa.UniqueConstraint('job_id', 'candidate_id', name='sourcing_hit_job_person'),))
    op.create_index('ix_sourcing_hit_candidate', 'sourcing_hit', ['candidate_id'])

    _base('off_limits',
          sa.Column('company_id', sa.UUID(), sa.ForeignKey('company.id'), nullable=False),
          sa.Column('reason', sa.String(), nullable=False),
          sa.Column('until', sa.Date(), nullable=True),
          sa.Column('note', sa.Text(), nullable=True),
          sa.Column('created_by', sa.String(), nullable=False),
          sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
          sa.Column('removed_by', sa.String(), nullable=True),
          sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True),
          constraints=(sa.CheckConstraint("reason IN ('client', 'placement', 'manual')", name='off_limits_reason'),))

    _base('permission',
          sa.Column('candidate_id', sa.UUID(), sa.ForeignKey('candidate.id'), nullable=False),
          sa.Column('job_id', sa.UUID(), sa.ForeignKey('job.id'), nullable=True),
          sa.Column('scope', sa.String(), nullable=False),
          sa.Column('how', sa.String(), nullable=True),
          sa.Column('note', sa.Text(), nullable=True),
          sa.Column('recorded_by', sa.String(), nullable=False),
          sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
          constraints=(sa.CheckConstraint("scope IN ('this_role', 'other_roles')", name='permission_scope'),))
    op.create_index('ix_permission_candidate', 'permission', ['candidate_id'])


def downgrade() -> None:
    op.drop_index('ix_permission_candidate', table_name='permission')
    op.drop_table('permission')
    op.drop_table('off_limits')
    op.drop_index('ix_sourcing_hit_candidate', table_name='sourcing_hit')
    op.drop_table('sourcing_hit')
    op.drop_table('sourcing_query')
    op.drop_index('ix_sourcing_run_job', table_name='sourcing_run')
    op.drop_table('sourcing_run')
    op.drop_table('sourcing_plan')
    op.drop_column('candidate', 'do_not_contact_note')
    op.drop_column('candidate', 'do_not_contact_at')
    op.drop_column('org', 'settings')
    op.drop_constraint('document_doc_type', 'document', type_='check')
    op.create_check_constraint('document_doc_type', 'document', "doc_type IN ('cv', 'jd', 'transcript', 'other')")
