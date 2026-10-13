"""The talent-release radar (docs/next/PLAN.md S1, S3): news that companies are releasing talent moves them up a role's
searches, and market-wide news adds companies to the plan, each signal with the sentence that says so and never a
person's name. Exa is a fake: synthetic companies and articles, nothing spent."""

import json
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from maindscout.api import autosource, costs, hiring, radar, sourcing_stats, strategy
from maindscout.db.models import Company, CompanySignal, CostEntry, SourcingPlan, SourcingQuery
from maindscout.intelligence import release
from tests.test_api import client, fake, make_job  # noqa: F401 (fixtures)
from tests.test_autosource import FakeExa, blobs, job  # noqa: F401 (fixtures)

RECENT = (date.today() - timedelta(days=20)).isoformat() + "T00:00:00.000Z"
OLD = (date.today() - timedelta(days=300)).isoformat() + "T00:00:00.000Z"


def article(slug, title, text, published=RECENT, companies=None):
    out = {"url": f"https://news.example/{slug}", "title": title, "text": text, "publishedDate": published}
    if companies is not None:
        out["summary"] = json.dumps({"companies": companies})
    return out


def test_the_reader_quotes_a_sentence_about_the_company_and_never_a_person():
    def kinds(text, name, title=""):
        return [(s.kind, s.quote) for s in release.read(title, text, [name])]

    assert kinds("Orbital Testworks will cut 120 jobs at its Munich site.", "Orbital Testworks") == [
        ("layoffs", "Orbital Testworks will cut 120 jobs")], "the quote runs from the company to the event"
    assert kinds("Orbital Testworks has been acquired by Big Holding.", "Orbital Testworks") == [
        ("acquisition", "Orbital Testworks has been acquired")], "never the buyer's name"
    assert kinds("Orbital Testworks was acquired by Jane Doe.", "Orbital Testworks") == [("acquisition", "Orbital Testworks was acquired")]
    assert kinds("Orbital Testworks acquires a smaller rival.", "Orbital Testworks") == [], "the buyer is not releasing anyone"
    assert kinds("Orbital Testworks said there would be no layoffs.", "Orbital Testworks") == [], "a denial is not a signal"
    assert kinds("There will be no layoffs at Orbital Testworks.", "Orbital Testworks") == []
    assert kinds("Jane Doe was laid off from Orbital Testworks in March.", "Orbital Testworks") == [], "one person losing a job"
    assert kinds("Orbital Testworks, whose founder Jane Doe started it, will cut 50 jobs.", "Orbital Testworks") == [], "never a name"
    assert kinds("Orbital Testworks will cut 50 jobs. © Jane Doe", "Orbital Testworks") == [("layoffs", "Orbital Testworks will cut 50 jobs")]
    assert kinds("Layoffs at Radar Testworks hit its engineering team.", "Radar Testworks") == [("layoffs", "Layoffs at Radar Testworks")]
    assert kinds("Der Hersteller Orbital Testworks aus Bremen meldet Insolvenz an.", "Orbital Testworks") == [
        ("insolvency", "Orbital Testworks aus Bremen meldet Insolvenz")], "German news too"
    assert kinds("Other news.", "Orbital Testworks", title="Orbital Testworks to close Toulouse office")[0][0] == "office_closure"
    assert kinds("Orbital Testworks bought Tiny Labs and, after a long review of its many teams, began restructuring.",
                 "Orbital Testworks") == [], "restructuring only when the company and the word are close"

    assert not release.looks_like_a_company("Jane Doe", "", "Jane Doe was laid off last week."), "a person never becomes a company"
    assert release.looks_like_a_company("Northvolt", "", "") and release.looks_like_a_company("Isar Aerospace", "", "")
    assert release.looks_like_a_company("Agile Robots", "", "The Munich startup Agile Robots will cut jobs.")


def test_news_about_a_target_company_moves_it_up_and_shows_on_the_map(session, job, blobs):
    autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", mode="weekly", role_variants=["InSAR engineer"])
    for name in ("Radar Testworks", "Orbital Testworks"):
        p = autosource.add_target(session, job.org_id, job.id, name, "owner@desk.test")
        autosource.set_target(session, job.org_id, job.id, p.targets[0]["company_id"], "owner@desk.test", pinned=False)
    ids = {t["name"]: t["company_id"] for t in autosource.current_plan(session, job.id).targets}
    before = strategy.next_searches(session, job, autosource.current_plan(session, job.id), set(), {})
    assert before[0]["target"] == "Orbital Testworks", "the last added comes first while nothing else differs"

    news = [article("radar-closes", "Radar Testworks to close its Toulouse office",
                    "Radar Testworks will close its Toulouse office by December. Orbital Testworks is hiring.")]
    fake_exa = FakeExa(people=[], news=news)
    row = autosource.run(session, blobs, job.org_id, job.id, "manual", fake_exa)
    asked = [c["query"] for c in fake_exa.calls if c["category"] == "news"]
    assert len(asked) == 2 and all("startPublishedDate" in c for c in fake_exa.calls if c["category"] == "news")
    assert row.report["radar"]["flagged"] == ["Radar Testworks"] and row.report["radar"]["added"] == []
    signal = session.scalar(select(CompanySignal))
    assert (signal.kind, str(signal.company_id), signal.published) == ("office_closure", ids["Radar Testworks"],
                                                                       date.fromisoformat(RECENT[:10]))
    assert "Orbital" not in signal.quote

    page = autosource.page(session, job.org_id, job.id)
    by_name = {t["name"]: t for t in page["plan"]["targets"]}
    assert by_name["Radar Testworks"]["release"]["label"] == "a site closing" and by_name["Orbital Testworks"]["release"] is None
    for q in session.scalars(select(SourcingQuery).where(SourcingQuery.job_id == job.id, SourcingQuery.channel == "exa_people")):
        q.last_run_at -= timedelta(days=100)  # past the 90-day wait for exhausted companies
    after = strategy.next_searches(session, job, autosource.current_plan(session, job.id), set(radar.live(session, job.org_id)), {})
    assert after[0]["target"] == "Radar Testworks"
    autosource.set_target(session, job.org_id, job.id, ids["Orbital Testworks"], "owner@desk.test", pinned=True)
    after = strategy.next_searches(session, job, autosource.current_plan(session, job.id), set(radar.live(session, job.org_id)), {})
    assert after[0]["target"] == "Orbital Testworks", "pinned still comes first"

    n = session.scalar(select(func.count()).select_from(CostEntry).where(CostEntry.purpose == "sourcing_exa_news"))
    assert n == 2 and costs.month_spent(session, job.org_id) == 0
    again = autosource.run(session, blobs, job.org_id, job.id, "manual", fake_exa)
    assert [c["query"] for c in fake_exa.calls if c["category"] == "news"] == asked, "no news search twice within 14 days"
    assert again.report["radar"]["queries"] == []
    radar_row = next(g for g in sourcing_stats.stats(session, job.org_id, job.id, "channel")["groups"] if g["key"] == "exa_news")
    assert radar_row["label"] == "talent-release radar (news)" and radar_row["spend_usd"] == pytest.approx(0.014)


