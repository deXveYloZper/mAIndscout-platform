"""Matching v2 (I5): a person's career profile against a job's hiring profile, requirement by requirement, then a
match tier composed by visible rules. Pure: no database, no model. Never a number, never a percentage.

Each requirement gets a verdict:
- strong   the profile or the file shows it;
- partial  part of it (a related kind of work, one level below, some years of the industry);
- gap      nothing shows it, or the facts speak against it;
- against  a "not wanted" requirement that the person meets;
- ask      only a conversation can settle it (where they live, visas, vague asks).

The tier (strong / possible / unlikely / unclear) comes from the RULES below, in order; every rule that fired is
reported with its reason. Where someone lives or their right to work is never a reason for "unlikely".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable

from maindscout.domain import specialism as specialism_mod
from maindscout.domain.profile import (FAMILY_LABEL, LEVEL_RANK, NOT_EXPERIENCE, Stint, employer_years, group_of, staff_words,
                                       years_at_size)

ENGINE_VERSION = "match-2026-10-26.1"  # a specialist role (CRM): a title saying that work counts as the role's field
MUST = ("must", "deal_breaker")

# The desk's rules, as data: id -> what it says. The order of evaluation is the order of this list.
RULES: list[dict[str, str]] = [
    {"id": "client_block", "text": "The client said no to this person: a wall at this client until a person lifts it."},
    {"id": "distinctive_must_missing", "text": "A must-have that decides the band has no evidence: do not submit."},
    {"id": "not_read", "text": "Clearly out for this role from the public profile alone (no title says the specialist work, or far too many years): not read, kept in the pool."},
    {"id": "too_senior", "text": "Many more years of work than the role's level: a no two years past its band, a reach one year past unless the match is excellent."},
    {"id": "distinctive_must_unproven", "text": "A must-have that decides the band is not on a public profile, but their title says the role's specialist work: possible, ask on the call."},
    {"id": "not_wanted", "text": "The person meets a requirement the hiring manager does not want."},
    {"id": "wants_otherwise", "text": "The job is what the person said they will not consider (a must, said on a call): unlikely."},
    {"id": "prefers_otherwise", "text": "The job is not what the person said they would prefer: a note for the call, never a reason on its own."},
    {"id": "fits_what_they_want", "text": "The job fits what the person said they want."},
    {"id": "substitution", "text": "A requirement the intake says can substitute for another is met, so that one counts as met."},
    {"id": "domain_over_seniority", "text": "A strong industry match outweighs one level below the level asked for."},
    {"id": "contractor_fit", "text": "A contract job and a contractor with long engagements: a strong plus."},
    {"id": "wrong_field", "text": "The role's kind of work is a must and the person works in another field altogether: unlikely."},
    {"id": "must_gaps", "text": "Two or more must-haves are gaps: unlikely; one: possible."},
    {"id": "partial_must", "text": "A must-have is only partly met (a related kind of work, a level below, fewer years): possible."},
    {"id": "too_little_known", "text": "Too little is known about the person to compare (no career profile yet): never Priority until it is read; otherwise the coarse band stands."},
    {"id": "too_big_a_move", "text": "A reach: their employer is 20 or more times the client's size, with no recent time at a company near the client's size and no step up."},
    {"id": "above_the_role", "text": "A reach: their level now is well above the role's (or at the role's seniority limit, or global or regional above it)."},
    {"id": "specialist", "text": "A specialist (CRM, media, merchandising...) for a role that asks for an all-round person: possible, not strong."},
    {"id": "strong_match", "text": "Every must-have is fully met or only needs asking, and at least half of the known strong-plus items are met."},
]
RULE_TEXT = {r["id"]: r["text"] for r in RULES}
TIER_BAND = {"strong": "priority", "possible": "review_later", "unlikely": "do_not_submit"}


@dataclass
class Verdict:
    requirement_id: str
    requirement: str
    kind: str
    strength: str
    verdict: str
    detail: str
    distinctive: bool = False


@dataclass
class Match:
    tier: str  # strong | possible | unlikely | unclear
    band: str | None  # None when the coarse band stands (unclear)
    reason: str  # stored as the pair's reason
    rows: list[Verdict] = field(default_factory=list)
    rules: list[dict[str, str]] = field(default_factory=list)  # [{id, text, detail}]

    def as_dict(self) -> dict[str, Any]:
        return {"tier": self.tier, "engine": ENGINE_VERSION, "rules": self.rules,
                "rows": [v.__dict__ for v in self.rows]}


# "likely" (their employer uses it, by its own advert) is partly met: it can lift a missing must-have to possible,
# never make a match strong on its own (owner, 2026-10-17).
GAP_TO_VERDICT = {"evidence": "strong", "likely": "partial", "missing": "gap", "conflict": "gap", "question": "ask"}


def _years(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".") + (" year" if round(x, 1) == 1 else " years")


def _role(p: dict[str, Any], profile: dict[str, Any], stints: list[Stint] | None = None,
          specialism: str | None = None) -> tuple[str, str]:
    ry, sen = profile["dimensions"]["relevant_years"], profile["dimensions"]["seniority"]
    if ry["label"] == "unknown":
        return "ask", "the kind of work is not clear from the CV"
    want, main = p.get("role_family"), ry["main"]
    parts, verdicts = [], []
    # A specialist role (CRM): a person whose recent title says that work does it, whatever family their career was
    # filed under (a CRM manager read as marketing, a Salesforce administrator read as IT support), owner 2026-10-22.
    said = next((s.title for s in sorted(stints or [], key=lambda s: s.end is not None)
                 if s.employment not in NOT_EXPERIENCE and (s.end is None or (date.today() - s.end).days <= 3 * 365)
                 and specialism_mod.title_says(specialism, s.title)), None)
    if said and not same_side(want, main):
        # The work, from another department: a Salesforce administrator in IT for a business-side CRM role that trains
        # stores and markets (owner, 2026-10-23: "people from IT has really nothing to do for this role").
        verdicts.append("partial")
        parts.append(f"{specialism_mod.broad_word(specialism)} work from {FAMILY_LABEL.get(main, main)} ({said}), "
                     f"not the {FAMILY_LABEL.get(want, want)} side")
    elif said:
        verdicts.append("strong")
        parts.append(f"works in {specialism_mod.broad_word(specialism)} ({said})")
    elif want == main:
        verdicts.append("strong")
        parts.append(f"works in {FAMILY_LABEL[main]}")
    elif want and group_of(want) == group_of(main) and group_of(want) != want:
        verdicts.append("partial")
        parts.append(f"works in {FAMILY_LABEL[main]}, related to {FAMILY_LABEL.get(want, want)}")
    else:
        verdicts.append("gap")
        parts.append(f"works in {FAMILY_LABEL[main]}, not {FAMILY_LABEL.get(want, want)}")
    level = p.get("level")
    if level in LEVEL_RANK and sen.get("label") in LEVEL_RANK:
        diff = LEVEL_RANK[sen["label"]] - LEVEL_RANK[level]
        if diff >= 0:
            verdicts.append("strong")
            parts.append(f"{sen['label']} by title")
        elif diff == -1:
            verdicts.append("level_one_below")
            parts.append(f"{sen['label']} by title, one below {level}")
        else:
            verdicts.append("gap")
            parts.append(f"{sen['label']} by title, well below {level}")
    if p.get("min_years") is not None:
        have = ry.get("main_years", 0)
        verdicts.append("strong" if have >= p["min_years"] else "partial" if have >= 0.75 * p["min_years"] else "gap")
        parts.append(f"{_years(have)} of related work against {p['min_years']:g} asked")
    if "gap" in verdicts:
        v = "gap"
    elif "level_one_below" in verdicts:
        v = "level_one_below"
    elif "partial" in verdicts:
        v = "partial"
    else:
        v = "strong"
    return v, "; ".join(parts)


# Kinds of employer in plain words. Without a funding round, size decides the kind (domain/profile.stint_category):
# up to 50 people is a start-up, up to 1,000 a scale-up, so an established 62-person brand reads as a scale-up. A size
# asked in people ("a small or mid-size brand") is its own range instead (min_staff / max_staff; profile.SIZE_BANDS).
KIND_WORDS = {"startup": "start-ups or small companies (up to 50 people)",
              "scaleup": "scale-ups or mid-size companies (51-1,000 people)", "large": "large companies",
              "consultancy": "consultancies", "agency": "agencies", "public_sector": "the public sector", "non_profit": "non-profits"}


def _relevant(family: str | None) -> Callable[[Stint], bool] | None:
    """The role's kind of work, and the work that builds on it (as relevant years count it). None: every job counts."""
    if not family:
        return None
    group = group_of(family)
    return lambda s: s.family is None or group_of(s.family) == group


