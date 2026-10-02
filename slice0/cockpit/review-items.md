# Slice 0 review surfaces

Three item types. No generic claim card in v1. Inbox order is `created_at` ascending, with blocking Decisions (identity / OCR contacts / SameAs) pinned above.

Shared shell for every item:

- subject name
- claim type
- status
- evidence snippet + page
- actions: Approve (attention_grade=human_individual) | Reject (reason_code default `low_confidence`) | Snooze is out of Slice 0

## 1. `revision_diff`

When: approved_view hash ≠ newly reconciled view (F3.3).

Props:

```ts
type RevisionDiffItem = {
  kind: "revision_diff";
  claim_id: string;
  old_view: Record<string, unknown>;  // approved_view
  new_view: Record<string, unknown>;  // proposed
  changed_paths: string[];            // e.g. ["title_raw"]
  causing_observation: {
    origin: string;
    source_authority: string;
    snippet: string;
    observed_as_of: string | null;
  };
};
```

Render: two-column diff, changed paths highlighted. Approve pins a new approved_view. Reject leaves the old approved_view standing and rejects only the revision proposal.

## 2. `duplicate_stint`

When: `possible_duplicate_stint` on a pair of CareerStepClaims.

Props:

```ts
type DuplicateStintItem = {
  kind: "duplicate_stint";
  left: { claim_id: string; payload: Record<string, unknown>; snippet: string };
  right: { claim_id: string; payload: Record<string, unknown>; snippet: string };
};
```

Render: two-option choice. “Same stint” attaches the newer row as an observation on the older claim and supersedes the duplicate. “Two stints” clears the flag on both and keeps both approved-eligible.

Do not use this renderer for concurrency across different companies — that is a flag on each claim, shown as a note on the contradiction or as a future fourth type. Slice 0 may list concurrency flags on the candidate page without a dedicated card.

## 3. `contradiction`

When: two claims cannot both be current truth and the temporal-succession carve-out did not apply.

Props:

```ts
type ContradictionItem = {
  kind: "contradiction";
  left: { claim_id: string; payload: Record<string, unknown>; snippet: string };
  right: { claim_id: string; payload: Record<string, unknown>; snippet: string };
};
```

Render: side-by-side. One action approves one side and rejects/supersedes the other in the same request (`POST /claims/{id}/approve` with `body.supersedes_peer`). Never leave both approved.

## Routes the UI calls

- `GET /v1/inbox`
- `GET /v1/decisions/{id}` (first GET seals the batch)
- `POST /v1/claims/{id}/approve`
- `POST /v1/claims/{id}/reject`
- `POST /v1/claims` for a born-approved ContactClaim that corrects OCR

No score widget. No pair pipeline. No Brief.