def test_market_news_adds_a_company_releasing_talent_but_never_a_person_or_an_off_limits_one(session, job, blobs, monkeypatch):
    monkeypatch.setattr(hiring, "company_summary", lambda session, company: {"name": "Catalyst Geo", "domains": ["earth observation"]})
    autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", mode="weekly", countries=["DE"],
                           role_variants=["InSAR engineer"])
    news = [
        article("radar-cuts", "Radar Testworks to cut 120 jobs",
                "The startup Radar Testworks will cut 120 jobs at its Munich site.\nJane Doe lost her job, she wrote.",
                companies=["Radar Testworks", "Jane Doe"]),
        article("client-cuts", "Catalyst Geo cuts jobs", "Catalyst Geo will cut 30 jobs.", companies=["Catalyst Geo"]),
        article("old-cuts", "Old Testworks cuts jobs", "Old Testworks will cut 50 jobs.", published=OLD, companies=["Old Testworks"]),
        article("quiet", "Quiet Testworks grows", "Quiet Testworks is hiring in Berlin.", companies=["Quiet Testworks"]),
        article("solar", "Solar Testwerke (STW) meldet Insolvenz an", "STW files for insolvency in Leipzig.",
                companies=["Solar Testwerke (STW)", "Solar Testwerke GmbH", "STW"]),
    ]
    fake_exa = FakeExa(people=[], news=news)
    row = autosource.run(session, blobs, job.org_id, job.id, "manual", fake_exa)
    market = [c for c in fake_exa.calls if c["category"] == "news"]
    assert len(market) == 1 and market[0]["userLocation"] == "DE" and "summary" in market[0]["contents"]
    assert "earth observation" in market[0]["query"]
    assert row.report["radar"]["added"] == ["Radar Testworks", "Solar Testwerke"], "one company under three names is one target"

    plan = autosource.current_plan(session, job.id)
    assert plan.created_by == "talent-release radar"
    added = next(t for t in plan.targets if t["name"] == "Radar Testworks")
    assert added["tier"] == "release" and "cut 120 jobs" in added["why"][0] and "Jane" not in added["why"][0]
    made = {c.normalized for c in session.scalars(select(Company))}
    assert "jane doe" not in made, "a person's name never becomes a company"
    assert not made & {"quiet testworks", "old testworks"}, "no signal, no company record"
    assert "stw" not in made, "an acronym of a company met in the same sweep is that company"
    assert "catalyst geo" not in {t["name"].lower() for t in plan.targets}, "the hiring company, an active client, is never added"
    assert session.scalar(select(func.count()).select_from(SourcingPlan).where(SourcingPlan.job_id == job.id)) == 3

    assert strategy.group_of(next(t for t in plan.targets if t["name"] == "Radar Testworks")) == "C", "news finds wait in tier C"
    plan = autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", open_tiers=["A", "B", "C"])
    queries = strategy.next_searches(session, job, plan, set(radar.live(session, job.org_id)), {})
    assert queries[0]["target"] == "Radar Testworks" and queries[0]["tier"] == "release"


def test_the_radar_stays_inside_the_budget(session, job, blobs, monkeypatch):
    monkeypatch.setattr(hiring, "company_summary", lambda session, company: {"name": "Catalyst Geo", "domains": ["earth observation"]})
    autosource.update_plan(session, job.org_id, job.id, "owner@desk.test", mode="weekly", countries=["DE", "AT"],
                           role_variants=["InSAR engineer"], monthly_budget_usd=0.02, open_tiers=["A", "B", "market"])
    fake_exa = FakeExa(people=[], news=[], cost=0.007)
    row = autosource.run(session, blobs, job.org_id, job.id, "manual", fake_exa)
    assert row.status == "stopped" and row.stop_reason == "budget"
    assert costs.sourcing_spent(session, job.org_id, job.id) <= 0.02
