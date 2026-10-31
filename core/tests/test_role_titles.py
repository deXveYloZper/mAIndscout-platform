"""The role's own titles (owner, 2026-10-30: "we cannot hard code every job family there is ... why our platform doesn't
generate this itself, when it understands the company and the role?"): read from the role's own material with its work
lines, confirmed by a person, and used by the searches in place of the shared family table's titles; a search looks in
the role's countries; one former colleague of the client's people makes a company worth searching. Fakes only."""

import pytest
from sqlalchemy import select

from maindscout.api import autosource, marketmap, strategy, work_lines
from maindscout.db.models import Claim, Company
from maindscout.intelligence import work_lines as engine
from maindscout.intelligence.llm import FakeClient, LLMResult
from tests.test_api import client, fake, make_job  # noqa: F401 (fixtures)
from tests.test_autosource import blobs, job  # noqa: F401
from tests.test_work_reader import LINES

OWNER = "owner@desk.test"
TITLES = {"titles": ["Senior InSAR Engineer", "SAR Processing Engineer", "Ingénieur InSAR"],
          "look_alike_titles": ["Radar Hardware Engineer", "SAR Processing Engineer"], "word": "InSAR processing"}


class Reader:
    """Answers the lines reading and the titles reading, as the model does."""

    model = "fake-reader"

    def __init__(self, lines=LINES, titles=TITLES):
        self.lines, self.titles, self.calls = lines, titles, []

    def complete_json(self, system, user, schema, name):
        self.calls.append((name, user))
        return LLMResult(self.titles if name == "role_titles" else self.lines, self.model, 0, 0, 0.0)


def kinds(session, job, status=None):
    rows = session.scalars(select(Claim).where(Claim.subject_id == job.id, Claim.claim_type == work_lines.CLAIM,
                                               Claim.status.in_([status] if status else list(work_lines.LIVE))))
    return sorted(((c.approved_view or c.payload)["kind"], (c.approved_view or c.payload)["words"]) for c in rows)


def test_titles_drop_seniority_and_a_look_alike_is_never_one_of_the_roles_own():
    got = engine.read_titles("InSAR Processing Specialist", "Catalyst", [], [], "The ad.", [], ["FR"], [],
                             FakeClient({**TITLES, "titles": TITLES["titles"] + ["One two three four five six seven eight nine"]}))
    assert got.titles == ["InSAR Engineer", "SAR Processing Engineer", "Ingénieur InSAR"]
    assert got.look_alikes == ["Radar Hardware Engineer"], "a title of the role itself is never its look-alike"
    assert got.word == "InSAR processing"
    assert [r["reason"] for r in got.rejected] == ["a title in one to 8 words"]


def test_titles_come_with_the_lines_wait_for_a_person_then_lead_the_search(session, job):
    before = marketmap.initial(session, job)["role_variants"]
    reader = Reader()
    work_lines.read(session, job.org_id, job.id, reader)
    assert [name for name, _ in reader.calls] == ["core_work_lines", "role_titles"]
    assert "People must live in" in reader.calls[1][1] or not job.open_countries
    assert ("title", "InSAR Engineer") in kinds(session, job, "proposed")
    assert marketmap.initial(session, job)["role_variants"] == before, "nothing searches by a title until a person confirms"

    work_lines.read(session, job.org_id, job.id, Reader(lines={"lines": [], "not_lines": []}))
    assert ("title", "InSAR Engineer") in kinds(session, job), "reading the lines again keeps the titles"

    work_lines.confirm(session, job.org_id, job.id, None, OWNER)
    variants = marketmap.initial(session, job)["role_variants"]
    assert variants[:3] == ["InSAR Engineer", "SAR Processing Engineer", "Ingénieur InSAR"]
    assert not {"remote sensing engineer", "gis engineer"} & {v.lower() for v in variants}, "the family table's titles go"
    assert strategy.broad_word(session, job) == "InSAR processing", "a small company is searched for the role's own word"

    later = Reader(titles={"titles": ["Something Else Engineer"], "look_alike_titles": [], "word": "other"})
    work_lines.read(session, job.org_id, job.id, later)
    assert [name for name, _ in later.calls] == ["core_work_lines"], "confirmed titles are not read again"


def test_a_rebuild_keeps_the_roles_titles_and_drops_the_family_defaults(session, job):
    p = autosource.plan(session, job.org_id, job.id, OWNER)
    p.role_variants = ["Radar Interferometry Specialist", "remote sensing engineer", "SAR engineer", "Typed By Me Engineer"]
    work_lines.read(session, job.org_id, job.id, Reader())
    work_lines.confirm(session, job.org_id, job.id, None, OWNER)
    variants, own = strategy.search_titles(session, job, p, {"titles": [["InSAR Analyst", 3]]})
    assert own and variants[:3] == ["InSAR Engineer", "SAR Processing Engineer", "Ingénieur InSAR"]
    assert "Typed By Me Engineer" in variants, "a title a person added stays"
    assert "remote sensing engineer" not in [v.lower() for v in variants], "a family default no longer comes back"


def test_a_title_typed_by_a_person_is_short_and_loses_its_seniority(session, job):
    claim = work_lines.add(session, job.org_id, job.id, "title", "Senior InSAR Processing Engineer", None, OWNER)
    assert (claim.approved_view or claim.payload)["words"] == "InSAR Processing Engineer" and claim.status == "approved"
    with pytest.raises(ValueError):
        work_lines.add(session, job.org_id, job.id, "title", "one two three four five six seven eight nine", None, OWNER)
    with pytest.raises(ValueError):
        work_lines.add(session, job.org_id, job.id, "word", "five words is too many", None, OWNER)


def test_a_company_is_searched_where_the_role_takes_people():
    group = Company(name="Testgroup", normalized="testgroup", exa_profile={"countries": [
        {"country": "France", "n": 900}, {"country": "United Kingdom", "n": 300}, {"country": "Germany", "n": 40}]})
    assert strategy.search_country(group, "FR", ["GB", "DE"]) == "GB", "not its home country: the role's, where most work"
    assert strategy.search_country(group, "GB", ["GB", "DE"]) == "GB"
    assert strategy.search_country(Company(name="Unknown", normalized="unknown"), "US", ["FI", "SE"]) == "FI"
    assert strategy.search_country(group, "FR", []) == "FR", "a role without countries searches the home country"


def test_one_former_colleague_makes_a_company_a_target(session, job):
    def company(name):
        c = Company(name=name, normalized=name.lower())
        session.add(c)
        session.flush()
        return c

    client_co, two, one, huge = company("Clientco"), company("Twoco"), company("Oneco"), company("Hugeco")
    dna = {"feeders": [{"company_id": str(two.id), "n": 2, "employees": 300},
                       {"company_id": str(one.id), "n": 1, "employees": 200},
                       {"company_id": str(huge.id), "n": 1, "employees": 9000}]}
    got = strategy.feeder_targets(session, dna, client_co, set())
    assert [(t["name"], t["tier"]) for t in got] == [("Twoco", "feeder"), ("Oneco", "feeder_one"), ("Hugeco", "feeder_large")]
    assert strategy.group_of(got[1]) == "A" and got[1]["why"] == ["1 of Clientco's people came from here"]
    assert not strategy.feeder_targets(session, dna, client_co, {str(two.id), str(one.id), str(huge.id)}), "never twice"
