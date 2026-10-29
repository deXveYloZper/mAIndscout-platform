# Status

Single page: what exists, what is next. A–D sign-off and accepted holes: [../decisions/2026-10-02-milestones-a-d-signoff.md](../decisions/2026-10-02-milestones-a-d-signoff.md). Slice gates are declared green by a human only, in [../decisions/](../decisions/).

**Slice 0 gate: GREEN**, declared by the owner on 2026-10-02 ([decision](../decisions/2026-10-02-slice-0-gate.md)). Slice 1 may start.

**Slice 1 gate: GREEN**, declared by the owner on 2026-10-03 ([decision](../decisions/2026-10-03-slice-1-gate.md)).

**Slice 2 gate: GREEN**, declared by the owner on 2026-10-04 ([decision](../decisions/2026-10-04-slice-2-gate.md)).

**Slice 3 gate: GREEN**, declared by the owner on 2026-10-04 ([decision](../decisions/2026-10-04-slice-3-gate.md)). Slice 4 (live desk) is unlocked.

**Slice 4 gate: GREEN**, declared by the owner on 2026-10-05 ([decision](../decisions/2026-10-05-slice-4-gate.md)). Slice 5 (Depth) unlocks once a desk is also running live jobs ([plan](../slice-5/PLAN.md)).

**Now:** the [intelligence track](../intelligence/PLAN.md), accepted 2026-10-03 ([decisions](../decisions/2026-10-03-intelligence-track.md)).

| Phase | What | State |
|---|---|---|
| I1 | Companies, linking, background tasks, cost ledger | **gate GREEN** 2026-10-03 ([decision](../decisions/2026-10-03-i1-gate.md)) |
| I2 | Company research (Grok, targeted facts) | **gate GREEN** 2026-10-03 ([decision](../decisions/2026-10-03-i2-gate.md)) |
| — | Coverage gate (archive outside EU/EEA/UK/CH/US/CA; light research for big consultancies) | built 2026-10-03 ([ADR](../decisions/2026-10-03-coverage-gate.md)) |
| I3 | Career profiles | **gate GREEN** 2026-10-04 ([decision](../decisions/2026-10-04-i3-gate.md)) |
| I4 | Hiring profiles | **gate GREEN** 2026-10-04 ([decision](../decisions/2026-10-04-i4-gate.md)) |
| I5 | Matching v2 | **gate GREEN** 2026-10-04 ([decision](../decisions/2026-10-04-i5-gate.md)) |
| I6 | Sourcing v2 | **gate GREEN** 2026-10-04 ([decision](../decisions/2026-10-04-i6-gate.md)) |
| I7 | Calibration from real decisions (band changes, pass reasons) | ongoing; first review after about 50 real decisions |

**Access** ([plan](../access/PLAN.md), approved 2026-10-05): built 2026-10-05 ([access](components/access.md)). Personal sign-in with optional two-step codes, desks and roles, members page; the shared operator token and `X-Actor` are gone. Hosting and HTTPS are a separate decision; until then everything listens on this machine only.

**Calls** ([plan](../calls/PLAN.md), approved 2026-10-06): built 2026-10-06 ([calls](components/calls.md)). Call transcripts into one bulk-approved Call review; what people want in matching and sourcing; approve all from a CV. Reading a transcript needs model credits; first real-model run 2026-10-08 (three reader fixes followed).

