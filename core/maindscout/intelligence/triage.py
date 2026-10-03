"""Coarse triage: a band and a reason, never a number.

Rules are data, not model judgement (docs/slice-0/HANDOFF.md section 11):
1. A distinctive must-have with zero support in the person's skills and titles -> do_not_submit.
2. At least one distinctive must-have supported -> priority.
3. Otherwise -> review_later.
4. A place or country mismatch never forces do_not_submit by itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ALIASES = {
    "nodejs": "node", "node.js": "node", "node js": "node",
    "reactjs": "react", "react.js": "react",
    "vuejs": "vue", "vue.js": "vue",
    "js": "javascript", "ts": "typescript",
    "d-insar": "insar", "dinsar": "insar",
    "persistent scatterer interferometry": "psi",
    "radar interferometry": "interferometry",
}


def canon(token: str) -> str:
    token = token.strip().lower()
    return ALIASES.get(token, token)


def _words(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9.+#\-]+", " ", text.lower()) + " "


@dataclass
class Triage:
    band: str  # priority | review_later | do_not_submit
    reason: str


def supports(token: str, skills: list[str], titles: list[str]) -> bool:
    """True if the token is one of the person's skills, or appears as a word in a skill or a job title.

    Alternatives written with a slash ("javascript/typescript") are supported by either one.
    """
    if "/" in token:
        return any(supports(part, skills, titles) for part in token.split("/") if part.strip())
    wanted = canon(token)
    haystack = {canon(s) for s in skills}
    if wanted in haystack:
        return True
    def whole(word: str) -> str:
        # A token is a whole word: "js" is not inside "next.js", "react" is not inside "reactive".
        return rf"(?<![a-z0-9.+#]){re.escape(word)}(?![a-z0-9+#])"

    blob = _words(" ".join(titles + skills))  # a skill like "InSAR basics" is evidence of "insar"
    for alias, target in ALIASES.items():
        if target == wanted:
            blob = re.sub(whole(alias), wanted, blob)
    return bool(re.search(whole(wanted), blob))


def triage(requirements: list[dict], skills: list[str], titles: list[str], process_stale: bool = False) -> Triage:
    """`requirements` are JobRequirementClaim payloads of the job."""
    distinctive = [
        r["normalized_token"] for r in requirements
        if r.get("distinctive") and r.get("strength") in ("must", "deal_breaker") and r.get("normalized_token")
    ]
    if not distinctive:
        return Triage("review_later", "no_distinctive_requirements")
    supported = [t for t in distinctive if supports(t, skills, titles)]
    if supported:
        return Triage("priority", f"supported:{','.join(sorted(set(supported)))}")
    return Triage("do_not_submit", f"no_support_for_must_have:{distinctive[0]}")
