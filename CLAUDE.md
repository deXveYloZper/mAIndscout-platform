# CLAUDE.md — mAIndScout platform

You are working on the mAIndScout platform: the recruiting desk's own system of record (Python core, Next.js cockpit).
This file is the session contract. Product vision: `docs/VISION.md`. Build order and what is locked: `docs/ROADMAP.md`.
What is actually built: `docs/build/`.

## Where the build is (2026-10-12)

Slices 0–4 are built and their gates green; the intelligence track I1–I6 is built and green; Access (sign-in), Calls
(transcripts) and the desk design are built. The next build ([plan](docs/next/PLAN.md)): phase 1, the sourcing engine
with Exa, is built and waits for its first real role (its gate is the owner's); phases 2–6 are drafts. Slice 5 and I7
calibration wait for real use. Details and dates: `docs/build/STATUS.md`.

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
- **Company research** asks only the fixed list of public facts: never people (names, titles), never tech stack. A
  company's stack, tools and methods are read only from its own job adverts, each with its advert as evidence
  ([employer evidence](docs/decisions/2026-10-17-evidence-for-strong-matches.md)): "likely" for its people, never proof.
- **The desk never sends mail** or LinkedIn messages: drafts go into the user's own mailbox, or are copied by the
  owner. Calls need no consent step (the call tools' notetakers already have it).
- **Sourcing** ([decision](docs/decisions/2026-10-12-sourcing-engine.md)): people found on the web are public data only,
  a guide to contact them, read through the CV path with every value quoted; never a photo. Searches name roles,
  companies and places, never a person, with one exception: a strong match found on the web gets an evidence check
  that may search their name with their company (owner, 2026-10-17). Off-limits companies and "stop" win; "stop" and
  erasure win over everything.
  The talent-release radar quotes company news only, never a person's name. Keep `SOURCING_AUTO=false`,
  `EVIDENCE_AUTO=false` and `PRACTICES_AUTO=false` while testing with real keys.
- **A rule change is measured before it goes live** (owner, 2026-10-19: "what we do not want is to have worse results"):
  `python -m maindscout match-eval` re-matches stored people with the new code (free, rolled back). With the code
  unchanged it must report no moves; after the change every move is explained, and the owner's own decisions and
  the labels in `core/eval-reports/match-labels.json` must not get worse ([match eval](docs/build/components/match-eval.md)).
- **Model and Exa calls cost the owner money.** Tests and e2e use fakes or recordings (`LLM_REPLAY`); keep
  `RESEARCH_AUTO=false` while testing; run paid checks only when the owner has agreed to them.
- **Secrets and real data stay out of git**: `core/.env`, `cockpit/.env.local`, real CVs, `core/eval-reports/`,
  `core/.llm-recordings/`. Never print an API key.

## Still locked

Until opened in writing in `docs/decisions/`: Slice 5 (critic, embeddings, BD two-stage), a vision/OCR model (scans
stay flagged `needs_vision`), sourcing sources beyond Exa's public profiles and news (opened 2026-10-12; GitHub may
point to a person, never be a contact source), a workflow engine (Temporal, LangGraph), hosting beyond this machine
(everything listens on 127.0.0.1), and phases 2–6 of the next build until the owner approves each.

## Done

Tests green (`python -m pytest` in `core/`, `npm run e2e:free` in `cockpit/`). Only the owner declares a gate green, in
`docs/decisions/`; a coding agent never does.

The core suite runs in Docker, with the real files mounted so their tests run too:
```
docker compose --profile core run --rm -T -v "<test_artifacts folder>:/artifacts:ro" -e TEST_ARTIFACTS=/artifacts core python -m pytest -q
```
Since the 2026-10-19 review, 563 tests pass and 45 are skipped: `test_live_artifacts.py` needs `RUN_LIVE=1`, and its
recordings are stale (see [golden eval](docs/build/components/golden-eval.md)). A test must exercise code the product
runs: when a feature goes, its tests go too, or move to the path that replaced it.

## Documentation is part of done

Docs live in `docs/build/` (start at its README). In the same commit as any change: update the component page (what,
why, how, depends on, used by), `ARCHITECTURE.md`, `STATUS.md`, any affected `connections/` page, and add one line to
`LOG.md`. Non-obvious choices get a note in `docs/decisions/`. A change without its docs is not done.

## Branches

Commit to `development`. Merge to `main` only when the owner asks.
