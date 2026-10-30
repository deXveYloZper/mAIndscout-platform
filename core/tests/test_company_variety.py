"""A varied list of strong suggestions (owner, 2026-10-29: "if we find more than 5 people that we believe are strong ...
from the same company ... we should propose only 5 candidates at the time, and keep the rest in the bank ... but our
sourcing should continue with other companies"; 21 of Procure AI's 25 strong were at Omnea): at most `per_company`
strong suggestions per company where they work now, the rest held back by company and never lost, the target counted
the same way, and a company that gave its share searched again only after the others. Fakes only: nothing is spent."""

import uuid
from datetime import date, datetime, timezone

import pytest

from maindscout.api import autosource, companies, strategy
from maindscout.db.models import Candidate, CandidateJob, Claim, SourcingHit, SourcingQuery, SourcingRun
from tests.test_api import client, fake, make_job  # noqa: F401 (fixtures)
from tests.test_autosource import blobs, job  # noqa: F401

OWNER = "owner@desk.test"


@pytest.fixture
def run(session, job):
    p = autosource.plan(session, job.org_id, job.id, OWNER)
    row = SourcingRun(org_id=job.org_id, job_id=job.id, plan_id=p.id, trigger="manual", status="done", report={})
    session.add(row)
    session.flush()
    return row


def company(session, name):
    found, _ = companies.resolve(session, name, "test")
    return found


def step(session, job, person, at, title="CRM specialist", start=date(2022, 1, 1), end=None):
    session.add(Claim(org_id=job.org_id, subject_type="candidate", subject_id=person.id, claim_type="CareerStepClaim",
                      status="approved", payload={"company": {"raw_name": at.name, "company_id": str(at.id)}, "title_raw": title},
                      valid_from=start, valid_to=end, natural_key=f"{person.id}|{title}|{start}", flags={}))
    session.flush()


def found(session, job, run, at, band="priority", name=None):
    """Someone the role's search found, working at `at` now, rated `band`."""
    person = Candidate(org_id=job.org_id, name_variants=[name or f"Testperson {uuid.uuid4().hex[:6]}"])
    session.add(person)
    session.flush()
    if at is not None:
        step(session, job, person, at)
    session.add_all([CandidateJob(org_id=job.org_id, candidate_id=person.id, job_id=job.id, triage_band=band),
                     SourcingHit(org_id=job.org_id, job_id=job.id, candidate_id=person.id, run_id=run.id, channel="exa_people",
                                 new_to_desk=True)])
    session.flush()
    return person


def test_where_someone_works_now_is_their_main_current_job(session, job):
    old, side, now, kept = (company(session, n) for n in ("Old Testco", "Board Testco", "Now Testco", "Kept Testco"))
    person = Candidate(org_id=job.org_id, name_variants=["Una Testperson"])
    session.add(person)
    session.flush()
    step(session, job, person, old, start=date(2015, 1, 1), end=date(2019, 1, 1))
    step(session, job, person, now, start=date(2019, 2, 1))
    step(session, job, person, side, title="Advisory Board Member", start=date(2024, 1, 1))
    assert autosource.main_employer(session, job.org_id, person.id) == str(now.id), "not the old job, not a board seat"
    companies.merge(session, kept.id, now.id, OWNER, job.org_id)
    assert autosource.main_employer(session, job.org_id, person.id) == str(kept.id), "a merged company is its kept record"


def test_at_most_five_strong_from_one_company_are_suggested_the_rest_held_back(session, job, run):
    big, other = company(session, "Big Testco"), company(session, "Other Testco")
    at_big = [found(session, job, run, big) for _ in range(8)]
    elsewhere = [found(session, job, run, other), found(session, job, run, None)]
    possible = [found(session, job, run, big, band="review_later") for _ in range(2)]
    pairs = {x.candidate_id: x for x in session.query(CandidateJob).filter(CandidateJob.job_id == job.id)}
    order = [pairs[p.id] for p in at_big + elsewhere + possible]
    kept, held = autosource.vary(session, job.org_id, order, 5)
    assert [x.candidate_id for x in kept] == [p.id for p in at_big[:5] + elsewhere + possible], \
        "the list's own order: the first five there, everyone else, and possible matches never held back"
    assert {k: [x.candidate_id for x in v] for k, v in held.items()} == {str(big.id): [p.id for p in at_big[5:]]}
    assert autosource.vary(session, job.org_id, order, 0) == (order, {}), "0 turns it off"


