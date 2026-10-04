"""Operator commands.

    python -m maindscout init [--org NAME]   migrate, seed registries, create the org if none exists, print its id
    python -m maindscout serve [--port 8765] run the API
    python -m maindscout eval [--folder DIR] [--with-tests]   golden eval over real files (Milestone G)
    python -m maindscout reset-db NAME --org-id UUID   recreate a throwaway database (*_e2e/_test/_eval only)
    python -m maindscout link-companies      resolve companies for existing career steps and jobs
    python -m maindscout research-backlog    queue company research for people and jobs already on the desk
    python -m maindscout research-recheck    apply the current checks to stored company facts (free)
    python -m maindscout coverage-check      apply the coverage rule to everyone already on the desk (free)
    python -m maindscout profiles-rebuild [--reclassify]  rebuild career profiles (reclassify: read step labels again, paid)
    python -m maindscout rematch             match every person on every job again (free)
    python -m maindscout demo-seed [--count 60]  add synthetic demo people ("Demo · ", @example.invalid) for testing
    python -m maindscout demo-clear          erase every demo person
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


def _ensure_mailbox_key() -> None:
    """Connected mailboxes' tokens are encrypted with this key (Fernet). Lose it and mailboxes must be reconnected."""
    from cryptography.fernet import Fernet

    from maindscout.settings import ENV_FILE, env

    if env("MAILBOX_KEY"):
        return
    with open(ENV_FILE, "a", encoding="utf-8") as f:
        f.write("\nMAILBOX_KEY=" + Fernet.generate_key().decode() + "\n")
    print(f"MAILBOX_KEY created in {ENV_FILE}. Back it up with the database.")


def init(org_name: str) -> None:
    _ensure_suppression_key()
    _ensure_mailbox_key()
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
    with make_session_factory(make_engine())() as session:
        writer.seed_registries(session)
        from maindscout.db.models import PUBLIC_ORG_ID

        org = session.scalar(select(Org).where(Org.id != PUBLIC_ORG_ID).order_by(Org.created_at))
        if org is None:
            org = writer.create_org(session, org_name)
        session.commit()
        print(f"org id: {org.id}  ({org.name})")


def _seed() -> None:
    """Claim and flag types from slice0/registry: new types (e.g. from a later phase) are known before any work runs."""
    with make_session_factory(make_engine())() as session:
        writer.seed_registries(session)
        session.commit()


