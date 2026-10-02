# Slice 0 — Development handoff

**This is the master paper for building Slice 0.**  
Hand this file, plus `slice0/`, to engineering or a coding agent. Do not hand `01`–`05` as the sprint.

| Sibling | Role |
|---|---|
| [GATES.md](GATES.md) | Done / not done. Slice 1 is closed until this is green |
| [../VISION.md](../VISION.md) | What the company is building. Do not implement it from that file |
| [../ROADMAP.md](../ROADMAP.md) | What comes after the gate |
| `../../slice0/` | Schemas, registries, reconcile, OpenAPI, golden oracles |

Constitution if a mechanism is disputed: `05` wins over `01`–`04`. Principles: `00-README.md` P1–P14.

---

## 1. What Slice 0 is

A recruiter can:

1. Open or upload a **job**, then drop CVs **onto that job** (or into an unassigned pool)
2. See a person page and a job page filled with **proposed** facts, each pointing at a snippet
3. See each person banded against that job: `priority` | `review_later` | `do_not_submit`
4. Work an **Inbox that defaults to priority people on the job they have open** — three card types (diff, same-stint-or-two, contradiction)
5. Leave the ~80% misses parked. Opening them is allowed; the product does not demand it
6. Approve, reject, or type a correction
7. Trust that official facts do not silently change
8. Erase a single person and see the check fail if anything remains

Triage is a **band**, not a score. It may use proposed facts. It does not pin official belief.

It is **not**: a calibrated composite score, Brief, mail, ATS, vision models, embeddings, or web sourcing (that is Slice 2, and it reuses this same path).

---

## 2. Who does what in the software

```
cockpit  →  api/  →  database
              ↑
         intelligence/     (pure: workspace in, staged claims out)
```

- `intelligence/` never opens a database session. It receives a **Workspace** DTO and returns **WorkspaceResult**.
- `api/` is the only writer: documents, claims, observations, evidence, decisions, identity keys, erasure.
- `cockpit` is: jobs list, job page (requirements + people by band), person page, upload-onto-job, Inbox filtered by job + band. Three item renderers, no generic claim tile as the v1 inbox.

If a module under `intelligence/` imports a SQL session, that is a defect.

---

## 3. Facts, not “the CV as a blob”

A **claim** is one fact about one subject (a person, later a company or job).

Slice 0 claim types (payload schemas in `slice0/schemas/`):

| Type | Example |
|---|---|
| IdentityClaim | “Jure Domajnko” |
| ContactClaim | email / phone / LinkedIn / URL |
| CareerStepClaim | one stint at one company in one period |
| EducationClaim | one credential |
| SkillClaim | one normalized skill + last evidenced date |
| LocationClaim | place + stated vs inferred |
| JobRequirementClaim | one must / nice-to-have fact on a job (thin: skill token, location phrase, education phrase, process date) |

Shared envelope: org, subject, class (`observed`), payload, dates, precision, flags, status (`staged` → `proposed` → `approved` | `rejected` | `superseded`).

**The record is not the belief.** Every source may add an observation. The official view changes only through approve / reject / a born-approved human assertion.

Do not invent an eighth type. Add a fixture first, then an ADR.

---

## 4. Rules that will be treated as bugs if broken

These are shortened from 05 RA-01–RA-04 and the invariants. Full text stays in `05`.

