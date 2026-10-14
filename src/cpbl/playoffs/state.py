"""T0–T5 佈局預設與正交狀態（#283 S02；PRD v2〈賽事狀態與頁面行為〉）。

純函式：輸入只有事實（系列計數、真實場次列、即時觀測、先發／名單狀態）與**注入的現在時刻**；
不讀 DB、不讀時鐘、不讀環境時區。讀取與組裝在 :mod:`cpbl.postseason_contract`。

判定優先序（PRD）：正式 decided → 已觀測 live → 有效賽後 60 分鐘窗口 → 雙方公告 → 正式場間 → 預熱。

紅線：

1. ``target_status == "final"`` 只來自 canonical ``completed``（G03）：非零比分、時間已過、
   刷新成功、即時快照 final 都**不是** final。
2. 60 分鐘窗口只影響版面：從可信 ``ended_at`` 起算；只有 ``first_observed_final_at`` 時標
   ``observed_final``；兩者皆無不開窗。T5 不等窗口、不等 PA（G04）。
3. 下一場無真實 DB 列 ⇒ ``target_game_key`` 為 None（安排待定），不以公告場序綁場號（G02）。
4. 32 人名單（roster）、28 人登錄（registration）、先發（starter）三個狀態互不推導。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta

WINDOW = timedelta(minutes=60)

#: 先發「有效公告」：雙方都在此集合才算鎖定。
VALID_STARTER = frozenset({"announced", "changed"})

LAYOUT_ORDER = {
    "T0": (1, 2, 3, 4),
    "T1": (1, 4, 3, 2),
    "T2": (1, 4, 3, 2),
    "T3": (1, 4, 3, 2),
    "T4": (1, 4, 3, 2),
    "T5": (1, 3, 4, 2),
}

SUMMARY_KIND = {"E": "advance_summary", "C": "championship_summary"}

GameKey = tuple[int, str, int]


def key_of(game: Mapping) -> GameKey:
    return (int(game["year"]), str(game["kind_code"]), int(game["game_sno"]))


def key_json(key: GameKey | None) -> dict | None:
    """契約輸出的場次身分一律三欄（G01）；⛔ 不含 game_season_code。"""
    if key is None:
        return None
    return {"year": key[0], "kind_code": key[1], "game_sno": key[2]}


def _as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def target_status(game: Mapping, *, live_phase: str | None, taipei_day: date) -> str:
    """單場 target_status：scheduled／live／suspended／final／postponed／unknown。

    ``final`` 只認 canonical ``completed``（G03）。即時快照只給 ``live``；快照 ``final`` 但正式未
    入庫 ⇒ 仍是官方狀態推出來的值（通常 unknown／scheduled），待更新由 overlays 呈現。
    """
    if game.get("completed"):
        return "final"
    if live_phase == "live":
        return "live"
    official = game.get("official_status") or "unknown"
    if official == "reserved":
        return "suspended"
    if official == "postponed":
        return "postponed"
    if official == "scheduled":
        return "scheduled"
    if official == "unknown":
        day = _as_date(game.get("game_date"))
        # 官方狀態未知時，只有「還沒到比賽日」能稱已排定；當天與過去一律 unknown。
        return "scheduled" if day is not None and day > taipei_day else "unknown"
    return "unknown"   # 官方 final 但正式未完賽：待更新，不是 final


def window_of(game: Mapping | None, *, now: datetime) -> dict:
    """賽後 60 分鐘窗口。可信 ended_at 優先；只有觀測 final 時標 observed_final；皆無不開窗。"""
    if game is None:
        return {"basis": "unknown", "started_at": None, "ends_at": None, "open": False}
    ended = game.get("ended_at")
    observed = game.get("first_observed_final_at")
    start, basis = (ended, "ended_at") if ended else (observed, "observed_final") if observed else (None, "unknown")
    if start is None:
        return {"basis": "unknown", "started_at": None, "ends_at": None, "open": False}
    ends = start + WINDOW
    return {"basis": basis, "started_at": start.isoformat(), "ends_at": ends.isoformat(), "open": start <= now < ends}


def analysis_status(games: Sequence[Mapping], analysis: Mapping[GameKey, str]) -> str:
    """系列完賽場的 PA 發布狀態：ready／partial／pending／reconciling（與 decided、MVP 互不推導，G04）。"""
    done = [key_of(g) for g in games if g.get("completed")]
    states = [analysis.get(k, "pending") for k in done]
    if any(s == "reconciling" for s in states):
        return "reconciling"
    if not states:
        return "pending"
    published = sum(s == "published" for s in states)
    return "ready" if published == len(states) else "partial" if published else "pending"


def _sorted(games: Sequence[Mapping]) -> list[Mapping]:
    return sorted(games, key=lambda g: (_as_date(g.get("game_date")) or date.max, int(g["game_sno"])))


def _both_valid(starters: Mapping[str, str], teams: Sequence[str | None]) -> bool:
    return all(t and starters.get(t) in VALID_STARTER for t in teams) and len([t for t in teams if t]) == 2


def series_layout(
    series: Mapping,
    games: Sequence[Mapping],
    *,
    live: Mapping[GameKey, str],
    starters: Mapping[GameKey, Mapping[str, str]],
    rosters: Mapping[str, str],
    pending_keys: frozenset[GameKey] = frozenset(),
    taipei_day: date,
    now: datetime,
) -> dict:
    """單一系列的佈局預設。``series``＝tally 輸出（需 ``kind_code``、``series_status``、
    ``decided_by_game_key``、``sides``）；``games``＝該系列的真實 DB 列。"""
    kind = series["kind_code"]
    rows = _sorted([g for g in games if g["kind_code"] == kind])
    done = [g for g in rows if g.get("completed")]
    live_rows = [g for g in rows if not g.get("completed") and live.get(key_of(g)) == "live"]
    open_rows = [g for g in rows if not g.get("completed")]
    teams = [s.get("team_code") for s in series.get("sides", [])]

    def status_of(g: Mapping | None) -> str | None:
        return None if g is None else target_status(g, live_phase=live.get(key_of(g)), taipei_day=taipei_day)

    last_done = done[-1] if done else None
    window = window_of(last_done, now=now)
    next_row = None if series.get("series_status") == "decided" else (open_rows[0] if open_rows else None)

    if series.get("series_status") == "decided":
        dk = series.get("decided_by_game_key")
        target = next((g for g in rows if dk and key_json(key_of(g)) == dk), last_done)
        layout, reason = "T5", "series_decided"
    elif live_rows:
        # 下一場已 live 優先於上一場的回顧窗口；同時多場 live 取最晚那場。
        target, layout, reason = live_rows[-1], "T4", "live_observed"
    elif window["open"]:
        target, layout, reason = last_done, "T4", f"post_game_window_{window['basis']}"
    else:
        target = next_row
        t_starters = starters.get(key_of(next_row), {}) if next_row else {}
        not_started = status_of(next_row) in ("scheduled", "postponed")
        locked = next_row is not None and not_started and _both_valid(t_starters, teams)
        rosters_in = all(t and rosters.get(t) == "submitted" for t in teams) and len(teams) == 2
        if locked and not done and next_row is rows[0] and rosters_in:
            layout, reason = "T1", "first_game_rosters_and_starters"
        elif locked:
            layout, reason = "T3", "starters_announced"
        elif done:
            layout, reason = "T2", "between_games" if next_row else "arrangement_pending"
        else:
            layout, reason = "T0", "warmup"

    overlays: list[str] = []
    t_status = status_of(target)
    if t_status in ("postponed", "suspended"):
        overlays.append(t_status)
    elif t_status == "unknown":
        overlays.append("status_unknown")
    # 本系列任一場（含本站尚無列的新場次）有待更新訊號 ⇒ 待更新提示；不以時間硬切。
    if any(k[1] == kind for k in pending_keys):
        overlays.append("pending_update")

    out = {
        "kind_code": kind,
        "layout_state": layout,
        "layout_reason": reason,
        "section_order": list(LAYOUT_ORDER[layout]),
        "summary_kind": SUMMARY_KIND[kind] if layout == "T5" else None,
        "target_game_key": key_json(key_of(target)) if target is not None else None,
        "target_status": t_status,
        "window": {k: v for k, v in window_of(target if layout == "T4" else last_done, now=now).items() if k != "open"},
        "overlays": overlays,
    }
    return out


def default_series(series_by_kind: Mapping[str, Mapping], live_kinds: Sequence[str]) -> str:
    """預設系列：有 live 取該場系列；E decided 且 C 參賽隊已定 ⇒ C；否則最早未 decided 系列。"""
    if live_kinds:
        return live_kinds[-1]
    e, c = series_by_kind.get("E"), series_by_kind.get("C")
    c_known = bool(c) and all(s.get("team_code") for s in c.get("sides", []))
    if e and e.get("series_status") == "decided" and c_known:
        return "C"
    for kind in ("E", "C"):
        s = series_by_kind.get(kind)
        if s and s.get("series_status") != "decided":
            return kind
    return "C" if c else "E"


def layout_state(
    series_by_kind: Mapping[str, Mapping],
    games: Sequence[Mapping],
    *,
    live: Mapping[GameKey, str],
    starters: Mapping[GameKey, Mapping[str, str]],
    rosters: Mapping[str, str],
    pending_keys: frozenset[GameKey] = frozenset(),
    taipei_day: date,
    now: datetime,
) -> dict:
    """全頁狀態：預設系列的佈局＋各系列各自的佈局（``by_series``）。"""
    by_series = {
        kind: series_layout(s, games, live=live, starters=starters, rosters=rosters,
                            pending_keys=pending_keys, taipei_day=taipei_day, now=now)
        for kind, s in series_by_kind.items()
    }
    live_kinds = [k for k in ("E", "C") if k in by_series and by_series[k]["layout_reason"] == "live_observed"]
    chosen = default_series(series_by_kind, live_kinds)
    return {"default_series": chosen, **by_series[chosen], "by_series": by_series}
