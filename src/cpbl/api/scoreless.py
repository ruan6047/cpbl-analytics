"""「連續無**自責**分局數」／「連續無**失**分局數」的取數層：把 DB 行餵給純函式
`cpbl.models.scoreless_streak`。

分工：本檔只負責 SQL 與 payload 組裝；**演算法、保守性判斷、名詞紅線全在
`cpbl.models.scoreless_streak`**（該檔 docstring 是語意單一來源，勿在此另立口徑）。

兩個口徑共用同一條取數與組裝路徑，差別只有 `Basis`（判準欄位＋對外名詞）。自責分讀
官方 `earned_runs`、失分讀官方 `runs`，本層對兩者都不做任何判定或補算。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date

from cpbl.api.helpers import _dicts, kinds_of
from cpbl.db import conn
from cpbl.models.scoreless_streak import (
    BOUNDARY_NOTE,
    DATA_FROM_YEAR,
    EARNED_RUN_BASIS,
    RUN_BASIS,
    SUSPENDED,
    Appearance,
    Basis,
    StreakResult,
    TailCredit,
    compute_streak,
    outs_to_innings,
    tail_credit,
)

__all__ = [
    "EARNED_RUN_BASIS",
    "RUN_BASIS",
    "classify_artifact_drift",
    "compute_all",
    "load_appearances",
    "load_opponent_runs",
    "map_opponent_runs",
    "population_fingerprint",
    "streak_payload",
    "tail_lookup_factory",
]


def _extended_basis(basis: Basis) -> str:
    return (f"{basis.strict_basis} ＋ 中斷場的零得分後綴（鴿籠下界：官方逐局比分 ＋ "
            "官方局數，不讀逐打席資料、不假設任何事件完整性）")
TAIL_BASIS_NOTE = (
    "尾段以官方逐局比分界定「零得分後綴」，再用鴿籠原理取下界："
    "他在後綴的出局數 ≥ 官方總出局數 − 3 × 前綴局數。零得分的局不管誰投都是零失分，"
    "故此下界與投手更替、再入賽、牽制出局皆無關，也不需要逐打席資料完整。"
)
# 兩個口徑共用的下界揭露：換口徑**不會**讓這個限制消失。
LOWER_BOUND_NOTE = (
    "中途登板／中途退場、且該場後段仍有得分時，官方逐場資料只記整場的量、不記事件時點，"
    "因此該場只能給鴿籠下界（多半為 0）——**此限制與判準用自責分或失分無關，換口徑不會"
    "消除它**。要消除只有取得官方的「逐局責任投手」對照。"
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
           p.runs,
           p.inning_pitched_cnt * 3 + p.inning_pitched_div3 AS outs,
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


def _appearance(row: dict) -> Appearance:
    return Appearance(
        year=row["year"], kind_code=row["kind_code"], game_sno=row["game_sno"],
        game_date=row["game_date"], earned_runs=row["earned_runs"], outs=row["outs"],
        delay_kind=row["delay_kind"], opponent=row["opponent"], team_code=row["team_code"],
        vht=row["vht"], opponent_score=row["opponent_score"],
        # NULL 原樣保留：失分口徑下 None 會走 BREAK_MISSING_LINE，不折成 0。
        runs=row["runs"],
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


def tail_lookup_factory(
    opponent_runs: dict[tuple[int, str, int], dict[str, dict[int, int | None]]],
):
    """尾段解析器：鴿籠下界（見 `pigeonhole_tail_outs`）。**不讀 livelog**。

    對手打擊側取投手主客別的相反：投手在主隊(2) → 對手在客隊打擊側(1)。
    """

    def lookup(a: Appearance) -> TailCredit | None:
        board = opponent_runs.get(a.key)
        if not board or a.vht not in ("1", "2"):
            return TailCredit(key=a.key, outs=0, reason="no_scoreboard")
        # `or {}` 在此無害：空 dict 會走 `pigeonhole_tail_outs` 的
        # 「無逐局比分 → (0, None)」fail-closed 路徑，不會被當成「全場零得分」。
        opp = board.get("1" if a.vht == "2" else "2") or {}
        return tail_credit(a.key, opp, a.outs, a.opponent_score)

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
    basis: Basis = EARNED_RUN_BASIS,
) -> dict[str, StreakResult]:
    """兩趟：先不採計尾段找出中斷場，批次抓那些場的**對手逐局得分**，再重算含尾段的值。

    尾段只需要官方逐局比分與官方局數，**完全不讀 livelog**（見 `pigeonhole_tail_outs`）。
    中斷場的判定走 `basis.break_reason`，兩個口徑不共用中斷原因碼。
    """
    first = {pid: compute_streak(apps, counted_kinds=counted_kinds, basis=basis)
             for pid, apps in by_player.items()}
    keys = [r.break_key for r in first.values()
            if r.break_reason == basis.break_reason and r.break_key]
    runs = load_opponent_runs(keys)
    lookup = tail_lookup_factory(runs)
    return {
        pid: compute_streak(apps, lookup, counted_kinds, basis=basis)
        for pid, apps in by_player.items()
    }


def build_item(player_id: str, name: str | None, apps: Sequence[Appearance],
               res: StreakResult, basis: Basis = EARNED_RUN_BASIS) -> dict:
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
        "basis": _extended_basis(basis),
        "strict_basis": basis.strict_basis,
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
    basis: Basis = EARNED_RUN_BASIS,
) -> dict:
    """連續無（自責）失分局數（下界）。`player_id` 指定時回單人，否則回該季母體排行。

    `basis` 決定判準與對外名詞（`EARNED_RUN_BASIS` 預設／`RUN_BASIS`）。payload 形狀
    兩者完全相同，前端可用同一個元件消費；差異全在 `metric`／`metric_label`／`note`／
    `basis`／`break_reason`。

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

    results = compute_all(by_player, counted_kinds, basis=basis)
    items = [build_item(pid, names.get(pid), by_player[pid], res, basis)
             for pid, res in results.items()]
    if player_id is None:
        items = [i for i in items if i["outs"] > 0]
    items.sort(key=lambda i: (-i["outs"], -i["strict_outs"], i["player_id"]))
    if player_id is None:
        items = items[:limit]

    as_of = max((a.game_date for apps in by_player.values() for a in apps if a.game_date),
                default=None)
    # 揭露欄位**兩個口徑都掛**（需求方裁決 2026-08-08：並列，失分為預設呈現面）。
    # iteration 1 曾只掛在失分口徑上，理由是卡面「既有端點行為不得改變」；裁決既定為
    # 並列，前提就變成**兩支對外語意必須對稱**——只有一支帶 `basis_field`／
    # `lower_bound_note`，讀者無從判斷另一支的判準欄位與下界性質。
    #
    # 這是**刻意的相容性破壞**，不是「向後相容的新增欄位」：對做嚴格 key 比對的消費者
    # 而言，多一個 key 就是破壞。目前 `web/` 兩支端點皆零消費者，破壞面僅止於 API 契約
    # 本身。兩支的 key 集合由 `tests/test_scoreless_streak_api.py` 的雙向凍結斷言釘住。
    return {
        "metric": basis.metric,
        "metric_label": basis.metric_label,
        "note": basis.metric_note,
        "basis_field": basis.field,          # 判準的官方欄位名，供前端／稽核直接對照
        "lower_bound_note": LOWER_BOUND_NOTE,
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


# ---------------------------------------------------------------------------
# 輸入指紋與漂移分類（ML-PITCHER-RUNLESS1 iteration 3）
#
# 為什麼放在取數層：指紋要指的是**演算法實際吃到的那份輸入**。若另寫一支平行 SQL 去
# 算指紋，那支 SQL 會和 `load_appearances`／`load_opponent_runs` 各自演化，指紋就會
# 慢慢不再代表輸入——所以出賽側的指紋直接由已載入的 `Appearance` 物件算出。
#
# 解決的問題：本紀錄的母體**每天都會長大**（新比賽入庫），所以「artifact 的數字重跑後
# 不一樣」是常態，不是缺陷（canonical `templates/statistical-redline.md` 第 9 條：
# 母體隨資料新增而變動是正常狀態，處置為標注 as-of，**不設法凍結數字**）。
# 但「不凍結」不等於「無從查證」——需要能區分兩件事：
#
#   輸入變了 → 輸出跟著變      = input drift，預期行為，報漂移量即可
#   輸入沒變 → 輸出卻不一樣    = 演算法／環境出問題，這才該紅
#
# 指紋涵蓋演算法讀到的**全部**兩張表：`pitching_gamelog`（＋ join 進來的 `games` 欄位）
# 與 `game_scoreboard`。除此之外本模組不讀任何資料，所以「指紋相同 ⇒ 輸入相同」在本
# 演算法的範圍內成立。**不涵蓋**程式碼版本——指紋相同而數字不同時，程式碼變更同樣是
# 候選原因，分類器只負責指出「不是資料造成的」，不負責指出是什麼造成的。
# ---------------------------------------------------------------------------

# 逐局比分側的指紋：**原始列**（不做 `max(score_cnt)` 聚合），比載入層更嚴格。
# `score_cnt` 的 NULL 用 '?' 表示而非 0——未知在指紋裡也要有自己的名字。
_SCOREBOARD_DIGEST_SQL = """
    SELECT count(*) AS rows_total,
           md5(coalesce(string_agg(t, E'\\n' ORDER BY t), '')) AS digest
      FROM (SELECT s.year || '/' || s.kind_code || '/' || s.game_sno || '/'
                   || coalesce(s.visiting_home_type, '-') || '/' || s.inning_seq
                   || '/' || coalesce(s.score_cnt::text, '?') AS t
              FROM cpbl.game_scoreboard s
              JOIN cpbl.games g USING (year, kind_code, game_sno)
             WHERE s.kind_code = ANY(%(kinds)s) AND s.year >= %(from_year)s
               -- cutoff 必須和出賽側用同一條界線：只濾一邊會讓「重建的舊快照」帶著
               -- 新的逐局比分，指紋因此不代表任何真實存在過的輸入狀態。
               AND (%(cutoff)s::date IS NULL OR g.game_date <= %(cutoff)s::date)) x
"""


def _appearance_digest(by_player: Mapping[str, Sequence[Appearance]]) -> str:
    """已載入出賽母體的內容指紋。排序後串接再雜湊，與載入順序無關。

    納入演算法會讀到的每一個欄位；`None` 一律寫成 `?`，不折成 0——把未知折成已知會讓
    兩份不同的輸入拿到同一個指紋，那正是指紋要防的事。
    """
    lines = sorted(
        "|".join(str(v) if v is not None else "?" for v in (
            pid, a.year, a.kind_code, a.game_sno, a.game_date, a.earned_runs, a.runs,
            a.outs, a.delay_kind, a.vht, a.opponent_score, a.team_code))
        for pid, apps in by_player.items() for a in apps
    )
    return hashlib.md5("\n".join(lines).encode()).hexdigest()   # noqa: S324 — 非安全用途


def population_fingerprint(
    by_player: Mapping[str, Sequence[Appearance]], kinds: Sequence[str],
    cutoff: date | None = None,
) -> dict:
    """→ 這次執行實際吃到的輸入的可比對描述（含 as-of、規模與內容指紋）。

    `data_asof` 是母體中最新的一場比賽日期，**不是 wall-clock**——artifact 因此不含
    執行時間，逐次比對才有意義（卡面驗證：artifact 不含 wall-clock 時戳）。

    **`data_asof` 排除保留賽**：保留賽的 `game_date` 是**改期後的未來日期**，而比分卻
    已經記上（實例 2026/D/165：`orig_date` 07-17、`game_date` 09-15、比分 1:3）。直接取
    `max(game_date)` 會讓 as-of 標成 2026-09-15，讀起來像「資料到九月」，實際上只到八月
    ——那是**把排程日期誤讀成資料新鮮度**。保留賽本來就一律中斷、不採計（見
    `compute_streak`），拿它當新鮮度指標更沒有理由。
    原始最大值仍以 `latest_game_date_any` 揭露，不做沉默捨棄。

    **排除只影響 as-of 這個標籤，不影響指紋**：`appearance_digest` 涵蓋每一列（含保留賽），
    所以保留賽被改期或補上比分仍會被偵測為輸入變動。
    """
    rows = _fetch_scoreboard_digest(kinds, cutoff)
    dates = [a.game_date for apps in by_player.values() for a in apps if a.game_date]
    played = [a.game_date for apps in by_player.values() for a in apps
              if a.game_date and a.delay_kind != SUSPENDED]
    return {
        "data_asof": str(max(played)) if played else None,
        "latest_game_date_any": str(max(dates)) if dates else None,
        "pitchers": len(by_player),
        "appearances": sum(len(apps) for apps in by_player.values()),
        "appearance_digest": _appearance_digest(by_player),
        "scoreboard_rows": rows["rows_total"],
        "scoreboard_digest": rows["digest"],
    }


def _fetch_scoreboard_digest(kinds: Sequence[str], cutoff: date | None = None) -> dict:
    with conn() as c:
        cur = c.cursor()
        cur.execute(_SCOREBOARD_DIGEST_SQL,
                    {"kinds": list(kinds), "from_year": DATA_FROM_YEAR, "cutoff": cutoff})
        return _dicts(cur)[0]


#: `classify_artifact_drift` 的三種判定。
DRIFT_IDENTICAL = "identical"          # 輸入與輸出都相同
DRIFT_INPUT = "input_drift"            # 輸入變了（預期；**不是缺陷**）
DRIFT_MISMATCH = "mismatch_same_input" # 輸入沒變、輸出卻變了（**這才該紅**）


def classify_artifact_drift(
    previous: Mapping | None, current: Mapping, tracked: Sequence[str],
) -> dict:
    """比對「artifact 裡記的那次執行」與「這次執行」，把差異歸因到輸入或輸出。

    `previous`／`current` 各需含 `fingerprint`（`population_fingerprint` 的輸出）與
    `tracked` 列出的統計欄位。回傳 `verdict` ＋ 逐欄位的 `before/after/delta`。

    **判定規則**（刻意只有這三種，不做「差得不多所以算過」之類的模糊帶）：

    - 指紋不同 → `input_drift`。母體長大或既有場次被修訂都會落在這裡，兩者都是資料
      面的正常事件。此時輸出數字不同**不構成失敗**，只報漂移量。
    - 指紋相同、追蹤欄位全同 → `identical`。
    - 指紋相同、追蹤欄位有差 → `mismatch_same_input`。同一份輸入給出不同輸出，
      資料面已被指紋排除，剩下的候選是程式碼或執行環境——**呼叫端應視為失敗**。

    `previous` 為 None（artifact 是舊格式、沒有指紋）時回 `verdict=None` 並說明原因，
    **不猜**：無從比對就明講無從比對，不要用「看起來差不多」放行。
    """
    if not previous or "fingerprint" not in previous:
        return {"verdict": None,
                "reason": "artifact 未帶 fingerprint（舊格式），本次無從分類，"
                          "請以本次輸出重新產生 artifact 後再比"}
    before, after = previous["fingerprint"], current["fingerprint"]
    input_changed = any(before.get(k) != after.get(k)
                        for k in ("appearance_digest", "scoreboard_digest"))
    fields = [
        {"field": k, "before": previous.get(k), "after": current.get(k),
         "delta": (current.get(k) - previous.get(k))
         if isinstance(previous.get(k), int) and isinstance(current.get(k), int) else None}
        for k in tracked
    ]
    changed = [f for f in fields if f["before"] != f["after"]]
    verdict = (DRIFT_INPUT if input_changed
               else DRIFT_MISMATCH if changed else DRIFT_IDENTICAL)
    return {
        "verdict": verdict,
        "data_asof_before": before.get("data_asof"),
        "data_asof_after": after.get("data_asof"),
        "input_delta": {
            k: {"before": before.get(k), "after": after.get(k),
                "delta": (after.get(k) - before.get(k))
                if isinstance(before.get(k), int) and isinstance(after.get(k), int)
                else None}
            for k in ("pitchers", "appearances", "scoreboard_rows")
        },
        "digest_changed": {
            "appearance": before.get("appearance_digest") != after.get("appearance_digest"),
            "scoreboard": before.get("scoreboard_digest") != after.get("scoreboard_digest"),
        },
        "fields": fields,
        "changed_fields": changed,
    }
