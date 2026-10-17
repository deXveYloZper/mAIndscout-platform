# Evidence for strong matches: alternatives, employer evidence, and a deeper look

**Date:** 2026-10-17 · **Decided by:** the owner ("automatic on strong matches, name + company allowed, go ahead"),
after a review of the first real web finds for a role (AI Product Engineer, Procure Ai); the mechanisms below were
chosen in the build · **Status:** accepted, built

## Why
In the review, 16 of 24 people found at the right companies were marked "do not submit". They were real engineers,
but their public profiles never named Node.js. The ad asked for "React and/or Node.js" and was read as two must-haves,
and one of the two companies (Tacto) does not use Node.js at all. The owner, in their own words: "we do need to dig
deeper once we believe someone is a strong match … and look more evidence to support or discard that opinion based on
their public available info, or once we have found out more info about the company and then have plausible
information that if this company uses node.js for example but the person hasnt metioned it, it is reasonable to think
that they are working with that technology (or any other such key info that would make sense and is relevant, not
just technologies for example for non tech roles)".

## Decisions
1. **Alternatives in one sentence are one requirement.** Skills that share one quote of the ad, with "or", "and/or" or
   "/" between them, become one requirement written with a slash ("react/node.js"). A list closed by "or" ("React, Vue
   or Angular") is joined too. This is done in code after the ad reader (`extract.join_alternatives`), whatever the
   model returned, so the prompt and its recordings are unchanged. "JavaScript/TypeScript and familiar with React"
   stays two asks.
2. **Employer evidence: company tech stack and tools may now be read, from the company's own adverts only.** This
   reverses "never the tech stack" (company knowledge, 2026-10-13, decision 3) for this one purpose.
   - **Source:** one web search for the company's job adverts. A page counts only if it is on the company's own
     website, or is an advert for it (its name in the address and in the text).
   - **Reading:** one model call lists technologies, tools, methods and standards. Each item has an exact quote that is
     checked against the page; nice-to-haves are left out; nothing about any person is kept.
   - **Storage:** the new claim type `CompanyPracticeClaim` (public tier, schema in `slice0/`), with the advert as
     evidence. Re-read after 180 days.
   - **Use in matching:** a skill nobody wrote down is **likely** when the person's employer uses it in their area of work
     (engineering, product and design, commercial, operations, or company-wide), and they were there no more than two
     years before the advert.
   - **Weight:** likely is never proof. A core must-have that is likely lifts the person from "do not submit" to
     possible, never to strong. A broad skill that is likely counts as "ask on the call", never against anyone. A
     likely row is never an approved fact for coverage.
3. **A deeper look at strong matches, automatic.** Anyone found on the web who becomes a strong match on a role (by the
   rules or by the owner's choice) gets one evidence check, in the background. It runs again only after 90 days;
   "Check deeper" runs one by hand.
   - **Pages:** the links on their own profile (GitHub, their projects), then a web search for **their name with their
     current company**, with LinkedIn left out. This is the one place a search may name a person. Discovery still
     never does.
   - **Same person:** a page counts only when it is linked from their own profile, or names them in full together with
     one of their employers. A namesake lends nothing, and the model never sees such a page.
   - **What it keeps:** only what bears on the role's requirements, about their work. Each finding is quoted and checked
     against its page. Code refuses "not mentioned" as evidence against, a description of a company as the person's
     work, and any "against" that is not one of three named reasons: they left this kind of work, they work elsewhere
     now, or they say so themselves. (The first real runs, the same day, did all three wrong until this was added.) A supported skill becomes a proposed `SkillClaim` (origin `independent_web`), so the ordinary
     rules re-judge the match, and nothing is believed until a person approves it. What weakens the match is shown on
     the card for the owner to decide; the machine never turns it into a band (a band is rules over facts, never a
     model's opinion).
   - **Storage and erasure:** a page with findings is kept as the person's own `web_page` document. Each person gets
     their own copy, so erasing one never waits on another. A `web_page` counts as public data like a found profile,
     so a checked person is still "known only from public data": a suggestion until the owner decides, with no paid
     research about them. Pages without findings are never stored; only their
     address is listed in the check's result. Everything is erased with the person.
   - **Cost:** about 1 to 3 cents a person, inside the role's sourcing budget.

## New things
- Claim type `CompanyPracticeClaim` (`slice0/schemas/company_practice_claim.schema.json`, registry entry).
- Document type `web_page`, column `company.practices_at` (migration `0030`).
- Gap status `likely`; triage reason `likely_from_employer:<tokens>`.
- Tasks `read_practices` and `evidence_check`; cost purposes `sourcing_company_practices` and `sourcing_evidence_check`.
- Switches: `PRACTICES_AUTO` and `EVIDENCE_AUTO` (both default on; turn off while testing with real keys).

Pages: [employer evidence](../build/components/employer-evidence.md), [evidence checks](../build/components/evidence-checks.md),
[matching](../build/components/matching.md), [gap table](../build/components/gap-table.md),
[sourcing engine](../build/components/sourcing-engine.md).
