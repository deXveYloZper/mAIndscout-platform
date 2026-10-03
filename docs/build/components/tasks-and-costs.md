# Background tasks and the cost ledger

**Status:** built (intelligence track I1, part 2)
**Code:** `core/maindscout/api/tasks.py` (queue, workers), `api/task_handlers.py` (what each task does), `api/costs.py` (ledger, budget), tables `task` and `cost_ledger` (migration `0009`), cockpit `components/MultiUpload.tsx`, `app/costs/`

## What
- **Tasks:** slow work (reading a CV now; company research and profiles next) runs in the background, several at a time, instead of inside the web request.
- **Cost ledger:** every paid call (model tokens, web sources) is recorded with its purpose, model, tokens and dollars; a monthly budget pauses paid work before it overspends; a Costs page shows the month.

## Why
The intelligence track adds many model and search calls per CV (plan section 4.8). They must run in parallel, retry safely, never block the recruiter, and stay within a budget the owner sets.

## How
- **Queue:** a `task` row per unit of work; workers claim the most urgent ready task with `FOR UPDATE SKIP LOCKED`, so two workers never take the same one. Each task runs in its own transaction: a failure rolls back everything it did, records the error, and retries with backoff (5 s, 10 s, 20 s…) up to its limit; a budget stop is permanent (no retries). A dedupe key stops the same work being queued twice.
- **Workers:** `python -m maindscout serve` starts 2 workers in the API process (`WORKERS` to change, `--no-workers` to turn off); `python -m maindscout worker --threads N` runs them on their own.
- **Uploads:** the cockpit stores each CV and queues its reading (`?background=true` on the upload routes, `202` with a task id); rows fill in as each read finishes (`GET /v1/tasks?ids=`). The API's synchronous mode stays for scripts and tests.
- **Ledger:** `cost_ledger` rows per call (org, purpose, model, tokens, sources, USD, subject, task). Shared company research (I2) is recorded without an org.
- **Budget:** `MONTHLY_BUDGET_USD` in `core/.env` (default 25). Before paid work, this month's spend is checked; at the budget, work stops with a clear message (HTTP 402 in synchronous calls, a failed task in the background).
- **Erasure:** cost rows keep their numbers (accounting) but lose their link to the person and their documents; verify checks no link remains.

## Depends on
[process.md](process.md), [persistence.md](persistence.md), [intelligence.md](intelligence.md) (the model client reports cost).

## Used by
[http-api.md](http-api.md), [cockpit.md](cockpit.md), and every later intelligence task (I2-I6).

## Tests
`core/tests/test_tasks.py` (9): runs once and keeps its result; retries with backoff then stops with the error; dedupe; two workers never take the same task; a background upload is read by a task; every read is in the ledger; the budget stops paid work; erasure unlinks cost rows; a paid call stays in the ledger when its task fails. e2e: uploads progress in the background; Costs page.

Since I3: a paid call stays in the ledger even if its task fails afterwards (the runner writes the cost rows again after the rollback); `serve` and `worker` seed the claim and flag registries at start.

## Known limits
- Workers in the API process are fine for one desk; separate worker processes come with deployment.
- The ledger records what the provider reports (`cost_in_usd_ticks`, which includes web sources). Shared research has its own budget, `RESEARCH_MONTHLY_BUDGET_USD` (default 10) ([company-research.md](company-research.md)).
