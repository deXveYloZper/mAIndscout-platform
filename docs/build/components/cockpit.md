# Cockpit (recruiter UI)

**Status:** built (Slice 0 screens)
**Slice / milestone:** Slice 0 / Milestone E (part 2)
**Code:** `cockpit/` (Next.js 15, React 19, TypeScript, plain CSS)

## What
Where the recruiter works: jobs list, job page with the three bands, person page, and the inbox. Runs on `http://localhost:3001` with `npm run dev` in `cockpit/`.

## Why
The vision's working day: open a job, drop CVs on it, work the priority pile, answer only the questions the system may not decide itself (VISION "Attention"; HANDOFF Milestone E).

## How
- **All data comes from the API, server-side.** `lib/api.ts` adds the operator token and org id from `cockpit/.env.local`; the browser never sees them. Actions (`app/actions.ts`) are server actions that call the API and refresh the page.
- **Jobs (`/`):** list with band counts and what waits for review; upload a job ad to create a job.
- **Uploads** are stored at once and read in the background; each file's row fills in when its read finishes (you can leave the page).
- **Costs (`/costs`):** this month's spend against the budget, by purpose and day.
- **Companies (`/companies`, `/companies/[id]`):** search; who we know at a company (one row per person, all roles); the company's jobs; its public facts, each with the page and quote it came from, and "Research now" ([company-research.md](company-research.md)). Career rows on a person link to their company.
- **People (`/people`):** everyone, or only those on no job (the pool); upload CVs without a job.
- **Job (`/jobs/[id]`):** "Find more people" when priority is thin (cap, result, campaign history; [sourcing.md](sourcing.md)); counts and review link in the header; where the job is; mobility as three facts (must live in, visa sponsorship, relocation); requirements grouped by kind with years and education tags; stale-date warning; drop several CVs at once, read one by one with a result row per file; Priority open by default, Review later and Do not submit folded away; each person's reason in plain words; band override with a note; requirements marked "decides the band" when distinctive; process dates.
- **Person on a job (`/jobs/[id]/people/[cid]`):** the gap table ([gap-table.md](gap-table.md)): per-status counts, every requirement with status, reason and snippets, approved or proposed, a "To ask on the call" list, "They have …" on missing skills, the official-coverage line (thin or above the floor), status controls (Mark seen, Submitted with a note, We passed with a reason, Reopen), the history of band and status changes, band change. The job page shows each person's status; people we passed on are dimmed; a "thin" tag marks people whose must-haves are not yet backed by approved facts. Names on the job page open this view; the job page shows evidence / missing / conflict / ask counts per person.
- **Person (`/people/[id]`):** jobs and bands; name, contacts, career (with periods and overlap warnings), education, location, skills; every fact with its status, Approve and Reject, and its source snippet with a link to the original file; "Put on job"; "Add or correct a fact" (saved as approved).
- **Inbox (`/inbox`):** inside a job, default is its priority people ("Everyone on this job" widens it); without a job, everything, with a job picker. Cards: confirm a contact (approve as is, type the correct value, or reject), who-is-this note (named links, open the CV, type a missing name), revision diff (keep official or accept new), same job or two, contradiction (pick one).
- **Forget this person** at the foot of the person page (type `forget`); see [erasure.md](erasure.md).
- **Original files** are streamed through `/files/[id]`, which only accepts a document id.
- Same palette and fonts as the public site; dense layout; works at phone width.

## Depends on
[http-api.md](http-api.md) only.

## Used by
The recruiter.

## Tests
`npm run typecheck` and `npm run build` (in CI). End to end: `npm run e2e` (Playwright, 17 tests, real files and model against a production build, fresh `maindscout_e2e` database; local only). Report: [../../slice-0/TEST-REPORT.md](../../slice-0/TEST-REPORT.md). Checked by hand on 2026-10-02 against the running API with all 13 test files: job pages, inbox (Ovi's two emails, Yousuf's unreadable name), person page, approving a name, original-file download.

## Known limits
- e2e is local only (needs the real files and the model key).
- Uploads run in the request: about 15 seconds per CV while the page waits.
- No sign-in: whoever can reach the cockpit acts as the operator. Run it only on a trusted machine or network until accounts exist.
