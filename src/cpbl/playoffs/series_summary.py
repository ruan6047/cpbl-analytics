"""季後專頁第 1 區系列累計榜（#288 S07 WP-G2）：打者前 3／投手前 2＋PA/BF＋官方單場 MVP 次數。

分三層（沿 :mod:`cpbl.playoffs.overview` 慣例）：

- :func:`read_series_rows`：薄 I/O，在 overview **同一個** REPEATABLE READ READ ONLY 交易內以
  ``unnest`` 批次讀本年度 E／C 完賽場的 published PA、livelog、換投四壞成員事件與 RE 矩陣；查詢數固定
  （4 支），不隨場數成長。失敗由呼叫端 ``contract._optional`` 降級成 ``None``。
- :func:`aggregate`：純函式。逐場呼叫既有 :func:`pa_facts.delta_re24`（單場頁／recap 共用核心，
  本模組 ⛔ 改它），再依記錄歸屬累計。
- :func:`summary_json`：純組裝，帶入姓名，輸出 ``playoffs-series-summary/v1``。

紅線：

1. **母體**＝S02 context 中該系列 ``completed`` 的場次，以 ``game_key`` 去重；E 與 C 分開算（G09）。
2. **涵蓋**：該場有 published build，且沒有任一打席落在 :data:`GAP_REASONS`（資料缺口）。有缺口的場
   **整場排除**並列入缺場清單（fail closed，不部分採計）；``pa_state_truncated``／``pa_state_non_pa``／
   ``negative_runs_on_play`` 是既有核心的正常歸桶（跑者桶），不算缺口。
3. **打者**歸 ``hitter_acnt``（規則 9.15(b) 記錄歸屬）；**投手**預設 ``end_pitcher_acnt``，打席中換投
   且以四壞收尾時依 :func:`matchup_teams.charged_walk_pitcher`（9.16(h)(1)）；判不出 ⇒ 不歸任何投手，
   記在 ``pitcher_unattributed``（⛔ 歸末投手、⛔ 猜）。投手展示值＝−ΣΔRE24（打者視角轉號，正＝壓制，G08）。
4. 排序用未四捨五入值（6 位）降冪、同值 ``player_id`` 升冪；候選不足就少列（G14）。⛔ 輸出任何
   「MVP」「領先」字樣給 RE24 排名；MVP 次數只計 S02 的官方 ``official_mvp_id``（A05、G07）。
5. 獎項 G2 恆 ``pending_source``；⛔ 從 MVP 次數推任何獎項。後端不產文案，句子由前端組。
6. **三大轉折**（WP-G3）：候選＝本系列**所有已涵蓋場**的打席（⛔ 先在單場截前 N），指標＝|ΔWP|
   （既有 :func:`pa_facts.wp_swings`，各場 final_outcome 依該場比分）。任一已涵蓋場拿不到 WP ⇒ **整組**
   改 |ΔRE24|（不混用兩種指標）；門檻沿用 ``KEY_PLAY_MIN_WP_ABS``／``KEY_PLAY_MIN_ABS``（⛔ 改）。
   平手依（系列場序, pa_index, pa_id）；少於 3 筆不補；取定後依時間排序。有未涵蓋場 ⇒
   ``scope=covered_only``（只能稱「已涵蓋場次轉折」）。WP 解算器由呼叫端注入（``scorer_for``），
   本模組 ⛔ 改模型或門檻。
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from cpbl import postseason_contract as contract
from cpbl.api.matchup_teams import charged_walk_pitcher
from cpbl.models import pa_facts

CONTRACT = "playoffs-series-summary/v1"
ALGORITHM = f"re24-span-{pa_facts.RE_SPAN}/v1"
SERIES_ORDER = ("E", "C")
BATTER_LIMIT = 3
PITCHER_LIMIT = 2
TURNING_LIMIT = 3
RE_CELLS = 24   # 8 壘況 × 3 出局；少於此 delta_re24 無從計算

# 資料缺口：任一打席落在這裡 ⇒ 整場排除。其餘 unavailable 原因是既有核心的正常歸桶。
GAP_REASONS = frozenset({
    "terminal_event_missing",
    "state_incomplete",
    "pa_state_unreliable",
    "pa_state_reconciliation_required",
})

_KEYS = "unnest(%(kinds)s::text[], %(snos)s::int[]) AS k(kind_code, game_sno)"

# 欄位清單取自 pa_facts 的固定常數（與單場頁同一 shape）；值一律參數化。
PA_SQL = f"""
    SELECT pa.kind_code AS _kind_code, pa.game_sno AS _game_sno, b.build_id::text AS _build_id,
           {pa_facts._PA_COLS}
    FROM {_KEYS}
    JOIN cpbl.game_plate_appearances pa
      ON pa.year = %(year)s AND pa.kind_code = k.kind_code AND pa.game_sno = k.game_sno
    JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id AND b.state = 'published'
    ORDER BY pa.kind_code, pa.game_sno, pa.pa_index
