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


OWNER = "owner@desk.test"
PASSWORD = "correct horse battery staple"
TOTP = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"


@pytest.fixture
def owner(session, org, monkeypatch):
    """The desk's owner, signed up with a password and two-step codes (access plan)."""
    from maindscout.api import auth

    monkeypatch.setenv("AUTH_KEY", "test-auth-key")
    user, _ = auth.create_user(session, OWNER, "Desk Owner", org.id, "owner", password=PASSWORD, totp_secret=TOTP)
    return user


@pytest.fixture(autouse=True)
def no_paid_calls(monkeypatch):
    """Tests never reach a paid API: in Docker the repo (and core/.env with real keys) is mounted. Background work
    that would build a real model, research or Exa client gets one that refuses; a test that needs one sets its own."""
    from maindscout.api import task_handlers
    from maindscout.intelligence.llm import LLMError

    class NoPaidCalls:
        model = "no-paid-calls"

        def complete_json(self, *args, **kwargs):
            raise LLMError("tests never call the real model")

        def search_json(self, *args, **kwargs):
            raise LLMError("tests never call the real research search")

    monkeypatch.setattr(task_handlers, "llm_factory", lambda: NoPaidCalls())
    monkeypatch.setattr(task_handlers, "search_factory", lambda: NoPaidCalls())
    monkeypatch.setattr(task_handlers, "exa_factory", lambda: None)


class TitleReader:
    """The career reading's model, from each job's title, as the real one would label it (no model call)."""

    model = "fake-reader"
    FAMILIES = [(r"insar|sar\b|radar|remote sens|geodes|earth observation|gis", "gis_remote_sensing"),
                (r"data scien|machine learning|\bml\b", "data_ml"), (r"marketing|brand|communication", "marketing"),
                (r"sales|account exec|business develop", "sales"), (r"engineer|developer|programmer|software", "software_engineering")]

    def complete_json(self, system, user, schema, name):
        import re

        from maindscout.intelligence.llm import LLMResult

        steps = []
        for sid, title in re.findall(r"^(s\d+): (.+?) at ", user, re.M):
            family = next((f for rx, f in self.FAMILIES if re.search(rx, title, re.I)), "other")
            steps.append({"id": sid, "role_family": family, "level": None, "domains": [], "signals": []})
        return LLMResult({"steps": steps}, self.model, 1, 1, 0.0)


@pytest.fixture
def careers_read_at_once(monkeypatch):
    """The background career reading, done at once. Nobody is Priority before it (owner, 2026-10-21), so a test of a
    person's band after an upload needs the reading the desk would have done by then."""
    from maindscout.api import profiles

    busy = set()

    def now(session, org_id, candidate_id):
        if candidate_id in busy:
            return
        busy.add(candidate_id)
        try:
            profiles.run(session, org_id, candidate_id, TitleReader)
        finally:
            busy.discard(candidate_id)

    monkeypatch.setattr(profiles, "queue", now)
