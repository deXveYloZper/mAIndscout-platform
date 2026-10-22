"""The desk settles the easy questions itself (owner, 2026-10-22: "easy and silly questions should be caught and
settled and handled by the desk"). The pairs are the real ones that were waiting in the inbox that day."""

from datetime import date

import pytest
from sqlalchemy import select

from maindscout.api import companies, settle
from maindscout.db.models import Candidate, Claim, Company, Decision, DecisionItem

SITE = "they share a website, LinkedIn page or Exa id"


def co(name):
    return Company(name=name, normalized=name.lower())


@pytest.mark.parametrize("new, existing, why, action", [
    # one name, written differently
    ("ClearTax", "ClearTax", SITE, "same"),
    ("Waitrose & Partners", "Waitrose & Partners", SITE, "same"),
    ("Piquadro", "PIQUADRO S.p.A.", SITE, "same"),
    ("DeliveryHero", "Delivery Hero", None, "same"),
    ("Tradewings Tour", "Tradewings Tours", None, "same"),
    ("Slingshot Aerospace (UK) Ltd", "Slingshot Aerospace", None, "same"),
    ("Ecole Normale Supérieure de Paris", "Ecole normale supérieure", None, "same"),
    # a part, or a renamed form
    ("CERN Large Hadron Collider ATLAS experiment", "CERN", None, "same"),
    ("University of Baghdad - Computer Centre", "University of Baghdad", None, "same"),
    ("Active Agent AG", "Active Agent - verschmolzen mit der ADITION technologies AG", None, "same"),
    ("BAE Systems Digital Intelligence", "BAE Systems", SITE, "same"),
    # only a shared website: kept apart
    ("Natural England", "Department of Health and Social Care", SITE, "different"),
    ("UK Space Agency", "Department of Health and Social Care", SITE, "different"),
    ("UCL Policy Lab", "UCL Dept of Civil, Environmental & Geomatic Engineering", SITE, "different"),
    ("UBS", "Credit Suisse", SITE, "different"),
    # not an employer, or like another of its names only
    ("Cambridge University Ultimate Club", "University of Cambridge", None, "different"),
    ("Bocconi Students for Fashion Association", "Bocconi Students For Fashion", None, "different"),
    ("NERC Envision PhD Studentship", "NERC: Natural Environment Research Council", None, "different"),
    ("Toro Loco Events", "AM Language", None, "different"),
    ("Virginia Tech Plant Genetics Lab", "Washington and Lee University", None, "different"),
    # real questions, for a person
    ("KPMG", "KPMG Avocats", None, None),
    ("VEGA Group plc", "Vega Space Systems Engineering Ltd", None, None),
])
def test_the_desk_settles_what_a_rule_can_and_asks_the_rest(new, existing, why, action):
    verdict = settle.company_verdict(co(new), co(existing), why)
    assert (verdict[0] if verdict else None) == action


@pytest.mark.parametrize("new, existing, aliases, action", [
    ("TELESPAZIO VEGA", "Telespazio UK", ["telespazio uk", "telespazio vega uk"], "same"),  # its former name
    ("Toro Loco Events", "AM Language", ["am language", "am language school"], "different"),
])
def test_a_companys_other_names_count(new, existing, aliases, action):
    verdict = settle.company_verdict(co(new), co(existing), None, aliases)
    assert (verdict[0] if verdict else None) == action


def test_a_profiles_loose_other_names_are_not_kept():
    assert companies.alias_fits("telespazio uk", "telespazio vega uk")
    assert companies.alias_fits("university of cambridge", "the university of cambridge")
    for name, loose in (("am language", "toro"), ("washington and lee university", "virginia"),
                        ("corpus christi college university of oxford", "university of oxford"),
                        ("university of cambridge", "masters")):
        assert not companies.alias_fits(name, loose)


def test_a_settled_same_company_is_merged_under_the_parents_name_and_kept_on_record(session, org):
    ucl, _ = companies.resolve(session, "UCL Testcollege", "test")
    dept, _ = companies.resolve(session, "UCL Testcollege Department of Space", "test")
    card = Decision(org_id=org.id, type="company_same", priority=30, subject_type="company", subject_id=ucl.id,
                    context={"question": "same company?", "new": {"id": str(ucl.id), "name": ucl.name},
                             "existing": {"id": str(dept.id), "name": dept.name}, "candidate_id": None})
    session.add(card)
    session.flush()
    assert settle.settle(session, card) is True
    assert dept.merged_into_id == ucl.id, "the department folds into the college, not the other way"
    assert card.resolution["by"] == "desk" and card.resolution["action"] == "same" and card.resolution["reason"]


def _step(session, org, person, title, start, end):
    c = Claim(org_id=org.id, subject_type="candidate", subject_id=person.id, claim_type="CareerStepClaim",
              payload={"company": {"raw_name": "Testsat"}, "title_raw": title}, status="proposed",
              valid_from=start, valid_to=end, natural_key=f"{person.id}|{title}|{start}", flags={})
    session.add(c)
    session.flush()
    return c


def _card(session, org, person, a, b):
    d = Decision(org_id=org.id, type="duplicate_stint", priority=50, subject_type="candidate", subject_id=person.id,
                 context={"company": "Testsat", "question": "same stint, or two?"})
    session.add(d)
    session.flush()
    session.add_all([DecisionItem(org_id=org.id, decision_id=d.id, claim_id=c.id, role="option") for c in (a, b)])
    session.flush()
    return d


def test_one_job_written_twice_is_joined_over_its_whole_span_and_a_gap_is_asked(session, org):
    person = Candidate(org_id=org.id, name_variants=["Una Testperson"])
    session.add(person)
    session.flush()
    a = _step(session, org, person, "Mission Analyst", date(2022, 9, 1), date(2023, 5, 1))
    b = _step(session, org, person, "Mission Analyst", date(2023, 5, 1), date(2024, 7, 1))
    assert settle.settle(session, _card(session, org, person, a, b)) is True
    kept, gone = sorted((a, b), key=lambda c: c.status != "proposed")
    assert gone.status == "superseded" and (kept.valid_from, kept.valid_to) == (date(2022, 9, 1), date(2024, 7, 1))
    c = _step(session, org, person, "Engineer", date(2015, 1, 1), date(2016, 1, 1))
    d = _step(session, org, person, "Engineer", date(2018, 1, 1), date(2019, 1, 1))
    assert settle.settle(session, _card(session, org, person, c, d)) is False, "two years apart: maybe two jobs"
    e = _step(session, org, person, "Analyst", date(2019, 1, 1), date(2020, 1, 1))
    f = _step(session, org, person, "Senior Analyst", date(2020, 1, 1), None)
    assert settle.settle(session, _card(session, org, person, e, f)) is False, "another title: a person decides"