1. **False merge is the catastrophe.** When unsure, keep two people. SameAs in Slice 0 is human-only.
2. **Text-layer contacts that look wrong** (`possible_ocr_identifier`) must not become match keys or mail targets until a human ContactClaim confirms them.
3. **Typed span check is mechanical** (dates, money, closed vocab, locator in the file). Paraphrase support is a separate, lower-trust flag. Do not blend them into one “hallucination rate.”
4. **Identity matching reads live claims** in the same transaction as the write. No materialized view. No backfill script that writes keys.
5. **Same company + overlapping dates** may be one stint. Same company + non-overlapping dates (boomerang) stay two stints. Concurrent roles at different companies stay separate and raise `concurrency.overlap_with` on both.
6. **Education overlapping a job is allowed.** Do not raise a consistency failure.
7. **Approved view does not mutate.** A new source that disagrees opens a **revision_diff** card. The old official view stands until the human acts.
8. **`relayed` origin does not corroborate `candidate`.** Two copies of the candidate’s own story are still one origin.
9. **Photo / appearance / gender / ethnicity** never become claims or rank. A photo on the page may raise `needs_vision` only.
10. **Footer contacts on a JD** belong to the company, not to a candidate.
11. **Erasure of a CV** deletes the single-subject file and the person’s rows. The verify query must fail out loud if survivors exist. Multi-subject web snapshots are out of Slice 0.
12. **`api/` is the only writer.**
13. **A CV uploaded onto a job creates a pair** with a triage band. The band is not a score and is not official belief.
14. **Inbox default is the open job + `priority`.** Cards for `do_not_submit` people are not in that default list. Identity/OCR cards on a *priority* person still sit on top of that list.
15. **Catalyst-style domain miss → `do_not_submit`.** Printing a composite percentage is a defect in every slice.

---

## 5. What to implement, in order

Do not start step *n+1* as a second product. Finish the tests for *n*.

### Milestone A — contracts in the repo

Copy or vendor `slice0/` into the application repo.

- `pytest slice0/domain/test_reconcile.py` stays green (8 cases).
- Flag and claim registries load as seed data. Unknown flag keys are rejected on write.

### Milestone B — persistence (unpartitioned)

Tables for: org, document, artifact (bytes + sha256), run, candidate, job, candidate_job (pair + `triage_band` + `triage_reason`), claim, observation, evidence, decision + decision_item, document_subject, not_same (empty use is fine), flag validation against the registry.

No Citus, no table partitions, no materialized identity view.

### Milestone C — upload + text layer

`POST /v1/documents` stores bytes, hashes, reuses by hash.  
Extract text (and PDF annotations: mailto / links). Persist `needs_vision` when layout looks lossy. Do not call a vision model.

### Milestone D — extract + typed spans + commit

`POST /v1/documents/{id}/process`:

1. Build Workspace DTO (`slice0/dto/workspace.schema.json`)
2. `intelligence/` returns staged claims
3. Typed span check; fail blocks that claim
4. Reconcile career steps with the pure function
5. `api/` commits atomically: claims + observations + evidence + run manifest
6. OCR-looking identifiers flagged; excluded from identity keys
7. If `job_id` was supplied: run **coarse triage** (see §11) and write `candidate_job.triage_band`
8. Return `ProcessDocumentResponse`

Identity: name + attributable, human-confirmed or clean contacts only. On ambiguity, create a new person and optionally an inbox note — do not merge.

### Milestone E — cockpit

- Jobs list + job page (requirements + people grouped by band)
- Upload onto a job, or into the unassigned pool
- Person page: timeline of proposed/approved facts + snippets
- Inbox: `GET /v1/inbox?job_id=&band=priority` default. Blocking identity/OCR on **priority** people first
- Three renderers exactly as `slice0/cockpit/review-items.md`
- Approve / reject
- A control to open `review_later` / `do_not_submit` on purpose — not the default home screen
- `POST /v1/claims` for a typed correction (born-approved)

### Milestone F — erasure

`POST /v1/subjects/candidate/{id}/erase`  
`GET .../erase/verify`  
Golden case: one CV, then zero survivors.

### Milestone G — golden folder

Run the 2026-09 PDFs against `slice0/evals/golden/*.json`.  
A run that writes `domainko@gmail.com` as a deterministic key **fails CI**.

API surface: `slice0/api/openapi.yaml` plus the job/pair/triage routes listed in §11. No mail, Brief, or sourcing routes.

---

## 6. Inbox cards (product, not decoration)

| Kind | When | Human action |
|---|---|---|
| `revision_diff` | Official view ≠ new view | Keep old or accept new |
| `duplicate_stint` | Two career steps may be one job | “Same stint” or “two stints” |
| `contradiction` | Two facts cannot both be current truth | Approve one; the other dies in the same request |

