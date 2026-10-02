# mAIndScout — Blueprint v4
## 01 — System Blueprint

*v4.2: implement against 05 where 05 revises a mechanism (RA-01–RA-11). This file remains the target architecture.*

---

## A. What this is

mAIndScout is an autonomous AI recruitment platform: it ingests the raw materials of recruiting (CVs, job descriptions, screening notes, research, conversations), reconstructs a master-recruiter-level understanding of candidates and companies as structured, evidence-backed knowledge, scores and matches with full explainability, and progressively automates coordination — while a human retains decision authority at every consequential point. It begins as a single-operator tool for real recruitment and is architected from day one for multi-tenant commercialization.

**The thesis in one number:** per candidate, ~ten minutes of machine work should require under ninety seconds of human judgment, and that judgment should be better-informed than an hour of manual research. Every mechanism serves this ratio; a feature that degrades it is wrong.

**Three foundational rules:**
1. **Knowledge is claims, never prose.** Every fact is an atomic, typed Claim backed by Evidence with provenance. Narratives and briefs are disposable views regenerated from claims.
2. **AI proposes; authority is explicit.** Agents create staged/proposed claims. Approval happens by humans directly or by human-defined, versioned, audited policies.
3. **Real-world input is degraded input.** Documents arrive undated, visually designed with corrupted text layers, incomplete, internally inconsistent, multi-subject, multi-language, and mutually contradictory. The system is designed for that as the default, not the exception.

---

## B. The trust calculus

Four orthogonal properties govern how much any piece of information is worth. They recur through every feature; learn them once here.

