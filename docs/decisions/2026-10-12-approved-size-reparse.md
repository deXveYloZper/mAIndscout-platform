# Re-reading approved company sizes

**Date:** 2026-10-12 · **Decided by:** the owner · **Status:** accepted, built (the re-read 2026-10-08; the hash fix 2026-10-12)

## Decision

`python -m maindscout research-recheck` may correct the **numbers** of an approved company head count when they were
misread from the fact's own words. This is a named exception to "an approved view is pinned at approval and never
changes" ([external code review](2026-10-05-external-code-review.md)).

## Why

On 2026-10-08 a live research run read Wise's "over 8.8 thousand employees" as **8 people**: the parser saw only the
digits. A person who approved that fact approved the words on the page; the 8 was a reading error, not their belief.
The owner chose to correct such numbers automatically rather than raise a review card per size: a card would ask a
person to confirm arithmetic.

## Exactly what may change

- Only `TeamSizeClaim` facts (the shared public company facts), and only their `min` / `max`.
- Only as recomputed by the current parser from the fact's own stored words (`raw`). The words, the source page, the
  quote, who approved it and when stay as they were.
- The stored `approved_view_hash` is recomputed with the view, so it always describes the view it sits next to.
- Every correction is printed by `research-recheck` with the words and the new range.

Everything else about an approved fact still changes only through a person (a revision card, a correction, a rejection).

## Known limits

The correction is printed, not recorded as an event on the fact. If corrections need an audit trail later, add one
before widening this exception to any other fact type.
