# Next build: the talent-intelligence desk

**Status: Phase 1 APPROVED** 2026-10-12 by the owner ("go"), including a first look at Exa with a few test searches.
Phase 1 is built (see [STATUS](../build/STATUS.md)) and waits for its first real role; its gate (two weeks on a real
role) is the owner's to declare.
**Phase 1b APPROVED** 2026-10-13 by the owner ("go ahead with phase 1b"; section 4b): company knowledge by identity keys (Exa for breadth, Grok for depth) and a
staged search (talent DNA, tiered target list, batches, exhaustion, widening with the owner's say). Built 2026-10-13
(see [STATUS](../build/STATUS.md)); peers come from descriptive company searches, since find-similar matched on names.
Phases 2–6 stay drafts until the owner approves them. Revised the same day with the owner's answers (section 10).
Written after a survey of what is built ([STATUS](../build/STATUS.md)).

**How it will be used:** the owner is the only user for a period, to prove it works and improve it. Clients get their
desk once it is solid. Selling the platform itself (section 7) is the ultimate goal, and comes last.

---

## 1. The idea

One loop, run faster and smarter on every role than a competitor can by hand:

> **Sign a role → understand it → map the market → reach the right people, continuously → qualify → submit with a
> coversheet → the client acts in their own desk → every outcome teaches the engine → the next role is faster.**

"Talent intelligence" is what accumulates on the way: which companies hold the people, which adjacent domains
convert, what candidates want and earn, who moved where, which channels answer, and what each of those cost. That
memory is the moat. Every build below either feeds it or puts it in front of someone (the desk, a client, a visitor).

## 2. What we already have, and what is missing

| Step of the loop | Built | Missing |
|---|---|---|
| Understand the role | Hiring profiles (ad + hiring-manager notes + recruiter edits), research on the hiring company (kind, stage, size, domains, funding, base) | An intake briefing: how big the market is, what each must-have costs in candidates |
| Map the market | Target companies only when the ad or hiring manager names them; alumni counts on the desk | **Suggested target companies** (peers by domain and stage, adjacent domains, companies releasing talent) |
| Find people | Search in your own words over the desk's people; "Find more people" on a thin job (desk only, by hand) | **External discovery** (web, Exa), **always-on** runs, rediscovery for every new role, inbound channels beyond upload |
| Judge | Matching v2 per requirement, bands, gap table, preferences from calls, coverage gate, client blocks | Off-limits companies (never poach from a client) |
| Talk | Brief with call questions, call transcripts → one bulk review, drafts into Gmail/Outlook, follow-ups a reply stops | Approaching people found on the web (a profile link, no email); recording their permission |
| Submit | Pipeline stage "submitted" with a note | **The coversheet** (why this person, evidence, what to probe, what they want) and a client-ready CV |
| Client | Client contacts and timelines, client rejection as a wall | **Everything client-facing**: accounts, their desk, interviews, feedback, statistics |
| Learn | Pair outcomes and reasons kept; costs in the ledger; I7 waits for real decisions | **What each search strategy costs and yields** |
| Be reachable | Runs on this machine only; the website's CV form saves to a local folder | **Hosting, HTTPS, outgoing system mail, the website ↔ platform seam** |

## 3. What stays, and what changes

Kept, everywhere: belief is gated (machine proposes, a person approves); every fact has evidence; same path for
everyone (a person found on the web is identified, matched, gated and blocked like an uploaded CV); never protected
characteristics, personality, culture or fit; where someone lives and works, never where they are from; a band is
never a number; a client rejection is a wall; "stop" and erasure win over everything.

Changed (owner, 2026-10-12):

1. **Sourcing runs by itself for open roles**: daily, weekly, or continuously until a role's target is reached.
2. **People found on the web are kept as public data only**: a guide from the platform to the owner, "contact this
   person". Their CV, contact details and permission come from them, when the owner talks to them. No extra GDPR
   machinery beyond what a recruiter normally does (owner: "do not over engineer this").
3. **Everyone found stays in the talent pool.** Someone wrong for this role may be right for the next; every new role
   looks at the pool first.
4. **Clients get a live desk** (hosted on the internet), and later **a paid plan** of their own.

## 4. Track S: the sourcing engine ("the search that never sleeps")

**S1. Market map for each role** (the strategy, shown and editable before anything runs)
- *Target companies, with why:* direct peers (same domain, similar stage and size, in the role's countries);
  adjacent domains where the skills transfer (e.g. automotive ADAS ↔ robotics perception; flight software ↔
  safety-critical medical or rail; power electronics ↔ energy storage); companies **releasing talent** (layoffs,
  acquisitions, shutdowns, office closures, funding trouble in recent months); companies we already know people at.
- *Sources:* our company research (domain, stage, size, base), Exa company search, the desk's alumni graph, and job
  discovery (blueprint Feature 11.1): public ATS job boards (Greenhouse, Lever, Ashby, Workable) show which companies
  are hiring the same profile, so we know who competes for this talent.
- *Role variants:* the titles that mean the same work ("embedded software engineer" ≈ "firmware engineer" ≈
  "flight software engineer"), from the shared role families.
- *Off-limits* (owner: correct): never source from active clients; a placed person's new employer is off-limits for
  12 months. Plus client blocks and "stop".
- The owner pins, removes or adds companies; the plan is versioned, so we always know which version found whom.

**S2. Discovery** (behind the existing `find` interface; background tasks, never in a request)
- **The pool first, it is free:** the desk's own people, people found for earlier roles, silver medallists (late stage
  for another client), people whose preferences or notice window now fit.
- **Exa people search** (`category: "people"`, 1B+ public profiles, LinkedIn and the wider web; about $0.007 a search
  with 10 results and their text). Queries come from the plan (role variant × target company; role × country ×
  domain) and name roles and companies, **never a person**.
- **Exa publication research** for research-heavy roles (perception, controls, ML): people with their papers,
  collaborators and research areas, evidence a job title never shows.
- **Engineering footprints** found through Exa: personal sites, open-source projects, conference talks. (GitHub's
  [acceptable use policies](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies),
  section 7, bar using its information for unsolicited emails or selling it to recruiters: a GitHub profile can point
  us to a person, never be a contact source.)
- **Public data only:** name, profile link, headline or title, company, location and the public lines that support
  them (each fact quoted from the page, as everywhere). No CV, no contact details, no photo.
- Every result goes through identity (no duplicate when we know them already; a known person found again may show a
  newer job), coverage, off-limits, client blocks, "stop", and matching. They arrive as **suggestions to contact**,
  each with **why we think they fit** (quotes) and **what we don't know** (the first call's questions).

