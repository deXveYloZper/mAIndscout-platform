# Slice 2 — Sourcing feeder

**Status: LOCKED.** Do not start until Slice 1’s gate is green.

Sourcing is not a second product. It exists to refill a thin priority queue on a live job. Every sourced document takes Slice 0 ingest + Slice 0/1 triage. No-fits park. They do not get a review session.

---

## User-visible result

On a job with fewer than N `priority` people (N operator-set; start at 5), the recruiter can start a bounded find: a query derived from the job’s must-have tokens, a cap, a stop condition.

Results land as documents on that job. Same bands. Same Inbox rule.

## In scope

- One source adapter to start (the desk’s own people graph, or one licensed external search — pick one)
- Campaign row: job_id, query, cap, spent, status (`running|stopped|exhausted`)
- Stop when cap hit, when priority queue ≥ N, or when the human stops it
- P13: a sourcing signal must not become a scoring feature
- Sourced people with `possible_ocr_identifier` still cannot be mailed

## Out of scope

- BD two-stage teasers (Slice 5)
- Autonomous outreach
- Embeddings as the ranker
- Unlicensed scraping

## Gate

- [ ] A sourced CV is indistinguishable downstream from an uploaded CV
- [ ] Campaign stops at cap
- [ ] Catalyst-like distinctive tokens do not pull software generalists into `priority`
- [ ] No mail send path

Slice 3 (Brief) may start in parallel if inbound priority volume is already enough — record that in `docs/decisions/`.