Concurrency across *different* companies is a flag on the person page in Slice 0, not a fourth card.

Snooze is out of Slice 0.

---

## 7. Golden documents (must / must_not)

Sources live with the attachments used in September 2026. Oracles: `slice0/evals/golden/`.

| Case | Must | Must not |
|---|---|---|
| Jure CV | Flag `possible_ocr_identifier` on the broken text-layer email | Use `domainko@` or `jure-domainko` as a match key |
| Veljko CV | Separate current-looking stints; `concurrency.overlap_with` | Fuse into one job; key on `wipiper.com` |
| Nir CV | Redis + Matrix jobs; Holon degree | `education_employment_overlap` failure; concurrency flag |
| Bianca CV | Email/phone extract; `needs_vision` allowed | Appearance / gender / photo claims |
| Dmitry CV | Corza + KPMG present; vision flag allowed | Quietly fuse KPMG Moscow + Toronto |
| Catalyst JD | Company is CATALYST / PCI Geomatics | Treat `hello@catalyst.earth` as a candidate |
| Procure Ai JD | `job_process_stale` when as-of is after 27 Aug 2026 | Hiring company = Revolut People |
| Five CVs × Catalyst | Each pair band `do_not_submit` | A composite fit number |
| Jure × Procure Ai | Band `priority` (or `review_later` if frontend evidence is called thin — never `do_not_submit`) | Auto-exclude on Austria |
| Dmitry × Procure Ai | Band `do_not_submit` or `review_later`, not `priority` | — |
| Bianca × Procure Ai | Not `do_not_submit` solely because the CV is in Romania | Silent discard on country |

A band is required. A composite score is forbidden.

---

## 8. Tech defaults (unless an ADR says otherwise)

- Language on `api/`: whatever the team already ships; Python is assumed for `intelligence/` because `reconcile.py` is Python.
- Postgres. `pgvector` may exist unused. Do not build embedding writes.
- One org isolation column (`org_id`) on every table. Header `X-Org-Id`.
- Auth can be a single-operator token in Slice 0. Multi-user SSO is not a gate.
- Job queue: any worker that can run `process_document`. Not Temporal.

---

## 9. What a coding agent must not do

- Open `02` and implement Feature 2 because it is next on the page
- Add Temporal, LangGraph, a critic, a research gateway, or a vision model
- Invent JSON fields not in `slice0/schemas`
- Treat 04’s amendment list as a sprint
- Declare the slice done because the UI “looks right”

One milestone per thread. Paste this handoff + the `slice0/` files for that milestone.

---

## 10. Definition of done

See [GATES.md](GATES.md). Until that list is checked by a human, Slice 1 does not start.

---

## 11. Coarse triage (Slice 0 matcher)

Not a score. A band + a short reason string.

Inputs: proposed JobRequirementClaims on the job + proposed Skill / CareerStep / Education / Location claims on the person.

Rules that must be coded as data, not as “the model thought”:

1. If the job’s distinctive must-have tokens (e.g. InSAR, D-InSAR, PSI, radar interferometry) have **zero** support in the person’s skills and titles → `do_not_submit`. Reason: `no_support_for_must_have:{token}`.
2. If at least one distinctive must-have is supported by a skill or a title token, and no hard process-kill applies → `priority`.
3. Else → `review_later`.
4. Country / city mismatch **never** by itself produces `do_not_submit` in Slice 0 (AL-22). It may appear in the reason as `location_unconfirmed`.
5. Never output a 0–100 number.

Distinctive tokens for the golden JDs are listed in `slice0/evals/golden/triage-*.json`.

New routes (add to OpenAPI when implementing):

- `POST /v1/jobs` (create from a JD document or empty)
- `GET /v1/jobs/{job_id}`
- `POST /v1/jobs/{job_id}/documents` (upload CV onto this job)
- `GET /v1/jobs/{job_id}/people?band=`
- `POST /v1/jobs/{job_id}/people/{candidate_id}/triage` (human override of the band)
- `GET /v1/inbox?job_id=&band=`

