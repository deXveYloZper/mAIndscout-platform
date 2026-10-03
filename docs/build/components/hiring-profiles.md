# Hiring profiles

**Status:** built (intelligence track I4)
**Code:** `core/maindscout/intelligence/hiring.py` (reads an ad or intake notes, with checks; no database), `core/maindscout/api/hiring.py` (storing, intake, recruiter edits, hiring company, target companies), task `profile_job`, migration `0014` (`job_intake`), cockpit `components/HiringProfile.tsx`, `IntakeForm.tsx`, `AddRequirement.tsx`

## What
What a job really asks for, in one place on the job page, grouped by how much it matters: **must**, **strong plus**, **nice to have**, **not wanted**. It's built from three sources:
- **the ad**, read once more for what the first reading leaves out: the role (kind of work, level, years only when written), permanent or contract, and any background, industry or target companies it asks for;
- **intake notes**: the recruiter pastes what the hiring manager said, and requirements are read from them;
- **the recruiter**, who can add requirements and change how much any requirement matters.

Beside them: what public research says about the hiring company (kind, stage, size, founded, base, industries), and, for target companies, how many people on the desk have worked there.

## Why
Plan section 4.5 and phase I4: matching (I5) needs to know what the hiring manager wants, not only what the ad says. For example: start-up experience as a strong plus, procurement experience that can substitute for it, permanent not contract, no candidates from big consultancies.

## How
- **One model call per text** (about $0.003). The values come from the same fixed lists as career profiles (kinds of work, levels, industries; employer kinds start-up / scale-up / large / consultancy / agency / public sector / non-profit), so I5 compares like with like.
- **Checks, before anything is stored:**
  - every item must quote the text, and the quote must be found in it;
  - years only when the number is written;
  - "permanent or contract" only when the quote speaks about employment;
  - target companies only when named in the quote;
  - a background the model leaves empty is read from the quote's own words ("start-up", "consultancies");
  - from notes, a "role" with no level or years is a concrete ask (e.g. "0-to-1 product delivery"), never the job's role.
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
  - fields `role_family`, `level`, `employer_kinds`, `domains`, `companies[{name, company_id}]`, `employment`, `source`, `note`.
- Table `job_intake` (0014).
- `POST /v1/jobs/{id}/intake {text}`, `POST /v1/jobs/{id}/requirements`, `POST /v1/requirements/{claim_id}/strength`.
- `GET /v1/jobs/{id}` adds `hiring` (`company`, `intakes`, `targets`).

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

e2e: intake notes become a hiring profile with quotes, and "culture fit" is left out.

## Known limits
- Where someone must live, and visas, stay with the ad's mobility facts and are asked on the call. Intake items about them are left out.
- The same industry can appear twice, from the ad and from the intake, when their lists differ. Both are shown with their source.
- Approving a public company fact is still open (see company research).
