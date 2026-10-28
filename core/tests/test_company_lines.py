"""Company lines of business along their dimensions, used to add, order and explain, never to leave a company out by
default (owner, 2026-10-26: "we shouldn't start our searches from the deepest, but do have an option if we want to
reach more specific person"). Nothing spent."""

import uuid

from sqlalchemy import select

from maindscout.api import autosource, company_lines, companies, strategy
from maindscout.db.models import Claim
from maindscout.intelligence import company_lines as engine
from maindscout.intelligence.llm import LLMResult
from tests.test_api import client, fake, make_job  # noqa: F401 (fixtures)
from tests.test_autosource import FakeExa, job  # noqa: F401
from tests.test_competitors import VISITED, FakeResearch, rival


class Reader:
    """The lines model: answers from a table of company name -> lines."""

    model = "fake-lines"

    def __init__(self, table):
        self.table, self.calls = table, []

    def complete_json(self, system, user, schema, name):
        self.calls.append(user)
        out = []
        for block in user.split("\n\n"):
            number = int(block.split("]")[0].strip("["))
            title = block.split("\n")[0].split("] ", 1)[1]
            out.append({"number": number, "lines": self.table.get(title, [])})
        return LLMResult({"companies": out}, self.model, 100, 50, 0.001)


def ln(line, industry, market, positioning, customers, basis):
    return {"line": line, "industry": industry, "market": market, "positioning": positioning, "customers": customers, "basis": basis}


def co(session, name, **profile):
    c, _ = companies.resolve(session, name, "test", keys={"domain": f"{name.lower().replace(' ', '-')}.example"})
    c.exa_profile = profile or None
    session.flush()
    return c


def test_a_line_needs_words_from_the_companys_own_text():
    blocks = [(1, engine.text_block(1, "Testgem", {"offering": "fine jewellery", "about": "Testgem makes rings and necklaces"}))]
    reader = Reader({"Testgem": [ln("jewellery", "luxury / fashion / beauty", "Fine Jewellery", "luxury", "consumers", "rings and necklaces"),
                                 ln("watches", "luxury / fashion / beauty", "watches", "luxury", "consumers", "Swiss watches since 1900"),
                                 ln("x", "not an industry", "bags", "posh", "people", "rings")]})
    out = engine.classify(blocks, reader)
    assert [(l.market, l.positioning) for l in out.lines[1]] == [("fine jewellery", "luxury"), ("bags", "unknown")]
    assert out.lines[1][1].industry == "other" and out.lines[1][1].customers == "unknown", "unknown values are never guessed"
    assert out.rejected == [{"number": 1, "line": "watches", "reason": "its words are not in the text"}]


def test_lines_are_stored_once_and_a_hiring_company_gets_the_lines_its_research_found(session, org):
    ferrari = co(session, "Testrari", offering="sports cars", about="Testrari is a Maranello based carmaker")
    reader = Reader({"Testrari": [ln("sports cars", "automotive / mobility", "sports cars", "luxury", "consumers", "Maranello based carmaker"),
                                  ln("fashion", "luxury / fashion / beauty", "apparel", "luxury", "consumers", "apparel and fashion")]})
    company_lines.classify(session, org.id, [ferrari], reader, extra={ferrari.id: ["Lifestyle: personal luxury goods, apparel and fashion"]})
    assert "Lines of business found by research" in reader.calls[0]
    assert [(l["industry"], l["market"]) for l in company_lines.of_company(session, ferrari.id)] == [
        ("automotive / mobility", "sports cars"), ("luxury / fashion / beauty", "apparel")]
    assert company_lines.classify(session, org.id, [ferrari], reader)["companies"] == 0, "already read: not read again"
    assert session.scalars(select(Claim.org_id).where(Claim.subject_id == ferrari.id, Claim.claim_type == "CompanyLineClaim")).all()


def test_matching_ordering_and_focus_by_the_dimensions(session, org):
    gem = co(session, "Testgem", offering="fine jewellery", about="Testgem makes fine jewellery")
    tailor = co(session, "Testsartoria", offering="menswear", about="Testsartoria makes luxury menswear")
    reader = Reader({"Testgem": [ln("jewellery", "luxury / fashion / beauty", "fine jewellery", "luxury", "consumers", "fine jewellery")],
                     "Testsartoria": [ln("menswear", "luxury / fashion / beauty", "apparel and menswear", "luxury", "consumers", "luxury menswear")]})
    company_lines.classify(session, org.id, [gem, tailor], reader)
    fashion_line = {"industry": "luxury / fashion / beauty", "market": "apparel", "positioning": "luxury", "customers": "consumers"}
    assert company_lines.closeness(company_lines.of_company(session, tailor.id), fashion_line) == 4
    assert company_lines.closeness(company_lines.of_company(session, gem.id), fashion_line) == 3, "the same level, another market"
    luxury_any = {"industry": "luxury / fashion / beauty", "market": None, "positioning": "luxury"}
    assert {c.id for c in company_lines.members(session, luxury_any)} == {gem.id, tailor.id}, "wide by default: all luxury"
    assert [c.id for c in company_lines.members(session, {**luxury_any, "market": "apparel"})] == [tailor.id]
    focus = {"words": "luxury apparel", "stems": sorted(company_lines.stems("luxury apparel"))}
    assert company_lines.in_focus(session, tailor, focus) and not company_lines.in_focus(session, gem, focus)
    assert company_lines.in_focus(session, gem, None), "no focus: everyone is in"


