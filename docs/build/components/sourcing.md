# Sourcing feeder

**Status:** built (desk adapter)
**Slice:** 2
**Code:** `core/maindscout/api/sourcing.py`, table `campaign` (migration `0007`), routes in `api/app.py`, cockpit `components/FindMore.tsx` and the job page

## What
When a job's priority queue is thin (fewer than 5 people by default), the recruiter can run a bounded find. A campaign derives a query from the job's must-haves, asks one source for people, and puts each person on the job through the ordinary pair-and-triage path.

## Why
Vision: "Sourcing exists only to refill a thin priority queue. Sourced people enter the same path." Slice 2 plan: one source adapter, campaign rows, stop at cap / target / human, and a sourcing signal must never become a scoring feature (P13).

## How
- **Source: the desk's own people graph** (owner's choice, 2026-10-03): everyone already read into the platform (the pool and people on other jobs) whose skills or job titles mention a query token, using triage's whole-word matching. Order is newest first, never by how well they match. A second adapter (e.g. GitHub profiles) plugs in behind the same `find` interface later.
- **Query:** the job's distinctive must-have tokens; if it has none, its must-have skill tokens. A job with no must-have skills cannot be sourced.
- **One person at a time:** look, put on the job with `_ensure_pair` (the same function an upload uses), count. Stop when priority reaches the target (`target_reached`), when the cap of people looked at is hit (`cap`), when the source has no one left (`exhausted`), or when a human stops it.
- **Same downstream:** a sourced person's band and reason come from the same rules and facts as for an upload; being sourced only appears in the pair's history (cause `sourced`, campaign id).
- **Refusals:** no campaign when priority is already at the target, when one is running for the job, or for an unknown source.
- **Privacy:** a campaign stores counts only (looked at, added, priority added), never names; the people it added are known through their pair history, which erasure deletes.
- **No mail:** there is no route that sends anything.

## Depends on
[process.md](process.md) (`_ensure_pair`, re-triage), [intelligence.md](intelligence.md) (whole-word matching), [persistence.md](persistence.md).

## Used by
[http-api.md](http-api.md), [cockpit.md](cockpit.md) ("Find more people" on a thin job), [golden-eval.md](golden-eval.md) (Slice 2 gate checks).

## Tests
`core/tests/test_sourcing.py` (8): refill through the same triage; distinctive tokens do not pull generalists in; stop at cap; stop at target and refuse when not thin; a sourced person behaves exactly like an uploaded one; stop and list; no must-have skills refused; no mail route. Eval case `slice-2-gate` on real files. e2e: a thin job refilled from the desk.

## Known limits
- The desk search reads every person on each step; fine for a desk of thousands, to be indexed before tens of thousands.
- Campaigns run inside the request (the desk is fast); an external adapter will need a background worker.
- External sources (GitHub, web, vendors) are not built; they bring personal-data and terms-of-use duties that need a decision first.
