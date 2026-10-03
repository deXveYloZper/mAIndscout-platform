# Companies (shared records) and "who do we know there"

**Status:** built (intelligence track I1, part 1)
**Code:** `core/maindscout/domain/companies.py` (names, pure), `core/maindscout/api/companies.py`, tables `company` and `company_alias` (migration `0008`), cockpit `app/companies/`

## What
Every company named in a CV or a job ad becomes one shared company record. Career steps and jobs link to it. Each company page shows the people this desk knows who worked there, with their roles and periods, and the desk's jobs from that company.

## Why
The intelligence track ([plan](../../intelligence/PLAN.md)) needs companies as things, not strings: company research (I2), employer type and stage in career profiles (I3), target-company sourcing ("we know 15 people at Company A"). The blueprint calls for canonical companies with career steps re-keyed after resolution.

## How
- **Shared public tier:** `company` and `company_alias` have no org id (owner's decision, [record](../../decisions/2026-10-03-intelligence-track.md)). Who worked there is read from each desk's own career claims, so one desk never sees another desk's people.
- **Names:** legal suffixes (GmbH, Ltd, d.o.o., Sp. z o.o., …) and punctuation are dropped; a trailing parenthetical ("Bwin.Party (Entain)") is a note, never an alias (it may be a parent company). "Self employed", "Freelance" are not companies and turn the stint into contract work; "Stealth", "Confidential" are not companies.
- **Matching is exact** on the normalised name. Anything else creates a new company: a false split is a nuisance, a false merge poisons every alumnus. A new name that looks like an existing one ("Bitpanda" / "Bitpanda Technology Solutions", or a one-letter difference in a long name) raises a **"Same company?"** card; "Same company" merges by redirect (nothing about any person is rewritten), "Different companies" keeps them apart.
- **Linking:** reading a CV resolves each career step's company into `payload.company.company_id`; reading a job ad sets `job.hiring_company_id`. `python -m maindscout link-companies` links data read before this existed.
- **Erasure:** company records hold no personal data and stay; "Same company?" cards raised by an erased person's CV are deleted, and verify checks for them.

## Depends on
[process.md](process.md), [review.md](review.md) (the card), [persistence.md](persistence.md).

## Used by
[http-api.md](http-api.md) (`/v1/companies`), [cockpit.md](cockpit.md), and next: company research (I2), career profiles (I3), sourcing by target company (I6).

## Tests
`core/tests/test_companies.py` (10): same company written differently; self-employment; similar names raise a card and merge only on "same"; "different" keeps them apart; desks are private; job links its hiring company; backfill; erasure removes cards; one row per person with all roles; name rules. e2e: companies from CVs, "who do we know there".

## Known limits
- No company facts yet (domain, stage, funding, size): phase I2.
- Different offices of one firm written with a city ("KPMG Moscow", "KPMG Toronto") stay separate companies unless a human merges them.
