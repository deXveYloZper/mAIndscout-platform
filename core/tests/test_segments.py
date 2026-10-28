"""Company segments: market knowledge kept on the company and reused by later roles (owner, 2026-10-26: "yes start with
company tags"). Nothing spent."""

from sqlalchemy import select

from maindscout.api import companies, segments, strategy
from maindscout.db.models import PUBLIC_ORG_ID, Claim, Evidence
from tests.test_api import client, fake, make_job  # noqa: F401 (fixtures)
from tests.test_autosource import FakeExa, job  # noqa: F401
from tests.test_competitors import VISITED, FakeResearch, rival


def co(session, name, **profile):
    c, _ = companies.resolve(session, name, "test", keys={"domain": f"{name.lower().replace(' ', '-')}.example"})
    c.exa_profile = profile or None
    session.flush()
    return c


def test_a_tag_is_a_public_fact_with_its_source_and_never_names_the_client(session):
    watch = co(session, "Testwatch Geneve", employees=900, offering="watches")
    segments.tag(session, watch, "Luxury Jewellery & Watches", "https://press.example/a", "Testwatch Geneve watches")
    segments.tag(session, watch, "luxury jewellery and watches", "https://press.example/a", "again")  # same page: no new source
    segments.tag(session, watch, "luxury jewellery and watches", "https://trade.example/b", "Testwatch, the Swiss maker")
    claims = session.scalars(select(Claim).where(Claim.subject_id == watch.id, Claim.claim_type == "CompanySegmentClaim")).all()
    assert [c.org_id for c in claims] == [PUBLIC_ORG_ID] and claims[0].payload == {"segment": "luxury jewellery and watches"}
    assert session.scalar(select(Evidence.id).where(Evidence.claim_id == claims[0].id).limit(1))
    assert segments.of_company(session, watch.id) == ["luxury jewellery and watches"]
    assert [c.id for c in segments.members(session, "Luxury Jewellery & Watches")] == [watch.id]
    assert ("luxury jewellery and watches", 1) in segments.known(session)
    assert segments.says_luxury(session, watch)
    assert segments.tag(session, watch, "Testclient Motors' direct rivals", client_name="Testclient Motors") is None


def test_research_never_rules_a_tagged_luxury_company_out_on_exas_words(session):
    hyper = co(session, "Testhyper Cars", employees=300, offering="hypercars", domains=["automotive"])
    assert strategy.fit(session, hyper, set(), None, luxury=True)["searched"] is False, "Exa's words alone: not luxury"
    segments.tag(session, hyper, "luxury sports car manufacturers", "https://press.example/c", "Testhyper Cars")
    assert strategy.fit(session, hyper, set(), None, luxury=True)["searched"] is True


def test_a_later_role_starts_from_a_known_segment_and_only_researches_what_is_new(session, job):
    client_co = co(session, "Testclient Watches", employees=800, offering="luxury watches")
    job.hiring_company_id = client_co.id
    session.flush()
    known = [co(session, f"Testknown Maison {n}", employees=500, offering="watches") for n in range(9)]
    for k in known:
        segments.tag(session, k, "luxury jewellery and watches", f"https://list.example/{k.name}", k.name)

    class Map(FakeResearch):
        def search_json(self, system, user, schema, name):
            self.calls.append((name, user))
            if name == "talent_pools":
                return {"business_lines": ["watches"], "pools": [
                    {"name": "Luxury jewellery and watches", "why": "same clients", "examples": ["Testknown Maison 1"]}]}, VISITED, {"usd": 0.1}
            if "Only this pool" in user:
                return {"companies": [rival("Testnew Horloger", website="new-horloger.example")]}, VISITED, {"usd": 0.2}
            return {"companies": []}, VISITED, {"usd": 0.2}

    researcher = Map([])
    targets, report = strategy.competitors(session, job.org_id, job, client_co, FakeExa(people=[], companies=[]), researcher, set(), ["CH"])
    pools_call = researcher.calls[0][1]
    assert "Pools we already know" in pools_call and "luxury jewellery and watches (9 companies)" in pools_call
    pool_rounds = [u for n, u in researcher.calls if n == "competitors" and "Only this pool" in u]
    assert len(pool_rounds) == 1 and "Look further" in pool_rounds[0], "known well: only the deeper round, told what is known"
    assert "Testknown Maison 3" in pool_rounds[0]
    names = {t["name"] for t in targets}
    assert {k.name for k in known} <= names and "Testnew Horloger" in names
    assert report["pools"][0]["reused"] == 9
    new = next(t for t in targets if t["name"] == "Testnew Horloger")
    assert segments.of_company(session, __import__("uuid").UUID(new["company_id"])) == ["luxury jewellery and watches"], \
        "what the research adds joins the segment for the next role"


def test_a_direct_competitors_line_finds_its_pool():
    pools = [{"name": "Luxury sports car manufacturers"}, {"name": "Luxury jewellery and watches"}]
    assert segments.best_pool("luxury sports cars", pools) == "Luxury sports car manufacturers"
    assert segments.best_pool("luxury watches", pools) == "Luxury jewellery and watches"
    assert segments.best_pool("racing", pools) is None and segments.best_pool(None, pools) is None


def test_a_team_in_the_country_is_judged_without_a_size_or_share_threshold():
    from maindscout.db.models import Company

    def company(rows):
        return Company(name="Testco", normalized="testco", exa_profile={"countries": rows})
    group = company([{"n": 984, "pct": 3, "country": "France"}, {"n": 670, "pct": 2, "country": "Italy"}])
    startup = company([{"n": 18, "pct": 100, "country": "Italy"}])
    few = company([{"n": 118, "pct": 10, "country": "France"}, {"n": 5, "pct": None, "country": "Italy"}])
    elsewhere = company([{"n": 40, "pct": 95, "country": "United Kingdom"}])  # the whole company: nobody in Italy
    cut = company([{"n": 100 - i, "pct": 1, "country": c} for i, c in enumerate(
        ["France", "Germany", "Spain", "Japan", "China", "Brazil", "India", "Mexico", "Canada", "Korea"])])
    assert strategy.team_in(group, {"IT"}) is True and strategy.team_in(startup, {"IT"}) is True
    assert strategy.team_in(few, {"IT"}) is True and strategy.people_in(few, {"IT"}) == 5, "few people: searched, last"
    assert strategy.team_in(elsewhere, {"IT"}) is False
    assert strategy.team_in(cut, {"IT"}) is None, "a list cut at ten countries does not prove nobody is in Italy"
