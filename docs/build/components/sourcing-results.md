# Sourcing results and spend

**Status:** built (next build, phase 1)
**Slice / milestone:** next build, phase 1 ([plan](../../next/PLAN.md) S5)
**Code:**
- `core/maindscout/api/sourcing_stats.py`
- `api/costs.py`: `sourcing_spent`, and the separate sourcing budget
- cockpit: `app/(desk)/sourcing/page.tsx` (the desk's Sourcing page) and the funnel on a role's Sourcing tab

## What
For each search strategy: what it cost, and how far the people it found got. This answers the owner's question, "for the $5 we found 800, 100 were relevant, 5 got interviews". The page also holds the desk's sourcing budget and its off-limits list.

## Why
The owner called this crucial (2026-10-12): "we should have the ability to critically adjust our sourcing strategy if something works or doesn't" ([plan section 10](../../next/PLAN.md)).

## How
- **One funnel per person found for a role.** The first search that found them gets the credit (`sourcing_hit`, one per role and person). The stages:
  1. found (new to the desk, or already known);
  2. relevant (now a strong suggestion; "possible" when review-later);
  3. contacted (a first message marked sent, or the pair moved on);
  4. replied;
  5. interested (a permission recorded; it also counts them as contacted and replied, so the funnel only narrows);
  6. CV received (a CV uploaded after they were found);
  7. submitted, interviewed, offered, placed.
- **"How far they got"** is the furthest stage their pair ever reached. An ending such as "we passed" keeps the stages before it.
- **Groups:**
  - channel (our own pool, web people search, or the talent-release radar; the radar finds companies, so its row has spend and no people);
  - company group (named, known, peer, added, releasing talent, market-wide);
  - target company;
  - each search;
  - week;
  - role.
- **Spend.**
  - The total comes from the cost ledger: the `sourcing_` purposes of the role, or of the desk.
  - Each group's share comes from what each of its searches cost.
  - Company searches for the market map count in the total but in no row.
  - The page shows the cost per relevant person, per interview and per placement.
- **Flags** give the numbers behind each one; the owner decides what to change:
  - 20 contacted and no replies;
  - $1 or more spent, 10 or more found, and none relevant;
  - 5 or more strong suggestions not yet contacted;
  - the cheapest interview, or the most relevant people if there are no interviews yet.
- **The budget kept apart.** Sourcing purposes are left out of the monthly model budget (`costs.month_spent`). The desk's sourcing budget sits in `org.settings` and only an owner changes it.

## Depends on
- [sourcing-engine.md](sourcing-engine.md): hits, searches and runs
- [pipeline.md](pipeline.md): pair history
- [messages.md](messages.md)
- [permission-and-stop.md](permission-and-stop.md)
- [tasks-and-costs.md](tasks-and-costs.md)

## Used by
- [http-api.md](http-api.md)
- [cockpit.md](cockpit.md): the Sourcing page, and the role's Sourcing tab

## Contracts
- `GET /v1/sourcing/stats?job_id=&group=&since=` returns `{totals, groups[], flags[]}`. Each row has the counts above, `spend_usd`, `cost_per_relevant`, `cost_per_interview` and `cost_per_placement`.
- `GET /v1/sourcing/settings` returns `{sourcing_budget_usd, spent_usd, web_ready}`.
- `PUT /v1/sourcing/settings {sourcing_budget_usd}` (owner only).

## Tests
In `core/tests/test_autosource.py`:
- a LinkedIn message, a permission and the pair's stages move one person through the funnel, and spend matches the ledger;
- the routes return results and spend;
- only an owner changes the desk budget.

## Known limits
- "Relevant" is the pair's band now, so a later re-match can move someone in or out.
- Spend per group comes from the searches' own costs. The desk's Costs page shows the sourcing total as one line.
- No chart yet: tables and flags only.
