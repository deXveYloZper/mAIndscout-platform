"""The core-work reader (owner, 2026-10-27: "yes build the reader, test on Ferrari and Bonaventura"): a role's work
lines proposed by the desk and confirmed by a person; each strong or possible person's own words read against them,
every quote checked by code; it orders people within a band and never rates anyone."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select

from maindscout.api import autosource, erasure, work_lines, work_reading
from maindscout.db.models import Candidate, CandidateJob, Claim, Task
from maindscout.intelligence import work_lines as lines_engine
from maindscout.intelligence import work_reader as engine
from maindscout.intelligence.llm import FakeClient
from tests.test_api import client, fake, make_job  # noqa: F401 (fixtures)
from tests.test_autosource import ADA, BEN, FakeExa, blobs, go, job, person_named  # noqa: F401

LINES = {"lines": [{"line": "Run the nightly InSAR processing chain for the satellite fleet", "central": True},
                   {"line": "Train the field teams to read the deformation maps", "central": True},
                   {"line": "Report the results to customers every month", "central": False}],
         "not_lines": ["Design the radar hardware on the satellites", "Sell imagery subscriptions to new customers"]}
ADA_WORK = "Built the nightly InSAR processing chain that runs for 40 satellites."
BEN_WORK = "Designed the radar hardware boards on the satellites for six years."
FIRST_JOB = "Orbital Testworks is a company with 50 employees."
ADA_DESCRIBED = dict(ADA, text=ADA["text"].replace(FIRST_JOB, f"{ADA_WORK}\n\n{FIRST_JOB}", 1))
BEN_DESCRIBED = dict(BEN, text=BEN["text"].replace(FIRST_JOB, f"{BEN_WORK}\n\n{FIRST_JOB}", 1))
OWNER = "owner@desk.test"


def answer(work=(), not_work=()):
    return FakeClient({"lines": [{"number": n, "verdict": v, "quote": q} for n, v, q in work],
                       "not_lines": [{"number": n, "verdict": v, "quote": q} for n, v, q in not_work],
                       "summary": "Their work, in the model's words: never kept."})


def pair_of(session, job, cid) -> CandidateJob:
    return session.scalar(select(CandidateJob).where(CandidateJob.job_id == job.id, CandidateJob.candidate_id == cid))


def found(session, job, blobs, *people, band="review_later"):
    go(session, job, FakeExa(people=list(people)), blobs)
    ids = [person_named(session, p["title"]) for p in people]
    for cid in ids:
        pair_of(session, job, cid).triage_band = band
    session.flush()
    return ids


def run_readings(session, models):
    """What the task runner does: run each queued reading and keep its result."""
    for t in session.scalars(select(Task).where(Task.kind == work_reading.KIND, Task.status == "queued")):
        cid = uuid.UUID(t.payload["candidate_id"])
        t.result = work_reading.run(session, t.org_id, uuid.UUID(t.payload["job_id"]), cid, models[cid])
        t.status, t.finished_at = "done", datetime.now(timezone.utc)
    session.flush()


# --- the role's lines ---------------------------------------------------------------------------------------------------


def test_the_role_lines_leave_out_personality_short_and_repeated_lines():
    raw = {"lines": [{"line": "Run the nightly InSAR processing chain", "central": True},
                     {"line": "Be a team player with the right attitude", "central": False},
                     {"line": "Coding", "central": False},
                     {"line": "Run the nightly InSAR processing chain.", "central": True}],
           "not_lines": ["Design the radar hardware on the satellites"]}
    got = lines_engine.read("InSAR Specialist", "Catalyst", [], [], "The ad.", FakeClient(raw))
    assert [(x.kind, x.words, x.central) for x in got.lines] == [
        ("work", "Run the nightly InSAR processing chain", True), ("not", "Design the radar hardware on the satellites", None)]
    assert {r["reason"] for r in got.rejected} == {"personality, culture or fit is never a line of the work",
                                                   "too short to be one thing a person does", "said twice"}


def test_the_lines_wait_for_a_person_and_confirming_them_reads_the_role_s_people_and_re_rates_nobody(session, job, blobs):
    ada, ben = found(session, job, blobs, ADA_DESCRIBED, BEN_DESCRIBED)
    out = work_lines.read(session, job.org_id, job.id, FakeClient(LINES))
    assert out["written"] == 5
    lines = session.scalars(select(Claim).where(Claim.subject_id == job.id, Claim.claim_type == work_lines.CLAIM)).all()
    assert {c.status for c in lines} == {"proposed"}
    assert work_lines.version(session, job.id) is None, "nothing is used until a person confirms"
    assert not session.scalars(select(Task).where(Task.kind == work_reading.KIND)).all()
    before = {cid: (pair_of(session, job, cid).triage_band, pair_of(session, job, cid).match_tier) for cid in (ada, ben)}
    rematches = session.scalar(select(func.count()).select_from(Task).where(Task.kind == "rematch_job"))
    got = work_lines.confirm(session, job.org_id, job.id, None, OWNER)
    assert got == {"confirmed": 5, "queued": 2}
    assert {t.payload["candidate_id"] for t in session.scalars(select(Task).where(Task.kind == work_reading.KIND))} == {str(ada), str(ben)}
    assert {cid: (pair_of(session, job, cid).triage_band, pair_of(session, job, cid).match_tier) for cid in (ada, ben)} == before
    assert session.scalar(select(func.count()).select_from(Task).where(Task.kind == "rematch_job")) == rematches, \
        "confirming the work re-rates nobody"
    again = work_lines.read(session, job.org_id, job.id, FakeClient({"lines": [], "not_lines": []}))
    assert again["written"] == 0 and len(work_lines.confirmed(session, job.id)[0]) == 3, "a new reading never replaces confirmed lines"


# --- reading a person ---------------------------------------------------------------------------------------------------


def test_a_quote_counts_only_when_it_is_their_own_words_about_the_work():
    body, titles = engine.own_words(ADA_DESCRIBED["text"])
    assert "InSAR Processing Engineer" in titles, "the headline"
    assert any("InSAR Engineer" in t for t in titles), "a job's heading"
    assert any("insar" in t for t in titles), "the skills section is a list"
    assert engine.evidence(ADA_WORK, body, titles)
    assert not engine.evidence("InSAR Engineer", body, titles), "a job title is never evidence"
    assert not engine.evidence("InSAR Processing Engineer", body, titles), "nor the headline"
    assert not engine.evidence("insar • python", body, titles), "nor a skills list"
    assert not engine.evidence("Built the InSAR chain for the fleet", body, titles), "not their words"
    assert not engine.evidence("nightly InSAR processing", body, titles), "too short to say what they did"
    assert engine.evidence("InSAR Engineer … " + ADA_WORK, body, titles), "a stitched quote with real work in it"


def test_the_reading_keeps_only_the_quotes_code_finds_in_their_words_and_never_the_model_s_summary():
    body, titles = engine.own_words(ADA_DESCRIBED["text"])
    work = [x["line"] for x in LINES["lines"]]
    r = engine.read(work, LINES["not_lines"], body, titles,
                    answer(work=[(1, "shown", ADA_WORK), (2, "partly", "InSAR Engineer"), (3, "not_shown", ""), (9, "shown", ADA_WORK)],
                           not_work=[(1, "some", "designs radar hardware every single day")]))
    assert [(v.line, v.verdict) for v in r.work] == [(1, "shown")]
    assert r.not_work == [] and r.rejected == 2, "a title and words that are not theirs"
    assert not hasattr(r, "summary")


def test_people_whose_words_show_the_work_come_first_and_look_alikes_last():
    central = {"group": "shows", "work": [{"verdict": "shown", "central": True}], "not": []}
    partly = {"group": "shows", "work": [{"verdict": "partly", "central": False}], "not": []}
    nothing = {"group": "nothing", "work": [], "not": []}
    looks = {"group": "looks_like", "work": [{"verdict": "shown", "central": True}], "not": [{"verdict": "main"}]}
    ordered = sorted([looks, None, nothing, partly, central], key=engine.order_key)
    assert ordered[:2] == [central, partly] and ordered[-1] is looks, "unread and nothing in between, as they were"
    assert engine.group([{"verdict": "shown"}], [{"verdict": "some"}]) == "shows", "some look-alike work never demotes"
    assert engine.group([{"verdict": "shown"}], [{"verdict": "main"}]) == "looks_like"


def test_a_reading_quotes_their_words_orders_the_suggestions_and_goes_with_the_person(session, job, blobs):
    ben, ada = found(session, job, blobs, BEN_DESCRIBED, ADA_DESCRIBED)
    work_lines.read(session, job.org_id, job.id, FakeClient(LINES))
    work_lines.confirm(session, job.org_id, job.id, None, OWNER)
    run_readings(session, {ada: answer(work=[(1, "shown", ADA_WORK)]), ben: answer(not_work=[(1, "main", BEN_WORK)])})
    page = autosource.page(session, job.org_id, job.id)
    names = [s["name"] for s in page["suggestions"]]
    assert names.index("Ada Testperson") < names.index("Ben Testperson"), "the work first, the look-alike last"
    card = next(s for s in page["suggestions"] if s["name"] == "Ada Testperson")
    assert card["work"]["group"] == "shows" and card["work"]["source"] == "web_profile"
    assert card["work"]["work"] == [{"line": LINES["lines"][0]["line"], "central": True, "verdict": "shown", "quote": ADA_WORK}]
    assert next(s for s in page["suggestions"] if s["name"] == "Ben Testperson")["work"]["group"] == "looks_like"
    assert work_reading.progress(session, job.id, work_lines.version(session, job.id))["read"] == 2
    erasure.erase_candidate(session, blobs, job.org_id, ada, OWNER, "asked to be forgotten")
    assert not session.scalar(select(func.count()).select_from(Task).where(Task.kind == work_reading.KIND,
                                                                         Task.payload["candidate_id"].astext == str(ada)))


def test_changed_lines_make_a_reading_stale_until_read_again(session, job, blobs):
    (ada,) = found(session, job, blobs, ADA_DESCRIBED)
    work_lines.read(session, job.org_id, job.id, FakeClient(LINES))
    work_lines.confirm(session, job.org_id, job.id, None, OWNER)
    run_readings(session, {ada: answer(work=[(1, "shown", ADA_WORK)])})
    first = next(c for c in session.scalars(select(Claim).where(Claim.subject_id == job.id, Claim.claim_type == work_lines.CLAIM,
                                                                Claim.status == "approved"))
                 if c.payload["kind"] == "not")
    work_lines.edit(session, job.org_id, first.id, "Build ground stations for the satellite operators", None, OWNER)
    assert session.get(Claim, first.id).status == "superseded"
    stale = work_reading.summaries(session, job.id, [ada])[ada]
    assert stale["status"] == "stale" and stale["group"] is None, "read against earlier lines: it orders nobody"
    assert work_reading.read_again(session, job.org_id, job.id) == 1
    run_readings(session, {ada: answer(work=[(2, "partly", ADA_WORK)])})
    assert work_reading.summaries(session, job.id, [ada])[ada]["group"] == "shows"


def test_someone_who_said_stop_or_who_is_not_strong_or_possible_is_never_read(session, job, blobs):
    ada, ben = found(session, job, blobs, ADA_DESCRIBED, BEN_DESCRIBED)
    pair_of(session, job, ben).triage_band = "do_not_submit"
    session.get(Candidate, ada).do_not_contact_at = datetime.now(timezone.utc)
    session.flush()
    work_lines.read(session, job.org_id, job.id, FakeClient(LINES))
    assert work_lines.confirm(session, job.org_id, job.id, None, OWNER)["queued"] == 1, "Ben is out of the bands it reads"
    model = answer(work=[(1, "shown", ADA_WORK)])
    run_readings(session, {ada: model})
    assert work_reading.summaries(session, job.id, [ada])[ada]["status"] == "skipped" and not model.calls


def test_a_line_typed_by_a_person_is_confirmed_at_once_and_personality_is_refused(client, session, job):
    r = client.post(f"/v1/jobs/{job.id}/work-lines/add", json={"kind": "not", "words": "Run CRM email campaigns"})
    assert r.status_code == 200 and r.json()["kind"] == "not"
    assert work_lines.version(session, job.id) is None, "no work line yet: nobody is read"
    assert client.post(f"/v1/jobs/{job.id}/work-lines/add", json={"words": "A great team player"}).status_code == 422
    r = client.post(f"/v1/jobs/{job.id}/work-lines/add", json={"words": "Train users across the regional hubs", "central": True})
    assert r.status_code == 200 and work_lines.version(session, job.id)
    view = client.get(f"/v1/jobs/{job.id}").json()["work_lines"]
    assert [(x["kind"], x["status"]) for x in view["lines"]] == [("not", "approved"), ("work", "approved")]
