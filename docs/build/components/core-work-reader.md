# Core-work reader

**Status:** built 2026-10-28 (owner, 2026-10-27: "yes build the reader, test on Ferrari and Bonaventura")
**Slice / milestone:** next build, after phase 1e ([measurement](../../evals/2026-10-27-core-work-reader-ferrari.md),
[decision](../../decisions/2026-10-28-core-work-reader.md))
**Code:** `core/maindscout/intelligence/work_lines.py` and `intelligence/work_reader.py` (no database),
`core/maindscout/api/work_lines.py` and `api/work_reading.py`, claim type `WorkLineClaim`, task `work_reading`;
cockpit `components/WorkLines.tsx`, `WorkLineForms.tsx`, `WorkReading.tsx`

## What
A role's work, line by line, and the jobs that share its words but are different jobs ("not this work"). Each strong
or possible person's own words are read against the lines a person confirmed: whoever's words show the work comes
first in their band, whoever's main work is a look-alike comes last. Each card shows the lines their words show, with
their exact words. It never changes a band, a tier or a rating.

## Why
On Ferrari's CRM role, matching by titles and keywords could not tell a CRM platform roll-out (the job) from CRM email
campaigns or Salesforce built from IT (look-alikes). Measured before it was built: with the lines confirmed as a
recruiter would, the client's interviewee's CV came first, the person the recruiter found "still light" last, and the
email marketers below the operations and roll-out people, on the desk's own model.

## How
- **The lines** (`work_lines.read`, one call, about a fifth of a cent): four to six things the hire will actually do
  (the central ones marked "the heart"), and two to four look-alikes, from the ad, the role brief and the
  requirements. Stored as proposed `WorkLineClaim`s with the reading as evidence. Read with the role brief (the
  button, an answer, "tell the desk") while no line is confirmed, or by "Read again"; a re-read replaces the desk's
  proposed lines, never a line a person confirmed or typed.
- **A person decides** on the hiring profile: "Confirm all", change a line's words (or whether it is the heart),
  remove one, add one in their own words (born confirmed). A change re-rates nobody (`review.NOT_RATED`).
- **Who is read** (`work_reading.maybe_queue`, `queue_role`): everyone in Priority or Review later once the role has a
  confirmed work line; then anyone who reaches those bands (called by matching and by sourcing). Read again when the
  confirmed lines change ("Read N against these lines") or a CV arrives. Never someone who asked not to be contacted.
  Off with `WORK_READER_AUTO=false`.
- **What is read:** their CV when there is one, else their public profile's own words without the company boilerplate.
- **One call per person** (`core_work_check`, about a fifth of a cent): each work line shown, partly or not shown, each
  look-alike their main work, some of it or not shown, with their exact words.
- **Checked by code:** every piece of a quote is literally in their words (the span check's tolerance), and one piece
  of at least four words is not inside a job title, a heading or a skills list (their career steps' titles, the
  profile's headline, job headings and skills). The model is also told that a phrase about a quality, an attitude or
  a wish is never evidence ("understand my counterpart's needs", owner: "very vague"). A quote that fails is dropped.
- **Kept:** the lines shown and the look-alikes, with their quotes, in the task's result (erased with the person). What
  the model writes about the person in its own words is never kept. The task is quiet in the activity log, and its
  prompt is personal (never logged).
- **The order** (`work_reader.order_key`, sorting only, never shown or stored): within a band, first those whose
  words show the work (the more lines, the earlier; a heart line counts double), then those whose words show nothing
  either way (and anyone not read yet), then those whose main work is a look-alike ("some" look-alike work never
  demotes anyone). On the Sourcing tab it comes before the strong-plus count; on the role's page within each band.
  A reading against earlier lines is "stale" and orders nobody.
- **On the card:** "shows the work" with its lines, or "main work looks like" a look-alike; under Details (Sourcing)
  or "Their words" (the role's page), every line with their words.

## Depends on
- [role-brief.md](role-brief.md): the brief's lines are part of what the lines are read from
- [hiring-profiles.md](hiring-profiles.md): the requirements
- [matching.md](matching.md): its bands decide who is read
- [tasks-and-costs.md](tasks-and-costs.md): the `work_reading` task, the ledger (`work_lines`, `work_reading`)
- [intelligence.md](intelligence.md): the model client and the span check

## Used by
- [sourcing-engine.md](sourcing-engine.md) and [outreach.md](outreach.md): the order of the suggestions and the card
- [cockpit.md](cockpit.md): the hiring profile's "The work, line by line", the cards

## Contracts
- `POST /v1/jobs/{id}/work-lines` reads the lines again; `POST /v1/jobs/{id}/work-lines/confirm` `{ids?}` confirms
  them and queues the readings; `POST /v1/jobs/{id}/work-lines/add` `{kind, words, central}`;
  `POST /v1/work-lines/{claim_id}/edit` `{words, central}`; a line is removed with `POST /v1/claims/{id}/reject`;
  `POST /v1/jobs/{id}/work-readings` reads again those read against earlier lines.
- `GET /v1/jobs/{id}` adds `work_lines` `{lines, version, read_at, people}` and each person's `work`; the Sourcing
  page adds `work` on each card: `{status, group, work[], not[], lines, source, reason, at}`.
- `WorkLineClaim`: [schema](../../../slice0/schemas/work_line_claim.schema.json), natural key `job_id|work|kind|words`.

## Tests
`core/tests/test_work_reader.py` (9): lines without personality, short or repeated lines; nothing read before a
person confirms, and confirming re-rates nobody; a title, a headline, a skills list, words not theirs or a short quote
never count; only checked quotes are kept, never the model's summary; the order; a reading orders the Sourcing tab,
shows on the card and is erased with the person; changed lines make a reading stale until read again; a stop or a
band outside Priority and Review later is never read; a typed line is confirmed at once and personality is refused.
Measured on Ferrari and Bonaventura: see the decision.

## The role's own titles (2026-10-30)
The owner: "we cannot hard code every job family there is ... why our platform doesn't generate this itself, when it
understands the company and the role?" After the lines, one more call (`role_titles`, about a fifth of a cent) reads
the titles people doing this work carry (no seniority words; also in the languages of the role's countries), the
titles of its look-alike jobs, and the work in a word. Once the strategy has found the client's own people, their
titles go into the reading too. They are kept as `WorkLineClaim`s of kind `title`, `not_title` and `word`, in the
reading's order (`rank`), shown under the lines on the hiring profile and confirmed with them ("Confirm these N
titles"). Only confirmed ones are used, and only by the searches ([sourcing strategy](sourcing-strategy.md)): they are
never read against and never change a rating, so they are left out of the lines' version. A reading of the lines
replaces only the desk's proposed lines, a reading of the titles only its proposed titles; titles are read again only
while none is confirmed. Read for all seven open roles on 2026-10-30 ($0.018): see the
[decision](../../decisions/2026-10-30-role-titles.md).

Tests: `core/tests/test_role_titles.py`.

## Known limits
- Public profiles mostly list titles: about half of a role's people give it nothing to quote, so it orders the rest.
- Call notes are not read yet (they hold the recruiter's words too).
- The look-alikes are the desk's guess until a person confirms them; a missing one is the most common gap.
