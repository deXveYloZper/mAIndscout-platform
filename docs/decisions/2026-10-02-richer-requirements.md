# ADR: richer job requirements (Slice 1 step 1)

**Date:** 2026-10-02 · **Status:** accepted (owner said "go" on the Slice 1 plan)

## Decision
Extend the `JobRequirementClaim` payload schema with **optional** fields only:
- `mobility` `{facet: residence | visa_sponsorship | relocation_assistance, countries?, offered?}`, one facet per row;
- `min_years` for seniority, `education_level` for education, `language` (with a new category `language`).

Job ads now yield, besides skills: seniority with minimum years, education level, languages, and the three mobility facts as three rows.

## Why
Slice 1 needs a gap table per requirement, and the vision insists residence, visa and relocation are three facts, not a location score (STAGES "Goalposts before Stage 2"; Procure Ai golden oracle `mobility_facts_when_extracted`, which is the fixture this change answers).

## Rules kept
- Every existing payload remains valid (no required field added, no field removed).
- Location never decides a band by itself (triage still takes no location).
- Each new value is checked against its quote like any other fact: a country, a "no visa" or a number of years must be written in the quote.

## Consequences
The golden eval's `mobility_facts_when_extracted` moves from INFO to a real check.
