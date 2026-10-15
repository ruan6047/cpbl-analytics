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

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from fractions import Fraction

from cpbl.api.helpers import OFFICIAL_SCHEDULE_ORDER_BY, _dicts, official_status
from cpbl.change_signals import UNRESOLVED_SQL, signal_games
from cpbl.completion import completed_games_sql_with_evidence
from cpbl.coverage import coverage_verdict, taipei_date
from cpbl.playoffs import state as playoff_state

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


# =====================================================================================
# postseason-series-context/v2（#283 S02）：系列身分、勝場與正交狀態的唯一計算
# =====================================================================================
#
# 規則住這裡（需求方 Q1「Ａ」：逐年常數寫在本模組，⛔ JSON／YAML、⛔ DB）。TS 只消費
# ``/api/v1/postseason-summary`` 的 ``series_context``，不平行維護 initial_wins／decided。
#
# ⛔ 參賽隊與 initial_wins **不寫死**：一律由規章 §60＋戰績推導（需求方 Q2「Ａ」）。2026 的
#    官方公告只拿來比對，不一致 ⇒ ``announcement_mismatch``，⛔ 改常數湊結果。
# ⛔ 不從比分反推讓勝；⛔ 不由公告場序發明 sno；⛔ 不由 E 推 C 場號；系列身分只用
#    ``(year, kind_code, game_sno)``，⛔ 不以 game_season_code join（2026 E 列為 ''）。

CONTEXT_CONTRACT = "postseason-series-context/v2"
SERIES_ALGO_VERSION = "s02.1"
E_WINNER = "E_WINNER"


@dataclass(frozen=True)
class SeriesFormat:
    kind: str
    best_of: int
    wins_needed: int


@dataclass(frozen=True)
class TeamSlot:
    """公告的主客：固定隊碼，或 ``E_WINNER``（挑戰賽勝隊）。"""
    code: str | None = None
    placeholder: str | None = None

    def to_json(self) -> dict:
        return {"code": self.code} if self.code else {"placeholder": self.placeholder}


@dataclass(frozen=True)
class VenueSpec:
    """球場：固定／依挑戰賽勝隊而定（官方未定，條件明確）／本站未取得。"""
    name: str | None = None
    by_winner: tuple[tuple[str, str], ...] = ()
    unknown: bool = False

    def to_json(self) -> dict:
        if self.name:
            return {"name": self.name}
        if self.by_winner:
            return {"by_winner": dict(self.by_winner)}
        return {"unknown": True}


@dataclass(frozen=True)
class ArrangedSlot:
    """公告安排的一格。``key`` 是公告場序（E1…、C1…），⛔ 不是官方場號。"""
    key: str
    kind: str
    seq: int
    date: str
    start: str | None
    away: TeamSlot | None
    home: TeamSlot | None
    venue: VenueSpec
    conditional: bool
    official_sno: int | None = None   # 只有 E：官方賽程 GameSno，只作歸併候選鍵（主客也要一致）


@dataclass(frozen=True)
class SourceCheck:
    on: str
    scope: str
    url: str
    ok: bool
    note: str


@dataclass(frozen=True)
class RosterLead:
    url: str
    label: str
    published_on: str
    kind: str


@dataclass(frozen=True)
class AnnouncementRef:
    """官方季後公告的轉錄（T4：原 TS 常數 ``ANNOUNCEMENTS`` 原樣移入）。

    ``e_handicap_team``／``e_teams``／``c_seeded_team`` 是**公告所寫**，只用來與推導比對。"""
    url: str
    published_on: str
    captured_at: str
    checks: tuple[SourceCheck, ...]
    e_name: str
    c_name: str
    e_handicap_team: str
    e_teams: tuple[str, str]
    c_seeded_team: str
    e_roster_leads: tuple[RosterLead, ...]
    c_roster_leads: tuple[RosterLead, ...]
    reserve_days: tuple[tuple[str, str, str], ...]   # (date, series, note)


@dataclass(frozen=True)
class SeasonRule:
    year: int
    rule_version: str
    clauses: tuple[str, ...]
    case_a_has_e: bool
    formats: tuple[SeriesFormat, SeriesFormat]
    announcement: AnnouncementRef | None = None
    arrangement: tuple[ArrangedSlot, ...] = ()

    def format(self, kind: str) -> SeriesFormat:
        return next(f for f in self.formats if f.kind == kind)


# 規章第 12 章：§60 於 110-12-29 修訂（上下半季冠軍不同⇒挑戰賽＋讓勝），§63／§66 於 106-02-09 修訂。
# 條文原文以 docs/reference/聯盟規章.txt 為準；本常數只記條號與版本。
_REGS_2022 = "cpbl-regs-ch12/§60@110-12-29,§63@106-02-09,§66@106-02-09"
_CLAUSES = ("§47", "§60-1", "§60-2", "§62", "§63", "§66", "§67")
_FORMATS = (SeriesFormat("E", 5, 3), SeriesFormat("C", 7, 4))

_LIONS, _BROTHERS, _DRAGONS = "ADD011", "ACN011", "AAA011"
_EW = TeamSlot(placeholder=E_WINNER)
_ON_WINNER = VenueSpec(by_winner=((_BROTHERS, "大巨蛋"), (_LIONS, "亞太主")))

#: 2026：CPBL 官方 10/05 公告，本站 10/06 14:28 取得（原 web/src/lib/postseason-announcement.ts 逐字移入）。
ANNOUNCEMENT_2026 = AnnouncementRef(
    url="https://www.cpbl.com.tw/xmdoc/cont?SId=0Q278399722865824041",
    published_on="2026-10-05",
    captured_at="2026-10-06T14:28:00+08:00",
    checks=(
        SourceCheck("2026-10-08", "E",
                    "https://stats.cpbl.com.tw/api/proxy/v1/games/schedule?kindCode=E&year=2026&month=10", True,
                    "官方進階數據站 E1–E4 的日期、開賽時間、主客與球場與公告一致"),
        SourceCheck("2026-10-08", "C",
                    "https://stats.cpbl.com.tw/api/proxy/v1/games/schedule?kindCode=C&year=2026&month=10", False,
                    "官方進階數據站尚無台灣大賽賽程，台灣大賽沿用 10/06 取得的公告"),
        SourceCheck("2026-10-08", "announcement",
                    "https://www.cpbl.com.tw/xmdoc/cont?SId=0Q278399722865824041", True,
                    "以瀏覽器讀取官網公告文內賽程表：台灣大賽 G5–G7 為「季後挑戰賽晉級球隊@味全龍」、臺北大巨蛋、如有必要；"
                    "其餘場次與 10/06 版一致。文內圖片只含挑戰賽四場。（同日稍早以非瀏覽器讀取被反爬擋下）"),
    ),
    e_name="季後挑戰賽",
    c_name="台灣大賽",
    e_handicap_team=_BROTHERS,
    e_teams=(_LIONS, _BROTHERS),
    c_seeded_team=_DRAGONS,
    # 登錄名單線索：UDN 2026-10-08 報導只涵蓋挑戰賽；台灣大賽各自一版，本站尚未取得。
    e_roster_leads=(RosterLead("https://udn.com/news/story/7001/9803100", "UDN", "2026-10-08", "二手報導"),),
    c_roster_leads=(),
    reserve_days=(("2026-10-19", "C", "移動補賽日"), ("2026-10-22", "C", "移動補賽日")),
)

