"""Step E of understanding the hire (owner, 2026-10-20): the suggestion card in a few words, "Confirm all" on the
hiring profile, and answering the brief's questions. Synthetic data; nothing spent."""

import pytest
from sqlalchemy import select

from maindscout.api import hiring, review
from maindscout.api import role_brief as briefs
from maindscout.db.models import Claim, JobIntake
from maindscout.domain import cards, geo
from maindscout.intelligence.llm import FakeClient, LLMResult
from tests.test_api import client, fake, make_job  # noqa: F401 (fixtures)
from tests.test_autosource import job  # noqa: F401
from tests.test_hiring import item
from tests.test_role_brief import READING, facet


def row(strength, verdict, detail, kind="domain", requirement="a requirement"):
    return {"requirement": requirement, "kind": kind, "strength": strength, "verdict": verdict, "detail": detail}


# The detail lines matching writes today (domain/matching.py), as stored on real pairs.
LUXURY = "4.7 years in luxury / fashion / beauty, travel / hospitality (luxury companies only)"
LEATHER = "4.7 years at companies making leather goods, leather, bags (Prada Group)"
SMALL = "4.2 years at companies of up to 200 people (Green Planner)"
NO_SMALL = "no time at companies of up to 200 people in this kind of work (as far as research shows)"


@pytest.mark.parametrize("detail,words", [
    (LUXURY, "4.7 years in luxury"),
    (LEATHER, "4.7 years at leather goods companies (Prada Group)"),
    ("1.5 years at companies making bags", "1.5 years at bags companies"),
    (SMALL, SMALL),
    (NO_SMALL, "no time at companies of up to 200 people in this kind of work"),
    ("2.6 years in procurement, enterprise software", "2.6 years in procurement"),
    ("11.5 years of related work (marketing) against 7 asked; about 12 years across 9 jobs", "11.5 years of related work (marketing) against 7 asked"),
    ("no time in luxury, premium fashion (luxury companies only)", "no time in luxury"),
    ("worked at Tacto", "worked at Tacto"),
    ("not in their file, but Tacto uses React (its job advert, 2026-10) and they work there as Software Engineer: likely, "
     "confirm on the call", "React only likely: Tacto uses it, not in their file"),
])
def test_a_match_rows_detail_is_shortened_for_the_card_without_changing_what_it_says(detail, words):
    assert cards.short(detail) == words


def test_the_why_line_is_their_work_and_level_then_each_strong_plus_they_meet():
    rows = [row("must", "strong", "works in marketing; manager by title", kind="role"),
            row("strong_plus", "strong", LUXURY), row("strong_plus", "gap", "no time at companies making leather goods"),
            row("strong_plus", "strong", SMALL, kind="employer"), row("nice", "strong", "2 years in beauty")]
    work = {"label": "marketing", "years": 11.5, "level": "manager"}
    assert cards.why(rows, work) == ["11.5 years in marketing, manager", "4.7 years in luxury", SMALL]
    assert cards.why(rows, {"label": "unknown", "years": 3, "level": "senior"}) == ["4.7 years in luxury", SMALL]
    assert cards.why(rows, None, "unclear") == ["too little known to compare yet: no career profile"]


def test_a_possible_match_says_what_it_is_short_of_musts_first():
    rows = [row("strong_plus", "gap", NO_SMALL, kind="employer"), row("must", "partial", "works in public relations, related to marketing", kind="role"),
            row("must", "ask", "Italian is not mentioned; ask", kind="language"), row("strong_plus", "strong", LUXURY)]
    assert cards.short_of(rows) == ["works in public relations, related to marketing (partly)",
                                    "no time at companies of up to 200 people in this kind of work"]
    likely = row("must", "partial", "not in their file, but Tacto uses React (its job advert, 2026-10) and they work there "
                 "as Engineering Lead: likely, confirm on the call", kind="skill")
    assert cards.short_of([likely]) == ["React only likely: Tacto uses it, not in their file"], "likely says it: no (partly)"


def test_what_to_settle_is_a_reach_and_living_outside_the_roles_city_or_country():
    reach = "Head of Marketing now, above this role: ask whether they would go back to hands-on work"
    assert cards.settle(("evidence", "lives in Rome, Latium, Italy"), "Rome, Latium, Italy", ["Milan"]) == [
        "lives in Rome, Italy; the role is in Milan"]
    assert cards.settle(("evidence", "lives in Italy"), "Italy", ["Milan"]) == [
        "lives in Italy, city not known; the role is in Milan"], "Italy alone may be Milan: the city is to ask"
    assert cards.settle(("evidence", "lives in Milan, Lombardy, Italy"), "Milano, Lombardia, Italia", ["Milan"]) == [], "Milano is Milan"
    assert cards.settle(("evidence", "lives in Munich"), "Munich, Bavaria, Germany", []) == [], "no city asked: the country decides"
    assert cards.settle(("question", "the file does not say where they live; ask"), None, ["Milan"]) == ["where they live is not known"]
    assert cards.settle(("question", "lives in Vienna, Austria; ask about working from Germany"), "Vienna, Austria", []) == [
        "lives in Vienna, Austria; ask about working from Germany"]
    assert cards.settle(None, "Milan, Italy", ["Milan"], reach + ".") == [reach]


