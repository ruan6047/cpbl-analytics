"""「連續無**自責**分局數」的取數層：把 DB 行餵給純函式 `cpbl.models.scoreless_streak`。

分工：本檔只負責 SQL 與 payload 組裝；**演算法、保守性判斷、名詞紅線全在
`cpbl.models.scoreless_streak`**（該檔 docstring 是語意單一來源，勿在此另立口徑）。

自責分一律讀官方 `cpbl.pitching_gamelog.earned_runs`，本層不做任何自責分判定。
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from cpbl.api.helpers import _dicts, kinds_of
from cpbl.db import conn
from cpbl.models.scoreless_streak import (
    BOUNDARY_NOTE,
    BREAK_EARNED_RUN,
    DATA_FROM_YEAR,
    METRIC,
    METRIC_LABEL,
    METRIC_NOTE,
    Appearance,
    StreakResult,
    TailCredit,
    compute_streak,
    outs_to_innings,
    tail_credit,
)

BASIS_STRICT = "官方 earned_runs=0 的整場出賽"
BASIS_EXTENDED = (
    f"{BASIS_STRICT} ＋ 中斷場的零得分後綴（鴿籠下界：官方逐局比分 ＋ 官方局數，"
    "不讀逐打席資料、不假設任何事件完整性）"
)
TAIL_BASIS_NOTE = (
    "尾段以官方逐局比分界定「零得分後綴」，再用鴿籠原理取下界："
    "他在後綴的出局數 ≥ 官方總出局數 − 3 × 前綴局數。零得分的局不管誰投都是零失分，"
    "故此下界與投手更替、再入賽、牽制出局皆無關，也不需要逐打席資料完整。"
)
SCOPE_NOTE = (
    "只計例行賽局數（與媒體／MLB／NPB 慣例一致，季後賽另計）。"
    "跨季時中間的季後賽出賽：官方自責分為 0 則跳過（不計局數也不中斷），"
    "掉自責分則中斷——被跳過的場次列在 skipped_postseason_games，不做沉默跳過。"
)

# 出賽（官方 box）＋ 場次脈絡。ER 與局數原樣取官方欄位，不加工。
_APPEARANCES_SQL = """
    SELECT p.pitcher_acnt                                   AS player_id,
           p.pitcher_name                                   AS player_name,
           p.year, p.kind_code, p.game_sno,
           g.game_date,
           p.earned_runs,
           p.inning_pitched_cnt * 3 + p.inning_pitched_div3 AS outs,
           g.delay_kind,
           p.visiting_home_type                             AS vht,
           CASE WHEN p.visiting_home_type = '2' THEN g.home_team_code
                ELSE g.away_team_code END                   AS team_code,
           CASE WHEN p.visiting_home_type = '2' THEN g.away_team_name
                ELSE g.home_team_name END                   AS opponent
      FROM cpbl.pitching_gamelog p
      JOIN cpbl.games g USING (year, kind_code, game_sno)
     WHERE p.kind_code = ANY(%(kinds)s)
       AND p.year >= %(from_year)s      -- 紅線 4：2018 前無逐場資料，不可混入
       AND (%(player_id)s::text IS NULL OR p.pitcher_acnt = %(player_id)s)
     ORDER BY p.pitcher_acnt, g.game_date, p.kind_code, p.game_sno
"""

# 中斷場的**對手逐局得分**——鴿籠下界唯一需要的 livelog 以外事實。
# `visiting_home_type` 取投手的相反側：投手在主隊(2) → 對手在客隊打擊側(1)，反之亦然。
_OPP_RUNS_SQL = """
    SELECT s.year, s.kind_code, s.game_sno, s.visiting_home_type AS vht,
           s.inning_seq, max(s.score_cnt) AS runs
      FROM cpbl.game_scoreboard s
      JOIN (SELECT (v->>0)::int AS year, v->>1 AS kind_code, (v->>2)::int AS game_sno
              FROM jsonb_array_elements(%(keys)s::jsonb) v) k
        ON k.year = s.year AND k.kind_code = s.kind_code AND k.game_sno = s.game_sno
     WHERE s.visiting_home_type IS NOT NULL
     GROUP BY 1, 2, 3, 4, 5
