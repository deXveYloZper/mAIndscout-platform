# Golden eval (`python -m maindscout eval`)

**Status:** built
**Slice / milestone:** Slice 0 / Milestone G
**Code:** `core/maindscout/evals/golden.py`, command in `core/maindscout/__main__.py`

## What
One command that runs every PDF in the test folder (`~/Downloads/test_artifacts` unless `--folder` says otherwise) through the real pipeline (real model) and checks the result against the golden oracles in `slice0/evals/golden/` and against general invariants for every CV. It writes a report that a human uses to decide the Slice 0 gate.

## Why
"If the screens look finished and any of those cases fail, Stage 0 is not done" (STAGES). The gate needs evidence from real files, not from a UI that looks right.

## How
- **Throwaway database** `maindscout_eval`, recreated each run; dev data is never touched. Original files go to a temporary folder deleted afterwards.
- **Oracles:** each `must` / `must_not` key is a named check. Unknown key: **NOT CHECKED** (turns the verdict RED). File not in the folder: **NOT RUN**. Keys about later slices: **INFO**.
- **Premise check:** an OCR oracle assumes the file's text layer is garbled. If none of the garbled identifiers it names are in this copy of the file, the flag check is NOT RUN with the reason, never PASS.
- **Mobility:** `mobility_facts_when_extracted` is a real check since Slice 1 step 1 (residence countries, sponsorship, relocation).
- **Eval date:** an oracle's `as_of_eval` pins "today" for that file (Procure Ai: 2026-09-04).
- **Every CV:** processed; nothing approved without a human; has a career history; has a name or an identity note; every snippet is exactly at its location; span failures at most 40%; no appearance or protected attributes; a band and a reason (never a number) on every job. Plus: **no two different people merged** (copies of the same CV may rightly be one person; two different names on one record fail). Pieced snippets are checked piece by piece.
- **File matching:** an oracle finds its file by exact name, else by the person's name; the words every CV file shares ("CV", "resume", numbers) are ignored, so "CV - Dmitry Chernyshov" no longer matches another Dmitry.
- **Slice 1 gate checks** (case `slice-1-gate`): no composite on any pair or snapshot; gap table is rows, never a number; mobility never excludes anyone; typing a missing must-have moves the band and the reason (then rejecting moves it back); a pair cannot be deleted. Acts are rolled back with the eval database.
- **Slice 2 gate checks** (case `slice-2-gate`): on copies of the real jobs, distinctive tokens do not pull generalists into priority; sourced people get the same band and reason as uploaded; a campaign stops at its cap; **nothing sends mail** (since Slice 4 the desk writes drafts into the user's own mailbox; no route or mailbox call sends one).
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

## Latest run (2026-10-08, real files)
RED: 401 PASS, 6 FAIL, 0 NOT CHECKED, 7 NOT RUN, 3 INFO over 43 files (41 CVs) for $0.28. The six FAILs are two known cases, both open: an image-only CV (three checks; it needs a vision reader, which no slice has opened yet) and Veljko's concurrency oracle (three checks; waiting on the owner's decision about the oracle). The same run's fixes are in the [log](../LOG.md). Reports stay local (`core/eval-reports/`, git-ignored).

## Known limits
- Two golden people (Nir, Dmitry) are not in the test folder; their cases are NOT RUN. The garbled-email case is covered only by synthetic tests.
- Each run costs a few cents to about $0.30 (43 files) and a few minutes.
