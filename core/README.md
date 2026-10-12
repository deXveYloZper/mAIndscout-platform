# core

Python core of the platform: `api/` (the only writer), `domain/` (pure rules), `db/` (tables), later `intelligence/` (pure, no DB).

```bash
docker compose up -d                 # Postgres 16 on 127.0.0.1:5433 (this machine only) (from repo root)
cd core && pip install -e ".[dev]"
python -m alembic upgrade head       # create tables in the dev database
python -m pytest                     # creates and migrates a throwaway maindscout_test database
python -m maindscout init            # migrate, seed, create the org; prints the org id
python -m maindscout serve           # API on http://127.0.0.1:8765 (docs at /docs) + 2 background workers
python -m maindscout worker          # (optional) more background workers in their own process
python -m maindscout perf-seed && python -m maindscout perf-check   # timings on a 3,000-person synthetic desk (free)
python -m maindscout eval --with-tests  # golden eval over test_artifacts (real model, a few cents)
cd ../cockpit && npm run e2e         # cockpit end to end (fresh maindscout_e2e database; model answers replayed when recorded)
npm run e2e:free                     # replay only: costs nothing (see docs/build/components/model-recordings.md)
```

Sign-in is per person: after `init`, create the first owner with `python -m maindscout user create --email you@example.com --name "Your Name" --role owner` and open the printed link to set a password. Scripts use a personal token (`python -m maindscout token create --email … --label …`). See [access](../docs/build/components/access.md).

Model: set `XAI_API_KEY` in `core/.env` (git-ignored); `MONTHLY_BUDGET_USD` caps paid calls (default 25). Sourcing: `EXA_API_KEY` for web people search (without it, runs use the desk's own pool only); its budgets are set per role and for the desk in the cockpit, apart from the model budget; `SOURCING_AUTO=false` stops the sourcing clock; `PRIVACY_URL` is the page a first LinkedIn message links to (default `maindscout.com/legal`). Live check over real files: `RUN_LIVE=1 python -m pytest tests/test_live_artifacts.py` (costs a few cents).

**If this machine's Python cannot load the database driver** (Windows Application Control blocking psycopg's DLL), run any of the
commands above in Docker instead: `docker compose run --rm core python -m pytest`, `docker compose run --rm core python -m maindscout init`,
and `docker compose --profile core up -d core` for the API. See [cockpit-api](../docs/build/connections/cockpit-api.md).

`DATABASE_URL` overrides the default dev connection; `API_HOST` the address `serve` listens on (default 127.0.0.1; 0.0.0.0 only inside the container); `BLOB_DIR` the original-file folder (default `core/.blobs`); `TEST_ARTIFACTS` the folder of real CVs and job ads used by `test_real_artifacts.py`. Documentation: [../docs/build/](../docs/build/README.md).
