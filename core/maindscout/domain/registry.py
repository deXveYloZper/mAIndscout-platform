"""Loads the claim and flag registries from slice0/registry and validates keys against them."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import json
from functools import lru_cache

import yaml
from jsonschema import Draft202012Validator

REGISTRY_DIR = Path(__file__).resolve().parents[3] / "slice0" / "registry"


class UnknownFlagError(ValueError):
    def __init__(self, keys: list[str]):
        super().__init__(f"Unknown flag key(s): {', '.join(sorted(keys))}")
        self.keys = keys


class UnknownClaimTypeError(ValueError):
    pass


def _load(name: str) -> dict[str, Any]:
    return yaml.safe_load((REGISTRY_DIR / name).read_text(encoding="utf-8"))


def load_flag_registry() -> dict[str, dict[str, Any]]:
    return {row["key"]: row for row in _load("flag_type_registry.yaml")["flags"]}


def load_claim_registry() -> dict[str, dict[str, Any]]:
    return dict(_load("claim_type_registry.yaml")["types"])


def flag_paths(flags: dict[str, Any], known: set[str]) -> list[str]:
    """Flatten a flags object into registry keys.

    A key that is itself in the registry (e.g. "concurrency.overlap_with") is a leaf, whatever
    its value. Any other key is a path segment: a dict value is descended into with the segment
    prefixed, so {"concurrency": {"overlap_with": [...]}} becomes "concurrency.overlap_with".
    """
    found: list[str] = []

    def walk(node: dict[str, Any], prefix: str) -> None:
        for key, value in node.items():
            path = f"{prefix}{key}"
            if path in known or not isinstance(value, dict):
                found.append(path)
            else:
                walk(value, f"{path}.")

    walk(flags, "")
    return found


def validate_flags(flags: dict[str, Any], known: set[str]) -> None:
    unknown = [path for path in flag_paths(flags, known) if path not in known]
    if unknown:
        raise UnknownFlagError(unknown)


class InvalidPayloadError(ValueError):
    pass


@lru_cache(maxsize=None)
def _validator(schema_path: str) -> Draft202012Validator:
    schema = json.loads((REGISTRY_DIR.parent / schema_path).read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_payload(claim_type: str, schema_path: str | None, payload: dict[str, Any]) -> None:
    """Reject payloads that do not match the claim type's schema in slice0/schemas (no invented fields)."""
    if not schema_path:
        return
    errors = sorted(_validator(schema_path).iter_errors(payload), key=lambda e: list(e.path))
    if errors:
        raise InvalidPayloadError(f"{claim_type} payload invalid: {errors[0].message}")
