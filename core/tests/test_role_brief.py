"""Step B of understanding the hire (owner, 2026-10-19): the role brief read between the lines, requirements grouped by
what the desk can use, and notes read without dropping an ask. Synthetic texts; nothing spent."""

import pytest
from sqlalchemy import select

from maindscout.api import hiring
from maindscout.api import role_brief as briefs
from maindscout.db.models import Claim, Evidence, JobIntake
from maindscout.domain import groups, matching
from maindscout.intelligence import hiring as reader
from maindscout.intelligence import role_brief as engine
from maindscout.intelligence.llm import FakeClient
from tests.test_api import client, fake, make_job  # noqa: F401 (fixtures)
from tests.test_autosource import job  # noqa: F401
from tests.test_hiring import OneItem, item
from tests.test_matching import req, run, verdict
from tests.test_profile_rubric import stint

AD = ("Marketing Manager Italy and Europe. We are looking for a commercially minded marketing leader who can build the "
      "brand's presence in Italy and Europe. Lead and develop the Digital Marketing and E-Commerce Specialist. "
      "Personally step into execution when required.")
NOTES = "not too senior like global and regional, not from big brands, ideally from small up to 200 people"
RESEARCH = "BONAVENTURA: premium full-grain leather bags.\nStaff: 62 people.\nWhere its people work: Japan 23%, Italy 13%."


def facet(name, value, words, basis, quote=None):
    return {"facet": name, "value": value, "words": words, "basis": basis, "quote": quote}


READING = {"facets": [
    facet("situation", None, "A 62-person leather-goods brand, its largest team in Japan, building Italy and Europe.", "research", "Staff: 62 people."),
    facet("team", "small_team", "Leads one specialist and works with agencies.", "ad", "Lead and develop the Digital Marketing and E-Commerce Specialist"),
    facet("hands_on", "mixed", "Leads and steps into the work.", "notes", "steps into the work every day"),  # not in the notes
    facet("market", "entering", "Building its presence in Italy and Europe.", "reading"),
    facet("level", "manager", "A hands-on manager, not a head of a large team.", "reading"),
    facet("reports_to", None, "Probably the founder, in Asia.", "reading"),
], "questions": [
    {"facet": "market", "question": "Is this the first marketing hire in Europe?", "why": "decides how hands-on"},
    {"facet": "situation", "question": "Where is the company based?", "why": "context"},
    {"facet": "team", "question": "Will they lead a team?", "why": "the ad already says"},
    {"facet": "level", "question": "Would a head of marketing at a 30-person brand fit?", "why": "sets the level limit"},
    {"facet": "reports_to", "question": "Who will they report to, and where?", "why": "a hire far from the boss works alone"},
]}


def test_a_brief_line_keeps_its_quote_only_where_it_is_written():
    b = engine.read(AD, NOTES, RESEARCH, FakeClient(READING))
    by = {f.facet: f for f in b.facets}
    assert (by["situation"].basis, by["situation"].quote) == ("research", "Staff: 62 people.")
    assert by["team"].basis == "ad" and by["team"].start is not None
    assert (by["hands_on"].basis, by["hands_on"].quote) == ("reading", None), "a quote not in the notes is our reading"
    assert [f.facet for f in b.facets] == ["situation", "team", "hands_on", "market", "reports_to", "level"]


def test_only_a_reading_that_changes_whom_to_look_for_is_asked():
    b = engine.read(AD, NOTES, RESEARCH, FakeClient(READING))
    assert [(f.facet, f.question) for f in b.questions()] == [
        ("market", "Is this the first marketing hire in Europe?"), ("reports_to", "Who will they report to, and where?"),
        ("level", "Would a head of marketing at a 30-person brand fit?")]
    reasons = {r["facet"]: r["reason"] for r in b.rejected}
    assert "only a reading" in reasons["situation"] and "only a reading" in reasons["team"]


def test_personality_and_unknown_values_are_never_part_of_a_brief():
    bad = {"facets": [facet("core_work", None, "A team player with a great attitude.", "reading"),
                      facet("team", "a big one", "Leads twenty people.", "reading")], "questions": []}
    b = engine.read(AD, NOTES, RESEARCH, FakeClient(bad))
    assert b.facets == [] and len(b.rejected) == 2


def test_the_research_a_brief_quotes_is_written_by_code_from_stored_facts():
    text = engine.research_text("BONAVENTURA", {"offering": "premium full-grain leather bags", "employees": 62,
                                                "countries": [{"country": "Japan", "pct": 23}, {"country": "Italy", "pct": 13}],
                                                "hq": "Singapore"}, None)
    assert "Staff: 62 people." in text and "Japan 23%, Italy 13%" in text and "Headquarters: Singapore." in text


