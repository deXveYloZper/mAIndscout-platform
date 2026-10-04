import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_URL = "postgresql+psycopg://maindscout:maindscout_dev@127.0.0.1:5433/maindscout"  # 127.0.0.1, not localhost: the database listens on IPv4 only


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_URL)


def make_engine(url: str | None = None) -> Engine:
    return create_engine(url or database_url(), pool_pre_ping=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
