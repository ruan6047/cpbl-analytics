"""DATA-RE24-GHOST-RUNNER1：``sabr.build_re24`` 的幽靈跑者紅燈與「未歸類 = 0」回歸。

病灶（`docs/research/INIT-GAME-RECAP/spike-report.md` §2.3／§7 O-1）：延長賽「突破僵局
上壘」把跑者**直接放上二壘**，沒有打席、沒有投球，但 naive 的「連續同 hitter」切界會把
那一列當成該跑者的一個打席，記給他 ``+RE(_2_,0) − RE(___,0) = +0.6356``——2026/A 全季
49 筆、2024–2026/A 合計 202 筆，直接汙染球員頁 SABR 區線上可見的 RE24。

本檔釘兩件事：

1. **紅燈**：幽靈跑者列永遠不記給打者／投手，其 ΔRE 必須落到跑者桶（不是丟掉——丟掉會
   破壞望遠鏡求和恆等式，看起來像修好了其實是把帳做平）。判準必須來自 taxonomy，
   不是在 sabr.py 裡比中文字串。
2. **未歸類 = 0**：每個 naive 打席的處置屬於 ``RE24_DISPOSITIONS`` 這個封閉集合，且
   計數恰好分割全部打席，沒有第五種狀態。這是 spike 建議的釘法在季彙總路徑上的形式。
"""

from __future__ import annotations

import psycopg
import pytest
from psycopg_pool import PoolClosed, PoolTimeout

from cpbl.ingest.pa_build import classify_island, is_non_pa_action, load_taxonomy
from cpbl.models.sabr import (
    RE24_CHARGED,
    RE24_DISPOSITIONS,
    RE24_NON_PA,
    RE24_TRUNCATED,
    re24_disposition,
    re24_plays,
)

TIEBREAK = "突破僵局上壘"     # taxonomy v1.1.0 唯一的 role=non_pa 成員
GHOST = "0000009001"          # 被放上二壘的跑者
BATTER1 = "0000009002"
BATTER2 = "0000009003"
PITCHER = "0000009900"

# 0 出局的 RE 取生產矩陣（2018-2025/A）實值，好讓 +0.6356 這個具體數字有意義；
# 1／2 出局用固定衰減造出來（本檔的斷言不依賴它們的絕對值）。
_RE_BASE = {"___": 0.5269, "1__": 0.9012, "_2_": 1.1625, "__3": 1.3576,
            "12_": 1.4785, "1_3": 1.7241, "_23": 1.9663, "123": 2.2802}
RE_MAP = {(bases, outs): round(value * (1 - 0.4 * outs), 4)
          for bases, value in _RE_BASE.items() for outs in (0, 1, 2)}
GHOST_DELTA = round(RE_MAP[("_2_", 0)] - RE_MAP[("___", 0)], 4)   # +0.6356


@pytest.fixture(scope="module")
def taxonomy():
    return load_taxonomy()


def _event(no: str, *, inning: int, half: str, hitter: str, action: str | None,
           content: str = "", outs: int = 0, bases: tuple[str | None, str | None, str | None] = (None, None, None),
           away: int = 0, home: int = 0, change: bool = False) -> dict:
    first, second, third = bases
    return {
        "main_event_no": no, "inning_seq": inning, "visiting_home_type": half,
        "hitter_acnt": hitter, "pitcher_acnt": PITCHER, "action_name": action,
        "content": content, "out_cnt": outs, "is_change_player": change,
        "first_base": first, "second_base": second, "third_base": third,
        "visiting_score": away, "home_score": home,
    }


def _tiebreak_half() -> list[dict]:
    """延長 10 局下：幽靈跑者上二壘 → 打者 1 飛球出局 → 打者 2 再見安打。"""
    return [
        # 佈局列：無投球、壘上空（livelog 壘位是「事件前」快照）
        _event("1020001000", inning=10, half="2", hitter=GHOST, action=TIEBREAK,
               content="突破僵局上二壘。"),
        _event("1020002000", inning=10, half="2", hitter=BATTER1, action="飛球接殺",
               content="擊出右外野高飛球， 打者-右外野手 飛球接殺出局。 1人出局。",
               bases=(None, "7", None)),
        _event("1020003000", inning=10, half="2", hitter=BATTER2, action="一壘安打",
               content="擊出中外野方向一壘安打。 二壘跑者回本壘得分。",
               outs=1, bases=(None, "7", None), home=1),
    ]


