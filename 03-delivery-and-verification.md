# mAIndScout — Blueprint v4
## 03 — Delivery & Verification

*v4.2: Slice 0 in §2 and 05 §D is the implementation contract. The rest of this file is the target eval catalogue, roadmap, and register.*

---

## §1. Evaluation harness & golden-set catalogue

Built **before the agents**, as an explicit blocking gate (05 §D), not as one bullet among a dozen infrastructure tasks — a multi-agent system without a regression suite cannot be safely iterated. `make eval`, one command; every run stored and trended; no prompt, model, graph, weight, policy, or projection change ships without a green run. Claim-type JSON Schemas and `reconcile(observations) -> view` must go green under `pytest` with no Docker before extractors exist. This is simultaneously the accuracy-monitoring evidence an AI Act file will ask for; it is not itself conformity.

**Golden set:** 20–50 real anonymized profiles with human-verified claim graphs, expected scores ± tolerance, expected resolutions. **Mandatorily including degraded and adversarial inputs** — a golden set of clean documents tests a system that will never run.

**Standing metrics:** claim precision/recall by type · hallucination rate (**typed-tier** span-fail count only — 05 RA-01; paraphrase-tier pass rate is a separate series) · injection-event handling · stint-dedup correctness across multi-source arrivals · reconciliation correctness on planted conflicts · entity-resolution precision/recall (name variants; hard negatives) · vetoed-claim precision (critic, after Slice 0) · per-model calibration curves · completeness accuracy · narrative faithfulness · **ranking stability under document thinning** (same candidates, full vs degraded inputs — orderings must match; after ranking exists) · embedding demographic-leakage probe (after embeddings exist) · end-to-end latency & cost per profile (Slice 0 already fails a golden profile over the cost cap).

**Case catalogue** (each traces to a specific reviewed failure; grouped by feature):

*Ingestion:* designed CV with corrupted text layer & annotation-only LinkedIn · agency-retyped CV (`transformed_by_third_party`; stripped contacts) · multi-subject shortlist PDF (splitter) · misclassified document (recovery + re-dispatch) · non-English CV · undated document (`as_of` inference; stated-duration anchor).
*Identity:* agency footer contacts (attribution + frequency tripwire) · conflicting deterministic keys · common-name/large-employer hard negative · name-variant merge (hyphenated/married surname) · merge → unmerge round-trip (redirect reversibility on claims **and** pairs — 05 RA-03) · SameAs with two conflicting in-flight pair states opens a Decision · `possible_ocr_identifier` must not become a match key · suppression-registry hit blocks re-ingestion.
*Claims:* boomerang employee (two stints, no fusion) · same-stint from three candidate-origin sources (confidence must **not** stack) · registry corroborating self-report (must stack) · approved-view revision on fresher conflicting source (diff proposal, no silent mutation) · gap filled by new stint (computed-claim auto-supersession) · temporal-succession contradiction (Series A→B: bounded, both approved) · reprocessing idempotency (no twins).
*Review:* trickle arrival after seal (next batch) · policy recall round-trip (sized, executed) · derivation bundle with one rejected parent (approval blocked) · audit-sample overturn → tightening proposal.
*Agents:* fabricated-span claim (blocked at commit, logged) · unserved-citation output (rejected) · budget exhaustion (degradation order honored; `budget_truncated`) · model swap (auto-approval suspended until recalibration) · non-person document to candidate extractor (bail-out Decision).
*Research:* planted/injection page (flagged, quarantined) · same-name-different-company anchor miss (discarded pre-extraction) · own-LinkedIn corroboration (must **not** raise confidence) · volatile refresh 15→120 (trajectory, not contradiction) · negative-cache hit (no repeat spend) · rate-limit park (no retry storm).
*Scoring:* cache-staleness (same claims six months later → refresh) · archetype flip (revision proposal, not silent jump) · coverage below floor (no composite shown) · proposed deal-breaker (flagged, **not** hidden) · leakage probe as standing gate · geographic corridor stint (auto-approval blocked; pre-submission gate) · footprint-suppressed flag (large multi-entity employer, distant candidate → **no** flag) · moderate flag (small company, large timezone gap).
*Pipeline:* concurrent-matching race (one pair row) · requirements revision (matched expires; interviewing flagged) · job-filled cascade with silver-medalist re-match · client-scoped re-submission block · competing-offer fan-out · awaiting-party timer reset on activity.
*Brief:* answered item survives regeneration (no resurrection) · inheritance (answered once, resolved everywhere) · inline capture → born-approved assertion → score refresh.
*PA/Learning:* reply mid-sequence (all automation halts) · "stop" writes suppression · heavily-edited draft (must **not** count toward promotion) · biased-override cluster (proposal blocked by suite) · pending-queue pull (undo real).
*Business development:* small-market teaser (Berlin seed climate-tech — fixed generalization + human review, 05 RA-05; corpus cardinality is a tuning aid not a ship gate) · rich-profile spec (must not be shippable on pool-size alone) · current-employer/ecosystem exclusion from spec recipients · active-pipeline conflict (candidate at `interviewing` receives **no** teaser — no self-competition) · staleness-triggered eligibility (fresh profile skipped, stale one selected) · cold-stale profile (two-step reconnection template, not one-step teaser) · "I'm at NewCo now" reply (fresh stint claim, old stint bounded, NewCo research triggered) · discovered job never enters client pipeline.
*Scale:* matching fan-out executes as SQL (E-i14 — an application-side loop must fail the test) · partitioned-table migration exists as a later eval case triggered by a measured signal (05 RA-06), not as a Phase-0 fixture · every sweep cursor-based (no full-scan) · 1M-row synthetic pool coarse-fit latency budget (after matching exists).
*2026-09 folder / 05 §E:* text-layer identifier ≠ visible identifier (`possible_ocr_identifier`, not an identity key) · JD with elapsed process dates (`job_process_stale`) · three-factor mobility × EU candidate outside the stated countries (Brief, not auto-exclude) · non-EU × no-sponsorship (UNKNOWN / Brief, not a numeric penalty) · overlapping paid-looking stints stay separate + AL-09 both sides · education ∩ employment is not a computed fail · vendor/product names are not employers · zero-domain job emits no composite · `exceeds_expectations` on “all levels” · photo CV yields zero appearance claims · JD footer contacts are not candidate keys · brand vs legal strings (CATALYST/PCI; Orion/Ericsson).
*Compliance:* erasure round-trip ending in the verification query (zero survivors) · Art. 14 sweep Decision at the deadline.

