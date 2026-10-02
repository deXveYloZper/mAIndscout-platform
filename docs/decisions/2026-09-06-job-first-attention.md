# 2026-09-06 — Job-first attention (reorder)

## Decision

Machine-read every document. Human time is spent first on people who might matter to a **live job**. Clear misses are parked, not reviewed. Sourcing exists to refill a thin priority queue for that job, and every sourced person takes the same ingest → triage path.

## Why

A filing cabinet that demands review of every CV, including the ~80% that will never be submitted, makes the product stale. Correctness machinery that is not attached to a requisition has nowhere to pay off.

## What did not change

- Claims, spans, identity caution, approved_view, OCR contacts, erasure.
- No composite score on a domain miss (Catalyst folder).
- Sourcing never writes official belief. It only creates documents and pairs.

## New order

0 ingest + job-first triage → 1 defendable match → 2 sourcing feeder → 3 Brief → 4 live desk → 5 depth.
