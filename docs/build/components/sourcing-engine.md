# Sourcing engine

**Status:** built; not yet run on a real role (next build, phase 1; the gate is the owner's)
**Slice / milestone:** next build, phase 1 ([plan](../../next/PLAN.md) S1–S3)
**Code:**
- `core/maindscout/api/autosource.py`: plans, runs, gates, budgets, the clock's list, the role's sourcing page
- `core/maindscout/api/marketmap.py`: the market map
- `api/task_handlers.py` (`sourcing_run`) and `__main__.py` (the sourcing clock)
- tables `sourcing_plan`, `sourcing_run`, `sourcing_query`, `sourcing_hit` and `off_limits` (migration `0026`)
- cockpit: the job page's Sourcing tab (`components/Sourcing.tsx`, `components/SourcingForms.tsx`)

## What
Each open role keeps finding people on its own.

A role has a **plan**:
- where to look (the market map);
- what the work is called (role titles);
- which countries;
- how often: daily, weekly, continuous until the target, or paused;
- a target of strong suggestions waiting;
- a monthly budget.

A **run** goes cheapest first: the desk's own pool (free), then the web through Exa (paid). Everyone found becomes a **suggestion to contact**, with who found them and why.

## Why
The owner's next build (2026-10-12): continuous, intelligent sourcing for hard-to-fill roles, beyond inbound and the desk's own pool. The owner's rules ([plan section 10](../../next/PLAN.md)):
- public data only, as a guide to contact people;
- off-limits: active clients, and for 12 months a client where we placed someone;
- budgets adjustable per role and for the desk;
- daily, weekly, or continuous until the target;
- everyone found stays in the pool for future roles.

How the build follows those rules (the CV path for found profiles, separate budgets, paused new plans, off-limits, "stop", first-finder credit): [decision](../../decisions/2026-10-12-sourcing-engine.md).

## How
- **The market map** (`marketmap.initial`, free):
  - Companies: first the target companies the hiring manager named (pinned). Then up to 20 companies that share an industry with the hiring company, from desk research: first those our people worked at ("known"), then the rest ("peer").
  - Role titles: the job's own title without gender tags such as "(m/w/d)", plus up to three titles for the same work in its role family.
  - Countries: the job's open countries, or the hiring company's base if it has none.
  - **Find peer companies** runs one paid web company search (about $0.007), built from the hiring company's stage and industries.
- **The plan is versioned.** Every change is a new version, so we know which version found whom: mode, target, budget, titles, countries, or a company added, pinned or removed. A new plan starts **paused**, so opening the tab never starts a paid search.
- **A run:**
  1. The pool: the desk's own people through the existing desk search ([people search](people-search.md) by hiring profile, otherwise by keywords), 40 at most.
  2. The web: the plan's searches, in order:
     - each of the first two titles at each target company (pinned first, then companies releasing talent, then named, added, known, peer…);
     - then each of the first three titles across each of the first three countries.

     A search is not repeated for the same role within 30 days. A run makes at most 8 searches, with 10 results each.
  3. Each found profile goes through [web discovery](web-discovery.md) into the pool. It then joins the role through the ordinary pair-and-matching path (`_ensure_pair`, cause `sourced`).
  4. The [talent-release radar](talent-release-radar.md): up to 3 news searches about the role's companies and market. A company releasing talent is searched first on the next run (after pinned ones), and one found by market news joins the plan.

  A run stops when:
  - the role has its target of strong suggestions waiting (a strong suggestion is priority, not yet contacted, and not stopped);
  - a budget is reached;
  - it hits its search limit;
  - or the plan has no searches left.

  It records how many people were found, new to the desk, already known, refused and strong; the results of each search; and its cost. Someone found by two searches in one run counts once.
- **Gates on everyone found.** These come on top of the ordinary checks: identity, the span check, coverage and suppression. A person is refused when:
  - **stop**: they asked not to be contacted;
  - **off-limits**: they work now at an active client (any company with an open or on-hold role), at a client where we placed someone in the last 12 months, or at a company on the desk's own list (companies merged into one share its status);
  - **client block**: the client said no to them;
  - **not for them**: they said they would not consider this kind of job;
  - **outside countries**: they are outside the role's countries.

  Refused people stay in the pool; they are just not suggested. The older desk search ("Find more people", [sourcing feeder](sourcing.md)) also skips stopped and off-limits people (`never_sourced`).
- **Budgets.** Each role has a monthly budget (default $5), and the desk has one too (default $50; only an owner changes it). Before each search, a run checks both, with a margin of $0.01 per search. Sourcing spend is kept separate from the model budget, so a busy search month never stops the desk reading CVs ([tasks and costs](tasks-and-costs.md)).
- **The clock** (`__main__`) checks every 10 minutes; `SOURCING_AUTO=false` turns it off.
  - When runs are due: daily plans after 24 hours, weekly after 7 days, continuous every hour while the role is short of its target.
  - Each due run becomes a `sourcing_run` task, one per role at a time, with no retries. "Run now" queues the same task.
- **Searches name roles, companies and places, never a person.**

**Since 2026-10-19:** suggestions to review are ordered strong first, then by how many of the role's strong-plus items
they meet, then newest; each card shows those items as tags (met, partly, missing, to ask).

**Since 2026-10-17** ([decision](../../decisions/2026-10-17-evidence-for-strong-matches.md)): after the searches, each target company searched gets its job adverts read in the background ([employer evidence](employer-evidence.md)), and a person the run finds on the web who is a strong match gets an [evidence check](evidence-checks.md). The suggestion card shows the check, with "Check deeper" for the others.

**Since phase 1b** ([sourcing strategy](sourcing-strategy.md)): what a run searches comes from the strategy: the next batch of 5 companies in the open tiers (A and B at first), each with its title variants until it is exhausted; country-wide searches only when the owner opens them. After the searches, the employers of the people added are profiled by Exa id and their career readings queued; then the list grows (snowball), then the radar. Searches record per company what they found, what was already known and what was relevant. The plan carries the talent DNA, the rules and the open tiers.

## Depends on
- [web-discovery.md](web-discovery.md)
- [process.md](process.md): `_ensure_pair`, `not_wanted_by`
- [people-search.md](people-search.md) and [sourcing.md](sourcing.md): the pool adapters
- [companies.md](companies.md)
- [company-research.md](company-research.md): industries and stage
- [coverage-gate.md](coverage-gate.md)
- [pipeline.md](pipeline.md): client blocks, placements
- [tasks-and-costs.md](tasks-and-costs.md)
- [permission-and-stop.md](permission-and-stop.md)
- [talent-release-radar.md](talent-release-radar.md)

## Used by
- [sourcing-results.md](sourcing-results.md)
- [http-api.md](http-api.md)
- [cockpit.md](cockpit.md): the role's Sourcing tab

## Contracts
- `GET /v1/jobs/{id}/sourcing`: the plan, budgets, the last 10 runs, and up to 100 suggestions waiting, each with who found them.
- `PATCH /v1/jobs/{id}/sourcing/plan {mode?, target?, monthly_budget_usd?, role_variants?, countries?}`
- `POST /v1/jobs/{id}/sourcing/targets {name}`
- `PATCH /v1/jobs/{id}/sourcing/targets/{company_id} {pinned?, removed?}`
- `POST /v1/jobs/{id}/sourcing/peers`
- `POST /v1/jobs/{id}/sourcing/run`: answers 202 and queues a task.
- `GET /v1/off-limits`, `POST /v1/off-limits {name, until?, note?}`, `DELETE /v1/off-limits/{id}`
- The tables of migration `0026` ([persistence](persistence.md)).

## Tests
`core/tests/test_autosource.py` uses a fake Exa: synthetic people, nothing spent. It proves:
- a new plan waits paused, and every change is a version;
- a run finds people on the web and refuses off-limits people and people outside the role's countries;
- someone found by several searches counts once;
- a search is not repeated within 30 days, and the target stops a run;
- a budget stops web search but not the free pool;
- someone who said stop, or who was erased, is never suggested again;
- the desk search skips stopped and off-limits people too;
- the clock runs only plans that are due;
- peer companies from a company search join the plan;
- the routes work, and only an owner changes the desk budget.

## Known limits
- Not yet run on a real role. The phase 1 gate (two weeks on a real role) is the owner's to declare.
- Exa monitors (results pushed to us instead of fetched) need a public HTTPS address, so they wait for going live (phase 3).
- One page of results per search (10); a search never pages on to the next 10.
