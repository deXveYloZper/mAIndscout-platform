# CLAUDE.md — mAIndScout platform

You are working on the mAIndScout platform: the recruiting desk's own system of record (Python core, Next.js cockpit).
This file is the session contract. Product vision: `docs/VISION.md`. Build order and what is locked: `docs/ROADMAP.md`.
What is actually built: `docs/build/`.

## Where the build is (2026-10-12)

Slices 0–4 are built and their gates green; the intelligence track I1–I6 is built and green; Access (sign-in), Calls
(transcripts) and the desk design are built. Next is running live jobs on the desk. Slice 5 and I7 calibration wait for
real use. Details and dates: `docs/build/STATUS.md`.

## Read first, in this order

1. `docs/build/README.md` (the docs rules)
2. `docs/build/STATUS.md` and `docs/build/ARCHITECTURE.md`
3. The component pages in `docs/build/components/` for what you will touch, and the decisions they link to
4. `docs/ROADMAP.md` before starting anything new

Open `00`–`05` (the blueprint) only when a mechanism is disputed. Where `05` revises `01`–`04`, `05` wins.

## Architecture

```
cockpit  →  api/  →  database
              ↑
         intelligence/     (pure: workspace in, staged claims out)
```

- `api/` is the only writer to the database. `intelligence/` never opens a database session (`tests/test_boundaries.py`).
- Identity matching reads live claims in the same transaction as the write. No materialized view, no backfill script.

## Rules that hold everywhere

- **Belief is gated.** The machine proposes facts; only a person approves, rejects or corrects them. An approved view is
  pinned (one named exception: [approved company sizes](docs/decisions/2026-10-12-approved-size-reparse.md)).
- **Every fact has its evidence**, checked mechanically (the span check), never by trusting the prompt.
- **No invented fields.** Payloads match `slice0/schemas`; unknown flag keys are refused on write. A new claim type,
  flag or table needs its schema, its registry entry and a note in `docs/decisions/`.
- **A band or tier is never a number.** No composite fit score (`score.value` stays NULL); no dual scoring.
- **A false merge is the catastrophe.** Records of people merge automatically only on a clean shared contact with
  agreeing names; anything else becomes a card for a person.
- **Where someone lives and works now, never where they are from.** Country alone never puts anyone in
  `do_not_submit`. Never protected characteristics, appearance, personality, culture or fit.
- **Company research** asks only the fixed list of public facts: never people (names, titles), never tech stack.
- **The desk never sends mail**: drafts go into the user's own mailbox. Calls need no consent step (the call tools'
  notetakers already have it).
- **Model calls cost the owner money.** Tests and e2e use fakes or recordings (`LLM_REPLAY`); keep `RESEARCH_AUTO=false`
  while testing; run paid checks only when the owner has agreed to them.
- **Secrets and real data stay out of git**: `core/.env`, `cockpit/.env.local`, real CVs, `core/eval-reports/`,
  `core/.llm-recordings/`. Never print an API key.

## Still locked

Until opened in writing in `docs/decisions/`: Slice 5 (critic, embeddings, BD two-stage), a vision/OCR model (scans
stay flagged `needs_vision`), an external sourcing adapter (needs a data-use decision), a workflow engine (Temporal,
LangGraph), hosting beyond this machine (everything listens on 127.0.0.1).

## Done

Tests green (`python -m pytest` in `core/`, `npm run e2e:free` in `cockpit/`). Only the owner declares a gate green, in
`docs/decisions/`; a coding agent never does.

## Documentation is part of done

Docs live in `docs/build/` (start at its README). In the same commit as any change: update the component page (what,
why, how, depends on, used by), `ARCHITECTURE.md`, `STATUS.md`, any affected `connections/` page, and add one line to
`LOG.md`. Non-obvious choices get a note in `docs/decisions/`. A change without its docs is not done.

## Branches

Commit to `development`. Merge to `main` only when the owner asks.
