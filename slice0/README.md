# Slice 0 — executable contracts

This folder is the executable source of truth for Slice 0 **code**.  
The paper a developer is handed: `docs/slice-0/HANDOFF.md`.  
Why the product exists: `docs/VISION.md`.  
What is forbidden until the gate: `docs/ROADMAP.md`.  
`00`–`05` explain mechanisms when the handoff is not enough.

If a coding agent invents a field that is not in `schemas/` or `registry/`, that is a spec change — refuse it until a fixture exists.

## Contents

| Path | Purpose |
|---|---|
| `schemas/` | JSON Schema for the six Slice-0 claim payloads + shared claim envelope |
| `registry/claim_type_registry.yaml` | class, natural key, volatility, review default |
| `registry/flag_type_registry.yaml` | AL-13 seed rows |
| `domain/reconcile.py` | Pure function. No DB. |
| `domain/test_reconcile.py` | Cases from 05 §D1 |
| `domain/fixtures/` | observations → expected view |
| `dto/workspace.schema.json` | Run workspace + process_document I/O |
| `api/openapi.yaml` | Slice-0 HTTP surface (`api/` is the only writer) |
| `cockpit/review-items.md` | Three item renderers |
| `evals/golden/` | Expected flags/claims for the 2026-09 folder |

## Agent protocol

1. `pytest /home/workdir/artifacts/slice0/domain` must pass before any extractor.
2. One milestone per thread. Paste this README + the files for that milestone, not 01–05 in full.
3. No Temporal, vision model, critic, research gateway, embeddings, or new claim types.

`pytest domain/test_reconcile.py` — 8 passed (2026-09-04).
