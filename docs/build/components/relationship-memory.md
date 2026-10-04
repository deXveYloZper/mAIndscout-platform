# Relationship memory

**Status:** built (Slice 4, step 1)
**Code:** `core/maindscout/api/relationship.py`, migration `0017` (`activity`, `client_contact`, `candidate_tag`), cockpit `components/Relationship.tsx`, `LogActivity.tsx`, `AddContact.tsx`, the person, company and People pages

## What
The desk's memory of every relationship.
- **Log** a call, email, meeting, message or note with a person or a client company: a line of what happened, when (default today), who reached out, optionally which job, and for a company, which contact.
- **One timeline** per person or company. It joins what the recruiter logs with what the platform already records: CVs read, band and stage changes, Brief answers, and jobs opened at the company. Nothing is entered twice.
- **Last contacted** (the last call, email, meeting or message, or Brief answer) and **last verified** (the last time a person confirmed or refreshed the facts: an approved or typed fact, a Brief answer, a CV read). For a company, last verified is when its public facts were researched.
- **Tags as talent pools:** tag people ("InSAR pool" becomes `insar-pool`); the People page lists the pools and filters by one.
- **Contacts at client companies:** the people we know there (e.g. hiring managers), with role, email, phone and LinkedIn; each shows when we last spoke to them. "Forget" removes a contact's details; the company's activities stay, without the link.

## Why
Slice 4 ([plan](../../slice-4/PLAN.md)): mAIndscout is the source of truth, not an ATS accessory ([decision](../../decisions/2026-10-04-source-of-truth-and-imports.md)). A desk can only run here if it remembers every relationship and shows how fresh it is: the thing most ATSs lose.

## How
- An `activity` row per entry (kind call / email / meeting / message / note; direction out / in; summary; occurred_at; optional job and contact). Entries in the future are refused; anything can be removed (×) if logged by mistake.
- The timeline is a read model: activities, plus documents linked to the person, pair events (band and stage), answered Brief items, and jobs whose hiring company is this company. Newest first.
- Companies stay in the shared public tier; contacts, activities and tags belong to the desk (`org_id`).
- Erasure deletes a person's activities and tags; verify checks they're gone.

## Depends on
[persistence.md](persistence.md), [brief.md](brief.md), [companies.md](companies.md), [erasure.md](erasure.md).

## Used by
[cockpit.md](cockpit.md). Next in Slice 4: the full pipeline (submissions and client feedback join the timeline), freshness (stale people and companies from these dates), import.

## Contracts
- `POST /v1/candidates/{id}/activities`, `POST /v1/companies/{id}/activities` (`{kind, summary, direction?, occurred_at?, job_id?, contact_id?}`), `DELETE /v1/activities/{id}`.
- `POST /v1/candidates/{id}/tags {tag}`, `DELETE /v1/candidates/{id}/tags/{tag}`, `GET /v1/tags`, `GET /v1/candidates?tag=`.
- `POST /v1/companies/{id}/contacts`, `DELETE /v1/contacts/{id}`.
- `GET /v1/candidates/{id}` adds `relationship {last_contacted, last_verified, tags, timeline}`; `GET /v1/companies/{id}` adds `contacts`, `timeline`, `last_contacted`.

## Tests
`core/tests/test_relationship.py` (5):
- a logged call joins the timeline with the CV and band history, and sets last contacted (a note does not);
- bad entries are refused;
- tags are talent pools;
- contacts at a client and their calls;
- erasure removes activities and tags.

e2e: a logged call, last contacted, and a tag that becomes a talent pool.

## Known limits
- Emails are logged by hand until a mailbox is connected (Slice 4, drafts step).
- One person's tags are free text; there is no pool description or owner yet.
