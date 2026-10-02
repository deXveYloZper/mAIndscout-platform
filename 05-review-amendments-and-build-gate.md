# mAIndScout — Blueprint v4
## 05 — Review amendments, freeze, and Slice-0 build gate

**Status:** accepted amendments arising from the external architecture review of v4 + 04, plus the September 2026 real-document stress test (Catalyst InSAR JD, Procure Ai AI Product Engineer JD, and five CVs). Per the change discipline in 00: this log amends; it does not replace. 01–03 remain the statement of the target architecture. 04 remains the post-v4 document-testing log. Where 05 revises a mechanism in 01–04, **05 wins for implementation.** Where 05 is silent, 01–04 stand.

Development handoff for Slice 0 is now `docs/slice-0/HANDOFF.md` plus `slice0/`. This file remains the mechanism-correction log. 01–04 remain the target architecture. Slice 0 is still the only contract that may be coded.

**Executable contracts:** `slice0/` (schemas, registries, `reconcile()` + 8 pytest fixtures, process_document DTOs, OpenAPI, three review-item specs, golden must/must_not for the 2026-09 PDFs). An agent that invents fields outside `slice0/schemas` is out of spec.

Closed intake: no new claim type, flag, or entity is added to the specification until `make eval` is green on the frozen Slice-0 set. New pain goes on a dated list in `docs/decisions/`, not into 01–04.

---

## A. What this round decided

The target architecture in 01–02 is retained. Four mechanisms in that architecture were **wrong as written**, not merely early. Phase 0–1 as scheduled in 03 §2 would have abandoned the eval-first rule. Feature 11’s pool-size k-anonymity check was the wrong safety mechanism. 04’s accumulation rate is frozen; AL-13 and AL-10 stay in the first schema, AL-18/19 are reserved as a JSON shape (not a reason to build full-fit scoring in Slice 0), and the rest of 04 is backlog until Slice 0 is green.

Two process corrections, owned plainly:

- Calling v4 “definitive” oversold what shipped (flag registry missing; span “entailment” billed as mechanical).
- 04 was ADR-sized item-by-item and a second spec in aggregate. This file restores a closed intake.

---

## B. Load-bearing mechanism fixes

These four replace the corresponding sentences in 01/02. Do not implement the pre-05 text.

### RA-01 — Span validation is two tiers, never one “contain/entail” metric
**Amends:** 01 E-i11, 02-F5.3, 03 §1 hallucination rate.

“Contain” is a substring / structured-field check. “Entail” is a model. Blending them into one hallucination-rate number makes the flagship P5 invariant a second model’s opinion of the first.

**Commit rule:**

1. **Typed tier (blocks commit on fail; counted as `span_fail` / hallucination rate).** Locator resolves inside the artifact. Payload fields of known types are checked without a model:
   - dates / date ranges against tokens in the span
   - money / currency against tokens in the span
   - closed vocabularies (seniority band, requirement strength, skill tokens from the registry)
   - org-name check **only after** company resolution has populated the alias table (pass 2). Extraction precedes resolution (02-F3.1); pass 1 must not pretend the alias table exists.
2. **Paraphrase tier (does not increment the hallucination-rate numerator).** Optional, separately measured pass rate. Typed-fail + paraphrase-pass → claim may stage as `proposed` with flag `paraphrase_only_support` and is barred from auto-approval. It is never counted as a clean span-pass.

Contact identifiers (email, phone, URL) that the text layer can parse but that look truncated, internally inconsistent with the candidate name tokens, or conflict with harvested PDF annotations raise `possible_ocr_identifier` and **must not become deterministic identity keys** until a human ContactClaim confirms them. Confirmed in the 2026-09 folder (Jure text-layer `domainko@` vs visible `domajnkoj@`; Veljko `wipiper` vs `wipher`; Dmitry `dmitychernyshov`).

### RA-02 — Identity index is a live query, not a materialized view
**Amends:** 01 §D3, 02-F2.2.

