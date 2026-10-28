"""What each action the desk's pages send means, in the words of the button (for the activity log). Every write route
has its words here (a test checks it); one not listed would show as its method and route."""

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
    ("POST", "/v1/jobs/{}/work-lines"): "Read the role's work lines again",
    ("POST", "/v1/jobs/{}/work-lines/confirm"): "Confirmed the role's work lines",
    ("POST", "/v1/jobs/{}/work-lines/add"): "Added a line of the role's work",
    ("POST", "/v1/work-lines/{}/edit"): "Changed a line of the role's work",
    ("POST", "/v1/jobs/{}/work-readings"): "Read the role's people again against its work lines",
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
    ("POST", "/v1/jobs/{}/people/{}/viewed"): "Opened a suggestion's profile",
    ("POST", "/v1/jobs/{}/people/{}/linkedin-email"): "Said which person LinkedIn's email is about",
    ("POST", "/v1/jobs/{}/people/{}"): "Put a person on the role",
    ("POST", "/v1/decisions/{}/resolve"): "Answered an inbox question",
    ("POST", "/v1/claims/{}/approve"): "Approved a fact",
    ("POST", "/v1/claims/{}/reject"): "Rejected a fact",
    ("POST", "/v1/claims"): "Typed a fact",
    ("POST", "/v1/candidates/{}/documents/{}/approve-all"): "Approved every fact from a CV",
    ("POST", "/v1/documents"): "Uploaded a file",
    ("POST", "/v1/documents/{}/process"): "Read a file again",
    ("POST", "/v1/candidates"): "Added a CV to the pool",
    ("POST", "/v1/companies/{}/merge"): "Merged two companies",
    ("POST", "/v1/companies/{}/research"): "Asked for company research",
    ("PUT", "/v1/companies/{}/keys"): "Set a company's website or LinkedIn",
    ("POST", "/v1/companies/{}/contacts"): "Added a contact at a client",
    ("DELETE", "/v1/contacts/{}"): "Forgot a contact at a client",
    ("POST", "/v1/companies/{}/activities"): "Logged a call, email or note with a client",
    ("POST", "/v1/off-limits"): "Put a company off-limits",
    ("DELETE", "/v1/off-limits/{}"): "Took a company off the off-limits list",
    ("POST", "/v1/blocks/{}/lift"): "Lifted a client's block on a person",
    ("POST", "/v1/candidates/{}/merge"): "Merged two people",
    ("POST", "/v1/merges/{}/undo"): "Undid a merge of two people",
    ("POST", "/v1/candidates/{}/tags"): "Tagged a person",
    ("DELETE", "/v1/candidates/{}/tags/{}"): "Removed a tag from a person",
    ("POST", "/v1/candidates/{}/activities"): "Logged a call, email or note with a person",
    ("DELETE", "/v1/activities/{}"): "Removed a logged call, email or note",
    ("POST", "/v1/candidates/{}/permission"): "Recorded what a person said yes to",
    ("POST", "/v1/candidates/{}/stop"): "Recorded that a person asked not to be contacted",
    ("POST", "/v1/candidates/{}/stop/lift"): "Lifted a person's request not to be contacted",
    ("POST", "/v1/candidates/{}/bring-back"): "Brought back an archived person",
    ("POST", "/v1/candidates/{}/transcripts"): "Added a call transcript",
    ("POST", "/v1/call-reviews/{}/apply"): "Approved lines from a call",
    ("POST", "/v1/call-reviews/{}/dismiss"): "Dismissed a call review",
    ("POST", "/v1/call-reviews/{}/retry"): "Read a call transcript again",
    ("POST", "/v1/brief/{}/answer"): "Answered a question on a person's Brief",
    ("POST", "/v1/brief/{}/asked"): "Marked a Brief question as asked",
    ("POST", "/v1/brief/{}/dismiss"): "Dismissed a Brief question",
    ("POST", "/v1/subjects/candidate/{}/erase"): "Erased a person",
    ("POST", "/v1/imports"): "Started an import",
    ("POST", "/v1/imports/{}/import"): "Imported the ticked rows",
    ("POST", "/v1/imports/{}/quote/accept"): "Ordered the paid analysis of an import",
    ("POST", "/v1/messages"): "Drafted a message",
    ("PATCH", "/v1/messages/{}"): "Edited a draft message",
    ("POST", "/v1/messages/{}/mailbox"): "Put a draft in the mailbox",
    ("POST", "/v1/messages/{}/sent"): "Marked a message as sent",
    ("POST", "/v1/messages/{}/replied"): "Marked a message as replied",
    ("POST", "/v1/mailbox/connect/{}"): "Connected a mailbox",
    ("DELETE", "/v1/mailbox"): "Disconnected the mailbox",
    ("POST", "/v1/mailbox/sync"): "Checked the mailbox now",
    ("POST", "/v1/members/invites"): "Invited someone to the desk",
    ("PATCH", "/v1/members/{}"): "Changed a member's role",
    ("DELETE", "/v1/members/{}"): "Removed someone from the desk",
    ("POST", "/v1/members/{}/reset"): "Made a new sign-in link for a member",
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


def line_of(path: str) -> str | None:
    """The requirement, line of work or fact a route acts on, when its path names no role (the log finds its role)."""
    m = re.match(rf"^/v1/(?:requirements|work-lines|claims)/({_UUID})", path)
    return m.group(1) if m else None