**S3. Runs on their own**
- Each open role has a mode: **daily**, **weekly**, or **continuous until the target** (e.g. 10 strong suggestions
  waiting), a monthly budget, and it stops when the role is filled, paused or closed.
- A run goes cheapest first: the pool → people we know at target companies → web discovery (only queries and profiles
  not seen before) → the talent-release radar (news about target companies).
- **Run report**, one screen: companies searched, people found, new vs already known, refused by the gates, strong
  ones waiting, cost. Aggregated, it is what the client later sees as "this week's search" (C4).
- **Hard-to-fill mode.** When a role has had no submission for some weeks, or the suggestions dry up, the engine
  proposes widening moves with numbers: "12 people in DE/AT/CH meet all must-haves and we have reached 10; dropping
  'Rust' as a must → 40; opening the UK → 25; adjacent domain automotive → 55." The owner picks one, or takes the
  numbers to the client: a calibration conversation backed by evidence.

**S4. Reaching them, and their permission**
- A **LinkedIn message** drafted from the person's public evidence and the role's public facts (the outward projection
  we already have); the owner sends it from LinkedIn and marks it contacted. Email when they publish one.
- Their answer (pasted, or by email) is read like a call: interested, not now, or stop (writes the do-not-contact
  list); new facts.
- When they share a CV, it is read like any CV and joins the record. **Their permission is recorded** as they give it:
  put forward for this role, and/or for other roles. Submission (C1) checks it.

**S5. Results and spend: does the strategy work?** (built in phase 1, not later; owner: "crucial")
- One funnel, with money on it: **spend → found → relevant → contacted → replied → interested → CV received →
  submitted → interviewed → offered → placed**, with cost per relevant person, per interview and per placement.
  Example: "$5 spent: 800 found, 100 relevant, 40 contacted, 12 replied, 5 interviewed."
- Split by everything we can change: target-company tier and company, channel (pool, network, Exa people,
  publications, footprints), query, message, role, week. Compared over time and across roles.
