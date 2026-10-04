"""I6: people search over career profiles, target-company alumni, profile-driven sourcing, and the demo desk."""

import uuid

from sqlalchemy import select

from maindscout.api import demo, search, sourcing
from maindscout.db.models import Candidate, CandidateJob, Company, Job
from maindscout.domain.profile import build
from tests.test_api import client, drop_cv, fake, make_job  # noqa: F401 (fixtures)
from tests.test_profile_rubric import AS_OF, stint


def org_of(client):
    return uuid.UUID(client.headers["X-Org-Id"])


def test_filters_pass_only_profiles_that_meet_every_one():
    from maindscout.domain.profile import CompanyFacts

    start = CompanyFacts(kind="product", team_min=20)
    p = build([stint(1, "S", "Senior Data Scientist", "2016-01", None, family="data_ml", level="senior", facts=start,
                     domains=["fintech"])], [], AS_OF)
    assert search.passes(p, search.Filters(family="data_ml", min_years=5, level="senior")) is not None
    assert search.passes(p, search.Filters(family="gis_remote_sensing")) is not None, "related work counts by default"
    assert search.passes(p, search.Filters(family="gis_remote_sensing", related=False)) is None
    assert search.passes(p, search.Filters(employer_kinds=["startup"], domains=["fintech"])) is not None
    assert search.passes(p, search.Filters(level="lead")) is None
    assert search.passes(p, search.Filters(domains=["banking"])) is None
    assert search.passes(p, search.Filters(min_years=20)) is None


def test_the_demo_desk_is_clearly_synthetic_searchable_and_erasable(client, fake, session, tmp_path):
    org = org_of(client)
    made = demo.seed(session, org, count=25)
    assert made["people"] == 25
    ids = demo.demo_people(session, org)
    assert len(ids) == 25
    rows = search.search(session, org, search.Filters())
    assert rows and all(r["name"].startswith("Demo · ") for r in rows)
    engineers = search.search(session, org, search.Filters(family="software_engineering", min_years=3))
    assert all("software engineering" in r["met"][0] or "technical work" in r["met"][0] for r in engineers)
    archived = session.scalars(select(Candidate).where(Candidate.id.in_(ids), Candidate.archived_at.is_not(None))).all()
    assert not {str(c.id) for c in archived} & {r["candidate_id"] for r in rows}, "archived people are never searched"
    from maindscout.storage import LocalBlobStore

    assert demo.clear(session, LocalBlobStore(tmp_path), org) == 25
    assert demo.demo_people(session, org) == []


def test_alumni_of_a_company_and_the_search_route(client, fake, session):
    job = make_job(client)
    cid = drop_cv(client, job)["subject_id"]  # Jane: Acme Space
    acme = session.scalar(select(Company).where(Company.normalized == "acme space"))
    assert [p["candidate_id"] for p in search.alumni(session, org_of(client), acme.id)] == [cid]
    r = client.get("/v1/search", params={"family": "software_engineering"})
    assert r.status_code == 200 and r.json()["people"] == [], "no career profile yet: not searchable"


def test_a_job_with_a_hiring_profile_is_sourced_by_profile_and_target_alumni_first(client, fake, session):
    org = org_of(client)
    demo.seed(session, org, count=30)
    job = make_job(client)
    client.post(f"/v1/jobs/{job}/requirements", json={"category": "role", "strength": "must", "text_raw": "Software engineer",
                                                     "role_family": "software_engineering"})
    query = sourcing.profile_query(session, session.get(Job, uuid.UUID(job)))
    assert query["filters"]["family"] == "software_engineering"
    r = client.post(f"/v1/jobs/{job}/campaigns", json={"cap": 10, "target": 50})
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["source"] == "profile" and c["query"]["words"] and 0 < c["added"] <= 10
    on_job = session.scalars(select(CandidateJob).where(CandidateJob.job_id == uuid.UUID(job))).all()
    assert all(p.match_tier for p in on_job), "everyone found goes through matching"


def test_a_job_without_a_hiring_profile_still_sources_by_keywords(client, fake, session):
    job = make_job(client)
    r = client.post(f"/v1/jobs/{job}/campaigns", json={})
    assert r.status_code == 201 and r.json()["source"] == "desk"