def _start_mailbox_clock(factory, every: int = 300) -> None:
    """Every few minutes, queue a look at each connected mailbox (sent drafts, replies, follow-ups due)."""
    import threading
    import time

    from maindscout.api import tasks
    from maindscout.db.models import Mailbox

    def loop() -> None:
        while True:
            try:
                with factory() as session:
                    for box in session.scalars(select(Mailbox).where(Mailbox.status == "connected")):
                        tasks.enqueue(session, box.org_id, "mailbox_sync", {}, priority=60, dedupe_key=f"mailsync:{box.org_id}")
                    session.commit()
            except Exception:  # noqa: BLE001 - the clock must keep ticking
                pass
            time.sleep(every)

    threading.Thread(target=loop, name="mailbox-clock", daemon=True).start()


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
    sub.add_parser("research-backlog")
    sub.add_parser("research-recheck")
    sub.add_parser("coverage-check")
    p_prof = sub.add_parser("profiles-rebuild")
    p_prof.add_argument("--reclassify", action="store_true")
    sub.add_parser("rematch")
    p_demo = sub.add_parser("demo-seed")
    p_demo.add_argument("--count", type=int, default=60)
    sub.add_parser("demo-clear")
    p_reset = sub.add_parser("reset-db")
    p_reset.add_argument("name")
    p_reset.add_argument("--org-id", required=True)
    args = parser.parse_args()
    if args.cmd == "init":
        init(args.org)
    elif args.cmd == "worker":
        from maindscout.api import task_handlers  # noqa: F401 (registers task kinds)
        from maindscout.api.tasks import start_threads, work_forever

        _seed()
        factory = make_session_factory(make_engine())
        start_threads(factory, max(args.threads - 1, 0))
        work_forever(factory, "worker-main")
    elif args.cmd == "link-companies":
        from maindscout.api import companies

        with make_session_factory(make_engine())() as session:
            for org in session.scalars(select(Org)):
                print(org.name, companies.link_org(session, org.id))
            session.commit()
    elif args.cmd == "research-backlog":
        from maindscout.api import process, research, tasks
        from maindscout.db.models import PUBLIC_ORG_ID, Candidate, Company, Job

        with make_session_factory(make_engine())() as session:
            queued = 0
            for org in session.scalars(select(Org).where(Org.id != PUBLIC_ORG_ID)):
                for cid in session.scalars(select(Candidate.id).where(Candidate.org_id == org.id)):
                    queued += process._queue_research(session, cid, org.id)
                for job in session.scalars(select(Job).where(Job.org_id == org.id, Job.hiring_company_id.is_not(None))):
                    company = session.get(Company, job.hiring_company_id)
                    if company is not None and research.due(company):
                        tasks.enqueue(session, None, "research_company", {"company_id": str(company.id), "context": "named in a job advertisement"},
                                      priority=80, dedupe_key=f"research:{company.id}")
                        queued += 1
            session.commit()
            print(f"queued {queued} (repeats of the same company collapse into one task)")
    elif args.cmd == "research-recheck":
        from maindscout.api import research

        with make_session_factory(make_engine())() as session:
            dropped = research.recheck(session)
            session.commit()
            for d in dropped:
                print(d["claim_type"], "-", d["reason"])
            print(f"rejected {len(dropped)} stored fact(s)")
    elif args.cmd == "coverage-check":
        from maindscout.api import coverage, research
        from maindscout.db.models import PUBLIC_ORG_ID, Candidate, Claim, Company

        with make_session_factory(make_engine())() as session:
            # Companies researched before the gate existed: take their base from the stored head-office fact.
            for company in session.scalars(select(Company).where(Company.hq_country.is_(None))):
                hq = session.scalar(select(Claim).where(Claim.org_id == PUBLIC_ORG_ID, Claim.subject_id == company.id,
                                                        Claim.claim_type == "CompanyLocationClaim", Claim.status.in_(("proposed", "approved"))))
                if hq is not None and hq.payload.get("hq_country"):
                    company.hq_country = hq.payload["hq_country"]
            archived = kept = 0
            for org in session.scalars(select(Org).where(Org.id != PUBLIC_ORG_ID)):
                for cid in list(session.scalars(select(Candidate.id).where(Candidate.org_id == org.id, Candidate.merged_into_id.is_(None)))):
                    verdict = coverage.evaluate(session, org.id, cid, {"act": "coverage_check"})
                    archived, kept = archived + verdict.outside, kept + (not verdict.outside)
            session.commit()
            print(f"in coverage {kept}, archived {archived}")
    elif args.cmd == "profiles-rebuild":
        from maindscout.api import profiles

        _seed()
        with make_session_factory(make_engine())() as session:
            print(profiles.rebuild_all(session, args.reclassify))
            session.commit()
        print("queued: the workers (serve, or `worker`) build them")
    elif args.cmd == "rematch":
        from maindscout.api.process import retriage_pair
        from maindscout.db.models import CandidateJob

        with make_session_factory(make_engine())() as session:
            changed = 0
            for pair in session.scalars(select(CandidateJob)):
                changed += retriage_pair(session, pair, {"act": "rematch"}, "system") is not None
            session.commit()
            print(f"bands changed: {changed}")
    elif args.cmd in ("demo-seed", "demo-clear"):
        import os

        from maindscout.api import demo
        from maindscout.db.models import PUBLIC_ORG_ID
        from maindscout.settings import env
        from maindscout.storage import LocalBlobStore

        os.environ.setdefault("PROFILE_AUTO", "false")  # profiles are built right here; no background work needed
        _seed()
        with make_session_factory(make_engine())() as session:
            org = session.scalar(select(Org).where(Org.id != PUBLIC_ORG_ID).order_by(Org.created_at))
            if args.cmd == "demo-seed":
                print(demo.seed(session, org.id, args.count))
            else:
                print(f"erased {demo.clear(session, LocalBlobStore(env('BLOB_DIR')), org.id)} demo people")
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
        _seed()
        if not args.no_workers:
            from maindscout.api import task_handlers  # noqa: F401 (registers task kinds)
            from maindscout.api.tasks import start_threads

            factory = make_session_factory(make_engine())
            start_threads(factory, int(os.environ.get("WORKERS", "2")))
            _start_mailbox_clock(factory)

        uvicorn.run("maindscout.api.app:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