ARRANGEMENT_2026 = (
    ArrangedSlot("E1", "E", 1, "2026-10-09", "17:05", TeamSlot(_LIONS), TeamSlot(_BROTHERS), VenueSpec("洲際"), False, 1),
    ArrangedSlot("E2", "E", 2, "2026-10-10", "17:05", TeamSlot(_BROTHERS), TeamSlot(_LIONS), VenueSpec("亞太主"), False, 2),
    ArrangedSlot("E3", "E", 3, "2026-10-11", "17:05", TeamSlot(_LIONS), TeamSlot(_BROTHERS), VenueSpec("洲際"), True, 3),
    ArrangedSlot("E4", "E", 4, "2026-10-12", "18:35", TeamSlot(_LIONS), TeamSlot(_BROTHERS), VenueSpec("洲際"), True, 4),
    ArrangedSlot("C1", "C", 1, "2026-10-17", "17:05", _EW, TeamSlot(_DRAGONS), VenueSpec("大巨蛋"), False),
    ArrangedSlot("C2", "C", 2, "2026-10-18", "17:05", _EW, TeamSlot(_DRAGONS), VenueSpec("大巨蛋"), False),
    ArrangedSlot("C3", "C", 3, "2026-10-20", "18:35", TeamSlot(_DRAGONS), _EW, _ON_WINNER, False),
    ArrangedSlot("C4", "C", 4, "2026-10-21", "18:35", TeamSlot(_DRAGONS), _EW, _ON_WINNER, False),
    # C5–C7：10/08 核對官網公告文內賽程表——季後挑戰賽晉級球隊@味全龍、臺北大巨蛋、如有必要。
    ArrangedSlot("C5", "C", 5, "2026-10-23", "18:35", _EW, TeamSlot(_DRAGONS), VenueSpec("大巨蛋"), True),
    ArrangedSlot("C6", "C", 6, "2026-10-24", "17:05", _EW, TeamSlot(_DRAGONS), VenueSpec("大巨蛋"), True),
    ArrangedSlot("C7", "C", 7, "2026-10-25", "17:05", _EW, TeamSlot(_DRAGONS), VenueSpec("大巨蛋"), True),
)

#: 年度規則常數只服務 2022–2026（§60-1 修訂後，有條文依據；T3 裁定）。其他年份 ⇒ ``rule_unsourced``。
SEASON_RULES: dict[int, SeasonRule] = {
    year: SeasonRule(
        year=year, rule_version=_REGS_2022, clauses=_CLAUSES, case_a_has_e=True, formats=_FORMATS,
        announcement=ANNOUNCEMENT_2026 if year == 2026 else None,
        arrangement=ARRANGEMENT_2026 if year == 2026 else (),
    )
    for year in range(2022, 2027)
}


# —— 戰績事實與規則推導（純函式） ——

@dataclass(frozen=True)
class TeamRecord:
    team_code: str
    w: int
    l: int  # noqa: E741 — 與 team_standings 欄名一致
    t: int = 0

    @property
    def pct(self) -> Fraction | None:
        """§47：勝場／(勝場＋敗場)，和局不計；用精確分數比較，⛔ 不用四捨五入的 win_pct 欄。"""
        return Fraction(self.w, self.w + self.l) if self.w + self.l else None


@dataclass(frozen=True)
class StandingsFacts:
    source: str                     # official（team_standings）／computed（games 即時算）
    full: tuple[TeamRecord, ...]
    first: tuple[TeamRecord, ...]
    second: tuple[TeamRecord, ...]


def _unique_top(records, exclude=()) -> tuple[str | None, bool]:
    """勝率唯一最高者；並列 ⇒ (None, True)（§47-4／§60-1(3) 屬加賽，不猜）。"""
    pool = [r for r in records if r.team_code not in exclude and r.pct is not None]
    if not pool:
        return None, False
    best = max(r.pct for r in pool)
    top = [r.team_code for r in pool if r.pct == best]
    return (top[0], False) if len(top) == 1 else (None, True)


def _pct_of(records, code) -> Fraction | None:
    return next((r.pct for r in records if r.team_code == code), None)


