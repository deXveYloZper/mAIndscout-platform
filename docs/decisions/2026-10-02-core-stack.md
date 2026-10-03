# ADR: core stack and early simplifications

**Date:** 2026-10-02 · **Status:** direction agreed with the owner; details are the builder's defaults

## Decision
- Core in Python 3.12+ (FastAPI later), SQLAlchemy 2, Alembic, Postgres 16. Cockpit in Next.js.
- Work queue: Postgres-backed (`FOR UPDATE SKIP LOCKED`) when needed. **No Temporal, Langfuse or MinIO in Slice 0**; file storage is a pluggable blob store (local folder in dev, S3-compatible later).
- Platform lives in its own repo, separate from the public website.
- Flag keys are validated by `api/` (the sole writer), not by database triggers.

## Why
The blueprint's own Slice 0 handoff excludes Temporal; the pipeline is short and the heavy cost is LLM calls, not orchestration. A separate repo keeps personal data and deploys apart from the public site.

## Revisit when
Long-running conversations with timers appear (Slice 4): adopt Temporal behind the queue interface.
