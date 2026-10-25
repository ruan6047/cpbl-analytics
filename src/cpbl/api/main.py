"""FastAPI 服務：app 組裝。路由按領域拆在 routers/，共用工具在 helpers.py / rows.py。

/api/info 是主站 InfoPoller 每 5 分鐘輪詢的端點（routers/info.py，永不拋錯）。
API 唯讀契約：只提供 GET（tests/test_route_snapshot.py 守門）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cpbl import __version__, db
from cpbl.api.routers import (
    ability,
    daily,
    facts,
    games,
    info,
    leaders,
    outcome,
    people,
    players,
    playoffs,
    playoffs_comparison,
    playoffs_highlights,
    playoffs_roster,
    playoffs_watch,
    projections,
    recap,
    report,
    standings,
    teams,
    tracking,
    trend,
    umpires,
    venues,
)
from cpbl.config import settings


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """只在 uvicorn 起 app 時執行——這就是「API 行程」的界線（#353）。

    1. WP2：讀端逾時。⛔ 不放在 import 時：migrate／訓練／ingest CLI 也會 import cpbl 套件，
       它們合法地跑超過 statement_timeout（``tests/test_api_db_timeouts_353.py`` 守門）。
    """
    db.configure_api_timeouts(
        pool_timeout_s=settings.api_db_pool_timeout_seconds,
        statement_timeout_ms=settings.api_db_statement_timeout_ms,
        lock_timeout_ms=settings.api_db_lock_timeout_ms,
    )
    yield


app = FastAPI(title="Ruan's CPBL Lab API", version=__version__, lifespan=lifespan)

# 公開唯讀 API；dev 時前端跨埠(:3000→:4001)需 CORS。prod 同源(經 nginx)不受影響。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

for _mod in (info, projections, leaders, outcome, standings, players, games, daily,
             ability, tracking, trend, teams, umpires, people, venues, recap, facts, report,
             playoffs, playoffs_watch, playoffs_comparison, playoffs_roster, playoffs_highlights):
    app.include_router(_mod.router)
