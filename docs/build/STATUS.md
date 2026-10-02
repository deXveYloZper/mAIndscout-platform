# Status

Single page: what exists, what is next. A–D sign-off and accepted holes: [../decisions/2026-10-02-milestones-a-d-signoff.md](../decisions/2026-10-02-milestones-a-d-signoff.md). Slice gates are declared green by a human only, in [../decisions/](../decisions/).

**Current slice:** 0, ingest + job-first triage ([handoff](../slice-0/HANDOFF.md), [gates](../slice-0/GATES.md))

| Milestone | What | State |
|---|---|---|
| A | Vendor `slice0/`, reconcile tests green | **signed off** 2026-10-02 |
| B | Persistence | **signed off** 2026-10-02 |
| C | Upload + text layer | **signed off** 2026-10-02 (HTTP route moved to E) |
| D | Extract, span check, commit, triage | **signed off** 2026-10-02 (HTTP route moved to E) |
| E | HTTP API + cockpit | **signed off** 2026-10-02 ([record](../decisions/2026-10-02-milestone-e-signoff.md)) |
| F | Erasure + verify | built 2026-10-02 (13 tests, checked by hand); awaiting human sign-off |
| G | Golden folder | partly covered by the live test (`tests/test_live_artifacts.py`). `test_artifacts` holds 11 CVs and 2 job ads. Rule going forward: every CV must pass the invariants; the golden JSON files apply where the person is present (Jure) |

How to run everything locally: [connections/cockpit-api.md](connections/cockpit-api.md).

Also pending: website ↔ platform contracts ([connections/website.md](connections/website.md)).
