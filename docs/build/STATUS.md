# Status

Single page: what exists, what is next. Slice gates are declared green by a human only, in [../decisions/](../decisions/).

**Current slice:** 0, ingest + job-first triage ([handoff](../slice-0/HANDOFF.md), [gates](../slice-0/GATES.md))

| Milestone | What | State |
|---|---|---|
| A | Vendor `slice0/`, reconcile tests green | done (8 passed, 2026-10-02); awaiting human sign-off |
| B | Persistence | done (17 tests passing, 2026-10-02); awaiting human sign-off |
| C | Upload + text layer | not started |
| D | Extract, span check, commit, triage | not started |
| E | Cockpit | not started |
| F | Erasure + verify | not started |
| G | Golden folder | blocked: `test_artifacts` has the Catalyst and Procure Ai JDs but different CVs (Gokhan, Ioannis, Luiz) than the golden set (Jure, Veljko, Nir, Bianca, Dmitry) |

Also pending: website ↔ platform contracts ([connections/website.md](connections/website.md)).
