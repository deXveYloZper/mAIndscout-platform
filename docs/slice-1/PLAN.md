# Slice 1 — Defendable match

**Status: OPEN** since 2026-10-02 (Slice 0 gate green, [decision](../decisions/2026-10-02-slice-0-gate.md)).

Slice 0 already bands people. This slice makes the band explainable and the pair durable.

---

## User-visible result

On a job, each person has a gap table: every requirement → evidence / missing / conflict.
A pair cannot be deleted.
If official coverage is too thin, the product still refuses a composite number.
Residence, visa, relocation remain three facts.

## In scope

- Richer JobRequirementClaims on top of Slice 0 thin tokens
- Gap table UI
- Pair states naive (`seen`, `priority`, `review_later`, `we_passed`, `submitted`)
- Reserved `score.breakdown` shape without shipping weights
- Coverage floor
- Re-triage when a human approves a fact the band depended on

## Out of scope

- Brief
- Web sourcing
- Mail
- ATS
- Dual-score calibration

## Gate to unlock Slice 2

- [ ] Catalyst folder still cannot emit a composite
- [ ] Gap table, not a single number, is the default view
- [ ] Bianca is not auto-excluded for Romania
- [ ] Approving a missing-skill fact can move a band; the reason updates
- [ ] A pair cannot be deleted
