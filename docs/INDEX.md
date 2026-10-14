# mAIndScout — Documentation index

Read this first. Everything else has a job. Do not mix them.

| Document | Job | Who opens it |
|---|---|---|
| **[VISION.md](VISION.md)** | The complete platform. What we are building toward. Never a sprint. | Anyone who needs the product in their head |
| **[ROADMAP.md](ROADMAP.md)** | Slices, gates, what is allowed to start when | Product + engineering lead |
| **[build/](build/README.md)** | What is actually built: status, architecture, one page per component, log | Anyone working on the code now |
| **[slice-0/HANDOFF.md](slice-0/HANDOFF.md)** | Slice 0 specification (ingest + job-first triage); gate green 2026-10-02 | History; the base every later slice builds on |
| **[slice-0/GATES.md](slice-0/GATES.md)** | Slice 0 goalposts (all green) | Same |
| **[STAGES-AND-BUYER-BRIEF.md](STAGES-AND-BUYER-BRIEF.md)** | Stages in plain language + buyer pitch | Founder / sales / new team |
| **slice-1…5 `/PLAN.md`** | Slice plans. Slices 1–4 built and green (2026-10-03 to 10-05); Slice 5 locked until a desk runs live jobs. Order: match → source → brief → live desk → depth | Leads planning ahead |
| **intelligence/, access/, calls/, design/ `PLAN.md`** | Plans approved alongside the slices (intelligence track I1–I7, sign-in, call transcripts, desk design), all built except I7 | Same |
| **[decisions/2026-09-06-job-first-attention.md](decisions/2026-09-06-job-first-attention.md)** | Why review is job-first | Anyone who still thinks Slice 0 is a library |
| **`../slice0/`** | Executable contracts: schemas, registries, reconcile tests, OpenAPI, golden oracles | Implementers, CI |
| **`../00`–`05`** | Constitution and history. Principles, data model, features, eval catalogue, amendment logs | Architects when a mechanism is disputed |

## Rule

- **Vision** answers “what is this company building?”
- **Handoff + `slice0/`** answer “what do I type this week?”
- **Roadmap + later PLANs** answer “what is allowed after the gate?”
- **00–05** answer “why is the mechanism this shape?”

If those four answers live in one file again, we are back in the rewrite loop.

## Change discipline (short)

- No new claim type, flag, or table in Slice 0 without a fixture in `slice0/` and a note in `docs/decisions/`.
- A later slice does not start because someone finished a chapter in 02. It starts when the **previous gate** in ROADMAP.md is checked.
- Vision may grow. Handoff may not grow to match Vision. That gap is the point.
