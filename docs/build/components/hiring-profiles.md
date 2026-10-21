# Hiring profiles

**Status:** built (intelligence track I4)
**Code:** `core/maindscout/intelligence/hiring.py` (reads an ad or intake notes, with checks; no database), `core/maindscout/api/hiring.py` (storing, intake, recruiter edits, hiring company, target companies), task `profile_job`, migration `0014` (`job_intake`), cockpit `components/HiringProfile.tsx`, `IntakeForm.tsx`, `AddRequirement.tsx`

## What
What a job really asks for, in one place on the job page. Each requirement says how much it matters (**must**, **strong plus**, **nice to have**, **not wanted**), and since step E (2026-10-20) the page shows them in three groups: what the desk searches and rates by, what is for the call, and context. It's built from three sources:
- **the ad**, read once more for what the first reading leaves out: the role (kind of work, level, years only when written), permanent or contract, and any background, industry or target companies it asks for;
- **intake notes**: the recruiter pastes what the hiring manager said, and requirements are read from them;
- **the recruiter**, who can add requirements and change how much any requirement matters.

Beside them: what public research says about the hiring company (kind, stage, size, founded, base, industries), and, for target companies, how many people on the desk have worked there.

## Why
Plan section 4.5 and phase I4: matching (I5) needs to know what the hiring manager wants, not only what the ad says. For example: start-up experience as a strong plus, procurement experience that can substitute for it, permanent not contract, no candidates from big consultancies.

## How
- **The ad reader's requirements, for every kind of role** (2026-10-18, [decision](../../decisions/2026-10-18-every-kind-of-role.md)):
  a skill written as a short name gets it as its skill word ("influencer marketing", "CRM", not only technologies);
  "several of / any of the following" is one requirement met by any item; "strongly preferred" is a strong plus;
  personality ("calm, decisive") is dropped. Skills typed here get their name as their word too.
- **One model call per text** (about $0.003). The values come from the same fixed lists as career profiles (kinds of work, levels, industries; employer kinds start-up / scale-up / large / consultancy / agency / public sector / non-profit), so I5 compares like with like.
- **Checks, before anything is stored:**
  - every item must quote the text, and the quote must be found in it;
  - years only when the number is written;
  - "permanent or contract" only when the quote speaks about employment;
  - target companies only when named in the quote;
  - a background the model leaves empty is read from the quote's own words ("start-up", "consultancies");
  - from notes, a "role" with no level or years is a concrete ask (e.g. "0-to-1 product delivery"), never the job's role.
- **Sizes, level limits, and no ask dropped** (2026-10-19, `HIRING_PROMPT_VERSION` 2026-10-19.1). The owner's
  Bonaventura notes had lost three asks: "not too senior like global and regional", "not from big brands" and "ideally
  from small up to 200 people". Now:
  - an employer item may give a size in people (`min_staff`, `max_staff`), in the desk's words: small up to 50,
    mid-size up to 250, big over 500;
  - a limit on seniority is a role item with strength anti and the first level that is too senior. It is its own
    requirement (key `role|anti`), takes the job's own kind of work, and is shown as "head and above";
  - an ask that fits no list is kept as kind other, for the conversation, never dropped;
  - an "other" ask already on the role under another kind is not added twice;
  - a leading article no longer makes a second requirement ("the salary…" and "salary…").
  - `reread_intakes` reads a role's notes again with today's reader. The marketing role's notes were read again the
    same day; Procure AI's were not (nothing was missing).
- **Three groups** ([role brief](role-brief.md), `domain/groups.py`): what the desk searches and rates by, what is for
  the conversation (asked on the call, nothing to confirm), and context. The job page API gives each requirement's
  group.
