# The Brief

**Status:** built (Slice 3)
**Code:** `core/maindscout/domain/brief.py` (the compiler; pure), `core/maindscout/api/brief.py` (reconcile, answer, asked, dismiss), migration `0016` (`brief_item`), claim type `BriefAnswerClaim`, cockpit `app/jobs/[id]/people/[cid]/brief/`

## What
A checklist for the recruiter's call with a priority person on a job, compiled from what the system doesn't know or doesn't trust.

**About the person** (asked once, for every job they're on):
- the career profile's questions: gaps over 6 months, short stays, a company that shut down, missing dates;
- contacts the file may have garbled;
- where they live, if the CV doesn't say;
- notice period, salary expectations, and whether they're open to being put forward for other roles.

**For this job:**
- every requirement only a conversation can settle;
- must-haves and strong-plus items the CV doesn't show;
- where they may live and work, visas, relocation.

Must-haves come first.

**Why, in one line** (owner, 2026-10-04): every question that isn't self-explanatory says why it's asked, so a recruiter who has never seen the person can work through Briefs at speed:
- job questions say who wants it and how much ("Required by CATALYST (a must-have); the CV cannot confirm it", "The hiring manager asked for this (a strong plus)…");
- career questions say what's unusual ("A gap from Aug 2025 to Mar 2026: clients ask, so have the answer ready");
- salary, notice period, where they live, and openness to other roles carry no reason.

A two-line header says who the person is (the career profile's summary) and why they're on the call list, in plain words (e.g. "Strong match: every must-have met or only to ask; a strong industry match outweighs one level below").

**Answering:** you capture the answer on the item as confirmed, not met or a note. It becomes an approved fact with you as the source, and the person is re-matched at once. **Nothing is ever sent to anyone.**

## A Brief without a job (2026-10-06, the owner's request)
- Anyone on the desk can be briefed from their page or the People list ("Brief for a call"), for example someone in the pool who sent a CV.
- It asks the questions about the person only: career questions from their profile, contacts to confirm, where they live, notice, salary, openness to other roles, and what they are looking for next (kind of work, level, on site / hybrid / remote).
- The answers are person-wide, so they count for every job they are matched to, now or later. Nothing is sent.
- Both Briefs open with **how to reach them:** phone, email and LinkedIn from their files or typed by a person, each one click away (call, write, open). Unconfirmed values are marked "check".
- Contract: `GET /v1/candidates/{id}/brief` returns `{available, items, header, contacts}`; the job Brief now also returns `contacts`.

## Why
Blueprint Feature 9 and the Slice 3 plan: the Brief is the interface of a loop, not a report. The call is where the best evidence is born; capturing it inline makes every answer improve the profile, the match and, later, calibration (I7).

## How
- **A compiler, not an agent.** Each item comes from a fixed template and keys to the source that produced it (`std:notice`, `career:<hash>`, `contact:<claim>`, `req:<requirement>`). No model is involved.
- **Lifecycle:** open → asked → answered | dismissed | expired.
  - Rebuilding the Brief reconciles: new sources add open items, items whose reason has gone expire (e.g. a fact got approved), and **answered and dismissed items never come back**.
  - If an expired item's reason returns, it opens again.
- **Two scopes, inherited.** Person-scope items have no job and appear on every job's Brief. Answered on one job, they're answered on all of them; a person on three jobs is asked their notice period once.
- **Answers:**
  - Every answer is a `BriefAnswerClaim` (born approved, human assertion).
  - A confirmed or not-met answer to a requirement settles it in matching: met ("confirmed on the call: …") or a gap ("not met, said on the call").
  - A skill confirmed on the call is also written as an approved `SkillClaim`.
  - An answer to "where do they live" that names a country becomes an approved `LocationClaim`, so the coverage gate re-checks.
  - A contact is approved or rejected.
- **Default scope: priority people.** For anyone else the recruiter can still ask for one ("Make a Brief anyway"). Archived people get none.
- **Erasure** deletes a person's Brief items; verify checks they're gone.

## Depends on
[matching.md](matching.md) (requirement verdicts), [career-profiles.md](career-profiles.md) (call questions), [coverage-gate.md](coverage-gate.md), [review.md](review.md) (human assertions), [erasure.md](erasure.md).

## Used by
[cockpit.md](cockpit.md): "Brief for the call" on the person-on-job page, and "Brief" beside each priority person on a job.

## Contracts
- Table `brief_item` (0016): unique per person, scope and source.
- `BriefAnswerClaim` payload: `topic`, `question`, `outcome` (confirmed / not_met / noted), `answer`, `job_id`, `requirement_id`.
- `GET /v1/jobs/{id}/people/{cid}/brief[?force=true]` returns `{available, reason, items[]}`.
- `POST /v1/brief/{item}/answer {outcome, answer}`, `POST /v1/brief/{item}/asked`, `POST /v1/brief/{item}/dismiss`.

## Tests
`core/tests/test_brief.py` (11), including that every question that needs one says why in a line, and that the header says why the person is on the list:
- briefs are for priority people by default;
- person and job questions come from templates;
- an answer becomes an official fact and settles its requirement;
- person-wide answers are inherited by every job;
- regeneration never brings back answered or dismissed items;
- an item whose reason is gone expires;
- a location answer becomes where they live;
- erasure removes the Brief;
- must-haves come first.

The existing sourcing test confirms no send path exists. e2e: answers become official, aren't asked again, and nothing is sent.

## Known limits
- Questions are fixed templates; phrasing by a model (the blueprint allows it) isn't used.
- Uploading call notes as a document (the "rich path") isn't built; inline capture is.
- Mailing Brief questions and interview kits are out of scope (Slice 3 plan).
