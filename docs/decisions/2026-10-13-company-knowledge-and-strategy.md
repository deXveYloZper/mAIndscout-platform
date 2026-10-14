# Company knowledge by identity keys, and a staged search

**Date:** 2026-10-13 · **Decided by:** the owner (phase 1b approved, "go ahead with phase 1b"; [plan section 4b](../next/PLAN.md));
the mechanisms below were chosen in the build to follow it · **Status:** accepted, built

## Decisions

1. **A company is found by its keys before its name.** The keys are the website domain, Exa's company ID and the
   LinkedIn company page.
   - A new name with a known key becomes an alias.
   - A key held by another company is never moved: one "Same company?" card, decided by a person.
   - Two companies with one name and different Exa IDs stay two records.
   - Owner's words: "we need to ensure that we do not conflict or research same exact company twice".
2. **Exa for breadth, Grok for depth** (owner: "price vs value and accuracy").
   - An Exa company profile costs $0.001 by ID. A name search ($0.007) is accepted only when a key confirms it, because
     in a test of 10 companies it returned a similar-named company for small or regional firms.
   - Grok research ($0.094) only for hiring companies, live targets and employers of candidates about to be submitted.
3. **Exa profiles are read with no model**, from their fixed layout. Exa's AI summary returned web addresses as
   industries in a test. Executives, emails, phones and reviews are removed **before** anything is kept, recordings
   included (the rule that company research never holds people's names). The tech stack is never read.
4. **Two sources are compared, never merged.** Agreement clears `single_source_web`; disagreement sets the new flag
   `sources_disagree`, and a person sees both values with their sources.
5. **An agreement to be acquired is not an acquisition:** it is stored as active, with that detail.
6. **People found by Exa get their employers and a career reading.** They pass the role's gates first. Their employers
   are profiled by Exa ID, and the career reading is classified like a CV's; there is no paid university research.
7. **The talent DNA never stores anyone.** The hiring company's people are the client's: only titles, counts and
   companies are kept.
8. **Peers come from descriptive company searches,** built from the company's own profile. Exa's find-similar was tried
   on procure.ai and returned name look-alikes (3–30 staff); the descriptive searches returned the real competitors.
   Micro companies under 10 staff are left out.
9. **Search in tiers and batches; widen by the owner's choice.** Country-wide searches run only when opened. The
   exhaustion and widening thresholds are the plan's rules: batch 5, exhausted after 2 quiet searches or 80% already
   known, waiting 90 days, low yield under 1 relevant per 5 searches. Each widening is a plan version.

## New columns and flag (migration `0028`)
- `company.domain`, `exa_id` (unique), `linkedin` (unique), `exa_profile` (fields, never the page), `profiled_at`.
- `sourcing_plan.dna`, `rules`, `open_tiers`; `sourcing_query.company_id`, `relevant`, `known`.
- Flag `sources_disagree` (company facts), added to `slice0/registry/flag_type_registry.yaml`.

Pages: [company knowledge](../build/components/company-knowledge.md), [sourcing strategy](../build/components/sourcing-strategy.md).
