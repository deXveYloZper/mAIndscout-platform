# Sign-off: Slice 0 Milestones A–D

**Date:** 2026-10-02
**Decision:** signed off by the owner (deXveYloZper), who instructed Claude to record it if the review recommended it.
**Scope:** milestones only. The **Slice 0 gate** in [../slice-0/GATES.md](../slice-0/GATES.md) stays open until E, F and G are done and the owner declares it green.

## Evidence
- `python -m pytest slice0/domain/test_reconcile.py`: 8 passed.
- `cd core && python -m pytest`: 83 passed, 15 skipped (live tests). A clean virtual environment without the real files gives 70 passed, 6 skipped.
- `RUN_LIVE=1 python -m pytest tests/test_live_artifacts.py`: 15 passed against all 11 CVs and 2 job ads in `test_artifacts` (Grok, about $0.07).
- CI workflow `.github/workflows/tests.yml` added. The repo is private and the result could not be read from here; the owner should check the first run on GitHub → Actions.

## Review against the handoff

| Milestone | Required | Result |
|---|---|---|
| A | Vendor `slice0/`; reconcile green; registries seeded; unknown flags rejected | Met. Flag keys are also checked against the subject type, for new claims and flag updates |
| B | Unpartitioned tables incl. pair with band and reason; org on every table | Met. Bands and statuses enforced by the database; a numeric band cannot be stored |
| C | Store bytes, hash, reuse by hash; text layer and PDF links; `needs_vision` only | Met as functions. HTTP route moved to E (see ADR) |
| D | Extract, typed span check blocks claims, reconcile, atomic commit, OCR identifiers excluded from keys, coarse triage | Met as functions. Live run passes. HTTP route moved to E |

Handoff section 4 rules: 1-10, 12, 13 and 15 hold and are tested. 11 (erasure) is Milestone F; 14 (Inbox default) is Milestone E.

## Fixed during the review
- No CI existed (a gate item): added.
- Two flag updates bypassed the writer's checks: now go through `writer.set_flags`.
- Name-match lookup scanned every name in the org: now filtered in SQL.

## Accepted holes (carried forward, none touch identity keys or Catalyst-as-priority)
1. HTTP routes for C and D come with Milestone E ([ADR](2026-10-02-workspace-interface.md)).
2. `intelligence/` uses typed arguments rather than the JSON Workspace DTO (same ADR).
3. "Distinctive" requirements are chosen by the model under a pinned prompt; re-run the live test after any prompt or model change ([ADR](2026-10-02-extraction-model.md)).
4. Golden cases for people not in `test_artifacts` (Veljko, Nir, Bianca, Dmitry) are not exercised; the live test applies the general invariants to every CV instead. The `test_artifacts` copy of Jure's CV has a clean text layer, so the garbled-email case is covered only by synthetic tests.
5. Span failures are stored in the run manifest, not a table.