def derive_series_plan(rule: SeasonRule | None, standings: StandingsFacts | None) -> dict:
    """§60 → 參賽隊與 initial_wins。

    回 ``{"status": derived|unknown, "case": "A"|"B"|None, "missing_reason": [...],
    "E": {"teams": [a, b], "initial_wins": {a: n, b: n}}, "C": {"seed": code, "seed_initial_wins": n}}``。
    名次並列一律 ``unknown``＋``seed_tiebreak_pending``，不猜加賽結果。
    """
    empty = {"status": "unknown", "case": None, "missing_reason": [],
             "E": {"teams": [None, None], "initial_wins": {}}, "C": {"seed": None, "seed_initial_wins": None}}
    if rule is None:
        return {**empty, "missing_reason": ["rule_unsourced"]}
    if standings is None or not standings.full:
        return {**empty, "missing_reason": ["standings_unavailable"]}
    h1, tie1 = _unique_top(standings.first)
    h2, tie2 = _unique_top(standings.second)
    if tie1 or tie2 or not h1 or not h2:
        return {**empty, "missing_reason": ["seed_tiebreak_pending" if (tie1 or tie2) else "standings_unavailable"]}
    if h1 != h2:
        p1, p2 = _pct_of(standings.full, h1), _pct_of(standings.full, h2)
        if p1 is None or p2 is None or p1 == p2:
            return {**empty, "case": "A", "missing_reason": ["seed_tiebreak_pending"]}
        low, high = (h1, h2) if p1 < p2 else (h2, h1)
        wild, tie = _unique_top(standings.full, exclude=(h1, h2))
        if tie or not wild:
            return {**empty, "case": "A", "missing_reason": ["seed_tiebreak_pending"]}
        # §60-1(1)：兩半季冠軍中全年勝率較低者先勝 1 場；(2) 總冠軍賽無讓勝。
        return {"status": "derived", "case": "A", "missing_reason": [],
                "E": {"teams": [low, wild], "initial_wins": {low: 1, wild: 0}},
                "C": {"seed": high, "seed_initial_wins": 0}}
    # §60-2：同一隊雙半季第 1 ⇒ 全年第 2 對第 3（無讓勝）；總冠軍賽全年第 1 先勝 1 場。
    ranked = sorted((r for r in standings.full if r.pct is not None), key=lambda r: r.pct, reverse=True)
    if len(ranked) < 3 or len({r.pct for r in ranked[:4]}) < min(4, len(ranked)):
        return {**empty, "case": "B", "missing_reason": ["seed_tiebreak_pending"]}
    first, second, third = (r.team_code for r in ranked[:3])
    return {"status": "derived", "case": "B", "missing_reason": [],
            "E": {"teams": [second, third], "initial_wins": {second: 0, third: 0}},
            "C": {"seed": first, "seed_initial_wins": 1}}


@dataclass(frozen=True)
class GameFact:
    """一列真實 E／C 場次（只來自 ``cpbl.games``）。"""
    year: int
    kind_code: str
    game_sno: int
    game_date: date | None
    away_team_code: str
    home_team_code: str
    away_score: int | None
    home_score: int | None
    completed: bool
    official_status: str = "unknown"
    venue: str | None = None
    mvp_id: str | None = None
    first_observed_final_at: datetime | None = None
    ended_at: datetime | None = None   # 可信終場時刻；目前全庫無此欄 ⇒ 恆 None（ended_at_unavailable）

    @property
    def key(self) -> tuple[int, str, int]:
        return (self.year, self.kind_code, self.game_sno)

    @property
    def result(self) -> str | None:
        if not self.completed or self.away_score is None or self.home_score is None:
            return None
        if self.home_score > self.away_score:
            return "home_win"
        return "away_win" if self.away_score > self.home_score else "tie"

    @property
    def winner(self) -> str | None:
        r = self.result
        return self.home_team_code if r == "home_win" else self.away_team_code if r == "away_win" else None

    def as_state_input(self) -> dict:
        return {"year": self.year, "kind_code": self.kind_code, "game_sno": self.game_sno,
                "game_date": self.game_date, "completed": self.completed,
                "official_status": self.official_status, "ended_at": self.ended_at,
                "first_observed_final_at": self.first_observed_final_at}


def _sorted_games(games, kind) -> list[GameFact]:
    return sorted((g for g in games if g.kind_code == kind), key=lambda g: (g.game_date or date.max, g.game_sno))


def tally_series(
    kind: str,
    fmt: SeriesFormat | None,
    sides: list[tuple[str | None, int | None]],
    games: list[GameFact],
    *,
    year: int,
    rule_version: str | None,
    signal_keys: frozenset[tuple[int, str, int]] = frozenset(),
    initial_wins_basis: str = "rule_standings",
) -> dict:
    """系列計數（§63 決勝、§66 和局、§67 平手再賽）。Python 唯一實作，TS 只讀輸出。

    ``sides``＝[(隊碼或 None, initial_wins 或 None)]；initial_wins 為 None ⇒ 規則未建檔。
    """
    rows = _sorted_games(games, kind)
    codes = [c for c, _ in sides]
    known = [c for c in codes if c]
    unsourced = fmt is None or any(iw is None for c, iw in sides if c)
    needed = fmt.wins_needed if fmt else None
    game_wins = dict.fromkeys(known, 0)
    ties = 0
    conflict: str | None = None
    winner: str | None = None
    decided_by: tuple[int, str, int] | None = None
    counted: set[tuple[int, str, int]] = set()

    def total(code: str) -> int | None:
        iw = dict(sides).get(code)
        return None if iw is None else iw + game_wins.get(code, 0)

    after_decided = False
    for g in rows:
        if not g.completed:
            continue
        if len(known) == 2 and {g.away_team_code, g.home_team_code} != set(known):
            conflict = conflict or "team_mismatch"
            continue
        if len(known) < 2:
            conflict = conflict or "participants_unresolved"
            continue
        if decided_by is not None:
            after_decided = True   # 決勝後仍有完賽列：照算，最後判 both_reached 或 game_after_decided
        if g.result == "tie":
            ties += 1          # §66-2 正式和局：不加任何一方勝場（§67 平手再賽另列新場）
            continue
        game_wins[g.winner] += 1
        if decided_by is None:
            counted.add(g.key)
        if needed is not None and not unsourced and decided_by is None:
            reached = [c for c in known if (total(c) or 0) >= needed]
            if reached:
                winner, decided_by = reached[0], g.key
    if needed is not None and not unsourced and len(known) == 2 and all((total(c) or 0) >= needed for c in known):
        conflict = conflict or "both_reached"   # ⛔ 取排序前者
    elif after_decided:
        conflict = conflict or "game_after_decided"

    played = any(g.completed for g in rows)
    if conflict:
        status = "unknown"
        winner, decided_by = None, None
    elif unsourced and known:
        status = "unknown"
    elif winner:
        status = "decided"
    elif played:
        status = "active"
    else:
        status = "pending"

    side_out = []
    for code, iw in sides:
        tot = None if code is None else total(code)
        decided = status == "decided"
        remaining = None if tot is None or needed is None else 0 if decided else max(0, needed - tot)
        side_out.append({
            "team_code": code,
            "initial_wins": iw if code else None,
            "initial_wins_basis": ("unsourced" if unsourced else initial_wins_basis) if code else None,
            "game_wins": game_wins.get(code, 0) if code else 0,
            "total_wins": tot,
            "remaining": remaining,
            "clinch": status == "active" and tot is not None and needed is not None and tot == needed - 1,
        })
    for i, s in enumerate(side_out):   # 聽牌／淘汰可同時成立；S08／S09 只讀此欄
        s["facing_elimination"] = side_out[1 - i]["clinch"] if len(side_out) == 2 else False

    corrections = []
    for g in rows:
        if g.key in signal_keys:
            corrections.append({"game_key": playoff_state.key_json(g.key), "reason": "official_change_unresolved"})
        elif g.official_status == "final" and not g.completed:
            corrections.append({"game_key": playoff_state.key_json(g.key), "reason": "official_final_not_completed"})
    for k in sorted(signal_keys):
        if k[1] == kind and k not in {g.key for g in rows}:
            corrections.append({"game_key": playoff_state.key_json(k), "reason": "official_change_unresolved"})

    return {
        "kind_code": kind,
        "series_id": {"year": year, "kind_code": kind, "rule_version": rule_version, "teams": codes},
        "participants_status": "known" if len(known) == 2 else "pending_e_winner" if kind == "C" else "unknown",
        "best_of": fmt.best_of if fmt else None,
        "wins_needed": needed,
        "sides": side_out,
        "ties": ties,
        "series_status": status,
        "conflict_reason": conflict,
        "winner": winner,
        "decided_by_game_key": playoff_state.key_json(decided_by),
        "summary_kind": playoff_state.SUMMARY_KIND[kind],
        "corrections": corrections,
        "counted_game_keys": [playoff_state.key_json(k) for k in sorted(counted)],
    }


