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
)

BASIS_STRICT = "官方 earned_runs=0 的整場出賽"
BASIS_EXTENDED = f"{BASIS_STRICT} ＋ 中斷場的「整個半局零得分」尾段半局"
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

# 中斷場的逐打席事件；換人列一併取回（純函式內再濾，語意見 half_innings_of）。
_LIVELOG_SQL = """
    SELECT l.year, l.kind_code, l.game_sno, l.main_event_no, l.inning_seq,
           l.visiting_home_type, l.out_cnt, l.is_score, l.is_change_player,
           l.pitcher_acnt, l.pitch_cnt, l.visiting_score, l.home_score
      FROM cpbl.game_livelog l
      JOIN (SELECT (v->>0)::int AS year, v->>1 AS kind_code, (v->>2)::int AS game_sno
              FROM jsonb_array_elements(%(keys)s::jsonb) v) k
        ON k.year = l.year AND k.kind_code = l.kind_code AND k.game_sno = l.game_sno
     ORDER BY l.year, l.kind_code, l.game_sno, l.main_event_no
"""

# 逐局記分板：覆蓋完整性與零得分的獨立交叉驗證來源（與 livelog 不同 payload）。
_SCOREBOARD_SQL = """
    SELECT s.year, s.kind_code, s.game_sno, s.inning_seq,
           s.visiting_home_type AS vht, max(s.score_cnt) AS runs
      FROM cpbl.game_scoreboard s
      JOIN (SELECT (v->>0)::int AS year, v->>1 AS kind_code, (v->>2)::int AS game_sno
              FROM jsonb_array_elements(%(keys)s::jsonb) v) k
        ON k.year = s.year AND k.kind_code = s.kind_code AND k.game_sno = s.game_sno
     WHERE s.visiting_home_type IS NOT NULL
     GROUP BY 1, 2, 3, 4, 5
"""

# 全場投球 box：覆蓋完整性用的**外部**證據（誰投過、各記幾個出局）。
_GAME_BOX_SQL = """
    SELECT p.year, p.kind_code, p.game_sno, p.pitcher_acnt,
           p.inning_pitched_cnt * 3 + p.inning_pitched_div3 AS outs,
           p.pitch_cnt AS pitches
      FROM cpbl.pitching_gamelog p
      JOIN (SELECT (v->>0)::int AS year, v->>1 AS kind_code, (v->>2)::int AS game_sno
              FROM jsonb_array_elements(%(keys)s::jsonb) v) k
        ON k.year = p.year AND k.kind_code = p.kind_code AND k.game_sno = p.game_sno
"""


def _appearance(row: dict) -> Appearance:
    return Appearance(
        year=row["year"], kind_code=row["kind_code"], game_sno=row["game_sno"],
        game_date=row["game_date"], earned_runs=row["earned_runs"], outs=row["outs"],
        delay_kind=row["delay_kind"], opponent=row["opponent"], team_code=row["team_code"],
    )


def _game_ref(a: Appearance) -> dict:
    return {
        "year": a.year, "kind_code": a.kind_code, "game_sno": a.game_sno,
        "game_date": str(a.game_date) if a.game_date else None,
        "opponent": a.opponent,
    }


TAIL_DISABLED_REASON = (
    "尾段（中斷場的部分局數）自 2026-07-28 起停用：所有由 livelog 推導出局數歸屬的方法"
    "都需要「該半局沒有隱藏列」這個前提，而該前提已證偽——`main_event_no` 主序號不是列的"
    "唯一鍵（全庫 2,457 個序號槽含多列，其中 204 個同時含換人列與比賽列），刪掉一列可以"
    "不留任何洞。故本指標目前只採計官方 earned_runs=0 的**整場出賽**（strict），"
    "零 livelog 推論。"
)


def tail_lookup_factory(
    player_id: str,
    livelog: dict[tuple[int, str, int], list[dict]],
    scoreboard: dict[tuple[int, str, int], dict[tuple[int, str], int]],
    box: dict[tuple[int, str, int], dict[str, dict[str, int]]],
):
    """尾段解析器——**目前一律回 None（fail-closed）**，理由見 `TAIL_DISABLED_REASON`。

    `cpbl.models.scoreless_streak.forced_outs()` 與 `tail_credit()` 及其測試保留在原處，
    待需求方裁定產品口徑後可直接接回；但**接回前必須先解決「無法證明半局內無隱藏列」
    這個根本問題**，不要只是把這個函式改回去。
    """

    def lookup(_a: Appearance) -> TailCredit | None:
        return None

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


