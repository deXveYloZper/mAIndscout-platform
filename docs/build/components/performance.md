# Performance

**Status:** first check done 2026-10-05
**Code:**
- `core/maindscout/evals/perf.py`: `python -m maindscout perf-seed` and `perf-check`;
- migration `0023` (indexes);
- `core/tests/test_performance.py`.

## What
A repeatable check of every main screen on a desk of realistic size, with no model calls and no cost:
- **`perf-seed`** builds `maindscout_perf`:
  - 3,000 synthetic people from the demo generator (careers, skills, education, career profiles);
  - 200 companies;
  - 20 jobs whose requirements are copied from the dev desk's real jobs;
  - 150 people per job, matched by the ordinary pairing code;
  - 200 review cards and 5,230 timeline entries.

  It takes about 30 minutes.
- **`perf-check`** times each screen through the real HTTP API as a signed-in owner (median of 3) and counts its database queries. A query count that grows with the desk is a per-row loop.

## Results (3,000 people, 3,000 on jobs, 42,330 facts)

| Screen | Before | After code fixes | After code + indexes |
|---|---|---|---|
| Jobs list | 13,195 ms (203 queries) | 15,451 ms (203) | **271 ms (14)** |
| Job page, 150 people | 1,023 ms (17) | 500 ms (17) | **397 ms (17)** |
| People list | 65,884 ms (11,110) | 1,796 ms (14) | **2,289 ms (14)** |
| Person page | 240 ms (29) | 167 ms (29) | **173 ms (29)** |
| Gap page | 119 ms (11) | 125 ms (11) | **82 ms (11)** |
| Inbox, one job | 111 ms (10) | 155 ms (10) | **42 ms (4)** |
| Inbox, all jobs | 13,777 ms (200) | 14,369 ms (200) | **507 ms (11)** |
| Companies list | 56,873 ms (10,622) | 298 ms (6) | **237 ms (6)** |
| Company page | 266 ms (21) | 190 ms (21) | **160 ms (21)** |
| Search (structured) | 944 ms (6) | 1,021 ms (6) | **914 ms (6)** |
| Refresh list | 35,836 ms (12,944) | 1,822 ms (17) | **1,606 ms (17)** |
| Export, everyone | 104,778 ms (26,110) | 3,053 ms (19) | **3,373 ms (19)** |
| Approve a fact (re-match) | 382 ms (48) | 245 ms (35) | **149 ms (20)** |
| Change a band | 54 ms (6) | 50 ms (6) | **46 ms (6)** |

Re-matching one person on one job: 31 → 16 queries, about 190 → 100 ms. Re-matching a 150-person job takes 6.5 s, so a job of more than 40 people now re-matches in the background.

## What was wrong, and the fixes
- **Missing indexes (migration `0023`).** Postgres doesn't index foreign keys. Looking up one fact's evidence scanned all 42,000 evidence rows (about 90 ms), once per inbox card: 17 s for the all-jobs inbox, and the jobs list builds that inbox. Indexes now cover:
  - evidence and readings by fact;
  - facts by subject;
  - people on a job;
  - review cards and their items;
  - documents by person;
  - client blocks;
  - messages by person;
  - company aliases;
  - CV readings by document;
  - open tasks by dedupe key.
- **Per-person loops:**
  - "stale" on the people list, the Refresh list and export each asked two to four queries per person. One grouped pass now covers the whole desk (`relationship.last_dates_many`, `freshness.people_status`), tested to agree with the one-person functions.
  - Company search fetched each company and its aliases separately.
  - Export read each person's facts separately.
  - The inbox fetched names and CVs per "Who is this?" card.
- **Matching:**
  - the job's requirements and the person's facts are loaded once (`process.pair_inputs`), and the gap table, the quick triage and the match are all derived from them;
  - the gap table is built once, not twice, and without snippets, which only the gap page shows;
  - companies and their public facts are read in two queries per career, not two per job.
- **A stable reason.** Requirements are now always in the ad's order. Before, the "first missing must-have" named in a reason followed whatever order the database returned rows in, so it could flip between re-matches and write a band-history event when nothing had changed.
- **Big jobs re-match in the background.** Changing a requirement on a job with more than 40 people queues one `rematch_job` task (deduplicated), and the job page says it's running. Smaller jobs still re-match before the page returns.

## The owner's desk, 2026-10-20 ("it takes forever to load once i press buttons on the toolbar")
Measured on the owner's own data (the marketing role: 187 people, 100 suggestions) and the owner's laptop (7.6 GB,
about 1 GB free while Docker, Chrome and the desk run, 1.4 GB in Windows' memory compression):
- **The development server was most of it.** `npm run dev` compiles a page when it is first opened and takes far more
  memory: a sidebar click took 13 s, the People page 30–36 s, the marketing Sourcing tab about a minute. The same
  pages from a production build (`npm run desk`: build, then serve on 3001) open in 0.2–1.1 s.
- **The Sourcing tab asked the same questions per person** (903 queries, about 7 s of API work): where each person
  lives, their current employers and whether they are a reach, one query each, some twice, and "how many strong are
  waiting" twice. Now a read-only page memo (`api/memo.py`) answers each once, everyone's places and career steps are
  loaded in one query, the target companies' status in one, and a company's merged ids and "does the role ask for
  luxury" are worked out once: 82 queries, under a second of work.
- **The card read every person's full gap table** for one line, where they live: now only that requirement is read.
  The job page's gap bars no longer load source quotes (counts only).
- **Each card's buttons were given the whole card** (every fact, twice per card, in a 1.25 MB page): now only what
  they use (`CardKeys`).
- **Reading a country from a place** tried some 300 names one search at a time: now one compiled pattern, the same
  answers.
- The API's own work, warm: the marketing job page 3.1 s → 0.45 s, its Sourcing tab 6.7 s → 0.9 s.

## Still slow, and why it's left for now
- **People list (2.3 s):** 0.85 s to build in the API; the rest is turning 3,000 rows into JSON and showing them. The fix is paging the list in the cockpit when desks reach this size.
- **Export (3.4 s):** a download of everyone, used rarely; acceptable.
- **Refresh (1.6 s) and structured search (0.9 s):** both read every person's profile or dates; acceptable at this size. They should be revisited at 10,000+ people.
- **Seeding a person** (career profile build) takes about 0.3 s, matching about 0.1 s per job. This is the cost of reading a CV, apart from the model call.
- **The model call happens inside the reading task's transaction.** Not a problem with 2 workers. It needs revisiting if workers are scaled up.

## Running it again
```bash
python -m maindscout perf-seed --people 3000 --jobs 20 --per-job 150
python -m maindscout perf-check
```
Compare with the table above. A screen whose query count grows with `--people` has a per-row loop.

## Tests
`core/tests/test_performance.py` (5):
- a big job re-matches in the background and says so (deduplicated);
- a small job still re-matches at once;
- the gap table is the same without snippets and from preloaded facts;
- the jobs list counts what each job's inbox shows;
- a second re-match writes no event.

Also `test_freshness.py`: the whole desk at once agrees with one person at a time.
