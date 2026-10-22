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
- **Merges are recorded:** who merged, from which desk, and when (`merged_by`, `merged_by_org`, `merged_at`), since companies are shared by every desk.
- **Linking:** reading a CV resolves each career step's company into `payload.company.company_id` (the payload only: an approved view is never rewritten; readers take the link from the payload); reading a job ad sets `job.hiring_company_id`. `python -m maindscout link-companies` links data read before this existed.
- **Erasure:** company records hold no personal data and stay; "Same company?" cards raised by an erased person's CV are deleted, and verify checks for them.

**Since phase 1b** ([company knowledge](company-knowledge.md)): a company is found by its keys (website domain, Exa company id, LinkedIn page) before its name. A new name with a known key becomes its alias; a key another company holds raises a "Same company?" card (with why), never a silent merge. Two companies with one name and different Exa ids stay two records.

## Depends on
[process.md](process.md), [review.md](review.md) (the card), [persistence.md](persistence.md).

## Used by
[http-api.md](http-api.md) (`/v1/companies`), [cockpit.md](cockpit.md), and next: company research (I2), career profiles (I3), sourcing by target company (I6).

## Tests
`core/tests/test_companies.py` (10): same company written differently; self-employment; similar names raise a card and merge only on "same"; "different" keeps them apart; desks are private; job links its hiring company; backfill; erasure removes cards; one row per person with all roles; name rules. e2e: companies from CVs, "who do we know there".

## Known limits
- No company facts yet (domain, stage, funding, size): phase I2.
- Different offices of one firm written with a city ("KPMG Moscow", "KPMG Toronto") stay separate companies unless a human merges them.
- 2026-10-06: a "Same company?" card can be handed to the person ("Not sure: ask them on the call"): it becomes a Brief question (kind `company`, kept until answered); a yes merges the companies, a no keeps them apart and is recorded on the card's resolution.

## The desk settles the easy questions itself (2026-10-22)
The owner: "we should questions that matter, easy and silly questions should be caught and settled and handled by the
desk". Of 48 questions waiting that day, 45 were settled by rule (`api/settle.py`), each sealed by "desk" with its
reason, so it stays on record:
- **Same stint, or two?** The same title at the same company, in periods that overlap or follow on within a month, is
  one job written twice (a profile splits one job at a renewal): joined over its whole span. A gap, or another title,
  is still asked. Joining by hand now also keeps the whole span (it used to keep the older step's dates only).
- **Same company?** Merged when the names are one name written differently (spaces, accents, legal form such as
  S.p.A., a country tag, a plural), or one is a part or a renamed form of the other (a department, lab, experiment,
  "verschmolzen mit"); the parent's name stands. Kept apart, not asked, when they only share a website (gov.uk
  carries every UK department, a university's site its labs, a group's its brands), when either is a club, society or
  studentship, or when the name is not like any of the company's names. The rest is asked (KPMG / KPMG Avocats).
- **Other names from a profile** are kept only when they start as the company's own name does: profiles also list
  places, nicknames and parent bodies ("toro", "virginia", "University of Oxford" for a college), and an alias decides
  where every later CV is filed. 1,378 such names were removed.

match-eval after settling: no moves on the three roles, the owner's labels 4/4.
