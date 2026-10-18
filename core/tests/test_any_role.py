"""Every kind of role, not only engineering (owner, 2026-10-18: "it is given a marketing role or a sales role, similar
rules should apply"). A marketing ad's skills are names a profile can show, a list of areas is met by any of them,
"strongly preferred" is a strong plus, personality is never a criterion, a profile's languages and its own job
descriptions are read, and a language a profile does not list is asked, never a gap. Synthetic people; nothing spent."""

import uuid

from sqlalchemy import select

from maindscout.api import autosource, discovery, hiring
from maindscout.db.models import Claim, Evidence, Document
from maindscout.domain import gaps, matching
from maindscout.intelligence import exa, extract, webprofile
from maindscout.intelligence.llm import FakeClient
from tests.test_api import client, fake, make_job  # noqa: F401 (fixtures)
from tests.test_autosource import ADA, FakeExa, blobs, go, job, person_named  # noqa: F401

AD = ("Marketing Manager Italy and Europe\n"
      "Demonstrated ability across several of the following areas: brand marketing, digital acquisition, CRM, PR, "
      "influencer marketing, events, partnerships and retail marketing.\n"
      "Experience in luxury, premium fashion, accessories, beauty, hospitality or another design-led consumer brand is "
      "strongly preferred.\n"
      "Native or fluent Italian and strong business English.\n"
      "Calm, constructive and decisive in a fast-moving, cross-functional environment.\n")
AREAS = ("Demonstrated ability across several of the following areas: brand marketing, digital acquisition, CRM, PR, "
         "influencer marketing, events, partnerships and retail marketing.")
LUXURY = ("Experience in luxury, premium fashion, accessories, beauty, hospitality or another design-led consumer brand is "
          "strongly preferred.")


def item(text, category, strength, quote, token=None, distinctive=False, language=None):
    return {"text": text, "category": category, "strength": strength, "token": token, "distinctive": distinctive,
            "min_years": None, "education_level": None, "language": language, "quote": quote}


def marketing_reading():
    areas = [item(t, "skill", "must", AREAS, token="crm" if t == "CRM" else None)
             for t in ("brand marketing", "digital acquisition", "CRM", "PR", "influencer marketing", "events", "partnerships",
                       "retail marketing")]
    return {"title": {"value": "Marketing Manager Italy and Europe", "quote": "Marketing Manager Italy and Europe"},
            "hiring_company": None,
            "requirements": areas + [
                item("Experience in luxury, premium fashion, accessories, beauty, hospitality or another design-led consumer brand",
                     "skill", "nice", LUXURY, distinctive=True),
                item("Native or fluent Italian", "language", "must", "Native or fluent Italian", language="Italian"),
                item("Calm, constructive and decisive in a fast-moving, cross-functional environment", "other", "must",
                     "Calm, constructive and decisive in a fast-moving, cross-functional environment.")],
            "mobility": {"residence": {"stated": False, "countries": [], "quote": None},
                         "visa_sponsorship": {"stated": False, "offered": None, "quote": None},
                         "relocation_assistance": {"stated": False, "offered": None, "quote": None}},
            "work_locations": [], "process_dates": []}


def test_a_marketing_ad_is_read_into_requirements_a_profile_can_show():
    out = extract.extract_jd(AD, uuid.uuid4(), FakeClient(marketing_reading()))
    by_cat = {}
    for r in out.requirements:
        by_cat.setdefault(r.payload["category"], []).append(r.payload)
    areas = [p for p in by_cat["skill"] if "/" in (p.get("normalized_token") or "")]
    assert len(areas) == 1, "'several of the following areas' is one ask, met by any of them"
    assert areas[0]["normalized_token"].split("/") == ["brand marketing", "digital acquisition", "crm", "pr", "influencer marketing",
                                                      "events", "partnerships", "retail marketing"]
    luxury = next(p for p in by_cat["skill"] if p["text_raw"].startswith("Experience in luxury"))
    assert luxury["strength"] == "strong_plus", "'strongly preferred' is a strong plus, not a nice to have"
    assert "other" not in by_cat, "personality is never a criterion"
    assert any("personality" in r.detail for r in out.span_results if r.result == "fail")
    assert by_cat["language"][0]["normalized_token"] == "italian"


def test_a_typed_skill_gets_its_name_so_a_profile_can_show_it(session, job):
    c = hiring.add_requirement(session, job.org_id, job.id, {"category": "skill", "strength": "must",
                                                             "text_raw": "Influencer marketing"}, "owner@desk.test")
    assert c.payload["normalized_token"] == "influencer marketing"
    c = hiring.add_requirement(session, job.org_id, job.id, {"category": "skill", "strength": "nice",
                                                             "text_raw": "Strong commercial judgment and a feel for numbers"},
                               "owner@desk.test")
    assert not c.payload.get("normalized_token"), "a quality stays a question for the call"


PROFILE = """# Giulia Testperson

Marketing Manager at Moda Testworks

Milan, Lombardy, Italy (IT)

## About

Marketing leader for premium brands.

## Experience

### Marketing Manager - [Moda Testworks](https://www.linkedin.com/company/moda-testworks) (Current)

Mar 2021 - Present (5 years) in Milan, Lombardy, Italy

- Led influencer marketing and PR for the Milan boutique.

Department: Marketing • Level: Manager

Moda Testworks is a Retail company. It runs events in 12 cities, has 200-300 employees (+5% YoY), founded in 2004.

## Languages

Italiano - Madrelingua

Inglese - Professional working proficiency
"""


