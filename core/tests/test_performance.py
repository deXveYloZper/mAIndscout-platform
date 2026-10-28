"""Performance work (2026-10-05): batched code must give the same answers as the one-at-a-time code it replaced, and a
big job re-matches in the background. Timings themselves are measured by `python -m maindscout perf-check`."""

import uuid
from contextlib import contextmanager

from sqlalchemy import event, select, text, update

from maindscout.api import autosource, company_lines, companies, memo, outreach, process, queries, tasks
from maindscout.db.models import CandidateJob, Claim, Company, Job, Task
from tests.test_api import client, drop_cv, fake, make_job  # noqa: F401 (fixtures)
from tests.test_autosource import blobs, job, person_named  # noqa: F401 (fixtures)
from tests.test_company_lines import Reader, co, ln
from tests.test_phase1c import found
from tests.test_process import CV_LINES


def org_of(client):
    return uuid.UUID(client.headers["X-Org-Id"])


def test_a_big_job_re_matches_in_the_background_and_says_so(client, session, monkeypatch):
    job = make_job(client)
    drop_cv(client, job)
    monkeypatch.setattr(process, "INLINE_JOB_REMATCH", 0)  # every job counts as big
    r = client.post(f"/v1/jobs/{job}/requirements", json={"category": "domain", "strength": "strong_plus", "text_raw": "Fintech experience",
                                                       "domains": ["fintech"]})
    assert r.status_code == 201, r.text
    queued = session.scalars(select(Task).where(Task.kind == "rematch_job", Task.status == "queued")).all()
    assert len(queued) == 1 and client.get(f"/v1/jobs/{job}").json()["rematching"] is True
    client.post(f"/v1/jobs/{job}/requirements", json={"category": "domain", "strength": "nice", "text_raw": "Payments", "domains": ["payments"]})
    assert len(session.scalars(select(Task).where(Task.kind == "rematch_job", Task.status == "queued")).all()) == 1, "deduplicated"
    tasks.execute(session, queued[0])
    queued[0].status = "done"
    session.flush()
    assert client.get(f"/v1/jobs/{job}").json()["rematching"] is False


def test_a_small_job_still_re_matches_at_once(client, session):
    job = make_job(client)
    drop_cv(client, job)
    client.post(f"/v1/jobs/{job}/requirements", json={"category": "domain", "strength": "strong_plus", "text_raw": "Fintech experience",
                                                   "domains": ["fintech"]})
    assert not session.scalars(select(Task).where(Task.kind == "rematch_job")).all()


def test_matching_without_snippets_gives_the_same_gap_table(client, session):
    job_id = make_job(client)
    cid = uuid.UUID(drop_cv(client, job_id)["subject_id"])
    job = session.get(Job, uuid.UUID(job_id))
    full = queries._gap_rows_many(session, org_of(client), job, [cid])[cid]
    lean = queries._gap_rows_many(session, org_of(client), job, [cid], with_snippets=False)[cid]
    strip = lambda rows: [(r.requirement_id, r.status, r.official, sorted(f.id for f in r.facts)) for r in rows]  # noqa: E731
    assert strip(full) == strip(lean)
    inputs = process.pair_inputs(session, org_of(client), cid, job)
    pre = queries._gap_rows_many(session, org_of(client), job, [cid], with_snippets=False, preloaded=(inputs[0], {cid: inputs[1]}))[cid]
    assert strip(pre) == strip(full)


def test_the_jobs_list_counts_the_same_as_each_jobs_inbox(client, session):
    job_a, job_b = make_job(client), make_job(client)
    drop_cv(client, job_a)
    drop_cv(client, job_b, CV_LINES[:1] + ["omar@example.com"] + CV_LINES[2:], name="b.pdf")
    for row in client.get("/v1/jobs").json():
        expected = len(queries.inbox(session, org_of(client), uuid.UUID(row["id"]), "priority"))
        assert row["to_review"] == expected


def test_re_matching_a_pair_twice_records_nothing_new(client, session):
    job = make_job(client)
    drop_cv(client, job)
    pair = session.scalars(select(CandidateJob)).first()
    assert process.retriage_pair(session, pair, {"act": "again"}) is None, "a stable reason: no spurious band event"


# --- the Sourcing tab on a large role (2026-10-28: Ferrari's CRM role, 1,684 people and 166 companies, 3 s warm) -------


@contextmanager
def statements(session):
    """How many statements the session sends to the database inside the block."""
    sent = [0]
    conn = session.connection()

    def count(*_):
        sent[0] += 1

    event.listen(conn, "before_cursor_execute", count)
    try:
        yield sent
    finally:
        event.remove(conn, "before_cursor_execute", count)


