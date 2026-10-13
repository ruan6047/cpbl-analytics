"""季後系列唯讀契約 ``postseason-series-contract/v1``（#268 WP1／WP5，供 #238 等消費端）。

**唯讀、不新增端點**：只是一支 Python 函式，四次 ``SELECT``（第四次是 #268 D1 的官方異動訊號）；不寫入、不觸發 refresh、不連官網。

它回答三件事，且每一件都只出自正式資料：

1. 本季有哪些**真實** E／C 場次——只取 ``cpbl.games`` 現有列的 ``(year, kind_code, game_sno)``。
   ⛔ 不從公告場序推 sno、不從 E 推 C、不從 stats 賽程推 sno；資料庫沒有 C 列就是沒有。
2. 每場是否完成——``completed`` 用與 ``/api/v1/postseason-summary``、``cpbl.reports.readers``
   **同一支** ``completed_games_sql_with_evidence``（2026 起 E／C 只認官方 final／完賽證據，#237）。
   本模組不另寫判準；``completed_keys`` 因此與 postseason-summary 的完賽場集合同源。
3. 資料時點——``as_of`` 把「最後一次整鏈刷新」與「是否已涵蓋最新完賽」（``coverage``）分開：
   刷新成功不等於最新一場已入庫（#268 反例）。``last_refresh_*`` 只代表 ``refresh_log`` 最新一列。

未知一律 ``None``／``"unknown"``，不零填：未完成場的比分是 ``None``（DB 的 0–0 是佔位）。
不含晉級判定、名單、報告語意、開賽時間（v1 不提供；``cpbl.games`` 沒有開賽時刻欄）。

本契約的 ``coverage`` 只看正式資料庫（不讀即時快取），所以「今晚即時已終場、正式未入庫」
在這裡要等台北日過了才會變成 ``pending_update``；首頁 ``daily.summary`` 另把即時 final 當作
待更新訊號。兩者語意一致（即時 final 都不是完賽），只是可見訊號的範圍不同。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime

from cpbl.api.helpers import OFFICIAL_SCHEDULE_ORDER_BY, _dicts, official_status
from cpbl.change_signals import UNRESOLVED_SQL, signal_games
from cpbl.completion import completed_games_sql_with_evidence
from cpbl.coverage import coverage_verdict, taipei_date

CONTRACT = "postseason-series-contract/v1"
POSTSEASON_KINDS = ("E", "C")

# 與 readers／standings 同一支 helper；as_of 以參數注入（＝台北日），預設呼叫時兩者同日。
_DONE_AS_OF = completed_games_sql_with_evidence("g", "%(as_of)s")

GAMES_SQL = f"""
    SELECT g.year, g.kind_code, g.game_sno, g.game_date, g.venue,
           g.away_team_code, g.home_team_code, g.away_score, g.home_score,
           COALESCE({_DONE_AS_OF}, FALSE) AS completed
    FROM cpbl.games g
    WHERE g.year = %(year)s AND g.kind_code IN ('E', 'C')
    ORDER BY g.game_date, g.kind_code, g.game_sno
"""

REVISIONS_SQL = f"""
    SELECT year, kind_code, game_sno, raw_present_status, raw_game_result,
           raw_game_date, payload_hash, fetched_at, last_seen_at
    FROM cpbl.game_schedule_status_revisions
    WHERE year = %(year)s AND kind_code IN ('E', 'C')
    ORDER BY year, kind_code, game_sno, {OFFICIAL_SCHEDULE_ORDER_BY}
