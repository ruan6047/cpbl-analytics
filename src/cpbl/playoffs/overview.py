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
from cpbl.playoffs import series_summary as summary

CONTRACT = "playoffs-overview/v1"
SERIES_ORDER = ("E", "C")

PLAYERS_SQL = "SELECT id, name FROM cpbl.players WHERE id = ANY(%(ids)s)"


@dataclass
class OverviewInputs:
    """一次唯讀交易讀到的全部事實（測試可直接構造）。"""

    context: dict                       # S02 compute_series_context 輸出
    names: dict[str, str] | None        # player_id → name；None ⇒ players 讀取失敗
    # #288 系列累計榜（series_summary.aggregate_all）；None ⇒ 未計算（只見於直接構造的測試）。
    series_summary: dict[str, summary.SeriesAggregate] | None = None
    summary_names: dict[str, str] | None = None   # 榜上／MVP 次數清單姓名（與 names 同一次批次查詢）


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


def compute_overview(inputs: OverviewInputs, series: str | None = None) -> dict:
    """``playoffs-overview/v1``：同輸入必得同輸出（JSON-able）。

    ``series``（E｜C，選填）＝使用者在 ``/playoffs?series=`` 選的系列；未給時用 S02 ``default_series``。
    所選系列只換組裝的軸（區塊、前一系列、目標場、第 4 區參數、累計榜），``default_series`` 與
    ``context_version`` 照舊轉出 S02 原值（#285 批次 B）。
    """
    ctx = inputs.context
    names = inputs.names
    current = series or ctx["state"]["default_series"]
    target = ctx["state"]["by_series"][current]["target_game_key"]
    has_games = {k: any(g["game_key"]["kind_code"] == k for g in ctx["games"]) for k in SERIES_ORDER}
    # 區塊空態＝整年 E／C 都沒有場次列；只有當前系列缺列時前一系列總結照常給，缺列記在 missing_reason
    # （#285 審核 F1：曾以當前系列判空，讓已有的挑戰賽總結被藏起來並誤稱全年無資料）。
    section_status = "ok" if any(has_games.values()) else "empty"

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
    aggs = inputs.series_summary
    manifest = [*ctx["source_manifest"],
                *([summary.manifest_entry(aggs, observed_at=ctx["as_of"]["now"])] if aggs is not None else []),
                {"source": "players", "scope": f"mvp:{len(ids)}",
                 "version_or_hash": contract._hash(sorted((names or {}).items())) if names is not None else None,
                 "observed_at": ctx["as_of"]["now"], "status": "ok" if names is not None else "unavailable"}]
    return {
        "contract": CONTRACT,
        "context_contract": ctx["contract"],
        "year": ctx["year"],
        "context_version": ctx["context_version"],
        "default_series": ctx["state"]["default_series"],
        "selected_series": current,
        "series_id": ctx["series"][current]["series_id"],
        "target_game_key": target,
        "as_of": ctx["as_of"],
        "coverage": ctx["coverage"],
        "missing_reason": ctx["missing_reason"],
        "source_manifest": manifest,
        "schedule_source": ({"kind": "official_announcement", "url": ann["url"], "published_on": ann["published_on"]}
                            if ann else None),
        "series_section": {
            "status": section_status,
            "missing_reason": series_missing,
            "previous": previous,
            "current": blocks[current],
            "next_game": next_game,
            "next_game_missing_reason": next_reason,
        },
        "series_summary": (summary.summary_json(aggs, inputs.summary_names, current=current,
                                                previous=prior[-1] if prior else None)
                           if aggs is not None else None),
        "sections": {
            "series": {"status": section_status, "missing_reason": series_missing},
            "watch": {"status": "ok" if target else "no_target", "series": current,
                      "game": target["game_sno"] if target else None},
        },
    }


def read_overview_inputs(cur, year: int, *, now: datetime, live_reader=None) -> OverviewInputs:
    """薄 I/O：S02 inputs＋一次姓名批次查詢，皆在呼叫端開好的同一交易內。"""
    context = contract.compute_series_context(
        contract.read_series_inputs(cur, year, now=now, live_reader=live_reader), now=now)
    aggs = summary.aggregate_all(context, contract._optional(cur, lambda: summary.read_series_rows(cur, context)),
                                 scorer_for=summary.scorer_for)
    mvp = mvp_ids(context)
    ids = list(dict.fromkeys([*mvp, *summary.player_ids(aggs)]))
    if not ids:
        return OverviewInputs(context=context, names={}, series_summary=aggs, summary_names={})

    def names_read():
        cur.execute(PLAYERS_SQL, {"ids": ids})
        return {r["id"]: r["name"] for r in _dicts(cur) if r.get("name")}

    found = contract._optional(cur, names_read)   # 失敗只降級（SAVEPOINT 隔離），不讓交易 aborted
    # 第 1 區 MVP 姓名只取 MVP id（其版本雜湊不因累計榜擴充 id 集合而變）
    keep = set(mvp)
    names = None if found is None else {k: v for k, v in found.items() if k in keep}
    return OverviewInputs(context=context, names=names, series_summary=aggs, summary_names=found)


READ_ONLY_TXN = contract.READ_ONLY_TXN


def playoffs_overview(year: int, *, series: str | None = None, now: datetime | None = None,
                      connect: Callable | None = None, live_reader=None) -> dict:
    """``playoffs-overview/v1``：單一 REPEATABLE READ READ ONLY 交易讀完全部來源。"""
    if connect is None:
        from cpbl.db import conn as connect
    now = now or datetime.now(UTC)
    with connect() as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute(READ_ONLY_TXN)
            inputs = read_overview_inputs(cur, year, now=now, live_reader=live_reader)
    return compute_overview(inputs, series)
