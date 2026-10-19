"""Company sizes in people, real jobs only, a kind of company counted in the role's own work, and "not from" a company
meaning its people now and its recent leavers (owner, 2026-10-19). Synthetic people; nothing spent."""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from maindscout.api import hiring
from maindscout.domain import matching
from maindscout.domain.profile import CompanyFacts, Stint, build, side_role, size_band, staff_words
from maindscout.evals.matching import owner_says
from tests.test_api import client, fake, make_job  # noqa: F401 (fixtures)
from tests.test_autosource import job  # noqa: F401
from tests.test_matching import req, run, verdict
from tests.test_profile_rubric import AS_OF, stint

ROLE = req(1, "role", "must", "Marketing manager", role_family="marketing", level="manager")
SMALL_BRAND = req(2, "employer", "strong_plus", "Experience at a small or mid-size brand (up to 500 people)", max_staff=500)
BIG = CompanyFacts(team_min=12213)
BRAND = CompanyFacts(team_min=103)
BAKERY = CompanyFacts(kind="product", team_min=4)
AGENCY = CompanyFacts(kind="agency", team_min=129)


def test_company_sizes_come_in_five_bands():
    assert [size_band(n) for n in (1, 50, 51, 250, 251, 500, 501, 5000, 5001, 98000)] == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]
    assert size_band(None) is None
    assert staff_words(None, 500) == "up to 500 people"
    assert staff_words(501, 5000) == "501-5,000 people"
    assert staff_words(5001, None) == "over 5,000 people"


@pytest.mark.parametrize("title", ["Board Member", "Advisory Board Member", "Membership Board", "Volunteer", "Mentor Marketing and Communication",
                                   "Non-Executive Director", "Board of Directors - Student Representative", "Trustee"])
def test_a_board_seat_volunteering_or_mentoring_is_not_a_job(title):
    assert side_role(title)


@pytest.mark.parametrize("title", ["Member of the Management Board", "CEO & Board Member", "Volunteer Coordinator", "Lecturer",
                                   "Adjunct Professor – Strategic Marketing", "Client Advisor", "Brand ambassador", "Head of Marketing",
                                   "Cybersecurity Advisor (Board-Level)"])
def test_jobs_that_sound_like_side_roles_stay_jobs(title):
    assert not side_role(title)


def test_a_side_role_never_counts_as_experience():
    board = stint(1, "The Robin Club", "Membership Board", "2019-01", None, family="marketing", employment="side",
                  facts=CompanyFacts(team_min=6))
    work = stint(2, "Prada Group", "Worldwide Media Director", "2015-01", None, family="marketing", level="director", facts=BIG)
    m, profile = run([ROLE, SMALL_BRAND], [board, work])
    assert verdict(m, 2).verdict == "gap"
    assert profile["dimensions"]["employer_mix"]["years"].get("startup") is None


def test_small_brand_experience_counts_only_the_roles_kind_of_work():
    baker = stint(1, "Tone - Bread Lab", "Baker", "2021-07", "2023-07", family="hospitality", facts=BAKERY)
    now = stint(2, "Prada Group", "Communication Manager", "2023-08", None, family="marketing", level="manager", facts=BIG)
    m, _ = run([ROLE, SMALL_BRAND], [baker, now])
    assert verdict(m, 2).verdict == "gap" and "in this kind of work" in verdict(m, 2).detail
    brand = stint(3, "Dondup", "Communication Manager", "2019-01", "2023-06", family="marketing", level="manager", facts=BRAND)
    m, _ = run([ROLE, SMALL_BRAND], [brand, now])
    assert verdict(m, 2).verdict == "strong" and verdict(m, 2).detail.startswith("4.4 years at companies of up to 500 people (Dondup)")


def test_a_size_counts_companies_like_a_client_not_agencies():
    agency = stint(1, "Digital Brand Architects", "Talent Manager", "2018-01", "2022-01", family="marketing", facts=AGENCY)
    now = stint(2, "Prada Group", "Marketing Manager", "2022-02", None, family="marketing", level="manager", facts=BIG)
    m, _ = run([ROLE, SMALL_BRAND], [agency, now])
    assert verdict(m, 2).verdict == "gap"
    from_agencies = req(3, "employer", "strong_plus", "A small agency", employer_kinds=["agency"], max_staff=500)
    m, _ = run([ROLE, from_agencies], [agency, now])
    assert verdict(m, 3).verdict == "strong"