- **Budgets are adjustable** per role and for the whole desk, at any time, and every run respects them.
- The engine flags what isn't working ("30 contacted at tier-2 companies, 0 replies: pause tier 2?") and what is
  ("peers in Munich: 1 interview per $1.20"), and each suggestion shows the numbers behind it. The owner decides; the
  plan changes are versioned so before/after can be compared.
- Over time this builds the desk's **domain transfer map** from real hires: where good people actually came from.
  No learned change may use a proxy for a protected characteristic (blueprint F10.9).

**S6. Inbound channels** (not sourcing, but the same intake)
- The website's applications and CVs go straight into the platform (F4).
- An applications inbox (e.g. apply@maindscout.com) for LinkedIn job-ad applicants and job boards: attachments read,
  the person put on the role, the channel recorded in S5. LinkedIn's direct ATS connection is for partners only;
  forwarding is the practical route. Reading those emails needs a wider mailbox permission than today's (decision 9).

## 4b. Phase 1b (APPROVED 2026-10-13): know the companies, and search like a recruiter

Written after the owner's questions of 2026-10-13 and five small Exa tests ($0.13 in all). Approved by the owner
2026-10-13 ("go ahead with phase 1b").

**Why.** Phase 1 finds people, but two things are weak.
- **People found by Exa get no company work.** Their fit rests on titles and skills alone, while every client rates
  a candidate by where they worked: the domain, the kind of company, its size and stage.
- **The search is a fixed list.** The market map is built once. Each target company gets "{title} at {company}"
  searches, and then the role is searched country-wide, which is the blind part. When every search has been made, a
  run just says "no new searches" and waits. Nothing measures when a list is exhausted, the list never grows by
  itself, and nobody is prompted to widen.

A master recruiter works differently:
1. learn where the hiring company's people came from;
2. build a list of similar companies and keep growing it;
3. search it in manageable batches;
4. when it is exhausted, widen the net, and only then loosen the profile.

### What the tests showed (2026-10-13)

| Test | Result |
|---|---|
| Grok company research, from the ledger | $0.094 a company (55 companies, about 10 pages read each); quoted facts with sources, including events (an acquisition agreement) and registry dates |
| Exa company search by name, on 10 companies Grok had researched ($0.07) | Right company 6–7 of 10; wrong but similar-named for small or regional firms (semantika.pl for semantika.si); founded year 5/6 agree, headcount 5/6 close, HQ 4/6 (CGI placed in the US); no status; no industries field, but a clear description |
| Exa company IDs ($0.015) | The company ID in a person's work history is the same ID company search returns (CATALYST `q923d4ct2dw` in both); about 7 of 10 employers carry one, the rest a LinkedIn company link or a name |
| A company profile by its ID (`/contents`, $0.001) | Size, HQ, founded, funding and an industry line ("…is a Software Development company"), as quotable text, plus its LinkedIn page |
| Talent DNA of Procure Ai ($0.041) | 4 "role at Procure Ai" searches found 13 of its people by its company ID. Titles: software and full-stack engineers, ML engineers. Before joining: senior full-stack and ML/LLM engineers, from big tech and consulting (IBM ×2, McKinsey ×2) and a small supply-chain startup (×2). The rest were single mentions, plus noise (hackathons, a community group, an award list) |

**Conclusions.**
- Exa is the cheap, exact way to know the employers of people Exa found: by ID, a tenth of a cent each.
- Exa's search by company name is risky: it should be accepted only when a key confirms it.
- Grok stays for depth, where accuracy matters most.
- For a small hiring company, the talent DNA is a pattern (kinds of company, domains, career paths), not a list of
  names.

### K. Company knowledge: one record, researched once, identified by keys

**K1. Identity keys.** Each company keeps its website domain, its Exa company ID and its LinkedIn company page. Every
route that brings in a company looks it up by these keys first: a CV, an applicant, an email, an Exa profile, the
market map or the news radar.
- A new name that shares a key with a known company is that company: it becomes an alias, because a key is not a
  guess.
- Two existing records that share a key raise one "Same company?" card. They are never merged silently.
- This is what stops paying twice for the same company: "CATALYST" and "PCI Geomatics", "Procure Ai" and "ProcureAi
  Ltd".