def _participants_unsourced(games, kind) -> list[str | None]:
    """規則未建檔年：參賽隊只能讀真實列（首場的主客），不推導。"""
    rows = _sorted_games(games, kind)
    if not rows:
        return [None, None]
    return [rows[0].away_team_code, rows[0].home_team_code]


def _announcement_mismatch(plan: dict, ann: AnnouncementRef | None) -> bool:
    if ann is None or plan["status"] != "derived":
        return False
    e = plan["E"]
    handicap = [c for c, n in e["initial_wins"].items() if n > 0]
    return (set(e["teams"]) != set(ann.e_teams) or handicap != [ann.e_handicap_team]
            or plan["C"]["seed"] != ann.c_seeded_team)


def compute_series(rule: SeasonRule | None, standings: StandingsFacts | None,
                   games: list[GameFact], *, year: int,
                   signal_keys: frozenset = frozenset()) -> tuple[dict, dict]:
    """推導＋計數 E、C 兩個系列；回 (series_by_kind, plan)。"""
    plan = derive_series_plan(rule, standings)
    mismatch = _announcement_mismatch(plan, rule.announcement if rule else None)
    basis = "announcement_confirmed" if rule and rule.announcement and not mismatch else "rule_standings"
    rv = rule.rule_version if rule else None
    if rule is None or plan["status"] != "derived":
        out = {}
        for kind in ("E", "C"):
            teams = _participants_unsourced(games, kind)
            out[kind] = tally_series(kind, rule.format(kind) if rule else None,
                                     [(t, None) for t in teams], games, year=year, rule_version=rv,
                                     signal_keys=signal_keys)
        return out, plan
    e_teams = plan["E"]["teams"]
    e = tally_series("E", rule.format("E"), [(t, plan["E"]["initial_wins"][t]) for t in e_teams], games,
                     year=year, rule_version=rv, signal_keys=signal_keys, initial_wins_basis=basis)
    seed = plan["C"]["seed"]
    opponent = e["winner"] if e["series_status"] == "decided" else None
    c = tally_series("C", rule.format("C"), [(seed, plan["C"]["seed_initial_wins"]), (opponent, 0)], games,
                     year=year, rule_version=rv, signal_keys=signal_keys, initial_wins_basis=basis)
    if mismatch:
        for s in (e, c):
            s.update(series_status="unknown", conflict_reason="announcement_mismatch", winner=None,
                     decided_by_game_key=None)
    return {"E": e, "C": c}, plan


# —— 公告安排 × 真實列（原 TS ``buildPostseasonJourney`` 的歸併，改由 Python 唯一計算） ——

_TAIPEI_OFFSET = "+08:00"


def slot_start(slot: ArrangedSlot, display_date: str) -> datetime:
    """公告開賽時刻（台北）；沒有開賽時刻時取當天 24:00 才算「已過」。"""
    if slot.start:
        return datetime.fromisoformat(f"{display_date}T{slot.start}:00{_TAIPEI_OFFSET}")
    return datetime.fromisoformat(f"{display_date}T00:00:00{_TAIPEI_OFFSET}") + timedelta(days=1)


