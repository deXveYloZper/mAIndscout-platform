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
- **`needs_vision`** is only a flag, never a model call. Raised when the text layer is missing or sparse (under 200 characters per page), a page holds an embedded image of at least 150×150 px (a photo or scan), or a page's layout is unsure (below). A photo is never interpreted.
- Supported: PDF and plain text. Anything else is refused (`UnsupportedMedia`); a corrupt PDF raises `UnreadableDocument`.

## Depends on
- [persistence.md](persistence.md): `document`, `extraction_artifact`.
- Library `pypdf` (pure Python, permissive licence).

## Used by
Milestone D (extract claims), which reads artifacts, never raw bytes.

## Contracts
`upload_document(session, blobs, org_id, data, filename, media_type, doc_type_hint)` → `(Document, reused)`; `extract_document(session, blobs, document_id)` → `ExtractionArtifact`. HTTP routes come with the API milestone.

## Tests
`core/tests/test_ingestion.py` (pure; two-column pages are generated in `tests/pdfs.py`, no real person's file), `test_documents.py` (database, generated PDFs), `test_real_artifacts.py` (runs every PDF in `test_artifacts`; skipped if the folder is absent; nothing is copied into the repo). Result on 2026-10-02: all 13 files (11 CVs, 2 job ads) upload and extract. Column reading on 2026-10-27, 46 test PDFs and the Ferrari interviewee's CV: 10 read in columns, no word lost, split or glued, all 245 dated lines still with their words; 1 page flagged unsure.

- **Letter-spaced text is repaired** (2026-10-05): some designer CVs store every letter as its own word ("S p a n i s h  ( n a t i v e )"), so no quote could ever match. A line that is mostly single characters is rejoined, with two or more spaces as word breaks; ordinary lines are untouched. `text_repair` is recorded with the reading, and a forced re-read refreshes a reading made before the current repair.
- **Two-column pages are read column by column** (2026-10-27, `text_repair` 3, [decision](../../decisions/2026-10-27-two-column-pdf-reading.md)): read across, a sidebar cuts into the main column's sentences ("...sul funzionamento eLingue Italiano..."), so quotes break. pypdf's layout mode shows where a gap runs down the page; each column is then read top to bottom, the left first, after a name set large over both columns. A narrow side that is mostly dates stays read across, each date with its job. A sentence over the page turn stays whole (the next page starts with the column the last one ended on), and in a document read in columns a long line repeated on several pages (a consent line) is kept once, on the last; other documents read exactly as before. The ordinary reading stays the reference for the words: layout mode only decides their order, and words it spaced apart ("T ECHNICAL", "Montre al") are joined back.
- **A glyph with no character behind it is dropped** (2026-10-30): the emoji bullets of Destinus's job ad read as NUL
  (`\x00`), which Postgres text cannot hold, so creating the job failed with a server error. Every extracted text, PDF or
  plain, is stored without NUL; nothing readable is lost. No stored reading held one (it could not be stored), so
  `text_repair` is unchanged.
- **Doubtful pages are reported, not fixed** (2026-10-27, owner: "if there is a problem or CV is probably unreadable or is split, we should report for manual user reading"): a page that looks split but has a line across its top or foot, or whose column reading would lose or add any character, is read across as before and adds `unsure_layout_pages:<n>` to `needs_vision`. The person page then marks the file "has images or a lossy layout: the text may be incomplete", for a person to read it.

## Known limits
- Word CVs, images and scans are not read yet (scans are flagged `needs_vision` and stay unread). Call transcripts in .docx are ([calls](calls.md)). The website's talent page accepts Word CVs, so this matters once the [website seam](../connections/website.md) is built.
- Images stored as inline PDF image data are not detected; embedded image objects are.
- Blob store is a local folder (`BLOB_DIR`, default `core/.blobs`); an S3-compatible store implements the same two methods later.
- Text order comes from pypdf. Two columns are read in order; three columns, or columns under a line across the page, are not (the latter are flagged). Downstream steps must still treat the text as raw material (the span check accepts a quote pieced from its places).
