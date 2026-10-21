# Match eval (`python -m maindscout match-eval`)

**Status:** built
**Slice / milestone:** next build, step A of [understand the hire](../../decisions/2026-10-19-understand-the-hire.md)
**Code:** `core/maindscout/evals/matching.py`, command in `core/maindscout/__main__.py`

## What
Before a change to the career-profile or matching rules goes live, it shows what the change would do to the desk's
verdicts. Everyone on the open roles (or the `--job` roles) is matched again with the code as it is now, and the result
is compared with three things:
- the verdict the desk shows;
- the owner's own decisions;
- hand labels.

## Why
The owner, 2026-10-19: "what we do not want is to have worse results once this is implemented", and "each step should
be properly evaluated before building the next layer". Rules that looked right in code had produced wrong strong
matches on a real role.

## How
- For each pair it does what re-matching does (`process._match_now`), with a career profile built afresh
  (`profile.build`), because a stored profile was built with the rules of its day.
- Nothing is written: the session is rolled back. It is free: no model and no search calls.
- **Moves:** a person whose tier changes is listed with the requirement rows that changed, old against new. People
  whose rows changed but not their tier are counted (`--quiet N` lists them).
- **Checks:**
  - The owner's decisions from the Sourcing tab: reaching out or further means the person should be strong; "not for
    this role" means they should not; "maybe later" is not counted.
  - Hand labels from `core/eval-reports/match-labels.json` (git-ignored, because it names people): `job_id`,
    `candidate_id`, `expect` (`strong` or `not_strong`), `why`.
  - Each check is shown agreeing now and after. FIXED or WORSE marks a change. The command exits 1 when anything gets
    worse.
- **The routine:**
  1. Run it before a change. It must report no moves, which shows the stored verdicts are current.
  2. Make the change and run it again.
  3. Explain every move, and apply only when the moves are the intended ones.
  4. A rolled-back what-if script can try a changed requirement the same way (step A tried "up to 500 people").

## Depends on
- [matching](matching.md), [career profiles](career-profiles.md), [process](process.md) (`pair_inputs`, `_triage_now`,
  `preference_rows`), [outreach](outreach.md) (`stage`).

## Used by
- Every change to `domain/profile.py` or `domain/matching.py` (rule in `CLAUDE.md`).

## Tests
- `tests/test_sizes_and_jobs.py::test_the_match_eval_reads_the_owners_own_decisions`.
- The baseline run on the real desk, before step A, reported 0 moves on all three open roles.

## Known limits
- Only verdicts are compared, not the order within a band.
- A wording change shows as a changed row: step A's baseline found 49 rows on Procure AI still carrying older words
  ("at startup"), and years differing by 0.1 as the month moved on.