def arrange(rule: SeasonRule, games: list[GameFact], series: dict, *, now: datetime) -> dict:
    """公告安排逐格對到真實列並給顯示狀態；原安排欄位保留供追溯。

    歸併（沿 #237）：E 以官方場號＋主客一致；C 只認「同一天唯一一場 C 列」。
    **公告沒有、但真實存在的 E／C 列**（動態官方加賽 G8、主客或日期對不上公告的列）另成一格
    （``announced=false``，``seq``＝該列在系列真實列中的場序），一樣進下一場與 remaining——
    ⛔ 不由公告序號發明 sno、⛔ 不把它塞進公告轉錄（#283 再審 F1）。
    顯示狀態：final（canonical 完賽）→ not_needed（系列已 decided 且該格未完賽，§63 剩餘比賽取消）
    → result_pending（已過預定開賽、無完賽）→ scheduled（有列）→ announced（無列）。
    """
    by_key = {g.key: g for g in games}
    c_rows = [g for g in games if g.kind_code == "C"]
    announced_c = {s.date for s in rule.arrangement if s.kind == "C"}
    c_moved = any(g.game_date and g.game_date.isoformat() not in announced_c for g in c_rows)

    def status_of(kind: str, row: GameFact | None, start: datetime) -> str:
        if row is not None and row.completed:
            return "final"
        if series[kind]["series_status"] == "decided":
            return "not_needed"
        if now >= start:
            return "result_pending"
        return "scheduled" if row else "announced"

    slots, starts, matched = [], {}, set()
    for slot in rule.arrangement:
        row: GameFact | None = None
        change: dict | None = None
        if slot.kind == "E" and slot.official_sno is not None:
            cand = by_key.get((rule.year, "E", slot.official_sno))
            away = slot.away.code if slot.away else None
            home = slot.home.code if slot.home else None
            if cand and cand.away_team_code == away and cand.home_team_code == home:
                row = cand
                if cand.game_date and cand.game_date.isoformat() != slot.date:
                    change = {"kind": "moved", "announced_date": slot.date}
            elif cand:
                change = {"kind": "changed"}
        elif slot.kind == "C":
            same_day = [g for g in c_rows if g.game_date and g.game_date.isoformat() == slot.date]
            if len(same_day) == 1:
                row = same_day[0]
            elif len(same_day) > 1 or c_moved:
                change = {"kind": "changed"}
        if row is not None:
            matched.add(row.key)
        display_date = row.game_date.isoformat() if row and row.game_date else slot.date
        start = slot_start(slot, display_date)
        status = status_of(slot.kind, row, start)
        starts[slot.key] = start
        slots.append({
            "slot_id": slot.key, "kind_code": slot.kind, "seq": slot.seq, "announced": True,
            "announced_date": slot.date, "date": display_date, "start": slot.start,
            "away": slot.away.to_json() if slot.away else None,
            "home": slot.home.to_json() if slot.home else None,
            "venue": slot.venue.to_json(), "conditional": slot.conditional,
            "official_sno": slot.official_sno,
            "game_key": playoff_state.key_json(row.key) if row else None,
            "change": change,
            "display_status": status,
            "hidden_not_needed": status == "not_needed",
        })

    # 公告外的真實列（真實 DB 列永遠出現在旅程裡）。
    for kind in ("E", "C"):
        for seq, row in enumerate(_sorted_games(games, kind), start=1):
            if row.key in matched or row.game_date is None:
                continue
            slot_id = f"{kind}-sno{row.game_sno}"
            # cpbl.games 沒有開賽時刻：以當天 24:00 才算「已過」（與公告無時刻的格同一規則）。
            start = datetime.fromisoformat(f"{row.game_date.isoformat()}T00:00:00{_TAIPEI_OFFSET}") + timedelta(days=1)
            status = status_of(kind, row, start)
            starts[slot_id] = start
            slots.append({
                "slot_id": slot_id, "kind_code": kind, "seq": seq, "announced": False,
                "announced_date": None, "date": row.game_date.isoformat(), "start": None,
                "away": {"code": row.away_team_code}, "home": {"code": row.home_team_code},
                "venue": {"name": row.venue} if row.venue else {"unknown": True}, "conditional": False,
                "official_sno": row.game_sno if kind == "E" else None,
                "game_key": playoff_state.key_json(row.key),
                "change": None,
                "display_status": status,
                "hidden_not_needed": status == "not_needed",
            })

    def is_open(s: dict) -> bool:
        return s["display_status"] not in ("final", "not_needed")

    ordered = sorted(slots, key=lambda s: starts[s["slot_id"]])
    nxt = (next((s for s in ordered if is_open(s) and s["display_status"] != "result_pending"), None)
           or next((s for s in ordered if is_open(s)), None))
    return {
        "slots": slots,
        "next_slot_id": nxt["slot_id"] if nxt else None,
        "remaining": series["C"]["series_status"] != "decided" and any(is_open(s) for s in slots),
    }


def announcement_json(ann: AnnouncementRef, rule: SeasonRule) -> dict:
    lead = lambda r: {"url": r.url, "label": r.label, "published_on": r.published_on, "kind": r.kind}  # noqa: E731
    e, c = rule.format("E"), rule.format("C")
    return {
        "url": ann.url, "published_on": ann.published_on, "captured_at": ann.captured_at,
        "checks": [{"on": x.on, "scope": x.scope, "url": x.url, "ok": x.ok, "note": x.note} for x in ann.checks],
        "series": {
            "E": {"name": ann.e_name, "best_of": e.best_of, "wins_needed": e.wins_needed,
                  "handicap_team": ann.e_handicap_team, "teams": list(ann.e_teams),
                  "roster_leads": [lead(r) for r in ann.e_roster_leads]},
            "C": {"name": ann.c_name, "best_of": c.best_of, "wins_needed": c.wins_needed,
                  "seeded_team": ann.c_seeded_team, "opponent_from": "E",
                  "roster_leads": [lead(r) for r in ann.c_roster_leads]},
        },
        "reserve_days": [{"date": d, "series": s, "note": n} for d, s, n in ann.reserve_days],
    }


# —— 輸入、組裝與讀取 ——

@dataclass
class SeriesInputs:
    """一次唯讀交易讀到的全部事實（測試可直接構造）。"""
    year: int
    games: list[GameFact]
    standings: StandingsFacts | None = None
    statuses_ok: bool = True
    change_signals: list[dict] = field(default_factory=list)
    last_refresh: dict | None = None
    analysis: dict = field(default_factory=dict)            # key → published／reconciling／pending
    starters: dict = field(default_factory=dict)            # key → {team: starter_status}
    rosters: dict = field(default_factory=dict)             # team → roster_status（S03 前恆 missing）
    registrations: dict = field(default_factory=dict)       # key → [RegistrationObservation]
    live: dict = field(default_factory=dict)                # key → phase
    manifest: list[dict] = field(default_factory=list)
    rule: SeasonRule | None = None
    rule_given: bool = False                                # True ⇒ 用 ``rule``（測試注入），否則查 SEASON_RULES


