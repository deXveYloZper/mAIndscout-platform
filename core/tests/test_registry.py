import pytest
from sqlalchemy import func, select

from maindscout.api import writer
from maindscout.db.models import ClaimTypeRegistry, FlagTypeRegistry
from maindscout.domain import registry as reg

KNOWN = set(reg.load_flag_registry())


def test_registries_seed_from_yaml(session):
    assert session.scalar(select(func.count()).select_from(ClaimTypeRegistry)) == len(reg.load_claim_registry())
    assert session.scalar(select(func.count()).select_from(FlagTypeRegistry)) == len(KNOWN)


def test_seeding_twice_changes_nothing(session):
    writer.seed_registries(session)
    assert session.scalar(select(func.count()).select_from(FlagTypeRegistry)) == len(KNOWN)


def test_every_slice0_claim_type_is_registered(session):
    keys = set(session.scalars(select(ClaimTypeRegistry.key)))
    assert {"IdentityClaim", "ContactClaim", "CareerStepClaim", "EducationClaim",
            "SkillClaim", "LocationClaim", "JobRequirementClaim"} <= keys


def test_flag_paths_flatten_nested_form():
    paths = reg.flag_paths({"concurrency": {"overlap_with": ["x"]}, "possible_ocr_identifier": True}, KNOWN)
    assert sorted(paths) == ["concurrency.overlap_with", "possible_ocr_identifier"]


def test_dotted_key_is_a_leaf():
    assert reg.flag_paths({"concurrency.overlap_with": ["x"]}, KNOWN) == ["concurrency.overlap_with"]


def test_unknown_flag_rejected_by_validator():
    with pytest.raises(reg.UnknownFlagError):
        reg.validate_flags({"made_up_flag": True}, KNOWN)
    with pytest.raises(reg.UnknownFlagError):
        reg.validate_flags({"concurrency": {"typo": 1}}, KNOWN)