Postgres materialized views do not update in the same transaction as a claim reject. Implementing `REFRESH MATERIALIZED VIEW` reopens the shadow-store bug F2.2 exists to kill.

**Rule:** identity matching reads **live** from identity/contact claims (plus not-same constraints and the suppression registry) in the same transaction as the claim write. A denormalized `identity_key` table is permitted only if the claim-write path in `api/` is the sole writer, including reject and supersede, in that same transaction. Scripts that backfill keys are forbidden. Slice 0 uses the live query.

### RA-03 — Candidate (and company) merge collapses the pair graph
**Amends:** 01 E-i13, 01 §D5 `candidate_job`, 02-F2.7, 02-F8.1.

Merge-time stint reconciliation was specified. Pair, score, Brief, thread, and embedding collapse was not. The first approved SameAsClaim against anyone with pipeline activity hits `UNIQUE(candidate_id, job_id)`.

**On approval of SameAsClaim(A → B):**

1. Claims stay on their original subject; reads follow `merged_into_id` (E-i13 unchanged).
2. Walk `candidate_job`, `score`, `brief_item`, `thread` / `pending_send`, `entity_embedding`, learning labels for both subjects.
3. For each job: if only one side has a pair, redirect the pair’s candidate_id (or store `merged_into` on the pair and resolve on read — same shape as claims). If both sides have a pair:
   - same or compatible `pair_state` → keep the more advanced row, redirect the other, copy structured outcome memory onto the survivor.
   - conflicting human-touched states (e.g. `placed` vs `interviewing`, `submitted` vs `we_passed`) → **do not collapse**. Open a Decision. SameAs may still approve for the claim graph; pipeline fusion waits for the human.
4. Company redirects apply the same discipline to `job.hiring_company_id` and to pairs keyed by job. Two jobs that become the same role at one canonical company are a second collapse path, not a footnote.

**Unmerge.** Claims remain reversible because ownership never moved. Collapsing two `candidate_job` rows destroys a state machine. Therefore: **pairs also redirect rather than rewrite**, or pipeline merge is documented as not reversible and any SameAs on an in-flight subject is always a human Decision that includes “these two processes are the same process.”

**Slice 0:** if either subject already has a `candidate_job` row, refuse automatic pair collapse and open that Decision. First merges are human SameAs only.

### RA-04 — Web snapshots are a cache; erasure is honest
**Amends:** 01 E-i9, 02-F6.1, 02-F9.7.

A CV is single-subject. A company news snapshot routinely names several people. Severing `document_subject` while bytes remain is not erasure of that person’s data. Full in-place redaction is not a Slice-0 build.

**Rule:**

- Durable residue of web evidence is `evidence.snippet` + content hash + a locator that **may go dead**.
- Full snapshot bytes are a cache with a TTL (operator-set; start at 90 days). After TTL, re-validation is “hash matches if still present, else snippet-only / unverifiable.”
- Erasure of a person: single-subject documents delete; multi-subject live snapshots that contain the subject are TTL-forced to now **or** deleted if the verify query cannot otherwise pass. If a live snapshot cannot be deleted without destroying another subject’s only artifact, the verify query must name that conflict — it must not report green.
- Slice 0 does not ingest research snapshots, so this conflict cannot ship in the first erasure test. The first erasure golden case is single-subject only.

Do not describe snapshot TTL as GDPR erasure. It is a compensating control plus an honest gap.

### RA-05 — k-anonymity is not “search our own pool”
**Amends:** 02-F11.4, 01 E-i12 (BD clause), 03 §5 Q11, 03 §1 BD cases that assume pool-size is the test.

Our talent pool is not the adversary’s universe. Unique-in-500 is often common-in-market; common-in-500 can still identify a company in a small market. A candidate spec de-anonymized to a current employer is the career-ending case.

**Rule:** drop pool-size and discovered-jobs-corpus cardinality as the *safety* mechanism. Keep:

