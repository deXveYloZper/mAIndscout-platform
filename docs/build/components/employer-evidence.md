# Employer evidence (what a company uses, read from its adverts)

**Status:** built (2026-10-17); first real run the same day on Tacto, Mercanis and Bendi (1-1.5 cents each): Tacto's adverts gave 15 practices (React, TypeScript, Next.js, Python/FastAPI, Postgres…), and its 8 engineers whose profiles named no framework became possible matches
**Slice / milestone:** next build, after phase 1c ([decision](../../decisions/2026-10-17-evidence-for-strong-matches.md))
**Code:**
- `core/maindscout/intelligence/practices.py` (pure: which pages are the company's own, the reading)
- `core/maindscout/api/practices.py` (reading, storage, facts for the gap table)
- `domain/gaps.py` (`employer_support`, the `likely` status), `domain/profile.py` (`area_of_title`)
- `intelligence/triage.py` (`likely_from_employer`), `domain/matching.py` (likely is partly met)
- task `read_practices`; claim type `CompanyPracticeClaim`; column `company.practices_at` (migration `0030`)
- cockpit: "What it uses, from its job adverts" on a company page; "Likely (their employer)" in a person's gap table

## What
A company's own job adverts name its stack, its tools and its methods. The desk reads them once, and a person at that
company who never wrote a skill down is taken to **likely** use it, when they work in that area there.

## Why
The owner (2026-10-17): "if this company uses node.js for example but the person hasnt metioned it, it is reasonable to
think that they are working with that technology (or any other such key info … not just technologies, for example for
non tech roles)". In the first real review, 16 of 24 engineers found at the right companies were turned away only
because their public profiles never named a framework.

## How
- **When it is read:** after a sourcing run, for every target company it searched (`practices.queue`), in the
  background, once per 180 days. It is paid inside the role's sourcing budget (about 1-2 cents). Off with
  `PRACTICES_AUTO=false`.
- **Search:** one web search, "{company} {the role's title} job". It names a company and a kind of work, never a person.
- **Which pages count** (`own_page`): pages on the company's own website, or adverts for it (its name in the address
  and as a word in the text). An aggregator's other companies never lend it their stack. A person's profile never
  counts.
- **Reading:** one model call over at most three pages. It lists technologies, tools, methods and standards, each with
  its area of work (engineering, product and design, commercial, operations, or company-wide) and an exact quote.
  - Code keeps an item only if its quote is on its page and names it. Nice-to-haves are left out.
  - Benefits, degrees, spoken languages and anything about a person are never asked for.
- **Storage:** a `CompanyPracticeClaim` in the public tier, with the advert as evidence (its address and quote). The
  same practice seen again is another observation; the claim keeps the latest date it was seen.
- **Use** (`employer_facts`, then `gaps.employer_support`): each practice reaches the gap table once per career step
  at that company, with the step's title and dates. A skill requirement with nothing of the person's own becomes
  **likely** when all of these hold:
  - the practice names it (or one of its alternatives);
  - the step's title is in the practice's area (or the practice is company-wide);
  - the step is current, or ended no more than two years before the advert.
- **Weight in the rules:**
  - A distinctive must-have that is likely makes the quick check `review_later` (`likely_from_employer:<token>`) and
    matching "partly met", so the person is a possible match, never strong on its own.
  - A broad skill that is likely counts as "ask".
  - A likely row is never an approved fact for coverage. Matching's call questions ask about it.
- **Re-judged at once:** after a company is read, everyone on the desk with a career step there is matched again.

## Depends on
- [Company knowledge](company-knowledge.md): company identity by keys; merged companies share their practices.
- [Sourcing engine](sourcing-engine.md): queues the reading for the companies a run searched.
- [Tasks and costs](tasks-and-costs.md): the background task, the role's sourcing budget.

## Used by
- [Gap table](gap-table.md) and [matching](matching.md): the `likely` status and its weight.
- [Evidence checks](evidence-checks.md): a strong match's own public work is the next step after this one.

## Contracts
- `CompanyPracticeClaim` payload: `token`, `raw_label`, `kind` (technology, tool, method, standard) and `area`
  ([schema](../../../slice0/schemas/company_practice_claim.schema.json)).
- `GET /v1/companies/{id}` gains `practices` (each with its quote and advert) and `practices_at`.

## Tests
`core/tests/test_evidence.py`:
- only the company's own pages count;
- an advert makes a missing core skill likely, and the person is re-judged to possible, never strong;
- same area of work and recent time only;
- a likely broad skill is never counted against anyone;
- read once per 180 days, paid inside the role's budget.

## Known limits
- One search per company, so a company whose adverts are not on the web says nothing.
- The area of a job title is read from its words (`area_of_title`), not from a career profile.
- Practices are not yet shown to the owner for approval in bulk; they stay proposed, with their adverts.
