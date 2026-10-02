# Contracts (vendored from the blueprint)

**Status:** built (vendored); 8 reconcile tests pass; not yet implemented against
**Slice / milestone:** Slice 0 / Milestone A
**Code:** `slice0/`

## What
Executable specs for Slice 0: JSON Schemas for the claim types, claim and flag registries, the pure `reconcile.py` career-step function with fixtures and tests, the workspace DTO, the OpenAPI file, and golden expected-results files.

## Why
Code must conform to these. Inventing a field not in `schemas/` or `registry/` is a spec change (see [slice0/README.md](../../../slice0/README.md)).

## How
Copied unchanged from the blueprint on 2026-10-02. `reconcile.py` is pure Python with no database.

## Depends on
Nothing.

## Used by
Every later component: persistence, `intelligence/`, `api/`, cockpit.

## Tests
`pytest slice0/domain/test_reconcile.py`, expected 8 passing.

## Known limits
Golden files describe expected output for CVs and JDs we do not have yet.
