"""#238 新唯讀報告。網頁原 journey 選 Y，第二讀驗同源 context。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from cpbl.api.helpers import DEFAULT_SEASON
from cpbl.db import conn
from cpbl.reports import official_population
from cpbl.reports.assembler import build_report, report_anchor
from cpbl.reports.context import ContextChanged, jsonable

router = APIRouter()


@router.get("/api/v1/games/{game_sno}/report")
def game_report(
    game_sno: int,
    season: int = Query(DEFAULT_SEASON),
    kind_code: str = Query(..., pattern="^(E|C)$"),
    next_kind: str | None = Query(None, pattern="^(E|C)$"),
    next_sno: int | None = Query(None, ge=1),
    context_hash: str | None = Query(None, pattern="^[0-9a-f]{64}$"),
    context_only: bool = Query(False),
) -> dict:
    if (next_kind is None) != (next_sno is None):
        raise HTTPException(422, "next_kind 與 next_sno 必須成對")
    if next_kind is not None and context_hash is None:
        raise HTTPException(422, "指定下一場必須帶 context_hash")
    if context_only and (next_kind is not None or context_hash is not None):
        raise HTTPException(422, "context_only 只供第一讀，不可帶下一場或 context_hash")
    try:
        with conn() as c:
            c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            out = build_report(c.cursor(), season, kind_code, game_sno,
                               next_kind, next_sno, context_hash,
                               population_records=[record for round_kind in ("E", "C")
                                                   for record in official_population.load(season, round_kind)],
                               context_only=context_only)
        return jsonable(out)
    except ContextChanged as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/api/v1/games/{game_sno}/report-anchor")
def game_report_anchor(
    game_sno: int,
    season: int = Query(DEFAULT_SEASON),
    kind_code: str = Query(..., pattern="^(E|C)$"),
) -> dict:
    """Y 觀戰報告只取截至場 X 身分；Y 是否為下一場仍由網頁 journey 與第二讀核對。"""
    with conn() as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        return jsonable(report_anchor(c.cursor(), season, kind_code, game_sno))