# A size alone asks about companies like a client: agencies, consultancies, public bodies and non-profits do not count
# unless the requirement names them (the start-up / scale-up reading never counted them either; a PR agency and a
# fashion trade body read as "small-brand experience" in the what-if of 2026-10-19).
NOT_LIKE_A_CLIENT = ("agency", "consultancy", "outsourcing", "public_sector", "non_profit")


def _employer(p: dict[str, Any], profile: dict[str, Any], stints: list[Stint] | None = None,
              family: str | None = None) -> tuple[str, str]:
    """A kind of company (start-up, agency…) or a size in people. What is wanted counts only years in the role's kind of
    work (owner, 2026-10-19: six months as a baker in a 4-person bakery is not "small-brand experience" for a marketing
    role); what is not wanted counts every job, as before."""
    from maindscout.domain.profile import stint_category

    kinds = p.get("employer_kinds") or []
    keep = _relevant(family) if stints is not None else None
    jobs = [s for s in stints or [] if s.employment not in NOT_EXPERIENCE and (keep is None or keep(s))]
    low, high = p.get("min_staff"), p.get("max_staff")
    if p.get("strength") != "anti" and (low is not None or high is not None):
        size = staff_words(low, high)
        if keep is not None and not jobs:
            return "gap", f"no time at companies of {size} in this kind of work"
        if not any(s.facts is not None and s.facts.team_min is not None for s in jobs):
            return "ask", f"the sizes of their employers are not known yet ({size})"
        like = (lambda s: stint_category(s) in kinds) if kinds else (
            lambda s: (s.facts.kind if s.facts is not None else None) not in NOT_LIKE_A_CLIENT)
        have, hits, _ = years_at_size(jobs, date.today(), low, high, like)
        names = list(dict.fromkeys(s.company for s in hits))[:3]
        at = f" ({', '.join(names)})" if names else ""
        if have >= 1:
            return "strong", f"{_years(have)} at companies of {size}{at}"
        if have > 0:
            return "partial", f"{_years(have)} at companies of {size}{at}"
        return "gap", f"no time at companies of {size} in this kind of work (as far as research shows)"
    mix = profile["dimensions"]["employer_mix"]
    names = " or ".join(KIND_WORDS.get(k, k.replace("_", " ")) for k in kinds)
    if p.get("strength") == "anti" or keep is None:
        years = mix.get("years") or {}
    elif not jobs:
        return "gap", f"no time at {names} in this kind of work"
    else:
        years = employer_years(jobs, date.today())
    known = {k: y for k, y in years.items() if k != "unknown"}
    if not known:
        return "ask", "the kinds of employer are not known yet"
    have = sum(known.get(k, 0) for k in kinds)
    total = sum(years.values()) or 1
    if p.get("strength") == "anti":
        share = have / total
        return ("against", f"{_years(have)} of the last 10 at {names}") if share >= 0.5 else ("strong", f"mostly not at {names}")
    if have >= 1:  # a year in that kind of company is enough (owner, 2026-10-18; it was two)
        return "strong", f"{_years(have)} at {names}"
    if have > 0:
        return "partial", f"{_years(have)} at {names}"
    return "gap", f"no time at {names} (as far as research shows)"


