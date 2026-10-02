# Process document (`api/process.py`)

**Status:** built
**Slice / milestone:** Slice 0 / Milestone D
**Code:** `core/maindscout/api/process.py`

## What
`process_document` takes a stored document and, in one transaction, writes what [intelligence.md](intelligence.md) proposed: a run, people or a job, **proposed** claims with evidence, flags, review decisions, and (when a job is given) the person-job pair with its band.

## Why
`api/` is the only writer. Doing the whole commit in one place means a failed run leaves nothing behind, and every claim traces to a run, a document and a snippet.

## How
- **A CV** (`doc_type=cv`): extract; resolve the person; write each claim as `proposed` with an evidence row (document, page, character offsets or link, snippet) and an observation; flag career overlaps; make the pair and band if a job was given.
- **Identity:** a person matches an existing one only on a clean, attributable, subject-owned contact (email, phone, LinkedIn) that is not flagged, or one a human approved. Anything else makes a **new** person. Same name without a shared contact, a contact matching several people, or no readable name creates an `identity_note` decision. It never merges.
- **Same fact twice:** a claim with the same natural key adds an observation to the existing claim. If that claim is already approved and the new view differs, a `revision_diff` decision opens and the approved view stands.
- **Careers:** each listed job is its own claim. Different companies overlapping get `concurrency.overlap_with` on both. Same company overlapping across two documents is kept as two claims, both flagged `possible_duplicate_stint`, with a `duplicate_stint` decision.
- **A job ad** (`doc_type=jd`): creates a job (title, hiring company) and `JobRequirementClaim`s; process dates already passed (against the file's date) get `job_process_stale`. Contact details in the ad are never filed as a person.
- **Rerun:** a processed document is not read again; passing a different job just (re)triages the pair. `force=True` reprocesses.
- A document that is neither cv nor jd ends as `needs_human`. Span failures, cost and the model/prompt versions are kept on the run.

## Depends on
- [intelligence.md](intelligence.md), [ingestion.md](ingestion.md), [persistence.md](persistence.md), [writer.md](writer.md) (`add_claim` guards flags).

## Used by
Later: the HTTP route `POST /v1/documents/{id}/process` and the cockpit (Milestone E).

## Contracts
`process_document(session, blobs, client, org_id, document_id, job_id=None, force=False)` returns `ProcessResult` (run, subject, band, reason, claim and decision ids, span failures, cost). The caller owns the transaction.

## Tests
`core/tests/test_process.py` (fake model, real Postgres). Live: `RUN_LIVE=1 python -m pytest tests/test_live_artifacts.py`. On 2026-10-02 all 11 CVs and 2 job ads passed it for about $0.07 in total.

## Known limits
- Not yet reachable over HTTP; no queue, so it runs inline.
- `contradiction` decisions and approve/reject come with the cockpit milestone.
- Span failures live in the run's manifest, not their own table.
