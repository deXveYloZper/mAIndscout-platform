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
  - **Likely from their employer** ([employer evidence](employer-evidence.md), 2026-10-17): a distinctive must-have that is only likely is "partly met" (so at most possible, never strong on its own); a broad skill that is likely is "Ask". The token triage that rule 1 reads says `likely_from_employer` instead of `no_support_for_must_have`, so rule 1 does not fire for it.
  - Role: compares the kind of work (same, related or other), the title level, and years of related work.
  - Years asked for ("7 or more years of marketing experience") are compared with their years in that kind of work
    when there is a career profile, not their whole career: under three quarters of the years is a gap, from three
    quarters partly met (2026-10-18).
  - Background: years at start-ups, scale-ups, consultancies and so on; a year is enough (2026-10-18). What is wanted
    counts only years in the role's kind of work and the work that builds on it (2026-10-19: six months as a baker in
    a 4-person bakery is not small-brand experience for a marketing role). What is not wanted counts every job.
  - Company size in people (2026-10-19, `min_staff` / `max_staff`, e.g. "a small or mid-size brand, up to 500
    people"): years at employers of that size, in the role's kind of work, with the companies named.
    - Agencies, consultancies, public bodies and non-profits count only when the requirement names them.
    - Unknown sizes make it a question.
    - Bands: 1–50, 51–250, 251–500, 501–5,000, 5,000+ (`profile.SIZE_BANDS`).
  - Industry in the companies' own words (2026-10-19): a requirement with `company_words` ("leather goods", "bags")
    counts years at employers whose own profile says it; a year is enough; unknown employers make it a question.
  - Industry: years from domain exposure; a year is enough (2026-10-18, it was two). For a luxury role, years in an
    industry other than luxury itself (hotels, travel…) count only at luxury companies.
  - Target companies: whether they worked there.
  - "Not from" a company (2026-10-19): against when they work there now or left less than 6 months ago
    (`recent_months` on the requirement). An earlier leaver is fine, with the date they left.
  - A limit on seniority (role, strength anti) and "not from" companies of a size (employer, anti, with a staff
    count) are read since 2026-10-19 but rate nobody yet. Step C defines them, after match-eval.
  - Employment: contract jobs read contractor patterns. A current contractor for a permanent job is a question.
  - Where someone lives and visas are always "Ask".
  - A language the profile or CV does not list is "Ask", never a gap (2026-10-18: many profiles list no languages).
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
- **A strong web find gets a deeper look** ([evidence checks](evidence-checks.md), 2026-10-17): when a re-banding leaves someone found by a web people search in priority, an evidence check is queued (once per 90 days).
- **When:** every re-banding computes the match: after a CV is read, a fact is approved or corrected, a career profile is built, or the hiring profile changes. The match is kept up to date even when a person set the band by hand, but a hand-set band is never changed. `python -m maindscout rematch` re-matches everyone at no cost.

## Depends on
[career-profiles.md](career-profiles.md), [hiring-profiles.md](hiring-profiles.md), [gap-table.md](gap-table.md), [process.md](process.md).

## Used by
[cockpit.md](cockpit.md). Next: sourcing v2 (I6) searches profiles and sends everyone found through the same matching.

## Contracts
- `candidate_job.match_tier` (checked: strong / possible / unlikely / unclear) and `candidate_job.match` (`tier`, `engine`, `rules[{id, text, detail}]`, `rows[{requirement_id, requirement, kind, strength, verdict, detail}]`), migration `0015`.
- Pair reasons `match:<tier>:<why>`. Today's `no_support_for_must_have:<token>` stays for rule 1.
- `GET /v1/jobs/{id}/people/{cid}/gaps` returns `match`; `GET /v1/jobs/{id}` returns `match_tier` per person.

## Step C: is the move realistic? (2026-10-21, `match-2026-10-21.3`)
The owner: "1st its not a competitor, 2. its not similar company compare to 12k people and 62 people, its a
standard recruiter logic." A match that is strong on paper becomes possible, a reach, with its reason on the card:
- **Too big a move** (`too_big_a_move`): their current employer is 20 or more times the client's size (Prada Group,
  12,203 people, for a 62-person brand), unless the role is a step up for them or they spent a year or more in the
  last 3 years at a company up to 5 times the client's size, in the role's kind of work. A ratio, not size bands:
  1,027 to 93 (Viridien to Catalyst, a normal move for InSAR people) is 11x, 12,203 to 62 is 197x.