def lined(session, org_id, name, *markets, at_once=False):
    """A company with lines of business, its main line first, each at its own time as when read on different days;
    `at_once`: read together, sharing one time."""
    company = co(session, name, offering=", ".join(markets), about=f"{name} sells {' and '.join(markets)}")
    lines = [ln(m, "luxury / fashion / beauty", m, "luxury", "consumers", m) for m in markets]
    company_lines.classify(session, org_id, [company], Reader({name: lines}))
    if not at_once:
        for hours, market in enumerate(reversed(markets), start=1):
            session.execute(update(Claim).where(Claim.subject_id == company.id, Claim.payload["market"].astext == market)
                            .values(created_at=text(f"now() - interval '{hours} hours'")))
    return company


def test_the_sourcing_tab_reads_its_companies_together_and_as_one_company_reads_alone(session, job):
    """Every target's lines and merged records in a few queries for all of them, not two per company (166 companies took a
    second), and the same lines in the same order as one company read alone: main line first. A company whose lines were
    read at once shares one time for them; it is read alone, as before."""
    one = lined(session, job.org_id, "Testlinea One", "apparel", "leather goods")
    old = lined(session, job.org_id, "Testlinea Old", "eyewear")  # an older record of the same company
    session.execute(update(Claim).where(Claim.subject_id == old.id).values(created_at=text("now() - interval '1 day'")))
    companies.merge(session, one.id, old.id)
    lined(session, job.org_id, "Testlinea Six", "footwear", "handbags", at_once=True)
    names = ["Testlinea One", "Testlinea Six", "Testlinea Two", "Testlinea Three", "Testlinea Four", "Testlinea Five"]
    for name in names[2:]:
        lined(session, job.org_id, name, "fragrance", "cosmetics")
    for name in names[:3]:
        autosource.add_target(session, job.org_id, job.id, name, "owner@desk.test")
    autosource.page(session, job.org_id, job.id)
    with statements(session) as three:
        autosource.page(session, job.org_id, job.id)
    for name in names[3:]:
        autosource.add_target(session, job.org_id, job.id, name, "owner@desk.test")
    with statements(session) as six:
        page = autosource.page(session, job.org_id, job.id)
    assert six[0] == three[0], "no query per company"
    for t in page["plan"]["targets"]:
        alone = company_lines.of_company(session, uuid.UUID(t["company_id"]))[:2]
        if t["name"] == "Testlinea Six":  # which of two lines read at once comes first is the database's, either way
            assert sorted(line["market"] for line in t["lines"]) == sorted(line["market"] for line in alone)
        else:
            assert t["lines"] == alone, t["name"]
    markets = {t["name"]: [line["market"] for line in t["lines"]] for t in page["plan"]["targets"]}
    assert markets["Testlinea Two"] == ["fragrance", "cosmetics"], "the main line first"
    assert markets["Testlinea One"] == ["eyewear", "apparel"], "through the record merged into it, oldest first"


def test_the_sourcing_tab_reads_the_facts_of_the_people_its_lists_can_show_only(session, job, blobs, monkeypatch):
    """A suggestion rated neither strong nor possible, and never decided on, is left out before its places and career steps
    are read (Ferrari's CRM role shows 61 of its 1,684 people); once the owner puts them on a list, they are read."""
    ada = found(session, job, blobs)  # rated strong; Ben is rated do not submit
    ben = person_named(session, "Ben Testperson")
    read = []
    prefetch = memo.prefetch_places_and_steps
    monkeypatch.setattr(memo, "prefetch_places_and_steps", lambda s, org_id, ids: (read.append(set(ids)), prefetch(s, org_id, ids)))
    page = autosource.page(session, job.org_id, job.id)
    assert [s["candidate_id"] for s in page["suggestions"]] == [str(ada)]
    assert ada in read[-1] and ben not in read[-1]
    outreach.decide(session, job.org_id, job.id, ben, "later", "owner@desk.test")
    page = autosource.page(session, job.org_id, job.id)
    assert [x["candidate_id"] for x in page["lists"]["later"]] == [str(ben)] and ben in read[-1]


def test_where_the_people_shown_work_is_read_in_one_query(session, job, blobs):
    """The country check and the card read each person's employer by id: after one query for all of them, that read asks
    the database nothing (91 queries, one per person, on the marketing role)."""
    ada = found(session, job, blobs)
    ben = person_named(session, "Ben Testperson")
    session.expire_all()
    with memo.reading(session):
        memo.prefetch_places_and_steps(session, job.org_id, [ada, ben])
        memo.prefetch_employers(session, job.org_id, [ada, ben])
        employers = autosource.current_employers(session, job.org_id, ada) | autosource.current_employers(session, job.org_id, ben)
        with statements(session) as sent:
            assert all(session.get(Company, uuid.UUID(c)) is not None for c in employers)
    assert employers and sent[0] == 0