def _tier_years(stints: list[Stint], wanted: list[str]) -> dict[str, float]:
    """Years in each wanted industry, counting an industry other than luxury itself (hotels, travel…) only at luxury
    companies: a luxury role's "hospitality" means luxury hospitality, not a 4-star chain (owner, 2026-10-18)."""
    from datetime import date

    from maindscout.domain.profile import NOT_EXPERIENCE, _span
    from maindscout.domain.profile import _years as span_years
    from maindscout.domain.tiers import INHERENT

    spans: dict[str, list] = {}
    for s in stints:
        span = _span(s, date.today())
        d = (s.domains[0] if s.domains else "").strip().lower().replace("_", " ")
        if span is None or s.employment in NOT_EXPERIENCE or d not in wanted:
            continue
        if d == INHERENT or (s.facts is not None and s.facts.luxury):
            spans.setdefault(d, []).append(span)
    return {d: round(span_years(v), 1) for d, v in spans.items()}


def _company_words(p: dict[str, Any], stints: list[Stint]) -> tuple[str, str]:
    """A niche industry in the companies' own words ("leather goods", "bags"): years at employers that say they make
    or sell it, from their profiles. A year is enough."""
    from datetime import date

    from maindscout.domain.profile import NOT_EXPERIENCE, _span
    from maindscout.domain.profile import _years as span_years

    words = [w.strip().lower() for w in p.get("company_words") or [] if w.strip()]
    stems = [re.escape(w[:-1] if w.endswith("s") else w) + "s?" for w in words]
    pattern = re.compile(r"\b(" + "|".join(stems) + r")\b", re.I)
    spans, names, known = [], [], False
    for s in stints:
        span = _span(s, date.today())
        if s.facts is None or not s.facts.words:
            continue
        known = True
        if span is None or s.employment in NOT_EXPERIENCE or not pattern.search(s.facts.words):
            continue
        spans.append(span)
        if s.company not in names:
            names.append(s.company)
    label = ", ".join(words[:3])
    if not known:
        return "ask", f"what their employers make is not known yet ({label})"
    have = round(span_years(spans), 1) if spans else 0.0
    at = f" ({', '.join(names[:3])})" if names else ""
    if p.get("strength") == "anti":
        return ("against", f"{_years(have)} at companies making {label}{at}") if have >= 2 else ("strong", f"little or no time in {label}")
    if have >= 1:
        return "strong", f"{_years(have)} at companies making {label}{at}"
    if have > 0:
        return "partial", f"{_years(have)} at companies making {label}{at}"
    return "gap", f"no time at companies making {label}"


def _domain(p: dict[str, Any], profile: dict[str, Any], stints: list[Stint] | None = None, luxury: bool = False) -> tuple[str, str]:
    from maindscout.domain.tiers import INHERENT

    if p.get("company_words"):
        return _company_words(p, stints or [])
    dom = profile["dimensions"]["domain_exposure"]
    years = dom.get("years") or {}
    wanted = p.get("domains") or []
    if not years:
        return "ask", "industries not known yet"
    names = ", ".join(wanted)
    if luxury and stints and p.get("strength") != "anti" and any(d != INHERENT for d in wanted):
        years = _tier_years(stints, wanted)
        names += " (luxury companies only)"
    have = max((years.get(d, 0) for d in wanted), default=0)
    if p.get("strength") == "anti":
        return ("against", f"{_years(have)} in {names}") if have >= 2 else ("strong", f"little or no time in {names}")
    if have >= 1:  # a year in the industry is enough (owner, 2026-10-18; it was two)
        return "strong", f"{_years(have)} in {names}"
    if have > 0:
        return "partial", f"{_years(have)} in {names}"
    return "gap", f"no time in {names}"