- **On the page** (step E, owner 2026-10-20: "too much information… why do we need to confirm a sentence that we
  cannot actually use in sourcing?"). Before, every requirement had a strength menu, Save, a source link, and Approve
  and Reject when unconfirmed: about 79 controls on the marketing role. Now, under the role brief and its questions:
  - **What we search and rate by:** one line each, with its strength, its source ("the ad", "your notes", "typed")
    and "new" when the desk read it. "Where people must live" is the first line; its "change" opens the role's
    countries, the one place they are kept. A must-have with no evidence that puts people in Do not submit says
    "decides the band".
  - **Confirm all:** the lines the desk read, approved together (`hiring.confirm`, `POST /v1/jobs/{id}/requirements/confirm`
    with their ids). Everyone on the role is re-matched once at the end (`review.job_batched`), not once per line. A
    line someone already decided is left as it is.
  - **change**, on any line (a small box that closes with Escape, a click outside it or its ✕, without doing
    anything): the line **in your own words** and how much it matters (Save), Remove, and the quote it came from.
    Changed words are read again (`hiring.edit_requirement`, `POST /v1/requirements/{id}/edit {text, strength}`):
    years by code ("5 or more years" makes it 5), the rest by the notes reader (a size, a kind of work; about a third
    of a cent) for the kinds it knows. The new line is yours (typed, approved); the old one is kept as superseded
    (owner, 2026-10-20: "the ad says 7 years, but if i want 5 i have no option").
  - **For the call, nothing to confirm:** what no profile shows (judgment, how they lead, pay, visa and relocation).
    Each becomes a question on the call brief. An ask already listed to search by (the ad's long sentence and the
    strong plus that says the same) is shown once.
  - **Tell the desk** (beside the brief's questions): anything about the role in plain words, a new must-have, a
    correction, what the hiring manager said. It is kept with the notes and read like them (each requirement with its
    quote, waiting for Confirm all), then the brief is read again (`role_brief.tell`, `POST /v1/jobs/{id}/tell`). It
    replaced the field-by-field "Add a requirement" form and the separate notes box (owner, 2026-10-20: "why we cant
    just write and our desk understand it?"); `POST /v1/jobs/{id}/requirements` stays in the API.
  - **Context:** where the job is, the posting's dates, then your notes and what you told the desk, folded.
- **Never personality, culture or "fit":** such items are dropped whatever the model says (owner's rule, 2026-10-03).
- **One requirement per subject.** A job has one role and one employment requirement. If the intake states a different value or strength than the ad, the intake's reading replaces the ad's (the ad's is kept as superseded). What a person approved is never replaced by a machine reading.
- **Stored as `JobRequirementClaim`s.**
  - Read by the model: proposed. Evidence is the ad's text span (origin employer) or the intake note's span (origin relayed, `locator.intake_id` with character offsets).
  - Typed by the recruiter: approved, source "recruiter".
- **Bands are recomputed** after every change. For example, the hiring manager downgrading InSAR from must to nice takes it out of "decides the band".
- **When:** the `profile_job` task is queued after an ad is read, once per ad (`PROFILE_AUTO=false` turns it off). Intake notes are read straight away when pasted.

## Depends on
[process.md](process.md) (the ad's first reading), [company-research.md](company-research.md) (the hiring company), [companies.md](companies.md) (target companies and who we know there), [career-profiles.md](career-profiles.md) (the shared lists), [review.md](review.md).

## Used by
[cockpit.md](cockpit.md) (job page). Next: matching v2 (I5) compares each hiring profile with career profiles, dimension by dimension.

## Contracts
- `JobRequirementClaim`, optional additions only:
  - categories `role`, `employer`, `domain`, `target_company`, `employment`;
  - strengths `strong_plus`, `anti`;
  - fields `role_family`, `level`, `employer_kinds`, `domains`, `companies[{name, company_id}]`, `employment`, `source`, `note`;
  - `company_words` (an industry as companies describe themselves, 2026-10-19);
  - `min_staff` / `max_staff`: a company size in people, typed as "Company size" on Add a requirement (2026-10-19);
  - `recent_months`: on a "not from" company, how recently a leaver still counts as from it; the default is 6
    (2026-10-19).
- Table `job_intake` (0014).
- `POST /v1/jobs/{id}/intake {text}`, `POST /v1/jobs/{id}/requirements`, `POST /v1/requirements/{claim_id}/strength`,
  `POST /v1/jobs/{id}/requirements/confirm {ids}` (step E).
- `GET /v1/jobs/{id}` adds `hiring` (`company`, `intakes`, `targets`).

## From the owner's 0-to-1 test (2026-10-21)
- **The ad's place can be wrong** (InSAR: "Markham or Gatineau", really the UK): place lines have "change"; a
  changed place stays a place (where people must live is set on its own line).
- **Dates told to the desk** ("the next hackathon is on 21 November in London and 22 November in Germany") replace
  the passed edition of the same event (`role_brief.dates`, `intelligence/dates.py`: one small model call, only when
  the words hold a date, each date quoted from them). Date lines can be removed.
- **Nothing told is dropped:** "the candidates should come from a competitor" (a company ask naming none) and pay
  ("the role pays €50k", which the model had left out) are kept for the call.

## Tests
`core/tests/test_hiring.py` (11):
- the ad adds role and employment, and every item is checked;
- intake requirements come with their quotes, the hiring manager beats the ad, the job is re-banded, and target companies show who we know there;
- the recruiter adds and reweighs requirements;
- the job page shows the hiring company;
- the task is queued after an ad is read;
- short notes are refused;
- personality is never a criterion;
- employment needs a quote about employment, and the intake corrects its value;
- employment words are recognised;
- an intake "role" without level or years isn't the role;
- a background left empty is read from the quote.

`core/tests/test_cards.py`: Confirm all approves what the desk read, re-matches the role once, leaves a decided line
alone, and refuses another role's claims.

e2e: intake notes become a hiring profile with quotes, and "culture fit" is left out; what the desk read is confirmed
together, and any line can be changed on its own; every control on the hiring profile has a name, and it fits a phone.

## Known limits
- Where someone must live, and visas, stay with the ad's mobility facts and are asked on the call. Intake items about them are left out.
- The same industry can appear twice, from the ad and from the intake, when their lists differ. Both are shown with their source.
- Approving a public company fact is still open (see company research).
