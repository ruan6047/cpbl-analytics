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
# TZ：容器本地日＝台北日。`date.today()`（如 daily.py 的 `_today_local`）吃的就是這個。
# 未設時容器是 UTC，台北 00:00–08:00 這 8 小時整支 API 的「今天」會指到昨天
# （2026-08-21 生產實測 /api/v1/daily/summary 的 next_slate.game_date=2026-08-20）。
# ⚠️ 基底映像已含 tzdata（/usr/share/zoneinfo/Asia/Taipei），不需 apt install。
# ⚠️ DB session timezone 另由 `cpbl.db` 的 pool `configure` 明示，不靠這個 env。
ENV PATH="/app/.venv/bin:$PATH" PORT=4001 ARTIFACT_DIR=/app/artifacts TZ=Asia/Taipei
RUN mkdir -p /app/artifacts /evidence && chown app:app /app/artifacts /evidence
USER app
EXPOSE 4001
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD curl -fsS http://localhost:4001/api/info || exit 1
CMD ["sh", "-c", "uvicorn cpbl.api.main:app --host 0.0.0.0 --port ${PORT}"]