def test_a_focus_narrows_the_search_only_when_chosen_and_is_undone_with_one_click(client, session, job):
    gem = co(session, "Testgem Two", offering="fine jewellery", about="Testgem Two makes fine jewellery")
    tailor = co(session, "Testsartoria Two", offering="menswear", about="Testsartoria Two makes luxury menswear")
    company_lines.classify(session, job.org_id, [gem, tailor], Reader({
        "Testgem Two": [ln("jewellery", "luxury / fashion / beauty", "fine jewellery", "luxury", "consumers", "fine jewellery")],
        "Testsartoria Two": [ln("menswear", "luxury / fashion / beauty", "apparel and menswear", "luxury", "consumers", "luxury menswear")]}))
    for name in ("Testgem Two", "Testsartoria Two"):
        autosource.add_target(session, job.org_id, job.id, name, "owner@desk.test")
    p = autosource.current_plan(session, job.id)  # as the research had found them (a company added by hand is always searched)
    autosource.update_plan(session, job.org_id, job.id, "owner@desk.test",
                           targets=[{**t, "tier": "competitor", "pinned": False} for t in p.targets])
    def searched():
        return {q["target"] for q in strategy.next_searches(session, job, autosource.current_plan(session, job.id), set(), {})}
    assert searched() == {"Testgem Two", "Testsartoria Two"}, "wide by default"
    page = client.put(f"/v1/jobs/{job.id}/sourcing/focus", json={"words": "luxury apparel"}).json()
    assert page["plan"]["lens"]["focus"]["words"] == "luxury apparel"
    assert searched() == {"Testsartoria Two"}
    gem_row = next(t for t in page["plan"]["targets"] if t["name"] == "Testgem Two")
    assert gem_row["fit"]["why"].startswith("outside the focus")
    page = client.put(f"/v1/jobs/{job.id}/sourcing/focus", json={"words": None}).json()
    assert "focus" not in page["plan"]["lens"] and searched() == {"Testgem Two", "Testsartoria Two"}


def test_a_talent_pool_reuses_known_companies_whose_lines_fit_it_and_the_client_gets_its_lines(session, job):
    client_co = co(session, "Testclient Cars", employees=5000, offering="sports cars", about="Testclient Cars makes sports cars")
    job.hiring_company_id = client_co.id
    session.flush()
    known = co(session, "Testmaison", employees=900, offering="luxury apparel", about="Testmaison sells luxury apparel")
    reader = Reader({"Testmaison": [ln("apparel", "luxury / fashion / beauty", "apparel", "luxury", "consumers", "luxury apparel")],
                     "Testclient Cars": [ln("cars", "automotive / mobility", "sports cars", "luxury", "consumers", "makes sports cars"),
                                         ln("fashion", "luxury / fashion / beauty", "apparel", "luxury", "consumers", "apparel and fashion")]})
    company_lines.classify(session, job.org_id, [known], reader)

    class Map(FakeResearch):
        def search_json(self, system, user, schema, name):
            self.calls.append((name, user))
            if name == "talent_pools":
                return {"business_lines": ["sports cars", "Lifestyle: apparel and fashion"],
                        "role_line": {"line": "fashion collection", "industry": "luxury / fashion / beauty", "market": "apparel",
                                      "positioning": "luxury", "customers": "consumers"},
                        "pools": [{"name": "luxury fashion houses", "why": "same clients", "examples": ["Testmaison"],
                                   "industry": "luxury / fashion / beauty", "market": "", "positioning": "luxury",
                                   "customers": "consumers"}]}, VISITED, {"usd": 0.1}
            return {"companies": []}, VISITED, {"usd": 0.2}

    targets, report = strategy.competitors(session, job.org_id, job, client_co, FakeExa(people=[], companies=[]), Map([]),
                                           set(), ["IT"], reader=reader)
    assert [t["name"] for t in targets] == ["Testmaison"] and targets[0]["source"] == "company_lines"
    assert report["role_line"]["market"] == "apparel"
    assert {l["market"] for l in company_lines.of_company(session, client_co.id)} == {"sports cars", "apparel"}, \
        "the client's fashion line, from its research, is on the client"


def test_a_basis_may_join_several_exact_phrases_but_none_invented():
    text = "sells: ai-native procurement platform about: they offer intake-to-procure, supplier onboarding and ap automation"
    assert engine.supported("AI-native procurement platform, intake-to-procure, supplier onboarding", text)
    assert not engine.supported("AI-native procurement platform, best in Europe", text)
    assert not engine.supported("", text)