- current-employer + named ecosystem **recipient exclusion** (mechanical, in-universe, ships with Feature 11)
- conservative fixed generalization rules, written later, calibrated on known small-market failures
- human review as a standing gate before Feature 11 artifacts ever send

Feature 11 itself remains Phase 2+. Do not write the generalization rule table now.

### RA-06 — Partitioning is a measured trigger, not Phase 0
**Amends:** 01 §C4, 03 §2 Phase 0, 03 §1 Scale case “partitioned-table migration present from Phase 0”, 03 §4 scale row.

Declarative partitions before the partition key is validated against real queries buy constraint/FK/join pain now and risk repeating the migration this rule was meant to avoid.

**Rule:** create the five large tables unpartitioned. Sweeps are cursor-based from the first one (this part of C4 stands). Partition when a measured signal trips (row count or p95 latency on a named query), via a migration that is itself an eval case. The growth path in C4 remains the target.

### RA-07 — Observability: keep the cheap three; defer the platforms
**Amends:** 03 §2 Phase 0 compose list; 03 §3 repo skeleton.

Keep from day one: `cost_ledger` (E-i7), `intelligence_run.version_manifest`, `activity`. Manifests are what make “this eval failed because of that prompt” a query.

Defer: LangFuse-as-required-infra in the first compose stack; a separate `validation_event` table (`activity.kind` is enough until hallucination rates are counted weekly).

### RA-08 — `intelligence/` does not open a DB session
**Amends:** 01 §C1 import-linter sentence.

The principle stands on day one by convention: extractors see bytes; everything else sees claims; `api/` commits. The CI import-linter gate is deferred until the team is large enough that convention fails.

The activity (or first sync worker) loads a workspace DTO, returns staged claims + citations, and `api/` commits. Querying `claim` from `intelligence/` is the shadow store inside the agent package.

### RA-09 — Computed timeline checks carve out education ∩ employment
**Amends:** 01 §F computed class, 02-F3.6.

A B.Sc. dated inside a full-time stint (Nir 2017–2020 ∩ Matrix IT 2015–2020) is normal. Auto-approved computed consistency claims must not fail closed on education overlapping employment. Concurrent *employment-like* stints still raise AL-09 flags on both sides.

### RA-10 — Fit verdict enum includes `exceeds_expectations`
**Amends:** 02-F7.8, 01 G1 step 10, AL-20.

`strong|partial|gap|deal_breaker|UNKNOWN|exceeds_expectations`. “All levels” + a 13-year shipped-AI profile (Jure × Procure Ai) is not undifferentiated `strong`. Routes to the Brief. Dumb-weights Slice 1+ may ignore the extra points; the enum and the flag exist so the question cannot disappear.

### RA-11 — Compliance tone
**Amends:** 03 §6.

The mechanisms in 01–02 are the right things to build. They are not a legal conclusion. Legitimate-interest challenges happen. High-risk AI Act conformity is not “one day of counsel.” 03 §6 must read as designed controls pending qualified review, not as settled compliance.

---

## C. Freeze list (04)

**In the first schema / Slice 0 contract:**

| Item | Disposition |
|---|---|
| AL-13 `flag_type_registry` | Implement. Highest-priority 04 item, still true. |
| AL-10 origin `relayed` | Implement. Add to B2’s origin enum. |
| AL-18 / AL-19 `score.breakdown` shape + UNKNOWN excluded from the per-requirement denominator | **Reserve the JSON shape** on `score.breakdown`. Do not build per-requirement full-fit in Slice 0 to fill it. |
| AL-02 JD process-date staleness | In JobIntelligence when JDs land; Procure Ai 26–27 Aug 2026 vs 4 Sep 2026 is the fixture. |
| AL-09 concurrency flags on both overlapping claims | Slice 0 for overlapping employment-like `valid_from/valid_to`. |
| AL-22 visa / relocation / residence as three facts | When RequirementClaim extraction for jobs exists (Slice 1+). Fixture: Procure Ai. |
| AL-07 registered address ≠ hiring footprint | When geographic plausibility exists. Not Slice 0. |
| AL-20 `exceeds_expectations` | Enum + flag now (RA-10). Scoring use later. |
| Photo / appearance blocklist | Already in 01 §F; keep. Text path never sees the photo. |

