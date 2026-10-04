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
| Writer: `api/` + registries | in progress | [writer.md](components/writer.md) |
| Persistence: tables + migrations | built | [persistence.md](components/persistence.md) |
| Contracts (vendored `slice0/`) | built | [contracts.md](components/contracts.md) |

Vendored contracts (from the blueprint, not yet implemented against): `slice0/schemas`, `slice0/registry`, `slice0/domain/reconcile.py`, `slice0/api/openapi.yaml`. See [components/contracts.md](components/contracts.md).

## Dependency rules

1. `cockpit → api → db`. Nothing else writes to the database.
2. `intelligence/` imports no database code.
3. Public output (the website feed) is produced only from approved, human-marked data, and anonymised on the platform side.
