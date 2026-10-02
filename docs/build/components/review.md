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
- **Band override** stores who overrode it; reprocessing never changes an overridden band.
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
