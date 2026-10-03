# Connection: cockpit → API

**Status:** built

## What flows
The cockpit's server calls the API over HTTP (`MAINDSCOUT_API`, default `http://127.0.0.1:8765`) with `Authorization: Bearer <OPERATOR_TOKEN>` and `X-Org-Id`. The browser talks only to the cockpit.

## Why this way
The token stays on the server; the cockpit holds no data and no rules, so every trust rule lives in one place (`api/`).

## Configuration
- `core/.env`: `OPERATOR_TOKEN`, `XAI_API_KEY` (API side).
- `cockpit/.env.local`: `MAINDSCOUT_API`, `OPERATOR_TOKEN` (same value), `ORG_ID` (printed by `python -m maindscout init`). Template: `cockpit/.env.local.example`. Both files are git-ignored.

## Running locally
```bash
docker compose up -d
cd core && python -m maindscout init && python -m maindscout serve
cd cockpit && npm install && npm run dev
```
Then open http://localhost:3001. `serve` also runs 2 background workers, which read uploaded CVs; without them uploads stay "waiting". Port 8765 is used because 8000 was taken on the development machine.

## When this changes
Update [http-api.md](../components/http-api.md), [cockpit.md](../components/cockpit.md) and this page together.
