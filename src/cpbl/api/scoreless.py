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
    last_pitch_inning,
    outs_to_innings,
    tail_credit,
)

BASIS_STRICT = "官方 earned_runs=0 的整場出賽"
BASIS_EXTENDED = (
    f"{BASIS_STRICT} ＋ 中斷場的零得分視窗（鴿籠下界：官方逐局比分 ＋ 官方局數 ＋ "
    "官方投球數耗盡的局，不假設任何事件完整性）"
)
TAIL_BASIS_NOTE = (
    "尾段以官方逐局比分界定「零得分視窗」，再用鴿籠原理取下界："
    "他在視窗內的出局數 ≥ 官方總出局數 − 3 × 視窗外的局數。零得分的局不管誰投都是零失分，"
    "故此下界與投手更替、再入賽、牽制出局皆無關，也不需要逐打席資料完整。"
    "視窗的右端取「官方投球數耗盡的局」（該局起他不可能再投球，也就不可能再讓跑者上壘、"
    "不可能再被記自責分）與比賽末端兩種，取下界較大者。"
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
           p.pitch_cnt                                      AS official_pitches,
           g.delay_kind,
           p.visiting_home_type                             AS vht,
           CASE WHEN p.visiting_home_type = '2' THEN g.away_score
                ELSE g.home_score END                       AS opponent_score,
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


# 尾段第二條下界唯一需要的 livelog 事實：**每局的累計投球數最大值**（見 `last_pitch_inning`）。
# 刻意只取 max，不數列、不看序號連續性——`pitch_cnt` 不是列的唯一鍵（全庫 68,372 組重複），
# 任何「數列」或「序號閉合」的用法都已被 iteration 4／5 的反例推翻。
# `pitch_cnt IS NOT NULL` 讓聚合只吃**已知值**：未知的列直接不參與，觀測到的最大值因此
# 只會偏小；而偏小只會讓認證的局往後移或整個不認證，是保守方向。
_LAST_PITCH_SQL = """
    SELECT l.year, l.kind_code, l.game_sno, l.pitcher_acnt,
           l.visiting_home_type AS batting_side,
           l.inning_seq, max(l.pitch_cnt) AS max_pitch
      FROM cpbl.game_livelog l
      JOIN (SELECT (v->>0)::int AS year, v->>1 AS kind_code, (v->>2)::int AS game_sno
              FROM jsonb_array_elements(%(keys)s::jsonb) v) k
        ON k.year = l.year AND k.kind_code = l.kind_code AND k.game_sno = l.game_sno
     WHERE l.pitcher_acnt IS NOT NULL
       AND l.pitch_cnt IS NOT NULL
       AND l.visiting_home_type IS NOT NULL
       AND l.inning_seq IS NOT NULL
     GROUP BY 1, 2, 3, 4, 5, 6
"""


def _appearance(row: dict) -> Appearance:
    return Appearance(
        year=row["year"], kind_code=row["kind_code"], game_sno=row["game_sno"],
        game_date=row["game_date"], earned_runs=row["earned_runs"], outs=row["outs"],
        delay_kind=row["delay_kind"], opponent=row["opponent"], team_code=row["team_code"],
        vht=row["vht"], opponent_score=row["opponent_score"], player_id=row["player_id"],
        official_pitches=row["official_pitches"],
    )


def _game_ref(a: Appearance) -> dict:
    return {
        "year": a.year, "kind_code": a.kind_code, "game_sno": a.game_sno,
        "game_date": str(a.game_date) if a.game_date else None,
        "opponent": a.opponent,
    }


def load_opponent_runs(
    keys: Sequence[tuple[int, str, int]],
) -> dict[tuple[int, str, int], dict[str, dict[int, int | None]]]:
    """{game: {打擊側 vht: {局: 得分}}}——鴿籠下界的官方事實來源。

    **`score_cnt` 的 NULL 一律原樣保留，不得正規化成 0。** schema 允許 NULL
    （`migrations/016_game_log.sql`），ingest 遇來源缺值就寫 NULL；NULL 的意思是
    「這一局得幾分**不知道**」，不是「這一局 0 分」。若在這裡折成 0，當官方終場得分
    恰為 0 時總和對帳會以 `0 == 0` 通過，缺值的局被當成零得分而採計——**把未知當成
    已知**。下游 `pigeonhole_tail_outs` 會因為看見 None 而 fail-closed。
    """
    if not keys:
        return {}
    payload = json.dumps([[k[0], k[1], k[2]] for k in sorted(set(keys))])
    with conn() as c:
        cur = c.cursor()
        cur.execute(_OPP_RUNS_SQL, {"keys": payload})
        rows = _dicts(cur)
    return map_opponent_runs(rows)


def map_opponent_runs(
    rows: Sequence[dict],
) -> dict[tuple[int, str, int], dict[str, dict[int, int | None]]]:
    """DB 行 → `{game: {打擊側 vht: {局: 得分 | None}}}`。

    抽成獨立函式是為了讓**邊界轉換本身**可以被直接測行為（餵一列 `runs=None` 進來、
    斷言出來仍是 `None`），而不是去搜原始碼長什麼樣——後者改個寫法就能一邊通過測試
    一邊把 bug 種回去。
    """
    out: dict[tuple[int, str, int], dict[str, dict[int, int | None]]] = {}
    for r in rows:
        game = (r["year"], r["kind_code"], r["game_sno"])
        runs = r["runs"]
        out.setdefault(game, {}).setdefault(r["vht"], {})[r["inning_seq"]] = (
            None if runs is None else int(runs))
    return out


def load_pitch_observations(
    keys: Sequence[tuple[int, str, int]],
) -> dict[tuple[tuple[int, str, int], str, str], dict[int, int | None]]:
    """→ `{(場次, 投手, 打擊側): {局: 該局觀測到的累計投球數最大值}}`。"""
    if not keys:
        return {}
    payload = json.dumps([[k[0], k[1], k[2]] for k in sorted(set(keys))])
    with conn() as c:
        cur = c.cursor()
        cur.execute(_LAST_PITCH_SQL, {"keys": payload})
        rows = _dicts(cur)
    return map_pitch_observations(rows)


def map_pitch_observations(
    rows: Sequence[dict],
) -> dict[tuple[tuple[int, str, int], str, str], dict[int, int | None]]:
    """DB 行 → `{(場次, 投手, 打擊側): {局: 累計投球數最大值 | None}}`。

    **`max_pitch` 的 NULL 一律原樣保留，不得折成 0。** 抽成獨立函式的理由與
    `map_opponent_runs` 相同：邊界轉換本身要能被直接測行為。折成 0 會讓
    `last_pitch_inning` 把「這一局不知道投了幾球」當成「投到第 0 球」，在官方投球數
    也是 0 的邊角情形下以 `0 == 0` 通過認證。
    """
    out: dict[tuple[tuple[int, str, int], str, str], dict[int, int | None]] = {}
    for r in rows:
        game = (r["year"], r["kind_code"], r["game_sno"])
        key = (game, r["pitcher_acnt"], r["batting_side"])
        mx = r["max_pitch"]
        out.setdefault(key, {})[r["inning_seq"]] = (None if mx is None else int(mx))
    return out


def build_last_pitch_map(
    appearances: Sequence[Appearance],
    opponent_runs: dict[tuple[int, str, int], dict[str, dict[int, int | None]]],
    observations: dict[tuple[tuple[int, str, int], str, str], dict[int, int | None]],
) -> dict[tuple[tuple[int, str, int], str], int | None]:
    """→ `{(場次, 投手): 官方投球數耗盡的局}`。證明不到就不放進去（等同不認證）。

    對手打擊側取投手主客別的相反——**取錯邊會拿到他在自己隊進攻時的列**，那是資料錯誤，
    正確側觀測不足就達不到官方總數，自然 fail-closed。
    """
    out: dict[tuple[tuple[int, str, int], str], int | None] = {}
    for a in appearances:
        if a.player_id is None or a.vht not in ("1", "2"):
            continue
        opp_side = "1" if a.vht == "2" else "2"
        board = (opponent_runs.get(a.key) or {}).get(opp_side) or {}
        if not board:
            continue
        obs = observations.get((a.key, a.player_id, opp_side)) or {}
        got = last_pitch_inning(obs, a.official_pitches, max(board))
        if got is not None:
            out[(a.key, a.player_id)] = got
    return out


def tail_lookup_factory(
    opponent_runs: dict[tuple[int, str, int], dict[str, dict[int, int | None]]],
    last_pitch: dict[tuple[tuple[int, str, int], str], int | None] | None = None,
):
    """尾段解析器：鴿籠下界（見 `pigeonhole_tail_outs`）。

    對手打擊側取投手主客別的相反：投手在主隊(2) → 對手在客隊打擊側(1)。

    `last_pitch` 是 `{(場次, 投手): 官方投球數耗盡的局}`；給 None 或查不到即不認證，
    退回原本的全場鴿籠下界（fail-closed，見 `last_pitch_inning`）。
    """

    def lookup(a: Appearance) -> TailCredit | None:
        board = opponent_runs.get(a.key)
        if not board or a.vht not in ("1", "2"):
            return TailCredit(key=a.key, outs=0, reason="no_scoreboard")
        # `or {}` 在此無害：空 dict 會走 `pigeonhole_tail_outs` 的
        # 「無逐局比分 → (0, None, None)」fail-closed 路徑，不會被當成「全場零得分」。
        opp = board.get("1" if a.vht == "2" else "2") or {}
        # `.get(...)` 缺鍵回 None＝**不認證**，不是「第 0 局」也不是「整場」——
        # None 會讓 `pigeonhole_tail_outs` 只走原本的全場式，是嚴格更保守的那一邊。
        lp = (last_pitch or {}).get((a.key, a.player_id)) if a.player_id else None
        return tail_credit(a.key, opp, a.outs, a.opponent_score, lp)

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
    """兩趟：先不採計尾段找出中斷場，批次抓那些場的官方事實，再重算含尾段的值。

    尾段需要官方逐局比分與官方局數，另加**該投手每局的累計投球數最大值**一項 livelog
    正向觀測（見 `last_pitch_inning`）；抓不到就退回全場鴿籠下界。
    """
    first = {pid: compute_streak(apps, counted_kinds=counted_kinds)
             for pid, apps in by_player.items()}
    break_apps = [
        a
        for pid, r in first.items()
        if r.break_reason == BREAK_EARNED_RUN and r.break_key
        for a in by_player[pid] if a.key == r.break_key and a.player_id == pid
    ]
    keys = [a.key for a in break_apps]
    runs = load_opponent_runs(keys)
    last_pitch = build_last_pitch_map(break_apps, runs, load_pitch_observations(keys))
    lookup = tail_lookup_factory(runs, last_pitch)
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
        # 零得分視窗的結束局。**視窗不一定開到比賽末端**——採用退場局下界時它會停在
        # 「他投最後一球的那一局」，其後的局可能有得分（那些分不是他的責任，見
        # `pigeonhole_tail_outs`）。對帳 R2 驗的就是 [from, to] 這個閉區間。
        "tail_suffix_to_inning": res.tail.suffix_to_inning if res.tail else None,
        "tail_last_pitch_inning": res.tail.last_pitch_inning if res.tail else None,
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
