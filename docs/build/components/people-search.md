# People search and sourcing v2

**Status:** built (intelligence track I6)
**Code:** `core/maindscout/api/search.py` (filters over career profiles, target-company alumni, a job's filters), `core/maindscout/api/sourcing.py` (`ProfileAdapter`, `profile_query`, source `auto`), `core/maindscout/api/demo.py` (synthetic demo desk), cockpit `app/search/`, job page "Find more people"

## What
**Search in your own words** (owner's decision 2026-10-04, [ADR](../../decisions/2026-10-04-search-in-own-words.md)): one search bar; the search is read by a small model (`intelligence/query.py`, about $0.0005, cached per wording) into criteria from the fixed lists and shown as "Understood as"; results are ranked best first by code (`search.ranked`): each criterion met / partly / not met with its reason (kind of work and skills count most), "meets N of M", no score. `GET /v1/search?q=...`. The filters below remain as "Refine with filters".

- **Search the desk** by what careers show: kind of work (including related work by default), at least N years of related work, at least a level by title, at least a year at a kind of employer (start-up, scale-up, large, consultancy…), at least a year in an industry, worked (or still works) at a named company. Every filter must be met. With filters only, results come newest first; a search in words is ranked best first (above).
- **Target-company alumni:** everyone on the desk who worked at a company, and when.
- **Sourcing v2:** "Find more people" on a job searches by its hiring profile.
  1. First the alumni of the job's target companies, because the hiring manager named them.
  2. Then everyone whose career profile meets the job's must-haves: the role (with related work), years (asked × 0.75, so matching can judge the near misses), must-have backgrounds and industries.
  3. Everyone found goes through the same matching as an uploaded CV.
  - A job without a hiring profile, or a desk without career profiles, falls back to the keyword search (source `desk`).
  - Campaign rules are unchanged: cap, target, human stop, and no messages to anyone.
- **Demo desk (testing only):** `python -m maindscout demo-seed [--count 60]` adds clearly synthetic people (names start with "Demo · ", emails at `example.invalid`, a reserved domain). Their careers are generated from a fixed seed at companies already researched on the desk. About 8% live outside coverage, to show the gate. It makes no model calls and costs nothing. `python -m maindscout demo-clear` erases them all through the ordinary erasure path.

## Why
Plan section 4.7 and phase I6: sourcing as a structured query over profiles and the people-to-company graph ("we know 15 people who worked at Company A"), not a keyword scan. The owner noted (2026-10-04) that the desk has too few real profiles to test this properly, so the demo desk gives it a realistic size.

## How
- **Search** reads each person's latest career profile (one query, `DISTINCT ON`) and applies the filters in code. Archived (out-of-coverage) and merged people are never searched.
- **Worked at** uses the career steps' company links, including companies merged into the one asked for.
- **Sourcing** order is by channel (alumni, then profile matches), newest first within each: it's never a ranking by fit. Matching then decides each person's band. The coverage gate still applies: archived people are found only if this job accepts their country.

## Depends on
[career-profiles.md](career-profiles.md), [hiring-profiles.md](hiring-profiles.md), [matching.md](matching.md), [companies.md](companies.md), [coverage-gate.md](coverage-gate.md), [sourcing.md](sourcing.md), [erasure.md](erasure.md).

## Used by
[cockpit.md](cockpit.md) (Search page; job page "Find more people").

## Contracts
- `GET /v1/search?family=&related=&min_years=&level=&employer=&domain=&company=&current=` returns `{filters, people[{candidate_id, name, summary, reading, met[]}]}`.
- `POST /v1/jobs/{id}/campaigns` defaults to `source: "auto"`.
- Campaign `query` for source `profile` is `{filters, targets, words}`.
- `GET /v1/jobs/{id}/campaigns` adds `by_profile` (the words of the profile search, when available).

## Tests
`core/tests/test_nl_search.py` (3): a search in plain words is read into checked criteria (culture fit dropped, unwritten years dropped); results come best first with reasons, the same search is not read twice; verdicts met / partly / missed. `core/tests/test_search.py` (5):
- every filter must be met, with related work counted by default;
- the demo desk is synthetic, searchable and erasable, and archived people are never searched;
- alumni and the search route;
- a job with a hiring profile is sourced by profile, and everyone found is matched;
- a job without one falls back to keywords.

The existing sourcing tests still pass. e2e: the desk is searched by career profile.

## Known limits
- Search is code over stored profiles, which is fine for thousands of people. A database-side index comes if the desk grows far beyond that.
- One industry and one company per search in the cockpit form (the API takes several).
- The demo desk is for testing on a development desk only; never seed it into a live desk.
