# Next build: the talent-intelligence desk

**Status: DRAFT** 2026-10-12, for brainstorming with the owner. Nothing here starts until the owner approves it (and the
decisions in section 9 are taken). Written after a survey of what is built ([STATUS](../build/STATUS.md)).

---

## 1. The idea

One loop, run faster and smarter on every role than a competitor can by hand:

> **Sign a role → understand it → map the market → reach the right people, continuously → qualify → submit with a
> coversheet → the client acts in their own desk → every outcome teaches the engine → the next role is faster.**

"Talent intelligence" is what accumulates on the way: which companies hold the people, which adjacent domains
convert, what candidates want and earn, who moved where, which channels answer. That memory is the moat. Every build
below either feeds it or puts it in front of someone (the desk, a client, a visitor).

## 2. What we already have, and what is missing

| Step of the loop | Built | Missing |
|---|---|---|
| Understand the role | Hiring profiles (ad + hiring-manager notes + recruiter edits), research on the hiring company (kind, stage, size, domains, funding, base) | An intake briefing: how big the market is, what each must-have costs in candidates |
| Map the market | Target companies only when the ad or hiring manager names them; alumni counts on the desk | **Suggested target companies** (peers by domain and stage, adjacent domains, companies releasing talent) |
| Find people | Search in your own words over the desk's people; "Find more people" on a thin job (desk only, by hand) | **External discovery** (web, Exa), **always-on** runs, rediscovery triggers, inbound channels beyond upload |
| Judge | Matching v2 per requirement, bands, gap table, preferences from calls, coverage gate, client blocks | Off-limits companies (never poach from a client) |
| Talk | Brief with call questions, call transcripts → one bulk review, drafts into Gmail/Outlook, follow-ups a reply stops | Approaching people found on the web (often no email), consent to submit |
| Submit | Pipeline stage "submitted" with a note | **The coversheet** (why this person, evidence, what to probe, what they want) and a client-ready CV |
| Client | Client contacts and timelines, client rejection as a wall | **Everything client-facing**: accounts, their desk, interviews, feedback, statistics |
| Learn | Pair outcomes and reasons kept; I7 waits for real decisions | Source effectiveness (which companies, channels, messages work) |
| Be reachable | Runs on this machine only; the website's CV form saves to a local folder | **Hosting, HTTPS, outgoing system mail, the website ↔ platform seam** |

## 3. Principles carried over, and the three this plan changes

Kept, everywhere: belief is gated (machine proposes, a person approves); every fact has evidence; same path for
everyone (a person found on the web is identified, matched, gated and blocked exactly like an uploaded CV); never
protected characteristics, personality, culture or fit; where someone lives and works, never where they are from;
a band is never a number; a client rejection is a wall; erasure and suppression win over everything.

Changed, and each needs the owner's yes (section 9):

