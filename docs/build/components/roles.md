# Roles: close, reopen, delete

**Status:** built 2026-10-14 (x-ray B6)
**Code:**
- `core/maindscout/api/roles.py`
- routes `PUT /v1/jobs/{id}/state`, `DELETE /v1/jobs/{id}?remove_people=`
- `erasure.erase_candidate(..., suppress=False)`
- cockpit: `components/RoleControls.tsx` ("Close or delete" on the role page); closed roles folded on the Jobs list

## What
A role can be closed (on hold, filled, cancelled) or opened again. A role added by mistake can be deleted.

## Why
The owner (2026-10-13): "there is no way to delete the job or archive the job". Every role stayed open for ever, kept its sourcing running and counted on Today.

## How
- **Close** (`set_state`):
  - the sourcing plan is paused;
  - the role leaves Today and the open part of the Jobs list;
  - a line goes on the hiring company's timeline ("Role X: filled", with the note);
  - everything on the role is kept.
  - Reopening leaves sourcing paused until a person chooses how often to search.
  - An on-hold role's company stays off-limits (an active client); a filled or cancelled one does not, except through the 12-month rule for placements.
- **Delete** (`delete_role`), with "delete" typed to confirm. These go:
  - the hiring profile and intake notes;
  - the pairs and their history (the one exception, with erasure, to "pairs are permanent");
  - the sourcing plan, runs, queries and finds;
  - messages, decisions and Brief items about the role;
  - the ad, and its file when no other document uses it, so the same PDF uploaded again is read fresh.

  Spend stays in the ledger.
- **The people only its sourcing found** (`found_only_here`): known only from public profiles and on no other role. They are removed when the box is ticked, through erasure without the never-again list, so a later search may find them again. Someone with a CV always stays.

## Tests
`core/tests/test_xray.py::test_a_role_can_be_closed_and_a_mistaken_one_deleted`.
