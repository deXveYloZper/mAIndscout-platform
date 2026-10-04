"""Search in the recruiter's own words: read into criteria (checked), ranked best first with reasons."""

import uuid

from maindscout.api import app as api
from maindscout.api import demo, search
from maindscout.intelligence import query as reader
from maindscout.intelligence.llm import LLMResult
from tests.test_api import client, fake  # noqa: F401 (fixtures)

TEXT = "senior devops engineer in Germany with at least 3 years working with kubernetes, good culture fit"
PARSED = {"role_family": "devops_infrastructure", "level": "senior", "min_years": 5,
          "skills": [{"token": "Kubernetes", "min_years": 3}, {"token": "culture fit", "min_years": None}],
          "countries": ["de"], "employer_kinds": [], "domains": [], "companies": ["Google"],
          "current_company_only": False, "ignored": ["good culture fit"]}


class Reader:
    model = "fake-query"

    def __init__(self, data=None):
        self.data, self.calls = data or PARSED, 0

    def complete_json(self, system, user, schema, name):
        assert name == "people_search"
        self.calls += 1
        return LLMResult(self.data, self.model, 100, 40, 0.0004)


def test_a_search_in_plain_words_is_read_into_checked_criteria():
    q = reader.read(TEXT, Reader())
    assert (q.role_family, q.level, q.countries) == ("devops_infrastructure", "senior", ["DE"])
    assert q.skills == [{"token": "kubernetes", "min_years": 3}], "culture fit is never a criterion"
    assert q.min_years is None, "5 years is not written in the search"
    assert q.companies == [], "a company not named in the search is dropped"
    assert search.understood(q) == ["senior", "DevOps / infrastructure", "kubernetes 3+ years", "lives in Germany"]


def test_results_come_best_first_with_their_reasons(client, session):
    org = uuid.UUID(client.headers["X-Org-Id"])
    demo.seed(session, org, count=40)
    reading = Reader({**PARSED, "companies": [], "skills": [{"token": "kubernetes", "min_years": 3}]})
    api.app.dependency_overrides[api.get_llm] = lambda: reading
    api._QUERY_CACHE.clear()
    r = client.get("/v1/search", params={"q": TEXT})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "lives in Germany" in body["understood"]
    people = body["people"]
    assert people, "the demo desk has DevOps engineers"
    weight = [sum(search.WEIGHT[c["kind"]] * search.CREDIT[c["verdict"]] for c in p["criteria"]) for p in people]
    assert weight == sorted(weight, reverse=True), "best matches first"
    top = people[0]["criteria"]
    assert next(c for c in top if c["kind"] == "role")["verdict"] in ("met", "partly")
    assert all(p["met_words"].startswith("meets ") for p in people)
    assert "%" not in str(body) and "score" not in str(body)
    client.get("/v1/search", params={"q": TEXT.upper()})
    assert reading.calls == 1, "the same search again is not read again"


def test_criteria_verdicts_are_met_partly_or_missed():
    q = reader.Query(text="x", role_family="devops_infrastructure", level="senior", skills=[{"token": "kubernetes", "min_years": 3}],
                     countries=["DE"])
    profile = {"dimensions": {"relevant_years": {"main": "software_engineering", "main_years": 2.0},
                              "seniority": {"label": "mid"}, "employer_mix": {}, "domain_exposure": {}}}
    crit = {c["kind"]: c for c in search.criteria_for(profile, q, ["kubernetes"], [], [], {})}
    assert crit["role"]["verdict"] == "partly"  # software engineering is related technical work
    assert crit["level"]["verdict"] == "partly"  # one below
    assert crit["skill"]["verdict"] == "partly" and "2 years" in crit["skill"]["detail"]
    assert crit["country"]["verdict"] == "partly", "where they live is not stated: never a miss"
