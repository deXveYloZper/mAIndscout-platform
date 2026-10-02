# ADR: intelligence interface differs from the Workspace DTO; HTTP routes move to Milestone E

**Date:** 2026-10-02 · **Status:** accepted with the A–D sign-off

## Decision
1. `intelligence/` takes plain arguments (`text`, `artifact_id`, `annotations`, a model client) and returns dataclasses (`ExtractionOutcome`, `JobOutcome`), instead of the JSON `Workspace` / `WorkspaceResult` in `slice0/dto/workspace.schema.json`. The run id and manifest are owned by `api/process.py`.
2. The HTTP routes named in Milestones C and D (`POST /v1/documents`, `POST /v1/documents/{id}/process`) are built at the start of Milestone E, together with the rest of the API. C and D deliver the functions those routes call.

## Why
1. The rule the DTO exists for holds: `intelligence/` gets no database session and writes nothing (enforced by `tests/test_boundaries.py`). A JSON envelope adds a serialisation step with no consumer until the intelligence layer runs as a separate worker.
2. One HTTP layer built at once (with org header, auth token and error shape) is simpler than three partial ones.

## Revisit when
The intelligence layer moves to a separate worker or queue: then serialise to the DTO at that boundary.
