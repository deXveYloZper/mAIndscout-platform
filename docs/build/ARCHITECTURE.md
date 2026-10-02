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
- The **cockpit** is the recruiter's UI. It only talks to `api/`.
- **`api/`** is the only thing that writes to the database.
- **`intelligence/`** is pure: a workspace goes in, staged claims come out. It never opens a database session.

## Components

Dependency direction is top to bottom: a component may depend only on those below it.

| Component | Status | Page |
|---|---|---|
| Contracts (vendored `slice0/`) | built | [contracts.md](components/contracts.md) |

Vendored contracts (from the blueprint, not yet implemented against): `slice0/schemas`, `slice0/registry`, `slice0/domain/reconcile.py`, `slice0/api/openapi.yaml`. See [components/contracts.md](components/contracts.md).

## Dependency rules

1. `cockpit → api → db`. Nothing else writes to the database.
2. `intelligence/` imports no database code.
3. Public output (the website feed) is produced only from approved, human-marked data, and anonymised on the platform side.
