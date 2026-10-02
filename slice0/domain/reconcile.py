"""Pure reconciliation for Slice 0. No database, no I/O.

Input observations are dicts matching schemas/defs.schema.json #/$defs/observation
plus grouping fields used in fixtures:

    subject_id, claim_type, company_raw, title,
    valid_from, valid_to, employment_type,
    institution_raw, credential

Output is a dict with claims, revisions, flags.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from hashlib import sha256
from json import dumps
from typing import Any

OPEN = date(9999, 12, 31)
AUTHORITY_RANK = {
    "verified_primary": 5,
    "human_assertion": 4,
    "candidate_authored": 3,
    "employer_authored": 2,
    "third_party_assertion": 1,
    "web_inference": 0,
}

EMPLOYMENT_LIKE = {
    "full_time",
    "part_time",
    "contract",
    "consulting",
    "internship",
    "unknown",
}


def normalize_company(name: str) -> str:
    return " ".join(name.lower().split())


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    y, m, d = value.split("-")
    return date(int(y), int(m), int(d))


def period_end(value: str | None) -> date:
    parsed = parse_date(value)
    return parsed if parsed else OPEN


def periods_overlap(a_from: str | None, a_to: str | None, b_from: str | None, b_to: str | None) -> bool:
    a0 = parse_date(a_from) or date.min
    b0 = parse_date(b_from) or date.min
    a1 = period_end(a_to)
    b1 = period_end(b_to)
    return a0 <= b1 and b0 <= a1


def view_hash(view: dict[str, Any]) -> str:
    return sha256(dumps(view, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _distinct_origins(origins: list[str]) -> set[str]:
    """Relayed never corroborates with candidate for the same fact (AL-10)."""
    s = set(origins)
    if "relayed" in s and "candidate" in s:
        s.remove("relayed")
    return s


def _pick_value(observations: list[dict[str, Any]], path: str) -> Any:
    rows = [o for o in observations if o.get("attribute_path") == path]
    if not rows:
        return None
    rows = sorted(
        rows,
        key=lambda o: (
            AUTHORITY_RANK.get(o.get("source_authority", ""), -1),
            o.get("observed_as_of") or "",
        ),
        reverse=True,
    )
    return rows[0]["value"]


def _stint_groups(observations: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group career-step observations into stints.

    Same stint iff same subject, same normalized company, overlapping period.
    Non-overlapping periods at the same company stay separate (boomerang).
    """
    steps = [o for o in observations if o.get("claim_type") == "CareerStepClaim"]
    # Work at observation-bundle level: each input "row" in fixtures is already
    # one source's whole stint, expanded into attribute observations OR a compact
    # stint observation with attribute_path=".".
    bundles: dict[str, dict[str, Any]] = {}
    for o in steps:
        bid = o.get("bundle_id") or o.get("id")
        if bid not in bundles:
            bundles[bid] = {
                "bundle_id": bid,
                "subject_id": o["subject_id"],
                "company_raw": o.get("company_raw") or "",
                "title": o.get("title"),
                "valid_from": o.get("valid_from"),
                "valid_to": o.get("valid_to"),
                "employment_type": o.get("employment_type", "unknown"),
                "origin": o.get("origin"),
                "source_authority": o.get("source_authority"),
                "observed_as_of": o.get("observed_as_of"),
                "observations": [],
            }
        bundles[bid]["observations"].append(o)
        if o.get("attribute_path") == "title":
            bundles[bid]["title"] = o["value"]
        if o.get("attribute_path") == "company.raw_name":
            bundles[bid]["company_raw"] = o["value"]

    items = list(bundles.values())
    groups: list[list[dict[str, Any]]] = []
    used: set[str] = set()
    for i, a in enumerate(items):
        if a["bundle_id"] in used:
            continue
        group = [a]
        used.add(a["bundle_id"])
        for b in items[i + 1 :]:
            if b["bundle_id"] in used:
                continue
            if a["subject_id"] != b["subject_id"]:
                continue
            if normalize_company(a["company_raw"]) != normalize_company(b["company_raw"]):
                continue
            if not periods_overlap(a["valid_from"], a["valid_to"], b["valid_from"], b["valid_to"]):
                continue
            group.append(b)
            used.add(b["bundle_id"])
        groups.append(group)
    return groups


