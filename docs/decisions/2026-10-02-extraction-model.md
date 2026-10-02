# ADR: extraction model and how its output is trusted

**Date:** 2026-10-02 · **Status:** owner chose xAI Grok; model and rules below are the builder's defaults

## Decision
- Provider xAI. Model `grok-4.20-0309-non-reasoning` for extraction: strict JSON-schema output, temperature 0, listed at $1.25 / $2.50 per million input/output tokens; measured about $0.007 per CV.
- The model proposes facts each with a verbatim quote. A mechanical check decides whether a claim is kept (quote in text, typed values in quote). The model is never asked whether it is right.
- The API key lives only in `core/.env` (git-ignored) or the environment.
- Everything is `proposed`. Triage uses proposed facts and outputs a band, never a score.

## Why
Cheap, fast and structured enough to run on every inbound file; the checks, not the model, carry the trust. A "non-reasoning" model is enough because the task is reading, not judging.

## Consequences / watch
- "Distinctive requirement" is a model judgement and drifted between prompt versions (python was once marked distinctive for a radar role). It is pinned by prompt `2026-10-02.3` and by the live test; re-run the live test after any prompt or model change.
- Swapping providers means one new class implementing `complete_json`.
- Real CVs are sent to xAI. Check the provider's data terms before using real candidate data beyond testing.
