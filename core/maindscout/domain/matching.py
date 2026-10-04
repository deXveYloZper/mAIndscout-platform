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
from typing import Any

from maindscout.domain.profile import FAMILY_LABEL, LEVEL_RANK, Stint, group_of

ENGINE_VERSION = "match-2026-10-04.1"
MUST = ("must", "deal_breaker")

# The desk's rules, as data: id -> what it says. The order of evaluation is the order of this list.
RULES: list[dict[str, str]] = [
    {"id": "client_block", "text": "The client said no to this person: a wall at this client until a person lifts it."},
    {"id": "distinctive_must_missing", "text": "A must-have that decides the band has no evidence: do not submit."},
    {"id": "not_wanted", "text": "The person meets a requirement the hiring manager does not want."},
    {"id": "substitution", "text": "A requirement the intake says can substitute for another is met, so that one counts as met."},
    {"id": "domain_over_seniority", "text": "A strong industry match outweighs one level below the level asked for."},
    {"id": "contractor_fit", "text": "A contract job and a contractor with long engagements: a strong plus."},
    {"id": "must_gaps", "text": "Two or more must-haves are gaps: unlikely; one: possible."},
    {"id": "partial_must", "text": "A must-have is only partly met (a related kind of work, a level below, fewer years): possible."},
    {"id": "too_little_known", "text": "Too little is known about the person to compare (no career profile yet): the coarse band stands."},
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


GAP_TO_VERDICT = {"evidence": "strong", "missing": "gap", "conflict": "gap", "question": "ask"}


def _years(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".") + (" year" if round(x, 1) == 1 else " years")


def _role(p: dict[str, Any], profile: dict[str, Any]) -> tuple[str, str]:
    ry, sen = profile["dimensions"]["relevant_years"], profile["dimensions"]["seniority"]
    if ry["label"] == "unknown":
        return "ask", "the kind of work is not clear from the CV"
    want, main = p.get("role_family"), ry["main"]
    parts, verdicts = [], []
    if want == main:
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


def _employer(p: dict[str, Any], profile: dict[str, Any]) -> tuple[str, str]:
    mix = profile["dimensions"]["employer_mix"]
    years = mix.get("years") or {}
    known = {k: y for k, y in years.items() if k != "unknown"}
    kinds = p.get("employer_kinds") or []
    if not known:
        return "ask", "the kinds of employer are not known yet"
    have = sum(known.get(k, 0) for k in kinds)
    total = sum(years.values()) or 1
    names = ", ".join(k.replace("_", " ") for k in kinds)
    if p.get("strength") == "anti":
        share = have / total
        return ("against", f"{_years(have)} of the last 10 at {names}") if share >= 0.5 else ("strong", f"mostly not at {names}")
    if have >= 2:
        return "strong", f"{_years(have)} at {names}"
    if have > 0:
        return "partial", f"{_years(have)} at {names}"
    return "gap", f"no time at {names} (as far as research shows)"


def _domain(p: dict[str, Any], profile: dict[str, Any]) -> tuple[str, str]:
    dom = profile["dimensions"]["domain_exposure"]
    years = dom.get("years") or {}
    wanted = p.get("domains") or []
    if not years:
        return "ask", "industries not known yet"
    have = max((years.get(d, 0) for d in wanted), default=0)
    names = ", ".join(wanted)
    if p.get("strength") == "anti":
        return ("against", f"{_years(have)} in {names}") if have >= 2 else ("strong", f"little or no time in {names}")
    if have >= 2:
        return "strong", f"{_years(have)} in {names}"
    if have > 0:
        return "partial", f"{_years(have)} in {names}"
    return "gap", f"no time in {names}"


def _target(p: dict[str, Any], stints: list[Stint]) -> tuple[str, str]:
    ids = {c.get("company_id") for c in p.get("companies") or [] if c.get("company_id")}
    hit = [s for s in stints if s.company_key in ids]
    names = ", ".join(c["name"] for c in p.get("companies") or [])
    if p.get("strength") == "anti":
        return ("against", f"worked at {hit[0].company}") if hit else ("strong", f"never at {names}")
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


def _covers(note: str, text: str) -> bool:
    """Does an intake note like 'can substitute for start-up experience' name this requirement?"""
    words = {w for w in re.findall(r"[a-z0-9]{4,}", text.lower().replace("-", "")) if w not in {"experience", "years", "with"}}
    return bool(words) and any(w in note.lower().replace("-", "") for w in words)


def match(requirements: list[dict[str, Any]], gap_rows: list, profile: dict[str, Any] | None, stints: list[Stint],
          coarse: tuple[str, str], answers: dict[str, dict[str, Any]] | None = None, blocked: str | None = None) -> Match:
    """`requirements`: [{id, payload}] (live, no process dates); `gap_rows`: domain.gaps rows for the same job and
    person; `profile`: the latest career profile (or None); `coarse`: the token triage (band, reason) as fallback."""
    by_id = {r["id"]: r["payload"] for r in requirements}
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
        rows.append(Verdict(g.requirement_id, g.requirement, g.kind, g.strength, verdict, detail, g.distinctive))
    thin = profile is None or profile["reading"]["label"] == "unclear"
    for r in requirements:
        p = r["payload"]
        cat = p.get("category")
        if cat not in ("role", "employer", "domain", "target_company", "employment"):
            continue
        if thin:
            v, d = "ask", "no career profile yet"
        elif cat == "role":
            v, d = _role(p, profile)
        elif cat == "employer":
            v, d = _employer(p, profile)
        elif cat == "domain":
            v, d = _domain(p, profile)
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

    fired: list[dict[str, str]] = []

    def fire(rule: str, detail: str) -> None:
        fired.append({"id": rule, "text": RULE_TEXT[rule], "detail": detail})

    # 0. The client said no: a wall.
    if blocked:
        fire("client_block", blocked)
        return Match("unlikely", "do_not_submit", f"match:unlikely:the client said no ({blocked})", rows, fired)
    # 1. Today's rule: a distinctive must-have with no evidence decides the band.
    if coarse[0] == "do_not_submit" and coarse[1].startswith("no_support_for_must_have"):
        fire("distinctive_must_missing", coarse[1].split(":", 1)[-1])
        return Match("unlikely", "do_not_submit", coarse[1], rows, fired)
    # 2. Not wanted.
    against = [v for v in rows if v.verdict == "against"]
    if against:
        fire("not_wanted", "; ".join(f"{v.requirement}: {v.detail}" for v in against))
        return Match("unlikely", "do_not_submit", f"match:unlikely:{against[0].requirement}", rows, fired)
    if thin:
        fire("too_little_known", "no career profile yet" if profile is None else "the career profile is unclear")
        return Match("unclear", None, coarse[1], rows, fired)
    # 3. Substitutions stated in the intake: a met requirement stands in for the one its note names.
    for a in rows:
        note = by_id.get(a.requirement_id, {}).get("note") or ""
        if a.verdict == "strong" and "substitut" in note.lower():
            for b in rows:
                if b is not a and b.verdict in ("gap", "partial") and _covers(note, b.requirement):
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
    # 6. Must-have gaps.
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
    if not plus or len(met) * 2 >= len(plus):
        fire("strong_match", f"{len(met)} of {len(plus)} known strong-plus items met" if plus else "every must-have met or to ask")
        return Match("strong", "priority", f"match:strong:{len(met)} of {len(plus)} strong-plus met" if plus else "match:strong:must-haves met", rows, fired)
    return Match("possible", "review_later", f"match:possible:{len(met)} of {len(plus)} strong-plus met", rows, fired)
