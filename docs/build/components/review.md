# Review: human acts and read models

**Status:** built
**Slice / milestone:** Slice 0 / Milestone E (part 1)
**Code:** `core/maindscout/api/review.py` (writes), `core/maindscout/api/queries.py` (reads)

## What
The only ways a fact becomes official (approve, reject, type a correction, answer a card), and the read views the cockpit shows (jobs list, job page, person page, inbox).

## Why
"Belief is gated": official truth changes only through a human act, and the Inbox holds only the questions the system may not answer itself (blueprint vision, Slice 0 handoff sections 6 and 7).

## How
- **Approve** pins the claim's current view as `approved_view` with who and when. It never changes afterwards except through a human accepting a revision.
- **Reject** keeps a reason code (`low_confidence`, `wrong`, `not_about_subject`, `duplicate`, `outdated`, `other`).
- **Typed fact** (`POST /v1/claims`) is born approved with `human_assertion` evidence; a typed ContactClaim is a clean identity key. `replaces` marks the corrected claim `superseded`.
- **Cards** (`resolve`):
  - `revision_diff`: `keep_old` (approved view stands) or `accept_new`.
  - `duplicate_stint`: `same` folds the newer claim's evidence into the older one and supersedes it; `two` clears the flag on both.
  - `contradiction`: `pick` approves one side and rejects the other in the same act. Raised today for two current locations in different countries stated as of the same date; different dates count as a move, not a contradiction.
  - `identity_note`: `acknowledge` only. Merging people is not in Slice 0.
- **Re-triage after every human act** (approve, reject, typed fact, card resolved): bands of every job the person is on are recomputed from live facts; a change to a job's requirements re-triages everyone on that job. Each band change is a `pair_event` with old band, new band, reason, cause (act, claim id, claim type) and actor.
- **Pair state** (`set_state`): `new` → `seen` → `submitted` (needs a note) or `we_passed` (needs a reason code); reopening needs a note. The outcome is stored on the pair and each move is a `pair_event` of kind `state`. Bands and states are independent ([ADR](../../decisions/2026-10-02-pair-states.md)).
- **Band override** stores who overrode it and is recorded in the history; reprocessing and new facts never change an overridden band.
- **Inbox** scope is the people on a job in a band (default `priority`) or everyone. Blocking items first (identity notes and suspect contacts flagged `possible_ocr_identifier`), then oldest first. Never sorted by a score. Item shapes follow `slice0/cockpit/review-items.md`.
- **Person page** shows each fact with status, flags, dates and its evidence (file, page, snippet, and why a flag was raised).

## Depends on
[persistence.md](persistence.md), [writer.md](writer.md) (payload and flag checks), [process.md](process.md) (which raises the cards).

## Used by
[http-api.md](http-api.md).

## Tests
`core/tests/test_api.py`: approve/reject, typed correction becomes a key, invented field refused, inbox default hides `do_not_submit`, contradiction pick, duplicate stint fold, revision diff keeps the approved view until accepted.

## Known limits
- No snooze, no batch sealing on first view.
- Contradictions cover locations only for now.
- Approving uses the claim's stored view; multi-source reconciled views beyond career steps are not computed yet.

## The desk settles the easy questions itself (2026-10-22)
The owner: "we should questions that matter, easy and silly questions should be caught and settled and handled by the
desk". Of 48 questions waiting that day, 45 were settled by rule (`api/settle.py`), each sealed by "desk" with its
reason, so it stays on record:
- **Same stint, or two?** The same title at the same company, in periods that overlap or follow on within a month, is
  one job written twice (a profile splits one job at a renewal): joined over its whole span. A gap, or another title,
  is still asked. Joining by hand now also keeps the whole span (it used to keep the older step's dates only).
- **Same company?** Merged when the names are one name written differently (spaces, accents, legal form such as
  S.p.A., a country tag, a plural), or one is a part or a renamed form of the other (a department, lab, experiment,
  "verschmolzen mit"); the parent's name stands. Kept apart, not asked, when they only share a website (gov.uk
  carries every UK department, a university's site its labs, a group's its brands), when either is a club, society or
  studentship, or when the name is not like any of the company's names. The rest is asked (KPMG / KPMG Avocats).
- **Other names from a profile** are kept only when they start as the company's own name does: profiles also list
  places, nicknames and parent bodies ("toro", "virginia", "University of Oxford" for a college), and an alias decides
  where every later CV is filed. 1,378 such names were removed.

match-eval after settling: no moves on the three roles, the owner's labels 4/4.
