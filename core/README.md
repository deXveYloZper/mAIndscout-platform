# core

Python core of the platform: `api/` (the only writer), `domain/` (pure rules), `db/` (tables), later `intelligence/` (pure, no DB).

```bash
docker compose up -d                 # Postgres 16 on localhost:5433 (from repo root)
cd core && pip install -e ".[dev]"
python -m alembic upgrade head       # create tables in the dev database
python -m pytest                     # creates and migrates a throwaway maindscout_test database
```

`DATABASE_URL` overrides the default dev connection; `BLOB_DIR` the original-file folder (default `core/.blobs`); `TEST_ARTIFACTS` the folder of real CVs and job ads used by `test_real_artifacts.py`. Documentation: [../docs/build/](../docs/build/README.md).
