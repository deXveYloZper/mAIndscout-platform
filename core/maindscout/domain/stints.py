"""Career-step rules. Pure, no database. Uses the vendored reconcile module for the shared rules.

Within one document, each job the author lists is its own stint: we never fuse them. Across
documents, a step that has the same company and an overlapping period as an existing one is not
merged either: both stay, flagged `possible_duplicate_stint`, and a human decides (false merge is
the catastrophe, a false split is a nuisance).
"""

from __future__ import annotations

import importlib.util
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

_PATH = Path(__file__).resolve().parents[3] / "slice0" / "domain" / "reconcile.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("slice0_reconcile", _PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reconcile = _load()

BOUNDARY_TOLERANCE_DAYS = 31  # a job ending in a month and the next starting in it is not concurrency


def normalize_company(name: str) -> str:
    return reconcile.normalize_company(name)


def same_company_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return normalize_company(a["company"]) == normalize_company(b["company"]) and reconcile.periods_overlap(
        a.get("valid_from"), a.get("valid_to"), b.get("valid_from"), b.get("valid_to")
    )


def _trim(step: dict[str, Any]) -> dict[str, Any]:
    end = step.get("valid_to")
    if end:
        end = (date.fromisoformat(end) - timedelta(days=BOUNDARY_TOLERANCE_DAYS)).isoformat()
    return {**step, "valid_to": end}


def concurrent_pairs(steps: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Ids of employment-like steps at different companies whose periods genuinely overlap.

    Each step: {id, company, employment_type, valid_from, valid_to}. Uses reconcile's own rule,
    with a one-month tolerance at the boundaries so an ordinary job change is not flagged.
    """
    claims = []
    for step in map(_trim, steps):
        claims.append(
            {
                "claim_type": "CareerStepClaim",
                "subject_id": "x",
                "natural_key": step["id"],
                "payload": {"company": {"raw_name": step["company"]}},
                "valid_from": step.get("valid_from"),
                "valid_to": step.get("valid_to"),
                "employment_type": step.get("employment_type") or "unknown",
            }
        )
    flags = reconcile._concurrency_flags(claims)
    return [(f["claim_natural_key"], f["other_natural_key"]) for f in flags]