def load_livelog(
    keys: Sequence[tuple[int, str, int]],
) -> dict[tuple[int, str, int], list[dict]]:
    if not keys:
        return {}
    payload = json.dumps([[k[0], k[1], k[2]] for k in sorted(set(keys))])
    with conn() as c:
        cur = c.cursor()
        cur.execute(_LIVELOG_SQL, {"keys": payload})
        rows = _dicts(cur)
    out: dict[tuple[int, str, int], list[dict]] = {}
    for r in rows:
        out.setdefault((r["year"], r["kind_code"], r["game_sno"]), []).append(r)
    return out


def load_scoreboard(
    keys: Sequence[tuple[int, str, int]],
) -> dict[tuple[int, str, int], dict[tuple[int, str], int]]:
    """逐局記分板 → {game: {(inning_seq, vht): 得分}}。

    來源與 livelog 不同（官網 box 的另一段 payload），故可作覆蓋完整性與零得分的
    **獨立**交叉驗證來源。
    """
    if not keys:
        return {}
    payload = json.dumps([[k[0], k[1], k[2]] for k in sorted(set(keys))])
    with conn() as c:
        cur = c.cursor()
        cur.execute(_SCOREBOARD_SQL, {"keys": payload})
        rows = _dicts(cur)
    out: dict[tuple[int, str, int], dict[tuple[int, str], int]] = {}
    for r in rows:
        game = (r["year"], r["kind_code"], r["game_sno"])
        out.setdefault(game, {})[(r["inning_seq"], r["vht"])] = int(r["runs"] or 0)
    return out


def load_game_box(
    keys: Sequence[tuple[int, str, int]],
) -> dict[tuple[int, str, int], dict[str, dict[str, int]]]:
    """該場**全部投手**的官方出局數與投球數 → {game: {pitcher: {"outs":…, "pitches":…}}}。

    覆蓋完整性最關鍵的一份證據：官方 box 知道有哪些投手、各記了幾個出局。livelog 若
    漏掉某位後援投手的事件，他的出局數就沒有可見的位置可以安放，對帳立刻不平——這是
    唯一能抓到「**半局內**事件缺漏」的訊號（其餘檢查都只到半局層級）。
    """
    if not keys:
        return {}
    payload = json.dumps([[k[0], k[1], k[2]] for k in sorted(set(keys))])
    with conn() as c:
        cur = c.cursor()
        cur.execute(_GAME_BOX_SQL, {"keys": payload})
        rows = _dicts(cur)
    out: dict[tuple[int, str, int], dict[str, dict[str, int]]] = {}
    for r in rows:
        game = (r["year"], r["kind_code"], r["game_sno"])
        out.setdefault(game, {})[r["pitcher_acnt"]] = {
            "outs": int(r["outs"] or 0),
            "pitches": r["pitches"],
        }
    return out


def compute_all(
    by_player: dict[str, list[Appearance]],
    counted_kinds: Sequence[str] | None = None,
) -> dict[str, StreakResult]:
    """兩趟：先不採計尾段找出中斷場，批次抓那些場的 livelog，再重算含尾段的值。

    livelog 只在「官方 ER>0 的那一場」用到——這是本卡「定位而非重建」的全部 livelog 用途。
    季後賽造成的中斷（`BREAK_POSTSEASON_EARNED_RUN`）不取尾段：那場的局數本來就不計入。
    """
    first = {pid: compute_streak(apps, counted_kinds=counted_kinds)
             for pid, apps in by_player.items()}
    keys = [r.break_key for r in first.values()
            if r.break_reason == BREAK_EARNED_RUN and r.break_key]
    livelog = load_livelog(keys)
    scoreboard = load_scoreboard(keys)
    box = load_game_box(keys)
    return {
        pid: compute_streak(apps, tail_lookup_factory(pid, livelog, scoreboard, box),
                            counted_kinds)
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
        "basis": BASIS_STRICT,
        "strict_basis": BASIS_STRICT,
        "appearances_counted": len(counted),
        "tail_half_innings": len(res.tail.credited) if res.tail else 0,
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
        "tail_disabled_note": TAIL_DISABLED_REASON,
        "team": team,
        "data_from_year": DATA_FROM_YEAR,
        "as_of": str(as_of) if as_of else None,
        "items": items,
    }