- **Above the role** (`above_the_role`): two or more levels above the role's level (its role requirement, else the
  role brief), at the role's own seniority limit ("not too senior: lead and above" now rates), or above it with a
  global or regional scope.
- **A specialist for an all-round role** (`specialist`): the role asks for an all-round person ("360", "broad
  marketing experience") and their title is a narrow kind of marketing work (CRM and clienteling, media, social
  media, merchandising, events, PR…), unless the role's must-haves or strong pluses ask for that work. A list of
  everything an all-round marketer touches (a nice-to-have, the brief's scope) does not ask for it.

The client's side (`process.client_context`): its size (a counted headcount first), the role's level, whether it
asks for an all-round person, and the words of its must-haves and strong pluses. match-eval: the marketing role from
28 strong to 5 (the 23 moved: 21 Prada Group people, two specialists), the owner's four labels from 0 to 4 right;
InSAR's two leads at the ad's own seniority limit; Procure AI unchanged.

## Nobody is strong before their career reading (2026-10-21, `match-2026-10-21.2`)
The owner: "People can't be considered strong before their career reading is done, obviously, this is a real bug!"
Someone with no career profile yet was Priority on the first, coarse reading (their skills against the must-haves);
web finds counted as strong and stopped a search at its target before anyone was read. Now a coarse Priority waits
in Review later ("being read") until the reading arrives; a coarse Review later or Do not submit stands. The card
says "Being read". Tests that judge a person after an upload use the `careers_read_at_once` fixture, which does the
background reading at once with a stand-in reader.

## Another field altogether (2026-10-21, `match-2026-10-21.1`)
A CFO, an HR manager, two operations directors and a store manager were "possible" for a marketing manager role
on one missing must-have. When the role's kind of work is a must and the person works in an unrelated field ("works
in finance, not marketing"), the rule `wrong_field` makes them unlikely. A related field (sales for marketing) stays
partial, and a field read as "other" (unknown) never counts. match-eval: those 5 moved, nothing else on any role.

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

## A specialist role (2026-10-22, `match-2026-10-22.2`)
- A person whose recent title says the role's specialist work (CRM, Salesforce, clienteling) works in its field,
  whatever family their career was filed under (a CRM manager read as marketing, a Salesforce administrator as IT).
- A must-have that decides the band (Salesforce) and is not on the public profile of someone found on the web, whose
  title says the specialist work, is "possible: to confirm on the call", not ruled out: a profile seldom lists every
  tool. With a CV on file, a missing must-have still decides.
match-eval: Ferrari's CRM role from 3 strong and 51 possible to 5 strong and 153 possible (104 CRM managers, CRM
specialists and clienteling leads at Prada, Miu Miu, Church's and others had been ruled out on "Salesforce" alone);
no moves on the three other roles; the owner's labels 4/4.

## Years for the role's level, and the side of the company (2026-10-23, `match-2026-10-23.1`)
- **Years** (owner: "everyone above 6 years is senior ... mid level with 2-5 is fine, 6 years if it is excellent match,
  mid level with 7 years of experience is a no"): full years since their first real job; for a mid role 2-5 fit, 6 is
  strong only with an otherwise excellent match, 7 or more is unlikely. A junior role: 0-2 (3 if excellent). Senior roles
  and above have no ceiling here.
- **The side** (owner: "people from IT has really nothing to do for this role"): a specialist title (CRM, Salesforce)
  counts as the role's field only on its side of the company (business: sales, marketing, client service, retail,
  hospitality); a Salesforce administrator in IT for a business-side CRM role is related, never strong.
- **A tool missing from a public profile** of someone whose title says the work is now a question for the call, and the
  rest of the match decides (it had capped them at possible): the owner's recruiter found the client's interviewee by
  her title ("CRM operations specialist" at Brunello Cucinelli) and asked for the CV.
match-eval on Ferrari: strong 9 to 12 (7 of the 9 out as too senior or IT side; in: CRM and clienteling specialists at
Prada, Valentino, Max Mara, Brunello Cucinelli, 3-5 years), possible 210 to 19 (181 too senior), the owner's two labels
0/2 to 2/2 (Arianna Orsini strong, Alessandro Pregno possible); the three other roles unchanged, Bonaventura's labels 4/4.

## The years band never sits below the ad (2026-10-26)
A role's years band is its level's (a mid role's 2-5), but never below what the ad asks: an ad asking at least 5 years
for a mid role gets 5-7, not a window of one year. match-eval: no moves on the four roles, labels 4/4 and 2/2.
