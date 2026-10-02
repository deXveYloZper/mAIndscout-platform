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
- **Jobs (`/`):** list with band counts; upload a job ad to create a job.
- **Job (`/jobs/[id]`):** stale-date warning; drop several CVs at once; Priority open by default, Review later and Do not submit folded away; each person's reason in plain words; band override with a note; requirements marked "decides the band" when distinctive; process dates.
- **Person (`/people/[id]`):** jobs and bands; name, contacts, career (with periods and overlap warnings), education, location, skills; every fact with its status, Approve and Reject, and its source snippet with a link to the original file.
- **Inbox (`/inbox`):** default is a job's priority people; "Everyone" widens it. Cards: confirm a contact (approve as is, type the correct value, or reject), who-is-this note, revision diff (keep official or accept new), same job or two, contradiction (pick one).
- **Original files** are streamed through `/files/[id]`, which only accepts a document id.
- Same palette and fonts as the public site; dense layout; works at phone width.

## Depends on
[http-api.md](http-api.md) only.

## Used by
The recruiter.

## Tests
`npm run typecheck` and `npm run build` (in CI). Checked by hand on 2026-10-02 against the running API with all 13 test files: job pages, inbox (Ovi's two emails, Yousuf's unreadable name), person page, approving a name, original-file download.

## Known limits
- No automated UI tests yet.
- Uploads run in the request: about 15 seconds per CV while the page waits.
- No sign-in: whoever can reach the cockpit acts as the operator. Run it only on a trusted machine or network until accounts exist.
- Erasure (Milestone F) has no button yet.