@pytest.mark.parametrize("place,cities,inside", [
    ("Milan, Lombardy, Italy", ["Milan"], True), ("Milano", ["Milan"], True), ("Greater Milan Metropolitan Area", ["Milan"], True),
    ("Rome, Latium, Italy", ["Milan"], False), ("München, Bayern", ["Munich"], True), ("Romano di Lombardia", ["Rome"], False),
    (None, ["Milan"], None), ("Milan", [], None),
])
def test_a_place_is_in_a_city_under_its_english_or_local_name(place, cities, inside):
    assert geo.in_city(place, cities) is inside


@pytest.mark.parametrize("place,only", [("Italy", True), ("United Kingdom", True), ("UK", True), ("Milan, Italy", False),
                                        ("Milan", False), ("", False), (None, False)])
def test_a_place_that_is_only_a_country_says_no_city(place, only):
    assert geo.only_country(place) is only


def test_the_card_places_a_person_in_town_and_country():
    assert cards.place_words("Rome, Latium, Italy") == "Rome, Italy"
    assert cards.place_words("Munich, Germany") == "Munich, Germany" and cards.place_words(None) is None


# --- Confirm all ---------------------------------------------------------------------------------------------------


def test_confirm_all_approves_what_the_desk_read_and_rematches_the_role_once(client, session, job, monkeypatch):
    calls = []
    real = review.rematch_job
    monkeypatch.setattr(review, "rematch_job", lambda *a, **k: calls.append(a[2]) or real(*a, **k))
    proposed = [c for c in session.scalars(select(Claim).where(Claim.subject_id == job.id, Claim.claim_type == "JobRequirementClaim",
                                                               Claim.status == "proposed"))]
    assert len(proposed) >= 2, "the test ad gives several requirements to confirm"
    r = client.post(f"/v1/jobs/{job.id}/requirements/confirm", json={"ids": [str(c.id) for c in proposed]})
    assert r.status_code == 200, r.text
    assert r.json() == {"confirmed": len(proposed), "already": 0}
    session.expire_all()
    assert {session.get(Claim, c.id).status for c in proposed} == {"approved"}
    assert calls == [job.id], "everyone on the role re-matched once, not once per line"
    again = client.post(f"/v1/jobs/{job.id}/requirements/confirm", json={"ids": [str(proposed[0].id)]})
    assert again.json() == {"confirmed": 0, "already": 1}, "a line already decided is left as it is"
    other = session.scalar(select(Claim).where(Claim.subject_id != job.id, Claim.claim_type == "IdentityClaim"))
    bad = client.post(f"/v1/jobs/{job.id}/requirements/confirm", json={"ids": [str(other.id) if other else "nonsense"]})
    assert bad.status_code == 404, "only this role's requirements"


# --- answering the brief's questions -------------------------------------------------------------------------------


class ByName:
    """A model that answers each reader with its own canned reply."""

    model = "fake"

    def __init__(self, replies):
        self.replies, self.calls = replies, []

    def complete_json(self, system, user, schema, name):
        self.calls.append((name, user))
        return LLMResult(self.replies[name], self.model, 1, 1, 0.0)


def test_an_answer_to_a_brief_question_is_read_like_notes_and_the_question_goes(session, job):
    briefs.read(session, job.org_id, job.id, FakeClient(READING))
    asked = {r["facet"]: r["question"] for r in briefs.view(session, job.id) if r.get("question")}
    assert asked["reports_to"] == "Who will they report to, and where?"
    answered = {"facets": [facet("reports_to", None, "Reports to the founder, in Tokyo.", "notes", "the founder, in Tokyo")]
                + [f for f in READING["facets"] if f["facet"] != "reports_to"], "questions": []}
    llm = ByName({"hiring_profile": {"items": []}, "role_brief": answered})
    out = briefs.answer(session, job.org_id, job.id, "reports_to", "  To the founder,   in Tokyo ", "owner@desk.test", llm)
    assert out["notes"]["intake_id"] and [n for n, _ in llm.calls] == ["hiring_profile", "role_brief"]
    note = session.scalar(select(JobIntake).where(JobIntake.job_id == job.id))
    assert note.text == 'The desk asked: "Who will they report to, and where?" The answer: To the founder, in Tokyo'
    rows = {r["facet"]: r for r in briefs.view(session, job.id)}
    assert rows["reports_to"]["basis"] == "notes" and rows["reports_to"]["quote"] == "the founder, in Tokyo"
    assert not any(r.get("question") for r in rows.values())
    with pytest.raises(LookupError):
        briefs.answer(session, job.org_id, job.id, "reports_to", "again", "owner@desk.test", llm)
    with pytest.raises(LookupError):
        briefs.answer(session, job.org_id, job.id, "team", "a small team", "owner@desk.test", llm)


