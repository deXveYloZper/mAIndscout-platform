# Gap table (a person against a job)

**Status:** built
**Slice / step:** Slice 1 / step 2
**Code:** `core/maindscout/domain/gaps.py` (pure), `api/queries.gap_page`, route `GET /v1/jobs/{job}/people/{person}/gaps`, cockpit `app/jobs/[id]/people/[cid]/page.tsx`

## What
Every requirement of a job set against one person's facts, row by row. Each row is **evidence**, **missing**, **conflict** or **ask**, with the reason in plain words, the snippets behind it, and whether those facts are approved or only proposed. It is the default view of a person on a job: names on the job page open it.

## Why
Slice 1: "On a job, each person has a gap table: every requirement → evidence / missing / conflict … the product refuses a composite number." A band says where someone sits; the gap table says why, and what to ask.

## How
- **Skills:** the same whole-word matching as triage, over skills and job titles. Alternatives written with a slash ("JavaScript/TypeScript") are met by either.
- **Experience:** years computed from career dates; overlapping jobs are merged so time is not counted twice; internships and side work are left out; a current job counts to today. Fewer years than asked is a **conflict**, with both numbers shown. No number in the ad: **ask**.
- **Education:** levels compared (doctorate > master > bachelor > diploma). Lower than asked is a **conflict**.
- **Languages:** looked for in skills; otherwise **missing, ask**.
- **Mobility:** residence, visa and relocation are separate rows and are never a conflict: living elsewhere, no sponsorship, or no relocation help are **ask** rows ("lives in Vienna; ask about working from Germany or United Kingdom"). Living in an allowed country is evidence for residence and "no move needed" for relocation; it never proves the right to work.
- **Vague requirements** (qualities, broad areas): **ask**.
- Process dates and plain work locations are job information, not rows.
- **No score:** the API returns rows and per-status counts; counts are never added up or weighted. The page says so.
- The "To ask on the call" list gathers every ask row (the seed of Slice 3's Brief).

## Depends on
[intelligence.md](intelligence.md) (triage matching, requirement shapes), [process.md](process.md) (the facts), [persistence.md](persistence.md).

## Used by
[http-api.md](http-api.md), [cockpit.md](cockpit.md) (job page counts per person; person-on-job page).

## Tests
`core/tests/test_gaps.py` (10: overlapping years, current job to today, skills, years conflict, education, mobility never a conflict, non-rows, official only when approved, counts never combined); `tests/test_api.py` (route, counts on the job page, 404 when not on the job); e2e "a person on a job opens as a gap table, with no overall score".

## Known limits
- Education compares level only, not field; the row says "check the field on the call".
- Languages are found only if the CV lists them as skills.
- Rows use proposed facts too; each row shows whether its facts are approved. The coverage floor (step 5) will decide when the table is too thin to show a band confidently.
