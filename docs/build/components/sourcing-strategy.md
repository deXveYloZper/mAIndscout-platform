# Sourcing strategy (talent DNA, tiers, batches, widening)

**Status:** built (next build, phase 1b, 2026-10-13); its peer search tuned on real Exa results; not yet built for a real role
**Slice / milestone:** next build, phase 1b ([plan](../../next/PLAN.md) section 4b, S7)
**Code:**
- `core/maindscout/api/strategy.py`
- `api/task_handlers.py` (`sourcing_strategy`)
- plan fields `dna`, `rules`, `open_tiers`, and query fields `company_id`, `relevant`, `known` (migration `0028`)
- cockpit: the Strategy panel, the tiered market map and the widening panel on a role's Sourcing tab

## What
A role's search runs the way a master recruiter's does:
1. learn where the hiring company's people came from;
2. build a list of companies in tiers, each with its reason;
3. search them in batches until each is exhausted, and let the list grow;
4. when the list is exhausted, propose widening with numbers, and let the owner decide.

## Why
The owner (2026-10-13): "we should be aware that our initial list of companies we have put together is probably not enough, so we continue building this list to target from and do searches in manageable bunches. Once we are fairly confident that we have exhausted those searches, we expand the net." Before this, the target list was fixed, nothing measured exhaustion, and country-wide searches ran in every run.

## How
- **Stage 1: talent DNA** (`talent_dna`, about $0.05).
  - The hiring company is profiled first (by its website or LinkedIn page). Without a confirmed Exa company ID, the strategy is refused with a clear message.
  - Up to 3 "{title} at {company}" people searches. Only people whose work history shows the hiring company under its **exact** company ID count.
  - From them it records their titles there, the job just before they joined, and their earlier employers (profiled by ID, grouped by kind, size band and categories).
  - Noise is dropped by name (hackathons, communities, clubs, pubs, schools) and by profile (no staff, no industry).
  - It adds the company's own profile: where the team works, departments, and Exa's talent sources.
  - **Nobody found here is ever stored:** they work at the client.