"""


def _appearance(row: dict) -> Appearance:
    return Appearance(
        year=row["year"], kind_code=row["kind_code"], game_sno=row["game_sno"],
        game_date=row["game_date"], earned_runs=row["earned_runs"], outs=row["outs"],
        delay_kind=row["delay_kind"], opponent=row["opponent"], team_code=row["team_code"],
        vht=row["vht"],
    )


def _game_ref(a: Appearance) -> dict:
    return {
        "year": a.year, "kind_code": a.kind_code, "game_sno": a.game_sno,
        "game_date": str(a.game_date) if a.game_date else None,
        "opponent": a.opponent,
    }


def load_opponent_runs(
    keys: Sequence[tuple[int, str, int]],
) -> dict[tuple[int, str, int], dict[str, dict[int, int]]]:
    """{game: {打擊側 vht: {局: 得分}}}——鴿籠下界的官方事實來源。"""
    if not keys:
        return {}
    payload = json.dumps([[k[0], k[1], k[2]] for k in sorted(set(keys))])
    with conn() as c:
        cur = c.cursor()
        cur.execute(_OPP_RUNS_SQL, {"keys": payload})
        rows = _dicts(cur)
    out: dict[tuple[int, str, int], dict[str, dict[int, int]]] = {}
    for r in rows:
        game = (r["year"], r["kind_code"], r["game_sno"])
        out.setdefault(game, {}).setdefault(r["vht"], {})[r["inning_seq"]] = int(r["runs"] or 0)
    return out


def tail_lookup_factory(
    opponent_runs: dict[tuple[int, str, int], dict[str, dict[int, int]]],
):
    """尾段解析器：鴿籠下界（見 `pigeonhole_tail_outs`）。**不讀 livelog**。

    對手打擊側取投手主客別的相反：投手在主隊(2) → 對手在客隊打擊側(1)。
    """

    def lookup(a: Appearance) -> TailCredit | None:
        board = opponent_runs.get(a.key)
        if not board or a.vht not in ("1", "2"):
            return TailCredit(key=a.key, outs=0, reason="no_scoreboard")
        opp = board.get("1" if a.vht == "2" else "2") or {}
        return tail_credit(a.key, opp, a.outs)

    return lookup


def load_appearances(
    kinds: Sequence[str], player_id: str | None = None,
) -> tuple[dict[str, list[Appearance]], dict[str, str]]:
    """→ (player_id → 出賽清單【舊→新】, player_id → 姓名)。

    含全部年份（2018+），**不以球季裁切連續紀錄**；球季只用來篩母體（見 streak_payload）。
    """
    with conn() as c:
        cur = c.cursor()
        cur.execute(_APPEARANCES_SQL, {"kinds": list(kinds), "player_id": player_id,
                                       "from_year": DATA_FROM_YEAR})
        rows = _dicts(cur)
    by_player: dict[str, list[Appearance]] = {}
    names: dict[str, str] = {}
    for r in rows:
        by_player.setdefault(r["player_id"], []).append(_appearance(r))
        if r["player_name"]:
            names[r["player_id"]] = r["player_name"]
    return by_player, names


def compute_all(
    by_player: dict[str, list[Appearance]],
    counted_kinds: Sequence[str] | None = None,
) -> dict[str, StreakResult]:
    """兩趟：先不採計尾段找出中斷場，批次抓那些場的**對手逐局得分**，再重算含尾段的值。

    尾段只需要官方逐局比分與官方局數，**完全不讀 livelog**（見 `pigeonhole_tail_outs`）。
    """
    first = {pid: compute_streak(apps, counted_kinds=counted_kinds)
             for pid, apps in by_player.items()}
    keys = [r.break_key for r in first.values()
            if r.break_reason == BREAK_EARNED_RUN and r.break_key]
    runs = load_opponent_runs(keys)
    lookup = tail_lookup_factory(runs)
    return {
        pid: compute_streak(apps, lookup, counted_kinds)
        for pid, apps in by_player.items()
    }

def build_item(player_id: str, name: str | None, apps: Sequence[Appearance],
               res: StreakResult) -> dict:
    counted = res.counted  # 新→舊
    start: Appearance | None = counted[-1] if counted else None
    through: Appearance | None = counted[0] if counted else None
    tail_key = res.tail.key if res.tail and res.tail.outs > 0 else None
    if tail_key:
        start = next(a for a in apps if a.key == tail_key)
        through = through or start
    break_app = next((a for a in apps if a.key == res.break_key), None) if res.break_key else None
    return {
        "player_id": player_id,
        "player_name": name,
        "team_code": apps[-1].team_code if apps else None,
        "outs": res.outs,
        "innings": outs_to_innings(res.outs),
        "strict_outs": res.strict_outs,
        "strict_innings": outs_to_innings(res.strict_outs),
        "basis": BASIS_EXTENDED,
        "strict_basis": BASIS_STRICT,
        "appearances_counted": len(counted),
        "tail_suffix_from_inning": res.tail.suffix_from_inning if res.tail else None,
        "tail_reason": res.tail.reason if res.tail else None,
        "tail_outs": res.tail.outs if res.tail else 0,
        "start": _game_ref(start) if start else None,
        "through": _game_ref(through) if through else None,
        "last_appearance": _game_ref(apps[-1]) if apps else None,
        "boundary_limited": res.boundary_limited,
        "boundary_note": BOUNDARY_NOTE if res.boundary_limited else None,
        "break_reason": res.break_reason,
        "break_game": _game_ref(break_app) if break_app else None,
        # 紀錄期間內被跳過的季後賽出賽（官方 ER=0，故不計局數也不中斷）。
        # 明列而非沉默跳過——讀者要能看見紀錄中間發生過什麼。
        "skipped_postseason_appearances": len(res.skipped),
        "skipped_postseason_games": [_game_ref(a) for a in reversed(res.skipped)],
    }


def streak_payload(
    season: int,
    kind_code: str = "A",
    player_id: str | None = None,
    team: str | None = None,
    limit: int = 10,
) -> dict:
    """連續無自責分局數（下界）。`player_id` 指定時回單人，否則回該季母體排行。

    `season`／`team` 只篩**母體**（誰進榜、算哪一隊），不裁切連續紀錄本身——紀錄可回溯到
    更早球季，資料邊界見 `DATA_FROM_YEAR`。

    `kind_code` 是**計入局數**的例行賽賽別；同層的季後賽仍需載入（乾淨跳過、掉分中斷，
    見 `scoreless_streak` 模組 docstring），故查詢範圍為 `kinds_of(kind_code)`。
    """
    kinds = kinds_of(kind_code)
    counted_kinds = (kind_code,)
    by_player, names = load_appearances(kinds, player_id)

    if player_id is None:
        by_player = {pid: apps for pid, apps in by_player.items()
                     if any(a.year == season for a in apps)}
        if team:
            by_player = {
                pid: apps for pid, apps in by_player.items()
                if next((a.team_code for a in reversed(apps) if a.year == season), None) == team
            }

    results = compute_all(by_player, counted_kinds)
    items = [build_item(pid, names.get(pid), by_player[pid], res)
             for pid, res in results.items()]
    if player_id is None:
        items = [i for i in items if i["outs"] > 0]
    items.sort(key=lambda i: (-i["outs"], -i["strict_outs"], i["player_id"]))
    if player_id is None:
        items = items[:limit]

    as_of = max((a.game_date for apps in by_player.values() for a in apps if a.game_date),
                default=None)
    return {
        "metric": METRIC,
        "metric_label": METRIC_LABEL,
        "note": METRIC_NOTE,
        "season": season,
        "kind_code": kind_code,
        "kinds_counted": list(counted_kinds),   # 計入局數的賽別（例行賽）
        "kinds_in_scope": kinds,                # 一併載入、可中斷紀錄的賽別（含季後賽）
        "scope_note": SCOPE_NOTE,
        "tail_basis_note": TAIL_BASIS_NOTE,
        "team": team,
        "data_from_year": DATA_FROM_YEAR,
        "as_of": str(as_of) if as_of else None,
        "items": items,
    }
