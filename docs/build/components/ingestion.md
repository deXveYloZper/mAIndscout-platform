# Ingestion: upload and text layer

**Status:** built
**Slice / milestone:** Slice 0 / Milestone C
**Code:** `core/maindscout/ingestion/pdf.py`, `core/maindscout/storage.py`, `core/maindscout/api/documents.py`

## What
Two steps. **Upload** stores the original file untouched and records it. **Extract** reads the file's text layer (and PDF links) into an `extraction_artifact`. Neither step makes any claim about a person or job.

## Why
Every fact must point at a snippet of the original (blueprint E-i, Slice 0 gate). So the original is kept immutable, and one stable text version of it exists for snippets to point into. Reading vs. believing stays separate: this step only reads.

## How
- **Upload** (`api/documents.upload_document`): hash the bytes (sha256); if this org already has that hash, return the existing document (`reused`); else write the bytes to the blob store under `sha256/ab/<hash>` and insert a `document` row (`status=stored`, `doc_type` from the hint: `cv`, `jd` or `other`).
- **Extract** (`api/documents.extract_document`): `ingestion/pdf.py` (pure, no database) returns text, link annotations, and a `needs_vision` verdict. The API writes one `extraction_artifact` (idempotent: a second call returns the same row), sets `document.needs_vision`, `as_of` (the file's creation date, else upload date) and `status=extracted`.
- **Text offsets:** pages are joined with a form-feed character. An evidence locator's `char_start`/`char_end` index into that text; the page is 1 + the form feeds before `char_start`.
- **Links:** every PDF link annotation is kept (`mailto:` as kind `email`, others as `link`). The visible email in the text and the hidden `mailto:` target can differ; spotting that is Milestone D's job, so both are preserved here.
- **`needs_vision`** is only a flag, never a model call. Raised when the text layer is missing or sparse (under 200 characters per page) or a page holds an embedded image of at least 150×150 px (a photo or scan). A photo is never interpreted.
- Supported: PDF and plain text. Anything else is refused (`UnsupportedMedia`); a corrupt PDF raises `UnreadableDocument`.

## Depends on
- [persistence.md](persistence.md): `document`, `extraction_artifact`.
- Library `pypdf` (pure Python, permissive licence).

## Used by
Milestone D (extract claims), which reads artifacts, never raw bytes.

## Contracts
`upload_document(session, blobs, org_id, data, filename, media_type, doc_type_hint)` → `(Document, reused)`; `extract_document(session, blobs, document_id)` → `ExtractionArtifact`. HTTP routes come with the API milestone.

## Tests
`core/tests/test_ingestion.py` (pure), `test_documents.py` (database, generated PDFs), `test_real_artifacts.py` (runs every PDF in `test_artifacts`; skipped if the folder is absent; nothing is copied into the repo). Result on 2026-10-02: all 13 files (11 CVs, 2 job ads) upload and extract.

## Known limits
- Word documents, images and scans are not read yet (scans are flagged `needs_vision` and stay unread).
- Images stored as inline PDF image data are not detected; embedded image objects are.
- Blob store is a local folder (`BLOB_DIR`, default `core/.blobs`); an S3-compatible store implements the same two methods later.
- Text order comes from pypdf and is not perfect for multi-column layouts; downstream steps must treat it as raw material.
