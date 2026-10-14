# Permission and "stop"

**Status:** built (next build, phase 1)
**Slice / milestone:** next build, phase 1 ([plan](../../next/PLAN.md) S4)
**Code:**
- `core/maindscout/api/consent.py`
- table `permission`, and `candidate.do_not_contact_at` / `do_not_contact_note` (migration `0026`)
- cockpit: the person page's Permission panel and stop banner, and the "asked not to be contacted" tag on a role's queue

## What
- **Permission:** what a person said yes to, recorded as they gave it: to be put forward for this role, for other roles, or both. It also records how they said it (a message, a call, an email) and who recorded it.
- **Stop:** they asked not to be contacted.

## Why
The owner's rule (2026-10-12): people found on the web are public data only, a guide to contact them. Their CV, contact details and permission come from them. "Do not over engineer this GDPR" ([plan section 10](../../next/PLAN.md)). The plan's other rule: "stop" and erasure win over everything ([decision](../../decisions/2026-10-12-sourcing-engine.md)).

## How
- **Recording permission** needs a choice (this role, other roles, or both); this role needs the role itself. Every grant is a row, never edited, and goes on the person's timeline. Permission cannot be recorded for someone who said stop.
- **Stop is permanent** until a person on the desk lifts it with a reason (for example, "they got back in touch"). From the moment it is set:
  - the person is never suggested by a sourcing run or the desk search;
  - they never count towards a role's target;
  - they drop out of a role's Sourcing suggestions;
  - no message to them is drafted (email or LinkedIn), and they are never introduced to a client;
  - open drafts are cancelled (drafts placed in the mailbox are deleted there) and follow-ups are cleared;
  - the role's queue tags them "asked not to be contacted";
  - the stop and its lifting both go on the timeline.
- **A merge keeps the stop.** If either record said stop, the person did ([merge](merge.md)); undoing the merge restores each record's own state.
- **Erasure** deletes their permissions with everything else ([erasure](erasure.md)).
- `may_put_forward(candidate, role)` answers "do we have their yes for this role?". Nothing calls it yet: the coversheet (phase 2) will check it before a submission.

## Depends on
- [relationship-memory.md](relationship-memory.md): the timeline
- [messages.md](messages.md)
- [persistence.md](persistence.md)

## Used by
- [sourcing-engine.md](sourcing-engine.md)
- [sourcing.md](sourcing.md)
- [sourcing-results.md](sourcing-results.md): "interested" counts a recorded permission
- [messages.md](messages.md)
- [http-api.md](http-api.md)
- [cockpit.md](cockpit.md)

## Contracts
- `POST /v1/candidates/{id}/permission {job_id?, this_role, other_roles, how?, note?}`
- `POST /v1/candidates/{id}/stop {note?}`
- `POST /v1/candidates/{id}/stop/lift {note}`
- The person page carries `do_not_contact {at, note}` and `permissions[]`. A role's people carry `stopped`.

## Tests
In `core/tests/test_autosource.py`:
- someone who said stop is never suggested again: not by a run, not in the suggestions or the target, and no message to them and no introduction of them can be drafted;
- the desk search skips them;
- a permission moves them to "interested";
- erasure takes their finds and permissions.

## Known limits
- Their answer to a message is recorded by hand: "replied" on the message, then permission or stop here. Reading the reply into a suggestion is part of a later phase.
- No expiry on permission: it stands until the person says otherwise.
