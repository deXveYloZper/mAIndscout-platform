# Coverage floor and the reserved score

**Status:** built
**Slice / step:** Slice 1 / step 5
**Code:** `core/maindscout/domain/coverage.py` (pure), `api/process.snapshot_pair`, table `score` (migration `0006`)

## What
- **Coverage:** how many of a pair's must-have requirements rest on facts a human has approved. Below the floor (60% of must-haves), the cockpit says the picture is too thin to rely on.
- **Reserved score:** the blueprint's `score` table, stored as append-only snapshots of what the machine considered for a pair (one dimension per requirement with status, official or not, the facts used, and a weight that is always empty). The `value` column is forced to stay empty by a database rule.

## Why
Slice 1: "If official coverage is too thin, the product still refuses a composite number" and "reserved `score.breakdown` shape without shipping weights". Coverage tells the recruiter when a band rests on unreviewed machine output; the snapshots keep an audit trail of what was considered, ready for a later, deliberate scoring decision.

## How
- Must-have rows exclude mobility (it is asked, not evidenced). A row is official only when every fact behind it is approved.
- Shown as counts in words: "1 of 6 must-haves rest on approved facts: below the floor (4 needed)". Never a percentage, so it cannot be read as a fit score.
- A snapshot is written after each re-triage only when the facts or statuses behind the pair changed (`claim_set_hash`); unchanged pairs add nothing.
- `CHECK (value IS NULL)` on `score`: any attempt to store a number fails in the database. Lifting it needs a migration and a recorded decision.
- Erasure deletes a person's snapshots; verify checks none remain.

## Depends on
[gap-table.md](gap-table.md), [process.md](process.md), [persistence.md](persistence.md).

## Used by
[http-api.md](http-api.md) (`coverage` in the gap page and the job page), [cockpit.md](cockpit.md) (coverage line; "thin" tag), [erasure.md](erasure.md).

## Tests
`core/tests/test_coverage.py`: counts and words, no must-haves never claims coverage, breakdown has no weights or value, the database refuses a score value, snapshots only when facts change, coverage on the gap page and job page. e2e: the gap table shows the coverage line.

## Known limits
- The floor (0.6) is a constant; it may become a per-desk setting.
- Coverage does not change the band; it qualifies how much to trust it.
