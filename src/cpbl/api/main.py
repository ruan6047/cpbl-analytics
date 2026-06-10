"""FastAPI 服務：子專案契約 /api/info + 成績投影查詢端點。

/api/info 是主站 InfoPoller 每 5 分鐘輪詢的端點，metrics 刻意設計成
展示一個「活的 ML 系統」：模型版本、回測 MAE、投影球員數、資料新鮮度。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Query

from cpbl import __version__
from cpbl.config import settings
from cpbl.db import conn

app = FastAPI(title="CPBL Analytics", version=__version__)


def _scalar(sql: str, params: tuple = ()) -> Any:
    with conn() as c:
        cur = c.cursor()
        cur.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None


@app.get("/api/info")
def info() -> dict:
    """主站 InfoPoller 契約。永遠回 200；資料未就緒時 metrics 退化但仍可用。"""
    metrics: dict[str, Any] = {}
    status = "running"
    try:
        metrics["batting_seasons"] = _scalar("SELECT count(*) FROM cpbl.batting_seasons") or 0
        metrics["players"] = _scalar("SELECT count(*) FROM cpbl.players") or 0
        metrics["seasons_covered"] = _scalar(
            "SELECT count(DISTINCT year) FROM cpbl.batting_seasons"
        ) or 0

        mv = None
        with conn() as c:
            cur = c.cursor()
            cur.execute(
                "SELECT id, trained_at, cv_metrics FROM cpbl.model_versions "
                "ORDER BY trained_at DESC LIMIT 1"
            )
            mv = cur.fetchone()
        if mv:
            metrics["model_version"] = mv[0]
            metrics["last_trained_at"] = mv[1].astimezone(timezone.utc).isoformat()
            cv = mv[2] or {}
            if "ops" in cv:
                metrics["backtest_ops_mae"] = round(cv["ops"]["lgbm_mae"], 4)
                metrics["beats_marcel_on_ops"] = cv["ops"]["lgbm_mae"] < cv["ops"]["marcel_mae"]
            metrics["projections_stored"] = _scalar(
                "SELECT count(*) FROM cpbl.projections WHERE model_version = %s", (mv[0],)
            ) or 0
        else:
            status = "maintenance"  # 尚未訓練模型
    except Exception:  # noqa: BLE001 — info 端點不可拋錯，退化即可
        status = "maintenance"

    return {"status": status, "version": settings.app_version, "metrics": metrics}


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/api/v1/projections/batting")
def batting_projections(
    year: int | None = Query(None, description="目標季；省略則取最新一版的最大目標季"),
    stat: str = Query("ops", pattern="^(avg|obp|slg|ops)$"),
    limit: int = Query(25, ge=1, le=200),
) -> dict:
    """最新模型版本的打擊投影排行。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT id FROM cpbl.model_versions ORDER BY trained_at DESC LIMIT 1")
        mv = cur.fetchone()
        if not mv:
            return {"model_version": None, "items": []}
        model_version = mv[0]

        if year is None:
            cur.execute(
                "SELECT max(target_year) FROM cpbl.projections WHERE model_version = %s AND actual IS NULL",
                (model_version,),
            )
            r = cur.fetchone()
            year = r[0] if r and r[0] else None

        cur.execute(
            """
            SELECT pr.player_id, p.name, pr.predicted, pr.actual
            FROM cpbl.projections pr
            JOIN cpbl.players p ON p.id = pr.player_id
            WHERE pr.model_version = %s AND pr.stat = %s AND pr.target_year = %s
            ORDER BY pr.predicted DESC
            LIMIT %s
            """,
            (model_version, stat, year, limit),
        )
        items = [
            {"player_id": pid, "name": name, "predicted": round(pred, 4),
             "actual": round(act, 4) if act is not None else None}
            for pid, name, pred, act in cur.fetchall()
        ]
    return {"model_version": model_version, "stat": stat, "target_year": year, "items": items}


@app.get("/api/v1/players/{player_id}/batting")
def player_batting(player_id: str) -> dict:
    """單一球員的逐年打擊史。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT id, name, bats, throws, birthday FROM cpbl.players WHERE id = %s", (player_id,))
        p = cur.fetchone()
        if not p:
            return {"player": None, "seasons": []}
        cur.execute(
            """
            SELECT year, sum(g), sum(pa), sum(ab), sum(h), sum(hr), sum(rbi), sum(bb), sum(so),
                   round(sum(h)::numeric / NULLIF(sum(ab),0), 3) AS avg
            FROM cpbl.batting_seasons WHERE player_id = %s
            GROUP BY year ORDER BY year
            """,
            (player_id,),
        )
        seasons = [
            {"year": y, "g": g, "pa": pa, "ab": ab, "h": h, "hr": hr, "rbi": rbi,
             "bb": bb, "so": so, "avg": float(avg) if avg is not None else None}
            for y, g, pa, ab, h, hr, rbi, bb, so, avg in cur.fetchall()
        ]
    return {
        "player": {"id": p[0], "name": p[1], "bats": p[2], "throws": p[3],
                   "birthday": p[4].isoformat() if p[4] else None},
        "seasons": seasons,
    }
