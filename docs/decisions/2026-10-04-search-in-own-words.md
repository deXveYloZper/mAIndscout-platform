# Search in the recruiter's own words, best matches first

**Date:** 2026-10-04 · **Decided by:** the owner · **Status:** accepted, built

## Decision
Searching the desk is one search bar. The recruiter writes what they are looking for in their own words ("senior devops engineer in Germany with at least 3 years working with kubernetes"), and results come **best matches first**, ranked by how much each person meets. Choosing from lists stays only as an optional "Refine with filters".

This replaces the rule written into I6 that search results are "never ranked by fit".

## Why (owner)
Modern platforms work like this; clicking and choosing filters is slower and less natural than writing the search.

## How we keep it honest
- The search is read by a small model into criteria from the fixed lists, and the reading is shown ("Understood as: senior · DevOps / infrastructure · kubernetes 3+ years · lives in Germany"). Anything that is not a criterion is shown as "left out".
- Ranking is by code, not by the model: each criterion is met / partly / not met, with its reason. Kind of work and skills count most, then level, years, where they live and named companies, then background and industry. Each result shows its ✓ ~ ✗ and "meets N of M". No percentage or score is shown.
- Personality, culture, fit, nationality, age, gender or family are never criteria: they are dropped and shown as left out.
- Years per skill cannot be measured from a CV (skills are not dated): a skill with years is "met" when the skill is on the CV and the person has that many years of related work, and the reason says so.
- A search never changes anyone's band; people outside coverage are not searched.
