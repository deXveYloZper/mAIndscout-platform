"""Step D (owner, 2026-10-21): the client's competitors researched on the web, companies far bigger left out, one broad
search per small company, and "Search now" going on until the role has its strong people. Nothing spent."""

from types import SimpleNamespace

from sqlalchemy import select

from maindscout.api import companies, strategy, task_handlers
from maindscout.db.models import Company, SourcingPlan, Task
from maindscout.intelligence import competitors as engine
from tests.test_api import client, fake, make_job  # noqa: F401 (fixtures)
from tests.test_autosource import FakeExa, job  # noqa: F401

VISITED = ["https://www.leathertrade.example/brands", "https://bonaventura.example/about"]


class FakeResearch:
    model = "fake-search"

    def __init__(self, companies_):
        self.data, self.calls = {"companies": companies_}, []

    def search_json(self, system, user, schema, name):
        self.calls.append((name, user))
        return self.data, VISITED, {"model": self.model, "usd": 0.21, "sources": 9}


def rival(name, website=None, quote=None, url="https://www.leathertrade.example/brands", staff=None, why="leather bags, same price"):
    return {"name": name, "website": website, "why": why, "source_url": url, "quote": quote or f"{name} makes full-grain bags",
            "staff_hint": staff}


def test_each_competitor_needs_a_page_the_search_opened_and_a_quote_that_names_it():
    out = engine.read("Bonaventura", "premium leather phone cases and bags; about 62 people", ["Italy"], FakeResearch([
        rival("Orciani"), rival("Il Bisonte S.p.A.", quote="Il Bisonte, Florence"),
        rival("Made Up Bags", url="https://elsewhere.example/x"), rival("Nameless", quote="a fine bag maker"),
        rival("Bonaventura"), rival("orciani")]))
    assert [(c.name, c.quoted) for c in out.companies] == [("Orciani", True), ("Il Bisonte S.p.A.", True), ("Nameless", False)]
    assert out.rejected == [{"company": "Made Up Bags", "reason": "its page was not one the search opened"}]


def test_the_strategy_lists_researched_competitors_and_leaves_out_those_far_bigger(session, job):
    client_co, _ = companies.resolve(session, "Client Testhaus", "test", keys={"domain": "client-test.example"})
    client_co.exa_profile = {"employees": 62, "offering": "full-grain leather bags", "domains": ["leather goods"]}
    job.hiring_company_id = client_co.id
    session.flush()
    researcher = FakeResearch([rival("Small Testleather", website="small-leather.example", staff=40),
                               rival("Giant Testgroup", website="giant-group.example", staff=12000),
                               rival("Unquoted Testco", quote="fine bags from Tuscany")])
    targets, report = strategy.competitors(session, job.org_id, job, client_co, FakeExa(people=[], companies=[]), researcher,
                                           set(), ["IT"])
    assert [(t["name"], t["tier"]) for t in targets] == [("Small Testleather", "competitor")]
    assert strategy.group_of(targets[0]) == "A", "competitors are the first companies searched"
    assert report["much_bigger"] == ["Giant Testgroup (12,000)"] and report["kept"] == 1 and report["found"] == 3
    assert report["refused"][0]["reason"] == "neither the quote nor Exa confirms it"
    assert "Italy" in researcher.calls[0][1] and "62 people" in researcher.calls[0][1]
    assert len(researcher.calls) == 1 and report["rounds"] == 1, "a round that adds under three new is the last"


def test_research_goes_deeper_told_what_is_known_and_upgrades_a_listed_company(session, job):
    client_co, _ = companies.resolve(session, "Client Testhaus", "test", keys={"domain": "client-test.example"})
    client_co.exa_profile = {"employees": 62}
    listed, _ = companies.resolve(session, "Listed Testbags", "test", keys={"domain": "listed-bags.example"})
    giant, _ = companies.resolve(session, "Huge Testhouse", "test", keys={"domain": "huge-house.example"})
    giant.exa_profile = {"employees": 12000}
    job.hiring_company_id = client_co.id
    session.flush()
    rounds = [[rival(f"Testmaker {n}", website=f"maker-{n}.example") for n in "ABC"] + [rival("Listed Testbags", website="listed-bags.example")],
              [rival(f"Testmaker {n}", website=f"maker-{n}.example") for n in "DE"], []]

    class Rounds(FakeResearch):
        def search_json(self, system, user, schema, name):
            self.calls.append((name, user))
            return {"companies": rounds[len(self.calls) - 1]}, VISITED, {"usd": 0.2}

    researcher = Rounds([])
    have = {str(listed.id)}
    better: dict = {}
    targets, report = strategy.competitors(session, job.org_id, job, client_co, FakeExa(people=[], companies=[]), researcher,
                                           have, ["IT"], known=["Listed Testbags"], upgrade=better)
    assert [t["name"] for t in targets] == ["Testmaker A", "Testmaker B", "Testmaker C", "Testmaker D", "Testmaker E"]
    assert report["rounds"] == 2 and str(listed.id) in better, "round 2 added two: the last"
    assert "Already known" not in researcher.calls[0][1] and "Listed Testbags" in researcher.calls[1][1]
    assert "Testmaker A" in researcher.calls[1][1]
    # a rebuild drops a far bigger company the desk's own search listed, never one a person placed
    assert strategy._stale(session, {"tier": "peer", "company_id": str(giant.id)}, 62, set())
    assert not strategy._stale(session, {"tier": "named", "company_id": str(giant.id)}, 62, set())
    assert not strategy._stale(session, {"tier": "peer", "company_id": str(giant.id), "pinned": True}, 62, set())
    assert strategy._stale(session, {"tier": "peer", "company_id": str(listed.id)}, 62, {str(listed.id)}), "not from it"
    assert engine._names_it("Gianni Chiarini", "Chiarini bags in Florence") and not engine._names_it("Pelle Italia", "Italia bags")


