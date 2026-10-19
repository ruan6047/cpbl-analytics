"""季後專頁第 1 區「逐場焦點」的精簡數據 adapter（#288 S07 WP-K3；``playoffs-highlights/v1``）。

焦點規則**只在前端**（``web/src/lib/game-highlights.ts``，單場頁同一個函式）；本模組只把規則要讀的欄位
一次批次投影出來（PRD「抽純規則與精簡數據 adapter，不複製條件」）：

- 母體沿用 S02 ``compute_series_context`` 與 :func:`series_summary.series_games`（該系列已完賽、以 game_key
  去重、E／C 分開）；未完賽場不列。
- 五表欄位投影在**同一個** REPEATABLE READ READ ONLY 交易內以 ``unnest`` 批次讀（固定 5 支查詢，不隨場數成長）；
  排序**逐字沿用**單場端點 ``routers/games.py`` 的 ``/api/v1/games/{sno}/live``——規則依列序判斷
  （例：再見＝最後一個得分事件），順序不同結果就會不同。⛔ 篩列、⛔ 判斷任何焦點條件。
- 勝敗救援中繼（``decisions``）逐場呼叫既有 :func:`pitcher_decisions.game_decisions`，與單場端點同一入口；
  它自開連線，**不在**上述交易內——與單場頁行為一致（單場頁也是分開取）。
- ``data_status``：``ok``＝scoreboard、livelog、batting、pitching 四表都有列；否則 ``pending``（不送 input，
  前端顯示「待更新」）。這是「資料到了沒」的判斷，不是焦點條件。
- **例外：判決標籤**（#285 批次 G，需求方 G-Q2「判定放在後端」）：逐打席 ΔWP 只能由後端解算器算，所以這一個
  標籤由 :mod:`cpbl.models.umpire_call_tag` 判定，每場以 ``umpire_call``（與單場 ``/facts`` 同一條權威源路徑、
  逐場自開連線，同 decisions，不在上述交易內）送出；前端只排字。其餘焦點仍只在前端判斷。

GET 只讀、不寫、不觸發爬取（G13）；⛔ 從 ``playoffs/__init__`` import（排程不載入本模組）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from cpbl import postseason_contract as contract
from cpbl.api.helpers import _dicts
from cpbl.playoffs.series_summary import series_games

CONTRACT = "playoffs-highlights/v1"

# 規則實際讀取的欄位（與 web/src/lib/game-highlights.ts 的 HighlightInput 同步；新增規則用到新欄位時兩邊一起改）。
GAME_COLS = ("away_team_code", "home_team_code", "home_score", "away_score", "away_starter_id", "home_starter_id")
SCOREBOARD_COLS = ("inning_seq", "visiting_home_type", "score_cnt", "error_cnt")
LIVELOG_COLS = ("main_event_no", "inning_seq", "visiting_home_type", "out_cnt", "pitch_cnt", "content",
                "action_name", "hitter_acnt", "hitter_name", "pitcher_acnt", "first_base", "second_base",
                "third_base", "is_score", "is_change_player", "visiting_score", "home_score",
                # #285 批次 F 失誤類標籤：捕手失誤歸屬、守位歸屬
                "catcher_acnt", "defend_station_code")
BATTING_COLS = ("hitter_name", "visiting_home_type", "role_type", "hits", "home_runs", "grand_slam", "rbi", "sb",
                "hitter_acnt", "errors")
PITCHING_COLS = ("pitcher_name", "visiting_home_type", "pitcher_acnt", "is_shutout", "is_complete_game", "so",
                 "inning_pitched_cnt", "inning_pitched_div3", "earned_runs", "hits", "bb", "hbp", "runs", "max_speed")

_KEYS = "unnest(%(snos)s::int[]) AS k(game_sno)"


def _select(table: str, cols: tuple[str, ...], order: str) -> str:
    """表名、欄名、排序皆取自本檔常數；值一律參數化。"""
    return (f"SELECT t.game_sno AS _game_sno, {', '.join('t.' + c for c in cols)} "  # noqa: S608
            f"FROM {_KEYS} JOIN cpbl.{table} t "
            f"ON t.year = %(year)s AND t.kind_code = %(kind)s AND t.game_sno = k.game_sno "
            f"ORDER BY t.game_sno, {order}")


# ORDER BY 第二段起逐字沿用 routers/games.py 單場 /live 端點。
GAMES_SQL = _select("games", GAME_COLS, "t.game_sno")
SCOREBOARD_SQL = _select("game_scoreboard", SCOREBOARD_COLS, "t.visiting_home_type, t.inning_seq")
LIVELOG_SQL = _select("game_livelog", LIVELOG_COLS, "t.main_event_no")
BATTING_SQL = _select("batting_gamelog", BATTING_COLS,
                      "t.visiting_home_type, t.plate_appearances DESC NULLS LAST, t.at_bats DESC NULLS LAST")
PITCHING_SQL = _select("pitching_gamelog", PITCHING_COLS, "t.visiting_home_type, t.inning_pitched_cnt DESC NULLS LAST")
TABLE_SQL = {"game": GAMES_SQL, "scoreboard": SCOREBOARD_SQL, "livelog": LIVELOG_SQL, "batting": BATTING_SQL,
             "pitching": PITCHING_SQL}


def read_rows(cur, year: int, kind: str, snos: list[int]) -> dict[str, dict[int, list[dict]]]:
    """五表投影，一表一支查詢：``{表: {game_sno: [列…]}}``（列序＝單場端點的列序）。"""
    out: dict[str, dict[int, list[dict]]] = {name: {} for name in TABLE_SQL}
    if not snos:
        return out
    params = {"year": year, "kind": kind, "snos": snos}
    for name, sql in TABLE_SQL.items():
        cur.execute(sql, params)
        for r in _dicts(cur):
            out[name].setdefault(int(r.pop("_game_sno")), []).append(r)
    return out


def compute_payload(context: dict, kind: str, rows: dict[str, dict[int, list[dict]]],
                    decisions: dict[int, dict[str, str]], umpire: dict[int, dict] | None = None) -> dict:
    """``playoffs-highlights/v1``（純函式）。``umpire``＝game_sno → 判決標籤結果（#285 批次 G）；未給或該場未算 ⇒ None。"""
    games = series_games(context, kind)
    out_games = []
    for g in games:
        sno = int(g["game_key"]["game_sno"])
        tables = {name: rows[name].get(sno, []) for name in ("scoreboard", "livelog", "batting", "pitching")}
        game_row = (rows["game"].get(sno) or [None])[0]
        ready = game_row is not None and all(tables.values())
        out_games.append({
            "series_game_no": g["series_game_no"],
            "game_key": g["game_key"],
            "data_status": "ok" if ready else "pending",
            "input": ({"game": game_row, **tables, "decisions": decisions.get(sno, {})} if ready else None),
            "umpire_call": (umpire or {}).get(sno) if ready else None,
        })
    return {
        "contract": CONTRACT,
        "context_version": context["context_version"],
        "series": kind,
        "series_id": context["series"][kind]["series_id"],
        "as_of": context["as_of"],
        "status": "ok" if games else "no_completed_games",
        "games": out_games,
    }


