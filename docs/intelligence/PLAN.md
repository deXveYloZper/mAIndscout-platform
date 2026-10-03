# Intelligence track: candidate strength, company intelligence, real matching

**Status:** accepted 2026-10-03 ([decisions](../decisions/2026-10-03-intelligence-track.md)); building from I1. Replaces the next slices in priority: no Slice 3 work until this track's first gate.
**Why this exists:** keyword matching (Slice 0-2) says *whether a CV mentions* what a job lists. It does not know who the person is, where they worked, or what makes someone great for *this* company. The owner's brief (2026-10-03) sets the bar: understand every candidate's career strength first, understand every company and its jobs first, then match.

---

## 1. The idea in one page

Three kinds of knowledge, built once and reused:

1. **Company intelligence** (shared, grows over time): for every company that appears in a CV or a job: domain, type (product / consultancy / agency / outsourcing), stage and funding history with dates, headcount over time, founding date, locations. Stored as time-bounded facts with sources. The 1,000th CV that mentions Revolut costs nothing to understand Revolut.
2. **Candidate career profile** (per person, before any job): relevant experience per role family, real seniority, progression, stability pattern, employer mix, domain exposure, contractor pattern, education, notable signals ("joined in the first 3 months", "promoted twice internally"). Every dimension with evidence and a plain-words reason. No vibes, no personality.
3. **Hiring profile** (per job, before any sourcing): the hiring company's profile + the job ad + the recruiter's intake (who the hiring manager wants, target companies, domain and stage preferences, contract or permanent, right to work).

**Matching** then compares 2 against 3 dimension by dimension (domain fit, stage fit, relevant seniority, stack, contract type, location and right to work, target-company alumni), giving a match tier with reasons. **Sourcing** becomes a structured query over profiles and the people-to-company graph ("we know 15 people who worked at Company A"), not a keyword scan.

```
 CV arrives ──► read facts (built) ──► resolve companies ──► research unknown/stale companies (parallel, cached)
                                              │                              │
                                              ▼                              ▼
                                     classify each job (role family, level, contract)  ──► career profile
                                                                                                │
 Job ad + intake ──► resolve + research hiring company ──► hiring profile ─────────► match (per dimension) ──► tier + gap table
                                                                   │
                                                                   └──► source from desk by profile + target companies
```

---

## 2. How this maps onto the blueprint (it is already the target)

| Owner's brief | Blueprint (`01`/`02`) | Status today |
|---|---|---|
| Company type, domain, stage, funding rounds, headcount over time | Company claims: `CompanyStageClaim`, `FundingClaim`, `TeamSizeClaim`, `DomainClaim`, `CompanyTypeClaim`, time-bounded (01 §F) | Not built (deferred to Slice 5) |
| Research companies with web search, cheaper as the base grows | Research Gateway F6: snapshots, company anchors, caching incl. absence, budgets | Not built |
| Joined early ("company founded March, joined June") | `JoinedAtStageClaim` (01 §F higher-order) | Not built |
| Progression, internal promotion, job-hopping | `PromotionClaim`, `CareerProgressionClaim`, `LeftBecauseClaim` | Not built |
| Relevant seniority by domain (restaurant → software) | `SeniorityA…` + trajectory archetype claim (F7.2) | Not built |
| General strength, not vs any job | F7 "General Strength" (archetype dimensions, coverage floor) | Not built |
| Matching to a job on many dimensions | F7 "Job Fit": categorical verdicts per requirement, code composes (E-i10); Environment Fit (stage, type, size) | Slice 1 gap table is the start |
| People tagged to companies; "who do we know at X" | Canonical company + `CareerStepClaim` re-keyed after company resolution | Company is plain text today |

So this track builds the blueprint's F5 cross-link layer, F6 and F7 now, in the order a desk needs them, rather than waiting for Slice 5.

---

## 3. Where I would do it differently, and why

