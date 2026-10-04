# External code review: findings and verdicts

**Date:** 2026-10-05
**Decided by:** owner (asked for each finding to be checked, not accepted as given); fixes by the build agent
**Status:** fixes merged to `development`

An outside reviewer read the code and probed functions with crafted inputs. Every finding was checked against the code, and the probes were re-run, before anything changed. The verdicts:
- **True, fixed:** real and now changed.
- **True, deferred:** real, but not worth changing at today's size; the trigger for doing it is named.
- **Overstated:** real in part.
- **Disagree:** the current behaviour is deliberate, and the reason is given.

Each fix has a regression test in `core/tests/test_review_fixes.py` (23 tests, none needs the model).

## Identity

| Finding | Verdict |
|---|---|
| A CV merges into an existing person on one clean contact; the name is never compared (an agency email or phone on many CVs folds people together) | **True, fixed.** A contact match merges only when the names agree (every word of the shorter name is in the longer, whole or as an initial; word order and accents ignored). A different name, or no name read, creates a new person with a "Who is this?" card naming the match. |
| `judge` trusts any email that is not a one-letter typo of the name; phones are never checked | **True; fixed by the rule above, not by flagging.** Flagging every email that doesn't contain the name would put a blocking card on most CVs. The name check at merge time stops the false merge without that cost. |
| Contacts taken from links (`mailto:`, LinkedIn) skip `judge` | **True, fixed.** They go through `judge` too. |
| The same-name note uses `LIKE` without escaping `%` and `_` | **True, fixed.** |

## The span check

| Finding | Verdict |
|---|---|
| Any two-digit number supports a year ("24th" supports 2024) | **True, fixed.** A two-digit year counts only when written as a date: `03/19`, `Mar 19`, `Mar '19`, `'19`. |
| Phone digits may be gathered from the whole file | **True, fixed.** They must be one written number. |
| Names are found inside longer words ("Ann" in "Joann") | **True, fixed.** The match must start and end on word edges. Spaces are still ignored, because PDF text splits words ("GUST AVO"). |
| Emails are matched after deleting every space | **Overstated, narrowed.** PDF text does split emails, so one stray space is still tolerated, but only at token edges. Two or more are refused. |
| A start with no end becomes a closed one-year job | **True, fixed.** If the quote writes an open range ("since 2019", "2019 –"), the step is open. A lone date ("2019  Intern") still stands for that year: that is what the CV says. |
| A contact whose quote is not found is accepted on its value alone | **Disagree.** For a contact, the value is the evidence and is checked first (now more strictly); the quote is only context. |

Checked on the real test CVs: zero span failures under the new rules.

## Official facts and review cards

| Finding | Verdict |
|---|---|
| Linking a company rewrites `approved_view` | **True, fixed.** The link goes on the payload only; readers take it from there. The approved view is pinned at approval and never changes. |
| Overlapping steps at one company from one CV never raise a card | **True in part, fixed.** Two titles at one company that overlap are usually a promotion and are left alone. The same title twice over overlapping dates now raises "Same job, or two?". |
| Two approved locations in different countries never raise a contradiction | **True, fixed.** Picking one rejects the other, so the card cannot loop. |
| A later file that casts doubt on a contact doesn't flag it | **True, fixed** for contacts still awaiting review. An approved one was decided by a person and stays. |

## Matching and the inbox

