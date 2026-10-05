"""Performance check on a synthetic desk at a realistic size. No model calls, no cost.

    python -m maindscout perf-seed [--people 3000] [--jobs 20] [--per-job 150]
    python -m maindscout perf-check

`perf-seed` recreates the throwaway database `maindscout_perf` and fills it: synthetic companies, jobs whose
requirements are copied from the jobs on the dev desk (so matching has real requirements), demo people (the same
generator as `demo-seed`: careers, skills, education, career profiles), people put on jobs through the ordinary
pairing (triage and matching), some review cards and timeline entries.

`perf-check` times every main screen and action through the real HTTP API (a signed-in owner) and counts the database
queries each one makes, so a query per row shows up as a count that grows with the desk.
"""

from __future__ import annotations

import os
import random
import statistics
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

PERF_DB = "maindscout_perf"
PERF_ORG = uuid.UUID("00000000-0000-0000-0000-00000000fe4f")


def _use_perf_db() -> None:
    from maindscout.db.session import database_url

    os.environ["DATABASE_URL"] = database_url().rsplit("/", 1)[0] + "/" + PERF_DB


def seed(people: int = 3000, jobs: int = 20, per_job: int = 150, seed_value: int = 7) -> None:
    from sqlalchemy import select

    from maindscout.__main__ import reset_db
    from maindscout.db.session import database_url, make_engine, make_session_factory

    dev_url = database_url()
    # Requirements of the real jobs on the dev desk: copied as payloads only.
    with make_session_factory(make_engine())() as dev:
        from maindscout.db.models import PUBLIC_ORG_ID, Claim, Job, Org

        dev_org = dev.scalar(select(Org.id).where(Org.id != PUBLIC_ORG_ID).order_by(Org.created_at))
        templates = []
        for job in dev.scalars(select(Job).where(Job.org_id == dev_org)):
            reqs = [(c.payload, c.claim_class) for c in dev.scalars(select(Claim).where(
                Claim.subject_id == job.id, Claim.claim_type == "JobRequirementClaim", Claim.status.in_(("proposed", "approved"))))]
            if reqs:
                templates.append((job.title, reqs))
    if not templates:
        raise SystemExit("The dev desk has no jobs with requirements to copy")

    reset_db(PERF_DB, str(PERF_ORG))
    os.environ["DATABASE_URL"] = dev_url.rsplit("/", 1)[0] + "/" + PERF_DB
    os.environ.setdefault("PROFILE_AUTO", "false")
    os.environ.setdefault("RESEARCH_AUTO", "false")
    os.environ.setdefault("AUTH_KEY", "perf-auth-key")
    from maindscout.api import auth, demo, process, writer
    from maindscout.db.models import Activity, Claim, Company, Decision, Job

    rnd = random.Random(seed_value)
    t0 = time.perf_counter()
    with make_session_factory(make_engine())() as session:
        names = ["Northwind", "Contoso", "Fabrikam", "Initech", "Globex", "Umbrella", "Stark", "Wayne", "Tyrell", "Cyberdyne",
                 "Hooli", "Pied Piper", "Vandelay", "Wonka", "Acme", "Soylent", "Oscorp", "Gringotts", "Monarch", "Aperture"]
        for i in range(200):
            name = f"{rnd.choice(names)} {rnd.choice(['Labs', 'Systems', 'Analytics', 'Space', 'Health', 'Pay', 'Cloud'])} {i}"
            session.add(Company(name=name, normalized=name.lower(), research_status="identified", hq_country=rnd.choice(["GB", "DE", "NL", "US"])))
        session.flush()
        print(demo.seed(session, PERF_ORG, people, seed_value))
        session.commit()
        print(f"people seeded in {time.perf_counter() - t0:.0f}s")

        all_people = [c for (c,) in session.execute(select(Claim.subject_id).where(
            Claim.org_id == PERF_ORG, Claim.claim_type == "IdentityClaim"))]
        made_jobs = []
        for j in range(jobs):
            title, reqs = templates[j % len(templates)]
            job = Job(org_id=PERF_ORG, title=f"{title} #{j + 1}", hiring_company=f"Client {j + 1}", state="open")
            session.add(job)
            session.flush()
            for payload, claim_class in reqs:
                key = process.natural_key(job.id, "JobRequirementClaim", payload)
                writer.add_claim(session, org_id=PERF_ORG, subject_type="job", subject_id=job.id, claim_type="JobRequirementClaim",
                                 payload=payload, natural_key=key, status="approved", claim_class=claim_class or "asserted")
            made_jobs.append(job)
        session.commit()
        t1 = time.perf_counter()
        for job in made_jobs:
            for cid in rnd.sample(all_people, k=min(per_job, len(all_people))):
                process._ensure_pair(session, PERF_ORG, cid, job, {"act": "perf_seed"})
            session.commit()
        print(f"{len(made_jobs) * per_job} pairs matched in {time.perf_counter() - t1:.0f}s")

        # Review cards and timelines, so the inbox and person pages have something to show.
        for cid in rnd.sample(all_people, k=min(200, len(all_people))):
            process._decision(session, PERF_ORG, "identity_note", "candidate", cid,
                              {"reason": "perf: same name as an existing person", "candidate_ids": []}, [])
        now = datetime.now(timezone.utc)
        for cid in rnd.sample(all_people, k=min(1500, len(all_people))):
            for k in range(rnd.randint(1, 6)):
                session.add(Activity(org_id=PERF_ORG, subject_type="candidate", subject_id=cid, kind=rnd.choice(["call", "email", "note"]),
                                     direction="out", summary="perf timeline entry", occurred_at=now - timedelta(days=rnd.randint(1, 400)),
                                     created_by="perf@desk.test"))
        auth.create_user(session, "perf@desk.test", "Perf Owner", PERF_ORG, "owner", password="orchard-telescope-quill",
                         totp_secret="JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP")
        session.commit()
        counts = {name: session.scalar(select(__import__("sqlalchemy").func.count()).select_from(model))
                  for name, model in (("people", Claim), ("decisions", Decision), ("activities", Activity))}
        print(f"seeded in {time.perf_counter() - t0:.0f}s: claims {counts['people']}, decisions {counts['decisions']}, activities {counts['activities']}")


