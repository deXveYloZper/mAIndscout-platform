# Status

Single page: what exists, what is next. A–D sign-off and accepted holes: [../decisions/2026-10-02-milestones-a-d-signoff.md](../decisions/2026-10-02-milestones-a-d-signoff.md). Slice gates are declared green by a human only, in [../decisions/](../decisions/).

**Slice 0 gate: GREEN**, declared by the owner on 2026-10-02 ([decision](../decisions/2026-10-02-slice-0-gate.md)). Slice 1 may start.

**Slice 1 gate: GREEN**, declared by the owner on 2026-10-03 ([decision](../decisions/2026-10-03-slice-1-gate.md)).

**Now:** the [intelligence track](../intelligence/PLAN.md), accepted 2026-10-03 ([decisions](../decisions/2026-10-03-intelligence-track.md)).

| Phase | What | State |
|---|---|---|
| I1 | Companies, linking, background tasks, cost ledger | in progress: companies done; tasks and cost ledger next |
| I2 | Company research (Grok, targeted facts) | |
| I3 | Career profiles | |
| I4 | Hiring profiles | |
| I5 | Matching v2 | |
| I6 | Sourcing v2 | |

**Current slice:** 2, sourcing feeder ([plan](../slice-2/PLAN.md))

| Step | What | State |
|---|---|---|
| 1 | Desk adapter, campaigns (cap / target / human stop), same triage, cockpit "Find more people" | done 2026-10-03 |
| 2 | Slice 2 gate checks in the eval | done 2026-10-03: GREEN; waiting for the owner's declaration |
| later | External adapter (e.g. GitHub profiles) | not started: needs a data-use decision |

**Slice 1** (defendable match, closed)

| Step | What | State |
|---|---|---|
| 1 | Richer job requirements; mobility as three facts | done 2026-10-02 |
| 2 | Gap table per person on a job | done 2026-10-02 |
| 3 | Re-triage when a fact the band depends on is approved | done 2026-10-02 |
| 4 | Pair states; a pair can never be deleted | done 2026-10-02 |
| 5 | Reserved score breakdown shape; coverage floor | done 2026-10-02 |
| 6 | Slice 1 gate evidence in eval and e2e | done 2026-10-03; gate declared GREEN |

Slice 0 (ingest + job-first triage) is closed ([handoff](../slice-0/HANDOFF.md), [gates](../slice-0/GATES.md))

| Milestone | What | State |
|---|---|---|
| A | Vendor `slice0/`, reconcile tests green | **signed off** 2026-10-02 |
| B | Persistence | **signed off** 2026-10-02 |
| C | Upload + text layer | **signed off** 2026-10-02 (HTTP route moved to E) |
| D | Extract, span check, commit, triage | **signed off** 2026-10-02 (HTTP route moved to E) |
| E | HTTP API + cockpit | **signed off** 2026-10-02 ([record](../decisions/2026-10-02-milestone-e-signoff.md)) |
| F | Erasure + verify | **signed off** 2026-10-02 (with the gate) |
| G | Golden folder | **signed off** 2026-10-02 (with the gate): eval GREEN |

How to run everything locally: [connections/cockpit-api.md](connections/cockpit-api.md).

Also pending: website ↔ platform contracts ([connections/website.md](connections/website.md)).
