# Talent-release radar

**Status:** built; tuned on one real Exa news search (2026-10-12); not yet run on a real role
**Slice / milestone:** next build, phase 1 ([plan](../../next/PLAN.md) S1, S3)
**Code:**
- `core/maindscout/intelligence/release.py`: the reader; pure, no database
- `core/maindscout/api/radar.py`: the run step, signals, and new targets
- table `company_signal` (migration `0027`)
- cockpit: the market map's "releasing talent" tag, and the run report on the role's Sourcing tab

## What
Watches recent news for companies **releasing talent**:
- layoffs;
- insolvency;
- shutting down;
- a site closing;
- being acquired;
- restructuring;
- a hiring freeze;
- funding trouble.

A company on a role's market map that is releasing talent is searched **first** on the role's next run. A company found by news across the role's market joins the plan as **"releasing talent"**.

## Why
The plan's market map lists "companies releasing talent (layoffs, acquisitions, shutdowns, office closures, funding trouble in recent months)". A run's last step is "the talent-release radar (news about target companies)" ([plan](../../next/PLAN.md) S1, S3). People at such a company are the likeliest to move.

## How
- **Two kinds of news search** (Exa `news`, published in the last 120 days, 5 articles each):
  - **About the role's companies:** "{company} layoffs, job cuts, restructuring or closure" for each target company, pinned first. Off-limits companies and companies the radar itself added are skipped.
  - **Across the role's market:** "{industries} companies cutting jobs, closing sites or insolvent in {country}" for the hiring company's industries, in each of the role's first two countries. These searches ask Exa for a structured summary of the companies each article is about.
- **The reader decides with a quote**, in English or German. The quote is the shortest stretch of one sentence (or the title) from the company's name to the event, as written: "EKD Files for Insolvency", "Energiekonzepte Deutschland (EKD) aus Leipzig meldet Insolvenz". Keeping to that stretch leaves the rest of the sentence (a quoted manager, a photo credit) out. It is at most 140 characters, and 80 for "restructuring", which counts only when the company and the word are close. Not counted:
  - a sentence that denies it ("no layoffs are planned");
  - one person losing a job ("was laid off");
  - a buyer: the company must be the one acquired, and the quote stops before the buyer's name.
- **Never a person's name** (the rule for company research). A quote is dropped when it:
  - mentions who said what ("said", "sagte", "chief executive", "Geschäftsführer", "founder", a photo credit and the like);
  - or has any run of two or more capitalised words, unless that run is the company's own name, a country, a known place, a month, or has a company word in it ("Big Holding", "Acme GmbH").

  That is strict on purpose: a missed signal costs little.
- **A name proposed by Exa** (market news) becomes a company record only when it looks like one: a single word ("Northvolt"), a company word or an acronym in brackets in it, or the article calls it a company ("the firm X", "X GmbH"); or the desk already knows it. "Jane Doe" never qualifies. One company met under several names in one pass ("Energiekonzepte Deutschland (EKD)", "… GmbH", "EKD") is one target.
- **A signal** keeps the kind, the sentence, the page and its date. One per company, page and kind. It moves the company up for 6 months, ranking after pinned companies and before the rest.
- **New targets** from market news are added as tier "release", with the sentence as their why, in one new plan version made by "talent-release radar". Never added: the hiring company, an off-limits company, or one already on the plan.
- **Cost and limits.**
  - The radar is the last step of a run. At most 3 searches a run, and a search is not repeated for the role within 14 days.
  - A search costs about $0.007 (plus Exa's summary on market searches). It is recorded as `sourcing_exa_news`, inside the role's and the desk's sourcing budgets.
  - In results and spend it is the channel "talent-release radar (news)": it finds companies, not people. People later found at those companies count under the company group "companies releasing talent".

## Depends on
- [sourcing-engine.md](sourcing-engine.md): plans, budgets, searches, off-limits
- [web-discovery.md](web-discovery.md): the Exa client
- [companies.md](companies.md)
- [company-research.md](company-research.md): the hiring company's industries
- [tasks-and-costs.md](tasks-and-costs.md)

## Used by
- [sourcing-engine.md](sourcing-engine.md): the order of a run's searches
- [sourcing-results.md](sourcing-results.md)
- [cockpit.md](cockpit.md)

## Contracts
- Table `company_signal`: org, company, kind, quote, url, published, and the role whose radar found it.
- On the role's sourcing page, a target carries `release {kind, label, quote, url, source, published}`. A run's report carries `radar {queries[], flagged[], added[], stopped}`.

## Tests
`core/tests/test_radar.py`:
- the reader quotes a sentence about the company, never a person, a denial or a buyer;
- news about a target company moves it up and shows on the map, with no news search repeated within 14 days;
- market news adds a company releasing talent, but never a person, an off-limits company, or one with only old news;
- the radar stays inside the budget.

## Known limits
- Checked on one real search only (5 articles: it found the one real insolvency in both its English and German reports, ignored the rest, and dropped a photo credit). The first real role will show how well the searches find relevant articles.
- English and common German wording only.
- A company appearing under different names across different runs can still become two records (merge them on its company page).
- A sentence about a rival ("Acme's rival Beta cuts jobs") can still count for Acme. The quote is shown, so a person can judge.
- Signals are per desk; they are not shared across desks like company research.