def series_highlights(year: int, kind: str, *, now: datetime | None = None, connect: Callable | None = None,
                      live_reader=None, decisions_for: Callable[[int, str, int], dict] | None = None,
                      umpire_for: Callable[[int, str, int], dict] | None = None) -> dict:
    """單一唯讀交易讀 S02＋五表投影；交易外逐場取 decisions 與判決標籤（同單場端點）。

    判決標籤由 ``umpire_for`` 計算；正式 router 注入 ``connect`` 時一併明確傳入 ``umpire_for``。只注入 ``connect``
    （隔離測試）而未傳 ``umpire_for`` 時不算，免得另開連線讀到非受測資料庫；兩者都未注入才用預設。
    """
    if umpire_for is None and connect is None:
        from cpbl.models.umpire_call_tag import game_umpire_call as umpire_for
    if connect is None:
        from cpbl.db import conn as connect
    if decisions_for is None:
        from cpbl.models.pitcher_decisions import game_decisions as decisions_for
    now = now or datetime.now(UTC)
    with connect() as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute(contract.READ_ONLY_TXN)
            context = contract.compute_series_context(
                contract.read_series_inputs(cur, year, now=now, live_reader=live_reader), now=now)
            snos = [int(g["game_key"]["game_sno"]) for g in series_games(context, kind)]
            rows = read_rows(cur, year, kind, snos)
    ready = [s for s in snos if rows["game"].get(s) and all(rows[t].get(s) for t in
                                                            ("scoreboard", "livelog", "batting", "pitching"))]
    decisions = {s: decisions_for(year, kind, s) for s in ready}
    umpire = {s: umpire_for(year, kind, s) for s in ready} if umpire_for is not None else None
    return compute_payload(context, kind, rows, decisions, umpire)