- **Stage 2: tiers** (`build`, under $0.50 in all).
  - **A:** named by the hiring manager, added by hand, and **repeat feeders** (2 or more people, at most 5,000 staff).
  - **B:** companies like the hiring company, from two descriptive company searches built from its profile ("{what it offers} companies in {where the team works}", "{its market} startups, {stage}"); micro companies under 10 staff are left out. Also desk companies in the same domain, and snowball finds. (Exa's find-similar was tried and dropped: on procure.ai it returned name look-alikes.)
  - **C:** feeders over 5,000 staff (a kind of employer, not a list to search), companies the radar finds in market news, and adjacent industries.
  - The plan's titles gain the hiring company's own titles held by 2 or more people (role-like only). Its countries become where the team works (15% or more), unless the owner set them.
  - **From the hiring profile** (`profile_queries`), always: its industries and the short backgrounds a person typed or the intake gave, as company searches in the role's countries ("luxury, fashion and beauty companies in Italy"). When the role has no hiring company, or Exa cannot confirm it (an anonymised ad, a small company), there is no talent DNA and the list is built from these alone; the Sourcing tab says so. With neither a company nor an industry, the strategy is refused and says what to add.
  - **Titles** start from the ad's title without its places ("Marketing Manager Italy and Europe" → "Marketing Manager"), then the usual titles for the kind of work (marketing, sales, customer success, design, finance, HR and operations as well as engineering).
  - **Checkpoint 1:** the owner reviews the DNA and the list before choosing how often to search (a new plan is paused).
- **Stage 3: batches** (`next_searches`, `company_state`).
  - Each run takes the next **5 companies** in the open tiers. The order is pinned first, then companies releasing talent, then tier, then kind.
  - Each company is searched with up to 3 title variants (plus "senior …" when it has more than 1,000 staff). A search is not repeated within 30 days.
  - **Deeper searches** (owner, 2026-10-13: replies take time, so each search should give a longer list). A search at a company asks for about a quarter of its staff, from 10 to 50 (`max_results`), or 25 when its size is unknown; a country-wide search asks for 25. Exa charges $0.007 for 10 and $0.001 for each one beyond, so 50 cost about $0.047. In a test, all 25 results of "software engineer at Omnea" (219 staff) really worked there. The budget check uses each search's own price.
  - **Only that company's people count.** A result counts only when the person's work history shows the company (its Exa ID, one of its names, or its LinkedIn page). Look-alikes are skipped and never stored: on the first real run, 20 results for a 9-person company included none of its people. A suggestion says "works at X now" or "worked at X before".
  - A company is **exhausted** when every variant has been searched and either the last 2 searches found no new relevant person, or 80% of its results were already known. An exhausted company waits 90 days, unless the radar flags it.
  - **Relevant is counted as it stands now** (2026-10-19, `relevant_now`): the strong suggestions each search found, by their current
    band. Most people become strong only when their career reading arrives after the run; counted when found, every marketing
    search read 0 while Safilo's three had found 15 strong people, and Safilo was rested as exhausted. The widening proposal's
    yield is counted the same way.
  - Per company the plan keeps searches, results, known, relevant and the date of the last search.
  - **Snowball** (after each run): an earlier employer of 2 or more strong people for the role becomes a tier B target. A company that has produced 3 or more strong suggestions gets its own peer search, once.
  - **Country-wide searches by title run only when the owner opens them.**
- **Stage 4: widening** (`widening`, `widen`). A proposal appears when every company in the open tiers is exhausted and the role is short of its target (the recent yield is shown in it, to help the choice). In detail:
  - every company in the open tiers is exhausted;
  - the role is short of its target;
  - (the recent yield, relevant people per search over the last 15, is shown; it no longer blocks the proposal).

  It also appears when the open tiers have no companies at all. Its options carry numbers:
  - open the next tier (with its company count);
  - widen the titles;
  - add a country (from where the hiring company's team works);
  - drop a must-have ("about N more on the desk", changed on the hiring profile);
  - last of all, country-wide searches.

  **Checkpoint 2:** the owner picks one, and it becomes a new plan version. Tier A always stays open.
- **A luxury client recruits from luxury** (2026-10-18, [decision](../../decisions/2026-10-18-every-kind-of-role.md)):
  when the role's own requirements say luxury, its industry searches use luxury words ("luxury hotels, five-star hotel
  groups and high-end hospitality companies in Italy") and a company known not to be luxury (a 4-star chain, a tour
  operator) is not searched; the map says "not a luxury company". The talent DNA searches the client by the name
  its confirmed profile gives ("BONAVENTURA", not the ad's "BUONAVENTURA").
- **In step with the hiring profile** (`sync`, at every run and page view; owner 2026-10-13): its "must live in" countries are the role's countries, and every company it names is a pinned tier A target. A new plan version only when something changed.
- **Where the role is.** The hiring profile's "must live in" countries, else the places the ad names ("LOCATION: Markham or Gatineau"). A city that names no country counts as the hiring company's home country. The sync only adds these countries; one the owner added is never taken away. When the ad names its place, the strategy never replaces it with where the hiring company's team works.
- **Companies that can give the role nobody are not searched:** one that has shut down (by its public facts), or one whose team works only outside the role's countries (from its profile). The map says why ("not searched: no team in the role's countries"). Pinning searches it anyway.
- **Peers also by the role's specialist skill:** "{skill} companies in {the role's countries}" ("insar companies in Canada" found 3vGeomatics), next to the searches built from the hiring company's own offering and market, always in the role's countries.
- **Only the role's countries.** When the role has countries, someone living elsewhere is not suggested, from the web or from the desk's own pool (refused as "outside the role's countries"). Where they live decides; where they work counts only when where they live is unknown; unknown altogether is not refused. They don't count towards the target either, so they never hold the search back. (Before this, the pool step put a Bucharest and a Heemstede person on a Germany-and-UK role, because the desk's coverage covers the EU.)
- **Strong first.** "Possible" matches are folded below the strong ones. "Search now" says when it did not search because the target of waiting suggestions is reached.
- **Rules** (`plan.rules`, editable through the plan route): `batch` 5, `exhausted_after` 2, `known_share` 0.8, `low_yield` 0.2, `recheck_days` 90, `yield_window` 15, `max_results` 50.

## Depends on
- [company-knowledge.md](company-knowledge.md)
- [sourcing-engine.md](sourcing-engine.md)
- [web-discovery.md](web-discovery.md)
- [talent-release-radar.md](talent-release-radar.md)
- [sourcing.md](sourcing.md): must-have tokens