def _hash(value) -> str:
    if isinstance(value, dict):   # 場次鍵是 tuple：轉成可排序字串再雜湊
        value = {"/".join(map(str, k)) if isinstance(k, tuple) else k: v for k, v in value.items()}
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def compute_series_context(inputs: SeriesInputs, *, now: datetime) -> dict:
    """``postseason-series-context/v2``：同輸入＋同 now 必得同輸出（JSON-able）。"""
    year = inputs.year
    rule = inputs.rule if inputs.rule_given else SEASON_RULES.get(year)
    taipei_day = taipei_date(now)
    signal_keys = frozenset((int(s["year"]), s["kind_code"], int(s["game_sno"])) for s in inputs.change_signals)
    series, plan = compute_series(rule, inputs.standings, inputs.games, year=year, signal_keys=signal_keys)

    statuses = ({g.key: g.official_status for g in inputs.games} if inputs.statuses_ok else None)
    coverage = coverage_verdict(
        [{"year": g.year, "kind_code": g.kind_code, "game_sno": g.game_sno,
          "game_date": g.game_date.isoformat() if g.game_date else None}
         for g in inputs.games if not g.completed and g.game_date],
        statuses, taipei_day=taipei_day, change_signals=inputs.change_signals,
    )
    pending_keys = frozenset((int(p["year"]), p["kind_code"], int(p["game_sno"])) for p in coverage["pending_games"])

    # 每系列目標場的先發狀態、隊伍三欄（32／28／先發分開，互不推導）。
    state_games = [g.as_state_input() for g in inputs.games]
    state = playoff_state.layout_state(series, state_games, live=inputs.live, starters=inputs.starters,
                                       rosters=inputs.rosters, pending_keys=pending_keys,
                                       taipei_day=taipei_day, now=now)
    for kind, s in series.items():
        s["analysis_status"] = playoff_state.analysis_status(
            [g.as_state_input() for g in inputs.games if g.kind_code == kind], inputs.analysis)
    teams = []
    for kind in ("E", "C"):
        target = state["by_series"][kind]["target_game_key"]
        tkey = (target["year"], target["kind_code"], target["game_sno"]) if target else None
        for side in series[kind]["sides"]:
            code = side["team_code"]
            if not code:
                continue
            regs = [r for r in inputs.registrations.get(tkey, []) if r.get("team_code") == code] if tkey else []
            teams.append({
                "series": kind, "team_code": code,
                "roster_status": inputs.rosters.get(code, "missing"),
                "registration_status": regs[-1]["status"] if regs else "unknown",
                "starter_status": inputs.starters.get(tkey, {}).get(code, "missing") if tkey else "missing",
            })

    counted = {(k["year"], k["kind_code"], k["game_sno"]) for s in series.values() for k in s["counted_game_keys"]}
    order = {g.key: i + 1 for kind in ("E", "C") for i, g in enumerate(_sorted_games(inputs.games, kind))}
    arrangement = arrange(rule, inputs.games, series, now=now) if rule and rule.arrangement else None
    slot_of = {(s["game_key"]["year"], s["game_key"]["kind_code"], s["game_key"]["game_sno"]): s["slot_id"]
               for s in (arrangement or {}).get("slots", []) if s["game_key"]}
    games_out = []
    for g in sorted(inputs.games, key=lambda g: (g.game_date or date.max, g.kind_code, g.game_sno)):
        games_out.append({
            "game_key": playoff_state.key_json(g.key),
            "official_game_sno": g.game_sno,
            "series_game_no": order[g.key],
            "announced_slot_id": slot_of.get(g.key),
            "game_date": g.game_date.isoformat() if g.game_date else None,
            "venue": g.venue,
            "away_team_code": g.away_team_code, "home_team_code": g.home_team_code,
            "away_score": g.away_score if g.completed else None,
            "home_score": g.home_score if g.completed else None,
            "completed": g.completed,
            "result": g.result,
            "counted_for_wins": g.key in counted,
            "official_status": g.official_status,
            "target_status": playoff_state.target_status(g.as_state_input(), live_phase=inputs.live.get(g.key),
                                                         taipei_day=taipei_day),
            "official_mvp_id": g.mvp_id,
            "analysis": inputs.analysis.get(g.key, "pending") if g.completed else None,
        })

    missing = list(plan["missing_reason"])
    if any(s.get("conflict_reason") == "announcement_mismatch" for s in series.values()):
        missing.append("announcement_mismatch")
    missing += ["roster_store_not_delivered", "registration_source_not_delivered", "ended_at_unavailable"]
    if not inputs.statuses_ok:
        missing.append("official_status_unavailable")
    for m in inputs.manifest:
        if m.get("status") == "unavailable":
            missing.append(f"{m['source']}_unavailable")

    rule_version = rule.rule_version if rule else None
    manifest = [{"source": "rule_constant", "scope": str(year), "version_or_hash": rule_version,
                 "observed_at": None, "status": "ok" if rule else "unsourced"}, *inputs.manifest]
    context_version = _hash({"algorithm_version": SERIES_ALGO_VERSION, "rule_version": rule_version,
                             "sources": [{k: v for k, v in m.items() if k != "observed_at"} for m in manifest]})
    done = [g for g in inputs.games if g.completed]
    return {
        "contract": CONTEXT_CONTRACT,
        "algorithm_version": SERIES_ALGO_VERSION,
        "year": year,
        "rule_version": rule_version,
        "rule_status": "sourced" if rule else "unsourced",
        "context_version": context_version,
        "source_manifest": manifest,
        "as_of": {
            "now": now.isoformat(),
            "taipei_date": taipei_day.isoformat(),
            "last_completed_game_date": max((g.game_date.isoformat() for g in done if g.game_date), default=None),
            "last_refresh_at": _iso(inputs.last_refresh["at"]) if inputs.last_refresh else None,
            "last_refresh_ok": inputs.last_refresh["ok"] if inputs.last_refresh else None,
            "last_refresh_scope": inputs.last_refresh["scope"] if inputs.last_refresh else None,
            "coverage": coverage["status"],
            "pending_games": coverage["pending_games"],
        },
        "coverage": coverage["status"],
        "missing_reason": list(dict.fromkeys(missing)),
        "series": series,
        "games": games_out,
        "announcement": announcement_json(rule.announcement, rule) if rule and rule.announcement else None,
        "arrangement": arrangement,
        "state": state,
        "teams": teams,
    }


GAMES_V2_SQL = f"""
    SELECT g.year, g.kind_code, g.game_sno, g.game_date, g.venue, g.mvp_id,
           g.away_team_code, g.home_team_code, g.away_score, g.home_score,
           COALESCE({_DONE_AS_OF}, FALSE) AS completed
    FROM cpbl.games g
    WHERE g.year = %(year)s AND g.kind_code IN ('E', 'C')
    ORDER BY g.game_date, g.kind_code, g.game_sno
"""

OFFICIAL_STANDINGS_SQL = """
    SELECT season_code, team_code, w, l, t FROM cpbl.team_standings
    WHERE year = %(year)s AND kind_code = 'A' AND season_code IN (0, 1, 2)
    ORDER BY season_code, team_code
"""

# 無官方 team_standings 的年份：與 standings._computed_standings 同一判準（canonical 完賽、kind A），
# 半季以官方內建 game_season_code 切。
COMPUTED_STANDINGS_SQL = f"""
    SELECT seg, tc, sum(w)::int, sum(l)::int, sum(t)::int FROM (
      SELECT g.game_season_code AS seg, g.home_team_code AS tc,
             (g.home_score > g.away_score)::int AS w, (g.home_score < g.away_score)::int AS l,
             (g.home_score = g.away_score)::int AS t
      FROM cpbl.games g WHERE g.year = %(year)s AND g.kind_code = 'A' AND {_DONE_AS_OF}
      UNION ALL
      SELECT g.game_season_code, g.away_team_code,
             (g.away_score > g.home_score)::int, (g.away_score < g.home_score)::int,
             (g.home_score = g.away_score)::int
      FROM cpbl.games g WHERE g.year = %(year)s AND g.kind_code = 'A' AND {_DONE_AS_OF}
    ) x GROUP BY seg, tc ORDER BY seg, tc
"""

