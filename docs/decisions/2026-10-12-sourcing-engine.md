# The sourcing engine: how found people enter, and what sourcing may spend

**Date:** 2026-10-12 · **Decided by:** the owner (phase 1 approved, "go"; rules in [plan section 10](../next/PLAN.md)); the
mechanisms below were chosen in the build to follow those rules · **Status:** accepted, built

## Decisions

1. **A profile found on the web enters through the CV path, read with no model.** Exa's structured profile is turned
   into the CV reader's answer, and every value is located and quoted in the page text (`webprofile.EntityReader`). So
   the same identity rules apply (the same LinkedIn page is the same person, never a merge on a name alone), as do the
   span check, company links, the coverage gate, suppression and erasure. Facts are marked `independent_web`. Values
   that can't be quoted are left out, as for a CV.
2. **Public data only, and nothing paid about them yet.** Someone known only from public profiles gets no company
   research, no career profile, and no email or phone read from a page. Contact goes through a LinkedIn message the
   owner sends. Owner's words: "this is just a guide, from the platform to me, that I should contact this person".
3. **Sourcing has its own budgets, per role and for the desk,** outside the model budget, so a busy search month never
   stops the desk reading CVs. A new plan starts **paused**, so opening a role's tab never starts a paid search.
4. **Off-limits is derived, plus the desk's own list.** It covers:
   - every company with an open or on-hold role (an active client);
   - a client where we placed someone in the last 12 months;
   - the `off_limits` list.

   It applies to everyone a search could suggest, including the older desk search.
5. **"Stop" wins over everything.** It is permanent until a person lifts it with a reason. Someone who said stop is
   never suggested, drafted to or introduced, and never counts towards a role's target. A merge keeps the stop.
6. **The talent-release radar quotes company news only.** A signal's quote is the shortest stretch of one sentence
   from the company's name to the event. A quote that could name a person is dropped: any run of two or more
   capitalised words other than the company, a country, a known place, a month or a company word counts. A company
   name proposed by Exa's summary must look like a company (one word, a company word or acronym, or called a company
   in the article) before a company record is made. A first version that demanded whole sentences and English verbs
   found nothing in real German news (2026-10-12), hence the stretch.
7. **Results credit the first finder.** One `sourcing_hit` per role and person. "How far they got" is the furthest
   stage their pair ever reached, so an ending keeps the stages before it.

## New tables (migrations `0026`, `0027`)
- `sourcing_plan`: versioned; every change is a new row.
- `sourcing_run` and `sourcing_query`: what each search returned and cost.
- `sourcing_hit`: erased with the person.
- `off_limits`.
- `company_signal` (migration `0027`): news that a company is releasing talent.
- `permission`: erased with the person.
- New columns: `candidate.do_not_contact_at` / `do_not_contact_note`, and `org.settings`.
- `document.doc_type` may be `web_profile`.

## Covers
Phase 1 of the next build only. Client-facing sharing (the coversheet checking permission, the client desk) comes with
phases 2 and 4, each approved separately.

Pages: [sourcing engine](../build/components/sourcing-engine.md), [web discovery](../build/components/web-discovery.md),
[results and spend](../build/components/sourcing-results.md), [permission and stop](../build/components/permission-and-stop.md),
[talent-release radar](../build/components/talent-release-radar.md).