**Backlog — do not implement until Slice 0 eval is green.** Every other 04 item (AL-03–AL-08, AL-11–AL-12, AL-14–AL-17, AL-21, AL-23–AL-48 except as listed above), Feature 11 generalization rules, sourcing sub-platform, vision extraction, Temporal-as-required-runtime, critic, research gateway, embeddings, provisional inbox ranking, policy audit sampling, PA, BD.

04’s retracted items (AL-00, AL-01, AL-43) stay retracted.

---

## D. Slice-0 build gate

This section replaces 03 §2 Phase 0–1 as the **implementation contract**. 03 §2 remains the target roadmap and is annotated there.

### D1. Blocking artifacts that must exist before agents

These run with `pytest` and **no Docker, no Temporal, no MinIO.**

1. Versioned JSON Schema for Slice-0 types: `IdentityClaim`, `ContactClaim`, `CareerStepClaim`, `EducationClaim`, `SkillClaim`, `LocationClaim`. Plus `flag_type_registry` seeded with the keys in D4.
2. `reconcile(observations) -> view` as a pure function with fixtures: same stint two origins (stack); same stint same origin (no stack); boomerang (no fusion); temporal succession (bound both); approved_view vs new observation (revision, not mutation); education ∩ employment (no computed fail).

If those two cannot go green alone, no extractors.

### D2. Slice 0 — implemented loop

Eval-gated, in this order:

1. Schemas + flag registry + origin enum including `relayed`.
2. Document + artifact + text-layer extract + annotation harvest + hash short-circuit. `needs_vision` is a flag, not a second model. Subjects after a dumb identity pass (exact email / phone / LinkedIn + name compatibility). Text-layer contacts that trip RA-01 do not become keys.
3. Typed span check only. Commit via `api/`. No critic, no research, no embeddings, no vision model.
4. Reconciliation + `approved_view` + revision-as-diff. Overlapping employment-like stints stay separate + AL-09 flags.
5. Review UI for **three item types only**: revision diff, duplicate-stint choice, contradiction pair. Approve / reject. Inbox order = `created_at` + blocking Decisions (identity confirmations first). No provisional score ranking.
6. Erasure workflow + verify query on **single-subject** documents.
7. `cost_ledger` + manifest + activity. Fail the eval if a golden profile exceeds the Slice-0 cost cap (one cheap extraction pass).

Orchestration: a sync `process_document` API command that writes a workspace row and commits is enough. Temporal is introduced when a real retry/timeout exists (vision, provider throttle), not because 01 drew the box.

Auth: single-user, `org_id` stamped. No tenant-isolation suite beyond one leak test.

### D3. Later slices (not the Slice-0 contract)

- **Slice 1 — implemented, not calibrated:** company resolution + stint re-key; one research snapshot type; JobIntelligence including AL-02 and AL-22; official score from approved claims with dumb weights and coverage count (no composite below floor); RequirementClaim extraction; three-factor mobility; `exceeds_expectations` in the verdict table. Weights, coverage-floor N, coarse-fit K remain open (03 §5) — the milestone is “functions exist,” not “DoD satisfied.”
- **Slice 2 — calibrated:** 03 §5 items 1, 3, 6 measured on the golden set. Only then may Phase 1 be called done for claims + official score.
- **After that:** 03 §2 from Phase 1.5, still behind a green eval and the closed intake rule.

### D4. Flag registry seed (AL-13 + this round)

Each row: `(key, default_severity, brief_template, blocks_auto_approval, blocks_matching, valid_subject_types)`.