def test_the_target_counts_five_per_company_so_the_search_goes_on(session, job, run):
    big, other = company(session, "Big Testco"), company(session, "Other Testco")
    for _ in range(8):
        found(session, job, run, big)
    found(session, job, run, other)
    found(session, job, run, None)
    assert autosource.strong_waiting(session, job.id) == 7, "five from Big Testco, one elsewhere, one with no known company"
    assert autosource.strong_waiting(session, job.id, every=True) == 10
    autosource.update_plan(session, job.org_id, job.id, OWNER, rules={"per_company": 0})
    assert autosource.strong_waiting(session, job.id) == 10, "off: everyone counts"


def test_a_company_that_gave_its_share_is_searched_again_after_the_others(session, job, monkeypatch):
    found_now: dict = {}
    monkeypatch.setattr(strategy, "relevant_now", lambda session, job_id: dict(found_now))
    for name in ("Full Testco", "Giving Testco", "Quiet Testco", "Fresh Testco"):
        autosource.add_target(session, job.org_id, job.id, name, OWNER)
    p = autosource.update_plan(session, job.org_id, job.id, OWNER, role_variants=["CRM specialist", "CRM manager"],
                               rules={"adaptive": 1})
    for name, strong in (("Full Testco", 6), ("Giving Testco", 2), ("Quiet Testco", 0)):
        t = next(x for x in p.targets if x["name"] == name)
        q = SourcingQuery(org_id=job.org_id, job_id=job.id, key=f"k-{uuid.uuid4()}", channel="exa_people", text=f"CRM specialist at {name}",
                          target=name, tier=t["tier"], runs=1, results=10, new=5, known=0, relevant=strong, cost_usd=0.007,
                          last_run_at=datetime.now(timezone.utc), company_id=uuid.UUID(t["company_id"]))
        session.add(q)
        session.flush()
        found_now[q.id] = strong
    texts = [q["text"] for q in strategy.next_searches(session, job, p, set(), {})]
    assert texts == ["CRM manager at Giving Testco", "CRM specialist at Fresh Testco", "CRM manager at Quiet Testco",
                     "CRM manager at Full Testco"], "it still gets its next title, after every other company"


def test_the_sourcing_tab_shows_five_and_says_how_many_more_wait(client, session, job, run):
    big = company(session, "Big Testco")
    for i in range(7):
        found(session, job, run, big, name=f"Testperson {i}")
    page = client.get(f"/v1/jobs/{job.id}/sourcing").json()
    strong = [x for x in page["suggestions"] if x["hint"] == "looks strong"]
    assert len(strong) == 5 and page["strong_waiting"] == 5 and page["strong_waiting_all"] == 7
    [held] = page["held_back"]
    assert (held["name"], held["count"]) == ("Big Testco", 2) and len(held["people"]) == 2, "never lost: their cards are there"
    assert {x["candidate_id"] for x in held["people"]}.isdisjoint({x["candidate_id"] for x in strong})


def test_the_number_is_a_setting_of_the_role_and_changing_it_keeps_the_other_rules(client, session, job):
    autosource.update_plan(session, job.org_id, job.id, OWNER, rules={"adaptive": 0})
    r = client.patch(f"/v1/jobs/{job.id}/sourcing/plan", json={"rules": {"per_company": 3}})
    assert r.status_code == 200, r.text
    rules = r.json()["plan"]["rules"]
    assert rules["per_company"] == 3 and rules["adaptive"] == 0, "a rule changed is merged, never a reset of the others"
    assert client.patch(f"/v1/jobs/{job.id}/sourcing/plan", json={"rules": {"per_company": -1}}).status_code == 422