1. **Sourcing becomes always-on for open roles**, not only a button on a thin job. It stays bounded: it keeps a
   target number of strong people waiting for each role (say 5–8) within a budget, and finds more as the desk works
   through them. It never floods the Inbox (the vision's attention rule holds).
2. **People found on the web may be stored** (today an external source "needs a data-use decision first").
3. **Clients get their own desk** over the internet: the vision's "interview kits and scorecards: a later room" opens,
   and the platform must be hosted.

## 4. Track S: the sourcing engine ("the search that never sleeps")

**S1. Market map for each role** (the strategy, shown and editable before anything runs)
- *Target companies, with why:* direct peers (same domain, similar stage and size, in the role's countries);
  adjacent domains where the skills transfer (e.g. automotive ADAS ↔ robotics perception; flight software ↔
  safety-critical medical or rail; power electronics ↔ energy storage); companies **releasing talent** (layoffs,
  acquisitions, shutdowns, office closures, funding trouble in the last months); companies we already know people at.
- *Sources:* our company research (domain, stage, size, base), Exa company search ("Series B robotics companies in
  Germany"), the desk's alumni graph, and job discovery (blueprint Feature 11.1): public ATS job boards (Greenhouse,
  Lever, Ashby, Workable) show which companies are hiring the same profile, so we know who competes for this talent.
- *Role variants:* the titles and kinds of work that mean the same thing ("embedded software engineer" ≈ "firmware
  engineer" ≈ "flight software engineer"), from the shared role families.
- *Exclusions:* off-limits companies (the client itself and other active clients; optionally a placed person's new
  employer for 12 months), client blocks, suppression.
- The recruiter pins, removes or adds companies; the plan is versioned, so we know which version found whom.

**S2. Discovery adapters** (behind the existing `find` interface; background tasks, never in a request)
- **Exa people search** (`category: "people"`, 1B+ public profiles, LinkedIn and the wider web; about $0.007 per
  search with 10 results and their text). Queries are built from the plan: role variant × target company, role ×
  country × domain. A query names roles and companies, **never a person** (no digging on someone by name).
- **Exa publication research** for research-heavy roles (perception, controls, ML): people with their papers,
  collaborators and research areas. Strong evidence for deep-tech hires that a LinkedIn title never shows.
- **Engineering footprints** found through Exa: personal sites, open-source projects, conference talks. (GitHub's
  [acceptable use policies](https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies),
  section 7, bar using its information for unsolicited emails or selling it to recruiters: a GitHub profile can point us
  to a person, never be a contact source.)
- **Rediscovery first, it is free:** the desk's own people, silver medallists (late-stage for another client), people
  whose preferences or notice window now fit, people a stale check would refresh.
- Every result becomes a person through the same identity rules (no duplicate if we already know them; a known person
  found again may show a newer job, proposed as a fact with the page as evidence), then coverage gate, off-limits,
  client blocks, suppression, matching. Web evidence is thin, so they mostly arrive as "promising, unverified":
  each with **why we think they fit** (quotes) and **what we don't know** (questions for the first call).

**S3. Always-on runs**
- Each open role has a cadence (weekly by default, daily when urgent), a waiting-list target, a monthly budget, and
  stops by itself when the role is filled, paused or closed.
- A run goes cheapest first: rediscovery → people we know at target companies → web discovery (only queries and
  profiles not seen before) → the talent-release radar (news about target companies).
- **Run report**, one screen: companies searched, people found, new vs already known, refused by the gates, strong ones
  waiting, cost. The same report, aggregated, is what the client sees as "this week's search" (C4).
- **Hard-to-fill mode.** When a role has had no submission for N weeks, or the waiting list stays empty, the engine
  proposes widening moves with numbers: "12 people in DE/AT/CH meet all must-haves and we have reached 10; dropping
  'Rust' as a must → 40; opening the UK → 25; adjacent domain automotive → 55." The recruiter picks one, or takes the
  numbers to the client: a calibration conversation backed by evidence, which most agencies cannot have.

**S4. Reaching the people found**
- First-contact drafts from the person's public evidence and the role's public facts only (the outward projection we
  already have), with the GDPR Art. 14 notice line and an easy opt-out.
- Most web-found people have a profile link, not an email: the draft is written for a LinkedIn message (copy, send
  from LinkedIn, mark contacted); email when they publish one; paid contact lookup only if the owner opts in (S-decision 2).
- Replies pasted or arriving by email are read like a call transcript: "interested", "not now", "stop" (writes the
  suppression list), and new facts.

**S5. Learning what works**
- A funnel per source, company tier, query and message: found → approached → replied → screened → submitted →
  interviewed → placed. Shown per role and across the desk.
- The plan reorders itself on that evidence (companies that never reply drop, adjacent domains that convert rise),
  and every learned change shows the outcomes that motivated it. No learned change may use a proxy for a protected
  characteristic (blueprint F10.9).
- Over time this builds the desk's **domain transfer map** from real placements: where hires actually came from.

**S6. Inbound channels** (not sourcing, but the same intake)
- The website's applications and CVs go straight into the platform (F4).
- An applications inbox (e.g. apply@maindscout.com) for LinkedIn job-ad applicants and job boards: attachments read,
  the person put on the role, the channel recorded. LinkedIn's direct ATS connection is for partners only; forwarding
  is the practical route. Reading message bodies needs a wider mailbox permission than today's (decision 9).

## 5. Track C: the client desk

**One truth.** The client desk is a window onto the same pipeline, never a copy. A client's click writes to the same
pair (party: client), lands on the recruiter's timeline and Inbox; a recruiter's move shows on the client's side.

**What a client never sees:** bands, match tiers, internal notes, the Brief, people not submitted to them, other
clients, and candidates' contact details (the recruiter introduces; this protects the candidate and the fee).

**C1. The coversheet** (built first, on the recruiter's side, useful before any hosting as a branded PDF)
- Who: current role, location and mobility, notice, salary expectation and availability (each only when the candidate
  agreed to share it).
- **Why I'm putting them forward:** the role's must-haves and strong pluses, one line each, with the evidence (CV or
  call, quoted) in client words; drafted from approved facts and match verdicts, edited by the recruiter.
- **What to explore in interview:** the open points (an unverified must-have, a gap, a question the call raised)
  written as questions for the hiring manager. A tailored interview guide per candidate: rare, and valued.
- What they want, and how this role fits it (from calls).
- The recruiter's own note; the CV attached (decision 7: original, or with contact details removed).
- Frozen at submission (what the client saw is kept), with the same mechanical check as drafts (no internal words).
- **Consent to submit** is recorded before submission (who, which client, which role, when): the website promises
  "you decide each introduction".

**C2. Client accounts and access**
- A client company becomes an account; its people get a `client` role scoped to that company and the roles they are
  named on. Invited by link like members today; optional two-step codes.
- A **share link** for a single candidate (view only, expiring) for clients who will not sign in.
- An access log (who viewed or downloaded what); CVs downloaded carry a watermark ("submitted by mAIndscout to
  <client> on <date>"); access ends some weeks after a role closes.

**C3. The client's desk** (polished, works on a phone, in the website's engineering look)
- Home: their roles with stage counts; "waiting for your feedback" with gentle timers.
- Role: a board (submitted → interviews → offer → hired; declined), candidate cards.
- Candidate: the coversheet, the CV, interviews and feedback so far.
- Actions: invite to interview, decline (a reason plus their words: becomes the client-block wall and a learning
  label), ask a question (reaches the recruiter, may become a Brief question for the candidate), give feedback after
  each interview (structured on the role's requirements; no personality or culture fields), make an offer.

**C4. Statistics and the weekly report**
- Per role and across roles: time to first submission, submissions per week, interview and offer rates, time in
  each stage, why candidates were declined.
- This week's search, from S3's run reports, in aggregate: companies searched, people approached, replies, the market
  map's size. Transparency is the differentiator: the client sees the work behind every submission.

**C5. Interviews**
- First version without calendar access: the client proposes times (or shares their booking link), the recruiter
  confirms with the candidate, everyone sees the booked slot, and calendar files are offered for download.
- Later, with the owner's yes: Google / Microsoft calendar connection (free/busy, creating the event).

**C6. Anonymised profiles and the two-stage introduction** (blueprint Feature 11; today's Slice 5 BD item)
- "Work before name" profiles shared with clients and prospects; "request an introduction" asks the recruiter, who
  asks the candidate; on their yes the full coversheet opens. The same rule the website states.

## 6. Track F: going live (needed by the client desk and by the website's CV form)

- **F1. Hosting** in the EU (GDPR): the Docker setup from 2026-10-12 is the seed; managed Postgres with backups that are
  restored in a test, encrypted file storage, HTTPS, separate domains (e.g. desk.maindscout.com, clients.maindscout.com),
  secrets outside the code, monitoring and alerts. Rough cost: €30–80 a month.
- **F2. Security pass before anything is public:** an authorisation test matrix (a client can never reach another
  client, a recruiter-only route, or a person not submitted to them), secure cookies, content security policy,
  dependency audit, rate limits on public routes.
- **F3. Outgoing system mail** (password resets, invitations, client notifications) through a transactional service.
  The desk still never sends relationship messages itself (decision 6).
- **F4. The website ↔ platform seam:** CVs and applications from the website into the platform (server to server,
  authenticated); published roles from the platform to the website; anonymised showcase profiles (human-approved).
  Until this exists, a CV sent from the hosted website would be lost.
- Privacy paperwork: notices for candidates and clients, the Art. 14 text, a retention schedule, a data-processing
  agreement for clients. Worth one review by a lawyer before the client desk opens.

## 7. Track W: the website (the window to the world)

- W1. Live roles and the CV form through the platform (F4); the anonymised talent showcase (C6).
- W2. A phone polish pass across every page (the opening's overflow was found only on a phone), plus speed and
  accessibility checks.
- W3. The two missing domain drawings (semiconductors, energy), so all seven chapters can be public.
- W4. **Insights from the market maps**, aggregated and anonymised ("Embedded engineering talent in DACH, Q4 2026"):
  the platform's intelligence becomes the business's proof and its inbound.
- W5. Privacy-friendly analytics: which pages clients and candidates actually use.

## 8. Order of work

| Phase | What | Why now | Gate (the owner declares) |
|---|---|---|---|
| **1. Find them** | S1 market map; S2 Exa + rediscovery; S3 always-on with run reports; S4 first-contact drafts (LinkedIn copy, email) | Faster sourcing on real roles is the first edge, and it runs on this machine | On a real role: a weekly run brings at least 10 new people in coverage, each with a why; the owner would approach most; no off-limits, blocked or suppressed person ever appears; cost under about $1 a role a week |
| **2. Submit beautifully** | C1 coversheet and consent; PDF export | Usable with clients by email at once, before hosting | The owner sends real coversheets and they need little editing |
| **3. Go live** | F1–F4; W1 | Needed by the client desk, and by the website's CV form in production | Security matrix green; a backup restored; a CV from the live site arrives in the platform |
| **4. The client desk** | C2–C5 | The client experience competitors don't have | A real client uses it for one role end to end |
| **5. Learn and widen** | S5 learning; S3 hard-to-fill mode; S6 applications inbox; C6 two-stage introductions; W4 insights; I7 calibration | Needs real outcomes to learn from | Per item |

Website polish (W2, W3) can be fitted between phases; it touches only the website.

## 9. Decisions for the owner (with my recommendation)

Before phase 1:
1. **Storing people found on the web:** yes, as people with web evidence; the GDPR Art. 14 notice in the first message
   (and within a month at the latest); **people never contacted are deleted after 60 days**; an objection writes the
   suppression list. *Recommended.*
2. **Contact details:** start with LinkedIn messages written by the desk and sent by you; paid email/phone lookup
   (Exa's partners: about $0.02 an email, $0.07 a phone) only later, per role, if replies are too slow.
3. **Off-limits:** never source from active clients; a placed candidate's new employer off-limits for 12 months.
   *Standard agency practice; recommended.*
4. **Budget:** a cap per role per month (suggested $5 for web search and reading; a typical week costs well under $1)
   and a desk-wide monthly cap, both in the cost ledger.
5. **Cadence:** weekly by default, daily for roles you mark urgent.

Before phases 2–4:
6. **System mail:** allow a transactional mail service for invitations, password resets and client notifications.
   The rule "the desk never sends relationship messages" stays.
7. **What clients see:** a named coversheet and CV only after the candidate's recorded yes; contact details never;
   the CV with contact details removed. Salary expectation only when the candidate agrees.
8. **Interviews:** start with proposed times confirmed through you; calendar connection later.
9. **Applications inbox:** a dedicated address whose mail the desk may read in full (a wider permission than today's
   drafts-only mailbox).
10. **Hosting:** an EU provider within roughly €30–80 a month; the domains to use.

## 10. Costs at a glance

- Exa: people search about $0.007 a query (10 results with text); monitors $0.015 a run; contents $0.001 a page;
  Websets (verified lists) are billed in their own credits. A role searched weekly with ~20 queries and ~50 profiles
  read costs roughly $0.20–0.40 a week, plus small model calls to read the profiles.
- Models: as today (cents per CV; drafts and profiles fractions of a cent).
- Hosting: €30–80 a month (F1); transactional mail: free tier to a few euros.

## 11. Risks, and how we hold them

- **Flooding the desk:** the waiting-list target and the Inbox attention rule; runs stop at the target.
- **Wrong people at scale:** the same matching and gates as uploads; "unverified" until a call; learning from dismissals.
- **Privacy:** minimal data, the 60-day rule, Art. 14 notices, suppression first, no searches by a person's name,
  no protected terms in any query (a mechanical check and a test, like blueprint AL-40).
- **Terms of service:** discovery through Exa, never scraping LinkedIn or harvesting GitHub contacts ourselves.
- **A client seeing what they shouldn't:** the authorisation matrix (F2) is a gate, not a nice-to-have.
- **Spend:** caps per role and per desk, every paid call in the ledger, tests on recordings.

## 12. Ideas parked for later

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
until the platform is hosted, our own background tasks run the schedule. To confirm with a test key before phase 1:
the fields a people result returns, and whether results can be limited by country.