---

## §2. Phase plan

**Slice 0 (05 §D — the implementation contract; replaces the former “Phase 0 weeks 1–2” as what may be coded first).** Blocking gate, no agents: JSON Schemas for six claim types + `flag_type_registry` seed + `reconcile()` fixtures under `pytest` with no Docker. Then: monorepo; compose stack (Postgres + pgvector + ltree, MinIO; Temporal and LangFuse are **not** required); Slice-0 subset of 01 §D (`org_id`, documents, artifacts, `document_subject`, claims/observations/evidence, runs/manifests, `flag_type_registry`, cost ledger, activity, suppression, single-subject erasure); five large tables **unpartitioned** (05 RA-06); sweeps cursor-based from the first one; text-layer ingestion + link harvest + `as_of` + `needs_vision` flag (no vision model); live-query identity (deterministic keys only); typed span check; `approved_view` + three review renderers (diff, duplicate-stint, contradiction); inbox = `created_at` + blocking Decisions; erasure + verify on single-subject docs; single-user real auth. Golden cases: 05 §E plus the degraded-input subset of §1 that Slice 0 can express.

**Phase 0 / foundations (target infra, not the first milestone).** Remaining 01 §D columns (pairs, brief items, policies, anticipatory BD columns `job.origin` / company `relationship_state`) land as slices need them. Partitioning lands on a measured trigger. Temporal lands when a real retry/timeout exists.

**Phase 1 — Operator Daily Driver, split (05 D3).**
*Implemented (Slice 1), not calibrated:* upload supported document → identity-resolved (attribution, deterministic + conflicting-key Decisions; three-band fuzzy is later), extracted (staged, tier-validated, rubric confidence), company-enriched (registry-first, snapshots-as-documents with RA-04 TTL, anchors), reconciled claims in a sealed-batch Decision Inbox → tiered review with diffs/bundles/duplicate-stint choices → official score from approved claims (dumb weights, coverage count, AL-18 shape reserved, no composite below floor) → pairs created (permanent, RA-03-aware) with structured outcomes → Brief items + inline capture. Includes: AL-02 job-process staleness; AL-22 three-factor mobility; basic splitter; job-level resolution; one registry provider. No provisional-score inbox ranking in Slice 0–1.
*Calibrated (Slice 2):* 03 §5 items 1, 3, 6 measured on the golden set. Only then is the claims engine + official score allowed to be called done.
*Full Phase-1 target (after Slice 2):* three-band identity; coverage floor as a measured N; coarse-matched (sanitized embeddings, adaptive admission, approved-only exclusions); geographic plausibility; party-aware timers; <90s median on candidate-authored mix. Manual for now (automated in 1.5): policy audit sampling, calibration measurement, policy recall tooling.

