# The architecture review: what was fixed, and what was not taken

**Date:** 2026-10-28 · **Decided by:** the owner ("implement the fixes that you agree with and agree that the review
found errors that should be fixed. note to me what you do not agree with so we can discuss them") · **Status:**
fixes built; the points not taken are for discussion

## Why
An exhaustive review of the API and the desk (2026-10-28): every route against every page's calls, blocking and
races, telemetry, wording and workflow. Each finding was checked again against the code and the live desk's own
records before anything was changed.

## Fixed
1. **Reading an ad no longer holds up the whole desk.** Six upload routes were `async def` and then did their work
   synchronously: on the server's one event loop, "Read the ad" (one or two model calls, 5 to 15 seconds) stopped every
   other page meanwhile. They are plain `def` like the other routes, so they run in the thread pool. A test keeps every
   route that way.
2. **Every button has its words in the activity log.** 42 of the 88 write routes logged as "POST /v1/…" (a call
   review approved, a stop, a permission, members, the mailbox, messages marked sent, tags, imports…). All have words
   now, and a test fails when a new route has none. Opening a suggestion's profile is named, not hidden: it moves the
   suggestion to "seen".
3. **A refusal says why.** An error turned into a response (a budget stop 402, a model failure 502, a rule broken
   422, a conflict 409) logged only "refused: 502". The line now reads "(refused: 402: …the error's words…)", with the
   whole reason in its detail.
4. **A change to a requirement or a line of the work is logged under its role** (their routes name only the line),
   so the role's own Activity view shows it, and the model calls it makes too.
5. **The clocks are no longer silent.** The sourcing and mailbox clocks swallowed every error. A failure is logged
   once until it changes, and so is the recovery; the clock keeps ticking.
6. **The Costs page names every purpose:** the 11 in the ledger it showed as raw keys (role briefs, work lines and
   readings, company lines, competitor research, the talent map, deeper public checks, companies' practices, process
   dates, and the two measurement purposes of 2026-10-27).
7. **Two-step codes can be turned off** on the Account page, with the password (they are optional, the owner's
   decision of 2026-10-05; until now only the API could switch them off). An owner who must keep them
   (`OWNER_TWO_STEP=required`) is told so instead.
8. **Wording:** Today's "Refresh list" beside "Recent activity" read as reloading the feed; it says "Who to re-contact".
   The hiring profile had two "Confirm all N" buttons of different scope; the work lines' says "Confirm these N lines".
   A contact's "forget" is "Forget", as elsewhere.

## Not taken (for discussion)
1. **A unique index on the task queue's dedupe key.** The race is real in theory (two callers checking in the same
   instant), but it never happened: in 2,730 tasks, no key ran twice at once and none was queued twice. The proposed
   index would also break "Search now": each batch queues the next round under the same key while it is still running,
   so the index would refuse it. If wanted, a lock on the key while queuing (`pg_advisory_xact_lock`, as the file store
   already does) closes the race without that harm; the cost is that a request queuing a key a long task is also
   queuing waits for that task.
2. **"Read the file again" for stored CVs.** The premise was that the two-column fix never reaches the CVs already
   stored. The live desk holds no stored CVs at all (its 4 ads read with the old repairs are not two-column; everyone
   else is a public profile, which has no PDF). New CVs are read with the current repairs, and a doubtful page is
   flagged for a person (the owner's fallback rule). A re-read would also call the model again and replace facts.
3. **Deleting routes nothing calls** (`POST /v1/companies/{id}/merge`, `GET /v1/documents/{id}/text`,
   `GET /v1/runs/{id}`): they are documented API routes, harmless, and the company merge is the same function the
   inbox uses. Kept.
4. **Reading the role brief and the work lines by themselves after the ad.** The brief's page says it will once the
   owner has reviewed its first readings, and they were reviewed (2026-10-19), but it spends on every new ad and
   changes the order of the owner's work: the owner's call.
5. **Other wording:** the nav item "Refresh" (the page's own name since Slice 4), "Sourcing" as both the role tab and the
   desk page (the same work at two scopes), the schedule buttons "Daily" / "Weekly" (they are buttons, beside
   "Scheduled searches"), and "Not on a job" beside "In the pool" (the People page says the pool is the people on no job).
   Matters of taste; not changed without the owner.
6. **Unchanged by design:** the role brief and requirement edits call the model inside their request (only the person
   waiting waits); the Sourcing tab's refresh writes the plan's sync (documented); the inbox hides calls to approve
   while one role is chosen.
