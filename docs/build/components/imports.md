# Import and export

**Status:** built (Slice 4, step 4)
**Code:** `core/maindscout/api/imports.py`, migration `0019` (`import_batch`, `import_row`), cockpit `app/import/`, `app/export/people/`

## What
- **Import from a CSV** (every ATS can export one) of candidates, or of clients (companies and their contacts).
  1. **Preview first.** Columns are recognised by common names. Each row is shown as ready, already here (same email or LinkedIn on the desk, or earlier in the file), or cannot use, with the reason: no name, no way to reach them, a malformed email, or erased earlier at their request. Nothing is saved yet.
  2. **Tick what you vouch for.** Ticked rows come in as **approved facts with the account holder as the source**: name, contacts, where they live (with its country), current company and title, tags, and notes as a timeline note. Each person then passes the coverage rule and is linked to their company.
  3. **Free allowance per account: 100 candidates and 25 clients**, counted by rows actually imported. Ticking more than is left is refused.
  4. **Beyond the allowance: a quote**, at our measured compute per record (from the cost ledger: reading, classifying, a share of company research) × **1.9**. Accepting it records the order and holds those rows; they're verified before they become facts.
- **Outside freshness is never trusted.** The file's "last contacted" is kept as a timeline note ("not counted as contact"), so freshness starts from what happens here.
- **Export is always free:** everyone on the desk as CSV (name, contacts, location, current role, tags, jobs and bands, last contacted, facts last verified). A cell that starts like a formula (`=`, `+`, `-`, `@`) is written as text, so a spreadsheet never runs it.

## Why
The owner's decision ([source of truth and imports](../../decisions/2026-10-04-source-of-truth-and-imports.md)): about 100 candidates and 25 clients is what one person can reliably vouch for. Beyond that, data is a guess and must be verified as paid work. Export keeps trust and meets data-protection law.

## How
- Upload: UTF-8 (BOM tolerated), comma, semicolon or tab separated (sniffed), up to 10 MB (never buffered beyond it) and 20,000 rows (a longer file is refused, not cut).
- Duplicates are checked against the desk's contact facts. People erased at their request are recognised through the suppression list (by contact hashes) and refused.
- Imported claims are written with `review.assert_claim` (born approved, human assertion), exactly as if the recruiter had typed them.
- Erasure deletes a person's import row (it holds their name and contacts).

## Depends on
[review.md](review.md), [companies.md](companies.md), [relationship-memory.md](relationship-memory.md), [coverage-gate.md](coverage-gate.md), [erasure.md](erasure.md), [tasks-and-costs.md](tasks-and-costs.md) (cost ledger for quotes).

## Contracts
- `POST /v1/imports` (multipart: `file`, `kind`) returns a preview.
- `GET /v1/imports`, `GET /v1/imports/{id}`.
- `POST /v1/imports/{id}/import {row_ids}`.
- `POST /v1/imports/{id}/quote/accept`.
- `GET /v1/export/people.csv`.

## Tests
`core/tests/test_imports.py` (8):
- columns are recognised;
- the preview says what each row is, and nothing is imported yet;
- ticked rows become approved facts, and outside freshness is only a note;
- the free allowance is enforced, with only a quote beyond it;
- clients come in with their contacts;
- people erased at their request aren't taken in again;
- a file without a name column is refused, showing the columns seen;
- export is always free.

e2e: import from a CSV, then the export download.

## Known limits
- The paid analysis of held rows is recorded and held; the processing pipeline for it (verification through outreach and research) comes later.
- One ATS's API connector isn't built; CSV covers every ATS.
- Payment collection isn't built; the quote is recorded.
