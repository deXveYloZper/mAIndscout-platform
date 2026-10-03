"""Coverage floor and the reserved score breakdown. Pure, no database.

Coverage answers: how much of this pair's picture rests on facts a human has approved? Below the floor,
the cockpit says the picture is too thin to rely on. It is reported as counts ("2 of 6 must-haves"),
never as a percentage, so it can never be read as a fit score.

The breakdown is the shape a future score would use: one dimension per requirement, with its status and
whether it is official. Every weight is None and there is no value: Slice 1 ships no score.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

from maindscout.domain.gaps import Row

COVERAGE_FLOOR = 0.6  # share of must-have rows that must rest on approved facts
ENGINE_VERSION = "gaps.v1"


@dataclass
class Coverage:
    applicable: int  # must-have rows (mobility excluded: it is asked, not evidenced)
    official: int  # of those, rows whose facts are all approved
    needed: int  # how many official rows the floor asks for
    met: bool

    def words(self) -> str:
        if self.applicable == 0:
            return "this job has no must-have requirements to check yet"
        state = "above the floor" if self.met else f"below the floor ({self.needed} needed)"
        return f"{self.official} of {self.applicable} must-haves rest on approved facts: {state}"

    def as_dict(self) -> dict[str, Any]:
        return {"applicable": self.applicable, "official": self.official, "needed": self.needed, "met": self.met,
                "floor": COVERAGE_FLOOR, "words": self.words()}


def coverage(rows: list[Row]) -> Coverage:
    must = [r for r in rows if r.strength in ("must", "deal_breaker") and r.kind != "mobility"]
    official = sum(1 for r in must if r.official)
    needed = math.ceil(COVERAGE_FLOOR * len(must)) if must else 0
    return Coverage(len(must), official, needed, bool(must) and official >= needed)


def breakdown(rows: list[Row]) -> dict[str, Any]:
    """The reserved shape of a future score breakdown. No weights, no value."""
    return {
        "engine": ENGINE_VERSION,
        "dimensions": [
            {"requirement_id": r.requirement_id, "kind": r.kind, "strength": r.strength, "status": r.status,
             "official": r.official, "facts": sorted(f.id for f in r.facts), "weight": None}
            for r in rows
        ],
        "coverage": coverage(rows).as_dict(),
    }


def claim_set_hash(rows: list[Row]) -> str:
    """Changes whenever the facts or statuses behind the rows change; equal hashes mean nothing new to record."""
    material = [(r.requirement_id, r.status, r.official, sorted((f.id, f.status) for f in r.facts)) for r in rows]
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()[:32]
