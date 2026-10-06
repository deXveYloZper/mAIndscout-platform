# Connection: cockpit → API

**Status:** built

## What flows
The cockpit's server calls the API over HTTP (`MAINDSCOUT_API`, default `http://127.0.0.1:8765`) with the signed-in user's session (`Authorization: Bearer <session>`, from an httpOnly cookie) and the chosen desk (`X-Org-Id`). The browser talks only to the cockpit and never sees the session token ([access](../components/access.md)).

## Why this way
The session token stays on the server; the cockpit holds no data and no rules, so every trust rule lives in one place (`api/`).

## Configuration
- `core/.env`: `XAI_API_KEY`, and the keys `init` creates (`SUPPRESSION_KEY`, `MAILBOX_KEY`, `AUTH_KEY`).
- `cockpit/.env.local`: `MAINDSCOUT_API` (and `COOKIE_SECURE=true` behind HTTPS). Template: `cockpit/.env.local.example`. Both files are git-ignored.

## Running locally
```bash
docker compose up -d
cd core && python -m maindscout init && python -m maindscout user create --email you@example.com --name "You" --role owner && python -m maindscout serve
cd cockpit && npm install && npm run dev
```
Then open http://localhost:3001. `serve` also runs 2 background workers, which read uploaded CVs; without them uploads stay "waiting". Port 8765 is used because 8000 was taken on the development machine.

## When this changes
Update [http-api.md](../components/http-api.md), [cockpit.md](../components/cockpit.md) and this page together.
