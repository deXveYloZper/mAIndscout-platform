"""What each action the desk's pages send means, in the words of the button (for the activity log). An action not
listed shows as its method and route."""

from __future__ import annotations

import re

_UUID = r"[0-9a-fA-F-]{36}"
# (method, route with {} for an id) -> what the person did
ACTIONS: dict[tuple[str, str], str] = {
    ("POST", "/v1/jobs"): "Added a role",
    ("POST", "/v1/jobs/{}/documents"): "Uploaded onto the role (ad or CVs)",
    ("POST", "/v1/jobs/{}/intake"): "Told the desk about the role (intake notes)",
    ("POST", "/v1/jobs/{}/tell"): "Tell the desk",
    ("POST", "/v1/jobs/{}/requirements"): "Added a requirement",
    ("POST", "/v1/jobs/{}/requirements/confirm"): "Confirmed the requirements",
    ("POST", "/v1/requirements/{}/edit"): "Changed a requirement",
    ("POST", "/v1/requirements/{}/strength"): "Changed must / nice of a requirement",
    ("POST", "/v1/jobs/{}/role-brief"): "Read the role brief again",
    ("POST", "/v1/jobs/{}/role-brief/answer"): "Answered a brief question",
    ("PUT", "/v1/jobs/{}/hiring-company"): "Set the hiring company",
    ("PUT", "/v1/jobs/{}/countries"): "Set where people must live",
    ("PUT", "/v1/jobs/{}/state"): "Changed the role's state (open, on hold, filled, cancelled)",
    ("DELETE", "/v1/jobs/{}"): "Deleted the role",
    ("POST", "/v1/jobs/{}/sourcing/run"): "Search now",
    ("POST", "/v1/jobs/{}/sourcing/strategy"): "Build the company list",
    ("POST", "/v1/jobs/{}/sourcing/widen"): "Widened the search",
    ("POST", "/v1/jobs/{}/sourcing/targets"): "Added a company to search",
    ("PATCH", "/v1/jobs/{}/sourcing/targets/{}"): "Pinned or removed a company on the list",
    ("PATCH", "/v1/jobs/{}/sourcing/plan"): "Changed how often, the target or the budget",
    ("PUT", "/v1/jobs/{}/sourcing/focus"): "Focused or widened the search",
    ("PUT", "/v1/sourcing/settings"): "Changed the desk's sourcing settings",
    ("POST", "/v1/jobs/{}/sourcing/people/{}/evidence"): "Asked for a deeper public check on a person",
    ("POST", "/v1/jobs/{}/people/{}/decide"): "Chose or passed on a suggestion",
    ("POST", "/v1/jobs/{}/people/{}/triage"): "Moved a person to another band",
    ("POST", "/v1/jobs/{}/people/{}/undo"): "Undid a choice",
    ("POST", "/v1/jobs/{}/people/{}/state"): "Moved a person in the pipeline",
    ("POST", "/v1/jobs/{}/people/{}/contacted"): "Marked as contacted",
    ("POST", "/v1/jobs/{}/people/{}/replied"): "Marked as replied",
    ("POST", "/v1/jobs/{}/people/{}/call-booked"): "Marked a call as booked",
    ("POST", "/v1/decisions/{}/resolve"): "Answered an inbox question",
    ("POST", "/v1/claims/{}/approve"): "Approved a fact",
    ("POST", "/v1/claims/{}/reject"): "Rejected a fact",
    ("POST", "/v1/documents"): "Uploaded a file",
    ("POST", "/v1/companies/{}/merge"): "Merged two companies",
    ("POST", "/v1/companies/{}/research"): "Asked for company research",
    ("PUT", "/v1/companies/{}/keys"): "Set a company's website or LinkedIn",
    ("POST", "/v1/candidates/{}/merge"): "Merged two people",
    ("POST", "/v1/subjects/candidate/{}/erase"): "Erased a person",
    ("POST", "/v1/imports"): "Started an import",
    ("POST", "/v1/messages"): "Drafted a message",
}
QUIET = ("/v1/auth/", "/v1/activity")  # sign-in steps are never logged; the log does not log itself


def describe(method: str, path: str) -> str | None:
    """The button's words, or None for an action that is not logged."""
    if path.startswith(QUIET):
        return None
    shape = re.sub(_UUID, "{}", path.rstrip("/"))
    return ACTIONS.get((method, shape)) or f"{method} {shape}"


def job_of(path: str) -> str | None:
    m = re.match(rf"^/v1/jobs/({_UUID})", path)
    return m.group(1) if m else None