def check(rounds: int = 3) -> list[dict[str, Any]]:
    _use_perf_db()
    os.environ.setdefault("AUTH_KEY", "perf-auth-key")
    os.environ.setdefault("LLM_REPLAY", "replay")  # nothing here may spend money
    from fastapi.testclient import TestClient
    from sqlalchemy import event, func, select
    from sqlalchemy.engine import Engine

    from maindscout.api import app as api
    from maindscout.api import auth
    from maindscout.db.models import AppUser, CandidateJob, Claim, Company, Job

    queries = {"n": 0}
    event.listen(Engine, "before_cursor_execute", lambda *a, **k: queries.__setitem__("n", queries["n"] + 1))

    with api._factory()() as session:
        user = session.scalar(select(AppUser).where(AppUser.email == "perf@desk.test"))
        if user is None:
            raise SystemExit("Run `python -m maindscout perf-seed` first")
        token = auth._start_session(session, user, PERF_ORG)["token"]
        big_job = session.scalar(select(Job.id).join(CandidateJob, CandidateJob.job_id == Job.id).group_by(Job.id)
                                 .order_by(func.count().desc()).limit(1))
        pair = session.scalar(select(CandidateJob).where(CandidateJob.job_id == big_job, CandidateJob.triage_band == "priority").limit(1)) \
            or session.scalar(select(CandidateJob).where(CandidateJob.job_id == big_job).limit(1))
        person = pair.candidate_id
        busiest_company = session.scalar(select(Company.id).order_by(Company.name).limit(1))
        skill = session.scalar(select(Claim).where(Claim.subject_id == person, Claim.claim_type == "SkillClaim",
                                                   Claim.status == "proposed").limit(1))
        people = session.scalar(select(func.count()).select_from(Claim).where(Claim.claim_type == "IdentityClaim"))
        pairs = session.scalar(select(func.count()).select_from(CandidateJob))
        session.commit()

    client = TestClient(api.app)
    client.headers.update({"Authorization": f"Bearer {token}"})
    reads = [
        ("Jobs list", "GET", "/v1/jobs"),
        ("Job page (largest job)", "GET", f"/v1/jobs/{big_job}"),
        ("People list", "GET", "/v1/candidates"),
        ("Person page", "GET", f"/v1/candidates/{person}"),
        ("Gap page (person on job)", "GET", f"/v1/jobs/{big_job}/people/{person}/gaps"),
        ("Brief", "GET", f"/v1/jobs/{big_job}/people/{person}/brief?force=true"),
        ("Inbox, one job", "GET", f"/v1/inbox?job_id={big_job}"),
        ("Inbox, all jobs", "GET", "/v1/inbox"),
        ("Companies list", "GET", "/v1/companies"),
        ("Company page", "GET", f"/v1/companies/{busiest_company}"),
        ("Search (structured)", "GET", "/v1/search?family=software_engineering&min_years=3"),
        ("Refresh list", "GET", "/v1/freshness"),
        ("Tags", "GET", "/v1/tags"),
        ("Costs", "GET", "/v1/costs"),
        ("Export (CSV, everyone)", "GET", "/v1/export/people.csv"),
    ]
    results = []
    for label, method, path in reads:
        times, n = [], 0
        for _ in range(rounds):
            queries["n"] = 0
            start = time.perf_counter()
            r = client.request(method, path)
            times.append(time.perf_counter() - start)
            n = queries["n"]
            if r.status_code >= 400:
                results.append({"what": label, "ms": None, "queries": n, "error": f"{r.status_code} {r.text[:120]}"})
                break
        else:
            results.append({"what": label, "ms": round(statistics.median(times) * 1000), "queries": n})

    # Writes: one approval (re-matches the person on every job) and one band change.
    if skill is not None:
        queries["n"] = 0
        start = time.perf_counter()
        r = client.post(f"/v1/claims/{skill.id}/approve")
        results.append({"what": "Approve a fact (re-match)", "ms": round((time.perf_counter() - start) * 1000),
                        "queries": queries["n"], **({"error": r.text[:120]} if r.status_code >= 400 else {})})
    queries["n"] = 0
    start = time.perf_counter()
    r = client.post(f"/v1/jobs/{big_job}/people/{person}/triage", json={"band": "review_later", "reason": "perf"})
    results.append({"what": "Change a band", "ms": round((time.perf_counter() - start) * 1000), "queries": queries["n"],
                    **({"error": r.text[:120]} if r.status_code >= 400 else {})})

    print(f"\nDesk: {people} people, {pairs} people on jobs. Median of {rounds} runs; queries per request.\n")
    width = max(len(r["what"]) for r in results)
    for r in results:
        ms = "error" if r.get("error") else f"{r['ms']:>6} ms"
        print(f"{r['what']:<{width}}  {ms:>9}  {r['queries']:>6} queries  {r.get('error', '')}")
    return results