1. **Bounded tasks, not free-roaming agents.** "Agents working in parallel" is right in spirit. In practice each "agent" should be a **task with one job**, a fixed prompt, a schema for its output, a budget and a cache, run by workers from a queue. A company-research task, a career-classification task, a hiring-profile task. They run in parallel and in dependency order (a career profile waits for its companies). Free-roaming agents are expensive, unrepeatable and hard to test.
2. **The model classifies; code judges.** Use the LLM for what only it can do: read messy text, classify a job title into a role family, find and summarise company facts with citations. Do the judging with **versioned rules** ("rubric"): years per role family, what counts as stable, how contractors are read, how tiers combine. Rules are cheap, repeatable, testable on golden cases, explainable to a client, and can later be calibrated from the desk's own outcomes (the pass reasons we now record). This is blueprint rule E-i10: no LLM-produced numbers.
3. **Strength as explained dimensions, then a band, never a magic number.** Each dimension gets a level (e.g. *strong / solid / developing / unclear*) with its evidence. An overall band appears only when enough dimensions rest on evidence (coverage floor). The vision's "refuses personality, culture-fit or vibe scores" stays; **career strength from evidence is allowed** ([ADR](../decisions/2026-10-03-career-strength.md)).
4. **University prestige and consultancy names need care.** Both are strong proxies for background and nationality (e.g. large Indian and Eastern European outsourcers). Using them blindly risks indirect discrimination, and recruitment AI is "high-risk" under the EU AI Act (human oversight, logging, bias testing). Proposal: show the recruiter the facts (institution, its tier, employer type) with context; **in automated tiers, weight what the experience was** (product ownership vs bench-and-staffing, length, progression) **rather than the brand name**; never hard-exclude on them; run a bias check on the eval set. The blueprint already keeps institution prestige out of automated similarity (F7.5).
5. **Job-hopping and consultancy time become questions as much as penalties.** As you said: layoffs and unfunded start-ups explain short stints. The profile marks the pattern ("6 employers in 10 years, 3 of them under 12 months") and adds a call question; companies we know shut down or had layoffs during the stint soften it automatically.
6. **The model's own memory is not a source for small companies.** For Revolut or EPAM, a model knows a lot; for a seed-stage Procure Ai it may invent. Company facts need **cited sources**: official registries where free (UK Companies House: incorporation date, status, industry codes), the company's own site, press, and web search with snapshots. Facts from model memory alone are kept but marked *unverified* and never decide anything on their own.
7. **Research only what matters, newest first.** A CV with 9 companies does not need 9 deep researches: research the last ~10 years and stints of 6+ months first; older and short stints get a light pass. This keeps cost per CV bounded.

---

## 4. System design

### 4.1 New and changed data
- **`company`** (blueprint D3): canonical name, aliases, website domain, registry ids, HQ country, `merged_into_id`. **Company claims** (time-bounded, with evidence): domain(s), type (product / consultancy / outsourcing / agency / public sector / non-profit), founded date, funding rounds (stage, date, amount if public), headcount points (value, as-of), status (active / acquired / shut down, with dates), locations, notable status (unicorn, public), tech stack if stated.
- **Company resolution:** `CareerStepClaim.company.company_id` (already in the schema) and `job.hiring_company_id` filled by a resolver: exact alias → normalised name + domain → registry match; ambiguous cases stay provisional and raise a review card (a wrongly merged company poisons every alumnus: blueprint F6.4).
- **Public vs private knowledge:** company facts from public sources live in a **shared public tier** (reused across all orgs, so compute falls as the base grows); what a desk knows privately (contacts, notes, "client's competitor") stays org-private.
- **Institution** (school/university) with a tier from a declared source; `EducationClaim.institution_id`.
- **Per-step classifications** (inferred claims, reviewable): role family (software engineering, data, product, design, sales, marketing, hospitality, …), level (junior / mid / senior / lead / head / founder), employment type normalised (permanent / contract / freelance / own company), domain of the work.
- **Career profile** (computed snapshot, like `score`): all dimensions with value, level, evidence ids, reason, confidence, rubric version, inputs hash; recomputed when facts or company knowledge change.
- **Hiring profile** (job side): `RequirementClaim` with strengths `must | strong_plus | nice | anti` (blueprint) and new categories: role family + relevant years, company stage/type preference, domain preference, target companies, contract vs permanent, location + right to work, stack.
- **`cost_ledger`**: every model and search call (task, model, tokens, sources, USD, subject). **`task` queue**: Postgres `FOR UPDATE SKIP LOCKED` with retries, priorities and per-org budgets (also moves CV processing out of the web request).

### 4.2 Tasks ("agents"), each bounded

| Task | When | Input → output | Model / tools | Cache |
|---|---|---|---|---|
| Read CV (built) | upload | text → facts | small model | by file hash |
| Resolve companies | after reading | raw names → company ids or review card | rules + registry lookup; model only to disambiguate | alias table |
| Research company | company unknown or a field stale | anchors → snapshots → company claims with citations | web search + small model extractor; registry API | per field TTL (founded: forever; funding/headcount: 6-12 months; absence: 1 month) |
| Classify career steps | after reading | each stint → role family, level, contract, domain | small model, batched per CV | by stint text hash |
| Build career profile | when its companies are ready | facts + company claims → dimensions | **code (rubric)** + small model for the 3-sentence summary only | by inputs hash |
| Build hiring profile | job created / intake saved | ad + intake notes + company profile → requirements | small model extractor + recruiter form | by inputs hash |
| Match | profile or hiring profile changed | profile × hiring profile → per-dimension verdicts, tier | code; model only for categorical judgements code cannot make (e.g. "is this stack equivalent?") | by both hashes |
| Source | thin queue | hiring profile → structured profile query + target-company alumni | SQL over profiles | none needed |

