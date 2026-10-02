# Erasure: forget one person

**Status:** built
**Slice / milestone:** Slice 0 / Milestone F
**Code:** `core/maindscout/api/erasure.py`, tables `erasure` and `suppression_registry` (migration `0002`), routes in `api/app.py`, cockpit `components/EraseForm.tsx`

## What
One action that deletes everything the platform holds about a person, followed by a check that looks again from scratch and lists anything left. A later upload of the same person is blocked before anything about them is stored.

## Why
"Forgetting someone is one action that fails out loud if anything about them is still findable" (vision). Blueprint E-i9 and 05 RA-04 (single-subject documents in Slice 0); 02 F1.9 (suppression check first).

## How
- **Deletes:** the pair history of the person's pairs; the person's claims with their observations and evidence; review decisions and their items; pairs with jobs; not-same records; document links; their documents, text artifacts and runs; the original files (unless another org's document uses the same stored bytes); the candidate row. Ids of the person are removed from other people's identity notes.
- **Pairs are permanent** (a database trigger refuses deletes); erasure is the only exception and switches the guard off for its own transaction only (`SET LOCAL maindscout.erasure = 'on'`).
- **Refuses rather than half-erasing:** if a document is also about someone else, other subjects' facts cite it, or a job was created from it, nothing is deleted and the error lists why (`409`).
- **Suppression:** each email, phone and LinkedIn is stored only as an HMAC-SHA256 with `SUPPRESSION_KEY` (created by `python -m maindscout init`, kept in `core/.env`). When a new CV yields one of those identifiers, the upload, its text and its file are deleted, no person is created, and only an encounter count is kept. Status `suppressed`.
- **Verify:** counts rows by person id and by the erased document ids, checks the files are gone, checks no identity note still points at them, and flags **another person carrying one of the erased identifiers** (the same human stored twice). Any finding is a survivor. Empty list is the only green.
- **The record:** `erasure` keeps who asked, an optional reason, document ids, counts and the verify result. No names, contacts or text.
- **Cockpit:** "Forget this person" at the foot of the person page; type `forget` to confirm. Success returns to Jobs with a confirmation; any survivor is shown as a failure.

## Depends on
[persistence.md](persistence.md), [ingestion.md](ingestion.md) (blob store `exists`/`delete`), [process.md](process.md) (calls the suppression check).

## Used by
[http-api.md](http-api.md): `POST /v1/subjects/candidate/{id}/erase`, `GET /v1/subjects/candidate/{id}/erase/verify`. [cockpit.md](cockpit.md).

## Tests
`core/tests/test_erasure.py` (11): one-CV person leaves nothing; job and other people untouched; record holds no personal data; planted survivor fails verify; same human stored twice is reported; identity-note pointers removed; bytes shared with another org kept; erased person re-uploaded is blocked; no key still erases and says suppression was skipped; entangled data refused; other org gets 404. Plus 2 API tests. Checked by hand on 2026-10-02 with a made-up person: erased from the cockpit, verify clean, re-upload `suppressed`.

## Known limits
- The original file is deleted before the database commit; if the commit then fails, rows return without the file. Run the erase again (verify will show the survivors).
- Lose `SUPPRESSION_KEY` and existing suppression entries stop matching. Back it up with the database.
- A suppressed upload still costs one model call (identifiers are only known after reading the file).
- No way yet to lift a suppression (for a person who later gives consent again); that needs a human decision type.
- Multi-subject documents (web snapshots) are out of Slice 0 and refused.
- Database backups are outside this mechanism; they need their own retention policy.