| Finding | Verdict |
|---|---|
| A substitution note covers another requirement on one shared word ("role") | **True, fixed.** The note must name the requirement: its skill token, or at least half its meaningful words. Generic words don't count. |
| `triage(process_stale=…)` is accepted and never read | **True, fixed** (dead parameter removed; the job page's stale banner is unchanged). |
| A slash in a must-have ("insar/python") is read as either | **Disagree.** Job ads use a slash for alternatives ("Java/Kotlin"); the gap table reads it the same way and says "or". |
| `GET /v1/inbox` without a job ignores `band` | **True, fixed.** A band without a job is now refused, not ignored. The cockpit already sent `band=all`. |

## Erasure

| Finding | Verdict |
|---|---|
| A later verify can't see an original file that failed to delete | **True, fixed.** The erasure record keeps the file keys (content hashes) and every verify checks them. |
| Without `SUPPRESSION_KEY`, an erase reports clean although the person can be uploaded again | **True, fixed.** It is a survivor, not green. The erase itself still completes: erasure is never refused. |
| Import swallows every error from the suppression lookup | **True, fixed.** A missing key already returns "not suppressed"; any other failure now stops the upload. |
| Rejected contacts aren't suppressed | **True in part, fixed.** Rejected as outdated, duplicate or low confidence: still theirs, suppressed. Rejected as wrong or not about them (an agency address, a misread): not suppressed, so other people aren't blocked. |
| Task payloads, import data and free-text notes survive | **True, and wider than reported, fixed.** Import rows never imported (previews, duplicates) also held the person's name and contacts; they are now deleted. Tasks naming them or their documents are deleted. Notes on other timelines that name them have the name struck out. The client's timeline no longer copies an email's subject, which could name the candidate. |
| Deleting a shared file is check-then-delete across orgs | **True, fixed.** Storing and deleting the same bytes take one advisory lock until commit. |

## Security

| Finding | Verdict |
|---|---|
| Uploaded files are served inline with the caller's content type: an HTML or SVG upload runs on the desk's origin | **True, fixed.** The type comes from the bytes, never the caller. Only a real PDF or plain text opens in the browser; anything else downloads. Always sent with `nosniff`, and everything but PDF with a sandboxing CSP; the cockpit route enforces the same. Filenames are reduced to safe characters. |
| CSV import reads the whole body before checking 10 MB | **True, fixed.** |
| Rows past 20,000 are dropped silently | **True, fixed.** The import is refused, with a request to split the file. |
| Export doesn't guard spreadsheet formulas | **True, fixed.** |
| The mailbox error is copied into the redirect unencoded | **True, fixed.** |
| Gmail's read scope is wider than needed | **True, fixed.** `gmail.readonly` replaced by `gmail.metadata` (labels and headers, never bodies). The code already read only metadata. |
| `cockpit/lib/api.ts` isn't marked server-only | **True, fixed** (`import "server-only"`). |
| Company merge isn't recorded and affects every desk | **True, fixed in part.** Merges record who, from which desk, and when. Companies stay shared by design. |
| One operator token for every desk; `X-Actor` is self-declared; the cockpit has no login | **True, deferred to before the desk leaves this machine.** Per-desk credentials and an actor from a real session are a project of their own, not a patch. Until then, the database and the cockpit are bound to this machine only (both listened on every network interface before). |
| Mapped exceptions return their message | **Overstated.** Our own errors are written to be read by the recruiter. Unexpected errors already return a generic 500. |
| A task left `running` by a crash is never reclaimed | **True, fixed.** After 30 minutes it is queued again (or failed, once out of attempts), freeing its dedupe key. |
| The desk can't follow the shared research it queued | **True, fixed** (shared tasks are visible to `GET /v1/tasks`). |
| The budget check isn't atomic with the call | **True; accepted.** The cap is soft: overshoot is bounded by the calls in flight (cents). Serialising every paid call would cost more than it saves. |
| The search cache is shared across desks and unlocked | **True, fixed.** It is keyed by desk, locked, and drops the oldest entry instead of clearing. |
| `settings.env` re-reads `.env` on every lookup | **True, fixed.** It is cached, and re-read only when the file changes. |

## Performance

| Finding | Verdict |
|---|---|
| The jobs list builds a full inbox per job just to count it | **True, fixed.** One build, counted per job. |
| The job page reloads requirements, claims and evidence per person | **True, fixed.** Three queries for the whole page. |
| Contact lookup scans every claim | **True, fixed.** Expression index on contact kind and value (migration `0021`). |
| The model call happens inside an open transaction and can starve the pool | **Overstated; deferred.** Uploads are queued, and workers are capped (2 by default), so at most that many connections wait on the model. The trigger to revisit is more workers, or synchronous model calls on hot paths. |
| Approving a fact rematches synchronously | **True, deferred.** Fine at desk size; it moves to the task queue when a job has hundreds of people. |
| Export, company search and verify are per row or done in Python | **True, deferred.** All are occasional, and small at this size. |

## Other
- The reviewer's session read `core/.env`, which holds the model provider key. Rotate it if that transcript is shared.
