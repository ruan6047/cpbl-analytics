"""DATA-RECAP-WP-PRESTATE1：``/recap-wp`` 打席前比分的紅燈與全季窮舉回歸。

病灶（UX-GAME-RECAP1 第五輪範圍外發現）：``/recap-wp`` 以 canonical
``pre_state.away_score``／``home_score`` 當「打席前比分」餵進 WP 解算器。但 livelog 的
比分欄是**事件後**快照，而 ``pre_state`` 是把**起始事件列**的比分欄原樣存下來——單一
事件就結束的得分打席（首球全壘打、首球再見安打…）起始列＝終結列，存到的已經是得分
**後**的比分。後果有兩層：

1. 該打席自己的 ``wpa``：``before`` 已經含了這一分 → 擺動被吃掉（趨近 0）。
2. **前一個打席**：其 ``after`` 錨點正是這個被污染的 ``pre_state`` → 平白背走那一分的
   勝率擺動，受益隊歸屬也跟著錯。

修法比照 ``models/pa_facts.delta_re24``（同一條紅線已在事實流側驗證過）：以
``start_event_no`` 對回 ``annotate_scores()`` 標好的事件流，取該事件**之前**的 running
比分。**病灶在讀取端**——canonical PA 忠實存下來源欄位，本卡不動 DB。

本檔釘三件事：
* 純函式紅燈：得分事件落在打席**起始列**（本卡病灶）與落在打席**之間**（盜壘／暴投，
  舊碼碰巧正確）兩種形狀都要對；解不出來要 fail closed 而非退回 ``pre_state``。
* 跨端點一致性：同一場同一打席，``/recap-wp`` 與 ``/facts`` 的打席前比分逐位相同。
* 全季窮舉（需 DB）：2026/A 全部 published 場次逐打席比對，**零分歧**；且新舊讀法的
  差異必須全部被「起始事件自帶得分」這個封閉形式解釋，不存在未歸類的差異。
"""

from __future__ import annotations

import psycopg
import pytest
from psycopg_pool import PoolClosed, PoolTimeout

from cpbl.api.routers.recap import (
    _load_livelog_scores,
    _load_pa_rows,
    enrich_items,
    pre_scores_from_events,
)
from cpbl.models.pa_facts import (
    RE_SPAN,
    delta_re24,
    load_livelog,
    load_published_pas,
    load_re_matrix,
)
from tests.test_pa_facts import ev, fake_scorer


# ===========================================================================
# 純函式紅燈
# ===========================================================================
def _rows_of(events: list[dict]) -> list[dict]:
    from cpbl.models.pa_facts import pa_rows_from_snapshot

    rows, _ = pa_rows_from_snapshot(2026, "A", 1, events)
    return rows


def test_run_on_the_starting_event_is_not_counted_as_pre_pa_score() -> None:
    """本卡病灶的最小重現：首球全壘打的打席前比分是 0：0，不是 1：0。"""
    events = [
        ev(1, "A1", action="全壘打", content="擊出陽春全壘打。1分打點。",
           is_strike=True, away=1),
        ev(2, "A2", action="三振", content="三振出局。 1人出局。", is_strike=True,
           order=2, away=1),
    ]
    rows = _rows_of(events)
    homer = rows[0]
    assert homer["pre_state"]["away_score"] == 1        # canonical 存的是事件後值
    scores = pre_scores_from_events(rows, events)
    assert scores[homer["pa_index"]] == (0, 0)          # 讀取端取事件前
    assert scores[rows[1]["pa_index"]] == (1, 0)        # 下一打席才看得到那一分


def test_run_scored_between_plate_appearances_is_included() -> None:
    """得分落在打席**之間**（盜壘／暴投）時，該分必須算進下一打席的打席前比分。

    這是另一半的守門：修法不能矯枉過正成「一律扣掉起始列的得分」——只有起始列**自身**
    造成的得分才不屬於打席前。
    """
    events = [
        ev(1, "A1", action="一壘安打", content="擊出一壘安打。", is_strike=True),
        # 打席之間的得分事件（無打者結果的特殊列，不 seed 打席）
        ev(2, None, action="", content="投手投出暴投，三壘跑者回本壘得分。", away=1,
           pitch_cnt=None, b3="A1"),
        ev(3, "A2", action="三振", content="三振出局。 1人出局。", is_strike=True,
           order=2, away=1),
    ]
    rows = _rows_of(events)
    scores = pre_scores_from_events(rows, events)
    last = rows[-1]
    assert scores[last["pa_index"]] == (1, 0)