### 4.3 Career profile: how each dimension is decided
- **Relevant experience per role family:** each stint classified; overlapping stints merged; years counted per family. *Restaurant 4 years then software 6 years = 6 relevant years in software engineering* → level by rubric (e.g. 0-2 junior, 2-5 mid, 5-8 senior, 8+ senior/lead, adjusted by titles held).
- **Progression:** internal promotions (same company, rising titles), title trajectory across companies, scope growth (team lead, owner) when stated.
- **Stability pattern:** median tenure, employers per 10 years, share of stints under 12 months; *for contractors*, separate norms (a good contractor has 12+ month engagements; 2-3 month repeats are a different pattern). Context from company knowledge (shut down, layoffs during the stint) softens and becomes a call question.
- **Employer mix:** share of time at product start-ups / scale-ups / unicorns / large product companies / consultancies and outsourcers (from company type and stage at the time of the stint).
- **Early joiner:** join date vs founded date and headcount at join ("joined 3 months after founding, headcount ~10").
- **Domain exposure:** years per domain (fintech, procurement, healthtech, aerospace, …) from the company's and the role's domain; strongest domain named.
- **Contractor:** detected from titles, employment type, own company, overlapping clients; years contracting; typical engagement length. A contract job lights this up in matching.
- **Education:** institution, level, field relevance, tier (shown with context; see section 3.4).
- **Notable signals:** founder, first engineer, unicorn alumni, publications, open source, awards (when evidenced).
- **Output:** each dimension with level + reason + evidence; overall band only above the coverage floor; a short written summary generated strictly from those facts; questions for the call.

Your three engineers, as the rubric would read them (illustrative):

| | Relevant years | Stability | Employer mix | Progression | Reading |
|---|---|---|---|---|---|
| 1 | 10 software | 3 employers, long tenures | scale-ups / a unicorn | promoted internally | strongest: stable, progressing, product companies |
| 2 | 10 software | 6-7 employers | mixed | unclear | solid, frequent moves → question: why each move? |
| 3 | 10 software | long tenures | consultancies | client-dependent | solid engineer, less product ownership → question: which products did you own? |

### 4.4 Company intelligence: sources and trust
- **Order of sources:** our own database (free) → official registry (UK Companies House, free; other countries later) → web search with snapshots (paid per source) → model memory (free, marked *unverified*).
- Facts carry source authority and origin like every other claim; consequential facts (stage, funding, size) need a second independent source or a human look before they count as approved (blueprint F6.5).
- **Company page in the cockpit:** facts with sources and dates, people on the desk who worked there (with periods), jobs from that company; recruiter can correct or approve facts.

### 4.5 Hiring profile: Procure Ai as the worked example
From the company profile: seed-stage start-up, procurement domain, Germany + UK. From the ad: Node.js / TypeScript / React, agentic AI. From the recruiter's intake: early-stage start-up experience (strong plus), 0-to-1 product delivery (strong plus), procurement domain (strong plus, can substitute for start-up experience), lives in DE/UK or willing to relocate (must, asked), right to work in UK/EU without sponsorship (must, asked), target companies (optional list), contract or permanent (permanent).

