"""The search that learns from its own results (2026-10-28, plan rule `adaptive`, on by default; measured first on
three roles and over the desk's 207 recorded searches): titles ordered by what they found and retired when barren;
deep where a company gives; and the qualities an ad lists never read as requirements. Fakes only: nothing is spent."""

import uuid
from datetime import datetime, timezone

import pytest

from maindscout.api import autosource, strategy
from maindscout.db.models import SourcingQuery
from maindscout.intelligence import extract
from tests.test_api import client, fake, make_job  # noqa: F401 (fixtures)
from tests.test_autosource import blobs, job  # noqa: F401

OWNER = "owner@desk.test"
TITLES = ["InSAR engineer", "SAR engineer", "radar engineer", "GIS engineer"]


@pytest.fixture
def live(monkeypatch):
    """What each search found, as rated now (`relevant_now` reads the priority pairs; here it is told directly)."""
    found: dict = {}
    monkeypatch.setattr(strategy, "relevant_now", lambda session, job_id: dict(found))
    return found


def plan_with(session, job, adaptive=True, titles=TITLES, companies=()):
    for name in companies:
        autosource.add_target(session, job.org_id, job.id, name, OWNER)
    return autosource.update_plan(session, job.org_id, job.id, OWNER, role_variants=titles, target=50,
                                  rules={"adaptive": 1 if adaptive else 0})


def target(p, name):
    return next(t for t in p.targets if t["name"] == name)


def searched(session, job, live, t, text, strong, results=10, new=5):
    """Record that a search ran at a company, and how many strong people it found."""
    q = SourcingQuery(org_id=job.org_id, job_id=job.id, key=f"k-{uuid.uuid4()}", channel="exa_people", text=text, target=t["name"],
                      tier=t["tier"], runs=1, results=results, new=new, known=0, relevant=strong, cost_usd=0.007,
                      last_run_at=datetime.now(timezone.utc), company_id=uuid.UUID(t["company_id"]))
    session.add(q)
    session.flush()
    live[q.id] = strong
    return q


def test_titles_are_ordered_by_what_they_found_and_a_barren_title_retires(session, job, live):
    p = plan_with(session, job, companies=[f"Title Testco {i}" for i in range(6)])
    ts = [target(p, f"Title Testco {i}") for i in range(6)]
    searched(session, job, live, ts[0], "InSAR engineer at Title Testco 0", 0)
    searched(session, job, live, ts[0], "SAR engineer at Title Testco 0", 2)
    searched(session, job, live, ts[1], "radar engineer at Title Testco 1", 1)
    searched(session, job, live, ts[2], "radar engineer at Title Testco 2", 0)
    for t in ts:
        searched(session, job, live, t, f"GIS engineer at {t['name']}", 0)
    assert strategy.title_yield(session, job.id, TITLES) == {"InSAR engineer": (1, 0), "SAR engineer": (1, 2),
                                                             "radar engineer": (2, 1), "GIS engineer": (6, 0)}
    assert strategy.ordered_variants(session, job, p) == ["InSAR engineer", "SAR engineer", "radar engineer"], \
        "the ad's title stays first; then by strong people per search; six barren searches retire a title"
    assert "GIS engineer" not in {q["text"].split(" at ")[0] for q in strategy.next_searches(session, job, p, set(), {})}
    p = autosource.update_plan(session, job.org_id, job.id, OWNER, rules={"adaptive": 0})
    assert strategy.ordered_variants(session, job, p) == TITLES, "off: the plan's own order, nothing retired"


def test_deep_where_it_gives_and_wide_elsewhere(session, job, live):
    p = plan_with(session, job, titles=["InSAR engineer", "SAR engineer"], companies=["Quiet Co", "Giving Co", "Silent Co", "Fresh Co"])
    searched(session, job, live, target(p, "Quiet Co"), "InSAR engineer at Quiet Co", 0)
    searched(session, job, live, target(p, "Giving Co"), "InSAR engineer at Giving Co", 3)
    searched(session, job, live, target(p, "Silent Co"), "InSAR engineer at Silent Co", 0)
    texts = [q["text"] for q in strategy.next_searches(session, job, p, set(), {})]
    assert texts[0] == "SAR engineer at Giving Co", "the company that gave gets its next title first"
    assert texts[1] == "InSAR engineer at Fresh Co", "then the company never searched gets its first"
    assert set(texts[2:]) == {"SAR engineer at Quiet Co", "SAR engineer at Silent Co"} and len(texts) == 4, "one search per company per run"
    p = autosource.update_plan(session, job.org_id, job.id, OWNER, rules={"adaptive": 0})
    assert [q["text"] for q in strategy.next_searches(session, job, p, set(), {})] == ["InSAR engineer at Fresh Co"], \
        "off: wide first, as before"


def test_a_giving_company_gets_its_peer_search_sooner(session, job, live, blobs):
    p = plan_with(session, job, titles=["InSAR engineer"], companies=["Giving Co"])
    t = target(p, "Giving Co")
    searched(session, job, live, t, "InSAR engineer at Giving Co", 2)
    assert strategy.company_state(session, job.id, p)[t["company_id"]]["relevant"] == 2
    from tests.test_autosource import FakeExa

    report = {}
    strategy.snowball(session, job.org_id, job, FakeExa(companies=[]), report)
    assert next(x for x in autosource.current_plan(session, job.id).targets if x["name"] == "Giving Co").get("similar_done"), \
        "two strong people are enough for its peer search (three before)"


def test_the_qualities_an_ad_lists_are_never_requirements():
    run = extract._Run("the ad", uuid.uuid4(), [])
    lines = ["Passion for innovation and continuous improvement", "Commitment to the company's core values of excellence and integrity",
             "Strong results orientation and attention to detail", "Able to operate under pressure",
             "Excellent interpersonal and communication skills", "Strong hands-on and problem-solving approach",
             "Salesforce knowledge", "Availability to travel extensively"]
    staged = [extract.StagedClaim(f"r{i}", "JobRequirementClaim", {"category": "skill" if "Salesforce" in text or "pressure" in text
                                                                    or "interpersonal" in text or "hands-on" in text else "other",
                                                                    "strength": "must", "text_raw": text, "normalized_token":
                                                                    "salesforce" if "Salesforce" in text else None},
                                  {"snippet": text}) for i, text in enumerate(lines)]
    kept = [c.payload["text_raw"] for c in extract.drop_traits(staged, run)]
    assert kept == ["Salesforce knowledge", "Availability to travel extensively"], "a named skill and a real ask stay"
    assert len(run.results) == 6 and all(r.detail.startswith("personality") for r in run.results)