# ===========================================================================
# 紅燈：幽靈跑者不進打者桶
# ===========================================================================
def test_tiebreak_runner_is_never_charged_to_a_batter(taxonomy):
    plays, _totals = re24_plays(_tiebreak_half(), RE_MAP, taxonomy)
    ghost = [p for p in plays if p["hitter_acnt"] == GHOST]
    assert len(ghost) == 1, "幽靈跑者列仍應被列舉（要能稽核），只是不得記給打者"
    assert ghost[0]["disposition"] == RE24_NON_PA
    charged = [p for p in plays if p["disposition"] == RE24_CHARGED]
    assert GHOST not in {p["hitter_acnt"] for p in charged}


def test_tiebreak_delta_is_the_known_plus_zero_point_six_three_five_six(taxonomy):
    """病灶的具體數值：這一列在舊碼下每筆給跑者 +0.6356。"""
    plays, _totals = re24_plays(_tiebreak_half(), RE_MAP, taxonomy)
    ghost = next(p for p in plays if p["hitter_acnt"] == GHOST)
    assert round(ghost["delta"], 4) == GHOST_DELTA == 0.6356


def test_tiebreak_delta_goes_to_the_runner_bucket_not_the_bin(taxonomy):
    """排除 ≠ 丟掉：ΔRE 必須落到跑者桶，否則望遠鏡求和恆等式會破。

    恆等式（build_re24 docstring）：Σ打者 + Σ跑者 = Σ得分 − 半局數 × RE(空壘,0)。
    """
    plays, totals = re24_plays(_tiebreak_half(), RE_MAP, taxonomy)
    batter_sum = sum(p["delta"] for p in plays if p["disposition"] == RE24_CHARGED)
    expected = totals["runs"] - totals["halves"] * RE_MAP[("___", 0)]
    assert round(batter_sum + totals["runner_delta"], 6) == round(expected, 6)


def test_real_batters_in_the_same_half_are_still_charged(taxonomy):
    """避免修過頭：同半局的真實打者照記，且幽靈列不會吃掉他們的打席。"""
    plays, _totals = re24_plays(_tiebreak_half(), RE_MAP, taxonomy)
    charged = {p["hitter_acnt"] for p in plays if p["disposition"] == RE24_CHARGED}
    assert charged == {BATTER1, BATTER2}


def test_tiebreak_pitcher_is_not_charged_either(taxonomy):
    """投手桶同病同治：沒有打席就沒有被面對的打者。"""
    plays, _totals = re24_plays(_tiebreak_half(), RE_MAP, taxonomy)
    ghost = next(p for p in plays if p["hitter_acnt"] == GHOST)
    assert ghost["disposition"] != RE24_CHARGED
    assert ghost["pitcher_acnt"] == PITCHER, "仍要留著投手欄供稽核，只是不記帳"


# ===========================================================================
# 判準的單一擁有者：taxonomy，不是字串字面值
# ===========================================================================
def test_criterion_comes_from_the_taxonomy(taxonomy):
    assert is_non_pa_action(TIEBREAK, taxonomy) is True
    assert is_non_pa_action("一壘安打", taxonomy) is False
    assert is_non_pa_action("", taxonomy) is False
    assert is_non_pa_action(None, taxonomy) is False
    # 未登錄的 action 不是「已知的非打席」；未知的 fail-closed 由呼叫端各自處理
    assert is_non_pa_action("這個動作不存在", taxonomy) is False


def test_re24_and_canonical_builder_agree_on_every_taxonomy_action(taxonomy):
    """同一份 taxonomy 下，RE24 路徑與 canonical PA builder 對「非打席」判定必須一致。

    兩邊各自比中文字串正是這張卡的病因；這條測試讓判準漂移直接紅燈。
    """
    for action in taxonomy.actions:
        island = [_event("1010001000", inning=1, half="1", hitter=BATTER1, action=action)]
        builder_says_non_pa = classify_island(island, taxonomy).state == "non_pa"
        re24_says_non_pa = re24_disposition(
            action, outs_before_terminal=0, runs_on_play=0, taxonomy=taxonomy) == RE24_NON_PA
        assert builder_says_non_pa == re24_says_non_pa, action


# ===========================================================================
# 未歸類 = 0：處置是封閉集合上的全函式
# ===========================================================================
def test_disposition_is_total_over_a_grid_of_inputs(taxonomy):
    actions = [TIEBREAK, "一壘安打", "三振", "", None, "這個動作不存在"]
    for action in actions:
        for outs in (0, 1, 2, 3, 4):
            for runs in (-1, 0, 1, 4):
                got = re24_disposition(action, outs_before_terminal=outs,
                                       runs_on_play=runs, taxonomy=taxonomy)
                assert got in RE24_DISPOSITIONS, (action, outs, runs, got)


