# Slice 1 gate readiness (prepared 2026-10-03)

Every item in the Slice 1 gate ([PLAN.md](PLAN.md), "Gate to unlock Slice 2") with its evidence. **This page does not declare the gate.** Only the owner does, in [../decisions/](../decisions/) (draft at the end).

Evidence run: `python -m maindscout eval --with-tests` on 2026-10-03 → **GREEN**, 135 checks: 119 pass, 0 fail, 0 not checked, 13 not run (golden people absent), 3 info; automated tests 156 passed. Summary: [../evals/2026-10-03-golden-summary-slice1.md](../evals/2026-10-03-golden-summary-slice1.md). Cockpit end to end: 20 passed.

## Gate items

| Gate item | State | Evidence |
|---|---|---|
| Catalyst folder still cannot emit a composite | Met | Eval `slice-1-gate / no composite score on any pair`: 22 pairs on real files, all a band and a reason; 22 breakdown snapshots, none with a value. The database refuses any score value (`score_value_reserved`; `tests/test_coverage.py`). Triage oracles still pass. |
| Gap table, not a single number, is the default view | Met | Names on the job page open the gap table (e2e "a person on a job opens as a gap table, with no overall score"); eval `gap table is rows, never a single number`. |
| Bianca is not auto-excluded for Romania | Met in substance; Bianca's file absent | Eval `residence, visa, relocation never exclude anyone`: 33 mobility rows across 11 real CVs and 2 ads, all evidence or ask, no band reason mentions place. Synthetic Romania case: `tests/test_requirements.py::test_mobility_never_decides_a_band` (priority) and `tests/test_gaps.py::test_living_elsewhere_is_a_question_never_a_conflict`. Triage takes no location at all. |
| Approving a missing-skill fact can move a band; the reason updates | Met | Eval `approving a missing skill moves the band and updates the reason` on a real do-not-submit person (→ priority, `supported:insar`, → back on reject, both in history); `tests/test_api.py` (typed, rejected, override sticks, job requirement change); e2e "recording a missing must-have as a fact moves the band". |
| A pair cannot be deleted | Met | Database trigger `candidate_job_no_delete` (erasure the only exception); eval `a pair cannot be deleted` (refused on real data); `tests/test_api.py::test_a_pair_cannot_be_deleted` (no route, direct delete refused). |

## What Slice 1 delivered (for the record)
1. Richer job requirements: experience years, education level, languages; residence / visa / relocation as three facts ([ADR](../decisions/2026-10-02-richer-requirements.md)).
2. Gap table per person on a job: evidence / missing / conflict / ask, with reasons, snippets and approval state.
3. Re-triage after every human act, with an append-only band history.
4. Pair states with reasons (seen / submitted / we passed / reopen); permanent pairs ([ADR](../decisions/2026-10-02-pair-states.md)).
5. Coverage floor in words; reserved score snapshots with value forced empty.
6. These checks in the eval.

Fixed along the way: span offsets after ligatures, alias matching inside words, slash alternatives, mobility reliability, re-reads creating duplicate jobs and keeping stale proposals, history ordering.

## Decisions the owner is asked to make
1. Accept Bianca's case as covered by the general check on 11 real CVs and the synthetic Romania tests (her file is not in `test_artifacts`).
2. Accept the coverage floor at 60% of must-haves (a constant for now).

## Draft decision (copy to `docs/decisions/<date>-slice-1-gate.md` if you agree)

> **Slice 1 gate: GREEN.** Declared by deXveYloZper on <date>.
> Eval: `python -m maindscout eval --with-tests` → GREEN (`docs/evals/2026-10-03-golden-summary-slice1.md`); cockpit e2e 20 passed; CI green.
> Accepted holes: Bianca's file absent (covered by the mobility check on 11 real CVs and synthetic tests); coverage floor fixed at 60%.
> Slice 2 (sourcing feeder) may start, or Slice 3 (Brief) if inbound volume is already enough, as ROADMAP allows.