## Used by
- [sourcing-engine.md](sourcing-engine.md): what each run searches
- [sourcing-results.md](sourcing-results.md): tiers as strategies
- [cockpit.md](cockpit.md)

## Contracts
- `POST /v1/jobs/{id}/sourcing/strategy`: answers 202 and queues a task.
- `POST /v1/jobs/{id}/sourcing/widen {option: open_tier|titles|country|market, value}`
- `PATCH /v1/jobs/{id}/sourcing/plan` also takes `rules` and `open_tiers`.
- The role's sourcing page carries `plan.dna`, `plan.rules`, `plan.open_tiers`, each target's `group`, `progress` and `profile`, plus `widening` and `building`.
- Ledger purposes: `sourcing_talent_dna`, plus `sourcing_company_profile` for the profiles and peer searches.

## In step with the hiring profile (x-ray, 2026-10-14)
- **One place for a role's countries:** the hiring profile's "where people must live" (`hiring.set_residence`).
  - The Sourcing tab's country box, the widening "add a country" option and the hiring profile all write to it. The plan follows it both ways (`sync`).
  - Names are understood ("Italy"). An unknown name is refused.
  - With nothing stated, the plan keeps what the strategy chose (the ad's places, or where the client's team works).
- **"Not from"** (`not_from`):
  - A company the hiring profile says not to recruit from is never searched, and its current people are refused (`not_from` in a run's report).
  - A background it does not want (consultancy, agency, public sector, non-profit) keeps companies of that kind out of the peer list and the batches.
- The old "Find peer companies on the web" button is gone: the strategy finds peers.

## A competitor is of comparable size (step C, 2026-10-21)
A company 20 or more times the client's size is in its market but no competitor (`much_bigger`, the same factor as
the move check): a new map lists it in Tier C ("in the client's market, much bigger"), and on an existing map it
says "about 197x the client's size: not a competitor (searched only if you widen to Tier C)". It is searched once
Tier C is open, or when pinned; a company the hiring manager or the owner named is always searched.

## From the owner's 0-to-1 test (2026-10-21)
Three roles rebuilt from an empty desk showed four kinds of wrong target; each is now refused by code:
- **A search by the role's skill** ("insar companies in United Kingdom") also returned look-alike names: a
  confined-space rescue firm (ISAR3), an automotive one (INSPHERE). A company found that way must name the skill
  in its own description.
- **A nice-to-have industry** ("infrastructure, dam, mining or other asset monitoring") filled the InSAR map with
  water utilities. The role's required industries decide where to hunt; nice-to-have ones only when it names none
  (an anonymised ad whose only industry is a nice-to-have sentence still has one).
- **A product company's peers** included seven procurement consultancies (Procure AI). Consultancies, agencies and
  outsourcers are never "like" a product company.
- **A company the hiring profile rules out** (Valentino) was listed as a target: it is never added, and if listed
  the map says "not searched: the hiring profile says not to recruit from here" (the search had always skipped it).

## Tests
`core/tests/test_phase1b.py`:
- the strategy reads the talent DNA and builds tiers: only the client's own people by exact ID, noise dropped, the hiring company never a target, countries from the team, peer searches phrased from the profile, micro companies left out, nobody at the client stored;
- companies are searched in batches until exhausted, then widening is proposed;
- the list grows from where strong people worked before;
- the strategy and widen routes.

`test_radar.py` covers ordering with release signals and exhausted companies.

## Known limits
- Not yet built for a real role; the talent DNA was tried by hand on Procure Ai (13 people, $0.041).
- For a small hiring company the feeder list is thin. The pattern (kinds, sizes, fields) is what guides the owner; it is shown, not yet used to filter tier B automatically.
- "Relevant" is the band when found, so a later re-match does not change a company's past counts.

## Competitors researched on the web (step D, 2026-10-21)
The owner: "the LLM deep search into competitors and similar companies is a must ... we should not even bother to
search companies that are way out the size range". Building the list (`strategy.build`) now starts with one Grok web
search (`intelligence/competitors.py`, up to 12 searches, about $0.20-0.50) for the client's competitors and similar
companies with people in the role's countries, 25 to 40 when the market has them. It is given only what the desk knows of
the client (what it sells, its kinds of work, its size, where), never a person. Each company must come with a page the
search opened and a short quote from it that names the company, or it is refused (the Sourcing tab says how many and
why). Each is confirmed by Exa (its size, where its team is); one 20 or more times the client's size is left out
and never searched, and so is one found by a company search (it used to go to Tier C). The rest are tier "competitor",
in Tier A with the named and feeder companies: the first places searched. The tab shows what the research found:
how many, kept, left out as much bigger, refused, pages read and cost.