**Phase 1 target (kept for the destination, not the first coding milestone).** The paragraph above (Implemented / Calibrated / Full Phase-1 target) is the contract. The historical one-block DoD is retired so it cannot be read as “ship three-band identity, dual scores, embeddings, and timers in weeks 3–8.”
**Explicitly out of Phase 1:** active sourcing; any sending; inbound machinery; voice; graph view; multi-user; learned reranking; dynamic agent spawning.

**Phase 1.5 (months 3–4).** Reflection loop + narrative synthesizer; supersession/revision UI polish; shadow scoring; enrichment budget/caching maturity; audit-sampling + calibration + recall automation; PA rung 1 (drafts, human-sent); learning capture + first weekly batch analysis (proposals cite labels); timeline visualization; bulk actions. **BD groundwork:** career-page/ATS collection during company research and `origin = discovered` job records — cheap, additive, and it starts building the demand-side dataset months before it is used; `marketable` added as a Brief item so permission accrues from the first calls.

**Phase 2 (months 5–8).** Sourcing campaigns behind identity + compliance gates; lookalike via sanitized vectors; **PA rung 2 + full inbound machinery** (halt rule, classification, replies-as-documents, suppression producer) — inbound ships *with* sending, never after; contradiction detection at scale; learning proposals behind the bias suite; learned reranker if ≥500–1,000 labels; SLA timers everywhere; LLM supervisor + dynamic spawning against the Phase-1 eval baseline. **BD stage one:** eligibility sweep (staleness × match × prospect value, warmth-gated), company-teaser generalization + human review (05 RA-05), candidate-first teasers as rung-1 drafts, refresher-call flow, client relationship states. Recipient exclusion is mechanical. Stage one ships before stage two deliberately — the teaser lands on a warm, known recipient and is the simpler, higher-trust motion.

**Phase 2.5.** **BD stage two:** candidate-spec generator with conservative generalization + human review (05 RA-05) and current-employer/ecosystem exclusion; warm company-side outreach; hiring-manager contact discovery as a research provider category. Segments (materialized saved queries), bench-strength view, and the supply×demand map.

**Phase 3 (month 9+).** PA rungs 3–4 (pending queue) for proven action types; voice behind the adapter (AI-disclosed) with live call assist over precomputed Brief items; multi-tenant activation; scale bolt-ons as measured need dictates (pgvectorscale, ParadeDB, read replicas, Citus — 01 §C4); extraction-model distillation once ~100k+ graded approved extractions exist; AI Act conformity pack + one day of specialist legal review; Kubernetes only if load demands.

---

## §3. Repo skeleton

```
maindscout/
├── docker-compose.yml            # postgres(+pgvector,ltree), minio; temporal/langfuse later (05 RA-07)
├── Makefile                      # make dev / make eval / make migrate
├── cockpit/                      # Next.js 16 — inbox / candidates / jobs / companies
├── core/
│   ├── api/                      # the only writer
│   ├── domain/                   # entities, state machines, claim registry,
│   │                             #   reconciliation fn, scoring, brief compiler
│   ├── intelligence/             # harness (span/citation validators, rubric,
│   │                             #   manifests, workspace), agents, versioned prompts
│   ├── research/                 # registries (Companies House, Crunchbase), providers,
│   │                             #   query planner, anchors, snapshots, global throttle
│   ├── ingestion/                # extraction+artifacts, link harvest, vision fallback,
│   │                             #   classifier, splitter, as_of, language
│   ├── workflows/  workers/      # Temporal
│   ├── compliance/               # erasure workflow+verify, sweeps, suppression
│   └── migrations/
├── evals/                        # golden/ (catalogue in §1) + run_eval.py
└── docs/                         # 00–05 (this set), claim-ontology.md, decisions/ (ADRs)
```

---

## §4. Risk register