REVISIONS_V2_SQL = f"""
    SELECT year, kind_code, game_sno, raw_present_status, raw_game_result,
           raw_game_date, payload_hash, fetched_at, last_seen_at,
           raw_payload->>'IsPlayBall' AS is_play_ball
    FROM cpbl.game_schedule_status_revisions
    WHERE year = %(year)s AND kind_code IN ('E', 'C')
    ORDER BY year, kind_code, game_sno, {OFFICIAL_SCHEDULE_ORDER_BY}
"""

RECAP_BUILDS_SQL = """
    SELECT year, kind_code, game_sno, state, built_at FROM cpbl.game_recap_builds
    WHERE year = %(year)s AND kind_code IN ('E', 'C')
      AND state IN ('published', 'reconciliation_required')
    ORDER BY year, kind_code, game_sno, built_at
"""

LINEUP_SQL = """
    SELECT year, kind_code, game_sno, source_type, source_url, fetched_at,
           content_hash, raw_status, raw_payload, last_seen_at
    FROM cpbl.game_lineup_announcement_revisions
    WHERE year = %(year)s AND source_type = 'stats_datagame'
      AND kind_code = ANY(%(kinds)s) AND game_sno = ANY(%(snos)s)
    ORDER BY kind_code, game_sno, fetched_at
"""


def _optional(cur, fn):
    """非 games 來源：失敗只降級（回 None），且以 SAVEPOINT 隔離，不讓交易進入 aborted。"""
    connection = getattr(cur, "connection", None)
    try:
        if connection is not None and hasattr(connection, "transaction"):
            with connection.transaction():
                return fn()
        return fn()
    except Exception:  # noqa: BLE001 — 缺表／權限：該欄 unknown＋missing_reason
        return None


def registration_observations(cur, game_key: tuple[int, str, int]) -> list[dict]:
    """28 人登錄觀測讀取契約（來源與保存歸 S11 #292）。

    回 ``[{team_code, status, member_ids, source_url, source_hash, observed_at}]``。S11 交付前
    沒有可靠來源 ⇒ 回空 ⇒ ``registration_status=unknown``＋``registration_source_not_delivered``。
    ⛔ 由 32 人名單、先發九人或 box 出賽推算。"""
    return []


def _starter_status(selected: dict, team: str, distinct_hashes: int) -> str:
    """074 選版結果 → 單隊 starter_status。只消費 ``reports.announcements.select``，不改它。"""
    ev = (selected.get("team_evidence") or {}).get(team) or {}
    if ev.get("status") == "announced":
        return "changed" if distinct_hashes > 1 else "announced"
    return "missing" if not selected.get("source_version") else "unknown"


