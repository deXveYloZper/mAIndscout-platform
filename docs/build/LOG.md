# Build log

Newest first. One line per merge to `development`: date, what, link to the component page.

- 2026-10-03 — **I1 gate GREEN**, declared by the owner; I2 starts — [decision](../decisions/2026-10-03-i1-gate.md)
- 2026-10-03 — I1 part 2: background task queue (SKIP LOCKED, retries, dedupe) with workers in `serve`; uploads read in the background with live progress; cost ledger, monthly budget and Costs page; erasure unlinks cost rows — [tasks-and-costs](components/tasks-and-costs.md)
- 2026-10-03 — I1 part 1: companies as shared records (public tier), exact-match resolver, "Same company?" cards, links from career steps and jobs, company pages with who we know there — [companies](components/companies.md)
- 2026-10-03 — Intelligence track proposed (candidate career strength, company intelligence, hiring profiles, matching v2, sourcing v2) to come before further slices; waiting for the owner's decisions — [plan](../intelligence/PLAN.md)
- 2026-10-03 — Slice 2: sourcing feeder from the desk's own people (campaigns, cap / target / stop, same triage, "Find more people"); Slice 2 gate checks in the eval, all passing — [sourcing](components/sourcing.md)
- 2026-10-03 — **Slice 1 gate GREEN**, declared by the owner; Slice 2 (sourcing) chosen next — [decision](../decisions/2026-10-03-slice-1-gate.md)
- 2026-10-03 — Slice 1 step 6: the five Slice 1 gate checks run in the golden eval on real files (all pass); gate readiness page with draft declaration — [readiness](../slice-1/GATE-READINESS.md)
- 2026-10-02 — Slice 1 step 5: coverage floor (counts in words, never a percentage), reserved `score` snapshots with value forced NULL by the database — [coverage](components/coverage.md)
- 2026-10-02 — Slice 1 step 4: pair states with reasons (seen / submitted / we passed / reopen), outcomes, pairs made permanent by a database trigger (erasure the only exception) — [ADR](../decisions/2026-10-02-pair-states.md)
- 2026-10-02 — Slice 1 step 3: re-triage after every human act, band history (`pair_event`, migrations 0003/0004), "They have …" on missing skills; erasure removes pair history — [review](components/review.md), [gap-table](components/gap-table.md)
- 2026-10-02 — Slice 1 step 2: gap table (domain, API, cockpit, default view of a person on a job). Fixed on the way: span offsets after ligatures (snippets were shifted), "js" matching inside "next.js", slash alternatives, vague tokens, mobility reliability (5/5), a forced re-read creating a second job and keeping stale proposals — [gap-table](components/gap-table.md)
- 2026-10-02 — Slice 1 step 1: richer job requirements (years, education, languages) and mobility as three facts; golden mobility check live and passing on the Procure Ai ad — [ADR](../decisions/2026-10-02-richer-requirements.md)
- 2026-10-02 — **Slice 0 gate GREEN**, declared by the owner; fresh eval GREEN with the new model key — [decision](../decisions/2026-10-02-slice-0-gate.md)
- 2026-10-02 — Thorough Slice 0 testing: CI root cause fixed; 17 end-to-end tests; 14 UX fixes incl. unassigned pool, live upload progress, type-a-name, all-jobs inbox — [test report](../slice-0/TEST-REPORT.md)
- 2026-10-02 — Milestone G: golden eval command and report; job ads now yield work-location facts; gate readiness page — [golden-eval](components/golden-eval.md), [readiness](../slice-0/GATE-READINESS.md)
- 2026-10-02 — Milestone F: erasure with verify, suppression of re-ingest, cockpit control; triage counts a must-have word inside a longer skill; Milestone E signed off — [erasure](components/erasure.md)
- 2026-10-02 — Milestone E part 2: cockpit (jobs, job bands, person, inbox cards, file proxy); cockpit build in CI — [cockpit](components/cockpit.md), [cockpit → API](connections/cockpit-api.md)
- 2026-10-02 — Milestone E part 1: HTTP API, review acts, inbox and page read models, contradiction cards, payload schema validation on every write — [http-api](components/http-api.md), [review](components/review.md)
- 2026-10-02 — Review fixes (CI, guarded flag updates); Milestones A–D signed off by the owner — [sign-off](../decisions/2026-10-02-milestones-a-d-signoff.md)
- 2026-10-02 — Milestone D: Grok extraction, typed span check, contact checks, identity, triage, process_document — [intelligence](components/intelligence.md), [process](components/process.md), [ADR](../decisions/2026-10-02-extraction-model.md)
- 2026-10-02 — Milestone C: upload by hash, text-layer extraction, links, needs_vision flag — [ingestion](components/ingestion.md)
- 2026-10-02 — Milestone B: schema, migration 0001, registries seeded, guarded claim write — [persistence](components/persistence.md), [writer](components/writer.md), [ADR](../decisions/2026-10-02-core-stack.md)
- 2026-10-02 — Platform repo created; blueprint vendored; build documentation system set up.
- 2026-10-02 — Milestone A: reconcile tests green (8 passed) — [contracts](components/contracts.md)
