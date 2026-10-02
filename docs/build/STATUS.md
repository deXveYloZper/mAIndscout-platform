# Status

Single page: what exists, what is next. A–D sign-off and accepted holes: [../decisions/2026-10-02-milestones-a-d-signoff.md](../decisions/2026-10-02-milestones-a-d-signoff.md). Slice gates are declared green by a human only, in [../decisions/](../decisions/).

**Slice 0 gate: GREEN**, declared by the owner on 2026-10-02 ([decision](../decisions/2026-10-02-slice-0-gate.md)). Slice 1 may start.

**Current slice:** 1, defendable match ([plan](../slice-1/PLAN.md))

| Step | What | State |
|---|---|---|
| 1 | Richer job requirements; mobility as three facts | done 2026-10-02 |
| 2 | Gap table per person on a job | next |
| 3 | Re-triage when a fact the band depends on is approved | |
| 4 | Pair states; a pair can never be deleted | |
| 5 | Reserved score breakdown shape; coverage floor | |
| 6 | Slice 1 gate evidence in eval and e2e | |

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
