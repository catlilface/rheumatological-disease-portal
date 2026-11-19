FROM ghcr.io/astral-sh/uv:python3.15-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app/server

COPY services/bff/pyproject.toml services/bff/uv.lock services/bff/.python-version ./

RUN uv sync --locked --no-dev --no-install-project

COPY services/bff/app ./app

RUN uv sync --locked --no-dev --no-editable \
    && addgroup -S app \
    && adduser -S -D -u 10001 -G app app

ENV PATH="/app/server/.venv/bin:$PATH"

USER app:app

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
