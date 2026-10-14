# The Python core in a container: for machines where the host Python cannot load the database driver
# (e.g. Windows Application Control blocking psycopg's DLL). Only the dependencies are baked in; the repo is mounted at
# /repo by docker-compose.yml, so code changes apply without a rebuild. Secrets stay in core/.env on the mount.
FROM python:3.12-slim

WORKDIR /build
COPY pyproject.toml ./
COPY maindscout ./maindscout
RUN pip install --no-cache-dir ".[dev]" && rm -rf /build

WORKDIR /repo/core
ENV PYTHONPATH=/repo/core PYTHONDONTWRITEBYTECODE=1
CMD ["python", "-m", "maindscout", "serve"]
