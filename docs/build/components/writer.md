# Writer (`api/`) and registries

**Status:** in progress (seeding and claim write built; document, process, decision and erasure writes come in later milestones)
**Slice / milestone:** Slice 0 / Milestone B onward
**Code:** `core/maindscout/api/writer.py`, `core/maindscout/domain/registry.py`

## What
`api/` is the only code allowed to write to the database. Today it can seed the registries, create an org, and write a claim. `domain/registry.py` loads the claim and flag registries from YAML and checks flag keys.

## Why
One writer means the rules (known flags only, valid claim types, atomic commits) are enforced in one place. This is blueprint rule E-i1 and a Slice 0 gate item.

## How
- `seed_registries` copies `slice0/registry/*.yaml` into the registry tables, safe to run repeatedly.
- `add_claim` rejects: a flag key not in the registry (dotted keys like `concurrency.overlap_with` and the nested form are both understood), an unknown claim type, or a claim type used on the wrong subject (e.g. a skill on a job).
- `tests/test_boundaries.py` fails if `domain/` or `intelligence/` ever call database write methods or import the database.

## Depends on
- [persistence.md](persistence.md): the tables.
- [contracts.md](contracts.md): the registry YAML.

## Used by
Later: upload, process, cockpit routes, erasure.

## Tests
`core/tests/test_registry.py`, `core/tests/test_writer.py`, `core/tests/test_boundaries.py`.

## Known limits
Flag validation is in application code, not a database trigger, so it holds only because `api/` is the sole writer.