def test_tiebreak_outranks_truncation_so_the_counter_stays_meaningful(taxonomy):
    """幽靈列即使同時符合截斷條件也要記成 non_pa（否則延長賽會稀釋截斷碎片指標）。"""
    assert re24_disposition(TIEBREAK, outs_before_terminal=3, runs_on_play=0,
                            taxonomy=taxonomy) == RE24_NON_PA
    assert re24_disposition("", outs_before_terminal=3, runs_on_play=0,
                            taxonomy=taxonomy) == RE24_TRUNCATED


def test_every_play_has_exactly_one_disposition(taxonomy):
    plays, _totals = re24_plays(_tiebreak_half(), RE_MAP, taxonomy)
    assert plays
    assert all(p["disposition"] in RE24_DISPOSITIONS for p in plays)


# ===========================================================================
# 真實資料窮舉（需要 DB；無 DB 時 skip）
# ===========================================================================
def _real_games(year: int = 2026, kind: str = "A") -> list[tuple[int, str, int]]:
    from cpbl.db import conn
    with conn() as connection:
        cur = connection.cursor()
        cur.execute("SELECT DISTINCT game_sno FROM cpbl.game_livelog "
                    "WHERE year=%s AND kind_code=%s ORDER BY game_sno", (year, kind))
        return [(year, kind, r[0]) for r in cur.fetchall()]


@pytest.fixture(scope="module")
def db_games() -> list[tuple[int, str, int]]:
    try:
        games = _real_games()
    except (psycopg.Error, PoolClosed, PoolTimeout, OSError) as exc:
        pytest.skip(f"無 DB：{type(exc).__name__}")
    if not games:
        pytest.skip("DB 無該季 livelog")
    return games


@pytest.fixture(scope="module")
def real_plays(db_games, taxonomy) -> list[dict]:
    from cpbl.db import conn
    from cpbl.models.sabr import _load_game, _load_re_matrix
    out: list[dict] = []
    with conn() as connection:
        cur = connection.cursor()
        re_map = _load_re_matrix(cur, "2018-2025", "A")
        if not re_map:
            pytest.skip("DB 無 run_expectancy 矩陣")
        for year, kind, sno in db_games:
            events = _load_game(cur, year, kind, sno)
            if not events:
                continue
            plays, _totals = re24_plays(events, re_map, taxonomy)
            for play in plays:
                play["game_sno"] = sno
            out.extend(plays)
    return out


def test_no_naive_pa_is_unclassified_on_real_games(real_plays):
    """全季窮舉：每個打席的處置都在封閉集合內，沒有第五種狀態。"""
    unknown = [(p["game_sno"], p["end_event_no"], p["disposition"])
               for p in real_plays if p["disposition"] not in RE24_DISPOSITIONS]
    assert not unknown, f"未歸類打席：{unknown[:10]}"


def test_every_tiebreak_row_in_the_database_is_excluded(db_games, real_plays):
    """紅燈的真實資料版：DB 裡每一筆幽靈跑者列都必須被排除在打者桶之外。

    以 SQL 獨立列舉母體（不靠被驗證的那條路徑自報家門），再逐筆比對。
    """
    from cpbl.db import conn
    year, kind, _ = db_games[0]
    with conn() as connection:
        cur = connection.cursor()
        cur.execute(
            "SELECT game_sno, main_event_no FROM cpbl.game_livelog "
            "WHERE year=%s AND kind_code=%s AND action_name=%s "
            "AND NOT COALESCE(is_change_player, false) AND hitter_acnt IS NOT NULL",
            (year, kind, TIEBREAK))
        expected = {(r[0], str(r[1])) for r in cur.fetchall()}
    if not expected:
        pytest.skip("該季無延長賽突破僵局列")
    seen = {(p["game_sno"], p["end_event_no"]) for p in real_plays
            if p["disposition"] == RE24_NON_PA}
    assert expected <= seen, f"漏抓的幽靈列：{sorted(expected - seen)[:10]}"
    charged = {(p["game_sno"], p["end_event_no"]) for p in real_plays
               if p["disposition"] == RE24_CHARGED}
    assert not (expected & charged), f"仍被記給打者的幽靈列：{sorted(expected & charged)[:10]}"
