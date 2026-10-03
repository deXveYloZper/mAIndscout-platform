# Coverage gate

**Status:** built (intelligence track, before I3)
**Code:** `core/maindscout/domain/geo.py` (countries, coverage, the rule; pure), `core/maindscout/api/coverage.py` (signals, archive, bring back, job countries), migration `0011`, cockpit job page ("Archived" and "Countries this job accepts"), person page ("Bring back"), People list tag

## What
After a CV is read, people who live or work outside every country the desk and their jobs accept are **archived**. No further paid intelligence is spent on them: no company research, and later no career profile or matching. Large consultancies and outsourcers get **light research** (kind and base only).

## Why
Owner's decision 2026-10-03 ([ADR](../../decisions/2026-10-03-coverage-gate.md)): the desk doesn't work those regions, the spend would be wasted, and such profiles' location claims are often unreliable.

## How
- **Coverage:** `geo.DEFAULT_COVERAGE` covers the EU, EEA, UK, Switzerland, US and Canada. `COVERAGE_COUNTRIES=DE,GB,...` overrides it.
- **A job accepts** the desk's coverage, plus the countries its ad names (the "live in or work from" requirement), plus `job.open_countries` set by a recruiter (`PUT /v1/jobs/{id}/countries`, codes or names).
- **A person is judged** against the desk's coverage plus every job they're on.
- **Signals**, all free and from facts we already have:
  - where the person lives now: `LocationClaim` of kind current, with its country code, or a country named in the place;
  - each current job (not side jobs): its country (`location_country`, which the CV read now returns, e.g. Bangalore → IN), or a country named in its place;
  - only if the job's place is unknown: the employer's `hq_country`, when research already found it.
- **The rule** (`geo.decide`): a person is outside when every stated home is outside, or every current job is outside. With no signals, they're never outside.
- **When it runs:**
  - after every CV read;
  - when someone is put on a job (upload, "put on job", desk sourcing);
  - when a recruiter changes a job's countries, or a job ad is re-read;
  - when a location or career fact is approved, rejected or corrected;
  - when research finds a company's base, which re-checks people whose current job there has no place of its own.
  - `python -m maindscout coverage-check` applies it to everyone on the desk, at no cost.
- **Archived:** `candidate.archived_at` plus `archived_reason` (the text, the basis lives / works / employer, and the country). Archived people:
  - show in a collapsed "Archived: outside coverage" section on the job, not in the bands;
  - ask nothing in the inbox;
  - are skipped by desk sourcing unless that job accepts their country.
- **Bring back** (`POST /v1/candidates/{id}/bring-back`) un-archives the person and sets `coverage_override`, after which the gate leaves them alone. Their company research is queued.
- **Light research:**
  - `research.LIGHT_RESEARCH` lists large consultancies and outsourcers (EPAM, TCS, Infosys, Wipro, Accenture, Capgemini, CGI and others).
  - A consultancy or outsourcer found by research to have at least 5,000 staff switches to `research_depth = basic`.
  - Basic research asks only for kind and head office, and refreshes after 365 days.
  - Research now also sets `company.hq_country`.

## Depends on
[process.md](process.md), [companies.md](companies.md), [company-research.md](company-research.md), [sourcing.md](sourcing.md), [review.md](review.md).

## Used by
Every later intelligence step (I3–I6) runs only for people in coverage.

## Contracts
- Migration `0011`: `candidate.archived_at`, `archived_reason`, `coverage_override`; `job.open_countries`; `company.research_depth`.
- `CareerStepClaim.location_country` (optional ISO code). CV prompt version `2026-10-03.1`.
- `GET /v1/jobs/{id}` returns `archived` and `coverage` (`desk`, `from_ad`, `opened`, `names`).
- `GET /v1/candidates/{id}` returns `archived` and `coverage_override`. `GET /v1/candidates` rows include `archived`.

## Tests
`core/tests/test_coverage.py` (14):
- country lookup (never guesses from a city);
- default coverage includes Switzerland and excludes Mexico;
- where someone lives and works decides, never where they're from;
- an Indian CV is archived, with no research for its employers, a section on the job, and nothing in the inbox;
- opening a job to India brings the person back and queues research;
- an ad naming Brazil accepts a Brazilian;
- a London job at Infosys stays in coverage;
- an unknown job place falls back to the employer's base once research finds it, using light research;
- bring back sticks;
- sourcing skips archived people unless the job accepts them;
- light research by list and by size;
- the CV read keeps each job's country.

e2e: opening a job to more countries, including an error for an unknown country.

## Known limits
- No retention period for archived CVs yet; the owner to decide.
- A city with no country ("Bengaluru") isn't recognised in CVs read before this change. The model fills in the country on new reads.
- One coverage setting for the whole platform until there's more than one desk.
