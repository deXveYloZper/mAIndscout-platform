# core

Python core of the platform: `api/` (the only writer), `domain/` (pure rules), `db/` (tables), later `intelligence/` (pure, no DB).

```bash
docker compose up -d                 # Postgres 16 on localhost:5433 (from repo root)
cd core && pip install -e ".[dev]"
python -m alembic upgrade head       # create tables in the dev database
python -m pytest                     # creates and migrates a throwaway maindscout_test database
python -m maindscout init            # migrate, seed, create the org; prints the org id
python -m maindscout serve           # API on http://127.0.0.1:8765 (docs at /docs) + 2 background workers
python -m maindscout worker          # (optional) more background workers in their own process
python -m maindscout eval --with-tests  # golden eval over test_artifacts (real model, a few cents)
cd ../cockpit && npm run e2e         # cockpit end to end (fresh maindscout_e2e database, real model)
```

Put `OPERATOR_TOKEN=<any long random string>` in `core/.env`; every API call needs it as a Bearer token plus `X-Org-Id`.

Model: set `XAI_API_KEY` in `core/.env` (git-ignored); `MONTHLY_BUDGET_USD` caps paid calls (default 25). Live check over real files: `RUN_LIVE=1 python -m pytest tests/test_live_artifacts.py` (costs a few cents).

`DATABASE_URL` overrides the default dev connection; `BLOB_DIR` the original-file folder (default `core/.blobs`); `TEST_ARTIFACTS` the folder of real CVs and job ads used by `test_real_artifacts.py`. Documentation: [../docs/build/](../docs/build/README.md).