def test_a_size_is_asked_when_no_employer_size_is_known():
    people = [stint(1, "Unknown Srl", "Marketing Specialist", "2014-01", "2018-01", family="marketing", level="mid"),
              stint(2, "Other Srl", "Marketing Manager", "2018-02", None, family="marketing", level="manager")]
    m, _ = run([ROLE, SMALL_BRAND], people)
    assert verdict(m, 2).verdict == "ask" and "not known yet" in verdict(m, 2).detail


def test_a_kind_of_company_counts_only_the_roles_kind_of_work_and_not_wanted_counts_every_job():
    startup = req(2, "employer", "strong_plus", "Start-up experience", employer_kinds=["startup"])
    baker = stint(1, "Tone - Bread Lab", "Baker", "2018-01", "2022-01", family="hospitality", facts=BAKERY)
    now = stint(2, "Prada Group", "Marketing Manager", "2022-02", None, family="marketing", level="manager", facts=BIG)
    m, _ = run([ROLE, startup], [baker, now])
    assert verdict(m, 2).verdict == "gap"
    m, _ = run([startup], [baker, now])  # no kind of work on the role: every job counts, as before
    assert verdict(m, 2).verdict == "strong"
    consult = CompanyFacts(kind="consultancy")
    anti = req(3, "employer", "anti", "No big consultancies", employer_kinds=["consultancy"])
    m, _ = run([ROLE, anti], [stint(3, "BigCo", "Consultant", "2017-01", None, family="business_consulting", facts=consult)])
    assert verdict(m, 3).verdict == "against"


def test_not_from_a_company_means_its_people_now_and_anyone_who_left_in_the_last_six_months():
    today = date.today()
    anti = req(1, "target_company", "anti", "cannot hire from Valentino", companies=[{"name": "Valentino", "company_id": "c-1"}])

    def at(end):
        s = Stint("1", "Valentino", "Marketing Manager", today - timedelta(days=4 * 365), end, "full_time", company_key="c-1",
                  family="marketing", level="manager")
        return [s, Stint("2", "Gucci", "Marketing Manager", end or today, None, "full_time", company_key="c-2", family="marketing")] if end else [s]

    assert matching._target(anti["payload"], at(None)) == ("against", "works at Valentino")
    assert matching._target(anti["payload"], at(today - timedelta(days=90)))[0] == "against"
    two_years = matching._target(anti["payload"], at(today - timedelta(days=730)))
    assert two_years[0] == "strong" and "more than 6 months ago" in two_years[1]
    assert matching._target({**anti["payload"], "recent_months": 0}, at(today - timedelta(days=90)))[0] == "strong"


def test_a_size_can_be_typed_on_the_hiring_profile(session, job):
    c = hiring.add_requirement(session, job.org_id, job.id, {"category": "employer", "strength": "strong_plus",
                                                             "text_raw": "A small or mid-size brand", "max_staff": 500}, "owner@desk.test")
    assert c.status == "approved" and c.payload["max_staff"] == 500
    assert hiring.key_for(job.id, c.payload).endswith("|employer||-500|want")
    with pytest.raises(ValueError):
        hiring.add_requirement(session, job.org_id, job.id, {"category": "employer", "strength": "nice", "text_raw": "x"}, "owner@desk.test")
    with pytest.raises(ValueError):
        hiring.add_requirement(session, job.org_id, job.id, {"category": "employer", "strength": "nice", "text_raw": "x",
                                                             "min_staff": 600, "max_staff": 500}, "owner@desk.test")


def test_the_match_eval_reads_the_owners_own_decisions():
    pair = lambda **kw: SimpleNamespace(**{"pair_state": "seen", "contact": None, "band_overridden_by": None,  # noqa: E731
                                           "triage_band": "priority", **kw})
    assert owner_says(pair(contact={"stage": "contacted"})) == ("yes", "contacted")
    assert owner_says(pair(pair_state="we_passed", contact={"passed_for": "level"})) == ("no", "level")
    assert owner_says(pair(band_overridden_by="owner", triage_band="review_later")) == ("later", None)
    assert owner_says(pair()) is None


def test_a_profile_still_builds_with_the_new_rules():
    p = build([stint(1, "Dondup", "Marketing Manager", "2019-01", None, family="marketing", level="manager", facts=BRAND)], [], AS_OF)
    assert p["dimensions"]["employer_mix"]["label"] == "scaleup"
