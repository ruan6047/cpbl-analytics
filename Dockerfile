# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml README.md ./
COPY src ./src
COPY migrations ./migrations
RUN uv sync --no-dev --no-editable

FROM python:3.12-slim-bookworm
RUN groupadd -r app && useradd -r -g app app \
    && apt-get update && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/migrations /app/migrations
ENV PATH="/app/.venv/bin:$PATH" PORT=4001 ARTIFACT_DIR=/app/artifacts
RUN mkdir -p /app/artifacts && chown app:app /app/artifacts
USER app
EXPOSE 4001
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD curl -fsS http://localhost:4001/api/info || exit 1
CMD ["sh", "-c", "uvicorn cpbl.api.main:app --host 0.0.0.0 --port ${PORT}"]
