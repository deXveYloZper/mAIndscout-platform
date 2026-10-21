# Company knowledge (identity keys and Exa profiles)

**Status:** built (next build, phase 1b, 2026-10-13); checked on real Exa company pages
**Slice / milestone:** next build, phase 1b ([plan](../../next/PLAN.md) section 4b, K1–K4)
**Code:**
- `core/maindscout/api/companies.py`: `domain_of`, `linkedin_of`, `by_key`, `learn_keys`, `resolve(..., keys=)`
- `core/maindscout/intelligence/company_profile.py`: reads an Exa company page with no model
- `core/maindscout/api/company_profiles.py`: profiles by Exa ID or by name
- `core/maindscout/api/research.py`: `write_facts`, `cross_check`, and the guard for an agreed acquisition
- migration `0028` (`company.domain`, `exa_id`, `linkedin`, `exa_profile`, `profiled_at`), flag `sources_disagree`

## What
Every company is one record, found by its keys before its name, and researched once.

Knowledge comes in three levels, used in this order:
1. **Known (free):** profiled in the last 6 months, or researched in depth.
2. **Profile (Exa):** about $0.001 by Exa company ID (up to 100 a call), or about $0.007 by name, accepted only when a key confirms it.
3. **Depth (Grok research, about $0.094):** for hiring companies, live targets, and employers of candidates about to be submitted.

## Why
The owner (2026-10-13): never research the same company twice, and choose the tool by price, value and accuracy. A candidate's fit depends on where they worked (domain, kind, size, stage), so people found by Exa need their employers known too.

The tests that decided it are in [plan section 4b](../../next/PLAN.md):
- Exa's search by company name found the right company 6–7 times out of 10;
- its company IDs match exactly between people's work histories and company pages;
- a profile fetched by ID costs a tenth of a cent.

## How
- **Keys:** the website domain (social and profile sites never count), the Exa company ID, and the LinkedIn company page.
  - `resolve` checks keys first. A new name with a known key becomes that company's alias.
  - Two companies with one name but different Exa IDs stay two records; the second is found by its key.
  - A key already held by another company is never moved. It raises one "Same company?" card (with why) when a desk and a person are known.
  - Grok research's website and an Exa profile's homepage, LinkedIn page and aliases all become keys.
- **The profile page.** Exa's company page has a fixed layout:
  - a first paragraph;
  - Company Details: industry, headquarters, founded, homepage, aliases, LinkedIn;
  - Financials: rounds;
  - Workforce: employees, by country, by department, talent sources;
  - Categories.

  `exa.clean` removes executives, emails, phones and reviews **before anything is kept** (recordings included). The tech stack is never read from a profile. Since 2026-10-17 a company's stack, tools and methods are read only from its own job adverts ([employer evidence](employer-evidence.md), [decision](../../decisions/2026-10-17-evidence-for-strong-matches.md)).
- **Domains are markets, read from the company's own words** (owner, 2026-10-13: "are they security, are they procurement"). Exa's industry ("Software Development") and its alphabetical category tags ("ai, automation, b2b…") are not domains. One small model call per 20 companies (`intelligence/company_domain.py`, about a tenth of a cent each) reads each description into 1–3 markets it serves and what it offers ("procurement automation platform"). Each comes with an exact quote, checked in code, and technology words are dropped. Without a model, the non-technology tags are shown and the reading is tried again later. Category-tag domain facts written earlier are set aside.
- **Facts:** founded, HQ, headcount, kind (from the industry, for example "IT Services and IT Consulting" is a consultancy), domains (as above) and funding rounds. Each is quoted from its own line through the same writer as Grok's research. Exa is a third-party estimate (web inference): consequential facts count as single-source.
- **Fields for the strategy** sit on `company.exa_profile`: where the team works, departments, talent sources, size band. They are fields, never the page.
- **Cross-check (K3).** A fact with observations from two sources (two hosts):
  - agreement removes `single_source_web`;
  - disagreement sets `sources_disagree`, and the company page shows both with their sources.

  Compared: founded year, HQ country, kind, status, funding amount (within 20%). A registry's incorporation date and Exa's founded year will often differ; that is meant to be seen.
- **"Agreed to be acquired" is not "acquired".** A status quote about an agreement, a pending deal or an expected close is stored as active, with the detail "agreed to be acquired, not completed".
- **People found by Exa (K4).** Each employer in their profile is registered under its keys before the profile is read, so the career step links to the exact company. After a run, employers of the people it added are profiled by ID in one call. Each added person's career reading is queued (classified with the model, about $0.003), with no paid university research.
- **CV people:** employers arrive as names. Keys and known aliases first, then Grok research as before. (An Exa search by name is accepted only with a confirming key, which a CV rarely gives.)
- **Costs:** profiles are sourcing spend (`sourcing_company_profile`), inside the role's and desk's sourcing budgets.

## Depends on
- [companies.md](companies.md)
- [company-research.md](company-research.md): the writer and the depth level
- [web-discovery.md](web-discovery.md): the Exa client
- [career-profiles.md](career-profiles.md)
- [tasks-and-costs.md](tasks-and-costs.md)

## Used by
- [sourcing-strategy.md](sourcing-strategy.md)
- [sourcing-engine.md](sourcing-engine.md)
- [matching.md](matching.md): via career readings
- [cockpit.md](cockpit.md): "Works at" facts on suggestions, and company facts on the market map

## Contracts
- `company.domain` (indexed), `company.exa_id` and `company.linkedin` (unique), `company.exa_profile` (JSON fields), `company.profiled_at`.
- Flag `sources_disagree` (company facts).
- Ledger purpose `sourcing_company_profile`.

## A CV's companies, and keys typed by a person (x-ray, 2026-10-14)
- **A company on a CV gets an Exa profile** (`by_name_and_place`, task `profile_company`, about a cent each, from the shared research budget). It is confirmed by one of:
  - a key (website, LinkedIn page, Exa id);
  - else the exact same name (or one of its names), with its head office or team in the country the CV gives for that job.

  Anything less is not taken: a similar name is not the same company.
- **Grok research** (about $0.09) is kept for hiring companies (from the ad, the intake notes or typed), companies named on a role, and "Research now". Before this, every company on every CV got it, and one re-check queued 88 at once against a $10 budget.
- **A person can type a company's website or LinkedIn page** on its company page (`PUT /v1/companies/{id}/keys`). A key another company already holds raises "Same company?" instead of moving.
- The company page shows the Exa profile, and what the last research attempt did (queued, or could not run because the shared budget is used up).

## Tests
`core/tests/test_phase1b.py` (also: a company's domain is its market, read with a quote and never a technology; without a model, the non-technology tags are shown):
- a company is found by its keys before its name;
- a profile is read without people and checked against research;
- an agreement to be acquired is not an acquisition;
- people found on the web get their employers profiled and a career reading.

`core/tests/test_recording.py` also covers recordings without the people parts.

- Where the team works is read with its thousands kept ("Italy: 2,701 (22%)" is one country, fixed 2026-10-18; the 36
  companies read before were read again).

## Known limits
- Exa's profiles are estimates. Small, regional or shut-down companies are often missing or confused, so a name match alone is never accepted.
- Employers without an Exa ID or LinkedIn link stay names until a CV or research identifies them.
- The cross-check compares the facts listed above; headcounts (dated) are not compared.
