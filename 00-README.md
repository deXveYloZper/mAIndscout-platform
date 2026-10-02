# mAIndScout — Blueprint v4 (Definitive)
## 00 — README & Master Index

**Version 4.3 — documentation split: vision, slice roadmap, and Slice-0 handoff live under `docs/`. This file remains the constitution (principles + how 01–05 relate).**

If you are **implementing Slice 0**, do not start here. Start at [`docs/INDEX.md`](docs/INDEX.md) → [`docs/slice-0/HANDOFF.md`](docs/slice-0/HANDOFF.md) + `slice0/`.

This set (`00`–`05`) is the specification of mechanisms and history. Where 05 revises a mechanism, 05 wins; 01–04 remain the target architecture and the historical record. Product vision and build order are no longer this file’s job.

---

### The document set

| File | Role | Read it to… |
|---|---|---|
| **00-README** (this file) | Map, principles, change discipline | Know how to read, and how this stops being rewritten |
| **01-system-blueprint** | The system: thesis, trust model, architecture, data model, invariants, ontology, walkthrough | Understand what exists and why |
| **02-feature-specifications** | The mechanics: eleven features, fully corrected, in dependency order | Build any part correctly |
| **03-delivery-and-verification** | Eval catalogue, phases, risks, open questions, compliance, findings register | Execute, test, and verify nothing was lost |
| **04-post-v4-amendment-log** | Accepted amendments from post-v4 real-document stress testing (CVs, JDs, transcripts, BD, sourcing) | Apply everything learned since v4 was finalized, as frozen and sequenced by 05 |
| **05-review-amendments-and-build-gate** | Mechanism fixes from the architecture review; 04 freeze list; Slice-0 contract; 2026-09 golden cases | Know what to code first, and which 01–04 sentences are no longer implementable as written |

**Reading order by role.**

- Implementer (now): `docs/INDEX.md` → `docs/slice-0/HANDOFF.md` → `slice0/` → `docs/slice-0/GATES.md`. Open 05 only when a mechanism in the handoff is disputed.
- Product / founder: `docs/VISION.md` → `docs/ROADMAP.md`.
- Architect: 00 principles → 01 → 05 → 03 §5 → 04 (frozen backlog).
- Completeness vs design history: 03 §7, 04, 05 §H.

---

### The fourteen principles

Every mechanism in this specification traces to one of these. They were extracted the hard way — each is the root cause of a family of design errors found and fixed during review. When implementing, use them as the tiebreaker; when extending, test the extension against them before writing anything.

| # | Domain | Principle |
|---|---|---|
| P1 | Ingestion | One document ≠ one author ≠ one subject ≠ one language ≠ one version. Never assume cardinality. |
| P2 | Identity | Error costs are asymmetric: a false split is a nuisance; a false merge is the catastrophe. All thresholds lean toward "separate." |
| P3 | Claims | The record is not the belief. Observations accumulate freely; beliefs change only through the review gate. |
| P4 | Review | Human attention is scarce, graded, and must be demonstrably real — budgeted, measured, and audited. |
| P5 | Agents | Guarantees live in the harness, never in the prompt. Anything the system depends on is enforced or measured mechanically. |
| P6 | Research | The web is not a database. It is ephemeral, adversarial, and unversioned; each property needs its countermeasure. |
| P7 | Scoring | A score is a measurement, not a property: it has an instrument, a timestamp, an error bar, and comparability conditions. |
| P8 | Pipeline | The pipeline is a multi-party coordination protocol with memory, not a record of positions. |
| P9 | Brief | The Screening Brief is the interface of a loop, not a report: the system asks for the evidence it lacks; answers return as its best evidence. |
| P10 | Autonomy | Outreach is conversations, not actions. Silence is the only state in which automation may proceed; every human touch is a label. |
| P11 | Business development | The recruiter's economic position is an information-flow rule: anonymized in writing, revealed only in conversation — on both sides, until both sides have committed interest. |
| P12 | Scale | Fan-out is the database's job, never the application's. Growth is a hardware and partitioning question; anything that turns it into a rewrite is a bug. |
| P13 | Sourcing | Discovery and decision are different risk tiers. A signal barred from scoring can still be a legitimate, non-exclusive input to who gets found, provided it never gates out and never leaks into scoring. |
| P14 | Protected characteristics | Never inferred, never weighted, never acted on absent an explicit, legally-reviewed client instruction — symmetrically, regardless of which direction a presumed preference would point. |

Two operator-set standards apply across everything:
- **Proportionality** (compliance and beyond): every mechanism must justify itself against "would a sensible practitioner actually need this," not "can a risk be imagined."
- **Probe, don't punish:** anomalies in a candidate's story (concurrency, geography, extraordinary claims) become verification questions and gates — never silent penalties.

---

### Change discipline — why v4 is the last full rewrite

The revision loop terminates here by construction, not by hope:

1. **Findings are encoded as tests, not prose.** Nearly every design error found in review exists in 03 §1, 04's eval additions, and 05 §E as a golden-set case. A future regression is a failing eval, fixed by a change that passes the gate — not a blueprint rewrite.
2. **Mechanisms trace to principles.** A newly discovered edge case is first tested against P1–P14. If an existing principle covers it, the fix is local (an ADR + an eval case). 04 followed that pattern item-by-item; 05 freezes further accumulation until Slice 0 is eval-green, because the *rate* of ADR-sized adds had become a second spec. Only a *disproven principle* would justify reopening the blueprint.
3. **ADRs amend; evals gate; intake is closed.** All future decisions land in `docs/decisions/` as ADRs referencing the section they refine. Prompt, model, weight, policy, and schema changes ship only behind a green eval run. **No new claim type, flag, or entity enters 01–04 until `make eval` is green on the frozen Slice-0 set** (05 §A). The blueprint documents the *target* design; 04–05 document its evolution; 05 §D is the implementation contract.
4. **Open questions are named, not hidden.** 03 §5 lists everything deliberately undecided. Deciding one produces an ADR, not a v5. Load-bearing open questions (reconciliation weights, coverage-floor N, `as_of` precedence) cannot be waved through a Phase-1 “done” claim — 05 splits *implemented* from *calibrated*.

**Implementation will still surface issues — that is expected and priced in.** The claim of v4 is not "no further discoveries"; it is that further discoveries will be ADR-sized, because every load-bearing assumption has now been stated, stress-tested on real documents, and either fixed or explicitly parked.

---

### Status

Target architecture: everything in 01 and 02, as amended by the accepted items in 04, as *revised* by 05 RA-01–RA-11. Implementation contract: 05 §D (Slice 0) plus the files in `slice0/`. Deliberately open: 03 §5. Golden-set construction (03 §1, 04, 05 §E) is the first implementation task and is itself part of the specification. 04 records two retracted proposals (AL-00, AL-01) and 05 records the process correction that 04’s aggregate had to be frozen — kept deliberately.
