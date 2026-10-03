# ADR (proposed): career strength is evidence, not vibes

**Date:** 2026-10-03 · **Status:** PROPOSED: needs the owner's acceptance before any strength level is shown. See [../intelligence/PLAN.md](../intelligence/PLAN.md).

## Context
The vision lists what the product refuses: "Personality, culture-fit, or vibe scores; protected characteristics inferred, weighted, or acted on; rank changed by a photograph; 'the model said so' as a guarantee." The owner (2026-10-03) wants every candidate understood for **career strength** (relevant experience, progression, stability, employer and domain history, education) before matching, and states that strength derived from a person's career is not what the ban targets. The blueprint already plans this as F7 "General Strength" under rule E-i10.

## Decision (proposed)
1. **Allowed:** career-strength dimensions derived from evidenced facts (dates, titles, employers and their public company facts, education records, stated achievements), each shown with its evidence and reason; an overall band only above a coverage floor; recruiter override with a recorded reason.
2. **Still refused, unchanged:** personality, values, culture fit, "vibe", appearance, protected characteristics, and anything inferred from a photograph.
3. **Judgement by versioned rules, not by the model:** the model classifies and extracts with citations; code composes levels and bands under a versioned rubric (E-i10). No model-produced numbers.
4. **Proxies are handled with care:** institution prestige and employer brand are shown to the recruiter with context; automated levels weigh the nature of the experience (ownership, length, progression) over brand names; neither ever excludes anyone on its own; a bias check runs on the eval set before a rubric version is promoted.
5. **Patterns that need context become questions:** short stints, gaps and consultancy time raise call questions; known company events (shutdowns, layoffs) soften them automatically.

## Consequences
VISION.md's "refuses" list gets one clarifying line when this is accepted. Recruitment AI is high-risk under the EU AI Act: the existing human gates, logging and explanations are the basis; the bias check and override log are added with phase I3.
