# ADR: pair states are separate from bands; pairs are permanent in the database

**Date:** 2026-10-02 · **Status:** accepted (Slice 1 step 4, owner said "go")

## Decision
1. A person-job pair has two independent values:
   - **band** (`priority` / `review_later` / `do_not_submit`): where the machine, or a human override, places the person. Recomputed from facts (step 3).
   - **state** (`new` → `seen` → `submitted` | `we_passed`, reopen back to `seen`): the recruiter's progress. Only humans move it.
   The Slice 1 plan's list "seen, priority, review_later, we_passed, submitted" mixes the two; priority and review_later already exist as bands.
2. Moves need reasons where they matter: `we_passed` needs a reason code (skills, seniority, location, compensation, candidate not interested, client rejected, duplicate, other); `submitted` needs a note; reopening needs a note. The outcome is kept on the pair and every move is a `pair_event` (kind `state`).
3. **A pair is never deleted.** A database trigger refuses `DELETE` on `candidate_job` unless the transaction has set `maindscout.erasure = 'on'`, which only the erasure workflow does. There is no delete route.

## Why
Vision: "A pair is permanent. You never delete the match. You move it. Outcomes have reasons." Enforcing permanence in the database means no future code path can silently drop a pair; erasure (a legal obligation) is the single, explicit exception.

## Consequences
- Pass reasons are structured data for later learning (blueprint F10), not free text.
- Later states (interviewing, offer, placed) extend the same column and history; the check constraint is widened by migration.