### 4.6 Matching v2
- Per dimension a categorical verdict: **strong / partial / gap / deal-breaker / unknown / exceeds**, each with its reason and evidence (the gap table grows these rows).
- Rules encode desk wisdom as data, e.g. *domain match at a start-up can outweigh one level of seniority* (your fintech rule); *contract job → contractors with 12+ month engagements first*; *must-have domain specialism missing → do not submit* (today's InSAR rule).
- **Match tier** (e.g. *strong match / possible / unlikely*) composed by code from the verdicts, shown with its reasons; never a percentage; hidden below the coverage floor ("unclear: approve facts or ask").
- Location and right to work remain questions, never silent exclusions.

### 4.7 Sourcing v2
- Structured search over career profiles: role family + relevant years band + domain years + employer stage mix + contract pattern + location, in SQL (fast, free).
- **Target-company alumni:** "people who worked at Company A or B, and when", from the people-to-company graph, with last contact date.
- Results go through Matching v2 like any upload.

### 4.8 Cost: what it should cost and how it falls
Rough, to be measured in phase I1 (prices change; the ledger is the truth):

| Item | Estimate | Notes |
|---|---|---|
| Read a CV (today) | ~$0.007 | measured |
| Classify career steps | ~$0.002 per CV | one batched small-model call |
| Research one new company | ~$0.05-0.15 | depends on search provider pricing and sources used; registry calls free |
| Career profile | ~$0.001 | rules; model writes 3 sentences |
| Match one person to one job | ~$0 | rules; occasional small categorical call |
| **First CVs on an empty base** | ~$0.30-0.60 each | mostly company research |
| **Later, most companies known** | ~$0.02-0.05 each | research only new/stale companies |

Controls: per-task and per-CV budgets (research stops at a budget and marks "unknown"), per-org monthly cap, newest-and-longest stints first, cache with per-field freshness, cheap model by default and a stronger one only where it pays, and a cost page in the cockpit.

### 4.9 Trust, privacy, compliance
Every inferred dimension is a claim with evidence; nothing becomes official without the existing human gates; the recruiter can override any level or tier with a reason (recorded, and later used to calibrate). Searches never combine a person's name with sensitive attributes; research is about companies, not people. Company research is public information about organisations; person research stays out of scope. A bias check (does any tier correlate with proxies such as nationality-heavy employers or school prestige?) runs on the eval set before a rubric version is promoted. Erasure covers the new person-level data (profiles, classifications).

---

## 5. Build plan

Each phase ships with tests, docs, a real-file eval run, cost numbers, and a gate the owner declares. Rough effort in focused build days.

| Phase | What ships | Gate (owner declares) | Effort |
|---|---|---|---|
| **I1 Foundations** | `company` entity, aliases, resolver and review card; link career steps and hiring company; task queue + workers (uploads stop blocking the page); `cost_ledger` + budgets + cost page; company page with "people on the desk who worked here" | All 13 test files resolve their companies with no wrong merges on review; "who do we know at X" works; CV processing runs in the background; every call is in the ledger | 3-4 |
| **I2 Company intelligence** | research task (registry + web search with snapshots + extractor), company claims with sources and freshness, shared public tier, corrections/approvals in the cockpit, negative-result cache | For every company in the test CVs: type, domain, stage, founded date and headcount (where public) with citations; spot-check accuracy ≥ 90% on a hand-checked list; repeat run costs ~0 (cache) | 4-5 |
| **I3 Career intelligence** | step classification, relevant years per role family, level, progression, stability (contractor-aware), employer mix, early joiner, domain years, education + institution tier, notable signals; career profile snapshot; profile section in the cockpit; questions for the call | Golden profiles for the 11 CVs hand-checked by the owner; synthetic cases pass (restaurant→software; the three engineers; contractor with long vs short engagements; early joiner); | 5-6 |
| **I4 Hiring profile** | hiring company profile; recruiter intake (form + extraction from pasted notes); requirement strengths must / strong plus / nice / anti; target companies; contract vs permanent | Procure Ai and Catalyst hiring profiles reviewed by the owner and matching what the hiring manager would say | 2-3 |
| **I5 Matching v2** | per-dimension verdicts, rubric rules as data (incl. domain-over-seniority, contractor lightbulb), match tier with reasons, coverage floor, richer gap table, re-match on changes; replaces token triage (kept as a fallback when profiles are thin) | Owner ranks the 11 CVs for both jobs by hand; tiers agree on the clear cases and every disagreement is explained by a visible rule; no percentages anywhere; still no exclusion by location | 4-5 |
| **I6 Sourcing v2** | structured desk search by profile; target-company alumni; same matching path | "People who worked at X" and profile searches return correct sets on the test base; campaign rules unchanged (cap, target, no mail) | 2 |
| **I7 Calibration (ongoing)** | recruiter overrides and pass reasons feed rubric proposals (human-approved); shadow-run new rubric versions against the eval before promotion | First calibration review after ~50 real decisions | continuous |

Order matters: I1 → I2 → I3 can overlap partly (classification does not need companies); I4 can start after I2; I5 needs I3 + I4.

## 6. What does not change
The trust model (proposed → approved by a human), the gap table as the main view, no composite percentage, location never a silent exclusion, erasure with verify, pairs permanent, documentation with every change, the golden eval as the gate.

## 7. Roadmap effect
Slice 2's gate is ready but not declared; it can be declared now or left open. Slice 3 (Brief) and later slices wait until at least I5 is green: the Brief's questions get much better once profiles and hiring profiles exist. Recorded in `docs/decisions/` when the owner accepts this plan.

## 8. Owner's decisions (2026-10-03): all accepted, see [decisions](../decisions/2026-10-03-intelligence-track.md). Point 4 settled as: university rank is merit evidence and may carry weight.

### Original questions
1. **Accept this plan and its order** (I1 first).
2. **Web search provider** for company research: xAI (Grok's built-in web search, same key, simplest) or a dedicated search API; and a **monthly research budget** to start with.
3. **Shared public company tier across future client orgs:** yes (compute falls fastest) or keep everything per org.
4. **University tier source:** a public ranking you are comfortable with, or tiers you define; and agreement that prestige is shown to the recruiter but carries little or no automated weight at first (section 3.4).
5. **Career-strength ADR:** accept the clarification of the vision's "refuses" list ([ADR](../decisions/2026-10-03-career-strength.md)).
