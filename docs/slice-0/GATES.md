# Slice 0 — Critical goalposts

Slice 1 ([../slice-1/PLAN.md](../slice-1/PLAN.md)) stays **closed** until every box below is true.  
A human records the green declaration in `docs/decisions/`.

## Engineering

- [ ] `pytest slice0/domain/test_reconcile.py` (or the vendored copy) is in CI and green
- [ ] Unknown `flags.*` keys are rejected on write
- [ ] `intelligence/` has no database session
- [ ] `api/` is the only writer of claims, identity keys, decisions, pairs, bands
- [ ] Identity match is a live query (or a denormalized table written in the same transaction as the claim). No `REFRESH MATERIALIZED VIEW`
- [ ] Typed span failure blocks commit of that claim
- [ ] Paraphrase-only support, if implemented at all, uses flag `paraphrase_only_support` and is **not** counted in the typed hallucination-rate numerator
- [ ] Coarse triage is a coded rule over tokens / requirements, not a free-form “fit percentage”

## Product

- [ ] A job can exist; a CV can be uploaded **onto that job**
- [ ] Each pair has a band `priority` | `review_later` | `do_not_submit` and a reason string
- [ ] Job page groups people by band
- [ ] Inbox default is `job_id` + `priority`. `do_not_submit` people are not in that list
- [ ] Upload stores the original and shows it next to a snippet
- [ ] Person page lists proposed and approved facts
- [ ] Inbox cards are the three renderers: `revision_diff`, `duplicate_stint`, `contradiction`
- [ ] Approve pins `approved_view`; a later disagreeing source opens a diff; the old view does not mutate
- [ ] Human-typed ContactClaim is born-approved and may become a match key
- [ ] Single-subject erasure + verify query: survivors list is empty on a one-CV person
- [ ] Human can override a band

## Golden folder (non-negotiable)

Against the September 2026 PDFs and `slice0/evals/golden/`:

- [ ] Jure: `possible_ocr_identifier` raised; `domainko@gmail.com` is **not** a deterministic identity key
- [ ] Veljko: BlueCat and Partizan (and the third current-looking stint) are separate CareerStepClaims; `concurrency.overlap_with` present; `wipiper.com` is not a key
- [ ] Nir: education during Matrix IT does **not** produce a computed failure
- [ ] Bianca: no appearance/gender/photo payload keys
- [ ] Catalyst: footer email/phone are not a candidate identity
- [ ] Procure Ai: hiring company is not “Revolut People”; `job_process_stale` fires when eval `as_of` is 2026-09-04
- [ ] All five CVs × Catalyst → `do_not_submit`. **No composite number**
- [ ] Jure × Procure Ai → not `do_not_submit`
- [ ] Bianca × Procure Ai → not `do_not_submit` *only because* of Romania

## Explicitly not required for this gate

- Calibrated composite score or `score.breakdown` weights
- Brief
- Mail
- Web sourcing
- Company registry resolution
- Vision model accuracy
- Multi-user auth
- Partitioned tables

If the UI is pretty and Catalyst is `priority`, or Jure’s broken email is a key, the gate is red.