def test_a_found_profile_shows_skills_and_languages_from_the_persons_own_lines():
    tokens = ["brand marketing/influencer marketing/pr/events", "italian", "english", "german"]
    got = {s["normalized"]: s["quote"] for s in webprofile.skills_in(webprofile.own_lines(PROFILE), tokens)}
    assert got["influencer marketing"].startswith("Led influencer marketing") and "pr" in got
    assert got["italian"] == "Italiano - Madrelingua" and got["english"].startswith("Inglese"), "language names in Italian too"
    assert "events" not in got, "Exa's blurb about the company is never the person's"
    assert "german" not in got


def test_a_language_a_profile_does_not_list_is_asked_never_a_gap():
    rows = [gaps.Row("it", "Native or fluent Italian", "language", "must", "missing", "Italian is not mentioned; ask"),
            gaps.Row("en", "strong business English", "language", "must", "missing", "English is not mentioned; ask")]
    reqs = [{"id": "it", "payload": {"category": "language", "strength": "must", "text_raw": "Native or fluent Italian"}},
            {"id": "en", "payload": {"category": "language", "strength": "must", "text_raw": "strong business English"}}]
    profile = {"reading": {"label": "clear"}, "dimensions": {}}
    m = matching.match(reqs, rows, profile, [], ("review_later", "no_distinctive_requirements"))
    assert [v.verdict for v in m.rows] == ["ask", "ask"]
    assert m.tier != "unlikely", "two unlisted languages never make a Milan marketing manager unlikely"


def test_stored_profiles_are_read_again_when_the_role_asks_for_a_new_skill(session, job, blobs):
    text = ADA["text"].replace("Jan 2022 - Present (2 years) in Munich, Bavaria, Germany\n",
                               "Jan 2022 - Present (2 years) in Munich, Bavaria, Germany\n\n- Built InSAR pipelines in Rust.\n", 1)
    go(session, job, FakeExa(people=[dict(ADA, text=text)]), blobs)
    ada = person_named(session, "Ada Testperson")
    skills = lambda: {c.payload["normalized_skill"] for c in session.scalars(select(Claim).where(  # noqa: E731
        Claim.subject_id == ada, Claim.claim_type == "SkillClaim", Claim.status.in_(("proposed", "approved"))))}
    assert "rust" not in skills(), "the role did not ask for Rust when she was found"
    hiring.add_requirement(session, job.org_id, job.id, {"category": "skill", "strength": "nice", "text_raw": "Rust"}, "owner@desk.test")
    assert "rust" in skills(), "read again from her stored page, for free, when the role asks"
    rust = session.scalar(select(Claim).where(Claim.subject_id == ada, Claim.payload["normalized_skill"].astext == "rust"))
    ev = session.scalar(select(Evidence).where(Evidence.claim_id == rust.id))
    assert ev.snippet == "Built InSAR pipelines in Rust." and ev.origin == "independent_web"
    assert session.get(Document, ev.document_id).doc_type == "web_profile"


def test_a_background_that_names_industries_is_an_industry():
    from maindscout.intelligence import hiring as reader

    raw = {"kind": "employer", "strength": "strong_plus", "text": "luxury, premium fashion or design-led consumer brand background",
           "quote": LUXURY, "role_family": None, "level": None, "min_years": None, "employer_kinds": [], "domains": [],
           "companies": [], "employment": None, "skill_token": None, "note": None, "countries": [], "cities": [], "relocation": None}
    out = reader.read(AD, FakeClient({"items": [raw]}), "ad")
    assert [(i.kind, i.fields["domains"]) for i in out.items] == [("domain", ["luxury / fashion / beauty", "travel / hospitality"])]
    assert out.rejected == [], "no longer lost as 'nothing usable from the lists'"


def test_a_quality_labelled_as_a_skill_is_still_never_a_criterion():
    data = marketing_reading()
    calm = data["requirements"][-1]
    data["requirements"][-1] = {**calm, "category": "skill"}
    out = extract.extract_jd(AD, uuid.uuid4(), FakeClient(data))
    assert not any(r.payload["text_raw"].startswith("Calm") for r in out.requirements)


def test_a_short_past_title_does_not_set_the_level():
    from datetime import date

    from maindscout.domain import profile

    S = profile.Stint
    stints = [S("1", "Alex Riviere", "PA and Brand Manager", date(2021, 6, 1), date(2021, 12, 1), family="marketing", level="manager"),
              S("2", "Gucci", "RTW Project Engagement Specialist", date(2022, 9, 1), date(2023, 9, 1), family="marketing", level="mid"),
              S("3", "Brioni", "Junior Marketing Specialist", date(2024, 6, 1), None, family="marketing", level="junior")]
    as_of = date(2026, 10, 18)
    level = profile.seniority(stints, profile.relevant_years(stints, as_of), as_of)
    assert level["label"] == "mid", "six months as a manager at a small firm does not make a junior specialist a manager"


def test_years_asked_for_a_kind_of_work_are_years_of_that_work():
    rows = [gaps.Row("y", "7 or more years of broad marketing experience", "seniority", "must", "evidence",
                     "about 8.2 years across 8 jobs; 7+ asked")]
    reqs = [{"id": "y", "payload": {"category": "seniority", "strength": "must", "min_years": 7,
                                    "text_raw": "7 or more years of broad marketing experience"}}]
    prof = {"reading": {"label": "clear"}, "dimensions": {"relevant_years": {"label": "marketing", "main_years": 5.3}}}
    m = matching.match(reqs, rows, prof, [], ("review_later", "no_distinctive_requirements"))
    assert m.rows[0].verdict == "partial" and "5.3 years of related work" in m.rows[0].detail
    assert m.tier == "possible"
