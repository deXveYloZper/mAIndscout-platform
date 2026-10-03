# Decisions: intelligence track accepted

**Date:** 2026-10-03 · **Decided by:** the owner (deXveYloZper) in chat. Recorded by Claude.

1. **Plan accepted**, built in the planned order starting with I1 ([../intelligence/PLAN.md](../intelligence/PLAN.md)). No further slices until this track's gates.
2. **Company research uses Grok** (xAI web search), **targeted by a predetermined fact list**: each search asks only for the facts the platform needs (domain, company type, founded date, funding rounds with dates and stage, headcount points with dates, status, locations, tech stack), never open-ended browsing.
3. **Company knowledge is a shared public tier**, reusable across future client organisations (and potentially monetisable) without exposing any org-private data: who a desk knows, notes and pipeline stay private. This is a deliberate exception to "org_id on every table" for public company facts only.
4. **University rank is merit evidence** that may carry weight, sourced from a cited ranking (see [career strength ADR](2026-10-03-career-strength.md)). Not over-engineered.
5. **Career strength ADR accepted:** personality, culture and vibes are never evaluated.

## Addendum (2026-10-03): no company tech stack

The owner decided company research must not try to find what technologies a company uses. Public signals (job ads elsewhere, blog posts, tool-detection sites) give vague and unreliable answers; only someone inside the company really knows. Stack is taken only from the desk's own job ad (hiring profile) and from what candidates write on their CVs. The research prompt forbids technologies, and "domains" means industries served, never technologies.
