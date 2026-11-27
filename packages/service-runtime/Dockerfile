FROM ghcr.io/astral-sh/uv:python3.15-trixie-slim

WORKDIR /app

COPY packages/service-runtime/pyproject.toml packages/service-runtime/uv.lock ./

RUN uv sync --locked --no-install-project

ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1

COPY contracts contracts

RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. contracts/*/v1/*.proto

COPY packages/service-runtime/runtime.py packages/service-runtime/database.py ./

ARG SERVICE

COPY services/${SERVICE}/ ./service/

USER 10001

CMD ["python", "-m", "service.main"]
