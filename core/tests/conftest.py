import os
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from maindscout.api import writer
from maindscout.db.models import Base
from maindscout.db.session import DEFAULT_URL

ADMIN_URL = os.environ.get("TEST_ADMIN_URL", DEFAULT_URL)
TEST_DB = "maindscout_test"


def _with_db(url: str, name: str) -> str:
    return url.rsplit("/", 1)[0] + "/" + name


@pytest.fixture(scope="session")
def engine():
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB}"))
    admin.dispose()
    url = _with_db(ADMIN_URL, TEST_DB)
    os.environ["DATABASE_URL"] = url  # alembic env reads this
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    command.upgrade(cfg, "head")
    eng = create_engine(url)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    """A session whose work is thrown away after each test."""
    conn = engine.connect()
    trans = conn.begin()
    sess = Session(conn, join_transaction_mode="create_savepoint")
    writer.seed_registries(sess)
    yield sess
    sess.close()
    trans.rollback()
    conn.close()


@pytest.fixture
def org(session):
    return writer.create_org(session, "test-org")


@pytest.fixture
def candidate_id():
    return uuid.uuid4()
