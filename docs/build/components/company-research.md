# Company research

**Status:** built (intelligence track I2)
**Code:** `core/maindscout/intelligence/research.py` (the search call and the mechanical checks, pure), `core/maindscout/api/research.py` (storing, freshness, budget), task `research_company` in `api/task_handlers.py`, migration `0010`, cockpit `app/companies/[id]/`

## What
For each company that matters to the desk, Grok looks up a fixed list of public facts and returns each one with the page it came from and a quote. Facts that pass the checks are stored once, in the shared public tier, and every desk sees them on the company page.

## Why
Matching and sourcing need to know what kind of company someone worked at (plan section 4.3): what it does, how old it is, how it is funded, how big it is. The owner decided (2026-10-03, [decisions](../../decisions/2026-10-03-intelligence-track.md)) that research must be **targeted, not open browsing**, and that company knowledge is a **shared public tier**.

## How
- **The fixed list:** website; domains (what it works in); kind (product, consultancy, outsourcing, agency, public sector, non-profit, other); founded; funding rounds (stage, date, amount, investors); headcount; status (active, acquired, merged, shut down, public); head office. Nothing else is asked for. **Never technologies or tech stack** (owner, 2026-10-03: only someone inside the company really knows it; stack comes from the job ad and CVs). The prompt forbids researching people, and only the company name and the location from the CV go into it, never a person's name or job title.
- **The call:** xAI Responses API with the `web_search` tool, a cap on tool calls, and a strict JSON schema for the answer. The provider reports the cost of each call (tokens and sources). Each company costs about $0.08–0.09.
- **Mechanical checks** (`check`), applied to every fact before anything is stored:
  - The source must be a page the model actually opened in this call. Any other source is dropped.
  - Numbers must appear in the quote: the founding year, headcount figures, and funding amounts. A funding year may come from the quote or from the article's address (`/2025/11/27/…`).
  - A status must be stated in its quote ("Company status Active", "Defunct", "acquired by…").
  - A company's kind can't be read from its legal form ("Privately Held", "Private limited Company"); the quote must say what it sells.
  - A funding round needs a date or an amount, since a running total ("has raised $85.5M") isn't a round. If the quote names a stage ("Seed Round"), the stored stage must match it.
  - Pages on company registers (e.g. Companies House) are marked as official records.
  - All typed checks live in one function, `fact_problem`. `python -m maindscout research-recheck` applies the current checks to stored facts at no cost and rejects proposed facts that now fail, with the reason. Approved facts are left alone.
  - If the model can't confirm it found this exact company (`identified: false`), nothing is stored.
- **Storing** (`apply`): each fact is a claim under the public-knowledge org (`PUBLIC_ORG_ID`) with status `proposed` and evidence (`research_result`, the URL and quote).
  - Authority comes from the source: register → official record; the company's own site or LinkedIn page → the company itself; any other site → a web page.
  - Funding and team size from a single independent web page get the `single_source_web` flag.
  - Seeing the same fact again adds an observation, not a new claim.
- **When:** after a CV is read, research is queued for companies in the last 10 years where the person stayed at least 6 months or is still there. The hiring company is queued after a job ad is read. Tasks are deduplicated per company.
  - Facts stay fresh for 180 days. A company that wasn't identified is retried after 30 days, and a failed run after 7.
  - "Research now" on the company page forces a run.
  - `RESEARCH_AUTO=false` turns automatic research off (the e2e run uses this).
  - `python -m maindscout research-backlog` queues research for people and jobs already on the desk.
- **Light research** for large consultancies and outsourcers (kind and head office only, yearly), and only for people in coverage ([coverage-gate.md](coverage-gate.md)).
- **Budget:** shared research has its own monthly budget, `RESEARCH_MONTHLY_BUDGET_USD` (default $10). Its cost is recorded without an org.

**Since phase 1b** ([company knowledge](company-knowledge.md)): Grok research is the depth level, for hiring companies, live targets and employers of candidates about to be submitted; Exa profiles ($0.001 by id) are the middle level. Both store facts through `write_facts`; `cross_check` clears `single_source_web` when two sources agree and flags `sources_disagree` when they do not. A status quote about an agreement or a pending deal is stored as active ("agreed to be acquired, not completed"). The research website becomes the company's domain key.

## Depends on
[companies.md](companies.md) (who the company is), [tasks-and-costs.md](tasks-and-costs.md) (queue, ledger, budget), [writer.md](writer.md) (guarded claim write; schemas and registry).

## Used by
[cockpit.md](cockpit.md) (company page). Next: career profiles (I3: employer type and stage for each stint) and matching (I5).

## Contracts
- Seven claim types for subject `company`, with schemas in `slice0/schemas/`: `CompanyDomainClaim`, `CompanyTypeClaim`, `CompanyFoundedClaim`, `FundingRoundClaim`, `TeamSizeClaim`, `CompanyStatusClaim`, `CompanyLocationClaim`.
- `company.research_status` (identified / not_identified / failed) and `researched_at`, both added in migration `0010`, which also creates the public-knowledge org.
- `GET /v1/companies/{id}` returns `research_status`, `researched_at` and `facts` (each with up to 3 sources).
- `POST /v1/companies/{id}/research` returns `202` with a task id.

## Tests
`core/tests/test_research.py` (25), using a fake search client that fails if a person's name or title reaches the prompt. They cover:
- the checks: status, kind and stage must be supported by their quotes; the prompt forbids people and technologies; recheck rejects stored facts that fail newer checks; an unopened page is dropped, a wrong amount is refused, a year in the address is accepted, a founding year missing from its quote is dropped, registers are recognised, an unidentified company stores nothing
- parsing of amounts and sizes
- storing: 7 public facts with the right authority, origin and flag, plus the cost row
- freshness and force; the research budget
- which stints queue research, and the off switch
- the company page facts and the research route

## Known limits
- **Nobody can approve public facts yet.** A desk can only approve its own claims, which is deliberate: one desk shouldn't certify shared knowledge for all. Who reviews the public tier (a platform operator, or agreement between desks) is an open question. Until then, facts show as "not yet checked by a person".
- We store the URL and the quote, not a snapshot of the page. If a page changes or disappears, the quote remains as the record.
- Amounts are converted to dollars only when written in dollars. Other currencies keep the raw text.
- Whether a domain is an industry or a technology isn't checked mechanically. The prompt forbids technologies, and the owner's spot-check catches any that slip through.
- Headcount comes from whatever page states it, usually LinkedIn's size band, and is dated. Sizes are read as written ("51-200", "over 8.8 thousand", "1.2k+", "10,000+"); before 2026-10-08 "8.8 thousand" was read as 8 people. `research-recheck` re-reads every stored size from its own words and corrects the numbers, **including on approved facts** (the words are unchanged; only the parsed min / max and the stored hash), a named exception to pinned approved views ([decision](../../decisions/2026-10-12-approved-size-reparse.md)).
