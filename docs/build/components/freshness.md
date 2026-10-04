# Freshness

**Status:** built (Slice 4, step 3)
**Code:** `core/maindscout/api/freshness.py`, cockpit `app/refresh/`, stale tags on the person, company and People pages

## What
- **Fresh or stale.**
  - A person is stale when the later of "last contacted" and "facts last verified" is more than **6 months** ago, or never.
  - A client is stale when the later of our last contact and its facts' research is more than **12 months** ago.
  - Both are settings: `FRESH_PERSON_MONTHS`, `FRESH_COMPANY_MONTHS`.
- **Refresh page.**
  - **Re-contact these people:** stale people, most valuable to the desk first, each with "why now". The order is priority on a live job, then a strong match on a live job, then a talent pool, then a strong career, with the longest-silent first among equals.
  - **Clients to reconnect with:** stale clients with a live job or contacts on file, live jobs first.
- **Tags:** "stale" on the People list, and a note on the person and company pages.

## Why
Slice 4 ([plan](../../slice-4/PLAN.md)) and the owner's point: most ATSs never know when a candidate was last contacted, and the knowledge goes stale silently. Freshness makes that visible and turns it into a to-do list.

## How
- Dates come from relationship memory ([relationship-memory.md](relationship-memory.md)): last contacted (calls, emails, meetings, messages, Brief answers), last verified (approved or typed facts, Brief answers, CVs read), and company research dates.
- The list is computed when the page opens, so it is always current. A weekly digest is a later convenience.
- An order with reasons, never a score; archived people (outside coverage) aren't listed.

## Depends on
[relationship-memory.md](relationship-memory.md), [matching.md](matching.md), [career-profiles.md](career-profiles.md), [company-research.md](company-research.md).

## Contracts
- `GET /v1/freshness` returns `{person_months, company_months, people[{candidate_id, name, why[], freshness}], clients[{company_id, name, why[], freshness}]}`.
- `GET /v1/candidates/{id}` and `GET /v1/companies/{id}` add `freshness {status, since, words}`; `GET /v1/candidates` rows add `stale`.

## Tests
`core/tests/test_freshness.py` (5):
- a new CV is fresh and goes stale after six months;
- a logged call makes a person fresh again;
- the re-contact list puts priority before a talent pool, with reasons;
- clients with live jobs go stale without contact;
- the route, and stale tags.

e2e: the Refresh page.

## Known limits
- A weekly email digest isn't built (the page is always current).
- The list shows the top 50 people.