**B1. Source authority — who authored the document.**
`verified_primary` (registries, official records) > `human_assertion` (the operator's direct statement) > `candidate_authored` (own CV/LinkedIn) > `employer_authored` (JD, offer letter) > `third_party_assertion` (agency notes, references) > `web_inference`.
A registry contradicting a human assertion surfaces as a contradiction rather than being silently overridden — humans misremember; registries rarely do. Documents that are candidate content *re-typed by a third party* (agency-templated CVs, detected via branding/layout) carry `transformed_by_third_party = true`: the factual skeleton keeps candidate-authored weight, prose assertions drop toward third-party weight, and the document is **disqualified from auto-approval**. The flag also explains stripped contact details (agencies remove them deliberately), so missing identifiers read as "withheld," not "nonexistent."

**B2. Origin — whose knowledge it ultimately is.**
`candidate | employer | registry | independent_web | human | relayed | unknown` — distinct from authority. The candidate's CV, their LinkedIn, and agency notes written after a call with them are three documents but **one informant**. `relayed` (04 AL-10) is the extra hop: an agency conveying the candidate's own situation; it must never corroborate with `candidate`-origin evidence for the same fact. Corroboration raises confidence only **across origins**; three candidate-origin sources agreeing ≈ one strong observation, while a registry confirming a self-report is real corroboration.

**B3. Time — `as_of`.**
Documents carry no dates, so every document gets an inferred `as_of` (precedence: content-stated durations, e.g. "– Present (3y)" anchors the writing date → PDF metadata → upload time; disagreement between the first two lowers `as_of_confidence`). Every claim inherits `observed_as_of`. **Conflict resolution = authority × recency**, with a domain rule: candidate-authored wins on *historical* facts (titles, dates); fresher sources win on *current-state* facts (availability, employment status). Low `as_of_confidence` softens recency's weight.

**B4. Confidence — computed, never self-reported.**
Stored confidence is produced by a harness rubric (evidence authority + origin, span-check result, claim class, cross-source agreement), with model self-report at most one bounded input. Per-model calibration is measured against the golden set; **swapping a model suspends auto-approval for its claims until recalibration passes.**

---

## C. Architecture

### C1. Deployables — exactly two, plus infrastructure

```
┌────────────────────────────┐        ┌──────────────────────────────────────┐
│  cockpit  (Next.js 16)     │  HTTP  │  core  (Python 3.12, FastAPI)        │
│  Recruiter OS UI, SSE      │───────▶│  api/          ← ONLY writer         │
└────────────────────────────┘        │  domain/       ← entities, state     │
                                      │    machines, claims, reconciliation, │
   docker compose infra:              │    scoring, brief compiler           │
   - PostgreSQL 16                    │  intelligence/ ← harness + agents    │
     (+ pgvector, ltree)              │  research/     ← providers,          │
   - Temporal (self-hosted)           │    registries, snapshots, throttle   │
   - MinIO (S3, content-addressed)    │  ingestion/    ← extraction,         │
   - LangFuse (tracing)               │    classifier, splitter, as_of       │
                                      │  workflows/ workers/  ← Temporal     │
                                      │  compliance/   ← erasure, sweeps     │
```

One language, two deployables. Module boundary: `intelligence/` never opens a database session — extractors see bytes, everything else sees claims, `api/` commits (E-i1, 05 RA-08). Convention from day one; a CI import-linter gate is deferred until the team is large enough that convention fails. Extraction into services later is days, not months — and happens only under concrete pressure, never preemptively. `org_id` on every table from the first migration.

### C2. Stack
Next.js 16 / Tailwind / shadcn / cmdk / TanStack Query · Python 3.12 / FastAPI / Pydantic v2 / SQLAlchemy 2 · Temporal (Python SDK) · LangGraph *inside* agent activities only · PostgreSQL + JSONB + pgvector + ltree · MinIO/S3 content-addressed and immutable · LISTEN/NOTIFY → SSE · versioned prompt & model registries; every LLM/provider call writes a cost row · voice (Phase 3+) behind an adapter.

### C3. Orchestration boundary
**One agent = one Temporal activity.** LangGraph runs inside an agent for its internal loop; inter-agent state passes only through persisted run-workspace records. Agent activities are idempotent via run-scoped output keys (a retry overwrites its own staged output). A **global per-provider token bucket with a priority queue** sits between all workflows and every external provider: rate-limit responses park the activity on a Temporal timer until capacity is granted — never retried as failures.

### C4. Scale & technology decisions (the 10M-candidate stress test)

**Growth path, zero architectural breaks:** single node → partitioned single node → read replicas (trivially safe — `api/` is the only writer) → **Citus** (open source) sharding by `org_id` when multi-tenant load demands it; multi-tenant-by-org is Citus's textbook case, which the schema anticipated. Two disciplines make "no rewrite at 10M" true rather than hopeful: (a) the five biggest tables — `claim`, `evidence`, `claim_observation`, `activity`, `score` — are **created unpartitioned**, then partitioned when a measured signal trips (row count or p95 latency on a named query — 05 RA-06), via a migration that is itself an eval case (declarative partitioning is cheap; picking the wrong key early repeats the copy this rule exists to avoid); (b) **every sweep is written incremental/cursor-based, never full-scan**.

**Scale bolt-ons, additive when needed:** pgvectorscale + quantization when plain pgvector HNSW strains (~10M embeddings); ParadeDB for BM25 search in-Postgres (Meilisearch/Typesense as the external escape hatch); Qdrant behind the same interface only if vectors ever outgrow Postgres; analytics later via logical replication into ClickHouse/DuckDB — purely additive, so dashboards never hammer OLTP.

**Alternatives considered and rejected, honestly:** graph databases (the claim graph is 1–2 hops deep — relational handles it, and atomic contradiction resolution *requires* transactions); document stores (the system's value is joins and constraints); a separate OLAP store now (see the replication bolt-on above).

**Language follows latency domain.** Batch/workflow (seconds fine) and interactive (100–300ms) domains stay Python: the system is I/O- and model-bound, and the AI ecosystem is Python-native — whose hot paths are already Rust underneath (Pydantic core, tokenizers, Polars). The real-time domain (live call assist, voice) is bounded by STT and model time-to-first-token, not application language: its levers are fast small models on high-throughput inference serving, streaming, and the fact that **the Brief pre-computes the questions** — live assist is retrieval + light selection over open Brief items, not generation. Rust enters only as a targeted PyO3 extension if profiling ever demands it; Go is excluded (its niche is fully covered by Temporal + async Python).

**Model economics.** The registry tiers tasks: frontier models for cross-linking, critique, and learning analysis (the moat — quality is the product); mid-tier for fit judgment; small or open-weight models for extraction, classification, phrasing, and live selection; self-hosted open embeddings via vLLM (at 10M+ documents, per-call embedding APIs are untenable — the clearest open-source win). The review system doubles as a **supervised-dataset factory**: at ~100k+ attention-graded approved extractions, the frontier extractor is distilled into a LoRA-tuned open model (10–50× cost cut at higher consistency, trained on this ontology specifically), entering the registry through the same calibration gate as any model swap (B4). LLM spend dominates all infrastructure cost at scale, which makes this flywheel worth more than any infra optimization.

---

## D. Data model

### D1. Documents & extraction
```
document            (id, org_id, sha256 UNIQUE, storage_key, media_type,
                     doc_type [cv|screening_notes|jd|interview_feedback|reference|
                               portfolio|cover_letter|email_thread|research_snapshot|other],
                     source_authority, transformed_by_third_party BOOL, language,
                     as_of, as_of_basis [stated|pdf_metadata|upload_time], as_of_confidence,
                     status [received|stored|extracted|classified|dispatched|processed|
                             needs_human|reprocessable],
                     needs_vision BOOL,              -- text path only in Slice 0 (05 D2)
                     research_context JSONB NULL,     -- query, provider, goal (snapshots)
                     last_processed_with JSONB, created_at)          -- immutable bytes
extraction_artifact (id, document_id, method [text_layer|vision], content_sha,
                     produced_with JSONB, created_at)  -- locators point HERE, never at bytes
document_subject    (document_id, subject_type, subject_id, segment_locator JSONB NULL,
                     established_by)                   -- who the doc is about; erasure depends on it
```
Web research results are **ordinary documents** (`doc_type = research_snapshot`, `as_of` = fetch time) — one pipeline, one guarantee set. Same-hash re-uploads are recorded, not reprocessed, unless `last_processed_with` is stale (which doubles as free corpus-wide reprocessing when agents improve).

### D2. Claims, observations, evidence
```
claim             (id, org_id, subject_type, subject_id, claim_type,
                   class [observed|inferred|computed],
                   payload JSONB, natural_key TEXT NULL,
                   valid_from, valid_to, temporal_precision
                     [exact|month|year_only|ordered_only|unknown],
                   confidence, verifiability [registry|public_record|scholarly|web|unverifiable],
                   flags JSONB,                    -- extraordinary_unverified, plausibility,
                                                  -- geographic{severity}, possible_duplicate_stint,
                                                  -- single_source_web, suppressed_by_critic, ...
                   status [staged|proposed|approved|rejected|superseded],
                   approved_view JSONB NULL, approved_view_hash NULL,   -- pinned at approval
                   approval_mode [human|policy] NULL, policy_id/version NULL,
                   attention_grade [policy|human_bulk|human_individual] NULL,
                   run_id NULL, created_by_*, observed_as_of,
                   approved_by/at, rejection_reason JSONB {code, note},
                   superseded_by NULL, created_at)
claim_observation (id, claim_id, attribute_path, value JSONB, evidence_id,
                   source_authority, origin, observed_as_of)
                   -- per-source values for keyed claims; the reconciled view is a
                   -- deterministic pure function over these (authority × recency, B3 rule)
evidence          (id, claim_id, evidence_type [document_span|research_result|
                   human_assertion|derived|registry_record],
                   source_id, locator JSONB → extraction_artifact,
                   source_authority, origin, snippet, observed_as_of,
                   model_used, tool_call_id)
claim_relation    (from_claim, to_claim,
                   kind [supports|contradicts|supersedes|derived_from|context_for],
                   consumed_paths JSONB NULL,      -- field-level provenance for derived_from
                   weak BOOL DEFAULT false)        -- served-but-uncited edges
```
`claim_type_registry` rows carry: versioned JSON schema, **class**, **dedup policy** (natural-key definition — e.g. SkillClaim: candidate + normalized skill), **volatility** (`volatile|stable` — drives contradiction-vs-trajectory handling), default review tier.

### D3. Identity & entities
```
candidate    (…, name_variants JSONB, global_state, trajectory ↦ via archetype claim,
              merged_into_id NULL,                 -- REDIRECT, never rewrite (see E-i)
              introduction_source, representation JSONB, contact_permission, …)
company      (…, canonical_name, aliases JSONB, registry_ids JSONB, last_researched_at,
              relationship_state [none|prospect|contacted|in_conversation|active_client|dormant],
              merged_into_id NULL, …)              -- brand-level entities; parent/sub links are claims
suppression_registry (salted_identifier_hash, reason, created_at)   -- written by erasure & by "stop"
```
The identity match index is a **live query over identity/contact claims** in the same transaction as the claim write (05 RA-02) — never a Postgres materialized view, and never a shadow store. A denormalized `identity_key` table is permitted only if `api/` is the sole writer, including reject and supersede, in that same transaction. Rejected `SameAsClaim`s persist as not-same constraints (overridden only by new deterministic evidence). Harvested identifiers carry **subject attribution** (is this the document subject's, or the author's/template's?); unattributable identifiers are stored but never used as match keys, and a nightly frequency tripwire quarantines any identifier appearing across many unrelated candidates.

### D4. Intelligence runs
```
intelligence_run (id, subject refs, trigger, version_manifest JSONB
                  [prompt vers., model vers., ontology ver., rubric ver.],
                  budget JSONB, status [running|committed|failed|budget_truncated],
                  committed_at)
validation_event (id, run_id, kind [hallucination|injection|span_fail|citation_fail|paraphrase_only],
                  payload, created_at)             -- may live on activity.kind until weekly volume (05 RA-07)
model_calibration(model_id, task, curve JSONB, valid BOOL, measured_at)
```
Claims are **staged** into the run (invisible to scores, matching, and review) and **commit atomically** at run completion — which is also the moment the review batch forms. Failed runs are garbage-collected having never existed for consumers.

### D5. Pipeline
```
job            (id, org_id, title, hiring_company_id, state [open|on_hold|filled|cancelled],
                origin [client_brief|discovered], source_posting JSONB NULL,
                version, pipeline_config JSONB      -- discovered jobs never silently enter
                  [states, awaiting: operator|candidate|client|nobody, SLA timers,
                   pa_behavior per state], …)       --   the client pipeline (F11)
candidate_job  (candidate_id, job_id  UNIQUE — permanent row, created once,
                merged_into_id NULL,               -- pair-level REDIRECT on SameAs (05 RA-03)
                pair_state [matched|considered|reviewed|shortlisted|contacted|screening|
                            submitted|interviewing|offer|placed|terminal],
                outcome JSONB {party: client|candidate|operator|system,
                               reason, cause, linked_claim_ids},
                coarse_fit, flags JSONB [possible_deal_breaker, competing_offer, no_longer_meets],
                version)                            -- optimistic concurrency on every event
score          (id, candidate_id, job_id NULL, kind, tier [provisional|official],
                value NULL, confidence, coverage, applicable_dimensions JSONB,
                breakdown JSONB, claim_set_hash, computed_as_of, engine_version,
                stale BOOL, created_at)             -- append-only
entity_embedding (…, projection_version)            -- sanitized projection only (F7)
segment        (id, org_id, name, query JSONB,      -- materialized saved queries over claims
                member_count, refreshed_at)         --   "GTM · Senior · seed–A · Berlin" (F11)
```

### D6. Review, brief, outreach, learning
```
decision        (id, type, priority, subject refs, context JSONB, sealed_at NULL,
                 status DERIVED from members, snooze_until NULL, created_at)
approval_policy (id, name, version, predicate JSONB
                 [claim_types, min_confidence, allowed_source_authorities], enabled, …)
                 -- fails closed; tightening offers a sized recall of past approvals
brief_item      (id, scope [candidate|pair], candidate_id, job_id NULL,
                 source_flag_ref, internal_reason, question, severity,
                 state [open|asked|answered|dismissed|expired], answered_claim_id NULL)
thread          (id, candidate_id, channel, automation_halted BOOL, last_inbound_at)
pending_send    (id, thread_id, payload, release_at, state [pending|sent|pulled])
learning_label  -- derived: attention-graded approvals/rejections + draft diffs +
                 -- structured pair outcomes; recency-decayed; proposals cite their labels
flag_type_registry (key PK, default_severity, brief_template,
                    blocks_auto_approval BOOL, blocks_matching BOOL,
                    valid_subject_types)            -- AL-13; 05 D4 seed list
cost_ledger, activity, data_subject_record          -- as v3, unchanged in role
                                                -- validation kinds may live on activity.kind (05 RA-07)
```

---

## E. Invariants — the rules that must never break

- **E-i1.** Only `api/` writes permanent records; agents and research propose through it.
- **E-i2.** No claim without evidence; human-entered facts are claims with `evidence_type = human_assertion` (born approved, individually graded).
- **E-i3.** Approved beliefs are immutable: approval **pins a snapshot** (`approved_view`). New observations attach freely to the record; if re-reconciliation yields the same view, confidence rises silently; if a different view, the approved claim stands and a **proposed revision** goes to review. Beliefs change only through the gate.
- **E-i4.** Two-tier reads: agents may read proposed claims; official scores, outbound content, and anything presented as fact use approved claims only, and provisional outputs are always labeled. **Hard exclusions (deal-breakers) additionally require an approved claim** — a proposed one flags, never hides.
- **E-i5.** Field-level rejection cascade: derived claims record consumed fields; a change or rejection in a consumed field flags every descendant for re-review. Weak (served-uncited) edges err toward re-review.
- **E-i6.** Free text is never the source of truth; narratives, briefs, digests are compiled/regenerated views.
- **E-i7.** Every LLM and provider call writes a cost row; every run carries an enforced budget with a defined degradation order (narrative first, deep research next — never extraction or critique).
- **E-i8.** Every state change is an event validated by the relevant state machine, with optimistic concurrency (expected-state check). **The machine may unwind only machine-created state; anything human-touched requires a human to unwind.**
- **E-i9.** Erasure overrides immutability: one privileged workflow deletes/anonymizes everything about a subject (claims, evidence, embeddings, scores, brief items, pair rows anonymized, multi-subject links severed), writes salted identifier hashes to the suppression registry, leaves a data-free tombstone — and ends with a **verification query that fails loudly on any survivor**. Research snapshots follow 05 RA-04: bytes are a TTL cache; durable residue is `evidence.snippet` + hash; a verify query must not report green across an unresolved shared-byte conflict. Slice-0 erasure fixtures are single-subject only.
- **E-i10.** **No LLM emits a number that enters a score.** LLM modules output categorical requirement-level judgments with cited claims; code converts categories to numbers under versioned weights.
- **E-i11.** Evidence is **tier-validated** against an immutable extraction artifact at workspace commit (05 RA-01): the typed tier (locator resolves; dates, money, closed vocabularies, and — after company resolution — org aliases) is mechanical and is the hallucination-rate numerator; the paraphrase tier is a separately measured pass rate and never increments that numerator. Typed-fail + paraphrase-pass may stage as `proposed` with `paraphrase_only_support`, barred from auto-approval. **Only extractor agents ever see raw content** — all downstream agents are document-blind and receive structured claims only. Required citations are validated against the served set. Text-layer contact identifiers that fail consistency checks raise `possible_ocr_identifier` and must not become deterministic identity keys until a human ContactClaim confirms them.
- **E-i12.** Nothing candidate-facing is generated outside the **outward projection** (approved claims about the recipient, public job facts, Brief `question` fields, conversation history — never scores, flags, `internal_reason`, or third parties). **Any inbound message halts all automation on its thread, unconditionally, at every autonomy rung.** In business development the rule is **two-sided: anonymized in writing, revealed only in conversation** — candidate specs to companies and job teasers to candidates use conservative fixed generalization plus human review; safety is **not** a pool-size search over our own base (05 RA-05). Current-employer and named-ecosystem recipient exclusion is mechanical. Company names of discovered jobs are structurally absent from the draft generator's served context; candidate identity reaches a company only at submission with consent.
- **E-i13.** Merges are **redirects, never rewrites**: claims keep their original subject forever; `merged_into_id` redirects reads; unmerge = supersede the SameAsClaim. The same redirect shape applies to `candidate_job`, scores, Brief items, threads, and `job.hiring_company_id` (05 RA-03). Conflicting human-touched pair states do not auto-collapse — they open a Decision. Reversibility of claims is structural; reversibility of fused pipeline state is either also a redirect or explicitly irreversible and human-gated.
- **E-i14.** **Matching fan-out executes as database queries** — prefilters + vector ranking composed in SQL, returning top-K — never as application-side loops over candidates. This single rule is what makes 10M-scale matching a hardware question instead of a rewrite.
- **E-i15.** `intelligence/` persists nothing and does not open a database session. Agents return staged claims + citations; `api/` commits (05 RA-08).

---

## F. Claim ontology (Phase-0 set)

**Career & identity:** IdentityClaim, ContactClaim, CareerStepClaim (stint-keyed: candidate + canonical company + overlapping period — one claim per stint; attributes reconcile via observations; provisional company ref at creation, **re-keyed after company resolution**; attach only when same-stint is confident, else separate + `possible_duplicate_stint` — boomerangs work for free), PromotionClaim, EducationClaim (keyed), SkillClaim (keyed on normalized skill), RootCapabilityClaim, SeniorityAssessmentClaim, TrajectoryArchetypeClaim (**inferred, reviewable** — `ladder|founder|academic_transition|portfolio`, optional secondary; flips arrive as revisions, never silent regime changes).
**Computed (auto-recomputed, rule approved once, never individually reviewed):** GapClaim, tenure totals, timeline-consistency checks. Education overlapping employment is **not** a consistency failure (05 RA-09). Concurrent employment-like stints raise concurrency flags on both sides (04 AL-09), not a fused stint.
**Recruiting primitives:** AvailabilityClaim, WorkAuthorizationClaim, LocationClaim (`basis: stated|inferred`), MotivationClaim, CompensationExpectationClaim (elevated review bar).
**Achievement:** PublicationClaim, RecognitionClaim, SideProjectClaim.
**Company (time-bounded):** CompanyStageClaim, FundingClaim, TeamSizeClaim, DomainClaim, CompanyTypeClaim — `volatile` types default disagreements to temporal bounding (growth is a trajectory, and trajectory is cross-linker material), `stable` types route to contradiction.
**Higher-order (inferred):** JoinedAtStageClaim, CareerProgressionClaim, ImpactClaim, LeftBecauseClaim.
**System:** SameAsClaim (merges as claims). **Job-side:** RequirementClaim (`must|strong_plus|nice|anti`).

**Environment, not "culture."** The system models **Environment Fit** only: demonstrated environments (stage joined, company type, team size, growth-during-tenure) matched against the job's environment — mostly deterministic from existing claims, at most one light categorical judgment. **Permanently excluded: personality/values/vibes claims** — no evidence in scope can support them, and the category is where matching drifts into pseudoscience.

**Geographic employment plausibility** (Critic check, sibling of the concurrency check): coherence of candidate location × employer footprint × timezone × remote-plausibility for current/recent stints. Same/adjacent timezone → coherent. Large gap + small single-entity employer → moderate flag — **suppressed if company research shows multiple entities or distributed hiring** (richer company knowledge de-flags honest candidates). Known fraud-prone corridors (configurable list) → high severity: stint claims excluded from auto-approval, verification prioritized, and a **pre-submission gate** — verified before the candidate ever reaches a client. Output is always a Brief question, never a score deduction. History-side geography feeds this check; **job-side** location/on-site requirements are the hard filter (per E-i4's approved-claim rule).

**Suppressed at schema level, never created:** special-category personal data; appearance-derived claims (the vision-extraction path transcribes text only, never describes people — validator-enforced, documented in the bias record).

---

## G. The walkthrough

### G1. Baseline: one clean CV, a brand-new candidate

| # | Stage | Default behavior | Output |
|---|---|---|---|
| 1 | **Ingest** | Hash, store immutably; extract (link-annotation harvest always; vision fallback on reading-order suspicion); classify with confidence; assign authority; infer `as_of`; register document subjects | Immutable document + extraction artifact with permanent anchors |
| 2 | **Identify** | Identity pass on attributed signals; deterministic → fuzzy (three bands) → none match ⇒ new canonical candidate | Canonical `candidate_id`; everything attaches correctly from birth |
| 3 | **Extract** | Full document → typed claims into the **run workspace** (staged); span-validated, rubric confidence, special-category & appearance validators | 30–60 staged claims |
| 4 | **Company context** | Employers resolved (registry-first) and **stint claims re-keyed**; research at relevance tier (skip / registry_only / standard / deep); snapshots = documents; anchor-validated; origin-classified | Time-bounded shared company claims |
| 5 | **Cross-link** | Document-blind agent over served claims → higher-order insights with harness-recorded field-level citations; archetype-aware | The master-recruiter layer |
| 6 | **Critique** | Completeness / confidence / source-trust; concurrency & geographic plausibility; extraordinary-claim triage (verify the verifiable, question the rest); bounded enrichment (identity precondition; ≤2 rounds; budget-gated; survivors → `unresolvable_by_research`) | Gap list, flags, verification priorities |
| 7 | **Commit + provisional score** | Workspace commits atomically → review batch forms; provisional General Strength (archetype dims, coverage-floored) ranks the Inbox; coarse fit (sanitized embeddings + filters; per-job adaptive admission) creates `matched` pairs | Prioritized work |
| 8 | **Review** | Tiered: policy auto-approvals (authority-gated, sampled ~5% for audit), bulk groups, individual items; derivation bundles reviewed with parents inline; batch **seals on first interaction**, later arrivals → next batch | Approved beliefs; <90s median (candidate-authored mix) |
| 9 | **Official score** | Approved claims only; `computed_as_of` + month-quantized time features; append-only with coverage and engine version | Trusted, reproducible measurement |
| 10 | **Full fit (earned)** | On top-N entry or human open: per-requirement categorical judgments (`strong|partial|gap|deal_breaker|UNKNOWN|exceeds_expectations`) with citations; code composes the number; UNKNOWN lowers confidence and asks, never scores; exceeds_expectations routes to the Brief (05 RA-10); **rank-first presentation** | Rank within job + reasons |
| 11 | **Brief** | Deterministic compilation of flags into lifecycle-bearing items (candidate-scope + pair-scope inheriting); `internal_reason` vs neutral `question`; **inline answer capture** → born-approved human assertions close items and refresh scores | The first-call agenda — and the loop's return path |
| 12 | **Pipeline** | Event-validated pair transitions; party-aware SLA timers; outcomes structured at every ending | Coordinated, remembered, learnable pipeline |

### G2. Branch catalogue — trigger → deviation → rejoin

**Ingestion:** designed/corrupted layout → vision re-extraction (rejoin 2). Non-CV type → routed per taxonomy (JD → JobIntelligence with **job-level resolution**: probable existing-job match ⇒ "new version or new role?" Decision; new version supersedes requirements and re-matches the pool). Multi-subject document → **splitter** segments per person; each segment routes independently, all linked to the one original. Low-confidence classification → `needs_human` Decision; `doc_type` is revisable and re-dispatches. Same hash → early exit unless reprocessable. Non-English → language-aware extraction; payloads store `{original, normalized_en}`.
**Identity:** person exists → attach; extraction diffs onto existing stints. Ambiguous → SameAsClaim proposal; work proceeds on the safe interpretation; confirmation triggers redirect-merge + merge-time stint reconciliation **and** pair/score/Brief/thread collapse per 05 RA-03 (conflicting human-touched pair states → Decision, no smash of `UNIQUE(candidate_id, job_id)`). Text-layer contacts flagged `possible_ocr_identifier` are not match keys. Conflicting deterministic keys → never auto-attach; Decision + SameAs proposal. No high-precision identifier → candidate exists but **web enrichment blocked** (`insufficient_identity` Decision). Suppression-registry hit → ingestion of that subject blocked, logged without personal data.
**Claims:** second source on a known stint → observations attach; same reconciled view = silent corroboration; different view = **revision proposal** (diff-rendered). Ambiguous stint overlap → separate + flag. Contradictions → atomic resolution (temporal-succession carve-out bounds windows instead).
**Agents/research:** agent bail-out ("this document doesn't describe a person") → Decision, never forced extraction. Injection-shaped content → flagged, logged, quarantined. Consequential single-origin web claims → individual review. Budget exhausted → defined degradation, `budget_truncated` folded into completeness. Provider rate-limited → parked on the global throttle, never a retry storm. Model swapped → auto-approval suspended for that model until recalibration.
**Scoring:** archetype flip → revision proposal, visible. Coverage below floor → no composite shown; breakdown + "insufficient data" (itself a Brief driver). Company claim revised → dependent scores flagged stale, recomputed lazily by pipeline-activity priority; per-candidate recompute is a debounced singleton.
**Pipeline:** requirements revised → machine-created `matched` auto-expires; human-touched pairs re-scored and flagged, never auto-moved. Job filled → in-flight pairs end `job_filled`; **silver medalists** re-matched immediately and enter top-priority nurture. Offer anywhere → competing-offer flags on all active pairs. Terminal pairs remembered: re-proposal only when causally linked claims change, with explanation; **client rejection blocks re-submission to that client** absent explicit override. `nurture` is defined behavior (entry: silver medalist / strong-general-no-fit; standing: elevated re-match + staleness refresh + later PA touches; exit: matched onward or archived).
**Outreach (Phase 2+):** three send gates in code — Art. 14 notice, representation/contact-permission, suppression list. **Any inbound reply halts the thread**; replies enter ingestion as documents, become claims, resolve Brief items. Rung-3 sends release through the pending queue (visible delay window; undo = pull).
**Business development (Phase 2+):** company research collects active postings (ATS endpoints) → `origin = discovered` jobs enter JobIntelligence and pool matching but never the client pipeline. Strong match at a non-client company → eligibility sweep (current-status-claim staleness × match strength × prospect value; gates: marketable, no active-pipeline conflict, standard send gates; warmth selects one-step teaser vs reconnection-first two-step) → **candidate-first teaser**, company anonymized (k-anonymity vs the discovered-jobs corpus) → name revealed only on the refresher call (Brief-driven; every reply branch yields claims — "I'm at NewCo now" is a fresh stint) → confirmed interest → **company-side warm spec**, candidate anonymized (k-anonymity vs own base; current employer and ecosystem excluded from recipients) → client relationship opens.

Review questions stand as before: for the trunk — too much, too little, wrong order? For each branch — right trigger, proportionate deviation, correct rejoin?
