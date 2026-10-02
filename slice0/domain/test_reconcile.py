from pathlib import Path
import json
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reconcile import reconcile, normalize_company  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_same_stint_two_origins_stacks():
    data = load("same_stint_two_origins.json")
    out = reconcile(data["observations"])
    steps = [c for c in out["claims"] if c["claim_type"] == "CareerStepClaim"]
    assert len(steps) == 1
    assert steps[0]["confidence_stacked"] is True
    assert steps[0]["distinct_origin_count"] == 2


def test_same_stint_same_origin_does_not_stack():
    data = load("same_stint_same_origin.json")
    out = reconcile(data["observations"])
    steps = [c for c in out["claims"] if c["claim_type"] == "CareerStepClaim"]
    assert len(steps) == 1
    assert steps[0]["confidence_stacked"] is False
    assert steps[0]["same_origin_duplicate_sources"] is True


def test_relayed_does_not_corroborate_candidate():
    data = load("relayed_and_candidate.json")
    out = reconcile(data["observations"])
    steps = [c for c in out["claims"] if c["claim_type"] == "CareerStepClaim"]
    assert len(steps) == 1
    assert steps[0]["confidence_stacked"] is False
    assert steps[0]["distinct_origin_count"] == 1


def test_boomerang_not_fused():
    data = load("boomerang.json")
    out = reconcile(data["observations"])
    steps = [c for c in out["claims"] if c["claim_type"] == "CareerStepClaim"]
    assert len(steps) == 2
    companies = {normalize_company(c["payload"]["company"]["raw_name"]) for c in steps}
    assert companies == {"acme"}


def test_temporal_succession_two_approved_windows():
    data = load("temporal_succession.json")
    out = reconcile(data["observations"])
    steps = [c for c in out["claims"] if c["claim_type"] == "CareerStepClaim"]
    assert len(steps) == 2


def test_approved_view_revision_not_mutation():
    data = load("approved_view_revision.json")
    out = reconcile(data["observations"], approved_views=data["approved_views"])
    assert len(out["revisions"]) == 1
    assert out["revisions"][0]["action"] == "propose_revision"
    standing = [c for c in out["claims"] if c.get("status") == "approved_stands"]
    assert standing


def test_education_overlap_is_not_a_computed_failure():
    data = load("education_during_employment.json")
    out = reconcile(data["observations"])
    assert out["computed_failures"] == []
    types = {c["claim_type"] for c in out["claims"]}
    assert "EducationClaim" in types
    assert "CareerStepClaim" in types


def test_concurrent_employment_flags_both_sides():
    data = load("concurrent_employment.json")
    out = reconcile(data["observations"])
    steps = [c for c in out["claims"] if c["claim_type"] == "CareerStepClaim"]
    assert len(steps) == 3
    flags = [f for f in out["flags"] if f["key"] == "concurrency.overlap_with"]
    keys = {f["claim_natural_key"] for f in flags}
    assert len(keys) == 3
    assert len(flags) >= 6
