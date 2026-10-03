# Career profiles

**Status:** built (intelligence track I3)
**Code:**
- `core/maindscout/domain/profile.py`: the rule set (rubric). Pure code: no database, no model.
- `core/maindscout/intelligence/classify.py`: reads each career step, one model call per CV.
- `core/maindscout/intelligence/institutions.py` and `api/institutions.py`: university rank (QS).
- `core/maindscout/api/profiles.py`: gathers the facts, stores snapshots, runs the task.
- Migrations `0012` and `0013`.
- Cockpit: `components/CareerProfile.tsx` and `components/StepFix.tsx`.

## What
For each person in coverage, a profile of what their career shows, dimension by dimension, each with the reason in words and the facts it rests on:
- relevant experience (the kind of work done now, and related work counted together)
- seniority (from titles, with years beside them)
- progression
- stability (contractor-aware)
- employer mix (start-up, scale-up, large company or consultancy, at the time they joined)
- early joiner
- domains (industries)
- contracting
- education (with QS university rank)

It also lists notable items (founder, first hire, led a team, managed people, promotions) and questions for the call. An overall reading (strong / solid / developing / unclear) is composed from the dimensions by visible rules. **There is no number anywhere.** It never looks at personality, culture or "fit".

## Why
Plan section 4.3 and the owner's brief (2026-10-03): understand a candidate's career strength before matching. Relevant years per kind of work, seniority, progression, stability without penalising contractors, the kind of employer and its stage, early joining, domain exposure, and university rank as merit evidence.

## How
1. **Classify** (the paid step, about $0.003 per CV, once): the model reads the CV text and the numbered list of extracted steps. For each step it gives the kind of work (24 fixed families), 1–3 industries (36 fixed domains, never technologies), and signals only when quoted from the CV. The prompt includes what public research says about each employer, so industries are anchored.
   - Checks: only the step ids we sent; domains from the list; a signal's quote must be written in the CV.
   - Stored as `StepClassificationClaim`s: class `inferred`, status `proposed`, with evidence pointing to the CV.
2. **Level by code**: read from the title words (Junior → junior, no level word → mid, Senior → senior, Lead / Staff → lead, Head of → head, …), computed when the profile is built.
   - Leading a team without the title is a notable item, never a higher level.
   - A recruiter's correction (approved) wins.
3. **University rank**: one web search per institution (shared, refreshed yearly) for its place in the QS World University Rankings. It's kept only if the page was opened by the search and the quote contains the rank. Stored as bands: top 50 / 51–100 / 101–200 / 201–500 / 501+ / not ranked.
4. **Build** (free): `domain/profile.build` turns the stints, company facts and education into the dimensions. Key rules:
   - **Relevant years:** related kinds of work count together (technical work; product and design; commercial work; operations). A restaurant job never counts towards software.
   - **Stability:** one tenure per employer, so a promotion isn't a move. Jobs before the career started, in another kind of work, don't count. Year-only dates ("2017 – 2018") never make a stay "short". A short stay at a company that shut down or was sold isn't counted, and becomes a question instead.
   - **Contractors** are read against contractor norms: long or short engagements.
   - **Employer kind** comes from the funding stage when they joined. A round more than 8 years earlier doesn't count; then company size decides.
   - **Reading:**
     - unclear when too little is known;
     - developing when relevant work is under 2 years;
     - strong when there are 5+ years, a rising progression and long tenures (or long engagements);
     - otherwise solid, with the reasons.
   - **Questions** come from facts only: short stays, a company that shut down, short contracts, consultancy-heavy careers, unclear progression, gaps over 6 months, missing dates.
5. **Snapshots**: `career_profile` rows are append-only, one per change of inputs (`inputs_hash`), timestamped in code.
6. **When:**
   - a `profile_candidate` task is queued when the coverage gate keeps a person;
   - again when research adds facts about any of their companies;
   - the profile is rebuilt at once (code only) when a person approves, rejects or corrects a career step, education or classification.
   - `python -m maindscout profiles-rebuild [--reclassify]` rebuilds everything; `--reclassify` reads the machine's labels again with the current prompt and keeps people's corrections.
   - `PROFILE_AUTO=false` turns the task off.
7. **Erasure** deletes the person's profiles; verify checks they're gone.

## Depends on
[process.md](process.md) (career and education facts), [company-research.md](company-research.md) (employer kind, stage, founding date), [coverage-gate.md](coverage-gate.md) (only people in coverage), [tasks-and-costs.md](tasks-and-costs.md), [review.md](review.md).

## Used by
[cockpit.md](cockpit.md) (person page). Next: matching v2 (I5) compares profiles with hiring profiles (I4).

## Contracts
- `StepClassificationClaim` (schema `slice0/schemas/step_classification_claim.schema.json`, registry `class: inferred`).
- Tables `career_profile` (0012) and `institution` (0013, shared public tier).
- `GET /v1/candidates/{id}` returns `profile` (dimensions, notable, reading, questions, summary, rubric version) and `classifications` (each step as read, with the level the profile uses).
- Corrections: `POST /v1/claims` with a `StepClassificationClaim` and `replaces`.

## Tests
- `core/tests/test_profile_rubric.py` (16), synthetic careers:
  - restaurant then software;
  - the three engineers from the plan;
  - contractors with long and short engagements;
  - an early joiner;
  - a company that shut down;
  - too little known is unclear, with no number;
  - education rank;
  - employer kind by stage at joining;
  - gaps;
  - related work counts together;
  - a promotion isn't a move;
  - year-only dates;
  - an old funding round;
  - undated jobs;
  - levels from titles;
  - progression ends at the highest role held today.
- `core/tests/test_profiles.py` (15):
  - classification checks;
  - snapshots;
  - corrections win;
  - archived people get nothing;
  - queueing, and the off switch;
  - erasure;
  - QS rank checks and the research flow.
- e2e: the person page shows the profile built by real workers, and the correction controls.

## Known limits
- Kind of work and industries are a model's reading of the CV; recruiters correct them on the person page. The owner's hand-check of the test CVs is the gate.
- Headcount is current, not at the time someone joined; the funding stage at joining is used first.
- Domains count each job's main industry only.
- No written summary by a model: the one-line summary is assembled by code, so nothing is invented.