def test_unresolvable_start_event_is_omitted_not_guessed() -> None:
    """``start_event_no`` 對不回事件流 → 不進 map（呼叫端 fail closed），不退回 pre_state。"""
    events = [ev(1, "A1", action="全壘打", content="擊出陽春全壘打。1分打點。",
                 is_strike=True, away=1)]
    rows = _rows_of(events)
    assert pre_scores_from_events(rows, []) == {}
    items = enrich_items(rows, pre_scores={}, completed=True, final_outcome=0.0,
                         scorer=fake_scorer)
    assert items[0]["wp_unavailable_reason"] == "pre_score_unresolved"
    assert items[0]["away_score_before"] is None


def test_beneficiary_moves_from_the_previous_pa_to_the_scoring_pa() -> None:
    """第二層後果的紅燈：那一分的勝率擺動必須記在得分打席，不是前一個打席。

    修復前：前一打席的 after 錨點＝被污染的 pre_state（已含該分）→ 前一打席吃掉整個
    擺動、得分打席自己趨近 0。
    """
    events = [
        ev(1, "A1", action="三振", content="三振出局。 1人出局。", is_strike=True),
        ev(2, "A2", action="全壘打", content="擊出陽春全壘打。1分打點。", is_strike=True,
           out=1, order=2, away=1),
        ev(3, "A3", action="一壘安打", content="擊出一壘安打。", is_strike=True, out=1,
           order=3, away=1),
    ]
    rows = _rows_of(events)
    fixed = {it["pa_index"]: it for it in enrich_items(
        rows, pre_scores=pre_scores_from_events(rows, events), completed=True,
        final_outcome=0.0, scorer=fake_scorer)}
    legacy_scores = {r["pa_index"]: (r["pre_state"]["away_score"],
                                     r["pre_state"]["home_score"]) for r in rows}
    legacy = {it["pa_index"]: it for it in enrich_items(
        rows, pre_scores=legacy_scores, completed=True, final_outcome=0.0,
        scorer=fake_scorer)}
    homer, prev = rows[1]["pa_index"], rows[0]["pa_index"]
    # 修復後：得分打席自己是負的（客隊得分 → 主隊勝率下降），前一打席不受該分影響
    assert fixed[homer]["wpa"] < 0 and fixed[homer]["beneficiary_team"] == "away"
    # 修復前：擺動被搬到前一打席，得分打席自己反而比修復後平緩
    assert legacy[prev]["wpa"] < fixed[prev]["wpa"]
    assert abs(legacy[homer]["wpa"]) < abs(fixed[homer]["wpa"])


# ===========================================================================
# 全季窮舉回歸（需 DB；無 DB 時 skip）
# ===========================================================================
SEASON, KIND = 2026, "A"


def _published_games() -> list[int]:
    from cpbl.db import conn

    with conn() as connection:
        cur = connection.cursor()
        cur.execute(
            "SELECT DISTINCT pa.game_sno FROM cpbl.game_plate_appearances pa "
            "JOIN cpbl.game_recap_builds b USING (build_id) "
            "WHERE b.state='published' AND pa.year=%s AND pa.kind_code=%s "
            "ORDER BY 1", (SEASON, KIND))
        return [int(r[0]) for r in cur.fetchall()]


@pytest.fixture(scope="module")
def season_games() -> list[int]:
    try:
        games = _published_games()
    except (psycopg.Error, PoolClosed, PoolTimeout, OSError) as exc:
        pytest.skip(f"無 DB：{type(exc).__name__}")
    if not games:
        pytest.skip("DB 無 published PA build")
    return games


def _facts_pre_scores(season: int, kind: str, sno: int,
                      re_map: dict) -> dict[int, tuple]:
    """``/facts`` 側的打席前比分（``pa_facts.delta_re24`` 是這兩欄的唯一產生者）。"""
    from cpbl.db import conn

    with conn() as connection:
        cur = connection.cursor()
        rows = load_published_pas(cur, season, kind, sno)
        events = load_livelog(cur, season, kind, sno)
    facts = delta_re24(rows, events, re_map)
    return {f["pa_index"]: (f["away_score_before"], f["home_score_before"]) for f in facts}


