"""FastAPI 服務：app 組裝。路由按領域拆在 routers/，共用工具在 helpers.py / rows.py。

/api/info 是主站 InfoPoller 每 5 分鐘輪詢的端點（routers/info.py，永不拋錯）。
API 唯讀契約：只提供 GET（tests/test_route_snapshot.py 守門）。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cpbl import __version__
from cpbl.api.routers import (
    ability,
    games,
    info,
    leaders,
    outcome,
    players,
    projections,
    standings,
    teams,
    tracking,
    trend,
)

app = FastAPI(title="CPBL Analytics", version=__version__)

# 公開唯讀 API；dev 時前端跨埠(:3000→:4001)需 CORS。prod 同源(經 nginx)不受影響。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

for _mod in (info, projections, leaders, outcome, standings, players, games,
             ability, tracking, trend, teams):
    app.include_router(_mod.router)