**K2. Three levels of knowledge, used in this order.**
1. **Known (free):** the company is on file and fresh enough, so nothing is spent.
2. **Profile (Exa):** by ID, $0.001; by name, $0.007, accepted only when a key confirms it. It gives size, HQ,
   founded, latest funding and the industry line, each quoted from the profile text. The source is a third-party
   estimate. One small model call (about $0.003) reads the industry and the kind of company (product, consultancy,
   agency…) from the profile's own lines, with the quote. Refreshed after 6 months.
3. **Depth (Grok, $0.094), only where it pays:**
   - hiring companies (clients);
   - companies on a live role's target list;
   - employers of a candidate about to be submitted.

   It gives the quoted facts as today: industries, kind, status and events, and funding history with investors.

**K3. Cross-check.** Where both sources give the founded year, HQ, headcount or latest round:
- if they agree, the fact counts as confirmed by two sources (no longer single-source);
- if they disagree, one card shows both, with their sources.

The status rule is fixed: "agreed to be acquired" is pending, not acquired.

**K4. Who gets what.**
- **CV, applicant or email:** employers arrive as names. Match by key or known alias first. Then try an Exa search
  confirmed by a key, and otherwise use Grok research as today.
- **Sourced (Exa):** employers arrive with their Exa ID or LinkedIn page. Look them up, and profile the new ones by
  ID. Then build the same career reading a CV person gets (kinds of employer, industries, level, years) and match them
  to the role. This is done only for people who pass the gates (stop, off-limits, countries). Each strong suggestion
  then says where they worked in facts ("a 90-person earth-observation software company"), not just titles.
- **The knowledge compounds:** every company profiled is kept and shared by every route. As the desk grows, most
  employers of new people are already known, so web lookups shrink.

### S7. A staged search that grows, measures and widens

**Stage 1. Talent DNA of the hiring company.**
- A few "{role} at {hiring company}" people searches, kept only for people whose history shows the hiring company
  under its exact company ID.
- From those people:
  - their titles there, which become the role's title variants;
  - the job just before they joined;
  - their earlier employers, profiled by ID and grouped by kind, size and domain.
- Noise is dropped: hackathons, communities, awards, volunteering and education. Only employers with a company profile
  that has staff and an industry count.
- For a small hiring company the result is a **pattern** ("big tech and consulting into an AI startup; small
  supply-chain startups; senior full-stack and ML engineers"). For a large one, the **repeat feeders** themselves (2
  or more people) become targets.
- Cost: about $0.05.

**Stage 2. Target list in tiers, each company with its why.**
- **Tier A:** companies the hiring manager named, then repeat feeders.
- **Tier B:** direct peers. They come from Exa's find-similar on the hiring company's website and from company
  searches by domain and stage, filtered by the DNA pattern. Desk companies in the same domain join too.
- **Tier C:** adjacent domains, other stages, companies the news radar flags as releasing talent, and the kinds of
  employer the DNA shows (for example, big tech engineering groups).
- Every company is profiled (K2), so "similar" is shown in facts: size, stage, HQ, domain.
- **Checkpoint 1 (the owner):** the DNA summary and the starting list, before anything wide runs. The owner pins,
  removes or adds.

**Stage 3. Search in batches; exhaust each company; let the list grow.**
- Each run takes the next batch of companies (default 5, in tier order). Each company is searched with the title
  variants, and with seniority words when it is large.
- A company is **exhausted** when every title variant has been searched and the last two searches brought no new
  relevant person, or when 80% or more of its results were already known. An exhausted company is searched again only
  after 90 days, or when the radar flags it.
- **Snowball:** when two or more strong suggestions share an earlier employer, it is proposed as a new target, with
  that reason. A company that keeps producing gets its own find-similar.
- Per company and per tier, the platform keeps the searches made, people found, relevant, contacted and interviewed.
  These feed results and spend (S5) as strategies: tier, DNA feeders, snowball.

**Stage 4. Checkpoints, and who decides to widen.** The platform measures, proposes and shows numbers; the owner
decides. A widening proposal appears when all of these hold:
- the current tier is exhausted;
- the role is still short of its target of strong suggestions;
- the recent yield is low: fewer than 1 relevant person per 5 searches over the last batches.

The thresholds are editable per role. The proposal offers options with numbers, which is the plan's hard-to-fill mode:
- open the next tier ("Tier C: 18 companies");
- widen the titles;
- add a country;
- loosen a must-have ("dropping 'Rust' finds about 40 more on the desk");
- last of all, country-wide searches.

