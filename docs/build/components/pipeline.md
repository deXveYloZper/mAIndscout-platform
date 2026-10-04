# Pipeline and client blocks

**Status:** built (Slice 4, step 2)
**Code:** `core/maindscout/api/review.py` (`set_state`), `core/maindscout/api/pipeline.py` (client blocks, stage counts), migration `0018`, cockpit `components/StateControls.tsx`, job page stage line, person page blocks

## What
- **The full pipeline** of a person on a job: new → seen → contacted → screened → submitted → interviewing → offer → placed. There are three other endings: **we passed** (with a reason code), **withdrawn** (the candidate pulled out, with a note) and **client rejected** (with the client's words). One "Move to" control on the gap table moves a pair anywhere; every move stays in the pair's history.
- **Rules:**
  - submitted needs a note (to whom, how);
  - withdrawn needs a note;
  - client rejected needs the client's feedback;
  - moving out of an ending (placed, passed, withdrawn, rejected) needs a note saying why.
- **A client's rejection is a wall.** It blocks the person at that client company: every job there, including companies merged into it.
  - Submitting them, or moving them to interviewing, offer or placed, at that client is refused.
  - Sourcing never finds them for that client.
  - Matching marks them unlikely there, with the client's words as the first rule.
  - Job pages show "blocked by client". The person page shows the block with **Lift block**, which needs a note (e.g. a new hiring manager).
- **The client's side of the story:** submissions and the client's answers (submitted, interviewing, offer, placed, rejected) appear on the company's timeline as well as the person's.
- **Stage counts** on each job page ("submitted 2 · interviewing 1 · placed 1").

## Why
Slice 4 ([plan](../../slice-4/PLAN.md)): a desk runs jobs end to end here, and a client's rejection is a wall.

## Depends on
[review.md](review.md), [matching.md](matching.md), [people-search.md](people-search.md) (sourcing), [relationship-memory.md](relationship-memory.md) (timelines), [companies.md](companies.md).

## Contracts
- `candidate_job.pair_state` takes the eleven stages (check constraint widened in `0018`); `outcome.party` is operator, candidate (withdrawn) or client (rejected).
- Table `client_block` (`0018`): company, person, job, the client's words, who and when; lifted with who, when and why. Erased with the person.
- `POST /v1/jobs/{id}/people/{cid}/state {state, reason?, note?}`: refusals are 422 (missing note or reason) or 409 (blocked by the client).
- `POST /v1/blocks/{id}/lift {note}`.
- `GET /v1/jobs/{id}` adds `stages` and `blocked` per person; `GET /v1/candidates/{id}` adds `blocks`.

## Tests
`core/tests/test_pipeline.py` (6):
- a pair moves through the whole pipeline and every move is kept;
- endings need their reasons;
- a client rejection is a wall at that client (refused, unlikely, tagged; lifting needs a note, then it works);
- blocked people aren't sourced for that client;
- the client's timeline shows submissions and its answers;
- erasure removes blocks.

e2e: a pair moves through the pipeline, passed, reopened, submitted, with stage counts.

## Known limits
- Interviews, offers and placements are stages with notes; interview dates, offer terms and fees come later (fees are out of Slice 4).
- A rejection where the job has no known hiring company stays on that job only.
