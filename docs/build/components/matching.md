# Matching v2

**Status:** built (intelligence track I5)
**Code:** `core/maindscout/domain/matching.py` (verdicts and rules; pure), `core/maindscout/api/process.py` (`_match_now`, `retriage_pair`), migration `0015`, cockpit person-on-job page (match panel and verdicts) and job page (tier tag)

## What
Each person on a job is compared with the job's hiring profile, requirement by requirement, using their career profile and their facts. Every requirement gets a **verdict**:
- **Met**: the profile or the file shows it.
- **Partly**: a related kind of work, one level below, or some years in the industry.
- **Gap**: nothing shows it, or the facts speak against it.
- **Not wanted**: they meet something the hiring manager doesn't want.
- **Ask**: only the call can settle it.

A **match tier** (strong / possible / unlikely / unclear) then comes from visible rules, and every rule that fired is shown with its reason. The band follows the tier:
- strong → priority
- possible → review later
- unlikely → do not submit

**There is no number or percentage anywhere.**

## Why
Plan section 4.6 and phase I5: replace keyword triage with a comparison of what the career shows against what the job really asks for, with the desk's own rules written as data.

## How
- **Verdicts:**
  - Skills, years, education and languages come from the gap table.
  - A broad must-have skill not written on a CV ("project management skills") is a question, not a gap: absence from a CV isn't evidence. Distinctive must-haves still decide, as today.
  - Role: compares the kind of work (same, related or other), the title level, and years of related work.
  - Background: years at start-ups, scale-ups, consultancies and so on, from employer mix.
  - Industry: years from domain exposure.
  - Target companies: whether they worked there.
  - Employment: contract jobs read contractor patterns. A current contractor for a permanent job is a question.
  - Where someone lives and visas are always "Ask".
- **Rules, in order** (`matching.RULES`, each with its wording):
  1. **distinctive_must_missing**: a must-have that decides the band has no evidence → unlikely (today's InSAR rule, unchanged).
  2. **not_wanted**: they meet a "not wanted" requirement → unlikely.
  2b. **What they want** (from calls, 2026-10-06; [calls](calls.md)): each approved preference is a row of its own (`kind` "preference", strength `their_must` / `their_prefer`, never counted as the job's must-haves), checked against the hiring company's public facts (size, what kind of employer it is today, read like a career step starting today) and the job's own kind of work, employment and countries (`domain/preferences.py`). **wants_otherwise**: a must the job contradicts → unlikely, the detail quoting both sides ("Catalyst Geo has 11-50 people; they said "I won't go anywhere under 200 people again""). **prefers_otherwise**: a prefer the job contradicts → a note only. **fits_what_they_want**: the job fits. Unknown (no company size on file, on site / remote not recorded for jobs) → the row says "check it". Runs before too_little_known: wishes need no career profile.
  3. **too_little_known**: no usable career profile yet → unclear, and the coarse band stands (token triage as the fallback).
  4. **substitution**: an intake note such as "can substitute for start-up experience" on a met requirement counts that other requirement as met. The note must name it: its skill token, or at least half its meaningful words; one shared generic word ("role", "team") is not enough.
  5. **domain_over_seniority**: a strong industry match (must or strong plus) outweighs one level below the level asked for.
  6. **contractor_fit**: a contract job and a contractor with long engagements.
  7. **must_gaps**: two or more must-have gaps → unlikely; one → possible.
  8. **partial_must**: a must-have only partly met → possible.
  9. **strong_match**: every must-have fully met or only to ask, and at least half of the known strong-plus items met → strong. Otherwise possible.
- **When:** every re-banding computes the match: after a CV is read, a fact is approved or corrected, a career profile is built, or the hiring profile changes. The match is kept up to date even when a person set the band by hand, but a hand-set band is never changed. `python -m maindscout rematch` re-matches everyone at no cost.

## Depends on
[career-profiles.md](career-profiles.md), [hiring-profiles.md](hiring-profiles.md), [gap-table.md](gap-table.md), [process.md](process.md).

## Used by
[cockpit.md](cockpit.md). Next: sourcing v2 (I6) searches profiles and sends everyone found through the same matching.

## Contracts
- `candidate_job.match_tier` (checked: strong / possible / unlikely / unclear) and `candidate_job.match` (`tier`, `engine`, `rules[{id, text, detail}]`, `rows[{requirement_id, requirement, kind, strength, verdict, detail}]`), migration `0015`.
- Pair reasons `match:<tier>:<why>`. Today's `no_support_for_must_have:<token>` stays for rule 1.
- `GET /v1/jobs/{id}/people/{cid}/gaps` returns `match`; `GET /v1/jobs/{id}` returns `match_tier` per person.

## Tests
- `core/tests/test_matching.py` (10):
  - today's rule still decides;
  - one level below is possible, unless an industry match outweighs it;
  - not wanted;
  - substitution from the intake;
  - contractor fit;
  - where someone lives is never a reason for unlikely;
  - no profile, so the coarse band stands;
  - must-have gaps;
  - broad skills are questions;
  - target companies, and never a number.
- `core/tests/test_profiles.py`: a built profile matches the person to their jobs.

## Known limits
- Rules are written in code as an ordered list. Changing them is a reviewed code change; calibration from recruiter decisions comes in I7.
- Background and industry use what research and classification know; unknown is "Ask", never a gap.
- A hand-set band is never moved; the match beside it may disagree, and that's shown.