"""

REFRESH_SQL = "SELECT refreshed_at, ok, scope FROM cpbl.refresh_log ORDER BY refreshed_at DESC LIMIT 1"

# #268 D1：未解決的官方賽程異動訊號（與首頁 daily.summary 同一支 SQL）。
CHANGE_SIGNALS_SQL = UNRESOLVED_SQL


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def series_state_from_cursor(cur, year: int, *, now: datetime) -> dict:
    """以既有 cursor 組出契約（測試與隔離 PG 契約測試直接呼叫）。

    查詢順序刻意是 games → refresh_log → 官方狀態 → 異動訊號（D1）：後三者失敗都只降級成
    unknown／None／無訊號，
    games 失敗則讓錯誤上浮（空清單會被讀成「沒有季後賽」）。
    """
    taipei_day = taipei_date(now)
    cur.execute(GAMES_SQL, {"year": year, "as_of": taipei_day})
    rows = _dicts(cur)

    last_refresh: dict | None
    try:
        cur.execute(REFRESH_SQL)
        refresh_row = cur.fetchone()
        last_refresh = ({"at": refresh_row[0], "ok": refresh_row[1], "scope": refresh_row[2]}
                        if refresh_row else None)
    except Exception:  # noqa: BLE001 — 缺表／權限：時點未知，不宣稱
        last_refresh = None

    statuses: dict[tuple[int, str, int], str] | None
    try:
        cur.execute(REVISIONS_SQL, {"year": year})
        grouped: dict[tuple[int, str, int], list[dict]] = {}
        for rev in _dicts(cur):
            grouped.setdefault((rev["year"], rev["kind_code"], rev["game_sno"]), []).append(rev)
        statuses = {key: official_status(group)[0] for key, group in grouped.items()}
    except Exception:  # noqa: BLE001 — 讀不到官方狀態 → 每場 unknown、coverage 不得稱 covered
        statuses = None

    # #268 D1：未解決的官方賽程異動訊號（含本站尚無列的新場次；只進 coverage，⛔ 不進 games）。
    # 最後一支查詢：失敗只少這個訊號，與 D1 之前資訊量相同。
    try:
        cur.execute(CHANGE_SIGNALS_SQL, {"kinds": list(POSTSEASON_KINDS), "season": year})
        changes = signal_games(_dicts(cur))
    except Exception:  # noqa: BLE001 — 缺表／權限
        changes = []

    games = []
    for row in rows:
        key = (int(row["year"]), row["kind_code"], int(row["game_sno"]))
        completed = bool(row["completed"])
        games.append({
            "year": key[0], "kind_code": key[1], "game_sno": key[2],
            "game_date": _iso(row["game_date"]),
            "away_team_code": row["away_team_code"], "home_team_code": row["home_team_code"],
            "venue": row.get("venue") or None,
            "completed": completed,
            "official_status": (statuses or {}).get(key, "unknown"),
            "away_score": row["away_score"] if completed else None,
            "home_score": row["home_score"] if completed else None,
        })

    done = [g for g in games if g["completed"]]
    coverage = coverage_verdict(
        [{"year": g["year"], "kind_code": g["kind_code"], "game_sno": g["game_sno"],
          "game_date": g["game_date"]} for g in games if not g["completed"]],
        statuses, taipei_day=taipei_day, change_signals=changes,
    )
    return {
        "contract": CONTRACT,
        "year": year,
        "as_of": {
            "taipei_date": taipei_day.isoformat(),
            "last_completed_game_date": max((g["game_date"] for g in done), default=None),
            "last_refresh_at": _iso(last_refresh["at"]) if last_refresh else None,
            "last_refresh_ok": last_refresh["ok"] if last_refresh else None,
            "last_refresh_scope": last_refresh["scope"] if last_refresh else None,
            "coverage": coverage["status"],
            "pending_games": coverage["pending_games"],
        },
        "games": games,
        "completed_keys": [[g["year"], g["kind_code"], g["game_sno"]] for g in done],
    }


def postseason_series_state(year: int, *, now: datetime | None = None,
                            connect: Callable | None = None) -> dict:
    """``postseason-series-contract/v1``：真實 E／C 場次、canonical 完賽集合與資料時點。"""
    if connect is None:
        from cpbl.db import conn as connect
    with connect() as c:
        return series_state_from_cursor(c.cursor(), year, now=now or datetime.now(UTC))
