# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# 兩段式安裝：先只放依賴宣告與 lock 檔裝第三方套件，再放程式碼裝本專案。
# - `--frozen`：嚴格照 uv.lock 安裝，lock 與 pyproject 不一致就直接失敗；
#   沒有 lock 時 uv sync 會重新解依賴，生產映像跑的版本就與 CI 測過的 uv.lock 脫鉤。
# - 依賴層只依賴 pyproject.toml／uv.lock，改程式碼不會讓它失效，重建只剩本專案那一層。
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-editable --no-install-project
COPY src ./src
COPY migrations ./migrations
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm
RUN groupadd -r app && useradd -r -g app app \
    && apt-get update && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/migrations /app/migrations
# 六工作的必要 Linux 入口/既有狀態與告警 helper；不整包 scripts，也不裝 Chromium。
COPY scripts/jobs.py scripts/refresh_status.py scripts/schedule_watch.py scripts/alert_watch.py scripts/alert_ping.py scripts/schedule-registry.json /app/jobs/
# TZ：容器本地日＝台北日。`date.today()`（如 daily.py 的 `_today_local`）吃的就是這個。
# 未設時容器是 UTC，台北 00:00–08:00 這 8 小時整支 API 的「今天」會指到昨天
# （2026-08-21 生產實測 /api/v1/daily/summary 的 next_slate.game_date=2026-08-20）。
# ⚠️ 基底映像已含 tzdata（/usr/share/zoneinfo/Asia/Taipei），不需 apt install。
# ⚠️ DB session timezone 另由 `cpbl.db` 的 pool `configure` 明示，不靠這個 env。
ENV PATH="/app/.venv/bin:$PATH" PORT=4001 ARTIFACT_DIR=/app/artifacts TZ=Asia/Taipei
RUN mkdir -p /app/artifacts /app/logs/locks /evidence \
    && chown app:app /app/artifacts /app/logs /app/logs/locks /evidence \
    && chmod 0700 /app/logs /app/logs/locks
USER app
EXPOSE 4001
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD curl -fsS http://localhost:4001/api/info || exit 1
CMD ["sh", "-c", "uvicorn cpbl.api.main:app --host 0.0.0.0 --port ${PORT} --no-access-log"]