def test_a_small_company_gets_one_broad_search_a_big_one_the_titles():
    p = SourcingPlan(role_variants=["Marketing Manager", "brand manager", "senior marketing manager"])
    small = Company(name="Franzi", normalized="franzi", exa_profile={"employees": 27})
    big = Company(name="Bigco", normalized="bigco", exa_profile={"employees": 2000})
    assert strategy.variants_for(p, small, "marketing") == ["marketing"]
    assert strategy.variants_for(p, big, "marketing") == ["Marketing Manager", "brand manager", "senior marketing manager",
                                                          "senior Marketing Manager"]
    assert strategy.variants_for(p, small) == ["Marketing Manager", "brand manager", "senior marketing manager"], "no kind of work known"


def _task(session, org_id, payload):
    t = Task(org_id=org_id, kind="sourcing_run", payload=payload, dedupe_key=f"sourcing:{payload['job_id']}", status="running")
    session.add(t)
    session.flush()
    return t


def test_search_now_goes_on_batch_after_batch_and_waits_for_the_readings(session, job, monkeypatch):
    from maindscout.api import autosource

    runs = []
    monkeypatch.setattr(autosource, "run", lambda *a, **k: runs.append(a[4]) or SimpleNamespace(
        status="done", stop_reason="run_limit", found=3, new=3, strong=0, cost_usd=0.05))
    monkeypatch.setattr(task_handlers, "exa_factory", lambda: None)
    first = _task(session, job.org_id, {"job_id": str(job.id), "trigger": "manual", "actor": "owner@desk.test"})
    out = task_handlers.sourcing_run(session, first)
    assert out["next_round"] is True and runs == ["manual"]
    nxt = session.scalar(select(Task).where(Task.kind == "sourcing_run", Task.status == "queued"))
    assert (nxt.payload["trigger"], nxt.payload["round"], nxt.dedupe_key) == ("continue", 2, first.dedupe_key)
    # the next batch waits while this one's career readings are still on their way
    from maindscout.db.models import Candidate, SourcingHit, SourcingRun
    plan = autosource.plan(session, job.org_id, job.id, "owner@desk.test")
    person = Candidate(org_id=job.org_id, name_variants=["Una Testperson"])
    session.add(person)
    session.flush()
    run = SourcingRun(org_id=job.org_id, job_id=job.id, plan_id=plan.id, trigger="manual", status="done", report={})
    session.add(run)
    session.flush()
    session.add(SourcingHit(org_id=job.org_id, job_id=job.id, candidate_id=person.id, run_id=run.id, channel="exa_people",
                            new_to_desk=True))
    session.add(Task(org_id=job.org_id, kind="profile_candidate", payload={"candidate_id": str(person.id)}, status="queued"))
    nxt.status = "running"
    session.flush()
    assert task_handlers.sourcing_run(session, nxt)["status"] == "waiting" and runs == ["manual"]
    # and it never goes on past the last batch, or when a run ended for another reason (the target, the budget)
    last = _task(session, job.org_id, {"job_id": str(job.id), "trigger": "continue", "round": task_handlers.MAX_ROUNDS})
    session.execute(Task.__table__.update().where(Task.kind == "profile_candidate").values(status="done"))
    assert task_handlers.sourcing_run(session, last)["next_round"] is False
    for stop, more in (("searched", True), ("target", False), ("budget", False), ("no_queries", False)):
        monkeypatch.setattr(autosource, "run", lambda *a, **k: SimpleNamespace(
            status="done", stop_reason=stop, found=3, new=3, strong=0, cost_usd=0.05))
        t = _task(session, job.org_id, {"job_id": str(job.id), "trigger": "manual"})
        assert task_handlers.sourcing_run(session, t)["next_round"] is more, f"a batch that ended on {stop}"
