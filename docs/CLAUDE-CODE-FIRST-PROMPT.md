# First message to paste into Claude Code

Attach this repo (or the zip, unpacked at the repo root) and send:

---

Read `CLAUDE.md`, then `docs/slice-0/HANDOFF.md` and `docs/slice-0/GATES.md`. Implement Milestone A only.

Milestone A: vendor the existing `slice0/` contracts into this repo and make `pytest slice0/domain/test_reconcile.py` pass in CI (8 cases). Do not invent schemas. Do not start Milestone B. Do not implement Features from `02-feature-specifications.md`. Do not add Brief, mail, scores, sourcing, Temporal, or a vision model.

When A is green, stop and list the exact files changed and the pytest command.

---

After A is green, next message:

---

Milestone B only, per `docs/slice-0/HANDOFF.md`. Unpartitioned Postgres tables for org, document, artifact, run, candidate, job, candidate_job (pair + triage_band + triage_reason), claim, observation, evidence, decision. `api/` is the only writer. No materialized identity view. Stop when migrations exist and a smoke write path is tested. Do not build the cockpit.
---
