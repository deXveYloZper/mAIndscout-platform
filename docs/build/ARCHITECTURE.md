# Architecture as built

Target architecture lives in [../../01-system-blueprint.md](../../01-system-blueprint.md) (section C). This page shows what is **actually present**, and how the parts depend on each other. Update it whenever a component is added or a dependency changes.

## Big picture

```
 Public web                      Platform (this repo)
┌───────────────┐   ingest     ┌─────────────────────────────────────────────┐
│  mAIndscout   │ ───────────▶ │ cockpit ──▶ api/ ──▶ Postgres + file store   │
│  website      │              │               ▲                              │
│ (other repo)  │ ◀─────────── │          intelligence/  (pure, no DB)        │
└───────────────┘  published   └─────────────────────────────────────────────┘
                   projection
```

- The **website** is the public face and one source of applications and clients. See [connections/website.md](connections/website.md).
- The **cockpit** is the recruiter's UI. It only talks to `api/`, server-side ([connections/cockpit-api.md](connections/cockpit-api.md)).
- **`api/`** is the only thing that writes to the database.
- **`intelligence/`** is pure: a workspace goes in, staged claims come out. It never opens a database session.

## Components

Dependency direction is top to bottom: a component may depend only on those below it.
Local setup: [core/README.md](../../core/README.md).

| Component | Status | Page |
|---|---|---|
| Sourcing results and spend: funnel per strategy, cost per relevant / interview / placement, flags (next build, phase 1) | built | [sourcing-results.md](components/sourcing-results.md) |
| Sourcing engine: per-role plans (market map, modes, target, budgets), runs pool-first then web, off-limits and "stop" gates, the clock (next build, phase 1) | built, not yet run on a real role | [sourcing-engine.md](components/sourcing-engine.md) |
| Talent-release radar: news that companies are releasing talent, quoted, never a person's name (next build, phase 1) | built, not yet run on real news | [talent-release-radar.md](components/talent-release-radar.md) |
| Web discovery: Exa people search read into public-data people through the CV path, no model (next build, phase 1) | built | [web-discovery.md](components/web-discovery.md) |
| Permission and "stop": what a person said yes to; never contacted again (next build, phase 1) | built | [permission-and-stop.md](components/permission-and-stop.md) |
| Background tasks + cost ledger (I1) | built | [tasks-and-costs.md](components/tasks-and-costs.md) |
| Companies: shared records, who we know there (I1) | built | [companies.md](components/companies.md) |
| Company research: targeted public facts with sources (I2) | built | [company-research.md](components/company-research.md) |
| Coverage gate: archive people outside the desk's countries; light research for big consultancies | built | [coverage-gate.md](components/coverage-gate.md) |
| Career profiles: classify steps, rubric dimensions, QS rank, questions for the call (I3) | built | [career-profiles.md](components/career-profiles.md) |
| Hiring profiles: ad + intake notes + recruiter edits, by strength; hiring company; target companies (I4) | built | [hiring-profiles.md](components/hiring-profiles.md) |
| Matching v2: verdict per requirement, tier by visible rules, band follows the tier (I5) | built | [matching.md](components/matching.md) |
| People search and sourcing v2: profile filters, target-company alumni, demo desk (I6) | built | [people-search.md](components/people-search.md) |
| The Brief: call checklist, answers become approved facts, person-wide inheritance (Slice 3) | built | [brief.md](components/brief.md) |
| Relationship memory: activity timeline, last contacted / verified, tags as talent pools, client contacts (Slice 4) | built | [relationship-memory.md](components/relationship-memory.md) |
| Pipeline to placed; client rejection as a wall at that client (Slice 4) | built | [pipeline.md](components/pipeline.md) |
| Freshness: stale people and clients, re-contact list by value with reasons (Slice 4) | built | [freshness.md](components/freshness.md) |
| Import (CSV; 100 / 25 free, vouched; quote beyond) and free export (Slice 4) | built | [imports.md](components/imports.md) |
| Messages: drafts, Gmail / Outlook drafts, sent / reply detection, follow-ups (Slice 4) | built | [messages.md](components/messages.md) |
| Calls: transcripts read into one bulk-approved Call review; what people want, in matching and sourcing | built | [calls.md](components/calls.md) |
| Same person: merge two records of one person, undoable; "different people" remembered | built | [merge.md](components/merge.md) |
| Access: sign-in, two-step codes, desks, roles, members | built | [access.md](components/access.md) |
| Model recordings: record once, replay free (tests, e2e, eval) | built | [model-recordings.md](components/model-recordings.md) |
| Performance check: 3,000-person benchmark desk, timings and query counts | built | [performance.md](components/performance.md) |
| Sourcing feeder (Slice 2) | built (desk) | [sourcing.md](components/sourcing.md) |
| Coverage floor + reserved score (Slice 1) | built | [coverage.md](components/coverage.md) |
| Gap table (Slice 1) | built | [gap-table.md](components/gap-table.md) |
| Golden eval (Milestone G) | built | [golden-eval.md](components/golden-eval.md) |
| Erasure + suppression | built | [erasure.md](components/erasure.md) |
| Cockpit (recruiter UI) | built | [cockpit.md](components/cockpit.md) |
| HTTP API `/v1` | built | [http-api.md](components/http-api.md) |
| Review: human acts + read models | built | [review.md](components/review.md) |
| Process document: commit proposed claims | built | [process.md](components/process.md) |
| Intelligence: extract, span check, triage | built | [intelligence.md](components/intelligence.md) |
| Ingestion: upload + text layer | built | [ingestion.md](components/ingestion.md) |
| Writer: `api/` + registries | built | [writer.md](components/writer.md) |
| Persistence: tables + migrations | built | [persistence.md](components/persistence.md) |
| Contracts (vendored `slice0/`) | built | [contracts.md](components/contracts.md) |

Vendored contracts (from the blueprint; every claim write is checked against the schemas and registries, which have grown with each slice): `slice0/schemas`, `slice0/registry`, `slice0/domain/reconcile.py`, `slice0/api/openapi.yaml` (the original Slice 0 target; the live API is FastAPI's own). See [components/contracts.md](components/contracts.md).

## Dependency rules

1. `cockpit → api → db`. Nothing else writes to the database.
2. `intelligence/` imports no database code.
3. Public output (the website feed) is produced only from approved, human-marked data, and anonymised on the platform side.
