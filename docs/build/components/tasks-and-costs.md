# Background tasks and the cost ledger

**Status:** built (intelligence track I1, part 2)
**Code:** `core/maindscout/api/tasks.py` (queue, workers), `api/task_handlers.py` (what each task does), `api/costs.py` (ledger, budget), tables `task` and `cost_ledger` (migration `0009`), cockpit `components/MultiUpload.tsx`, `app/costs/`

## What
- **Tasks:** slow work (reading a CV now; company research and profiles next) runs in the background, several at a time, instead of inside the web request.
- **Cost ledger:** every paid call (model tokens, web sources) is recorded with its purpose, model, tokens and dollars; a monthly budget pauses paid work before it overspends; a Costs page shows the month.

## Why
The intelligence track adds many model and search calls per CV (plan section 4.8). They must run in parallel, retry safely, never block the recruiter, and stay within a budget the owner sets.

## How
- **Queue:** a `task` row per unit of work; workers claim the most urgent ready task with `FOR UPDATE SKIP LOCKED`, so two workers never take the same one. Each task runs in its own transaction: a failure rolls back everything it did, records the error, and retries with backoff (5 s, 10 s, 20 s…) up to its limit; a budget stop is permanent (no retries). A dedupe key stops the same work being queued twice. A task left `running` for 30 minutes (its process died) is queued again, or failed once out of attempts, which frees its dedupe key. Shared public work (company research) is visible to the desk that asked for it. The budget is a soft cap: overshoot is bounded by the calls already in flight.
- **Workers:** `python -m maindscout serve` starts 2 workers in the API process (`WORKERS` to change, `--no-workers` to turn off); `python -m maindscout worker --threads N` runs them on their own. An idle worker looks at the queue less and less often (1 s, 2 s, 4 s … up to 15 s); a task committed in the API process wakes them at once, so a button's work starts straight away, and work queued for later or by another process is seen within 15 s (2026-10-29: two workers looking every second made about 170,000 queries a day on an idle desk).
- **Uploads:** the cockpit stores each CV and queues its reading (`?background=true` on the upload routes, `202` with a task id); rows fill in as each read finishes (`GET /v1/tasks?ids=`). The API's synchronous mode stays for scripts and tests.
- **Ledger:** `cost_ledger` rows per call (org, purpose, model, tokens, sources, USD, subject, task). Shared company research (I2) is recorded without an org.
- **Budget:** `MONTHLY_BUDGET_USD` in `core/.env` (default 25). Before paid work, this month's spend is checked; at the budget, work stops with a clear message (HTTP 402 in synchronous calls, a failed task in the background).
- **Erasure:** cost rows keep their numbers (accounting) but lose their link to the person and their documents; verify checks no link remains.
- **Sourcing has its own budget** (next build, phase 1). Purposes starting `sourcing_` (`sourcing_exa_people`, `sourcing_company_search`, `sourcing_exa_news`, `sourcing_company_profile`, `sourcing_talent_dna`) are left out of the monthly model budget, so a busy search month never stops the desk reading CVs. They are checked against the role's and the desk's sourcing budgets instead (`costs.sourcing_spent`, [sourcing engine](sourcing-engine.md)). `GET /v1/costs` adds `sourcing_usd` and `sourcing_budget_usd`. The Costs page shows them as one line and labels the sourcing rows.
- **`sourcing_strategy`** builds a role's strategy in the background (one per role at a time, no retries).
- **Long sourcing work takes turns across the desk** (2026-10-30): `sourcing_strategy` and `sourcing_run` add shared
  companies inside a transaction of up to ten minutes, so two at once waited for each other's new rows. Three roles'
  company lists built at once: two added "Skyrora" and "Kongsberg Defence & Aerospace" in opposite order, and Postgres
  ended both as a deadlock (both failed, paid work never retried). Such a task now takes a desk-wide turn (a Postgres
  advisory lock held until its transaction ends); one whose turn has not come goes back to the queue for 15 seconds,
  its attempt not spent, and the worker moves on to other work. The activity log says once that it "waits its turn".
  Three roles' lists and searches now run one after another instead of side by side.
- **A deadlock gets one more try** (2026-10-30), even for work queued to run once: it is another task's timing, not the
  task's fault. Its paid calls stay in the ledger, so the second try spends them again.
- **`work_reading`** (2026-10-28) reads one strong or possible person's own words against the role's confirmed work
  lines (one per person and role, deduplicated; quiet in the activity log; purposes `work_lines` and `work_reading`,
  inside the monthly model budget, a spent budget skips the reading) ([core-work reader](core-work-reader.md)).
- **The sourcing clock** queues `sourcing_run` tasks (one per role at a time, no retries) every 10 minutes for plans that are due; `SOURCING_AUTO=false` turns it off. A tick that fails is written to the activity log once until the failure changes, and so is the recovery (2026-10-28; the sourcing and mailbox clocks used to fail silently).
- **The Costs page names every purpose in the ledger** (2026-10-28: 11 had shown as raw keys, from role briefs to the talent map).
- **Dedupe is a check before the insert**, with no lock: two callers in the same instant could queue the same key twice. It never happened (2,730 tasks, 2026-10-28), and a unique index would refuse "Search now"'s next round, which is queued under the same key while its batch still runs ([decision](../../decisions/2026-10-28-architecture-review.md)).

## Depends on
[process.md](process.md), [persistence.md](persistence.md), [intelligence.md](intelligence.md) (the model client reports cost).

## Used by
[http-api.md](http-api.md), [cockpit.md](cockpit.md), every later intelligence task (I2-I6), [sourcing-engine.md](sourcing-engine.md) and [sourcing-results.md](sourcing-results.md).

## Tests
`core/tests/test_tasks.py` (12): runs once and keeps its result; retries with backoff then stops with the error; dedupe; two workers never take the same task; a background upload is read by a task; every read is in the ledger; the budget stops paid work; erasure unlinks cost rows; a paid call stays in the ledger when its task fails; an idle worker looks less often and new work wakes it; long sourcing work takes turns and a waiting task spends no attempt; a deadlock gets one more try, not endless ones. e2e: uploads progress in the background; Costs page.

Since I3: a paid call stays in the ledger even if its task fails afterwards (the runner writes the cost rows again after the rollback); `serve` and `worker` seed the claim and flag registries at start.

## Known limits
- Workers in the API process are fine for one desk; separate worker processes come with deployment.
- The ledger records what the provider reports (`cost_in_usd_ticks`, which includes web sources). Shared research has its own budget, `RESEARCH_MONTHLY_BUDGET_USD` (default 10) ([company-research.md](company-research.md)).