From 01/02/04 that Slice 0 or Slice 1 will actually write:

`possible_duplicate_stint`, `extraordinary_unverified`, `single_source_web`, `suppressed_by_critic`, `possible_deal_breaker`, `insufficient_identity`, `budget_truncated`, `needs_vision`, `needs_human` (document), `paraphrase_only_support`, `possible_ocr_identifier`, `concurrency.overlap_with`, `job_process_stale`, `exceeds_expectations`, `possible_progress_evidence_mismatch` (AL-47 — backlog to write, register now so the compiler can see it).

Do not invent keys outside this table.

### D5. Explicitly out of Slice 0

Vision model, critic, research gateway, company registry providers, embeddings, coarse match, Brief inheritance engine, party timers, PA, BD, sourcing, Temporal, LangFuse, partitioned tables, multi-agent supervisor, policy audit sampling, shadow scoring, fuzzy three-band identity, size-weighted overlap, frequency tripwire as a shipped nightly job.

---

## E. Eval catalogue additions (this round)

Add to 03 §1. Representative, not exhaustive.

**From the architecture review**

- Typed-fail / paraphrase-pass is logged separately; hallucination rate does not include it (RA-01).
- Rejected email claim stops matching in the same transaction via live query (RA-02).
- SameAs on two in-flight candidates with conflicting pair states opens a Decision and does not smash `UNIQUE(candidate_id, job_id)` (RA-03).
- Single-subject erasure verify query fails loudly on a planted survivor; no snapshots in the fixture (RA-04).
- Education overlapping employment does not emit a failing computed consistency claim (RA-09).

**From the 2026-09 document folder** (keep the files in `evals/golden/` as anonymized fixtures)

1. Text-layer email / URL ≠ visible identifier (Jure, Veljko, Dmitry) → `possible_ocr_identifier`; must not become the identity key.
2. JD with elapsed process dates (Procure Ai London 26.08 / Berlin 27.08 vs 2026-09-04) → `job_process_stale`; matching may proceed; submission warned or blocked.
3. Three-factor mobility clause (DE/UK remote, no visa, no relocation) × EU candidate outside DE/UK (Bianca, Jure) → Brief, not auto-exclude.
4. Non-EU candidate × no-sponsorship JD (Veljko × Procure Ai) → WorkAuthorization UNKNOWN / Brief, not a numeric penalty.
5. Overlapping paid-looking stints (Veljko BlueCat + trainer + Partizan; Jure Bitpanda FT→consultant + self-employed) → separate claims + concurrency flags both ways; no fusion.
6. Education inside a job (Nir 2017–2020 ∩ Matrix IT) → RA-09.
7. Vendor / product names in a CV (Orb, Twilio, Vena, OpenSearch) must not become employers.
8. Zero domain-overlap job (Catalyst InSAR × all five software / finance CVs) → no composite; requirement table of gaps.
9. `exceeds_expectations` (Jure × “all levels”).
10. Photo CV (Bianca) → zero appearance claims on the text path; `needs_vision` may raise.
11. Footer contacts on a JD (Catalyst `hello@catalyst.earth`) → not candidate identity keys.
12. Brand vs legal / client strings (CATALYST / PCI Geomatics; Orion Innovation / Ericsson; Matrix IT / Unit 8200). Unit 8200 is employer-context, not a protected-characteristic feature (P14).
13. Negative P14 case: photo and founder-gender-like signals produce **no** change in ranking (folder has a photo; no client-founder signal — still assert the probe is a no-op).

04’s own eval additions remain on the backlog list; they are not deleted.

---

## F. Schema deltas (merge into 01 §D on next full edit)

Additive only.