| Risk | Mitigation |
|---|---|
| Silent input corruption (most dangerous: no error surfaces) | Artifacts + vision fallback + link harvest; degraded-input golden cases |
| Cross-person / cross-entity contamination | Identity precondition; subject attribution; company anchors; frequency tripwire |
| False merge | Asymmetric thresholds; redirect merges; not-same memory; merge round-trip eval |
| Silent belief mutation | Approved-view snapshots; revisions through the gate |
| Review fatigue kills the claims model | Policies + authority gate + classes (computed skip review); <90s KPI by source mix; item-specific rendering |
| Ceremonial oversight (AI Act exposure) | Attention grades; audit sampling; graded labels |
| Hallucination past the gate | Document-blindness + **tiered** span/citation validation (05 RA-01); typed-tier rate only |
| Fit-cost explosion / recompute storms | Lazy tiers; debounced singletons; stale-flag laziness; budgets + ledger |
| Bias vs non-standard careers, thin documents, protected proxies | Archetypes + renormalization + coverage floor; UNKNOWN semantics; sanitized projection + leakage probe; probe-don't-punish; inbox decision-value ranking; learning bias gate |
| Relationship damage (outreach) | Inbound halt; outward projection; suppression; representation + Art. 14 + client-scope gates; pending queue |
| Knowledge-base divergence | Stint keys + reconciliation; per-type dedup; sweeps |
| Re-identification through anonymized BD artifacts | Conservative fixed generalization + human review before send (05 RA-05); current-employer/ecosystem recipient exclusion; small-market test cases. Pool-size search is not the safety mechanism. |
| Self-competition / relationship damage in BD | Active-pipeline conflict gate; `marketable` permission; warmth-gated templates; names only in conversation (E-i12) |
| Scale rewrite at 10M records | Unpartitioned start; partition on a measured trigger (05 RA-06); cursor-based sweeps; fan-out as SQL (E-i14); additive bolt-ons only (01 §C4) |
| Legal | Phase-0 erasure + verify; proportionate Art. 14/retention; counsel at commercialization only |
| Scope creep / spec drift | Slice-0 contract (05 §D); closed intake until eval-green; ADR + eval-gate change discipline (00) |

---

## §5. Open questions (deliberate; each closes via ADR, not a v5)

