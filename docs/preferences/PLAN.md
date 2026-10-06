# Candidate preferences: what they want next, and matching that respects it

**Status: DRAFT**, waiting for the owner's approval. No model calls needed.

---

## User-visible result

On a call, the recruiter records what the person wants next in a few quick controls, not free text. For example: "no companies under 200 people", "no more early-stage start-ups", "hybrid or remote", "permanent only", "lead roles". Each answer becomes an approved fact, in the person's words, dated.

From then on, matching respects it. A job at a 40-person seed start-up is shown as unlikely for them: "they said no companies under 200 people; this one has about 40". A job at an established company that fits shows "fits what they want". Search and "Find more people" respect it too. Nobody is ever ruled out on a guess: if we don't know a company's size or stage, the match says "ask".

## Why

The owner's example: an engineer with strong start-up experience is matched, by evidence, to start-ups. If they say they are done with start-ups and want an established company, that is the newest and most important fact about them. Matching on their past against their stated wishes wastes everyone's call.

## In scope, in order

1. **Preferences as facts.**
   - A new claim type, `PreferenceClaim`, about a candidate. It is born approved (a human assertion from the call), quotes what was said, and is dated.
   - One fact per facet:
     - **Company size:** at least N people and/or at most N people.
     - **Kind of employer:** want or avoid start-ups, scale-ups, large companies, consultancies / outsourcers, public sector. These are the same categories the career profile already uses.
     - **Company stage:** want or avoid funding stages (seed, series A–B, later, public).
     - **Setting:** on site, hybrid and/or remote.
     - **Places:** where they will work: countries or cities, or "anywhere in …".
     - **Kind of work and level:** role families wanted or not wanted; level wanted.
     - **Employment:** permanent, contract, or either.
   - Each facet is **must** ("won't consider") or **prefer** ("would rather"). A newer answer to the same facet replaces the older one; the history is kept.
   - Erasure deletes them with the person.
2. **Capture in the Brief.**
   - The "What are they looking for next" question opens a small structured form: size bounds, employer kinds (want / avoid), stages, setting, places, role and level, employment, each marked must or prefer, plus their own words.
   - Saving creates the facts and re-matches the person at once.
   - Also available on the person page (Overview, "What they want"), editable at any time.
3. **Matching respects them** (new rules in `domain/matching.py`, data like the existing ones):
   - **must contradicted by known facts → unlikely.** Example: the company is known to have ~40 people and they said at least 200; or they avoid start-ups and the employer is classed as a start-up. The reason quotes what they said and what we know.
   - **prefer contradicted → stays in its band, with a note** ("would rather not: start-up").
   - **The company fact is unknown → ask.** Never assumed either way; it becomes a Brief question for the job ("How big is the team at …?") and a research request when credits allow.
   - **met → a visible "fits what they want" line** on the gap page and the person card. It's never a number and never lifts a band on its own.
   - Setting, places and employment compare with the job's own facts (remote or on-site where the ad says so, residence, contract or permanent). Where the ad is silent, it's a question.
4. **Freshness.**
   - Preferences older than the person's freshness window (6 months) are shown as "said …, 8 months ago". They still apply, but the Brief asks to confirm them again.
   - A newer answer replaces them.
5. **Search and sourcing.**
   - "Find more people" and search treat a must-preference as a filter: someone who said no start-ups is not proposed for a start-up job.
   - A one-line "why not shown" lets the recruiter see who was left out for a preference.
6. **Proof.**
   - Tests:
     - the owner's example (strong start-up history, now wants 200+ people: unlikely for a 40-person start-up, fits an established company);
     - an unknown company size gives "ask", not a rule-out;
     - prefer never changes the band;
     - a newer answer replaces the older;
     - stale preferences are re-asked;
     - search and sourcing respect must-preferences;
     - erasure removes them.
   - Docs: a preferences component page; matching rules; the Brief; persistence; STATUS; LOG.

## What it depends on
- **Company facts** (size, stage, kind) come from company research, which is paused while model credits are out. Until it runs again, many companies are "unknown", so preferences mostly produce "ask", the safe answer. With credits back, the 83 queued researches fill most of it in.
- Jobs: "remote / hybrid / on site" is read from the ad only when written. Otherwise it's a question for the hiring manager.

## Out of scope
- Salary as a matching rule (it's recorded as a Brief answer; comparing pay bands needs the job's pay range, which ads rarely state).
- Anything about personality, culture or "fit" (never a criterion, as before).
- Learning preferences automatically from behaviour (I7 territory, later).

## Gate
- [ ] The owner's example passes, end to end, through the Brief form.
- [ ] A must-preference contradicted by a known fact makes the match unlikely, with both sides quoted. An unknown fact asks.
- [ ] A prefer-preference never changes the band.
- [ ] Search and "Find more people" respect must-preferences, and say who was left out.
- [ ] Erasure removes preferences; the core suite is green.