**Since Calls** (2026-10-06 to 10-08): fewer contact questions, merging two records of one person ([merge](components/merge.md)), "Same company?" asked on the call, company sizes read correctly, and the golden eval run on 43 real files: RED on two known cases (an image-only CV that needs a vision reader; Veljko's oracle, waiting on the owner) ([golden eval](components/golden-eval.md)).

**Slice 4 (closed):** ATS core and import ([plan](../slice-4/PLAN.md)): rescoped by the owner (we are the source of truth; import 100 candidates / 25 clients free, more as paid analysis at compute cost + 90%, [decision](../decisions/2026-10-04-source-of-truth-and-imports.md)); plan approved 2026-10-04.

| Step | What | State |
|---|---|---|
| 1 | Relationship memory | built 2026-10-04 ([relationship-memory](components/relationship-memory.md)) |
| 2 | Full pipeline, submissions, client feedback and block | built 2026-10-05 ([pipeline](components/pipeline.md)) |
| 3 | Freshness | built 2026-10-05 ([freshness](components/freshness.md)) |
| 4 | Import (100 / 25 free, more paid) | built 2026-10-05 ([imports](components/imports.md)) |
| 5 | Drafts, Gmail / Outlook drafts, sent and reply detection, follow-ups a reply stops | built 2026-10-05 ([messages](components/messages.md)); live mailbox needs the [app registrations](connections/mailbox-setup.md) |

All five Slice 4 steps built; gate declared GREEN 2026-10-05.

**Next build** ([plan](../next/PLAN.md)): phase 1 approved by the owner 2026-10-12 ("go"); phases 2–6 are drafts.

| Phase | What | State |
|---|---|---|
| 1 | Sourcing engine: market map, pool + Exa, runs with modes and budgets, LinkedIn first messages and permission, results and spend | built 2026-10-12 ([engine](components/sourcing-engine.md), [web discovery](components/web-discovery.md), [results](components/sourcing-results.md), [permission](components/permission-and-stop.md), [radar](components/talent-release-radar.md), [decision](../decisions/2026-10-12-sourcing-engine.md)); not yet run on a real role; gate: two weeks on a real role, declared by the owner |
| 1b | Know the companies (identity keys, Exa profiles, Grok depth, cross-check) and search like a recruiter (talent DNA, tiers, batches, exhaustion, snowball, widening) | built 2026-10-13 ([company knowledge](components/company-knowledge.md), [strategy](components/sourcing-strategy.md), [decision](../decisions/2026-10-13-company-knowledge-and-strategy.md)); not yet built for a real role |
| 1c | From suggestion to conversation: suggestions stay off Priority until the owner decides, one-click triage with undo, the contact track, reaches, LinkedIn's emails | built 2026-10-13 ([outreach](components/outreach.md)); LinkedIn email reading tested with a fake mailbox, switches on when the owner connects @maindscout.com |
| 1d | Evidence for strong matches: alternatives in an ad are one requirement ("React and/or Node.js"), employer evidence from a company's own job adverts (a skill nobody wrote down is "likely", never strong on its own), and an automatic deeper look at strong web finds (their links, their name with their company) | built 2026-10-17 ([employer evidence](components/employer-evidence.md), [evidence checks](components/evidence-checks.md), [decision](../decisions/2026-10-17-evidence-for-strong-matches.md)) |
| 1e | Understand the hire ([decision](../decisions/2026-10-19-understand-the-hire.md), approved 2026-10-19): A sizes, real jobs, a kind of company counted in the role's own work, "not from" with a 6-month window, and `match-eval` to measure every rule change before it goes live; B role brief and grouped requirements; C kind of work, level and move check; D the new search; E less text; F why they might move | A built 2026-10-19 ([match eval](components/match-eval.md), [matching](components/matching.md), [career profiles](components/career-profiles.md)); B built 2026-10-19 ([role brief](components/role-brief.md), [hiring profiles](components/hiring-profiles.md)): first briefs read for Procure AI and Bonaventura, reviewed by the owner (one correction: team "small team"); E built 2026-10-20 after the owner's word on its preview ([outreach](components/outreach.md), [hiring profiles](components/hiring-profiles.md)): the suggestion card in a few lines with LinkedIn one click away, the hiring profile in three groups with the brief, its questions answerable on the page, and Confirm all; C built 2026-10-21 (the move check, level, specialists, competitors by size; [matching](components/matching.md)); D built 2026-10-21 (competitors researched on the web, search on to 15 strong; [sourcing strategy](components/sourcing-strategy.md)); next F |
| 2–6 | Coversheet, going live, client desk, learn and widen, paid plan | drafts |

**Since the Ferrari role** (2026-10-22 to 10-27): the [activity log](components/activity-log.md); the talent map, company segments and company lines with an optional focus ([company knowledge](components/company-knowledge.md), [sourcing strategy](components/sourcing-strategy.md)); years and side for the role ([matching](components/matching.md)); people clearly out not read ([sourcing engine](components/sourcing-engine.md)); two-column CVs read in order, doubtful pages flagged for a person ([ingestion](components/ingestion.md)). The [core-work reader](components/core-work-reader.md) is built (2026-10-28) after its step-by-step measurement on Ferrari ([measurement](../evals/2026-10-27-core-work-reader-ferrari.md)): the role's lines confirmed by a person, everyone strong or possible ordered within their band by what their own words show. The API puts Ferrari's Sourcing tab together in under a second (2026-10-28, [performance](components/performance.md)). The search learns from its own results (2026-10-28, measured on three roles before it was built: barren titles retire, a giving company is searched deeper first; [sourcing strategy](components/sourcing-strategy.md), [decision](../decisions/2026-10-28-search-that-learns.md)). The architecture review's fixes (2026-10-28): no route holds up the others, every button named in the activity log with the reason for a refusal, the clocks no longer silent ([decision](../decisions/2026-10-28-architecture-review.md)).

**Next:** run live jobs on the desk, starting the sourcing engine on a real role (the owner reviews its market map, then presses "Search now"). Before it is reachable beyond this machine: hosting and HTTPS (a separate decision; sign-in itself is built). Slice 5 and I7 calibration follow from real use.

Slice 3 (the Brief, closed): built 2026-10-04 ([brief](components/brief.md)).

Slice 2 (sourcing feeder, closed):

| Step | What | State |
|---|---|---|
| 1 | Desk adapter, campaigns (cap / target / human stop), same triage, cockpit "Find more people" | done 2026-10-03 |
| 2 | Slice 2 gate checks in the eval | done 2026-10-03; **gate GREEN** 2026-10-04 |
| later | External adapter (e.g. GitHub profiles) | not started: needs a data-use decision |

**Slice 1** (defendable match, closed)

| Step | What | State |
|---|---|---|
| 1 | Richer job requirements; mobility as three facts | done 2026-10-02 |
| 2 | Gap table per person on a job | done 2026-10-02 |
| 3 | Re-triage when a fact the band depends on is approved | done 2026-10-02 |
| 4 | Pair states; a pair can never be deleted | done 2026-10-02 |
| 5 | Reserved score breakdown shape; coverage floor | done 2026-10-02 |
| 6 | Slice 1 gate evidence in eval and e2e | done 2026-10-03; gate declared GREEN |

Slice 0 (ingest + job-first triage) is closed ([handoff](../slice-0/HANDOFF.md), [gates](../slice-0/GATES.md))

| Milestone | What | State |
|---|---|---|
| A | Vendor `slice0/`, reconcile tests green | **signed off** 2026-10-02 |
| B | Persistence | **signed off** 2026-10-02 |
| C | Upload + text layer | **signed off** 2026-10-02 (HTTP route moved to E) |
| D | Extract, span check, commit, triage | **signed off** 2026-10-02 (HTTP route moved to E) |
| E | HTTP API + cockpit | **signed off** 2026-10-02 ([record](../decisions/2026-10-02-milestone-e-signoff.md)) |
| F | Erasure + verify | **signed off** 2026-10-02 (with the gate) |
| G | Golden folder | **signed off** 2026-10-02 (with the gate): eval GREEN |

How to run everything locally: [connections/cockpit-api.md](connections/cockpit-api.md).

Also pending: website ↔ platform contracts ([connections/website.md](connections/website.md)).