```
# B2 origin enum
origin += relayed     -- AL-10; never corroborates with candidate-origin for the same fact

# D2
claim.flags keys validated against flag_type_registry
evidence.origin includes relayed
span_validation: { tier: typed|paraphrase, result, metric_bucket }

# D3
-- identity match: LIVE query over contact/identity claims
-- do not implement as a Postgres materialized view
candidate_job.merged_into_id NULL   -- pair-level redirect, same semantics as candidate.merged_into_id

# D4
validation kinds may live on activity.kind until volume justifies validation_event
intelligence_run.version_manifest required at run start

# D5
score.breakdown JSONB reserved shape per AL-18
  { requirement_id, requirement_text, strength, outcome
    [strong|partial|gap|deal_breaker|UNKNOWN|exceeds_expectations],
    contributing_claims, weight, points_contributed }
  UNKNOWN → points_contributed null, weight excluded from denominator (AL-19)

# D6
flag_type_registry (key PK, default_severity, brief_template,
                    blocks_auto_approval, blocks_matching, valid_subject_types)

# documents
document.status / flags: needs_vision
research_snapshot.ttl_expires_at
```

`registry_ids` jurisdiction map (AL-06) and `CompanyWorkPolicyClaim` (AL-08) stay in 04 / backlog.

---

## G. Invariant restatements (authoritative)

Use these wordings when they differ from 01 §E.

- **E-i9 (additive).** Erasure of single-subject documents is complete and verify-fail-loud. Multi-subject research snapshots follow RA-04. The verify query must not report green across an unresolved shared-byte conflict.
- **E-i11 (replace last sentence’s “contain/entail”).** Evidence is tier-validated against an immutable extraction artifact at commit (RA-01). Only extractor agents see raw content. Required citations are validated against the served set.
- **E-i12 (BD clause).** Candidate specs and job teasers remain outward-projected and two-sided-anonymous. Safety is recipient exclusion + conservative generalization + human review, **not** a pool-size search (RA-05).
- **E-i13 (additive).** Redirects apply to pairs and to `job.hiring_company_id` as specified in RA-03. Unmerge of fused pipeline state is either structurally redirect-based or explicitly irreversible and human-gated.
- **E-i15 (new).** `intelligence/` persists nothing. `api/` is the only writer (E-i1) and the only module that opens the database for permanent records.

---

## H. Findings coverage (this round)

| ID | Home |
|---|---|
| RA-01 span tiers | 02-F5.3 · 01 E-i11 · 05 B |
| RA-02 live identity query | 02-F2.2 · 01 §D3 · 05 B |
| RA-03 pair/job collapse on merge | 02-F2.7 · 02-F8.1 · 01 E-i13 · 05 B |
| RA-04 snapshot cache + honest erasure | 02-F6.1 · 02-F9.7 · 01 E-i9 · 05 B |
| RA-05 k-anon universe | 02-F11.4 · 01 E-i12 · 05 B |
| RA-06 partition trigger | 01 §C4 · 03 §2 · 05 B |
| RA-07 cheap observability | 01 §D4/D6 · 03 §2 · 05 B |
| RA-08 intelligence/ no DB | 01 §C1 · 05 B |
| RA-09 education carve-out | 01 §F · 02-F3.6 · 05 B |
| RA-10 exceeds_expectations | 02-F7.8 · AL-20 · 05 B |
| RA-11 compliance tone | 03 §6 · 05 B |
| Slice-0 gate | 03 §2 annotated · 05 D |
| 2026-09 golden cases | 03 §1 · 05 E |

---

## I. What was considered and not changed

- Principles P1–P14 stand. No principle was disproved.
- `approved_view`, origin-aware corroboration, redirect-merge for **claims**, document-blind downstream agents, Brief item lifecycle, E-i8 (machine unwinds only machine state), E-i10 (no LLM numbers), E-i14 (fan-out as SQL) — unchanged.
- Client-scoped rejection memory, decision-value ranking as a *later* inbox rule, snapshot-as-document as a *later* research path — checked in 04 and still sound, just not Slice 0.
- AL-43 stays retracted: authority × recency already handles a downward live self-correction.