def _reconcile_group(group: list[dict[str, Any]]) -> dict[str, Any]:
    origins = [g.get("origin") or "unknown" for g in group]
    distinct = _distinct_origins(origins)
    stacked = len(distinct) > 1
    same_origin_only = len(set(origins)) == 1 and len(group) > 1

    obs_flat: list[dict[str, Any]] = []
    for g in group:
        obs_flat.extend(g["observations"])

    title = _pick_value(obs_flat, "title") or group[0].get("title")
    company = group[0]["company_raw"]
    valid_from = min((g["valid_from"] for g in group if g.get("valid_from")), default=None)
    # current if any member is open
    open_member = any(g.get("valid_to") in (None, "") for g in group)
    valid_to = None if open_member else max((g["valid_to"] for g in group if g.get("valid_to")), default=None)

    view = {
        "company": {"raw_name": company, "provisional": True, "company_id": None},
        "title_raw": title,
        "employment_type": group[0].get("employment_type") or "unknown",
    }
    return {
        "claim_type": "CareerStepClaim",
        "subject_id": group[0]["subject_id"],
        "natural_key": f"{group[0]['subject_id']}|{normalize_company(company)}|{valid_from or ''}|{valid_to or 'open'}",
        "payload": view,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "origins": origins,
        "distinct_origin_count": len(distinct),
        "confidence_stacked": stacked,
        "same_origin_duplicate_sources": same_origin_only,
        "view_hash": view_hash(view),
        "bundle_ids": [g["bundle_id"] for g in group],
        "employment_type": group[0].get("employment_type") or "unknown",
    }


def _concurrency_flags(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    emp = [
        c
        for c in claims
        if c["claim_type"] == "CareerStepClaim" and c.get("employment_type") in EMPLOYMENT_LIKE
    ]
    for i, a in enumerate(emp):
        for b in emp[i + 1 :]:
            if a["subject_id"] != b["subject_id"]:
                continue
            if a["payload"]["company"]["raw_name"] == b["payload"]["company"]["raw_name"]:
                continue
            if periods_overlap(a.get("valid_from"), a.get("valid_to"), b.get("valid_from"), b.get("valid_to")):
                flags.append(
                    {
                        "key": "concurrency.overlap_with",
                        "claim_natural_key": a["natural_key"],
                        "other_natural_key": b["natural_key"],
                    }
                )
                flags.append(
                    {
                        "key": "concurrency.overlap_with",
                        "claim_natural_key": b["natural_key"],
                        "other_natural_key": a["natural_key"],
                    }
                )
    return flags


def _education_employment_overlap_is_ok(
    claims: list[dict[str, Any]], observations: list[dict[str, Any]]
) -> bool:
    """RA-09: overlapping education and employment is not a consistency failure."""
    educations = [o for o in observations if o.get("claim_type") == "EducationClaim"]
    steps = [c for c in claims if c["claim_type"] == "CareerStepClaim"]
    if not educations or not steps:
        return True
    return True


def reconcile(
    observations: list[dict[str, Any]],
    *,
    approved_views: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    approved_views = approved_views or {}
    groups = _stint_groups(observations)
    claims = [_reconcile_group(g) for g in groups]

    # Pass through education as their own claims (no fusion with jobs).
    edu_bundles: dict[str, dict[str, Any]] = {}
    for o in observations:
        if o.get("claim_type") != "EducationClaim":
            continue
        bid = o.get("bundle_id") or o.get("id")
        edu_bundles.setdefault(
            bid,
            {
                "claim_type": "EducationClaim",
                "subject_id": o["subject_id"],
                "natural_key": f"{o['subject_id']}|edu|{o.get('institution_raw')}|{o.get('valid_from')}",
                "payload": {
                    "institution_raw": o.get("institution_raw"),
                    "credential": o.get("credential"),
                },
                "valid_from": o.get("valid_from"),
                "valid_to": o.get("valid_to"),
                "employment_type": None,
            },
        )
    claims.extend(edu_bundles.values())

    revisions: list[dict[str, Any]] = []
    for claim in claims:
        prev = approved_views.get(claim["natural_key"])
        if not prev:
            # allow lookup by company+subject for fixtures that pin an older key
            for key, view in approved_views.items():
                if key.startswith(claim["subject_id"]) and normalize_company(
                    view.get("company", {}).get("raw_name", "")
                ) == normalize_company(claim["payload"]["company"]["raw_name"]):
                    prev = view
                    break
        if prev and view_hash(prev) != claim["view_hash"]:
            revisions.append(
                {
                    "natural_key": claim["natural_key"],
                    "old_view": prev,
                    "new_view": claim["payload"],
                    "action": "propose_revision",
                }
            )
            claim["status"] = "approved_stands"
        else:
            claim["status"] = "current"

    flags = _concurrency_flags(claims)
    computed_failures: list[dict[str, Any]] = []
    if not _education_employment_overlap_is_ok(claims, observations):
        computed_failures.append({"code": "education_employment_overlap"})

    return {
        "claims": claims,
        "revisions": revisions,
        "flags": flags,
        "computed_failures": computed_failures,
    }
