"""Which of a role's requirements the desk searches and rates by, which are for the conversation, and which are context
(owner, 2026-10-19: "why do we need to confirm a sentence that we cannot actually use in sourcing?"). Pure: no database.

- search: the desk checks it on a public profile or a CV (kind of work, level, years, industry, kind or size of
  company, named companies, where people live, languages, education, a skill a profile can name). These decide who
  is found and how they are rated, so they are confirmed once.
- conversation: no profile can show it (judgment, sensitivity, how they lead, pay, visas). Matching asks it, so it
  becomes a question on the call brief, and the answer becomes evidence. Nothing to confirm.
- context: about the job itself (where it is, the posting's dates). Shown, never rated.
"""

from __future__ import annotations

from typing import Any

SEARCH, CONVERSATION, CONTEXT = "search", "conversation", "context"
GROUPS = (SEARCH, CONVERSATION, CONTEXT)
CHECKED = ("role", "seniority", "employer", "domain", "target_company", "employment", "education", "language")


def group(p: dict[str, Any]) -> tuple[str, str]:
    """(group, why in a few words) for one requirement's payload."""
    cat = p.get("category")
    facet = (p.get("mobility") or {}).get("facet")
    if cat == "process":
        return CONTEXT, "the posting's own dates"
    if facet == "residence":
        return SEARCH, "sourcing searches and suggests only there"
    if facet in ("visa_sponsorship", "relocation_assistance"):
        return CONVERSATION, "asked on the call, never a reason to rule anyone out"
    if cat == "location":
        return CONTEXT, "where the job is"
    if cat in CHECKED:
        return SEARCH, "checked on a profile or CV"
    if cat == "skill":
        from maindscout.intelligence.extract import skill_name_token

        if p.get("normalized_token") or skill_name_token(p.get("text_raw")):
            return SEARCH, "a profile or CV can name it"
        return CONVERSATION, "no profile shows it: asked on the call"
    return CONVERSATION, "no profile shows it: asked on the call"
