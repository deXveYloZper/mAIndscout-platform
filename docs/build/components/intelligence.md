# Intelligence (`intelligence/`): extraction, checks, triage

**Status:** built
**Slice / milestone:** Slice 0 / Milestone D
**Code:** `core/maindscout/intelligence/` (`llm.py`, `extract.py`, `spans.py`, `contacts.py`, `triage.py`), `core/maindscout/domain/stints.py`

## What
Pure logic that turns a document's text into **proposed** claims and places a person against a job in a band. It never touches the database.

## Why
The model may suggest, but nothing it says is trusted until checked mechanically and approved by a human (blueprint P-rules, Slice 0 handoff section 4). Keeping this layer database-free means a model mistake can never write itself into the record.

## How
- **`llm.py`:** one `complete_json` interface. `XaiClient` calls xAI Grok (`grok-4.20-0309-non-reasoning`, strict JSON schema, temperature 0, retries on 429/5xx, reads `XAI_API_KEY` from env or `core/.env`). `FakeClient` serves tests. Cost per document is recorded (about $0.007 per CV).
- **`extract.py`:** `extract_cv` and `extract_jd`. The model returns facts, each with a verbatim `quote`. Prompt version is recorded with every run. Dates: `2019-03` is month precision, `2019` is year-only; only an explicit `present` leaves a job open, and a job with **no stated end** is stored as ending in its start period (it is not "current"). Contacts also come from the file's own links (a `mailto:` is a clean, separate contact).
- **`spans.py` (typed span check):** the quote must really be in the text (tolerant of whitespace, case, ligatures); every date's year (and month) must be written in the quote; emails, phones and URLs must be in the text or a link; a tidied name must match the quote ignoring spaces and accents. A job-ad date with no year takes the document's own year and says so. A claim that fails is **left out** and reported.
- **`contacts.py`:** an email or LinkedIn that disagrees with the file's own link, or is a one-letter misspelling of the person's name, gets `possible_ocr_identifier`. Such a contact is never an identity key or a mail target until a human confirms it.
- **`triage.py`:** a band and a reason string, never a number. A distinctive must-have with no support in the person's skills or job titles (as a whole skill or a word inside one, e.g. "InSAR basics") gives `do_not_submit`; one supported gives `priority`; otherwise `review_later`. Country and city never kill a candidate (the function does not even take a location).
- **`domain/stints.py`:** concurrency flags use the vendored `slice0/domain/reconcile.py` rule with a one-month tolerance so an ordinary job change is not flagged. Two jobs are never fused within a document, and same-company overlaps across documents are flagged for a human, not merged.

## Depends on
- [contracts.md](contracts.md): claim and flag registries, `reconcile.py`, payload schemas.
- [ingestion.md](ingestion.md): the text and links it reads.

## Used by
- [process.md](process.md): the only caller; it commits what this layer proposes.

## Tests
`tests/test_intelligence_pure.py` (spans, contacts, triage); `tests/test_process.py` (through a fake model); `tests/test_live_artifacts.py` (real model on every file in `test_artifacts`; runs only with `RUN_LIVE=1`). `test_boundaries.py` fails if this package imports or writes to the database.

## Known limits
- Which requirements are "distinctive" is the model's call, steered by the prompt; it is the least stable part and is the first thing to check if a band looks wrong.
- Quotes that span awkward line breaks fail the check and the claim is dropped (about 0-4 items per CV in testing), a safe loss rather than a risk.
- Photos and scans are not read (`needs_vision` only). Paraphrase-only support is not implemented.
- Pairs are triaged from proposed, not approved, facts (by design in Slice 0).