# "Not from" a company: its people now, and anyone who left it less than this long ago; earlier leavers are fine
# (owner, 2026-10-19: no-compete clauses rarely run past two years, and six months is the line). A setting on each
# restriction ("recent_months").
RECENT_MONTHS = 6


def _target(p: dict[str, Any], stints: list[Stint]) -> tuple[str, str]:
    ids = {c.get("company_id") for c in p.get("companies") or [] if c.get("company_id")}
    hit = [s for s in stints if s.company_key in ids]
    names = ", ".join(c["name"] for c in p.get("companies") or [])
    if p.get("strength") == "anti":
        months = RECENT_MONTHS if p.get("recent_months") is None else int(p["recent_months"])
        cutoff = date.today() - timedelta(days=round(months * 30.44))
        now = [s for s in hit if s.end is None]
        if now:
            return "against", f"works at {now[0].company}"
        recent = [s for s in hit if s.end >= cutoff]
        if recent:
            return "against", f"left {recent[0].company} in {max(s.end for s in recent):%B %Y}, less than {months} months ago"
        if hit:
            return "strong", f"left {hit[0].company} in {max(s.end for s in hit):%B %Y}, more than {months} months ago"
        return "strong", f"never at {names}"
    return ("strong", f"worked at {', '.join(sorted({s.company for s in hit}))}") if hit else ("gap", f"never at {names}")


def _employment(p: dict[str, Any], profile: dict[str, Any]) -> tuple[str, str]:
    want = p.get("employment")
    con = profile["dimensions"]["contractor"]
    stab = (profile["dimensions"]["stability"].get("parts") or {}).get("contract")
    if want == "contract":
        if stab and stab["label"] == "long_engagements":
            return "strong", "a contractor with long engagements"
        if con["label"] in ("current", "past"):
            return "partial", "has contracted before"
        return "ask", "has not contracted: ask whether a contract suits them"
    if want == "permanent" and con["label"] == "current":
        return "ask", "contracting now: ask whether they want a permanent role"
    return "strong", "no conflict with the kind of employment"


_GENERIC = {"experience", "years", "year", "with", "role", "roles", "work", "working", "team", "senior", "junior", "level",
            "strong", "good", "skills", "skill", "knowledge", "background", "plus", "must", "have", "required", "preferred",
            "ability", "able", "solid", "proven", "hands", "least", "minimum", "this", "that", "from", "into", "their"}


