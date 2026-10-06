# mAIndScout — Slice roadmap

Work proceeds slice by slice. A later slice is **readable now** and **forbidden to start** until the previous gate is green.

Vision: [VISION.md](VISION.md)  
Current build: [slice-0/HANDOFF.md](slice-0/HANDOFF.md)  
Gate checklist: [slice-0/GATES.md](slice-0/GATES.md)  
Why the order changed: [decisions/2026-09-06-job-first-attention.md](decisions/2026-09-06-job-first-attention.md)

---

## The line that must not move

The machine reads every file.  
A human spends time on a person **because that person might matter to a live job** — not because a CV arrived.

If a piece of work does not (a) put the next relevant person in front of the desk, or (b) make the next call with that person shorter to run, it is not next.

## Attention rule (product, all slices)

| Band | Meaning | Human time |
|---|---|---|
| `priority` | Plausible for a live job; facts that block acting get Inbox cards **now** | First |
| `review_later` | Not a clear miss, not a clear fit; parked | After priority is empty |
| `do_not_submit` | Hard miss on this job (wrong profession, failed must-have with evidence) | Not unless they open the file |
| `unassigned` | No live job attached | Hidden from the job Inbox |

~80% of inbound should land in `do_not_submit` or `review_later` and **not** demand a review session.

Triage may use **proposed** facts. It does not pin official belief. Approving a fact is still a human gate. A band is not a score.

## Slice map

| Slice | Name | User-visible result | Starts when | Plan |
|---|---|---|---|---|
| **0** | Ingest + job-first triage | Upload JD and CVs onto a live job; facts extracted; each person banded; Inbox shows priority first; wipe a person | Now | [slice-0/HANDOFF.md](slice-0/HANDOFF.md) |
| **1** | Defendable match | Gap table; pairs persist; coverage floor (no fake composite); mobility as three facts | Slice 0 gate green | [slice-1/PLAN.md](slice-1/PLAN.md) |
| **2** | Sourcing feeder | When a job’s priority queue is thin, a bounded search feeds **the same** ingest + triage | Slice 1 gate green | [slice-2/PLAN.md](slice-2/PLAN.md) |
| **3** | Brief | Call checklist on **priority** people; tick → official fact; items stay dead | Slice 2 gate green *or* Slice 1 green if inbound is already enough | [slice-3/PLAN.md](slice-3/PLAN.md) |
| **4** | ATS core and import | Relationship memory; full pipeline to placed; client feedback and block; freshness; import 100 / 25 free, more as paid analysis; drafts with reply halt (rescoped 2026-10-04: [decision](decisions/2026-10-04-source-of-truth-and-imports.md)) | Slice 3 gate green | [slice-4/PLAN.md](slice-4/PLAN.md) |
| **5** | Depth | Company resolution, research snapshots, critic, embeddings, BD two-stage | Slice 4 green **and** a desk running live reqs | [slice-5/PLAN.md](slice-5/PLAN.md) |

Slice 3 may start in parallel with Slice 2 only if a human records that inbound volume is already enough. Sourcing does not block the Brief if the desk is already talking to priority people.

Constitution (`01`–`05`) describes target mechanisms. It does not describe this order.

## What is explicitly not a slice

- Temporal / workflow engine as a prerequisite
- Vision/OCR model in Slice 0 (`needs_vision` flag only)
- Dual official/provisional scoring theatre
- “Interviewing platform”
- Building sourcing before a matcher exists to receive the results

Note (2026-10-06): "replacing the client's ATS" was struck from this list. Since [the source-of-truth decision](decisions/2026-10-04-source-of-truth-and-imports.md), mAIndscout is the desk's own system of record.

## How a gate is declared green

The slice owner records in `docs/decisions/`: date, eval command, result, golden folder, accepted holes (empty for identity keys and for Catalyst-as-priority).

A coding agent may not declare a gate green.
