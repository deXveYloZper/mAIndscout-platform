# The pool step (the desk's own people, first in every sourcing run)

**Status:** built. Slice 2's campaigns are removed: their endpoints went on 2026-10-14, their code on 2026-10-19.
**Slice:** 2, then the [sourcing engine](sourcing-engine.md)
**Code:** `core/maindscout/api/sourcing.py` (the adapters and the queries), called by `autosource.run` (step 1). The table
`campaign` (migration `0007`) is kept as history.

## What
Before searching the web, every sourcing run looks at the desk's own people. It finds them by the role's hiring
profile, or else by its distinctive must-have skills, and puts each one on the role through the ordinary pair-and-match
path.

## Why
Vision: "Sourced people enter the same path." The desk's own people are free and the warmest. A sourcing signal must
never become a scoring feature (P13).

## How
- **Two adapters, one `find` interface:**
  - `ProfileAdapter`: the alumni of the role's target companies first, then everyone whose career profile meets the
    hiring profile ([people-search.md](people-search.md)).
  - `DeskAdapter`: anyone whose skills or titles mention the role's distinctive tokens, using triage's whole-word
    matching.
  - The order is newest first, never by fit. People who said "stop", people at off-limits companies (passed as
    `exclude`) and people outside the coverage the role accepts are skipped.
- **Query:** `profile_query` when the hiring profile gives something to search by; otherwise `query_tokens` (the
  distinctive must-haves, else the must-have skills).
- **Same downstream:** a person found here gets their band and reason from the same rules and facts as an upload.
  Being found shows only in the pair's history (cause `sourced`, channel `pool`) and as a `SourcingHit`.
- **No mail:** there is no route that sends anything.

## Depends on
[process.md](process.md) (`_ensure_pair`, re-matching), [intelligence.md](intelligence.md) (whole-word matching),
[people-search.md](people-search.md).

## Used by
[sourcing-engine.md](sourcing-engine.md) (step 1 of every run), [golden-eval.md](golden-eval.md) (the slice-2 checks
on real files, through the same pool look).

## Tests
`core/tests/test_sourcing.py` (4), rewritten on 2026-10-19 to go through `autosource.run` with no web client, the way
the desk runs it:
- a specialist is found by the role's distinctive skill and banded with the reason;
- distinctive skills do not pull software generalists in;
- a person found in the pool is handled exactly like an uploaded one;
- no mail route.

Also tested elsewhere:
- `test_search.py`: a role with a hiring profile is searched by profile; a role without one, by its skills.
- `test_coverage.py`: people outside coverage are skipped until the role accepts their country.
- `test_autosource.py`: "stop" and off-limits people are skipped.

## Known limits
- The desk search reads every person on each look. That is fine for a desk of thousands; it needs indexing before
  tens of thousands.
