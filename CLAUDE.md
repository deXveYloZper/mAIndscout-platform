# CLAUDE.md — mAIndScout Slice 0

You are implementing Slice 0 of mAIndScout. This file is the session contract. The product vision is in `docs/VISION.md`. The build order is in `docs/ROADMAP.md`. You implement only what `docs/slice-0/HANDOFF.md` and `docs/slice-0/GATES.md` allow.

## Read first, in this order

1. `docs/INDEX.md`
2. `docs/slice-0/HANDOFF.md`
3. `docs/slice-0/GATES.md`
4. `docs/decisions/2026-09-06-job-first-attention.md`
5. `slice0/README.md`

Do not implement `01`–`05` as a sprint. Open `05` only when a mechanism in the handoff is disputed. Where `05` revises `01`–`04`, `05` wins.

## What Slice 0 is

A recruiter opens a job, drops CVs onto that job, and sees people in three piles: `priority`, `review_later`, `do_not_submit`. Facts are extracted for everyone and tied to a snippet. The Inbox default is priority people on the open job, with three cards only: `revision_diff`, `duplicate_stint`, `contradiction`. Official facts change only through approve, reject, or a human-typed correction. A person can be erased; the verify query fails out loud if anything remains.

A band is not a score. Catalyst-style domain miss is `do_not_submit`. Country mismatch never by itself produces `do_not_submit`.

## Architecture

```
cockpit  →  api/  →  database
              ↑
         intelligence/     (pure: workspace in, staged claims out)
```

- `intelligence/` never opens a database session.
- `api/` is the only writer of claims, observations, evidence, decisions, identity keys, pairs, bands.
- Identity matching reads live claims in the same transaction as the write. No materialized view. No backfill script.
- Do not invent fields outside `slice0/schemas`. Unknown flag keys are rejected on write.

## Build order

One milestone at a time. Finish tests before the next.

- A — vendor `slice0/` and keep `pytest slice0/domain/test_reconcile.py` green (8 cases)
- B — unpartitioned persistence (document, artifact, candidate, job, candidate_job + triage_band, claim, observation, evidence, decision)
- C — upload + text layer. No vision model. `needs_vision` flag only
- D — extract, typed span check, reconcile, commit, coarse triage if `job_id` supplied
- E — cockpit: jobs first, three piles, three cards
- F — single-subject erasure + verify
- G — golden folder. A run that keys on `domainko@gmail.com` or bands Catalyst as `priority` fails CI

## Forbidden until a later slice is opened in writing

Brief, mail, ATS, web sourcing, Temporal, LangGraph, critic, embeddings, vision/OCR model, composite fit score, dual official/provisional scoring, new claim types.

## Done

`docs/slice-0/GATES.md` is the checklist. Pretty UI with a failed identity-key or Catalyst-as-priority case is not done. Only a human records the green gate in `docs/decisions/`.

## Documentation is part of done

Docs live in `docs/build/` (start at its README). In the same commit as any change: update the component page (what, why, how, depends on, used by), `ARCHITECTURE.md`, `STATUS.md`, any affected `connections/` page, and add one line to `LOG.md`. Non-obvious choices get an ADR in `docs/decisions/`. A change without its docs is not done.

## Branches

Commit to `development`. Merge to `main` only when the owner asks.
