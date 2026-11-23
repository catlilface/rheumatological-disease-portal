# Separate from packages/service-runtime on purpose: that image runs on
# Python 3.15, which segfaults psycopg[binary]/SQLAlchemy today (beta-ABI
# incompatibility with prebuilt C-extension wheels). Migrations and the
# isolation/integrity test suites need a real Postgres connection, so they
# get their own Python 3.12 image built from the service's own pyproject.toml
# (services/<name>/pyproject.toml + uv.lock), not the shared gRPC runtime.
FROM ghcr.io/astral-sh/uv:python3.12-alpine

ARG SERVICE

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /build

# Mirrors the real repo layout (services/<name> and packages/db as siblings)
# so services/<name>/pyproject.toml's `../../packages/db` path dependency
# resolves without rewriting it per-image.
COPY packages/db packages/db
COPY services/${SERVICE} services/${SERVICE}

WORKDIR /build/services/${SERVICE}
RUN uv sync --locked

ENV PATH="/build/services/${SERVICE}/.venv/bin:$PATH"

# DATABASE__USER/NAME/HOST/PORT come from the compose service's `environment:`;
# DATABASE__PASSWORD is read from whichever secret file the invoker mounted,
# so the same image serves both migrations (postgres superuser) and the
# isolation/integrity tests (least-privilege app_<service> role).
CMD ["sh", "-c", "export DATABASE__PASSWORD=\"$(cat /run/secrets/postgres-password)\"; exec alembic upgrade head"]
