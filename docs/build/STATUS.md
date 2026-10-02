# Status

Single page: what exists, what is next. Slice gates are declared green by a human only, in [../decisions/](../decisions/).

**Current slice:** 0, ingest + job-first triage ([handoff](../slice-0/HANDOFF.md), [gates](../slice-0/GATES.md))

| Milestone | What | State |
|---|---|---|
| A | Vendor `slice0/`, reconcile tests green | done (8 passed, 2026-10-02); awaiting human sign-off |
| B | Persistence | done (17 tests passing, 2026-10-02); awaiting human sign-off |
| C | Upload + text layer | done (48 tests; all 13 test files extract, 2026-10-02); awaiting human sign-off |
| D | Extract, span check, commit, triage | done (82 tests; live run over all 13 files passes, 2026-10-02); awaiting human sign-off. Not yet over HTTP |
| E | Cockpit | not started |
| F | Erasure + verify | not started |
| G | Golden folder | partly covered by the live test (`tests/test_live_artifacts.py`). `test_artifacts` holds 11 CVs and 2 job ads. Rule going forward: every CV must pass the invariants; the golden JSON files apply where the person is present (Jure) |

Also pending: website ↔ platform contracts ([connections/website.md](connections/website.md)).