def _covers(note: str, text: str, token: str | None = None) -> bool:
    """Does an intake note like 'can substitute for start-up experience' name this requirement?

    The requirement's own skill token, or most of its meaningful words, must be written in the note, as whole words.
    One shared generic word ("role", "team") is not naming it."""
    said = set(re.findall(r"[a-z0-9+#]+", note.lower().replace("-", "")))
    if token and token.lower().replace("-", "") in said:
        return True
    words = {w for w in re.findall(r"[a-z0-9+#]{4,}", text.lower().replace("-", "")) if w not in _GENERIC}
    if not words:
        return False
    hit = len(words & said)
    return hit >= max(1, (len(words) + 1) // 2)


def match(requirements: list[dict[str, Any]], gap_rows: list, profile: dict[str, Any] | None, stints: list[Stint],
          coarse: tuple[str, str], answers: dict[str, dict[str, Any]] | None = None, blocked: str | None = None,
          preferences: list[tuple[str, str, str, str, str]] | None = None, client: dict[str, Any] | None = None) -> Match:
    """`requirements`: [{id, payload}] (live, no process dates); `gap_rows`: domain.gaps rows for the same job and
    person; `profile`: the latest career profile (or None); `coarse`: the token triage (band, reason) as fallback;
    `preferences`: domain.preferences.rows for what the person said they want."""
    by_id = {r["id"]: r["payload"] for r in requirements}
    from maindscout.domain.tiers import luxury_role

    luxury = luxury_role([p.get("text_raw") or "" for p in by_id.values() if p.get("strength") != "anti"])
    family = next((p["role_family"] for p in by_id.values() if p.get("category") == "role" and p.get("role_family")
                   and p.get("strength") != "anti"), None)  # the role's kind of work
    rows: list[Verdict] = []
    for g in gap_rows:  # skills, years, education, languages, mobility, and anything the gap table already reads
        p = by_id.get(g.requirement_id, {})
        if p.get("category") in ("role", "employer", "domain", "target_company", "employment"):
            continue
        verdict = "ask" if g.kind == "mobility" else GAP_TO_VERDICT[g.status]
        detail = g.detail
        if g.kind == "skill" and g.status == "missing" and not g.distinctive:
            # A broad skill not written on a CV is not evidence of its absence: ask (distinctive ones decide, rule 1).
            verdict, detail = "ask", f"{g.detail}; not shown on the CV: ask"
        elif g.kind == "seniority" and g.status in ("evidence", "conflict") and by_id.get(g.requirement_id, {}).get("min_years")                 and profile is not None and profile["reading"]["label"] != "unclear"                 and (profile["dimensions"].get("relevant_years") or {}).get("label") not in (None, "unknown"):
            # "7 or more years of marketing experience" is years of that kind of work, not of a whole career (a junior
            # specialist with 8.2 years across translating, retail and 5.3 in marketing read as met, 2026-10-18).
            need = float(by_id[g.requirement_id]["min_years"])
            ry = profile["dimensions"]["relevant_years"]
            have = float(ry.get("main_years") or 0)
            verdict = "strong" if have >= need else "partial" if have >= 0.75 * need else "gap"
            detail = f"{_years(have)} of related work ({ry['label']}) against {need:g} asked; {g.detail}"
        elif g.kind == "language" and g.status == "missing":
            # Many profiles never list languages: a Milan marketing manager without "Italian" on their profile is a
            # question, never two must-have gaps that make them unlikely (a real marketing role, 2026-10-18).
            verdict = "ask"
        elif g.status == "likely" and not g.distinctive:
            verdict = "ask"  # their employer's stack: at least as good as a broad skill not written down
        rows.append(Verdict(g.requirement_id, g.requirement, g.kind, g.strength, verdict, detail, g.distinctive))
    thin = profile is None or profile["reading"]["label"] == "unclear"
    for r in requirements:
        p = r["payload"]
        cat = p.get("category")
        if cat not in ("role", "employer", "domain", "target_company", "employment"):
            continue
        if p.get("strength") == "anti" and (cat == "role" or (cat == "employer" and (p.get("min_staff") or p.get("max_staff")))):
            # A limit on seniority ("not too senior") or "not from" companies of a size: read since 2026-10-19, rated
            # from step C of understanding the hire, once match-eval has shown what they change.
            continue
        if thin:
            v, d = "ask", "no career profile yet"
        elif cat == "role":
            v, d = _role(p, profile, stints, (client or {}).get("specialism"))
        elif cat == "employer":
            v, d = _employer(p, profile, stints, family)
        elif cat == "domain":
            v, d = _domain(p, profile, stints, luxury)
        elif cat == "target_company":
            v, d = _target(p, stints)
        else:
            v, d = _employment(p, profile)
        rows.append(Verdict(r["id"], p["text_raw"], cat, p["strength"], v, d))

    # Answers captured on the call (the Brief) are the best evidence there is: they settle their requirement.
    for v in rows:
        a = (answers or {}).get(v.requirement_id)
        if a and v.kind != "mobility":
            said = f": {a['answer']}" if a.get("answer") else ""
            v.verdict, v.detail = ("strong", f"confirmed on the call{said}") if a["outcome"] == "confirmed" else ("gap", f"not met, said on the call{said}")
        elif a:
            v.detail = ("confirmed on the call" if a["outcome"] == "confirmed" else "not met, said on the call") + (f": {a['answer']}" if a.get("answer") else "")

    # What they want (said on a call): rows of their own kind and strength (their_must / their_prefer), so they are
    # never counted as the job's must-haves.
    wants = [Verdict(pid, words, "preference", f"their_{strength}", verdict, detail)
             for pid, words, strength, verdict, detail in preferences or []]
    rows += wants

    fired: list[dict[str, str]] = []

    def fire(rule: str, detail: str) -> None:
        fired.append({"id": rule, "text": RULE_TEXT[rule], "detail": detail})

    # 0. The client said no: a wall.
    if blocked:
        fire("client_block", blocked)
        return Match("unlikely", "do_not_submit", f"match:unlikely:the client said no ({blocked})", rows, fired)
    # 1. Today's rule: a distinctive must-have with no evidence decides the band. Except for someone known only from a
    # public profile whose recent title says the role's specialist work: a profile seldom lists every tool, so a CRM
    # specialist at a luxury house without "Salesforce" on it is asked, not ruled out (Ferrari's CRM role, 2026-10-22:
    # 190 such people had been dropped).
    if coarse[0] == "do_not_submit" and coarse[1].startswith("no_support_for_must_have"):
        spec = (client or {}).get("specialism")
        said = next((s.title for s in stints if s.employment not in NOT_EXPERIENCE
                     and (s.end is None or (date.today() - s.end).days <= 3 * 365) and specialism_mod.title_says(spec, s.title)), None)
        main = (((profile or {}).get("dimensions") or {}).get("relevant_years") or {}).get("main")
        want = next((r["payload"].get("role_family") for r in requirements if r["payload"].get("category") == "role"
                     and r["payload"].get("strength") != "anti"), None)
        if said and not (client or {}).get("has_cv", True) and same_side(want, main):
            # The tool is a question for the call, and the rest of the match decides (owner, 2026-10-23: the recruiter
            # saw "CRM operations specialist" at Brunello Cucinelli, asked for the CV, and the client interviewed her).
            missing = coarse[1].split(":")[1] if ":" in coarse[1] else "a must-have"
            fire("distinctive_must_unproven", f"{missing}: not on their public profile; their title says the work ({said})")
            for v in rows:
                if v.verdict == "gap" and v.strength in MUST and missing.lower() in (v.requirement + " " + v.detail).lower():
                    v.verdict, v.detail = "ask", f"not on their public profile; their title says the work ({said}): confirm on the call"
        else:
            fire("distinctive_must_missing", coarse[1].split(":", 1)[-1])
            return Match("unlikely", "do_not_submit", coarse[1], rows, fired)
    # 2. Not wanted.
    against = [v for v in rows if v.verdict == "against"]
    if against:
        fire("not_wanted", "; ".join(f"{v.requirement}: {v.detail}" for v in against))
        return Match("unlikely", "do_not_submit", f"match:unlikely:{against[0].requirement}", rows, fired)
    # 2b. What they said they want. A must the job contradicts: they would say no, so unlikely. A prefer: a note.
    fits = [v for v in wants if v.verdict == "strong"]
    if fits:
        fire("fits_what_they_want", "; ".join(v.detail.removeprefix("fits what they want: ") for v in fits))
    soft = [v for v in wants if v.verdict == "gap" and v.strength == "their_prefer"]
    if soft:
        fire("prefers_otherwise", "; ".join(f"{v.requirement}: {v.detail}" for v in soft))
    hard = [v for v in wants if v.verdict == "gap" and v.strength == "their_must"]
    if hard:
        fire("wants_otherwise", "; ".join(f"{v.requirement}: {v.detail}" for v in hard))
        return Match("unlikely", "do_not_submit", f"match:unlikely:not what they want ({hard[0].requirement})", rows, fired)
    if profile is None and not (client or {}).get("has_cv", True):
        # Not worth a career reading for this role, from the public profile alone (owner, 2026-10-26: 1,603 of Ferrari's
        # 1,632 ruled-out people had each been read first). They stay in the pool, unread, for another role.
        if why := not_worth_reading(stints, client or {}):
            fire("not_read", why)
            return Match("unlikely", "do_not_submit", f"match:unlikely:not read: {why} (public profile)", rows, fired)
    if thin:
        fire("too_little_known", "no career profile yet" if profile is None else "the career profile is unclear")
        # Nobody is strong before their career reading (owner, 2026-10-21: "obviously, this is a real bug"): a coarse
        # Priority waits in Review later until the reading arrives; Do not submit and Review later stand.
        if coarse[0] == "priority":
            return Match("unclear", "review_later", "match:unclear:being read", rows, fired)
        return Match("unclear", None, coarse[1], rows, fired)
    # 3. Substitutions stated in the intake: a met requirement stands in for the one its note names.
    for a in rows:
        note = by_id.get(a.requirement_id, {}).get("note") or ""
        if a.verdict == "strong" and "substitut" in note.lower():
            for b in rows:
                if b is not a and b.verdict in ("gap", "partial") and _covers(note, b.requirement, by_id.get(b.requirement_id, {}).get("normalized_token")):
                    b.verdict, b.detail = "strong", f"{b.detail}; counts as met: {a.requirement} can substitute for it"
                    fire("substitution", f"{a.requirement} stands in for {b.requirement}")
    # 4. Domain over seniority: one level below is outweighed by a strong industry match.
    for v in rows:
        if v.verdict == "level_one_below":
            dom = [d for d in rows if d.kind == "domain" and d.verdict == "strong" and d.strength in MUST + ("strong_plus",)]
            if dom:
                v.verdict = "strong"
                v.detail += f"; outweighed by {dom[0].requirement}"
                fire("domain_over_seniority", f"{v.requirement}: {dom[0].requirement}")
            else:
                v.verdict = "partial"
    # 5. Contract job, contractor with long engagements.
    if any(v.kind == "employment" and v.verdict == "strong" and "contractor" in v.detail for v in rows):
        fire("contractor_fit", "long contract engagements fit a contract job")
    # 6. Another field altogether: a CFO, an HR manager or a store manager for a marketing role (owner's 0-to-1 test,
    # 2026-10-21) was "possible" on one must-have gap. A related field (sales for marketing) is partial, not this.
    wrong = [v for v in rows if v.kind == "role" and v.strength in MUST and v.verdict == "gap" and ", not " in v.detail.split(";")[0]
             and not v.detail.startswith(f"works in {FAMILY_LABEL.get('other', 'other')},")]  # a field read as "other" is unknown
    if wrong:
        fire("wrong_field", wrong[0].detail.split(";")[0])
        return Match("unlikely", "do_not_submit", f"match:unlikely:{wrong[0].detail.split(';')[0]}", rows, fired)
    # 6b. Too many years for the role's level (owner, 2026-10-23: "mid level with 2-5 is fine, 6 years if it is
    # excellent match ... mid level with 7 years of experience is a no").
    years, band = career_years(stints), years_band(client or {})
    if band and years is not None and years >= band[1] + 2:
        detail = f"{years:g} years of work, for a {client['level']} role ({band[0]}-{band[1]} years; {band[1] + 1} with an excellent match)"
        fire("too_senior", detail)
        return Match("unlikely", "do_not_submit", f"match:unlikely:too senior: {detail}", rows, fired)
    # 7. Must-have gaps.
    must_gaps = [v for v in rows if v.strength in MUST and v.verdict == "gap"]
    if len(must_gaps) >= 2:
        fire("must_gaps", ", ".join(v.requirement for v in must_gaps[:4]))
        return Match("unlikely", "do_not_submit", f"match:unlikely:{len(must_gaps)} must-haves are gaps", rows, fired)
    if len(must_gaps) == 1:
        fire("must_gaps", must_gaps[0].requirement)
        return Match("possible", "review_later", f"match:possible:{must_gaps[0].requirement} is a gap", rows, fired)
    # 7. Strong match: musts met (or to ask), and at least half of the known strong-plus items met.
    partial_musts = [v for v in rows if v.strength in MUST and v.verdict == "partial"]
    if partial_musts:
        fire("partial_must", "; ".join(f"{v.requirement}: {v.detail}" for v in partial_musts[:3]))
        return Match("possible", "review_later", f"match:possible:{partial_musts[0].requirement} only partly met", rows, fired)
    plus = [v for v in rows if v.strength == "strong_plus" and v.verdict != "ask"]
    met = [v for v in plus if v.verdict == "strong"]
    reaches = _reaches(by_id, profile, stints, client or {}, family)
    if (not plus or len(met) * 2 >= len(plus)) and reaches:
        # Step C (owner, 2026-10-21: "its a standard recruiter logic"): strong on paper, but a reach.
        for rule, detail in reaches:
            fire(rule, detail)
        return Match("possible", "review_later", f"match:possible:a reach: {reaches[0][1]}", rows, fired)
    if (not plus or len(met) * 2 >= len(plus)) and band and years is not None and years >= band[1] + 1:
        excellent = all(v.verdict == "strong" for v in rows if v.strength in MUST + ("strong_plus",) and v.kind != "mobility")
        if not excellent:
            detail = f"{years:g} years of work, one more than a {client['level']} role's {band[0]}-{band[1]}: strong only with an excellent match"
            fire("too_senior", detail)
            return Match("possible", "review_later", f"match:possible:a reach: {detail}", rows, fired)
    if not plus or len(met) * 2 >= len(plus):
        fire("strong_match", f"{len(met)} of {len(plus)} known strong-plus items met" if plus else "every must-have met or to ask")
        return Match("strong", "priority", f"match:strong:{len(met)} of {len(plus)} strong-plus met" if plus else "match:strong:must-haves met", rows, fired)
    return Match("possible", "review_later", f"match:possible:{len(met)} of {len(plus)} strong-plus met", rows, fired)


# --- step C: is the move realistic? (owner, 2026-10-19 and 2026-10-21) ------------------------------------------------

# Years of work that fit a role's level (owner, 2026-10-23, for a mid role: "everyone above 6 years is senior ... mid
# level with 2-5 is fine, 6 years if it is excellent match"): (from, to); one year more only with an excellent match,
# two or more is a no. Senior roles and above have no ceiling here (the level check of step C covers them).
YEARS_BAND = {"intern": (0, 1), "junior": (0, 2), "mid": (2, 5)}


# The sides of a company, for a specialist title: CRM done in marketing, sales, client service or a boutique is the
# business side; CRM done in IT, data or product is another department (owner, 2026-10-23).
SIDES = {"business": {"sales", "marketing", "customer_success", "business_consulting", "retail", "hospitality"}}


_INTERN_TITLE = re.compile(r"\b(intern|internship|stage|stagista|tirocin\w*|trainee|apprentice\w*|praktik\w*|working student|"
                           r"werkstudent\w*|summer analyst)\b", re.I)


def not_worth_reading(stints: list[Stint], client: dict[str, Any]) -> str | None:
    """Why someone found on the web is clearly out for this role from their public profile alone (so they are not
    read), or None: no title in the last 3 years says a specialist role's work, or their first real job (titles of
    internships left out) already puts them two years past the role's band."""
    today = date.today()
    spec = client.get("specialism")
    recent = [s for s in stints if s.end is None or (today - s.end).days <= 3 * 365]
    if spec and stints and not any(specialism_mod.title_says(spec, s.title) for s in recent):
        return f"no title in the last 3 years says {specialism_mod.broad_word(spec)} work"
    band = years_band(client)
    starts = [s.start for s in stints if s.start and not _INTERN_TITLE.search(s.title or "")]
    if band and starts:
        years = int((today - min(starts)).days // 365.25)
        if years >= band[1] + 2:
            return f"{years} years of work, for a {client.get('level')} role"
    return None


def same_side(want: str | None, main: str | None) -> bool:
    """Is a person's kind of work on the role's side of the company? An unknown either way is not held against them."""
    if not want or not main or "other" in (want, main):
        return True
    if want == main or group_of(want) == group_of(main):
        return True
    return any(want in side and main in side for side in SIDES.values())


def years_band(client: dict[str, Any]) -> tuple[int, int] | None:
    """The years that fit the role's level, never below what its ad asks: a mid role's 2-5, but 5-7 when the ad asks
    for at least 5 years (a rule for every role, not one ad: owner, 2026-10-26)."""
    band = YEARS_BAND.get(client.get("level") or "")
    if band is None:
        return None
    asked = client.get("min_years")
    return (max(band[0], int(asked)), max(band[1], int(asked) + 2)) if asked else band


def career_years(stints: list[Stint]) -> float | None:
    """Years since their first real job (internships, side work, board seats and volunteering not counted)."""
    starts = [s.start for s in stints if s.start and s.employment not in NOT_EXPERIENCE]
    if not starts:
        return None
    return int((date.today() - min(starts)).days // 365.25)  # full years: 5 years and 9 months is 5


BIG_MOVE = 20  # an employer this many times the client's size: from 12,203 people to 62 is a reach; 1,027 to 93 is not
NEAR = 5  # a company up to this many times the client's size counts as "near the client's size"
RECENT_YEARS = 3
SCOPE = re.compile(r"\b(global|worldwide|international|regional|emea|apac|americas)\b", re.I)
# Narrow kinds of marketing work, read from the current title. A role that asks for an all-round marketer ("360",
# "broad marketing experience") finds them possible, unless the role asks for that work itself.
SPECIALISMS = {"social media": r"social media", "crm": r"\bcrm\b|clienteling|client (development|experience)",
               "media": r"\bmedia\b",
               "performance marketing": r"performance marketing|\bseo\b|\bsem\b|paid (social|search)",
               "merchandising": r"merchandis", "trade marketing": r"trade marketing", "events": r"\bevents?\b",
               "public relations": r"\bpr\b|public relations|press office", "copywriting": r"copywrit",
               "content production": r"content production",
               "analytics": r"analytic|insights"}
GENERALIST_TITLE = re.compile(r"\b(marketing (manager|director|lead)|head of marketing|marketing (and|&) communications? manager"
                              r"|brand manager|cmo)\b", re.I)


def _size(facts) -> int | None:
    return None if facts is None or facts.team_min is None else facts.team_min


def _reaches(by_id: dict[str, dict[str, Any]], profile: dict[str, Any] | None, stints: list[Stint],
             client: dict[str, Any], family: str | None) -> list[tuple[str, str]]:
    """Why a match that is strong on paper is a reach: [(rule, detail)]. Nothing without a career profile."""
    if profile is None:
        return []
    out: list[tuple[str, str]] = []
    today = date.today()
    now = [s for s in stints if s.end is None and s.employment not in NOT_EXPERIENCE]
    level = ((profile.get("dimensions") or {}).get("seniority") or {}).get("label")
    rank, role_rank = LEVEL_RANK.get(level or ""), LEVEL_RANK.get(client.get("level") or "")
    # 1. The move: from a company far bigger than the client, unless it is a step up or they were recently at a
    #    company near the client's size (in the role's kind of work).
    staff = client.get("staff")
    if staff and now:
        biggest = max(now, key=lambda s: _size(s.facts) or 0)
        theirs = _size(biggest.facts)
        step_up = rank is not None and role_rank is not None and rank < role_rank
        keep = _relevant(family)
        recent_near = any((s.end is None or (today - s.end).days <= RECENT_YEARS * 365)
                          and s.start is not None and ((s.end or today) - s.start).days >= 365
                          and _size(s.facts) is not None and _size(s.facts) <= NEAR * staff and (keep is None or keep(s))
                          for s in stints if s.employment not in NOT_EXPERIENCE)
        if theirs and theirs >= BIG_MOVE * staff and not step_up and not recent_near:
            out.append(("too_big_a_move", f"from {biggest.company} ({theirs:,} people) to a {staff:,}-person company, "
                                          "with no recent time at a company near that size"))
    # 2. The level: well above the role, at the role's seniority limit, or global or regional above it.
    if rank is not None and role_rank is not None:
        limit = next((LEVEL_RANK.get(p.get("level") or "") for p in by_id.values()
                      if p.get("category") == "role" and p.get("strength") == "anti" and p.get("level")), None)
        title = now[0].title if now else ""
        if rank - role_rank >= 2:
            out.append(("above_the_role", f"{level} now ({title}), well above a {client.get('level')} role"))
        elif limit is not None and rank >= limit:
            out.append(("above_the_role", f"{level} now ({title}): at the role's seniority limit"))
        elif rank > role_rank and SCOPE.search(title):
            out.append(("above_the_role", f"{title}: a {level} with a global or regional scope, above a {client.get('level')} role"))
    # 3. A specialist for an all-round role.
    if client.get("generalist") and family == "marketing" and now:
        title = now[0].title
        wanted = client.get("wanted") or ""
        for name, rx in SPECIALISMS.items():
            if re.search(rx, title, re.I) and not GENERALIST_TITLE.search(title) and not re.search(rx, wanted, re.I):
                out.append(("specialist", f"{title}: a {name} specialist, for an all-round marketing role"))
                break
    return out
