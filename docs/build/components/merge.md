# Same person (merge)

**Status:** built
**Slice / milestone:** follow-up to the inbox review (owner, 2026-10-06)
**Code:** `core/maindscout/api/merge.py`, cockpit inbox "Who is this?" card and person page

## What
Two records of one person made one, on a human's word: "Same person: merge" on a "Who is this?" card. The older record is kept; everything of the other moves onto it. "Undo the merge" on the person's page puts everything back. "Different people" is remembered, so nobody merges them later by mistake.

## Why
A CV read before a name was known, or the same person sent twice with no contact in common, made two records that the desk could only acknowledge ("Understood"). Merging is never automatic: a wrong merge is worse than a duplicate.

## How
- Facts move to the kept record; a fact both had (same natural key) is kept once, the copy superseded (an approved copy beats a proposed one).
- Documents, Brief questions (an open duplicate is set aside), notes, tags, client blocks, messages, call reviews, import rows, score snapshots and open questions move.
- Jobs: a pair moves; on a job both were on, the kept pair stays, takes the further stage, and the other pair's history moves onto it (the empty pair row is the one other place a pair may be deleted, besides erasure).
- The "Who is this?" questions about only these two are answered; the merged record points to the kept one (its page redirects) and leaves the people list.
- `person_merge` records every moved row and what it was before; undo uses it. Changes made since to moved rows stay with them.
- Then: career profile rebuilt, coverage and matching run once. Erasing the person erases both records and the merge record.

## Contracts
- `POST /v1/candidates/{id}/merge` `{other_id}`; `POST /v1/merges/{id}/undo`; decision action `different` on an identity note (records `not_same`, which refuses a later merge).
- Table `person_merge` (migration 0025). Person page fields `merged_into`, `merges`.

## Tests
`core/tests/test_merge.py`: everything moves onto the older record with one person on the job and no history lost; undo restores facts, jobs and the open question; "different people" blocks a later merge; erasure removes both records.

## Known limits
- No automatic merging (the owner chose the button only).
- A merge on a card that names several possible people is not offered; open both pages instead.
