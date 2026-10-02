# Golden eval (`python -m maindscout eval`)

**Status:** built
**Slice / milestone:** Slice 0 / Milestone G
**Code:** `core/maindscout/evals/golden.py`, command in `core/maindscout/__main__.py`

## What
One command that runs every PDF in `test_artifacts` through the real pipeline (real model) and checks the result against the golden oracles in `slice0/evals/golden/` and against general invariants for every CV. It writes a report that a human uses to decide the Slice 0 gate.

## Why
"If the screens look finished and any of those cases fail, Stage 0 is not done" (STAGES). The gate needs evidence from real files, not from a UI that looks right.

## How
- **Throwaway database** `maindscout_eval`, recreated each run; dev data is never touched. Original files go to a temporary folder deleted afterwards.
- **Oracles:** each `must` / `must_not` key is a named check. Unknown key: **NOT CHECKED** (turns the verdict RED). File not in the folder: **NOT RUN**. Keys about later slices (e.g. mobility as three facts): **INFO**.
- **Premise check:** an OCR oracle assumes the file's text layer is garbled. If none of the garbled identifiers it names are in this copy of the file, the flag check is NOT RUN with the reason, never PASS.
- **Eval date:** an oracle's `as_of_eval` pins "today" for that file (Procure Ai: 2026-09-04).
- **Every CV:** processed; nothing approved without a human; has a career history; has a name or an identity note; every snippet is exactly at its location; span failures at most 40%; no appearance or protected attributes; a band and a reason (never a number) on every job. Plus: one person per CV (no merges).
- **Verdict:** GREEN only with zero FAIL and zero NOT CHECKED. `--with-tests` adds the pytest result.
- **Reports:** `core/eval-reports/golden-<time>.md` names the files (git-ignored, real people); `…-summary.md` hides file names and emails and can be committed (see [../../evals/](../../evals/)).

## Depends on
[process.md](process.md), [intelligence.md](intelligence.md), [persistence.md](persistence.md), the oracles in [contracts.md](contracts.md).

## Used by
The owner, to decide the Slice 0 gate ([../../slice-0/GATES.md](../../slice-0/GATES.md)).

## Tests
`core/tests/test_golden_harness.py`: file matching; missing file is NOT RUN; unknown key is RED; every shipped oracle key has a check; the summary hides emails.

## Result on 2026-10-02
GREEN: 114 PASS, 0 FAIL, 0 NOT CHECKED, 13 NOT RUN, 3 INFO; tests 114 passed; cost $0.06. The first run was RED on two items: Catalyst's work locations were not captured (fixed: job ads now yield work-location facts), and Jure's OCR oracle was applied to a different copy of his CV with a clean text layer (now reported as premise absent). Summary: [../../evals/2026-10-02-golden-summary.md](../../evals/2026-10-02-golden-summary.md).

## Known limits
- Four golden people (Veljko, Nir, Bianca, Dmitry) are not in `test_artifacts`; their cases are NOT RUN. The garbled-email case is covered only by synthetic tests.
- Each run costs a few cents and about two minutes.
