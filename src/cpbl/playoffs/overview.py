"""季後專頁 overview 讀取面（#285 S04）：第 1 區（系列賽表現）＋各區呼叫參數。

分兩層（沿 :mod:`cpbl.postseason_contract` 慣例）：

- :func:`read_overview_inputs`：薄 I/O，呼叫端已開好單一 ``REPEATABLE READ READ ONLY`` 交易；只 SELECT。
  S02 inputs 與 MVP 姓名在**同一交易**讀，姓名只批次查一次。
- :func:`compute_overview`：純組裝，同輸入同輸出。

紅線：

1. 只組裝、不重算：勝場、完賽、目標場、覆蓋全取 S02 ``compute_series_context`` 原值；
   ⛔ 在這裡或前端重算勝場／完賽／T 狀態。
2. ⛔ 讀 ``games.*_starter_id``：第 1 區預告不顯示先發投手（需求方裁定 D7，issuecomment-6184623087），
   先發只由第 4 區灰列呈現；S11 定案後兩處一起接。
3. ⛔ 讀 ``reports/background``／``reports/assembler``（#272 共享區）；GET ⛔ 寫入、⛔ 觸發爬取。
4. 系列一句只給原值（勝場、規則勝、勝隊），中文句由前端組；後端不產文案。
5. ``context_version`` 原樣轉出 S02 的值，與 #289 watch 同源可比；姓名不進版本。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from cpbl import postseason_contract as contract
from cpbl.api.helpers import _dicts

CONTRACT = "playoffs-overview/v1"
SERIES_ORDER = ("E", "C")

PLAYERS_SQL = "SELECT id, name FROM cpbl.players WHERE id = ANY(%(ids)s)"


@dataclass
class OverviewInputs:
    """一次唯讀交易讀到的全部事實（測試可直接構造）。"""

    context: dict                       # S02 compute_series_context 輸出
    names: dict[str, str] | None        # player_id → name；None ⇒ players 讀取失敗


def _key(gk: dict | None) -> tuple[int, str, int] | None:
    return (int(gk["year"]), str(gk["kind_code"]), int(gk["game_sno"])) if gk else None


def mvp_ids(context: dict) -> list[str]:
    """完賽場的官方 MVP id（去重、保序）；未完賽場不讀。"""
    return list(dict.fromkeys(g["official_mvp_id"] for g in context["games"]
                              if g["completed"] and g.get("official_mvp_id")))


def _mvp(game: dict, names: dict[str, str] | None) -> tuple[dict | None, str | None]:
    """完賽卡的 MVP 與缺值理由。未完賽 ⇒ (None, None)，⛔ 寫「未公布」。"""
    if not game["completed"]:
        return None, None
    mid = game.get("official_mvp_id")
    if not mid:
        return None, "official_mvp_not_ingested"           # 本站尚未取得，不等於官方未公布
    name = (names or {}).get(mid)
    return {"id": mid, "name": name}, (None if name else "player_name_unavailable")


def _card(game: dict, slot: dict | None, names: dict[str, str] | None) -> dict:
    mvp, mvp_missing = _mvp(game, names)
    return {
        "game_key": game["game_key"],
        "official_game_sno": game["official_game_sno"],
        "series_game_no": game["series_game_no"],
        "announced_slot_id": game["announced_slot_id"],
        "game_date": game["game_date"],
        "start": slot.get("start") if slot else None,
        "venue": game["venue"],
        "away_team_code": game["away_team_code"],
        "home_team_code": game["home_team_code"],
        "completed": game["completed"],
        "result": game["result"],
        "away_score": game["away_score"],      # S02：未完賽恆 null
        "home_score": game["home_score"],
        "counted_for_wins": game["counted_for_wins"],
        "official_status": game["official_status"],
        "target_status": game["target_status"],
        "display_status": slot.get("display_status") if slot else None,
        "conditional": bool(slot.get("conditional")) if slot else False,
        "hidden_not_needed": bool(slot.get("hidden_not_needed")) if slot else False,
        "mvp": mvp,
        "mvp_missing_reason": mvp_missing,
    }


def _series_block(kind: str, context: dict, names: dict[str, str] | None) -> dict:
    s = context["series"][kind]
    slots = {_key(sl["game_key"]): sl for sl in ((context.get("arrangement") or {}).get("slots") or [])
             if sl.get("game_key")}
    games = [g for g in context["games"] if g["game_key"]["kind_code"] == kind]
    games.sort(key=lambda g: g["series_game_no"])
    return {
        "kind_code": kind,
        "series_id": s["series_id"],
        "participants_status": s["participants_status"],
        "best_of": s["best_of"],
        "wins_needed": s["wins_needed"],
        "series_status": s["series_status"],
        "conflict_reason": s["conflict_reason"],
        "winner": s["winner"],
        "ties": s["ties"],
        "sides": [{k: side[k] for k in ("team_code", "initial_wins", "initial_wins_basis", "game_wins",
                                         "total_wins", "remaining")} for side in s["sides"]],
        "games": [_card(g, slots.get(_key(g["game_key"])), names) for g in games],
    }


def compute_overview(inputs: OverviewInputs) -> dict:
    """``playoffs-overview/v1``：同輸入必得同輸出（JSON-able）。"""
    ctx = inputs.context
    names = inputs.names
    current = ctx["state"]["default_series"]
    target = ctx["state"]["by_series"][current]["target_game_key"]
    has_games = {k: any(g["game_key"]["kind_code"] == k for g in ctx["games"]) for k in SERIES_ORDER}

    blocks = {k: _series_block(k, ctx, names) for k in SERIES_ORDER if has_games[k] or k == current}
    prior = [k for k in SERIES_ORDER[:SERIES_ORDER.index(current)] if has_games[k]]
    previous = blocks[prior[-1]] if prior else None

    next_game = None
    next_reason = None
    if target is None:
        next_reason = "no_target"
    else:
        card = next((c for c in blocks[current]["games"] if _key(c["game_key"]) == _key(target)), None)
        if card is None:
            next_reason = "target_not_in_games"
        elif card["completed"]:
            next_reason = "series_decided" if blocks[current]["series_status"] == "decided" else "target_completed"
        else:
            next_game = card

    series_missing: list[str] = []
    if not has_games[current]:
        series_missing.append("series_games_missing")
    if ctx["coverage"] != "covered":
        series_missing.append(f"coverage_{ctx['coverage']}")
    if names is None and mvp_ids(ctx):  # 無完賽 MVP 時不需要姓名
        series_missing.append("player_names_unavailable")

    ann = ctx.get("announcement")
    ids = mvp_ids(ctx)
    manifest = [*ctx["source_manifest"],
                {"source": "players", "scope": f"mvp:{len(ids)}",
                 "version_or_hash": contract._hash(sorted((names or {}).items())) if names is not None else None,
                 "observed_at": ctx["as_of"]["now"], "status": "ok" if names is not None else "unavailable"}]
    return {
        "contract": CONTRACT,
        "context_contract": ctx["contract"],
        "year": ctx["year"],
        "context_version": ctx["context_version"],
        "default_series": current,
        "series_id": ctx["series"][current]["series_id"],
        "target_game_key": target,
        "as_of": ctx["as_of"],
        "coverage": ctx["coverage"],
        "missing_reason": ctx["missing_reason"],
        "source_manifest": manifest,
        "schedule_source": ({"kind": "official_announcement", "url": ann["url"], "published_on": ann["published_on"]}
                            if ann else None),
        "series_section": {
            "status": "ok" if has_games[current] else "empty",
            "missing_reason": series_missing,
            "previous": previous,
            "current": blocks[current],
            "next_game": next_game,
            "next_game_missing_reason": next_reason,
        },
        "sections": {
            "series": {"status": "ok" if has_games[current] else "empty", "missing_reason": series_missing},
            "watch": {"status": "ok" if target else "no_target", "series": current,
                      "game": target["game_sno"] if target else None},
        },
    }


def read_overview_inputs(cur, year: int, *, now: datetime, live_reader=None) -> OverviewInputs:
    """薄 I/O：S02 inputs＋一次姓名批次查詢，皆在呼叫端開好的同一交易內。"""
    context = contract.compute_series_context(
        contract.read_series_inputs(cur, year, now=now, live_reader=live_reader), now=now)
    ids = mvp_ids(context)
    if not ids:
        return OverviewInputs(context=context, names={})

    def names_read():
        cur.execute(PLAYERS_SQL, {"ids": ids})
        return {r["id"]: r["name"] for r in _dicts(cur) if r.get("name")}

    names = contract._optional(cur, names_read)   # 失敗只降級（SAVEPOINT 隔離），不讓交易 aborted
    return OverviewInputs(context=context, names=names)


READ_ONLY_TXN = contract.READ_ONLY_TXN


def playoffs_overview(year: int, *, now: datetime | None = None, connect: Callable | None = None,
                      live_reader=None) -> dict:
    """``playoffs-overview/v1``：單一 REPEATABLE READ READ ONLY 交易讀完全部來源。"""
    if connect is None:
        from cpbl.db import conn as connect
    now = now or datetime.now(UTC)
    with connect() as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute(READ_ONLY_TXN)
            inputs = read_overview_inputs(cur, year, now=now, live_reader=live_reader)
    return compute_overview(inputs)
