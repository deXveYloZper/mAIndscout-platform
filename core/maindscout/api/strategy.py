"""A role's search strategy, built and grown like a recruiter's (docs/next/PLAN.md section 4b, S7).

1. **Talent DNA** of the hiring company: a few "{role} at {company}" people searches, kept only for people whose work
   history shows the hiring company under its exact Exa company id. From them: their titles there, the job just before
   they joined, and their earlier employers, profiled and grouped by kind, size and domain. Plus the company's own
   profile: where its team works, its departments, its talent sources. Nobody found here is ever stored: they work at
   the client (an active client is off-limits). Only counts, titles and companies are kept.
2. **Target list in tiers**, each company with its why: A (named by the hiring manager, repeat feeders), B (companies
   like the hiring company, from descriptive company searches built from its profile; desk companies in the same
   domain; snowball finds), C (very large feeders,
   companies releasing talent, adjacent domains). Every company is profiled, so "similar" is shown in facts.
3. **Snowball** after each run: an earlier employer of two or more strong people for the role becomes a target; a
   company that keeps producing gets its own peer search.
4. **Widening** is proposed with numbers when the open tiers are exhausted, the role is short of its target and the
   recent yield is low. The owner decides; each choice is a new plan version.
Searches name roles, companies and places, never a person.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from maindscout.api import autosource, companies, company_profiles, costs
from maindscout.db.models import PUBLIC_ORG_ID, Candidate, CandidateJob, Claim, Company, Job, SourcingPlan, SourcingQuery
from maindscout.domain import geo, tiers
from maindscout.intelligence import company_profile, exa

LIVE = ("proposed", "approved")
DNA_SEARCHES = 3
LARGE = 5000  # a feeder this big is a kind of employer (tier C), not a list of people to search one by one
GROUP_OF_TIER = {"named": "A", "manual": "A", "feeder": "A", "known": "B", "peer": "B", "snowball": "B",
                 "adjacent": "C", "release": "C", "feeder_large": "C", "large_peer": "C"}
GROUPS = ("A", "B", "C")
RULES = {"batch": 5, "exhausted_after": 2, "known_share": 0.8, "low_yield": 0.2, "recheck_days": 90, "yield_window": 15,
         "max_results": 50}
MARKET_RESULTS = 25
NOT_THE_ROLE = re.compile(r"\b(sales|account|ceo|cfo|coo|founder|co-founder|recruit|talent|hr|people|marketing|finance|"
                          r"legal|office|operations|intern|student)\b", re.I)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def group_of(target: dict[str, Any]) -> str:
    return target.get("group") or GROUP_OF_TIER.get(target.get("tier") or "", "B")


def rules(p: SourcingPlan) -> dict[str, Any]:
    return {**RULES, **(p.rules or {})}


def size_band(n: int | None) -> str | None:
    if not n:
        return None
    return "startup (up to 50)" if n <= 50 else "scale-up (51-500)" if n <= 500 else "mid-size (501-5,000)" if n <= LARGE else "large (5,000+)"


def _ym(value: str | None) -> tuple[int, int] | None:
    m = re.match(r"(\d{4})(?:-(\d{2}))?", value or "")
    return (int(m.group(1)), int(m.group(2) or 1)) if m else None


def _target(company: Company, tier: str, why: list[str], source: str, pinned: bool = False) -> dict[str, Any]:
    p = company_profiles.summary(company) or {}
    return {"name": company.name, "company_id": str(company.id), "tier": tier, "group": GROUP_OF_TIER.get(tier, "B"),
            "why": why, "source": source, "people_on_desk": 0, "pinned": pinned, "removed": False,
            "country": company.hq_country, "employees": p.get("employees")}


# --- stage 1: talent DNA -----------------------------------------------------------------------------------------------


def hiring_company(session: Session, job: Job) -> Company | None:
    return companies.canonical(session, session.get(Company, job.hiring_company_id)) if job.hiring_company_id else None


def talent_dna(session: Session, org_id: uuid.UUID, job: Job, p: SourcingPlan, caller, task_id=None) -> dict[str, Any]:
    company = hiring_company(session, job)
    if company is None:
        raise autosource.SourcingEngineError("The role has no hiring company")
    if not (company.domain or company.linkedin or company.exa_id):
        # Exa is never asked by a name alone: a similar name is not the same company (x-ray A6, 2026-10-13).
        raise autosource.SourcingEngineError(
            f"The desk has no website or LinkedIn page for {company.name}, so Exa cannot be sure which company it is: add "
            "one on its company page, then build again")
    if not company_profiles.fresh(company) and not company_profiles.by_name(session, company, caller, org_id, job.id, task_id):
        raise autosource.SourcingEngineError(
            f"Exa found no company with {company.name}'s website or LinkedIn page ({company.domain or company.linkedin}): "
            "check it on its company page")
    if not company.exa_id:
        raise autosource.SourcingEngineError(f"Exa has no company id for {company.name}: add target companies by hand")
    profile = company.exa_profile or {}

    people: dict[str, list[dict[str, Any]]] = {}
    spent, searches = 0.0, []
    # The name the company goes by, as its confirmed profile writes it: an ad's "BUONAVENTURA" found none of
    # Bonaventura's people (2026-10-18).
    name = (profile.get("name") or company.name).strip()
    for variant in (p.role_variants or [job.title])[:DNA_SEARCHES]:
        results = exa.search(caller, f"{variant} at {name}", "people", num_results=10, text_chars=1000)
        spent += results.usd
        kept = 0
        for found in results.found:
            history = (found.person or {}).get("workHistory") or []
            if any((j.get("company") or {}).get("id") == company.exa_id for j in history):
                people.setdefault(found.url, history)
                kept += 1
        searches.append({"text": f"{variant} at {name}", "results": len(results.found), "theirs": kept})
    costs.record(session, org_id, "sourcing_talent_dna", {"model": "exa", "usd": spent, "sources": len(people)},
                 subject_type="job", subject_id=job.id, task_id=task_id)

    titles, before_titles, feeders, names = Counter(), Counter(), Counter(), {}
    for history in people.values():
        here = [j for j in history if (j.get("company") or {}).get("id") == company.exa_id]
        joined = min((_ym((j.get("dates") or {}).get("from")) or (9999, 1)) for j in here)
        for j in here:
            if j.get("title"):
                titles[j["title"]] += 1
        earlier = []
        for j in history:
            c = j.get("company") or {}
            start = _ym((j.get("dates") or {}).get("from"))
            if c.get("id") != company.exa_id and c.get("name") and start and start < joined:
                earlier.append((start, c, j.get("title")))
        if earlier:
            before_titles[max(earlier, key=lambda x: x[0])[2]] += 1
        for key in {(c.get("id") or c["name"]): c for _, c, _ in earlier}:
            c = next(c for _, c, _ in earlier if (c.get("id") or c["name"]) == key)
            if not company_profile.NOISE.search(c["name"]):
                feeders[key] += 1
                names[key] = c["name"]

    ids = {k: None for k in feeders if str(k).startswith("https://exa.ai/")}
    profiled = company_profiles.by_ids(session, ids, caller, org_id, job.id, task_id) if ids else {}
    rows, kinds, bands, categories = [], Counter(), Counter(), Counter()
    for key, n in feeders.most_common():
        c = profiled.get(key)
        s = company_profiles.summary(c) if c is not None else None
        if c is None or not s or not s.get("employees"):
            continue  # no profile with staff: a community, an award, a one-person page
        rows.append({"company_id": str(c.id), "name": c.name, "n": n, "employees": s["employees"], "kind": s.get("kind"),
                     "industry": s.get("industry"), "hq": s.get("hq"), "domains": s.get("domains")})
        kinds[s.get("kind") or "unknown"] += n
        bands[size_band(s["employees"])] += n
        for domain in s.get("domains") or []:
            categories[domain] += n
    return {
        "at": _now().isoformat(), "company": {"id": str(company.id), "name": company.name, "employees": profile.get("employees"),
                                              "team_countries": (company_profiles.summary(company) or {}).get("team_countries")},
        "people": len(people), "searches": searches, "titles": titles.most_common(8), "before": before_titles.most_common(8),
        "feeders": rows[:20], "pattern": {"kinds": kinds.most_common(), "sizes": bands.most_common(), "domains": categories.most_common(6)},
        "talent_sources": company_profile.feeders(company_profile.Profile(talent_sources=profile.get("talent_sources") or []))[:10],
        "departments": (profile.get("departments") or [])[:5], "cost_usd": round(spent, 4),
    }


# --- stage 2: the target list in tiers ---------------------------------------------------------------------------------


# A programming tool is not a field of work: "node.js companies" is no peer search (seen on a real role, 2026-10-13).
TOOLS = {"python", "java", "javascript", "typescript", "node.js", "nodejs", "node", "react", "react.js", "vue", "angular", "go",
         "golang", "rust", "c", "c++", "c#", ".net", "php", "ruby", "scala", "kotlin", "swift", "sql", "nosql", "postgresql",
         "mysql", "mongodb", "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "linux", "git", "graphql", "rest",
         "html", "css", "django", "flask", "fastapi", "spring", "next.js", "pytorch", "tensorflow", "spark", "kafka", "matlab"}
STAGE_WORDS = {"pre seed": "pre-seed to Series A", "seed": "seed to Series B", "series a": "Series A to C",
               "series b": "Series A to C", "series c": "growth stage", "private equity": "growth stage", "venture": "venture-backed"}
MIN_PEER_STAFF = 10  # smaller ones are mostly name look-alikes and one-person pages


def peer_queries(company: Company, countries: list[str] | None = None, skills: list[str] | None = None) -> list[str]:
    """Descriptive company searches from a company's own profile: what it does, where its team works, its stage.
    (Exa's find-similar on a website matched on names in the 2026-10-13 test, so it is not used.)"""
    p = company.exa_profile or {}
    what = p.get("offering") or (p.get("domains") or [None])[0]
    if not what:
        return []
    market = (p.get("domains") or [what])[0]
    where = ([geo.name_of(c) for c in countries][:2] if countries
             else [c["country"] for c in p.get("countries") or [] if (c.get("pct") or 0) >= 10][:2])
    out = [f"{what} companies in {' and '.join(where)}" if where else f"{what} companies"]
    stage = ((p.get("rounds") or [{}])[0].get("stage") or "").lower()
    if stage in STAGE_WORDS:
        out.append(f"{market} startups, {STAGE_WORDS[stage]}")
    place = f" in {' and '.join(where)}" if where else ""
    for skill in [k for k in skills or [] if k.lower() not in TOOLS][:1]:  # who else does this specialist work:
        out.append(f"{skill} companies{place}")                           # "insar companies in Canada"
    return out


def profile_queries(session: Session, job: Job, countries: list[str] | None = None) -> list[str]:
    """Company searches from the hiring profile itself, for a role whose company is unknown or not confirmed (an
    anonymised ad): its industries ("luxury / fashion / beauty" -> "luxury, fashion and beauty companies in Italy"),
    industries named in its background sentences ("Experience in luxury, premium fashion…"), and the short backgrounds
    a person typed or the intake gave ("luxury")."""
    from maindscout.domain.profile import domains_in

    def as_words(d: str) -> str:
        bits = [b.strip() for b in d.split("/")]
        return ", ".join(bits[:-1]) + f" and {bits[-1]}" if len(bits) > 1 else bits[0]

    where = " and ".join(geo.name_of(c) for c in (countries or [])[:2])
    place = f" in {where}" if where else ""
    lux = luxury(session, job)  # a luxury client's industries are searched in luxury words (owner, 2026-10-18)
    words = (lambda d: tiers.search_words(d, as_words(d))) if lux else as_words
    # The role's required industries decide where to hunt; nice-to-have ones only when it names none (2026-10-21: an
    # InSAR role's "asset monitoring" nice-to-have filled its map with water utilities, while an anonymised ad whose
    # only industry is a nice-to-have sentence still needs it).
    asked = {"required": [], "nice": []}
    for c in session.scalars(select(Claim).where(Claim.subject_id == job.id, Claim.claim_type == "JobRequirementClaim",
                                                 Claim.status.in_(LIVE)).order_by(Claim.created_at)):
        p = c.approved_view or c.payload
        if p.get("strength") != "anti":
            asked["nice" if p.get("strength") in ("nice", "unknown") else "required"].append(p)
    phrases: list[str] = []
    for p in asked["required"] + asked["nice"]:
        if p in asked["nice"] and phrases:
            break
        if p.get("category") == "domain":
            phrases += [words(d) for d in p.get("domains") or [] if d != "other"]
        elif p.get("category") in ("skill", "other") and (p.get("distinctive") or BACKGROUND.search(p.get("text_raw") or "")):
            phrases += [words(d) for d in domains_in(p.get("text_raw") or "")[:1]]
        elif p.get("category") in ("employer", "other") and p.get("source") in ("recruiter", "intake"):
            text = " ".join((p.get("text_raw") or "").split())
            if 0 < len(text.split()) <= 4 and not p.get("employer_kinds"):
                phrases.append(tiers.search_words("", text) if lux else text)
    out = list(dict.fromkeys(f"{x.lower()} companies{place}" for x in phrases))
    return out[:3]


def luxury(session: Session, job: Job) -> bool:
    """Does the role ask for luxury (its own requirements say so)? Then its companies must be luxury ones too."""
    from maindscout.api import memo

    return memo.cached(session, ("luxury", job.id), lambda: _luxury(session, job))


def _luxury(session: Session, job: Job) -> bool:
    texts = []
    for c in session.scalars(select(Claim).where(Claim.subject_id == job.id, Claim.claim_type == "JobRequirementClaim",
                                                 Claim.status.in_(LIVE))):
        p = c.approved_view or c.payload
        if p.get("strength") != "anti":
            texts.append(p.get("text_raw") or "")
    return tiers.luxury_role(texts)


# Kinds of company that sell services, not a product: never "like" a product company (its peers make products too).
SERVICES = ("consultancy", "agency", "outsourcing")


# A requirement that speaks about where a person comes from, not what they can do ("Experience in luxury, …").
BACKGROUND = re.compile(r"\b(experience (in|with|at|from)|background in|industry|sector|brands?)\b", re.I)


def _peers(session: Session, org_id: uuid.UUID, job: Job, of: Company | None, caller, have: set[str], why: str, limit: int,
           task_id=None, countries: list[str] | None = None, skills: list[str] | None = None,
           queries: list[str] | None = None) -> list[dict[str, Any]]:
    """Companies like `of`, from descriptive company searches; each result is its own Exa profile (kept, no second
    call). The hiring company, companies already listed and micro companies are left out. Their domains are read in
    one call at the end."""
    out: list[dict[str, Any]] = []
    made: list[Company] = []
    lux = luxury(session, job)
    like_client = of is not None and (of.exa_profile or {}).get("kind") in (None, "product") and queries is None
    from maindscout.api.process import client_context

    client_staff = client_context(session, job)["staff"]
    for query in queries if queries is not None else peer_queries(of, countries, skills):
        # A search by the role's skill ("insar companies in United Kingdom") also returns look-alike names (ISAR3, a
        # rescue firm; INSPHERE, automotive; 2026-10-21): a company found that way must name the skill itself.
        skill = next((k for k in skills or [] if query.lower().startswith(f"{k.lower()} companies")), None)
        results = exa.search(caller, query, "company", num_results=10, text_chars=8000)
        costs.record(session, org_id, company_profiles.PURPOSE, {"model": "exa", "usd": results.usd, "sources": len(results.found)},
                     subject_type="job", subject_id=job.id, task_id=task_id)
        for found in results.found:
            if skill and not re.search(rf"(?<![\w-]){re.escape(skill)}(?![\w-])", found.text or "", re.I):
                continue
            p = company_profile.read(found.text)
            name = p.name or (found.company or {}).get("name")
            if not name or (p.employees is not None and p.employees < MIN_PEER_STAFF):
                continue
            company, _ = companies.resolve(session, name, "exa", keys={"exa_id": found.entity_id, "domain": p.homepage or found.url})
            company = companies.canonical(session, company)
            if company is None or str(company.id) in have or company.id == job.hiring_company_id or (of is not None and company.id == of.id):
                continue
            company_profiles.apply(session, company, found, org_id)
            if str(company.id) in not_from(session, job)[0]:
                continue  # a company the hiring profile says not to recruit from is never a target (2026-10-21)
            if like_client and (company.exa_profile or {}).get("kind") in SERVICES:
                continue  # a product company's peers make products: consultancies' people are consultants (2026-10-21)
            if fit(session, company, set(), not_from(session, job)[1], lux)["searched"] is False:
                continue  # a kind of company the hiring profile does not want, or not luxury for a luxury role
            have.add(str(company.id))
            made.append(company)
            times = much_bigger(company, client_staff)  # 20x the client's size: in its market, but no competitor
            out.append(_target(company, "large_peer" if times else "peer",
                               [why, f'company search: "{query}"'] + ([f"about {times}x the client's size"] if times else []), "exa_company"))
            if len(out) >= limit:
                break
        if len(out) >= limit:
            break
    company_profiles.read_domains(session, made, org_id, task_id=task_id)
    return out


def build(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, caller, actor: str, task_id=None) -> dict[str, Any]:
    """Stages 1 and 2: the talent DNA and the tiered target list, as a new plan version (paid, under $0.50)."""
    job = autosource._job(session, org_id, job_id)
    p = autosource.plan(session, org_id, job_id, actor)
    autosource._check_budgets(session, org_id, job, p)
    from maindscout.api import marketmap

    company = hiring_company(session, job)
    countries = list(p.countries)
    skipped = None
    try:
        dna = talent_dna(session, org_id, job, p, caller, task_id)
    except autosource.SourcingEngineError as error:
        # No hiring company, or Exa cannot confirm it (an anonymised or small company): no talent DNA, but the list is
        # still built, from the hiring profile's industries and backgrounds (seen on a real role, 2026-10-13).
        dna, skipped = None, str(error)
        if not profile_queries(session, job, countries) and not p.targets:
            raise autosource.SourcingEngineError(
                f"{error}. Or give the hiring profile an industry (Add a requirement → Industry, e.g. luxury / fashion / "
                "beauty), or add target companies by hand") from error
    limits = autosource.off_limits(session, org_id)
    targets = [dict(t, group=group_of(t)) for t in p.targets]
    have = {t.get("company_id") for t in targets} | ({str(company.id)} if company is not None else set())

    for row in (dna or {}).get("feeders", []):
        if row["n"] < 2 or row["company_id"] in have:
            continue
        large = (row.get("employees") or 0) > LARGE
        c = session.get(Company, uuid.UUID(row["company_id"]))
        why = [f"{row['n']} of {company.name}'s people came from here"]  # its facts show on their own line
        targets.append(_target(c, "feeder_large" if large else "feeder", why, "talent_dna"))
        have.add(row["company_id"])
    if dna is not None:
        derived = not countries or countries == ([company.hq_country] if company.hq_country else [])
        team = [geo.country_in(c["country"]) for c in (dna["company"].get("team_countries") or []) if (c.get("pct") or 0) >= 15]
        if derived and not role_countries(session, job) and [c for c in team if c]:  # the ad's own place always wins
            countries = list(dict.fromkeys(c for c in team if c))[:3]
    from maindscout.api.sourcing import query_tokens

    if dna is not None:
        targets += _peers(session, org_id, job, company, caller, have, f"like {company.name}", 15, task_id, countries,
                          query_tokens(session, job))
    from_profile = profile_queries(session, job, countries)
    if from_profile:  # the hiring profile's own industries and backgrounds, always (they say what the client wants)
        targets += _peers(session, org_id, job, company, caller, have, "fits the hiring profile's industry or background",
                          15, task_id, countries, queries=from_profile)
    for t in targets:  # profile the rest we can confirm by a key, so every company shows its facts
        c = session.get(Company, uuid.UUID(t["company_id"])) if t.get("company_id") else None
        if c is not None and not company_profiles.fresh(c) and (c.exa_id or c.domain or c.linkedin) and not limits.get(str(c.id)):
            if company_profiles.by_name(session, c, caller, org_id, job.id, task_id):
                t["employees"] = (company_profiles.summary(c) or {}).get("employees")

    # Titles: the ad's title cleaned of its places ("Marketing Manager Italy and Europe" -> "Marketing Manager") and the
    # usual titles for the kind of work, before any the owner added.
    fresh = marketmap.initial(session, job)["role_variants"]
    raw = " ".join((job.title or "").split()).lower()
    variants = list(dict.fromkeys([*fresh[:1], *[v for v in p.role_variants if v.lower() != raw], *fresh[1:]]))
    words = {w for v in variants for w in re.findall(r"[a-z]+", v.lower())}
    for title, n in (dna or {}).get("titles", []):
        other_work = [w for w in NOT_THE_ROLE.findall(title.lower()) if w not in words]  # "marketing" is fine for a marketer
        if (n >= 2 and title.lower() not in {v.lower() for v in variants} and not other_work
                and words & set(re.findall(r"[a-z]+", title.lower()))):
            variants.append(title)
    changes: dict[str, Any] = {"targets": targets, "role_variants": variants[:5], "countries": countries}
    if dna is not None:
        changes["dna"] = dna
    new = autosource.update_plan(session, org_id, job_id, actor, **changes)
    if dna is None:
        return {"version": new.version, "people": 0, "feeders": 0, "note": f"No talent DNA: {skipped}. The list was built from the "
                "hiring profile instead.",
                "targets": {g: sum(1 for t in new.targets if group_of(t) == g and not t.get("removed")) for g in GROUPS},
                "countries": new.countries, "role_variants": new.role_variants}
    return {"version": new.version, "people": dna["people"], "feeders": len(dna["feeders"]),
            "targets": {g: sum(1 for t in new.targets if group_of(t) == g and not t.get("removed")) for g in GROUPS},
            "countries": new.countries, "role_variants": new.role_variants}


# --- in step with the hiring profile -----------------------------------------------------------------------------------


def sync(session: Session, org_id: uuid.UUID, job: Job, actor: str = "hiring profile") -> SourcingPlan:
    """The plan follows the role's hiring profile (owner, 2026-10-13): where people must live (its residence
    requirement) are the role's countries, and every company it names is a pinned tier A target. A new plan version
    only when something changed."""
    from maindscout.api import coverage, search

    p = autosource.plan(session, org_id, job.id, actor)
    changes: dict[str, Any] = {}
    wanted = role_countries(session, job)
    # One source of truth (x-ray B1): the hiring profile's "must live in" (else the ad's places). Every country box
    # writes there, so the plan follows it both ways. With neither, the plan keeps what the strategy chose.
    if wanted and set(p.countries or []) != wanted:
        changes["countries"] = [c for c in (p.countries or []) if c in wanted] + sorted(wanted - set(p.countries or []))
    _, named = search.job_filters(session, job)
    have = {t.get("company_id") for t in p.targets}
    new = []
    for company_id in named:
        company = companies.canonical(session, session.get(Company, uuid.UUID(company_id)))
        if company is not None and str(company.id) not in have and company.id != job.hiring_company_id:
            new.append(_target(company, "named", ["named in the hiring profile"], "hiring_profile", pinned=True))
            have.add(str(company.id))
    if new:
        changes["targets"] = [*new, *p.targets]
    return autosource.update_plan(session, org_id, job.id, actor, **changes) if changes else p


def role_countries(session: Session, job: Job) -> set[str]:
    """Where the role is, by its hiring profile: its "must live in" countries, else the places the ad names
    ("LOCATION: Markham or Gatineau"): a place that names no country counts as the hiring company's home country."""
    from maindscout.api import coverage

    residence = set(coverage.ad_countries(session, job))
    if residence:
        return residence
    out: set[str] = set()
    for c in session.scalars(select(Claim).where(Claim.subject_id == job.id, Claim.claim_type == "JobRequirementClaim",
                                                 Claim.status.in_(LIVE))):
        p = c.approved_view or c.payload
        if p.get("category") != "location" or not (p.get("text_raw") or "").strip():
            continue
        if re.search(r"bremoteb", p["text_raw"], re.I):
            continue
        code = geo.country_in(p["text_raw"])
        if code is None:
            company = hiring_company(session, job)
            code = company.hq_country if company is not None else None
        if code:
            out.add(code)
    return out


def team_in(company: Company | None, countries: set[str]) -> bool | None:
    """Does the company have people in the role's countries (5% of its team or more)? None when its profile does
    not say. A company whose team is all elsewhere only gives people the role would refuse."""
    rows = ((company.exa_profile or {}).get("countries") or []) if company is not None else []
    if not countries or not rows:
        return None
    return any(geo.country_in(r.get("country")) in countries and (r.get("pct") or 0) >= 5 for r in rows)


def closed(session: Session, company: Company | None) -> bool:
    """Shut down, by its public facts (a person may still approve or reject that fact)."""
    from maindscout.api import memo

    if company is None:
        return False
    return memo.cached(session, ("closed", company.id), lambda: _shut_down(session.scalar(select(Claim).where(
        Claim.org_id == PUBLIC_ORG_ID, Claim.subject_id == company.id, Claim.claim_type == "CompanyStatusClaim",
        Claim.status.in_(LIVE)))))


def _shut_down(status: Claim | None) -> bool:
    return bool(status) and (status.approved_view or status.payload).get("status") == "shut_down"


def prefetch_closed(session: Session, companies_: list[Company]) -> None:
    """Inside a page's memo: every company's status in one query."""
    from maindscout.api import memo

    if session.info.get("memo") is None or not companies_:
        return
    found = {c.subject_id: c for c in session.scalars(select(Claim).where(
        Claim.org_id == PUBLIC_ORG_ID, Claim.subject_id.in_([c.id for c in companies_]),
        Claim.claim_type == "CompanyStatusClaim", Claim.status.in_(LIVE)))}
    for c in companies_:
        memo.put(session, ("closed", c.id), _shut_down(found.get(c.id)))


# A background the hiring profile does not want, as the kinds of company that give it.
ANTI_KIND = {"consultancy": {"consultancy", "outsourcing"}, "agency": {"agency"}, "public_sector": {"public_sector"},
             "non_profit": {"non_profit"}}


def not_from(session: Session, job: Job) -> tuple[set[str], set[str]]:
    """The hiring profile's "not from" (x-ray B3, 2026-10-13): the companies it names (every id each is known by), and
    the kinds of company a background it does not want comes from ("no candidates from big consultancies")."""
    ids: set[str] = set()
    kinds: set[str] = set()
    for c in session.scalars(select(Claim).where(Claim.subject_id == job.id, Claim.claim_type == "JobRequirementClaim",
                                                 Claim.status.in_(LIVE))):
        p = c.approved_view or c.payload
        if p.get("strength") != "anti":
            continue
        if p.get("category") == "target_company":
            for named in p.get("companies") or []:
                company = (companies.canonical(session, session.get(Company, uuid.UUID(named["company_id"])))
                           if named.get("company_id") else None)
                if company is not None:
                    ids |= set(companies._ids_for(session, company))
        elif p.get("category") == "employer":
            for k in p.get("employer_kinds") or []:
                kinds |= ANTI_KIND.get(k, set())
    return ids, kinds


def fit(session: Session, company: Company | None, countries: set[str], avoid_kinds: set[str] | None = None,
        luxury: bool = False, client_staff: int | None = None, wide: bool = False) -> dict[str, Any]:
    """Why a company is or is not searched for this role, for the map. `luxury`: the role asks for luxury, so a
    company that is known and is not a luxury one is left out (a 4-star chain, a tour operator). `client_staff`: a
    company 20 or more times the client's size is not a competitor (owner, 2026-10-21: "its not similar company
    compare to 12k people and 62 people, its a standard recruiter logic"); it is searched only once Tier C is open
    (`wide`)."""
    if closed(session, company):
        return {"searched": False, "why": "shut down"}
    times = much_bigger(company, client_staff)
    if times and not wide:
        return {"searched": False, "why": f"about {times}x the client's size: not a competitor (searched only if you widen to Tier C)"}
    kind = ((company.exa_profile or {}).get("kind") if company is not None else None)
    if kind and avoid_kinds and kind in avoid_kinds:
        return {"searched": False, "why": f"a {kind.replace('_', ' ')}: the hiring profile says not from there"}
    if luxury and company is not None and tiers.luxury_company(company.exa_profile) is False:
        return {"searched": False, "why": "not a luxury company: the role asks for luxury"}
    inside = team_in(company, countries)
    if inside is False:
        where = ", ".join(r["country"] for r in (company.exa_profile or {}).get("countries", [])[:2])
        return {"searched": False, "why": f"no team in the role's countries (its team: {where})"}
    return {"searched": True, "why": None}


BIG_PEER = 20  # the same factor as matching's move check (domain/matching.BIG_MOVE)


def much_bigger(company: Company | None, client_staff: int | None) -> int | None:
    """How many times the client's size a company is, when that makes it no competitor (20x or more), else None."""
    staff = ((company.exa_profile or {}).get("employees") if company is not None else None)
    if not staff or not client_staff or staff < BIG_PEER * client_staff:
        return None
    return round(staff / client_staff)


def outside_countries(session: Session, org_id: uuid.UUID, candidate_id: uuid.UUID, countries: set[str]) -> bool:
    """Is this person outside the role's countries? Where they live decides; where they work only when where they
    live is unknown; unknown altogether is not refused (a person can tell us on the call)."""
    from maindscout.api import coverage

    if not countries:
        return False
    lives, works = coverage.signals(session, org_id, candidate_id)
    where = set(lives) or {c for c, _ in works}
    return bool(where) and not (where & countries)


# --- stage 3: progress per company, exhaustion, snowball ---------------------------------------------------------------


def results_for(company: Company | None, rules_: dict[str, Any]) -> int:
    """How many profiles one search at a company asks for: about a quarter of its staff, 10 to `max_results` (50).
    Replies take time, so a deeper list per search helps; a small company is never padded with look-alikes (a test
    on 2026-10-13: all 25 results of "software engineer at Omnea", 219 staff, really worked there)."""
    employees = ((company.exa_profile or {}).get("employees") if company is not None else None) or 0
    top = int(rules_.get("max_results", RULES["max_results"]))
    return 25 if not employees else max(10, min(top, employees // 4))


def search_cost(results: int) -> float:
    """Exa's price for one search: $0.007 with up to 10 results, $0.001 for each one beyond."""
    return 0.007 + 0.001 * max(0, results - 10)


def variants_for(p: SourcingPlan, company: Company | None) -> list[str]:
    out = list(p.role_variants or [])[:3]
    employees = ((company.exa_profile or {}).get("employees") if company is not None else None) or 0
    if employees > 1000 and out:
        out.append(f"senior {out[0]}")
    return out


def relevant_now(session: Session, job_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """search id -> the strong suggestions it found (it was their first finder), as they stand now. Most people become
    strong only when their career reading arrives, after the run: counted when they were found, every marketing search
    read 0 while Safilo's three had found 15 strong people, and Safilo was rested as exhausted (2026-10-19)."""
    from sqlalchemy import func

    from maindscout.db.models import Candidate, SourcingHit

    rows = session.execute(select(SourcingHit.query_id, func.count()).join(
        CandidateJob, (CandidateJob.job_id == SourcingHit.job_id) & (CandidateJob.candidate_id == SourcingHit.candidate_id)).join(
        Candidate, Candidate.id == SourcingHit.candidate_id).where(
        SourcingHit.job_id == job_id, SourcingHit.query_id.is_not(None), CandidateJob.triage_band == "priority",
        Candidate.do_not_contact_at.is_(None)).group_by(SourcingHit.query_id)).all()
    return {qid: n for qid, n in rows}


def company_state(session: Session, job_id: uuid.UUID, p: SourcingPlan) -> dict[str, dict[str, Any]]:
    """company id -> what its searches brought for this role, and whether it is exhausted: every title variant
    searched and the last `exhausted_after` searches brought no new relevant person, or most of what it returns is
    already known."""
    r = rules(p)
    out: dict[str, dict[str, Any]] = {}
    rows = list(session.scalars(select(SourcingQuery).where(SourcingQuery.job_id == job_id, SourcingQuery.company_id.is_not(None),
                                                            SourcingQuery.channel == "exa_people").order_by(SourcingQuery.last_run_at)))
    live = relevant_now(session, job_id)
    for q in rows:
        s = out.setdefault(str(q.company_id), {"searches": 0, "results": 0, "known": 0, "relevant": 0, "texts": {}, "recent": [],
                                               "last_run_at": None})
        s["searches"] += q.runs or 0
        s["results"] += q.results or 0
        s["known"] += q.known or 0
        s["relevant"] += live.get(q.id, 0)
        s["texts"][q.text.lower()] = q.last_run_at
        s["recent"].append(live.get(q.id, 0))
        s["last_run_at"] = q.last_run_at
    by_id = {t.get("company_id"): t for t in p.targets}
    for cid, s in out.items():
        t = by_id.get(cid) or {}
        c = None
        try:
            c = session.get(Company, uuid.UUID(cid))
        except ValueError:
            pass
        name = t.get("name") or (c.name if c else "")
        wanted = {f"{v} at {name}".lower() for v in variants_for(p, c)}
        all_done = wanted <= set(s["texts"])
        quiet = len(s["recent"]) >= r["exhausted_after"] and sum(s["recent"][-r["exhausted_after"]:]) == 0
        mostly_known = s["results"] >= 5 and s["known"] / max(s["results"], 1) >= r["known_share"]
        s["exhausted"] = bool(all_done and (quiet or mostly_known)) or (all_done and s["results"] == 0)
        s["texts"] = {k: (v.isoformat() if v else None) for k, v in s["texts"].items()}
        s["last_run_at"] = s["last_run_at"].isoformat() if s["last_run_at"] else None
    return out


def next_searches(session: Session, job: Job, p: SourcingPlan, releasing: set[str], limits: dict[str, str]) -> list[dict[str, Any]]:
    """This run's searches: the next batch of companies (in tier order, pinned and releasing first), each with its
    title variants not yet searched; an exhausted company again only after `recheck_days` or new release news.
    Country-wide searches only when the owner opened them (a widening step)."""
    r = rules(p)
    state = company_state(session, job.id, p)
    open_groups = set(p.open_tiers or ["A", "B"])
    order = {t: i for i, t in enumerate(("named", "manual", "feeder", "release", "known", "peer", "snowball", "adjacent", "feeder_large"))}
    targets = sorted((t for t in p.targets if not t.get("removed") and group_of(t) in open_groups and t.get("company_id")
                      and not limits.get(t["company_id"])),
                     key=lambda t: (not t.get("pinned"), t["company_id"] not in releasing, group_of(t), order.get(t.get("tier"), 9)))
    now = _now()
    out: list[dict[str, Any]] = []
    used = 0
    countries = set(p.countries or [])
    avoid_ids, avoid_kinds = not_from(session, job)
    lux = luxury(session, job)
    from maindscout.api.process import client_context

    staff, wide = client_context(session, job)["staff"], "C" in open_groups
    for t in targets:
        s = state.get(t["company_id"])
        if t["company_id"] in avoid_ids:
            continue  # the hiring profile says not from here
        company = session.get(Company, uuid.UUID(t["company_id"]))
        mine = t.get("tier") in ("named", "manual")  # a company the owner or hiring manager named is always searched
        if not t.get("pinned") and not fit(session, company, countries, avoid_kinds, lux, None if mine else staff, wide)["searched"]:
            continue  # shut down, its team works only outside the role's countries, or a kind the profile does not want
        if s and s["exhausted"]:
            last = datetime.fromisoformat(s["last_run_at"]) if s["last_run_at"] else None
            if last and now - last < timedelta(days=r["recheck_days"]) and t["company_id"] not in releasing:
                continue
        pending = []
        for v in variants_for(p, company):
            text = f"{v} at {t['name']}"
            done = (s or {}).get("texts", {}).get(text.lower())
            if done and now - datetime.fromisoformat(done) < autosource.QUERY_COOLDOWN:
                continue
            pending.append(text)
        if not pending:
            continue
        used += 1
        if used > r["batch"]:
            break
        for text in pending:
            out.append({"text": text, "target": t["name"], "company_id": t["company_id"], "tier": t.get("tier"),
                        "group": group_of(t), "country": t.get("country") or (p.countries[0] if p.countries else None),
                        "results": results_for(company, r)})
    if "market" in open_groups:
        for v in (p.role_variants or [])[:3]:
            for c in (p.countries or [None])[:3]:
                out.append({"text": f"{v} in {geo.name_of(c)}" if c else v, "target": None, "company_id": None,
                            "tier": "market", "group": "market", "country": c, "results": MARKET_RESULTS})
    return out


def snowball(session: Session, org_id: uuid.UUID, job: Job, caller, report: dict[str, Any], task_id=None) -> int:
    """After a run: earlier employers shared by two or more strong people for this role become targets (tier B);
    a company that has produced three or more strong suggestions gets its own find-similar (once)."""
    p = autosource.current_plan(session, job.id)
    if p is None:
        return 0
    limits = autosource.off_limits(session, org_id)
    strong = [cid for cid, in session.execute(select(CandidateJob.candidate_id).join(Candidate, Candidate.id == CandidateJob.candidate_id).where(
        CandidateJob.job_id == job.id, CandidateJob.triage_band == "priority", Candidate.do_not_contact_at.is_(None)))]
    counts: Counter = Counter()
    for cid in strong:
        past = {(c.approved_view or c.payload).get("company", {}).get("company_id") for c in session.scalars(select(Claim).where(
            Claim.org_id == org_id, Claim.subject_id == cid, Claim.claim_type == "CareerStepClaim", Claim.status.in_(LIVE),
            Claim.valid_to.is_not(None)))}
        counts.update(c for c in past if c)
    targets = [dict(t) for t in p.targets]
    have = {t.get("company_id") for t in targets} | {str(job.hiring_company_id)}
    added = []
    for company_id, n in counts.most_common():
        if n < 2 or company_id in have or limits.get(company_id):
            continue
        c = companies.canonical(session, session.get(Company, uuid.UUID(company_id)))
        if c is None or str(c.id) in have:
            continue
        targets.append(_target(c, "snowball", [f"earlier employer of {n} strong people for this role"], "snowball"))
        have.add(str(c.id))
        added.append(c.name)
    state = company_state(session, job.id, p)
    for t in targets:
        s = state.get(t.get("company_id") or "")
        if not s or s["relevant"] < 3 or t.get("similar_done") or autosource._budget_left(session, org_id, job, p):
            continue
        c = session.get(Company, uuid.UUID(t["company_id"]))
        new = _peers(session, org_id, job, c, caller, have, f"like {c.name}, which produced {s['relevant']} strong suggestions", 5, task_id)
        targets += new
        added += [x["name"] for x in new]
        t["similar_done"] = True
    report["snowball"] = added
    if added or any(t.get("similar_done") for t in targets) != any(t.get("similar_done") for t in p.targets):
        autosource.update_plan(session, org_id, job.id, "snowball", targets=targets)
    return len(added)


# --- stage 4: widening -------------------------------------------------------------------------------------------------


def _must_have_numbers(session: Session, org_id: uuid.UUID, job: Job) -> list[dict[str, Any]]:
    """For each must-have, how many more people on the desk would meet the others if it were dropped."""
    from maindscout.api.sourcing import query_tokens
    from maindscout.intelligence.triage import supports

    tokens = query_tokens(session, job)
    if len(tokens) < 2:
        return []
    meets_all, without = 0, Counter()
    for person in session.scalars(select(Candidate).where(Candidate.org_id == org_id, Candidate.merged_into_id.is_(None),
                                                         Candidate.archived_at.is_(None))):
        claims = list(session.scalars(select(Claim).where(Claim.subject_id == person.id, Claim.status.in_(LIVE),
                                                          Claim.claim_type.in_(("SkillClaim", "CareerStepClaim")))))
        skills = [c.payload["normalized_skill"] for c in claims if c.claim_type == "SkillClaim"]
        titles = [c.payload.get("title_raw", "") for c in claims if c.claim_type == "CareerStepClaim"]
        has = {t for t in tokens if supports(t, skills, titles)}
        if has == set(tokens):
            meets_all += 1
        elif len(has) == len(tokens) - 1:
            without[(set(tokens) - has).pop()] += 1
    return [{"must_have": t, "more_on_desk": without[t]} for t in tokens if without[t]]


def widening(session: Session, org_id: uuid.UUID, job: Job, p: SourcingPlan) -> dict[str, Any] | None:
    """A widening proposal with numbers, or None. It appears when the open tiers are exhausted, the role is short of
    its target, and recent searches bring few relevant people. The owner decides."""
    r = rules(p)
    limits = autosource.off_limits(session, org_id)
    open_groups = set(p.open_tiers or ["A", "B"])
    state = company_state(session, job.id, p)
    countries = set(p.countries or [])
    live = [t for t in p.targets if not t.get("removed") and group_of(t) in open_groups and t.get("company_id")
            and not limits.get(t["company_id"])
            and (t.get("pinned") or fit(session, session.get(Company, uuid.UUID(t["company_id"])), countries, None,
                                         luxury(session, job))["searched"])]
    if autosource.strong_waiting(session, job.id) >= p.target:
        return None
    if not live:
        options = [{"option": "open_tier", "value": g, "text": f"Open tier {g}: {n} companies"}
                   for g in GROUPS if g not in open_groups
                   for n in [sum(1 for t in p.targets if not t.get("removed") and group_of(t) == g)] if n]
        if "market" not in open_groups:
            options.append({"option": "market", "value": None, "text": "Search the market by title in the role's countries"})
        return {"why": "No target companies to search in the open tiers: build the strategy, add companies, or widen.",
                "options": options, "empty": True}
    if not all((state.get(t["company_id"]) or {}).get("exhausted") for t in live):
        return None
    recent = list(session.scalars(select(SourcingQuery).where(SourcingQuery.job_id == job.id, SourcingQuery.channel == "exa_people",
                                                              SourcingQuery.last_run_at.is_not(None))
                                  .order_by(SourcingQuery.last_run_at.desc()).limit(r["yield_window"])))
    # Everything open is exhausted and the role is short: there is nothing left to search, so the owner is always asked,
    # whatever the recent yield (it is shown, to help the choice).
    live = relevant_now(session, job.id)
    rate = sum(live.get(q.id, 0) for q in recent) / len(recent) if recent else 0.0
    options = []
    closed = [g for g in GROUPS if g not in open_groups]
    if closed:
        n = sum(1 for t in p.targets if not t.get("removed") and group_of(t) == closed[0])
        options.append({"option": "open_tier", "value": closed[0],
                        "text": f"Open tier {closed[0]}: {n} {'company' if n == 1 else 'companies'}" + ("" if n else " (add some first)")})
    from maindscout.api.marketmap import FAMILY_TITLES

    from maindscout.api.search import job_filters

    have = {v.lower() for v in p.role_variants}
    family = job_filters(session, job)[0].family
    extra = [t for t in FAMILY_TITLES.get(family or "", []) if t.lower() not in have][:3]  # the role's own field only
    if extra:
        options.append({"option": "titles", "value": extra, "text": "Widen the titles: " + ", ".join(extra)})
    team = [geo.country_in(c["country"]) for c in ((p.dna or {}).get("company") or {}).get("team_countries") or []]
    more = [c for c in dict.fromkeys(team) if c and c not in (p.countries or [])]
    options.append({"option": "country", "value": more[:1], "text": f"Add a country{': ' + geo.name_of(more[0]) if more else ''}"})
    for m in _must_have_numbers(session, org_id, job):
        options.append({"option": "must_have", "value": m["must_have"],
                        "text": f"Dropping the must-have '{m['must_have']}' finds about {m['more_on_desk']} more on the desk (change it on the hiring profile)"})
    if "market" not in open_groups:
        options.append({"option": "market", "value": None, "text": "Last: search the market by title in the role's countries"})
    searched = sum(s["searches"] for s in state.values())
    relevant = sum(s["relevant"] for s in state.values())
    return {"why": f"Tiers {', '.join(sorted(g for g in open_groups if g in GROUPS))} are exhausted: {len(live)} companies, "
                   f"{searched} searches, {relevant} relevant found ({rate:.1f} per search lately); "
                   f"{autosource.strong_waiting(session, job.id)} of {p.target} strong suggestions waiting.", "options": options}


def widen(session: Session, org_id: uuid.UUID, job_id: uuid.UUID, actor: str, option: str, value: Any = None) -> SourcingPlan:
    """The owner's choice from a widening proposal, as a new plan version."""
    p = autosource.plan(session, org_id, job_id, actor)
    if option == "open_tier":
        if value not in GROUPS:
            raise autosource.SourcingEngineError("open_tier takes A, B or C")
        return autosource.update_plan(session, org_id, job_id, actor, open_tiers=list(dict.fromkeys([*p.open_tiers, value])))
    if option == "market":
        return autosource.update_plan(session, org_id, job_id, actor, open_tiers=list(dict.fromkeys([*p.open_tiers, "market"])))
    if option == "titles":
        titles = [value] if isinstance(value, str) else list(value or [])
        return autosource.update_plan(session, org_id, job_id, actor, role_variants=[*p.role_variants, *titles][:6])
    if option == "country":
        codes = [value] if isinstance(value, str) else list(value or [])
        codes = [c.upper() for c in codes if isinstance(c, str) and len(c) == 2]
        if not codes:
            raise autosource.SourcingEngineError("Say which country (a two-letter code)")
        from maindscout.api import hiring

        hiring.set_residence(session, org_id, job_id, list(dict.fromkeys([*p.countries, *codes])), actor)  # the one place
        return autosource.current_plan(session, job_id)
    raise autosource.SourcingEngineError("option must be open_tier, titles, country or market (a must-have is changed on the hiring profile)")
