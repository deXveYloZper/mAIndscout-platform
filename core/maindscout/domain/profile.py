"""Career profile: what a career shows, dimension by dimension, decided by code from facts. Pure: no database, no model.

Every dimension says what it found, in words, with the facts it rests on. There is no overall number. The overall
reading (strong / solid / developing / unclear) is composed from the dimensions by visible rules, and is "unclear"
when too little is known. Contracting is never a weakness: contractors are read against contractor norms.
Never personality, culture or "fit" (owner's rule, 2026-10-03).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from statistics import median
from typing import Any

RUBRIC_VERSION = "2026-10-04.3"

ROLE_FAMILIES = [
    "software_engineering", "data_ml", "devops_infrastructure", "security", "qa_testing", "embedded_hardware",
    "gis_remote_sensing", "research_science", "engineering_management", "product_management", "design", "it_support",
    "sales", "marketing", "customer_success", "operations", "finance", "hr_recruiting", "business_consulting",
    "hospitality", "retail", "education", "healthcare", "other",
]
FAMILY_LABEL = {f: f.replace("_", " ") for f in ROLE_FAMILIES} | {
    "data_ml": "data / ML", "devops_infrastructure": "DevOps / infrastructure", "qa_testing": "QA / testing",
    "embedded_hardware": "embedded / hardware", "gis_remote_sensing": "GIS / remote sensing",
    "research_science": "research / science", "it_support": "IT support", "hr_recruiting": "HR / recruiting"}
LEVELS = ["intern", "junior", "mid", "senior", "lead", "principal", "manager", "head", "director", "executive", "founder"]
# Rank on one ladder for progression; founder is read separately.
LEVEL_RANK = {"intern": 0, "junior": 1, "mid": 2, "senior": 3, "lead": 4, "manager": 4, "principal": 5, "head": 5,
              "director": 6, "executive": 7}
SIGNALS = ["founder", "first_hire", "people_manager", "team_lead", "promotion"]
# Industries the work served: a fixed list, so years per domain can be counted and compared. Never technologies.
DOMAINS = [
    "fintech", "payments", "banking", "insurance", "crypto / web3", "e-commerce", "retail", "telecommunications",
    "media / entertainment", "gaming / gambling", "healthcare", "pharma / biotech", "energy / utilities",
    "environment / water", "climate / sustainability", "aerospace / defence", "space / earth observation",
    "automotive / mobility", "logistics / supply chain", "procurement", "construction / property", "public sector",
    "education", "travel / hospitality", "marketing / advertising", "it services / consulting", "enterprise software",
    "cybersecurity", "ai / data", "agriculture / food", "manufacturing / industrial", "hr / recruiting", "legal",
    "research / academia", "non-profit", "other",
]
# Kinds of work that build on each other count together as relevant experience (a GIS data scientist who becomes a
# data scientist, an engineer who becomes a team lead). A restaurant job never counts towards software.
GROUPS = {
    "engineering": {"software_engineering", "data_ml", "devops_infrastructure", "security", "qa_testing", "embedded_hardware",
                    "gis_remote_sensing", "research_science", "engineering_management"},
    "product_design": {"product_management", "design"},
    "commercial": {"sales", "marketing", "customer_success", "business_consulting"},
    "operations": {"operations", "it_support", "finance", "hr_recruiting"},
}
GROUP_LABEL = {"engineering": "technical work", "product_design": "product and design", "commercial": "commercial work",
               "operations": "operations"}


def group_of(family: str | None) -> str | None:
    return next((g for g, fams in GROUPS.items() if family in fams), family)

CONTRACT = ("contract", "consulting")
NOT_EXPERIENCE = ("internship", "side")
YEAR = 365.25


@dataclass
class CompanyFacts:
    kind: str | None = None  # product | consultancy | outsourcing | agency | public_sector | non_profit | other
    founded: date | None = None
    rounds: list[tuple[str, date | None]] = field(default_factory=list)  # (stage, date)
    team_min: int | None = None
    team_max: int | None = None  # the top of a published range ("51-200"), when there is one
    status: str | None = None  # active | acquired | merged | shut_down | public
    domains: list[str] = field(default_factory=list)


@dataclass
class Stint:
    id: str  # career claim id (evidence)
    company: str
    title: str
    start: date | None
    end: date | None  # None = current
    employment: str = "unknown"
    company_key: str | None = None  # canonical company id, or the raw name
    family: str | None = None
    level: str | None = None
    domains: list[str] = field(default_factory=list)  # from the step's classification
    signals: list[str] = field(default_factory=list)
    facts: CompanyFacts | None = None
    self_employed: bool = False
    precise: bool = True  # dates known to the month; "2017 - 2018" is not precise enough to call a stay short


@dataclass
class Education:
    id: str
    institution: str
    level: str | None = None
    field: str | None = None
    end: date | None = None
    rank: int | None = None
    rank_band: str | None = None
    rank_source: str | None = None


def _months(a: date, b: date) -> float:
    return max(0.0, (b - a).days / (YEAR / 12))


def _years(intervals: list[tuple[date, date]]) -> float:
    """Total years covered by intervals, overlaps counted once."""
    total, cur_s, cur_e = 0.0, None, None
    for s, e in sorted(intervals):
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += (cur_e - cur_s).days
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)
    if cur_e is not None:
        total += (cur_e - cur_s).days
    return total / YEAR


def _span(s: Stint, as_of: date) -> tuple[date, date] | None:
    if s.start is None:
        return None
    end = s.end or as_of
    return (s.start, end) if end >= s.start else None


def _dim(label: str, reason: str, evidence: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    return {"label": label, "reason": reason, "evidence": evidence or [], **extra}


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _y(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".") + (" year" if round(x, 1) == 1 else " years")


# --- dimensions -----------------------------------------------------------------------------------


def relevant_years(stints: list[Stint], as_of: date) -> dict[str, Any]:
    by_family: dict[str, list[tuple[date, date]]] = {}
    ids: dict[str, list[str]] = {}
    for s in stints:
        span = _span(s, as_of)
        if span is None or not s.family or s.employment in NOT_EXPERIENCE:
            continue
        by_family.setdefault(s.family, []).append(span)
        ids.setdefault(s.family, []).append(s.id)
    years = {f: round(_years(v), 1) for f, v in by_family.items()}
    if not years:
        return _dim("unknown", "No dated jobs with a known kind of work.", years={})
    # The main family is the one of the most recent dated job (what they do now), not the longest one.
    dated = sorted((s for s in stints if s.start and s.family and s.employment not in NOT_EXPERIENCE), key=lambda s: s.start)
    main = dated[-1].family
    group = group_of(main)
    related = [f for f in by_family if group_of(f) == group]
    group_years = round(_years([span for f in related for span in by_family[f]]), 1)
    reason = f"{_y(years[main])} in {FAMILY_LABEL[main]}"
    if len(related) > 1:
        reason += f"; {_y(group_years)} of {GROUP_LABEL.get(group, FAMILY_LABEL[main])} in all, including " + ", ".join(
            f"{FAMILY_LABEL[f]} ({_y(years[f])})" for f in sorted(related, key=lambda f: -years[f]) if f != main)
    other = {f: y for f, y in years.items() if f not in related and y >= 0.5}
    if other:
        reason += "; also " + ", ".join(f"{_y(y)} in {FAMILY_LABEL[f]}" for f, y in sorted(other.items(), key=lambda kv: -kv[1]))
    evidence = [i for f in related for i in ids[f]]
    return _dim(FAMILY_LABEL[main], reason + ".", evidence, years=years, main=main, group=group,
                family_years=years[main], main_years=group_years)


def level_by_years(y: float) -> str:
    return "junior" if y < 2 else "mid" if y < 5 else "senior"


def seniority(stints: list[Stint], ry: dict[str, Any], as_of: date) -> dict[str, Any]:
    main = ry.get("main")
    if not main:
        return _dim("unknown", "Relevant years unknown.")
    by_years = level_by_years(ry["main_years"])
    recent = [s for s in stints if group_of(s.family) == ry.get("group") and s.level in LEVEL_RANK
              and _span(s, as_of) and _span(s, as_of)[1].year >= as_of.year - 5]
    top = max(recent, key=lambda s: LEVEL_RANK[s.level], default=None)
    if top is None:
        return _dim(by_years, f"{_cap(by_years)} by years ({_y(ry['main_years'])}); titles do not show a level.", ry["evidence"], by_years=by_years)
    # Titles held decide; years are shown beside them (plan 4.3: "level by rubric, adjusted by titles held").
    label = top.level
    reason = f"Highest recent title: {top.title} ({top.level}); {_y(ry['main_years'])} would suggest {by_years}."
    if top.level == by_years:
        reason = f"Highest recent title: {top.title} ({top.level}), in line with {_y(ry['main_years'])}."
    return _dim(label, reason, [top.id], by_years=by_years, by_title=top.level)


def progression(stints: list[Stint], as_of: date) -> dict[str, Any]:
    ranked = sorted((s for s in stints if s.start and s.level in LEVEL_RANK and s.employment not in ("side",)), key=lambda s: s.start)
    promotions = []
    for a, b in zip(ranked, ranked[1:]):
        if a.company_key and a.company_key == b.company_key and LEVEL_RANK[b.level] > LEVEL_RANK[a.level]:
            promotions.append((a, b))
    promotions += [(s, s) for s in stints if "promotion" in s.signals and all(s is not p[1] for p in promotions)]
    if len(ranked) < 2 and not promotions:
        return _dim("unclear", "Too few jobs with a clear level to see a direction.")
    current = [s for s in ranked if s.end is None]
    # Where they are now: the highest role they hold today (a side consultancy next to a senior job is not a step down).
    first, last = ranked[0], max(current, key=lambda s: LEVEL_RANK[s.level]) if current else ranked[-1]
    rise = LEVEL_RANK[last.level] - LEVEL_RANK[first.level]
    parts = []
    if promotions:
        parts.append("promoted at " + ", ".join(sorted({b.company for _, b in promotions})))
    parts.append(f"from {first.level} ({first.start.year}) to {last.level} ({last.start.year})")
    if promotions or rise > 0:
        label = "rising"
    elif rise == 0:
        label = "steady"
    else:
        label = "unclear"
        parts.append("the latest title is below an earlier one (a change of track or of company size is common)")
    ev = [s.id for pair in promotions for s in pair] or [first.id, last.id]
    return _dim(label, _cap("; ".join(parts)) + ".", sorted(set(ev)), promotions=len(promotions))


def _tenures(stints: list[Stint], as_of: date) -> list[dict[str, Any]]:
    """One tenure per employer: consecutive or overlapping roles at the same company are one stay (a promotion is not a move)."""
    out: list[dict[str, Any]] = []
    for s in sorted(stints, key=lambda s: s.start):
        key = s.company_key or s.company.lower()
        end = s.end or as_of
        same = next((t for t in out if t["key"] == key and (s.start - t["end"]).days <= 92), None)
        if same:
            same["end"], same["current"] = max(same["end"], end), same["current"] or s.end is None
            same["ids"].append(s.id)
            same["precise"] = same["precise"] and s.precise
            same["softened"] = same["softened"] or bool(s.facts and s.facts.status in ("shut_down", "acquired", "merged"))
        else:
            out.append({"key": key, "company": s.company, "start": s.start, "end": end, "current": s.end is None, "ids": [s.id],
                        "precise": s.precise, "softened": bool(s.facts and s.facts.status in ("shut_down", "acquired", "merged"))})
    return out


def stability(stints: list[Stint], as_of: date, group: str | None = None) -> dict[str, Any]:
    """Employees and contractors are read separately; contracting is never a weakness in itself. Jobs before the
    career started (in another kind of work, e.g. a student's shop job) do not count."""
    window = as_of.replace(year=as_of.year - 10)
    career = [s for s in stints if s.start and s.employment not in NOT_EXPERIENCE]
    first_main = min((s.start for s in career if group and group_of(s.family) == group), default=None)
    if first_main:
        career = [s for s in career if group_of(s.family) == group or (s.end or as_of) > first_main]
    recent = [s for s in career if (s.end or as_of) >= window]
    employed = [s for s in recent if s.employment not in CONTRACT and not s.self_employed]
    contract = [s for s in recent if s.employment in CONTRACT or s.self_employed]
    out: dict[str, Any] = {}

    if employed:
        stays = _tenures(employed, as_of)
        done = [t for t in stays if not t["current"]]
        current = [t for t in stays if t["current"]]
        months = lambda t: _months(t["start"], t["end"])  # noqa: E731
        softened = [t for t in done if months(t) < 12 and t["softened"]]
        counted = [t for t in done if t not in softened and t["precise"]]  # "2017 - 2018" cannot say how long
        short = [t for t in counted if months(t) < 12]
        brief = [t for t in counted if months(t) < 18]
        longest_current = max((months(t) for t in current), default=0)
        if len(counted) < 2:
            if longest_current >= 30:
                label = "long_tenures"
                reason = f"{len(stays)} employer{'s' if len(stays) != 1 else ''} in 10 years; in the current job for {_y(longest_current / 12)}."
            else:
                label, reason = "unclear", "Too few finished jobs in the last 10 years to see a pattern."
        else:
            med = median(months(t) for t in counted)
            share = len(short) / len(counted)
            if share <= 0.25 and (med >= 30 or longest_current >= 48):
                label = "long_tenures"
            elif len(counted) >= 3 and (med < 18 or share >= 0.5):
                label = "frequent_moves"
            else:
                label = "mixed"
            reason = (f"{len(stays)} employer{'s' if len(stays) != 1 else ''} in 10 years; typical stay {_y(med / 12)}; "
                      f"{len(short)} of {len(counted)} finished stays under a year")
            if longest_current >= 12:
                reason += f"; {_y(longest_current / 12)} in the current job"
        if softened:
            reason = reason.rstrip(".") + f" (not counting {', '.join(t['company'] for t in softened)}: the company shut down or was sold)."
        elif not reason.endswith("."):
            reason += "."
        out["employed"] = _dim(label, reason, [i for t in stays for i in t["ids"]], short=[t["ids"][-1] for t in short], brief=[t["ids"][-1] for t in brief],
                               softened=[t["ids"][-1] for t in softened])
    if contract:
        lengths = [_months(s.start, s.end or as_of) for s in contract]
        med = median(lengths)
        label = "long_engagements" if med >= 12 else "short_engagements" if med < 6 else "mixed_engagements"
        years = _years([_span(s, as_of) for s in contract if _span(s, as_of)])
        out["contract"] = _dim(label, f"{len(contract)} contract engagement{'s' if len(contract) != 1 else ''}, {_y(years)} contracting; typical engagement {_y(med / 12)}.",
                               [s.id for s in contract], years=round(years, 1))
    if not out:
        return _dim("unknown", "No dated jobs in the last 10 years.")
    main = out.get("employed") if out.get("employed") and (not contract or len(employed) >= len(contract)) else out.get("contract")
    return {**main, "parts": out}


def stint_category(s: Stint) -> str:
    """What kind of employer it was when they joined. A funding round more than 8 years before they joined says
    nothing about the company they joined; then its size decides."""
    f = s.facts
    if f is None:
        return "unknown"
    if f.kind in ("consultancy", "outsourcing"):
        return "consultancy"
    if f.kind in ("agency", "public_sector", "non_profit"):
        return f.kind
    stage = None
    for st, d in sorted((r for r in f.rounds if r[1] and r[0] not in ("acquisition", "debt", "grant", "other")), key=lambda r: r[1]):
        if s.start and d <= s.start and (s.start - d).days <= 8 * YEAR:
            stage = st
    if f.status == "public" or stage == "ipo":
        return "large"
    if stage in ("pre_seed", "seed", "series_a"):
        return "startup" if f.team_min is None or f.team_min <= 1000 else "scaleup"
    if stage in ("series_b", "series_c", "series_d", "series_e_plus", "growth"):
        return "scaleup" if f.team_min is None or f.team_min <= 5000 else "large"
    if f.team_min is not None:
        return "startup" if f.team_min <= 50 else "scaleup" if f.team_min <= 1000 else "large"
    if f.founded and s.start and 0 <= (s.start - f.founded).days <= 5 * YEAR:
        return "startup"
    return "unknown"


CATEGORY_LABEL = {"startup": "start-ups", "scaleup": "scale-ups", "large": "large companies", "consultancy": "consultancies / outsourcers",
                  "agency": "agencies", "public_sector": "public sector", "non_profit": "non-profits", "unknown": "not known"}


def employer_mix(stints: list[Stint], as_of: date) -> dict[str, Any]:
    window = as_of.replace(year=as_of.year - 10)
    months: dict[str, float] = {}
    ids: dict[str, list[str]] = {}
    for s in stints:
        span = _span(s, as_of)
        if span is None or s.employment in NOT_EXPERIENCE:
            continue
        start = max(span[0], window)
        if span[1] <= start:
            continue
        cat = stint_category(s)
        months[cat] = months.get(cat, 0) + _months(start, span[1])
        ids.setdefault(cat, []).append(s.id)
    known = {k: v for k, v in months.items() if k != "unknown"}
    if not known:
        return _dim("unknown", "Employer kinds not known yet (company research pending or not found).")
    total = sum(months.values())
    top = max(known, key=known.get)
    parts = [f"{_y(v / 12)} at {CATEGORY_LABEL[k]}" for k, v in sorted(months.items(), key=lambda kv: -kv[1])]
    label = top if known[top] / total >= 0.5 else "mixed"
    return _dim(label, "Last 10 years: " + ", ".join(parts) + ".", ids.get(top, []), years={k: round(v / 12, 1) for k, v in months.items()})


def early_joiner(stints: list[Stint]) -> dict[str, Any]:
    early = []
    for s in stints:
        if s.start and s.facts and s.facts.founded and 0 <= (s.start - s.facts.founded).days <= 2 * YEAR and s.employment not in NOT_EXPERIENCE:
            early.append((s, round(_months(s.facts.founded, s.start))))
    if not early:
        return _dim("no", "No job started within two years of the company's founding (where the founding date is known).")
    words = "; ".join(f"joined {s.company} {m} months after it was founded" for s, m in early)
    return _dim("yes", words[0].upper() + words[1:] + ".", [s.id for s, _ in early])


def domain_exposure(stints: list[Stint], as_of: date) -> dict[str, Any]:
    spans: dict[str, list[tuple[date, date]]] = {}
    ids: dict[str, list[str]] = {}
    for s in stints:
        span = _span(s, as_of)
        if span is None or s.employment in NOT_EXPERIENCE:
            continue
        domains = s.domains[:1]  # the main industry the work served (fixed list); secondary ones are not counted
        for d in {d.strip().lower().replace("_", " ") for d in domains if d}:
            spans.setdefault(d, []).append(span)
            ids.setdefault(d, []).append(s.id)
    years = {d: round(_years(v), 1) for d, v in spans.items()}
    if not years:
        return _dim("unknown", "No domains known yet.")
    top = sorted(years.items(), key=lambda kv: -kv[1])
    return _dim(top[0][0], "Most time in " + ", ".join(f"{d} ({_y(y)})" for d, y in top[:4]) + ".", ids[top[0][0]], years=years)


def contractor(stints: list[Stint], as_of: date) -> dict[str, Any]:
    c = [s for s in stints if (s.employment in CONTRACT or s.self_employed) and _span(s, as_of)]
    if not c:
        return _dim("no", "No contract or freelance work stated.")
    years = _years([_span(s, as_of) for s in c])
    med = median(_months(*_span(s, as_of)) for s in c)
    own = [s for s in c if s.self_employed]
    reason = f"{_y(years)} contracting over {len(c)} engagement{'s' if len(c) != 1 else ''}, typically {_y(med / 12)} each"
    if own:
        reason += f"; self-employed ({', '.join(s.company for s in own)})"
    current = any(s.end is None for s in c)
    return _dim("current" if current else "past", reason + ".", [s.id for s in c], years=round(years, 1), typical_months=round(med, 1))


BAND_WORDS = {"top_50": "top 50", "51_100": "51-100", "101_200": "101-200", "201_500": "201-500", "501_plus": "501+",
              "not_ranked": "not ranked"}
EDU_RANK = {"doctorate": 4, "master": 3, "bachelor": 2, "associate": 1, "diploma": 1, "other": 0}


def education(items: list[Education]) -> dict[str, Any]:
    if not items:
        return _dim("unknown", "No education stated.")
    best = max(items, key=lambda e: (EDU_RANK.get(e.level or "other", 0), e.end or date.min))
    words = f"{_cap(best.level or 'degree')}{' in ' + best.field if best.field else ''}, {best.institution}"
    if best.rank_band:
        words += f" (ranked {BAND_WORDS.get(best.rank_band, best.rank_band)} in {best.rank_source or 'a world ranking'})"
    return _dim(best.level or "unknown", words + ".", [best.id], rank_band=best.rank_band)


def notable(stints: list[Stint], early: dict[str, Any], prog: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for s in stints:
        title = s.title.lower()
        if "founder" in s.signals or "founder" in title or s.level == "founder":
            out.append({"kind": "founder", "text": f"Founder or co-founder at {s.company}", "evidence": [s.id]})
        if "first_hire" in s.signals:
            out.append({"kind": "first_hire", "text": f"Among the first hires at {s.company}", "evidence": [s.id]})
        if "people_manager" in s.signals or s.level in ("manager", "head", "director"):
            out.append({"kind": "people_manager", "text": f"Managed people at {s.company}", "evidence": [s.id]})
        elif "team_lead" in s.signals or s.level == "lead":
            out.append({"kind": "team_lead", "text": f"Led a team at {s.company}", "evidence": [s.id]})
    if early["label"] == "yes":
        out.append({"kind": "early_joiner", "text": early["reason"].rstrip("."), "evidence": early["evidence"]})
    if prog.get("promotions"):
        out.append({"kind": "promotion", "text": prog["reason"].rstrip("."), "evidence": prog["evidence"]})
    seen, unique = set(), []
    for n in out:
        if (n["kind"], n["text"]) not in seen:  # two roles at one company: one line
            seen.add((n["kind"], n["text"]))
            unique.append(n)
    return unique


def reading(dims: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The overall reading, composed by visible rules. Never a number."""
    ry, stab, prog = dims["relevant_years"], dims["stability"], dims["progression"]
    known = [d for d in (ry, stab, prog) if d["label"] not in ("unknown", "unclear")]
    if ry["label"] == "unknown" or len(known) < 2:
        return _dim("unclear", "Too little is known to read this career: approve facts or ask.")
    years = ry["main_years"]
    family = GROUP_LABEL.get(ry["group"], FAMILY_LABEL[ry["main"]]) if ry["main_years"] > ry["family_years"] else FAMILY_LABEL[ry["main"]]
    steady = stab["label"] in ("long_tenures", "long_engagements")
    if years < 2:
        return _dim("developing", f"Under two years in {family}.")
    if years >= 5 and prog["label"] == "rising" and steady:
        return _dim("strong", f"{_y(years)} in {family}, rising, with {stab['label'].replace('_', ' ')}.")
    why = [f"{_y(years)} in {family}"]
    if prog["label"] != "rising":
        why.append(f"progression {prog['label']}")
    if not steady:
        why.append(stab["label"].replace("_", " "))
    return _dim("solid", ", ".join(why) + ".")


def questions(stints: list[Stint], dims: dict[str, dict[str, Any]], as_of: date) -> list[str]:
    """Questions for the call, from facts only. Never about personality, culture or 'fit'."""
    qs: list[str] = []
    stab = dims["stability"].get("parts", {})
    emp = stab.get("employed")
    by_id = {s.id: s for s in stints}
    moved = (emp or {}).get("brief") if (emp or {}).get("label") == "frequent_moves" else (emp or {}).get("short")
    if emp and emp["label"] in ("frequent_moves", "mixed") and moved:
        names = ", ".join(by_id[i].company for i in moved[:4])
        qs.append(f"What led to the short stays at {names}?")
    for i in (emp or {}).get("softened", []):
        s = by_id[i]
        qs.append(f"{s.company} shut down or was sold around their time there: what was their role at the end?")
    con = stab.get("contract")
    if con and con["label"] == "short_engagements":
        qs.append("Their contracts were mostly short: were they planned that way, and what did each deliver?")
    if dims["employer_mix"]["label"] == "consultancy":
        qs.append("Mostly consultancy work: which products did they own end to end, and for how long?")
    if dims["progression"]["label"] == "unclear" and dims["relevant_years"].get("main_years", 0) >= 5:
        qs.append("Titles do not show a clear direction: what was their scope and who did they report to in each role?")
    undated = [s for s in stints if s.start is None and s.employment not in NOT_EXPERIENCE]
    for s in undated[:2]:
        qs.append(f"The CV gives no dates for {s.title} at {s.company}: when was that?")
    dated = [] if undated else sorted((s for s in stints if s.start and s.employment not in NOT_EXPERIENCE), key=lambda s: s.start)
    reach = None
    for s in dated:
        end = s.end or as_of
        if reach and (s.start - reach).days > 183 and reach.year >= as_of.year - 10:
            qs.append(f"What were they doing between {reach.strftime('%b %Y')} and {s.start.strftime('%b %Y')}?")
        reach = max(reach or end, end)
    if dims["relevant_years"]["label"] == "unknown":
        qs.append("The CV does not make the kind of work clear: what did they actually do in their recent roles?")
    return qs


def summary(dims: dict[str, dict[str, Any]]) -> str:
    """One plain sentence built from the dimensions (no model, so nothing is invented)."""
    ry = dims["relevant_years"]
    if ry["label"] == "unknown":
        return "Not enough dated facts to describe this career yet."
    bits = [f"{_y(ry['family_years'])} in {FAMILY_LABEL[ry['main']]}"]
    if ry["main_years"] > ry["family_years"]:
        bits[0] += f" ({_y(ry['main_years'])} of {GROUP_LABEL.get(ry['group'], 'related work')})"
    if dims["seniority"]["label"] != "unknown":
        bits.append(dims["seniority"]["label"])
    if dims["employer_mix"]["label"] not in ("unknown", "mixed"):
        bits.append(f"mostly at {CATEGORY_LABEL[dims['employer_mix']['label']]}")
    if dims["domain_exposure"]["label"] != "unknown":
        bits.append(f"strongest domain {dims['domain_exposure']['label']}")
    if dims["stability"]["label"] not in ("unknown", "unclear"):
        bits.append(dims["stability"]["label"].replace("_", " "))
    if dims["progression"]["label"] == "rising":
        bits.append("rising")
    return _cap("; ".join(bits)) + "."


def build(stints: list[Stint], edu: list[Education], as_of: date) -> dict[str, Any]:
    ry = relevant_years(stints, as_of)
    dims: dict[str, dict[str, Any]] = {"relevant_years": ry}
    dims["seniority"] = seniority(stints, {**ry, "evidence": ry["evidence"]}, as_of)
    dims["progression"] = progression(stints, as_of)
    dims["stability"] = stability(stints, as_of, ry.get("group"))
    dims["employer_mix"] = employer_mix(stints, as_of)
    dims["early_joiner"] = early_joiner(stints)
    dims["domain_exposure"] = domain_exposure(stints, as_of)
    dims["contractor"] = contractor(stints, as_of)
    dims["education"] = education(edu)
    return {"dimensions": dims, "notable": notable(stints, dims["early_joiner"], dims["progression"]),
            "reading": reading(dims), "questions": questions(stints, dims, as_of), "summary": summary(dims),
            "rubric_version": RUBRIC_VERSION, "as_of": as_of.isoformat()}
