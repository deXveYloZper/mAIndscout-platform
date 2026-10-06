# Cockpit (recruiter UI)

**Status:** built (Slice 0 screens)
**Slice / milestone:** Slice 0 / Milestone E (part 2)
**Code:** `cockpit/` (Next.js 15, React 19, TypeScript, plain CSS on design tokens, Lucide icons). Design: [../../design/PLAN.md](../../design/PLAN.md).

## What
Where the recruiter works: jobs list, job page with the three bands, person page, and the inbox. Runs on `http://localhost:3001` with `npm run dev` in `cockpit/`.

## Why
The vision's working day: open a job, drop CVs on it, work the priority pile, answer only the questions the system may not decide itself (VISION "Attention"; HANDOFF Milestone E).

## How
- **Design (2026-10-06):**
  - `app/globals.css` is one token-driven system: colours, spacing, radius, shadow and motion.
  - Type: IBM Plex Sans for the interface, Special Elite for page titles (the website's voice), Plex Mono for numbers.
  - Bands have meaning in colour (Priority amber, Review later slate, Do not submit muted red).
  - Motion stays under 250 ms and is off with reduced motion.
- **Shell (`app/(desk)/layout.tsx`, `components/shell/`):**
  - a grouped sidebar (Work, Find, Desk) with icons and the inbox count (`/v1/nav`); it collapses, and becomes a drawer on phones;
  - a top bar with the find bar and account menu;
  - **⌘K / Ctrl K** finds people, jobs and companies by name as you type (`/v1/lookup`) and offers actions;
  - shortcuts: `/` find, `g` then `t j i p c s r` to go somewhere, `?` lists them.
  - Sign-in and invite links use a bare layout (`app/(public)/`).
- **Today (`/`):** the start of the day (`/v1/today`):
  - priority people, inbox waiting, people going stale and the pool, as split-flap counts;
  - priority people by job;
  - recent activity.
- **Uploads** use drop zones (`components/DropZone.tsx`): drag files on, or click to choose.
- **Errors** inside the desk keep the navigation (`app/(desk)/error.tsx`). Search in your own words says when the model is unavailable, and keeps the filters.
- **All data comes from the API, server-side.** `lib/api.ts` adds the operator token and org id from `cockpit/.env.local`; the browser never sees them. Actions (`app/actions.ts`) are server actions that call the API and refresh the page.
- **Jobs (`/jobs`):** list with band counts and what waits for review, whole rows clickable; drop a job ad to create a job.
- **Job (`/jobs/[id]`):**
  - a header with the company, where, the ad and the inbox;
  - band tiles that act as tabs (Priority, Review later, Do not submit, Archived);
  - section tabs: People, Hiring profile, Find more, Countries;
  - each person as a card with tier, tags, reason, a bar of evidence / to ask / missing / conflict, Brief, and Move (a band change with a reason).
- **People and person pages show a person's jobs only when they fit** (Priority or Review later) **or something happened on that pair** (contacted, submitted, passed, client answered). A plain "Do not submit" stays on the job page; otherwise the person reads "no match on open jobs" (owner, 2026-10-06).
- **Brief everywhere:** a Brief button on every People row and every job card, and "Brief for a call" in the person header (a job-free Brief, `/people/[id]/brief`).
- **Person (`/people/[id]`):**
  - a header card: name, current role, where, freshness, tags, put on a job, draft a message, the CV;
  - section tabs: Overview (jobs, career profile, relationship), Facts, Messages, Timeline, Documents (and Forget).
- **Uploads** are stored at once and read in the background; each file's row fills in when its read finishes (you can leave the page).
- **Costs (`/costs`):** this month's spend against the budget, by purpose and day.
- **Companies (`/companies`, `/companies/[id]`):** search; who we know at a company (one row per person, all roles); the company's jobs; its public facts, each with the page and quote it came from, and "Research now" ([company-research.md](company-research.md)). Career rows on a person link to their company.
- **People (`/people`):** everyone, or only those on no job (the pool); upload CVs without a job.
- **Messages (person page) and Mailbox (`/mailbox`) ([messages.md](messages.md)):** draft, edit, put in your Gmail or Outlook drafts or copy; mark sent or replied; connect or disconnect the mailbox.
- **Import (`/import`) ([imports.md](imports.md)):** upload a CSV, preview, tick what you vouch for, free allowance shown, quote beyond it; download everyone as CSV.
- **Refresh (`/refresh`) ([freshness.md](freshness.md)):** stale people to re-contact, most valuable first with why; stale clients to reconnect with; stale tags on People, person and company pages.
- **Pipeline ([pipeline.md](pipeline.md)):** "Move to" on the gap table with the notes and reasons each move needs; stage counts on the job page; "blocked by client" tags; blocks with "Lift block" on the person page.
- **Relationship ([relationship-memory.md](relationship-memory.md)):** on the person and company pages, last contacted / verified, log a call or note, the timeline; tags on people and talent-pool filters on People; contacts at client companies.
- **Brief ([brief.md](brief.md)):** call questions about the person and for the job, answered inline (confirmed / not met / note), asked, not needed; linked beside priority people and from the gap table.
- **Search (`/search`) ([people-search.md](people-search.md)):** a search bar in your own words, "Understood as", results best first with ✓ ~ ✗ per criterion; filters under "Refine"; results with what each person meets, "Put on job"; "Find more people" on a job describes its profile search.
- **Match ([matching.md](matching.md)):** on the person-on-job page, the tier with the rules that fired and a verdict per requirement; on the job page, the tier beside each person.
- **Hiring profile ([hiring-profiles.md](hiring-profiles.md)):** on the job page, requirements by strength with source, quote, approve / reject and a strength control; the hiring company's facts; who we know at target companies; intake notes; add a requirement.
- **Career profile ([career-profiles.md](career-profiles.md)):** on the person page, the reading, each dimension with its reason, notable items, questions for the call, and how each job was read with a "Correct" control.
- **Coverage ([coverage-gate.md](coverage-gate.md)):** a job's "Archived: outside coverage" section and its "Countries this job accepts" panel; an archived person's note with "Bring back"; an "archived" tag in People.
- **Job (`/jobs/[id]`):** "Find more people" when priority is thin (cap, result, campaign history; [sourcing.md](sourcing.md)); counts and review link in the header; where the job is; mobility as three facts (must live in, visa sponsorship, relocation); requirements grouped by kind with years and education tags; stale-date warning; drop several CVs at once, read one by one with a result row per file; Priority open by default, Review later and Do not submit folded away; each person's reason in plain words; band override with a note; requirements marked "decides the band" when distinctive; process dates.
- **Person on a job (`/jobs/[id]/people/[cid]`):** the gap table ([gap-table.md](gap-table.md)): per-status counts, every requirement with status, reason and snippets, approved or proposed, a "To ask on the call" list, "They have …" on missing skills, the official-coverage line (thin or above the floor), status controls (Mark seen, Submitted with a note, We passed with a reason, Reopen), the history of band and status changes, band change. The job page shows each person's status; people we passed on are dimmed; a "thin" tag marks people whose must-haves are not yet backed by approved facts. Names on the job page open this view; the job page shows evidence / missing / conflict / ask counts per person.
- **Person (`/people/[id]`):** jobs and bands; name, contacts, career (with periods and overlap warnings), education, location, skills; every fact with its status, Approve and Reject, and its source snippet with a link to the original file; "Put on job"; "Add or correct a fact" (saved as approved).
- **Inbox (`/inbox`):** inside a job, default is its priority people ("Everyone on this job" widens it); without a job, everything, with a job picker. Cards: confirm a contact (approve as is, type the correct value, or reject), who-is-this note (named links, open the CV, type a missing name), revision diff (keep official or accept new), same job or two, contradiction (pick one).
- **Forget this person** at the foot of the person page (type `forget`); see [erasure.md](erasure.md).
- **Sign-in** (`/login`, `/invite/[token]`, `/account`, `/members` for owners) ([access.md](access.md)): every page needs a signed-in user; the header shows who, a desk switcher (more than one desk) and Sign out.
- **Original files** are streamed through `/files/[id]`, which only accepts a document id. Only a real PDF or plain text opens in the browser; anything else downloads (`nosniff`, sandboxing CSP), so an uploaded HTML or SVG never runs on the desk's origin. `lib/api.ts` is `server-only`: the operator token can never be bundled into the browser.
- **Bound to this machine** (`next dev -H 127.0.0.1`): the cockpit has no login of its own yet, so it must not be reachable from the network.
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
