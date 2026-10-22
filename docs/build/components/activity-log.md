# Activity log

The owner, 2026-10-22: "add logs that are easy to track, what buttons do, what is happening, so errors are easier to
read and unearthed when they happen and our logics are clear if they work, what is searched, what prompts do we ask
xAI".

## What it records
One line per thing that happened, in plain words, with its detail one click away:
- **button**: every action a page sends (`api/buttons.py` names them as the buttons do: "Search now", "Build the company
  list", "Confirmed the requirements"), who pressed it, how long it took, and a refusal (4xx) as a warning.
- **step**: the desk's own logic, said plainly: "Search now: this role's company list was never built, so it is built
  first", "Search (manual): 11 searches planned at 5 companies, in IT" (with every search listed), "Competitor research
  for Ferrari: 42 kept of 43 found in 3 rounds" (with the business lines, kept, left out and refused), "The desk settled
  'GUCCI SHOWROOM' / 'Gucci': the same company (a shop of the brand)".
- **task**: each background task that ended, with its result ("Search: done in 64s · status done, stop_reason
  run_limit, found 123, new 60"). The many per-person readings are logged only when they fail.
- **search**: each Exa call: its words, kind, country, how many results, the first titles, the cost.
- **model**: each model call: what for, the instructions and the input, the answer, model, tokens, cost and time; the
  web research also lists the pages it opened. A call carrying a person's own text (a CV, a call, their career titles,
  an evidence check, a message draft) keeps only its size, never the text.
- **error**: a failed task, a failed model or Exa call, a server error, and a page that crashed in the browser (the
  desk's error screens report themselves), each with its trace.

Lines carry the desk, the role, the task and the actor when known, so a role's story reads on its own.

## Where to read it
- The desk's **Activity** page (sidebar), filtered by kind, "only problems", a role, or words.
- A role's Sourcing tab: "What the desk did".
- `python -m maindscout activity [--job ID] [--kind K] [--since MIN] [--full]` for the full detail in a terminal.

## How
- `maindscout/activity.py`: `note`, `step`, `error`; `about(...)` sets the org, role, task and actor for everything
  noted inside it (the task runner and the API middleware use it).
- The model, web-research and Exa clients are wrapped once in `intelligence/recording.py` (`ObservedChat`,
  `ObservedSearch`, `ObservedExa`), so no call is missed.
- Written in its own short transaction (the story of a task that failed and rolled back survives), in the `desk_log`
  table (migration 0031), kept 30 days, and never able to break the work it describes.
- `ACTIVITY_LOG=off` turns it off.
