# Persistence (database schema and migrations)

**Status:** built
**Slice / milestone:** Slice 0 / Milestone B
**Code:** `core/maindscout/db/models.py`, `core/migrations/`, `docker-compose.yml`

## What
The Slice 0 Postgres tables, created by one Alembic migration (`0001`). Tables: `org`, `document`, `extraction_artifact`, `document_subject`, `candidate`, `job`, `candidate_job`, `not_same`, `intelligence_run`, `claim`, `evidence`, `claim_observation`, `decision`, `decision_item`, plus two seeded registries (`claim_type_registry`, `flag_type_registry`). Migration `0002` adds `erasure` and `suppression_registry` ([erasure.md](erasure.md)). Migration `0011` adds the coverage gate's `candidate.archived_at` / `archived_reason` / `coverage_override`, `job.open_countries` and `company.research_depth` ([coverage-gate.md](coverage-gate.md)). Migration `0010` adds `company.research_status` / `researched_at` and the public-knowledge org that owns company facts ([company-research.md](company-research.md)). Migration `0009` adds `task` (background work) and `cost_ledger` ([tasks-and-costs.md](tasks-and-costs.md)). Migration `0008` adds `company` and `company_alias` in the **shared public tier (no org id**, a deliberate exception) and `job.hiring_company_id` ([companies.md](companies.md)). Migration `0007` adds `campaign` (sourcing, counts only; [sourcing.md](sourcing.md)). Migration `0006` adds the reserved `score` table, whose `value` must stay NULL ([coverage.md](coverage.md)). Migration `0005` adds pair states with a check constraint, the `outcome` of a pair, and a trigger that refuses any delete of a pair outside erasure ([ADR](../../decisions/2026-10-02-pair-states.md)). Migrations `0003`/`0004` add `pair_event`, the append-only history of each pair, ordered by a sequence (timestamps tie inside one transaction).

## Why
Every later piece reads and writes these. The shape follows [01-system-blueprint.md](../../../01-system-blueprint.md) section D, trimmed to what Slice 0 needs, so later slices add to it rather than reshape it.

## How
- Every table has `org_id` (multi-tenant from day one). Documents are unique per org by `sha256`, so the same bytes are never stored twice.
- A **claim** is one fact. It has a status (`staged` → `proposed` → `approved` | `rejected` | `superseded`). `approved_view` is pinned at approval and never mutated.
- `claim_observation` holds per-source values; `evidence` points at a span in `extraction_artifact` (the text layer), never at raw bytes.
- `candidate_job` is the permanent pair: unique per candidate and job, with a `triage_band` restricted by the database to `priority`, `review_later`, `do_not_submit`, `unassigned`. A numeric score cannot be stored there.
- `candidate.merged_into_id` and `candidate_job.merged_into_id` are redirects: merges never rewrite history.
- Enums are enforced as CHECK constraints, so a bad value fails even if application code is wrong.
- Original bytes are not in Postgres; `document.storage_key` points to a blob store added in Milestone C.

## Depends on
- [contracts.md](contracts.md): the registries seed from `slice0/registry`.

## Used by
- [writer.md](writer.md): the only code that writes these tables.

## Contracts
Tables as defined in `models.py`. Change them only through a new Alembic migration.

## Tests
`core/tests/test_writer.py` (constraints: duplicate documents, unique pairs, band is not a number, invalid status). Run `python -m pytest` in `core/` with Postgres up.

## Known limits
- No company, suppression, or embedding tables yet (later slices). `job.hiring_company` is plain text.
- No partitioning (deliberate, see blueprint RA-06).
- The blueprint's JSON claim envelope lists claim types without `JobRequirementClaim`, while the registry includes it; the database follows the registry.
