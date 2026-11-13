FROM ghcr.io/astral-sh/uv:python3.15-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app/server

COPY server/pyproject.toml server/uv.lock server/.python-version ./

RUN uv sync --locked --no-dev --no-install-project

COPY server/app ./app

RUN uv sync --locked --no-dev --no-editable \
    && useradd --create-home --user-group --uid 10001 app

ENV PATH="/app/server/.venv/bin:$PATH"

USER app:app

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