**Checkpoint 2:** the owner picks one. It becomes a new plan version, so results before and after compare.
**Checkpoint 3:** weekly results and spend per strategy.

Country-wide searches by title stop being part of every run. They are the last widening option.

**Costs.**
- Setting up a role: under $0.50 (DNA about $0.05; about 40 company profiles at $0.001–0.007; one or two
  find-similar searches).
- Each batch: a few cents.
- Employer profiles for sourced people: about 1 cent a person, falling as the knowledge base grows.
- Grok depth only on the hiring company, the live targets, and employers of candidates about to be submitted.

## 5. Track C: the client desk

**One truth, live.** The client desk is a window onto the same pipeline, never a copy. When the owner submits a
candidate it appears on the client's desk at once (and they get a short email); a client's click writes to the same
pair (party: client) and lands on the owner's timeline and Inbox.

**What a client never sees:** bands, match tiers, internal notes, the Brief, people not submitted to them, other
clients, and candidates' contact details (the owner introduces; this protects the candidate and the fee).

**C1. The coversheet** (built first, on the owner's side; useful before any hosting as a branded PDF)
- Who: current role, location and mobility, notice, availability, and the **salary expectation, shown once the owner
  has confirmed it with the candidate** (the coversheet says when).
- **Why I'm putting them forward:** the role's must-haves and strong pluses, one line each, with the evidence (CV or
  call, quoted) in client words; drafted from approved facts and match verdicts, edited by the owner.
- **What to explore in interview:** the open points (an unverified must-have, a gap, a question the call raised)
  written as questions for the hiring manager and interviewers. A tailored interview guide per candidate.
- What they want, and how this role fits it; the owner's own note; the CV attached (decision 7).
- Frozen at submission (what the client saw is kept); the same mechanical check as drafts (no internal words).
- Submission needs the candidate's recorded permission for this role (S4).

**C2. Client accounts and members**
- A client company becomes an account. The **hiring manager** is its admin; they can **add interviewers, only from
  their own company**: an invitation is accepted only for an email at the company's own domain(s), which the owner
  sets. No one outside the company can ever be added (owner: "to avoid any misunderstandings").
- Each member sees the roles they are part of. Sign-in like members today (optional two-step codes).
- A **share link** for a single candidate (view only, expiring) for anyone who will not sign in.
- An access log (who viewed or downloaded what); downloaded CVs carry a watermark ("submitted by mAIndscout to
  <client> on <date>"); access ends some weeks after a role closes.

**C3. The client's desk** (polished, works on a phone, in the website's engineering look)
- Home: their roles with stage counts; "waiting for your feedback", with gentle timers.
- Role: a board (submitted → interviews → offer → hired; declined), candidate cards; it updates itself live.
- Candidate: the coversheet, the CV, interviews and every interviewer's feedback so far.
- Actions: invite to interview, decline (a reason plus their words: becomes the client-block wall and a learning
  label), ask a question (reaches the owner, may become a Brief question for the candidate), feedback after each
  interview from each interviewer (structured on the role's requirements; no personality or culture fields), offer.

**C4. Statistics and the weekly report**
- Per role and across roles: time to first submission, submissions per week, interview and offer rates, time in each
  stage, why candidates were declined.
- This week's search, from S3's run reports, in aggregate: companies searched, people approached, replies, the size
  of the market. The client sees the work behind every submission. **This is what gets them hooked** (section 7).

**C5. Interviews**
- First version without calendar access: the client proposes times (or shares their booking link), the owner confirms
  with the candidate, everyone sees the booked slot, and calendar files are offered for download.
- Later, with the owner's yes: Google / Microsoft calendar connection (free/busy, creating the event).

**C6. Anonymised profiles and the two-stage introduction** (blueprint Feature 11; today's Slice 5 BD item)
- "Work before name" profiles shared with clients and prospects; "request an introduction" asks the owner, who asks
  the candidate; on their yes the full coversheet opens. The same rule the website states.

## 6. Track F: going live (needed by the client desk and by the website's CV form)

- **F1. Hosting** in the EU: the Docker setup from 2026-10-12 is the seed; managed Postgres with backups that are
  restored in a test, encrypted file storage, HTTPS, separate domains (e.g. desk.maindscout.com, clients.maindscout.com),
  secrets outside the code, monitoring and alerts. Rough cost: €30–80 a month.
- **F2. Security pass before anything is public:** an authorisation test matrix (a client member can never reach
  another client, a recruiter-only route, or a person not submitted to them; an invitation outside the company's
  domain is refused), secure cookies, content security policy, dependency audit, rate limits on public routes.
- **F3. Outgoing system mail** (invitations, password resets, "new candidate to review") through a transactional
  service. The desk still never sends relationship messages itself (decision 6).
- **F4. The website ↔ platform seam:** CVs and applications from the website into the platform; published roles from
  the platform to the website; anonymised showcase profiles (owner-approved). Until this exists, a CV sent from the
  hosted website would be lost.
- A privacy notice on the website for candidates and clients, and simple terms for client desk users.

## 7. Track M: the paid plan (the ultimate goal, after the owner-only period)

Owner, 2026-10-12: clients who like how we find candidates but have no budget for a 15–20% fee could subscribe
instead: **a monthly plan (e.g. $300) with a number of searches included, and credits to buy for more, at our margin.**

- **The client desk is the doorway**: they already know the desk, the coversheets and the weekly search report.
- **A client's own sourcing desk:** the same engine (market map, runs, results and spend) on their roles, with their
  own budget, in their own desk (desks are already separate tenants).
- **The owner's talent pool stays the owner's.** A paying client searches the web and their own people, never the
  owner's pool, unless the owner chooses to offer it. The pool is the business's moat.
- **Metering from phase 1:** every paid action (search, reading, enrichment) is already in the cost ledger per desk;
  phase 1 adds which role and strategy it served. Prices can then be set from real costs (as imports are priced at
  compute cost × 1.9).
- Plans, credits, invoices and payments (e.g. Stripe), self-service sign-up, usage limits: built only when the owner
  decides to open it.

## 8. Track W: the website (the window to the world)

- W1. Live roles and the CV form through the platform (F4); the anonymised talent showcase (C6).
- W2. A phone polish pass across every page (the opening's overflow was found only on a phone), plus speed and
  accessibility checks.
- W3. The two missing domain drawings (semiconductors, energy), so all seven chapters can be public.
- W4. **Insights from the market maps**, aggregated and anonymised ("Embedded engineering talent in DACH, Q4 2026"):
  the platform's intelligence becomes the business's proof and its inbound.
- W5. Privacy-friendly analytics: which pages clients and candidates actually use.

## 9. Order of work

| Phase | What | Gate (the owner declares) |
|---|---|---|
| **1. Find them, and know what works** | S1 market map; S2 the pool + Exa; S3 runs with modes and reports; S4 LinkedIn messages and permission; **S5 results and spend** | On a real role, over two weeks: suggestions the owner would contact, each with a why; no off-limits, blocked or "stop" person ever suggested; the results-and-spend page answers "what did $X buy?" per strategy |
| **1b. Know the companies, search like a recruiter** (draft) | K1–K4 company knowledge; S7 staged search | On a real role: the owner agrees with the talent DNA and the starting list; sourced suggestions show their employers in facts; no company is researched twice; a widening proposal with numbers when a tier is exhausted |
| **2. Submit beautifully** | C1 coversheet (salary confirmed, permission checked); PDF export | The owner sends real coversheets and they need little editing |
| **3. Go live** | F1–F4; W1 | Security matrix green; a backup restored; a CV from the live site arrives in the platform |
| **4. The client desk** | C2–C5 | A real client uses it for one role end to end |
| **5. Learn and widen** | S3 hard-to-fill mode; S6 applications inbox; C6 introductions; W4 insights; I7 calibration | Per item |
| **6. The paid plan** | Track M | When the owner decides to open it |

Website polish (W2, W3) fits between phases; it touches only the website.

### Phase 1 in steps

1. **Exa adapter and a first look** (with a test key; a few cents): confirm what a people result returns and whether
   it can be limited by country; recordings for tests, like the model recordings; the key in `core/.env`
   (`EXA_API_KEY`), never in code or chat; spend in the ledger under its own budget.
2. **Market map**: suggested target companies with why, role variants, off-limits list; editable and versioned.
3. **Suggestions to contact**: the pool first, then Exa; public data only, each fact quoted; same identity, gates and
   matching as everyone; "why they fit" and "what we don't know".
4. **Runs on their own**: daily / weekly / continuous until the target; budgets per role and per desk, adjustable;
   run reports.
5. **Reaching them**: LinkedIn message drafts, contacted / replied / interested / stop; CV received; permission recorded.
6. **Results and spend**: the funnel with cost per stage, split by strategy, per role and for the desk; "this isn't
   working / this is" flags with their numbers.

## 10. Decisions

Taken by the owner, 2026-10-12:
1. **People found on the web:** public data only, as a guide to contact them; their CV, contact details and permission
   come from them. No extra GDPR machinery. (2026-10-13: no privacy line in messages either; the desk holds only public
   profile information.)
2. **Contacting them:** LinkedIn messages drafted by the desk, sent by the owner.
3. **Off-limits:** never source from active clients; a placed person's new employer off-limits for 12 months.
4. **Budget:** adjustable per role and for the desk, with results-and-spend statistics to judge every strategy.
5. **Modes:** daily, weekly, or continuous until the target; everyone found stays in the pool for future roles.
6. **Client desk:** one hiring manager per role, who may add interviewers from the same company only; live updates.
7. **Salary:** clients see the candidate's salary expectation once the owner has confirmed it.
8. **The paid plan** (Track M) is the ultimate goal, after an owner-only period.

Taken by the owner, 2026-10-13:
9. **Company research by price, value and accuracy:** Exa where it is cheaper and accurate enough (company profiles,
   by ID or confirmed by a key), Grok where accuracy matters most (section 4b). A company is never researched twice.
10. **Search like a recruiter:** talent DNA first, a growing target list searched in batches, widening only when the
    list is exhausted, and the owner decides each widening (section 4b, draft for approval).

Still open (needed by phases 2–4, not by phase 1):
- **System mail:** a transactional service for invitations, password resets and "new candidate" notices (recommended;
  the desk still never sends relationship messages).
- **The CV clients receive:** with contact details removed (recommended), or the original.
- **Interviews:** proposed times confirmed through the owner first (recommended); calendar connection later.
- **Applications inbox:** a dedicated address whose mail the desk may read in full.
- **Hosting:** an EU provider within roughly €30–80 a month; the domains to use.

## 11. Costs at a glance

- Exa: people search about $0.007 a query (10 results with text); monitors $0.015 a run; contents $0.001 a page;
  Websets (verified lists) in their own credits. A role searched weekly with ~20 queries and ~50 profiles read costs
  roughly $0.20–0.40 a week, plus small calls to read the profiles.
- Models: as today (cents per CV; drafts and profiles fractions of a cent).
- Hosting: €30–80 a month (F1); transactional mail: free tier to a few euros.

## 12. Risks, and how we hold them

- **Flooding the desk:** the target per role and the Inbox attention rule; runs stop at the target.
- **Wrong people at scale:** the same matching and gates as uploads; "unverified" until a call; dismissals teach S5.
- **Spending without knowing what works:** S5 from day one; budgets per role and desk; every paid call in the ledger.
- **Privacy and terms:** public data only; no searches by a person's name; no protected terms in any query (a
  mechanical check and a test, like blueprint AL-40); discovery through Exa, never scraping LinkedIn or harvesting
  GitHub contacts ourselves; "stop" is permanent.
- **A client seeing what they shouldn't:** the authorisation matrix (F2) is a gate, not a nice-to-have.
- **Giving away the moat:** a paying client never searches the owner's pool unless the owner offers it.

## 13. Ideas parked for later

- An **intake briefing** the moment a role is signed: market size, what each must-have costs in candidates, the
  salary range we see, questions that sharpen the brief. It turns the intake call into consulting.
- A **candidate link**: people update their availability and what they want, or correct their data, themselves ("Tell
  us once", as the website promises), arriving as their own facts.
- Referrals from placed people and from people we know at target companies.
- A Websets-based "verified list" mode for the hardest roles (criteria checked by Exa before we pay to read profiles).

---

Sources for the Exa facts above (checked 2026-10-12): [People search (changelog, 2025-12-19)](https://exa.ai/docs/changelog),
[pricing](https://exa.ai/docs/reference/pricing.md), [Websets overview](https://exa.ai/docs/websets/overview),
[Monitors API](https://exa.ai/docs/reference/monitors.md). Exa's monitors deliver only to a public HTTPS webhook, so
until the platform is hosted, our own background tasks run the schedule.