def _recap_pre_scores(season: int, kind: str, sno: int) -> dict[int, tuple]:
    """``/recap-wp`` 側：走路由自己的 DB adapter 與純函式（含 SQL 是否真的取 start_event_no）。"""
    rows = _load_pa_rows(season, kind, sno)
    events = _load_livelog_scores(season, kind, sno)
    items = enrich_items(rows, pre_scores=pre_scores_from_events(rows, events),
                         completed=True, final_outcome=1.0, scorer=None)
    return {it["pa_index"]: (it["away_score_before"], it["home_score_before"])
            for it in items}


def test_full_season_pre_scores_match_the_fact_stream(season_games) -> None:
    """全季窮舉：``/recap-wp`` 與 ``/facts`` 的逐打席打席前比分**零分歧**。

    宣稱由本測試的窮舉產生，不是人工抽驗；分母（場次數、打席數）一併 assert 出來，
    避免「跑了 0 場也叫全季一致」。
    """
    from cpbl.db import conn

    with conn() as connection:
        re_map = load_re_matrix(connection.cursor(), KIND, RE_SPAN)
    mismatches: list[tuple] = []
    unresolved: list[tuple] = []
    total_pas = 0
    for sno in season_games:
        theirs = _facts_pre_scores(SEASON, KIND, sno, re_map)
        mine = _recap_pre_scores(SEASON, KIND, sno)
        assert set(mine) == set(theirs), (sno, "pa_index 集合不一致")
        total_pas += len(mine)
        for index, value in mine.items():
            if value != theirs[index]:
                mismatches.append((sno, index, value, theirs[index]))
            if value == (None, None):
                unresolved.append((sno, index))
    assert len(season_games) >= 200, f"母體過小，不足以稱全季：{len(season_games)} 場"
    assert total_pas > 0
    assert not unresolved, f"打席前比分解不出（前 5 筆）：{unresolved[:5]}"
    assert not mismatches, f"與事實流分歧（前 5 筆）：{mismatches[:5]}"


def test_full_season_legacy_differences_are_all_explained(season_games) -> None:
    """新舊讀法的差異必須**全部**被「起始事件自帶得分」解釋，不存在未歸類的差異。

    這是修復的封閉形式證明：若差異裡出現無法用該形式解釋的筆數，代表病灶不只一種
    形狀（或修法有副作用），必須人工判讀而非放行。
    """
    from cpbl.db import conn
    from cpbl.models.pa_facts import annotate_scores

    unexplained: list[tuple] = []
    changed = 0
    for sno in season_games:
        rows = _load_pa_rows(SEASON, KIND, sno)
        events = _load_livelog_scores(SEASON, KIND, sno)
        fixed = pre_scores_from_events(rows, events)
        by_event = {str(e["main_event_no"]): e for e in annotate_scores(events)}
        for row in rows:
            legacy = ((row.get("pre_state") or {}).get("away_score"),
                      (row.get("pre_state") or {}).get("home_score"))
            if row["pa_index"] not in fixed or fixed[row["pa_index"]] == legacy:
                continue
            changed += 1
            start = by_event.get(str(row.get("start_event_no")))
            # 封閉解釋：起始事件列**自身**造成得分（事件後 ≠ 事件前）
            scored_on_start = start is not None and (
                (start["_post_away"], start["_post_home"])
                != (start["_pre_away"], start["_pre_home"]))
            if not (scored_on_start and (start["_post_away"], start["_post_home"]) == legacy):
                unexplained.append((sno, row["pa_index"], legacy, fixed[row["pa_index"]]))
    assert changed > 0, "全季找不到任何受影響打席——病灶重現失敗，測試無效"
    assert not unexplained, f"未歸類的差異（前 5 筆）：{unexplained[:5]}"
    with conn() as connection:  # 分母留痕：受影響打席佔全季比例
        cur = connection.cursor()
        cur.execute(
            "SELECT count(*) FROM cpbl.game_plate_appearances pa "
            "JOIN cpbl.game_recap_builds b USING (build_id) "
            "WHERE b.state='published' AND pa.year=%s AND pa.kind_code=%s",
            (SEASON, KIND))
        total = int(cur.fetchone()[0])
    assert changed < total, (changed, total)
