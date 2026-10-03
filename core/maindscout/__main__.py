"""Operator commands.

    python -m maindscout init [--org NAME]   migrate, seed registries, create the org if none exists, print its id
    python -m maindscout serve [--port 8765] run the API
    python -m maindscout eval [--folder DIR] [--with-tests]   golden eval over real files (Milestone G)
    python -m maindscout reset-db NAME --org-id UUID   recreate a throwaway database (*_e2e/_test/_eval only)
    python -m maindscout link-companies      resolve companies for existing career steps and jobs
    python -m maindscout worker [--threads 2] run background tasks (serve also starts workers unless --no-workers)
"""

from __future__ import annotations

import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from maindscout.api import writer
from maindscout.db.models import Org
from maindscout.db.session import make_engine, make_session_factory


def _ensure_suppression_key() -> None:
    """Erasure hashes identifiers with this key. Lose it and old suppression entries stop matching."""
    import secrets

    from maindscout.settings import ENV_FILE, env

    if env("SUPPRESSION_KEY"):
        return
    with open(ENV_FILE, "a", encoding="utf-8") as f:
        f.write("\nSUPPRESSION_KEY=" + secrets.token_urlsafe(32) + "\n")
    print(f"SUPPRESSION_KEY created in {ENV_FILE}. Back it up with the database.")


def init(org_name: str) -> None:
    _ensure_suppression_key()
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
    with make_session_factory(make_engine())() as session:
        writer.seed_registries(session)
        org = session.scalar(select(Org).order_by(Org.created_at))
        if org is None:
            org = writer.create_org(session, org_name)
        session.commit()
        print(f"org id: {org.id}  ({org.name})")


def reset_db(name: str, org_id: str) -> None:
    """Drop and recreate a throwaway database, migrate, seed, and create one org with a known id."""
    import os
    import re
    import uuid

    from sqlalchemy import create_engine, text

    from maindscout.db.session import database_url

    if not re.fullmatch(r"[a-z0-9_]+_(e2e|test|eval)", name):
        raise SystemExit("refusing: only databases named *_e2e, *_test or *_eval can be reset")
    admin = create_engine(database_url(), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {name}"))
    admin.dispose()
    os.environ["DATABASE_URL"] = database_url().rsplit("/", 1)[0] + "/" + name
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
    with make_session_factory(make_engine())() as session:
        writer.seed_registries(session)
        session.add(Org(id=uuid.UUID(org_id), name=name))
        session.commit()
    print(f"{name} ready, org {org_id}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="maindscout")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init")
    p_init.add_argument("--org", default="mAIndscout")
    p_serve = sub.add_parser("serve")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.add_argument("--database", default=None, help="serve another database on the same server, e.g. maindscout_e2e")
    p_serve.add_argument("--no-workers", action="store_true", help="do not run background workers in this process")
    p_worker = sub.add_parser("worker")
    p_worker.add_argument("--threads", type=int, default=2)
    p_eval = sub.add_parser("eval")
    p_eval.add_argument("--folder", type=Path, default=None)
    p_eval.add_argument("--with-tests", action="store_true")
    sub.add_parser("link-companies")
    p_reset = sub.add_parser("reset-db")
    p_reset.add_argument("name")
    p_reset.add_argument("--org-id", required=True)
    args = parser.parse_args()
    if args.cmd == "init":
        init(args.org)
    elif args.cmd == "worker":
        from maindscout.api import task_handlers  # noqa: F401 (registers task kinds)
        from maindscout.api.tasks import start_threads, work_forever

        factory = make_session_factory(make_engine())
        start_threads(factory, max(args.threads - 1, 0))
        work_forever(factory, "worker-main")
    elif args.cmd == "link-companies":
        from maindscout.api import companies

        with make_session_factory(make_engine())() as session:
            for org in session.scalars(select(Org)):
                print(org.name, companies.link_org(session, org.id))
            session.commit()
    elif args.cmd == "reset-db":
        reset_db(args.name, args.org_id)
    elif args.cmd == "eval":
        from maindscout.evals.golden import main as eval_main

        raise SystemExit(eval_main(args.folder, args.with_tests))
    else:
        import os

        import uvicorn

        if args.database:
            from maindscout.db.session import database_url

            os.environ["DATABASE_URL"] = database_url().rsplit("/", 1)[0] + "/" + args.database
        if not args.no_workers:
            from maindscout.api import task_handlers  # noqa: F401 (registers task kinds)
            from maindscout.api.tasks import start_threads

            start_threads(make_session_factory(make_engine()), int(os.environ.get("WORKERS", "2")))

        uvicorn.run("maindscout.api.app:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
