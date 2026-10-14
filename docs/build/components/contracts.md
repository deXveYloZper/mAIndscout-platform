# Contracts (vendored from the blueprint)

**Status:** built; every claim write is checked against `slice0/schemas` and the registries; 8 reconcile tests pass
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

## Changes since vendoring
- 2026-10-02: `job_requirement_claim.schema.json` extended with optional `mobility`, `min_years`, `education_level`, `language` and category `language` ([ADR](../../decisions/2026-10-02-richer-requirements.md)). All Slice 0 payloads stay valid.
- 2026-10-03: company claims for research (`company_domain`, `company_type`, `company_founded`, `funding_round`, `team_size`, `company_status`, `company_location`; [company-research](company-research.md)) and `step_classification` ([career-profiles](career-profiles.md)); later the same day, hiring-profile fields on job requirements ([hiring-profiles](hiring-profiles.md)).
- 2026-10-04: `brief_answer` ([brief](brief.md)).
- 2026-10-06: `preference` ([calls](calls.md)).
- `slice0/api/openapi.yaml` is kept as the original Slice 0 target; the live API is FastAPI's own (served at `/docs`, see [http-api](http-api.md)).

## Known limits
Golden files describe expected output for CVs and JDs we do not have yet.