1. Reconciliation weights & contradiction-surfacing threshold — calibrate on golden set.
2. Coarse-fit admission K and floor — start conservative, tune on overrides.
3. `as_of` precedence under stated-vs-metadata disagreement; how much low confidence softens recency.
4. Vision extraction: always-on for designed layouts vs heuristic-triggered — measure heuristic miss rate first.
5. Provisional-score visibility outside Inbox ranking (anchoring risk).
6. Coverage-floor N (default 4/7) — validate against operator judgment on golden profiles.
7. Draft edit-distance threshold for "lightly edited."
8. Corridor list governance — who maintains it, review cadence (probe-don't-punish audit).
9. ~~Client-as-account entity~~ — **closed by Feature 11**: company `relationship_state` plus contacts; BD made it necessary for an offensive reason. Remaining sub-question: when a client is an account with *contractual terms* (fee agreements, exclusivity), does that warrant a separate entity beyond the company record?
10. Corporate-structure graph (brand vs legal entity vs subsidiary) — deferred; Critic materiality Decision suffices meanwhile.
11. ~~k-anonymity floor via pool-size / discovered-jobs cardinality~~ — **closed as the safety mechanism by 05 RA-05**. Remaining: the written generalization rules themselves (candidate side vs company side may differ; small-market calibration). Human review is a standing send gate until those rules exist. Recipient exclusion is not an open question.
12. BD eligibility constants — the staleness threshold (~4–6 months) and the warmth cutoff separating one-step teaser from two-step reconnection.
13. Live call assist: managed voice (Retell) vs self-hosted (LiveKit) — a cost-vs-control call best made with real usage data; the adapter exists so it can wait.
14. Extraction-model distillation timing — the graded-approval volume at which a tuned open model beats frontier cost/quality in practice (~100k is an estimate, not a measurement).

---

## §6. Compliance summary (one page, proportionate)

**GDPR, designed now, not settled:** intended lawful basis = legitimate interest (LIA to be written once and reviewed); sourced-candidate notice via first-outreach footer + one deadline sweep (contact-or-delete Decision); retention = one rule + one sweep (erase-or-refresh); erasure = one workflow + verification query, suppression hashes written, with the shared-snapshot limitation named in 05 RA-04; SAR export = on-demand claim/evidence dump; minimization = the ontology itself; special-category & appearance claims schema-suppressed. Web *querying* is ordinary practice — obligations attach to stored results and profiles. Provider DPAs are a one-time checklist. Legitimate-interest challenges happen; these controls are what we build, not a legal opinion.
**EU AI Act (high-risk on commercialization is plausible, not assumed):** the architecture is designed as the control story — human oversight (gates, policies, grades, audit sampling), logging (activity, manifests, cost), accuracy monitoring (harness), transparency (citations, explainable scores), bias mitigation (renormalization, sanitized projection + probe, decision-value ranking, learning gate, probe-don't-punish). Pre-launch: documentation pack, bias report from standing metrics, instructions for use, and **qualified** counsel. “One day of counsel” is not a conformity assessment (05 RA-11).

---

## §7. Findings coverage register

Maps every review finding and operator correction to its v4 home — the completeness check. (Fn.m = Feature-dive n, finding m; 01 = system blueprint, 02 = specs.)

| Findings | v4 location |
|---|---|
| F1.1–F1.11 (hash layering; document_subject; artifacts; vision bias; misclassification recovery; splitter; transformed-by-third-party; as_of precedence; job resolution; language; doc lifecycle) | 02-F1.1–11 · 01 §D1, §B1, §B3, G2 |
| F2.1–F2.9 (attribution+tripwire; index=claims; key conflicts; size-weighted overlap; three bands; not-same memory; **redirect merges**; brand-level companies; suppression) | 02-F2.1–9 · 01 §D3, E-i13, G2 |
| F3.1–F3.9 (re-keying; boomerang/ambiguous stints; **approved-view snapshots**; origin corroboration; field-level cascade; claim classes; supersession heads; per-type dedup; atomic contradictions + volatility carve-out) | 02-F3.1–9 · 01 §B2–B4, §D2, E-i3/5, §F |
| F4.1–F4.9 (status ownership; seal-on-interaction; grades+audit sampling; policy versioning/recall/fail-closed; decision-value ranking; bundles; born-approved edits+authority slot; reject-label hygiene; KPI+rendering) | 02-F4.1–9 · 01 §D6, G1-8 |
| F5.1–F5.10 (activity boundary; workspace commit; **blindness+span validation**; rubric+calibration gating; code supervisor; harness provenance; critic semantics; budget degradation; manifests; partial aggregation) | 02-F5.1–10 · 01 §C3, §D4, E-i7/11 |
| F6.1–F6.9 incl. operator-revised F6.3 (**snapshots-as-documents**; research extractor; proportionate provider hygiene; anchors; injection+single-source rule; origin≠channel; honest+negative caching; volatile-vs-stable; global throttle) | 02-F6.1–9 · 01 §D1, §C3 |
| F7.1–F7.9 + operator corrections (**computed_as_of**; archetype claim; comparability-via-fit; coverage floor; sanitized projection+probe; adaptive admission; approved-only exclusion; **no-LLM-numbers**; recompute discipline; **Environment Fit**; **geographic plausibility gradient**) | 02-F7.1–11 · 01 §F, E-i4/10, G2 |
| F8.1–F8.10 (permanent pairs; decaying matched; revision handling; structured outcomes; job cascade+**silver medalists**; cross-pair events; party timers; concurrency; **client-scoped memory**; nurture defined) | 02-F8.1–10 · 01 §D5, E-i8, G2 |
| F9.1–F9.8 (compiler; **item lifecycle/no-resurrection**; scope inheritance; reason/question split; **inline capture**; Art. 14 collapse; erasure+verify; retention rule) | 02-F9.1–8 · 01 §D6, E-i9, G1-11 |
| F10.1–F10.10 (outward projection; **inbound halt+classification**; replies-as-documents; edit-distance promotion+diff labels; pending queue; sequences-as-state-behavior; personalization framing+considered archive; bias-gated proposals; label hygiene; digest compiler) | 02-F10.1–10 · 01 E-i12, §D6, G2 |
| Pre-dive v3 corpus (authority tiers; temporal precision; parallel tracks; verification ladder; research tiers; UNKNOWN; provisional/official; rank-first; autonomy ladder; representation gate; special-category suppression; org_id; …) | Distributed through 01 §B–G and 02; unchanged in substance |
| **Business development** (ATS job discovery; `origin` separation; two-stage candidate-first funnel; both k-anonymity validators + recipient exclusion; triple-product eligibility sweep; warmth-gated templates; refresh-instrument reply tree; `marketable` Brief item; segments + supply×demand map; client lifecycle) | 02-F11.1–10 · 01 §D3/§D5, E-i12, G2 · 00 P11 |
| **Scale & technology** (growth path; partition-on-signal; cursor-based sweeps; fan-out as SQL; bolt-ons and rejected alternatives; language-by-latency-domain; model tiering; distillation flywheel) | 01 §C4, E-i14 · 03 §2 · 05 RA-06 · 00 P12 |
| **05 review amendments** (span tiers; live identity query; pair collapse; snapshot TTL; k-anon universe; observability; intelligence/ no DB; education carve-out; exceeds_expectations; compliance tone; Slice-0 gate; 2026-09 fixtures) | 05 RA-01–RA-11 · 05 §D–E · 01 §E, §D3/D5 · 02-F2/F3/F5/F6/F7/F8/F11 |

Every register row is additionally represented in §1's eval catalogue where a behavioral test is meaningful — the second, executable layer of the completeness guarantee.