def test_an_empty_answer_is_refused_before_anything_is_spent(session, job):
    briefs.read(session, job.org_id, job.id, FakeClient(READING))
    llm = ByName({})
    with pytest.raises(ValueError):
        briefs.answer(session, job.org_id, job.id, "market", "   ", "owner@desk.test", llm)
    assert llm.calls == []


def test_the_answer_endpoint_returns_the_new_brief(client, session, job, monkeypatch):
    briefs.read(session, job.org_id, job.id, FakeClient(READING))
    session.commit()
    monkeypatch.setattr(briefs, "answer", lambda s, o, j, f, t, a, c: {"notes": None, "written": 1})
    r = client.post(f"/v1/jobs/{job.id}/role-brief/answer", json={"facet": "market", "answer": "yes, the first"})
    assert r.status_code == 200 and r.json()["written"] == 1 and isinstance(r.json()["brief"], list)


# --- a requirement in your own words (owner, 2026-10-20) ----------------------------------------------------------


def test_a_line_rewritten_in_your_words_keeps_your_words_and_its_years_follow(session, job):
    old = hiring.add_requirement(session, job.org_id, job.id, {"category": "seniority", "strength": "must",
                                                               "text_raw": "Approximately 7 or more years of marketing", "min_years": 7}, "owner@desk.test")
    llm = ByName({})
    new = hiring.edit_requirement(session, job.org_id, old.id, "5 or more years of marketing", "strong_plus", "owner@desk.test", llm)
    assert (new.payload["text_raw"], new.payload["min_years"], new.payload["strength"]) == ("5 or more years of marketing", 5.0, "strong_plus")
    assert new.status == "approved" and new.payload["source"] == "recruiter" and old.status == "superseded"
    assert llm.calls == [], "years are read by code: nothing spent"


def test_a_rewritten_line_is_read_again_for_its_values(session, job):
    old = hiring.add_requirement(session, job.org_id, job.id, {"category": "employer", "strength": "strong_plus",
                                                               "text_raw": "ideally from small up to 200 people", "max_staff": 200}, "owner@desk.test")
    llm = ByName({"hiring_profile": {"items": [item("employer", "strong_plus", "From brands of up to 100 people",
                                                    "from brands of up to 100 people", max_staff=100)]}})
    new = hiring.edit_requirement(session, job.org_id, old.id, "from brands of up to 100 people", None, "owner@desk.test", llm)
    assert (new.payload["max_staff"], new.payload["strength"], new.payload["text_raw"]) == (100, "strong_plus", "from brands of up to 100 people")
    same = hiring.edit_requirement(session, job.org_id, new.id, "from brands of up to 100 people", "must", "owner@desk.test", llm)
    assert same.payload["strength"] == "must" and len(llm.calls) == 1, "the same words: only the strength changes, nothing read"
    with pytest.raises(ValueError):
        hiring.edit_requirement(session, job.org_id, same.id, " ", None, "owner@desk.test", llm)


def test_a_few_words_typed_on_the_profile_are_read_like_notes(session, job):
    llm = ByName({"hiring_profile": {"items": [item("skill", "must", "Japanese", "Japanese is a must", skill_token="japanese")]}})
    out = briefs.tell(session, job.org_id, job.id, "Japanese is a must", "owner@desk.test", llm)
    assert out["notes"]["written"] == 1 and [n for n, _ in llm.calls] == ["hiring_profile"], "no brief yet: none read"
    briefs.read(session, job.org_id, job.id, FakeClient(READING))
    llm = ByName({"hiring_profile": {"items": []}, "role_brief": READING})
    briefs.tell(session, job.org_id, job.id, "They report to the founder in Tokyo", "owner@desk.test", llm)
    assert [n for n, _ in llm.calls] == ["hiring_profile", "role_brief"], "with a brief, it is read again"
    with pytest.raises(ValueError):
        briefs.tell(session, job.org_id, job.id, "ok", "owner@desk.test", llm)