"""  # noqa: S608

LIVELOG_SQL = f"""
    SELECT l.kind_code AS _kind_code, l.game_sno AS _game_sno, {pa_facts._LIVELOG_COLS}
    FROM {_KEYS}
    JOIN cpbl.game_livelog l
      ON l.year = %(year)s AND l.kind_code = k.kind_code AND l.game_sno = k.game_sno
"""  # noqa: S608

# 只取打席中換投且以四壞收尾的成員事件（9.16(h)(1) 判定用），依成員順序。
MID_WALK_SQL = f"""
    SELECT pa.kind_code, pa.game_sno, pa.pa_index, e.event_no
    FROM {_KEYS}
    JOIN cpbl.game_plate_appearances pa
      ON pa.year = %(year)s AND pa.kind_code = k.kind_code AND pa.game_sno = k.game_sno
    JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id AND b.state = 'published'
    JOIN cpbl.game_pa_events e ON e.pa_row_id = pa.pa_row_id
    WHERE pa.state = 'ready' AND pa.outcome_family = 'walk'
      AND pa.start_pitcher_acnt <> pa.end_pitcher_acnt
    ORDER BY pa.kind_code, pa.game_sno, pa.pa_index, e.event_position
"""  # noqa: S608

GameKey = tuple[str, int]   # (kind_code, game_sno)；年度由 overview 固定


@dataclass
class SeriesRows:
    """一次唯讀交易讀到的累計榜原料（測試可直接構造）。"""

    pas: dict[GameKey, list[dict]] = field(default_factory=dict)                  # 依 pa_index
    livelog: dict[GameKey, list[dict]] = field(default_factory=dict)
    members: dict[tuple[str, int, int], list[str]] = field(default_factory=dict)  # (kind, sno, pa_index) → 事件號
    re_map: dict[tuple[str, int], float] = field(default_factory=dict)
    build_ids: dict[GameKey, str] = field(default_factory=dict)


def series_games(context: dict, kind: str) -> list[dict]:
    """該系列已完賽場（以 game_key 去重、依系列場序）。"""
    seen: dict[tuple, dict] = {}
    for g in context["games"]:
        gk = g["game_key"]
        if gk["kind_code"] == kind and g["completed"]:
            seen.setdefault((gk["year"], gk["kind_code"], gk["game_sno"]), g)
    return sorted(seen.values(), key=lambda g: g["series_game_no"])


def read_series_rows(cur, context: dict) -> SeriesRows:
    """薄 I/O：本年度 E／C 完賽場一次批次讀完（固定 4 支查詢）。呼叫端以 ``contract._optional`` 包住。"""
    keys = [(kind, int(g["game_key"]["game_sno"])) for kind in SERIES_ORDER for g in series_games(context, kind)]
    rows = SeriesRows()
    if not keys:
        return rows
    params = {"year": context["year"], "kinds": [k for k, _ in keys], "snos": [s for _, s in keys]}

    cur.execute(PA_SQL, params)
    for r in pa_facts._rows(cur):
        key = (r.pop("_kind_code"), int(r.pop("_game_sno")))
        rows.build_ids[key] = r.pop("_build_id")
        rows.pas.setdefault(key, []).append(r)
    cur.execute(LIVELOG_SQL, params)
    for r in pa_facts._rows(cur):
        rows.livelog.setdefault((r.pop("_kind_code"), int(r.pop("_game_sno"))), []).append(r)
    cur.execute(MID_WALK_SQL, params)
    for kind, sno, pa_index, event_no in cur.fetchall():
        rows.members.setdefault((kind, int(sno), int(pa_index)), []).append(str(event_no))
    rows.re_map = pa_facts.load_re_matrix(cur, "C")   # 季後 kind 借一軍例行矩陣（E、C 同一張）
    return rows


@dataclass
class Line:
    player_id: str
    team_code: str | None = None
    value: float = 0.0      # 打者 ΣΔRE24；投手 −ΣΔRE24
    count: int = 0          # 打者 PA／投手 BF


@dataclass
class SeriesAggregate:
    kind_code: str
    status: str             # ok | partial | pending_pa | no_completed_games | unavailable
    games_total: int
    games_covered: int
    missing_games: list[int]            # 未涵蓋（未送達＋整場排除），系列場序
    excluded_games: list[dict]          # 整場排除者 [{series_game_no, reason}]
    batters: list[Line]
    pitchers: list[Line]
    pitcher_unattributed: int
    mvp_counts: list[dict]              # [{player_id, count, first_game}]
    mvp_missing_games: list[int]
    build_ids_hash: str | None
    livelog_names: dict[str, str] = field(default_factory=dict)   # players 缺名時的後備
    teams: dict[str, str | None] = field(default_factory=dict)    # 已涵蓋場出現過的打者／投手 → 隊（MVP 清單用）
    turning: dict | None = None         # 三大轉折（turning_points 純函式輸出）；無已涵蓋場 ⇒ None


# (kind_code, season) → (scorer | None, 不可用原因 | None)；由呼叫端注入，測試可替身。
ScorerFor = Callable[[str, int], tuple[Any, str | None]]


def scorer_for(kind_code: str, season: int) -> tuple[Any, str | None]:
    """既有 WP 解算器（``models.winprob_scorer``）的取得與降級原因，語意同 ``pa_facts._load_wp_swings``。

    ⚠️ ``get_scorer`` 首次會以 ``cpbl.db.conn()`` 讀 ``run_dist`` artifact（process 級快取）——那支查詢
    **不在** overview 的單一交易內；artifact 是離線建置的靜態表，與單場 recap 同一取得方式。
    """
    from cpbl.models.winprob_scorer import DIST_SOURCE, get_scorer

    if kind_code not in DIST_SOURCE:
        return None, "wp_scope_unsupported"
    try:
        scorer, _model = get_scorer(kind_code, season)
    except Exception:  # noqa: BLE001 — artifact／解算器異常一律降級，不中斷累計榜
        return None, "winprob_model_error"
    return (scorer, None) if scorer is not None else (None, "winprob_model_not_built")


def _final_outcome(game: dict) -> float | None:
    home, away = game.get("home_score"), game.get("away_score")
    if home is None or away is None:
        return None
    return 1.0 if home > away else (0.0 if home < away else 0.5)


def turning_points(covered: list[tuple[dict, list[dict]]], *, scorer: Any, scorer_reason: str | None,
                   full_scope: bool, limit: int = TURNING_LIMIT) -> dict:
    """全系列三大轉折（純函式）。``covered``＝[(S02 場次, 該場 delta_re24 事實流)]，只含已涵蓋場。

    回傳 ``{signal, min_abs, degraded, reason, degraded_games, scope, items}``；``items`` 已依時間排序，
    每筆是事實流打席的淺拷貝＋``series_game_no``／隊別＋``delta_wp``（降級時 None）。
    """
    swings: dict[int, dict[int, dict]] = {}
    degraded_games: list[int] = []
    reason = scorer_reason
    for g, facts in covered:
        if scorer is None:
            degraded_games.append(g["series_game_no"])
            continue
        final = _final_outcome(g)
        wp = pa_facts.wp_swings(facts, scorer=scorer, final_outcome=final) if final is not None else {}
        if not wp:
            degraded_games.append(g["series_game_no"])
            reason = reason or ("final_unknown" if final is None else "winprob_no_scored_plays")
            continue
        swings[g["series_game_no"]] = wp
    use_wp = scorer is not None and not degraded_games

    candidates: list[tuple[float, dict, dict]] = []
    for g, facts in covered:
        wp = swings.get(g["series_game_no"], {})
        for f in facts:
            if f.get("delta_re24") is None:
                continue
            if use_wp:
                w = wp.get(f["pa_index"])
                if w is None or abs(w["delta"]) < pa_facts.KEY_PLAY_MIN_WP_ABS:
                    continue
                candidates.append((abs(w["delta"]), g, {**f, "delta_wp": w["delta"]}))
            elif abs(f["delta_re24"]) >= pa_facts.KEY_PLAY_MIN_ABS:
                candidates.append((abs(f["delta_re24"]), g, {**f, "delta_wp": None}))

    def order(c):
        return (c[1]["series_game_no"], c[2]["pa_index"], c[2].get("pa_id") or "")

    top = sorted(candidates, key=lambda c: (-c[0], *order(c)))[:limit]
    items = []
    for _metric, g, f in sorted(top, key=order):
        items.append({
            "series_game_no": g["series_game_no"],
            "game_key": g["game_key"],
            "away_team_code": g["away_team_code"], "home_team_code": g["home_team_code"],
            **{k: f.get(k) for k in ("pa_id", "pa_index", "inning", "half", "outs_before", "bases_before",
                                     "away_score_before", "home_score_before", "away_score_after",
                                     "home_score_after", "hitter", "pitcher", "result_action", "delta_re24",
                                     "delta_wp")},
        })
    return {
        "signal": "delta_wp" if use_wp else "delta_re24",
        "min_abs": pa_facts.KEY_PLAY_MIN_WP_ABS if use_wp else pa_facts.KEY_PLAY_MIN_ABS,
        "degraded": not use_wp,
        "reason": None if use_wp else (reason or "winprob_unavailable"),
        "degraded_games": [] if use_wp else degraded_games,
        "scope": "full" if full_scope else "covered_only",
        "items": items,
    }


def charged_pitcher(pa: dict, members: list[str], by_event: dict[str, dict]) -> str | None:
    """該打席的責任投手。只有「打席中換投＋四壞」才走 9.16(h)(1)；判不出回 None。"""
    start, end = pa.get("start_pitcher_acnt"), pa.get("end_pitcher_acnt")
    if not (start and end and start != end and pa.get("outcome_family") == "walk"):
        return end
    seq = []
    for event_no in members:
        e = by_event.get(event_no)
        if e is None:
            return None
        seq.append((e.get("pitcher_acnt"), e.get("ball_cnt"), e.get("strike_cnt"), e.get("is_change_player")))
    return charged_walk_pitcher(start, end, seq)


def _rank(lines: dict[str, Line], limit: int) -> list[Line]:
    return sorted(lines.values(), key=lambda x: (-x.value, x.player_id))[:limit]


def _mvp(games: list[dict]) -> tuple[list[dict], list[int]]:
    counts: Counter[str] = Counter()
    first: dict[str, int] = {}
    missing: list[int] = []
    for g in games:
        mid = g.get("official_mvp_id")
        if not mid:
            missing.append(g["series_game_no"])
            continue
        counts[mid] += 1
        first.setdefault(mid, g["series_game_no"])
    out = [{"player_id": pid, "count": n, "first_game": first[pid]} for pid, n in counts.items()]
    out.sort(key=lambda m: (-m["count"], m["first_game"], m["player_id"]))
    return out, missing


def aggregate(context: dict, kind: str, rows: SeriesRows | None, *,
              scorer_for: ScorerFor | None = None) -> SeriesAggregate:
    """單一系列累計（``scorer_for`` 以外為純函式）。``rows=None`` ⇒ 讀取失敗 ⇒ ``unavailable``（比分與 MVP 照常）。

    ``scorer_for=None`` ⇒ 不取 WP，三大轉折直接走 |ΔRE24|（reason ``winprob_not_requested``）。"""
    games = series_games(context, kind)
    mvp_counts, mvp_missing = _mvp(games)

    def result(status: str, **kw) -> SeriesAggregate:
        base = dict(games_covered=0, missing_games=[], excluded_games=[], batters=[], pitchers=[],
                    pitcher_unattributed=0, build_ids_hash=None)
        return SeriesAggregate(kind_code=kind, status=status, games_total=len(games), mvp_counts=mvp_counts,
                               mvp_missing_games=mvp_missing, **{**base, **kw})

    if not games:
        return result("no_completed_games")
    if rows is None or len(rows.re_map) < RE_CELLS:
        return result("unavailable", missing_games=[g["series_game_no"] for g in games])

    batters: dict[str, Line] = {}
    pitchers: dict[str, Line] = {}
    unattributed = 0
    missing: list[int] = []
    excluded: list[dict] = []
    builds: list[str] = []
    names: dict[str, str] = {}
    covered_facts: list[tuple[dict, list[dict]]] = []
    for g in games:
        sno = int(g["game_key"]["game_sno"])
        pas = rows.pas.get((kind, sno))
        if not pas:
            missing.append(g["series_game_no"])
            continue
        events = [dict(e) for e in rows.livelog.get((kind, sno), [])]   # annotate_scores 會就地標比分
        facts = pa_facts.delta_re24(pas, events, rows.re_map, game_completed=True)
        gaps = sorted({f["unavailable_reason"] for f in facts} & GAP_REASONS)
        if gaps:
            missing.append(g["series_game_no"])
            excluded.append({"series_game_no": g["series_game_no"], "reason": gaps[0]})
            continue
        builds.append(rows.build_ids.get((kind, sno)) or "")
        covered_facts.append((g, facts))
        names.update(pa_facts.player_names(events))
        by_event = {str(e["main_event_no"]): e for e in events}
        by_index = {int(p["pa_index"]): p for p in pas}
        for f in facts:
            if f["delta_re24"] is None:
                continue
            pa = by_index[int(f["pa_index"])]
            top = str((pa.get("pre_state") or {}).get("half")) == "1"   # 上半局＝客隊進攻
            bat_team, pit_team = ((g["away_team_code"], g["home_team_code"]) if top
                                  else (g["home_team_code"], g["away_team_code"]))
            hitter = pa.get("hitter_acnt")
            if hitter:
                line = batters.setdefault(hitter, Line(hitter))
                line.team_code, line.value, line.count = bat_team, line.value + f["delta_re24"], line.count + 1
            pitcher = charged_pitcher(pa, rows.members.get((kind, sno, int(pa["pa_index"])), []), by_event)
            if pitcher is None:
                unattributed += 1
                continue
            line = pitchers.setdefault(pitcher, Line(pitcher))
            line.team_code, line.value, line.count = pit_team, line.value - f["delta_re24"], line.count + 1

    for line in (*batters.values(), *pitchers.values()):
        line.value = round(line.value, 6)
    covered = len(games) - len(missing)
    turning = None
    if covered_facts:
        scorer, reason = (scorer_for(kind, int(context["year"])) if scorer_for
                          else (None, "winprob_not_requested"))
        turning = turning_points(covered_facts, scorer=scorer, scorer_reason=reason,
                                 full_scope=covered == len(games))
    return result(
        "ok" if covered == len(games) else ("partial" if covered else "pending_pa"),
        games_covered=covered, missing_games=missing, excluded_games=excluded,
        batters=_rank(batters, BATTER_LIMIT), pitchers=_rank(pitchers, PITCHER_LIMIT),
        pitcher_unattributed=unattributed,
        build_ids_hash=contract._hash(sorted(builds)) if builds else None,
        livelog_names=names,
        teams={line.player_id: line.team_code for line in (*batters.values(), *pitchers.values())},
        turning=turning,
    )


def aggregate_all(context: dict, rows: SeriesRows | None, *,
                  scorer_for: ScorerFor | None = None) -> dict[str, SeriesAggregate]:
    return {kind: aggregate(context, kind, rows, scorer_for=scorer_for) for kind in SERIES_ORDER}


def player_ids(aggs: dict[str, SeriesAggregate]) -> list[str]:
    """需要姓名的球員（榜上＋MVP 次數清單）；併入 overview 既有的單次 players 批次查詢。"""
    ids: dict[str, None] = {}
    for a in aggs.values():
        for line in (*a.batters, *a.pitchers):
            ids[line.player_id] = None
        for m in a.mvp_counts:
            ids[m["player_id"]] = None
        for t in (a.turning or {}).get("items", []):
            for who in (t.get("hitter"), t.get("pitcher")):
                if who and who.get("player_id"):
                    ids[who["player_id"]] = None
    return list(ids)


def _block(agg: SeriesAggregate, names: dict[str, str] | None) -> dict:
    def name(pid: str) -> str | None:
        return (names or {}).get(pid) or agg.livelog_names.get(pid)

    mvp = {m["player_id"]: m["count"] for m in agg.mvp_counts}

    def person(who: dict | None) -> dict | None:
        if not who or not who.get("player_id"):
            return None
        return {"player_id": who["player_id"], "name": (names or {}).get(who["player_id"]) or who.get("name")}

    turning = None
    if agg.turning is not None:
        turning = {**agg.turning, "items": [{**t, "hitter": person(t["hitter"]), "pitcher": person(t["pitcher"])}
                                             for t in agg.turning["items"]]}
    return {
        "kind_code": agg.kind_code,
        "status": agg.status,
        "games_total": agg.games_total,
        "games_covered": agg.games_covered,
        "missing_games": agg.missing_games,
        "excluded_games": agg.excluded_games,
        "batters": [{"player_id": b.player_id, "name": name(b.player_id), "team_code": b.team_code,
                     "pa": b.count, "re24_raw": b.value, "mvp_count": mvp.get(b.player_id, 0)}
                    for b in agg.batters],
        "pitchers": [{"player_id": p.player_id, "name": name(p.player_id), "team_code": p.team_code,
                      "bf": p.count, "value_raw": p.value, "mvp_count": mvp.get(p.player_id, 0)}
                     for p in agg.pitchers],
        "pitcher_unattributed": agg.pitcher_unattributed,
        "mvp_counts": [{"player_id": m["player_id"], "name": name(m["player_id"]),
                        "team_code": agg.teams.get(m["player_id"]), "count": m["count"]} for m in agg.mvp_counts],
        "mvp_missing_games": agg.mvp_missing_games,
        "awards": {"status": "pending_source"},
        "turning_points": turning,
        "source": {"pa_build_ids_hash": agg.build_ids_hash, "re_span": pa_facts.RE_SPAN},
    }


def summary_json(aggs: dict[str, SeriesAggregate], names: dict[str, str] | None, *,
                 current: str, previous: str | None) -> dict:
    """``playoffs-series-summary/v1``；current／previous 與 overview ``series_section`` 同系列。"""
    return {
        "contract": CONTRACT,
        "algorithm": ALGORITHM,
        "current": _block(aggs[current], names),
        "previous": _block(aggs[previous], names) if previous else None,
    }


def manifest_entry(aggs: dict[str, SeriesAggregate], *, observed_at: str | None) -> dict:
    """``source_manifest`` 一筆（overview 在 S02 之後附加，不進 ``context_version``）。"""
    shown = [a for a in aggs.values() if a.games_total]
    return {
        "source": "pa_published",
        "scope": "series:" + ";".join(f"{a.kind_code}:{a.games_covered}/{a.games_total}" for a in shown),
        "version_or_hash": contract._hash(sorted((a.kind_code, a.build_ids_hash or "") for a in shown)),
        "observed_at": observed_at,
        "status": "unavailable" if any(a.status == "unavailable" for a in shown) else "ok",
    }