def test_the_brief_is_kept_with_evidence_and_a_new_reading_never_replaces_a_persons_line(session, job):
    intake = JobIntake(org_id=job.org_id, job_id=job.id, text=NOTES, created_by="owner@desk.test")
    session.add(intake)
    session.flush()
    reading = {"facets": [facet("market", "entering", "Building its presence in Italy and Europe.", "reading"),
                          facet("level", "manager", "Not above manager: no global or regional heads.", "notes",
                                "not too senior like global and regional"),
                          facet("team", "small_team", "Leads one specialist.", "reading")],
               "questions": [{"facet": "market", "question": "Is this the first marketing hire in Europe?", "why": "how hands-on"},
                             {"facet": "level", "question": "How senior?", "why": "the notes already say"}]}
    out = briefs.read(session, job.org_id, job.id, FakeClient(reading))
    assert out["lines"] == 3 and out["questions"] == 1
    rows = {r["facet"]: r for r in briefs.view(session, job.id)}
    assert rows["market"]["basis"] == "reading" and rows["market"]["question"] == "Is this the first marketing hire in Europe?"
    assert rows["level"]["quote"] == "not too senior like global and regional" and rows["level"]["question"] is None
    ev = {c.payload["facet"]: session.scalar(select(Evidence).where(Evidence.claim_id == c.id))
          for c in session.scalars(select(Claim).where(Claim.subject_id == job.id, Claim.claim_type == "RoleScopeClaim"))}
    assert ev["market"].evidence_type == "inference"
    assert ev["level"].evidence_type == "intake_note" and ev["level"].locator == {"intake_id": str(intake.id)}
    level = session.scalar(select(Claim).where(Claim.subject_id == job.id, Claim.claim_type == "RoleScopeClaim",
                                               Claim.payload["facet"].astext == "level"))
    level.status, level.approved_view = "approved", dict(level.payload)
    session.flush()
    again = {"facets": [facet("level", "head", "A head of marketing.", "reading"), facet("team", "works_alone", "Alone.", "reading")],
             "questions": []}
    out = briefs.read(session, job.org_id, job.id, FakeClient(again))
    rows = {r["facet"]: r for r in briefs.view(session, job.id)}
    assert rows["level"]["value"] == "manager", "a line a person approved stays"
    assert rows["team"]["value"] == "works_alone" and "market" not in rows, "the machine's old lines go"


@pytest.mark.parametrize("payload,group", [
    ({"category": "role", "strength": "must", "role_family": "marketing"}, "search"),
    ({"category": "employer", "strength": "strong_plus", "max_staff": 200}, "search"),
    ({"category": "skill", "strength": "must", "text_raw": "influencer marketing"}, "search"),
    ({"category": "skill", "strength": "must", "text_raw": "Strong commercial judgment and the ability to connect awareness, traffic and conversion"}, "conversation"),
    ({"category": "other", "strength": "must", "text_raw": "salary will peak around €50,000"}, "conversation"),
    ({"category": "location", "strength": "must", "mobility": {"facet": "residence", "countries": ["IT"]}}, "search"),
    ({"category": "location", "strength": "unknown", "text_raw": "Milan"}, "context"),
    ({"category": "location", "strength": "must", "mobility": {"facet": "visa_sponsorship", "offered": False}}, "conversation"),
    ({"category": "process", "strength": "unknown", "text_raw": "closes 1 November"}, "context"),
    ({"category": "language", "strength": "nice", "text_raw": "Japanese"}, "search"),
])
def test_requirements_fall_into_search_conversation_and_context(payload, group):
    assert groups.group(payload)[0] == group


def test_notes_keep_sizes_level_limits_and_every_ask():
    read = lambda it: reader.read(NOTES, OneItem(it), "intake").items  # noqa: E731
    big = read(item("employer", "anti", "Not from big brands", "not from big brands", min_staff=501))
    assert (big[0].kind, big[0].fields) == ("employer", {"min_staff": 501})
    small = read(item("employer", "strong_plus", "From small brands up to 200 people", "ideally from small up to 200 people",
                      employer_kinds=["startup"], max_staff=200))
    assert small[0].fields == {"max_staff": 200}, "the size says it in people"
    limit = read(item("role", "anti", "Not too senior", "not too senior like global and regional", role_family="marketing", level="head"))
    assert (limit[0].kind, limit[0].strength, limit[0].fields["level"]) == ("role", "anti", "head")
    vague = read(item("employer", "anti", "Not from big brands", "not from big brands"))
    assert vague[0].kind == "other", "an ask the lists cannot hold is kept for the conversation, never dropped"


def test_a_seniority_limit_is_its_own_requirement(job):
    assert hiring.key_for(job.id, {"category": "role", "strength": "anti"}).endswith("|role|role|anti")
    assert hiring.key_for(job.id, {"category": "role", "strength": "must"}).endswith("|role|role")


def test_a_seniority_limit_and_a_size_not_wanted_rate_nobody_until_step_c():
    people = [stint(1, "Prada Group", "Global Head of Influencer Marketing", "2019-01", None, family="marketing", level="head")]
    reqs = [req(1, "role", "must", "Marketing manager", role_family="marketing", level="manager"),
            req(2, "role", "anti", "Not too senior", role_family="marketing", level="head"),
            req(3, "employer", "anti", "Not from big brands", min_staff=501)]
    m, _ = run(reqs, people)
    assert {v.requirement_id for v in m.rows} == {"1"} and verdict(m, 1).verdict == "strong"
