"""pair states, outcomes, and permanent pairs

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE candidate_job SET pair_state = 'new' WHERE pair_state NOT IN ('new', 'seen', 'submitted', 'we_passed')")
    op.alter_column("candidate_job", "pair_state", server_default=None)
    op.create_check_constraint("pair_state", "candidate_job", "pair_state IN ('new', 'seen', 'submitted', 'we_passed')")
    op.add_column("candidate_job", sa.Column("outcome", postgresql.JSONB(), nullable=True))
    # A pair is permanent: it changes state, it is never deleted. Only the erasure workflow may delete one,
    # and it must say so for its own transaction (SET LOCAL maindscout.erasure = 'on').
    op.execute("""
        CREATE FUNCTION forbid_pair_delete() RETURNS trigger AS $$
        BEGIN
            IF current_setting('maindscout.erasure', true) = 'on' THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION 'person-job pairs are permanent: change the state instead of deleting';
        END
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER candidate_job_no_delete BEFORE DELETE ON candidate_job
        FOR EACH ROW EXECUTE FUNCTION forbid_pair_delete();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS candidate_job_no_delete ON candidate_job")
    op.execute("DROP FUNCTION IF EXISTS forbid_pair_delete()")
    op.drop_column("candidate_job", "outcome")
    op.drop_constraint("pair_state", "candidate_job", type_="check")