def read_series_inputs(cur, year: int, *, now: datetime, live_reader=None) -> SeriesInputs:
    """薄 I/O：呼叫端已開好單一 ``REPEATABLE READ READ ONLY`` 交易；本函式只 SELECT。

    games 失敗上浮（空清單會被讀成「沒有季後賽」）；其餘來源各自降級並記入 source_manifest。"""
    from cpbl.reports import announcements as lineup  # 只 import；選版規則屬 074 owner

    observed = now.isoformat()
    taipei_day = taipei_date(now)
    cur.execute(GAMES_V2_SQL, {"year": year, "as_of": taipei_day})
    rows = _dicts(cur)
    manifest = [{"source": "games", "scope": f"{year}/E,C", "version_or_hash": _hash(rows),
                 "observed_at": observed, "status": "ok"}]

    def standings_read():
        cur.execute(OFFICIAL_STANDINGS_SQL, {"year": year})
        official = cur.fetchall()
        if official:
            return "official", [(str(seg), *rest) for seg, *rest in official]
        cur.execute(COMPUTED_STANDINGS_SQL, {"year": year, "as_of": taipei_day})
        return "computed", cur.fetchall()

    st = _optional(cur, standings_read)
    standings = None
    if st:
        source, recs = st
        seg = {"0": [], "1": [], "2": []}
        for s, tc, w, l, t in recs:  # noqa: E741
            seg.setdefault(str(s), []).append(TeamRecord(tc, int(w), int(l), int(t or 0)))
        full = seg["0"] if source == "official" else _sum_records(seg)
        standings = StandingsFacts(source, tuple(full), tuple(seg["1"]), tuple(seg["2"]))
    manifest.append({"source": "standings", "scope": f"{year}/A/{st[0] if st else '-'}",
                     "version_or_hash": _hash(st[1]) if st else None, "observed_at": observed,
                     "status": "ok" if st else "unavailable"})

    def revisions_read():
        cur.execute(REVISIONS_V2_SQL, {"year": year})
        return _dicts(cur)

    revs = _optional(cur, revisions_read)
    grouped: dict[tuple[int, str, int], list[dict]] = {}
    for rev in revs or []:
        grouped.setdefault((rev["year"], rev["kind_code"], rev["game_sno"]), []).append(rev)
    statuses = {k: official_status(g)[0] for k, g in grouped.items()}
    first_final = {k: min((r["fetched_at"] for r in g if official_status([r])[0] == "final"), default=None)
                   for k, g in grouped.items()}
    manifest.append({"source": "schedule_revisions", "scope": f"{year}/E,C",
                     "version_or_hash": _hash([[r["year"], r["kind_code"], r["game_sno"], r["payload_hash"]]
                                               for r in revs]) if revs is not None else None,
                     "observed_at": observed, "status": "ok" if revs is not None else "unavailable"})

    def signals_read():
        cur.execute(CHANGE_SIGNALS_SQL, {"kinds": list(POSTSEASON_KINDS), "season": year})
        return signal_games(_dicts(cur))

    changes = _optional(cur, signals_read)
    manifest.append({"source": "change_signals", "scope": f"{year}/E,C", "version_or_hash": _hash(changes),
                     "observed_at": observed, "status": "ok" if changes is not None else "unavailable"})

    def refresh_read():
        cur.execute(REFRESH_SQL)
        r = cur.fetchone()
        return {"at": r[0], "ok": r[1], "scope": r[2]} if r else {}

    refresh = _optional(cur, refresh_read)
    manifest.append({"source": "refresh_log", "scope": "latest", "version_or_hash": _hash(refresh),
                     "observed_at": observed, "status": "ok" if refresh is not None else "unavailable"})

    def recap_read():
        cur.execute(RECAP_BUILDS_SQL, {"year": year})
        out: dict[tuple[int, str, int], str] = {}
        for r in _dicts(cur):
            # 依 built_at 升冪讀，最新的 published／reconciliation_required 決定該場分析狀態
            out[(r["year"], r["kind_code"], r["game_sno"])] = "published" if r["state"] == "published" else "reconciling"
        return out

    analysis = _optional(cur, recap_read)
    manifest.append({"source": "recap_builds", "scope": f"{year}/E,C", "version_or_hash": _hash(analysis),
                     "observed_at": observed, "status": "ok" if analysis is not None else "unavailable"})

    games = [GameFact(
        year=int(r["year"]), kind_code=r["kind_code"], game_sno=int(r["game_sno"]), game_date=r["game_date"],
        away_team_code=r["away_team_code"], home_team_code=r["home_team_code"],
        away_score=r["away_score"], home_score=r["home_score"], completed=bool(r["completed"]),
        official_status=statuses.get((r["year"], r["kind_code"], r["game_sno"]), "unknown") if revs is not None
        else "unknown",
        venue=r.get("venue") or None, mvp_id=r.get("mvp_id") or None,
        first_observed_final_at=first_final.get((r["year"], r["kind_code"], r["game_sno"])),
    ) for r in rows]

    # 先發只讀每系列「最早未完賽」那一場（T1／T3 的目標場）。
    candidates = []
    for kind in ("E", "C"):
        nxt = next((g for g in _sorted_games(games, kind) if not g.completed), None)
        if nxt:
            candidates.append(nxt)
    # 即時快照（#283 再審 F2）：任何「可能正在比」的未完賽列都要讀，不能只看最早那一場——較早場次
    # 尚未同步為完賽、或保留未續完時，後一場仍可能是唯一 live。可能＝日期不晚於台北今天、或有未決
    # 官方異動訊號（日期可能已改到今天），另含每系列最早未完賽列。日期在未來且無異動訊號的列不會 live。
    signal_keys = {(int(c["year"]), c["kind_code"], int(c["game_sno"])) for c in changes or []}
    live_candidates = [g for g in sorted(games, key=lambda g: (g.game_date or date.max, g.kind_code, g.game_sno))
                       if not g.completed and (g in candidates or g.key in signal_keys
                                               or (g.game_date is not None and g.game_date <= taipei_day))]

    def lineup_read():
        cur.execute(LINEUP_SQL, {"year": year, "kinds": [g.kind_code for g in candidates],
                                 "snos": [g.game_sno for g in candidates]})
        return _dicts(cur)

    lineup_rows = _optional(cur, lineup_read) if candidates else []
    starters: dict = {}
    for g in candidates:
        if lineup_rows is None:
            starters[g.key] = {g.away_team_code: "unknown", g.home_team_code: "unknown"}
            continue
        target = {"year": g.year, "kind_code": g.kind_code, "game_sno": g.game_sno,
                  "away_team_code": g.away_team_code, "home_team_code": g.home_team_code}
        scoped = [r for r in lineup_rows if (r["kind_code"], r["game_sno"]) == (g.kind_code, g.game_sno)]
        schedule = grouped.get(g.key, [])
        selected = lineup.select(scoped, schedule, target)
        hashes = len({r["content_hash"] for r in scoped})
        starters[g.key] = {t: _starter_status(selected, t, hashes) for t in (g.away_team_code, g.home_team_code)}
    manifest.append({"source": "lineup_announcements", "scope": ",".join(f"{g.kind_code}{g.game_sno}"
                                                                          for g in candidates) or "-",
                     "version_or_hash": _hash([[r["kind_code"], r["game_sno"], r["content_hash"]]
                                               for r in lineup_rows or []]),
                     "observed_at": observed, "status": "ok" if lineup_rows is not None else "unavailable"})

    live: dict = {}
    live_ok = True
    if live_reader is not None:
        for g in live_candidates:
            try:
                snap = live_reader(g.year, g.kind_code, g.game_sno, now=now)
            except Exception:  # noqa: BLE001 — 快取不可用 ⇒ 不宣稱 live，也不再逐場等逾時
                live_ok = False
                break
            if snap and snap.get("phase"):
                live[g.key] = snap["phase"]
    manifest.append({"source": "live_snapshot", "scope": ",".join(f"{g.kind_code}{g.game_sno}"
                                                                   for g in live_candidates) or "-",
                     "version_or_hash": _hash(sorted((list(k), v) for k, v in live.items())),
                     "observed_at": observed,
                     "status": "ok" if live_ok and live_reader is not None else "unavailable"})

    registrations = {g.key: registration_observations(cur, g.key)
                     for g in [*candidates, *(x for x in live_candidates if x not in candidates)]}
    return SeriesInputs(
        year=year, games=games, standings=standings, statuses_ok=revs is not None,
        change_signals=changes or [], last_refresh=refresh or None, analysis=analysis or {},
        starters=starters, rosters={}, registrations=registrations, live=live, manifest=manifest,
    )


def _sum_records(seg: dict) -> list[TeamRecord]:
    acc: dict[str, list[int]] = {}
    for recs in seg.values():
        for r in recs:
            a = acc.setdefault(r.team_code, [0, 0, 0])
            a[0] += r.w
            a[1] += r.l
            a[2] += r.t
    return [TeamRecord(tc, *v) for tc, v in sorted(acc.items())]


READ_ONLY_TXN = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"


def postseason_series_context(year: int, *, now: datetime | None = None,
                              connect: Callable | None = None, live_reader=None) -> dict:
    """``postseason-series-context/v2``：單一 REPEATABLE READ READ ONLY 交易讀完全部來源。"""
    if connect is None:
        from cpbl.db import conn as connect
    now = now or datetime.now(UTC)
    with connect() as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute(READ_ONLY_TXN)
            inputs = read_series_inputs(cur, year, now=now, live_reader=live_reader)
    return compute_series_context(inputs, now=now)