A small company (150 people or fewer) is searched with one broad search for the role's kind of work ("marketing") in
place of each title variant: a 40-person brand has two or three marketing people, whatever their titles.

First live run, Bonaventura (2026-10-21): one call found 10 companies, so the research now goes deeper. Up to three
rounds, each later one told every company already known and looking from another side (smaller, online and
direct-to-consumer brands, the same retailers and districts; then neighbouring categories and nearby countries); a
round adding fewer than 3 new is the last. A quote that does not name the company is kept only when Exa confirms the
company (a page's "about" sentence often never says its name); a refusal keeps the start of its quote. A listed company
the research names becomes a competitor. A rebuild drops what the desk's own searches listed earlier that is now known
to be far bigger, or that the hiring profile says not from (Valentino, Dolce&Gabbana, Armani, Prada Group went);
never a company a person named, pinned or placed. Bonaventura: 3 rounds, 197 pages, $0.44, 28 kept, Bottega Veneta,
TOD'S and Brunello Cucinelli left out as far bigger; 49 competitors in Tier A with the earlier round's.

## The Ferrari investigation (2026-10-22)
The owner uploaded a CRM role for Ferrari: its list was the last role's fashion houses, its searches were for
"customer success manager", and 432 of 444 found were unlikely. What was wrong, and what changed:
- **"Search now" ran on a list nobody built.** It now builds the list first when it was never built (the competitor
  research, about $0.45), then the search follows by itself; the tab says "Building the company list…".
- **The starting list ranked companies by how many of our own people worked there**, so a new role got the last
  role's pool. It now ranks by shared industry, leaves out companies 20x the client's size, and our people only break
  a tie.
- **The research did not know the role, nor every line of the client's business.** It now first establishes every
  line (for Ferrari: its cars, racing, and its fashion and lifestyle collection; owner: "Ferrari has recently also moved
  into fashion"), then finds competitors for each line, and companies whose people do the role's work for the same
  customers (line "talent"). The tab shows the lines found. Ferrari: 42 kept of 43, luxury car makers (Pagani,
  Pininfarina, McLaren, Bentley, Porsche, Dallara) and luxury fashion (Zegna, Canali, Herno, Fratelli Rossetti).
- **A specialist role searches its specialism's titles** (`domain/specialism.py`): "Salesforce" or "CRM" in the title
  or must-haves makes a CRM role ("CRM specialist", "CRM manager", "Salesforce administrator", "CRM analyst"; broad
  search "CRM" at a small company), never the family's defaults ("account manager"); a rebuild drops titles that were
  only a family's defaults. A CRM in a marketer's nice-to-have list is scope, not a CRM role.

## The talent map (2026-10-23)
The owner: "Pomellato was not even in our list ... Luxury is Luxury ... we need to ensure that Exa does not rule out our
hard work". The research now starts with one call for the client's lines of business and the role's **talent pools**:
its direct competitors and every industry serving the same customers at the same level (for a luxury client: luxury
cars, fashion and leather goods, jewellery and watches, beauty, hospitality, e-commerce), six to ten pools with
examples. Each pool gets its own research round; a pool that gave three or more new companies gets a deeper round
(smaller, less obvious names). At most 16 rounds per build (about $2). Each company keeps its pool; the tab and the
activity log show the pools. Without a map (no answer), the old rounds run as before.

**Exa confirms, never judges, a researched company.** A company the research or a person placed is never left out by
Exa's own words: Lamborghini, Pagani, McLaren and Dallara had been "not a luxury company" because Exa calls them "super
sports cars" and "hypercars". Exa still supplies size and team; far bigger than the client, or no team in the role's
countries, still leaves a company out.

**Wide before deep.** While a company on the list has never been searched, each gets its first search, one per company,
up to 8 per run; other titles follow once all had one (13 of Ferrari's 37 competitors had never been reached when its
budget ran out, after four titles at each of the first houses).
