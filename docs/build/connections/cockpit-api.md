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

**The core in Docker** (when this machine's Python cannot load the database driver: since 2026-10-12 Windows Application
Control blocks psycopg's DLL on the development machine). The cockpit is unchanged; it reaches the API on the same address.
```bash
docker compose run --rm core python -m maindscout init            # and any other command, e.g. user create
docker compose --profile core up -d core                          # the API on http://127.0.0.1:8765, with workers
docker compose run --rm core python -m pytest                     # tests
```
The repo is mounted into the container, so code changes apply without a rebuild (`docker compose build core` after a
dependency change). `API_HOST=0.0.0.0` applies only inside the container; the port is published to 127.0.0.1 alone.
Known limit: the cockpit's `npm run e2e` starts the API with the host's Python, so it does not run on such a machine yet.

## When this changes
Update [http-api.md](../components/http-api.md), [cockpit.md](../components/cockpit.md) and this page together.
