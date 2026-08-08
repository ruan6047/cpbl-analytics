"""ML-PITCHER-ER-REBUILD1 iteration 8 回歸：`official_error_unlocated` 的窄化界線。

官方記分板說某半局有失誤、逐球敘述卻完全沒寫時，`rebuild_er.py` 原本**整場**
fail-closed。消融量到那道閘門擋掉的 62 場裡有 34 場拿掉閘門就會通過，逐案查證後
其中 23 場的未定位失誤落在**一分未得的半局**——9.16 的失誤效果（(b) 失誤所致得分
非自責、(d) 以無失誤重建該半局、漏接第三出局後該半局的續打）全部侷限在同一個
半局內，重建的帳本也逐半局重置，故該半局沒有分可以被那個看不見的失誤影響。
擋掉它們是**排太多**。

窄化因此只有一條界線：**該半局官方得分為 0 才放行**。本檔把界線的兩側都釘住，
避免日後被誤讀成「官方說有失誤就一律放行」：

* `2018/A/124` 十二局下 官方 E=1、敘述無失誤字樣、**該半局 0 分** → 不得再被擋；
* `2018/A/213` 一局下 官方 E=1、敘述無失誤字樣、**該半局 1 分** → 仍須擋。

並釘住 `--mutation wide_official_error_gate` 能還原窄化前的行為——窄化本身要能被
消融，否則「修正」與「放寬」分不開（卡面紅線的基準案例即出自這個分界）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "docs" / "research" / "ML-PITCHER-ER-REBUILD1"
sys.path.insert(0, str(RESEARCH))

ER_IRRELEVANT_GAME = (2018, "A", 124)  # 12 局下 E=1、該半局 0 分
ER_POSSIBLE_GAME = (2018, "A", 213)  # 1 局下 E=1、該半局 1 分


def _rebuild(year: int, kind: str, sno: int, mutation: str = "full"):
    """唯讀取單場 livelog ＋ 記分板並重建。DB 不可達時 skip（沿用本倉慣例）。"""
    try:
        import psycopg
        from psycopg.rows import dict_row
        from rebuild_er import DSN, EVENT_COLS, _s, rebuild_game

        from cpbl.ingest.pa_build import load_taxonomy

        taxonomy = load_taxonomy()
        with psycopg.connect(DSN, row_factory=dict_row, connect_timeout=5) as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT {EVENT_COLS} FROM cpbl.game_livelog "  # noqa: S608
                "WHERE year=%s AND kind_code=%s AND game_sno=%s",
                (year, kind, sno),
            )
            events = [dict(r) for r in cur.fetchall()]
            cur.execute(
                "SELECT inning_seq, visiting_home_type, error_cnt, score_cnt "
                "FROM cpbl.game_scoreboard "
                "WHERE year=%s AND kind_code=%s AND game_sno=%s",
                (year, kind, sno),
            )
            errors: dict[tuple[int, str], int] = {}
            half_runs: dict[tuple[int, str], int] = {}
            for r in cur.fetchall():
                if r["inning_seq"] is None:
                    continue
                inning = int(r["inning_seq"])
                visiting = _s(r["visiting_home_type"]) == "1"
                if r["error_cnt"] is not None:
                    # 失誤是守方犯的 → 半局別翻轉
                    ek = (inning, "2" if visiting else "1")
                    errors[ek] = errors.get(ek, 0) + int(r["error_cnt"])
                if r["score_cnt"] is not None:
                    # 得分是攻方的 → 半局別不翻
                    rk = (inning, "1" if visiting else "2")
                    half_runs[rk] = half_runs.get(rk, 0) + int(r["score_cnt"])
    except Exception as exc:  # noqa: BLE001 - 無 DB／無 livelog 皆非本測試要驗的事
        pytest.skip(f"DB 不可達或資料未就緒：{type(exc).__name__}: {exc}")

    if not events:
        pytest.skip(f"{year}/{kind}/{sno} 無 livelog 資料")
    return rebuild_game(
        year, kind, sno, events, taxonomy, mutation=mutation,
        official_errors=errors, official_half_runs=half_runs,
    )


def test_unlocated_error_in_scoreless_half_is_not_excluded() -> None:
    """一分未得的半局裡的未定位失誤，不得再讓整場 fail-closed。"""
    res = _rebuild(*ER_IRRELEVANT_GAME)
    assert res.reason != "official_error_unlocated", (
        "該半局 0 分，未定位失誤依 9.16 的半局侷限性不可能影響三個對帳維度，"
        f"仍被排除代表窄化已回歸：detail={res.detail}"
    )


def test_unlocated_error_in_scoring_half_is_still_excluded() -> None:
    """有得分的半局裡的未定位失誤仍須擋——窄化不得擴大成「一律放行」。"""
    res = _rebuild(*ER_POSSIBLE_GAME)
    assert res.reason == "official_error_unlocated", (
        "該半局有得分、失誤發生在哪一球未知，那些分的自責與否無從判定，"
        f"必須維持 fail-closed，實得 reason={res.reason} detail={res.detail}"
    )


def test_wide_gate_mutation_restores_pre_narrowing_behaviour() -> None:
    """窄化本身要能被消融，否則「修正」與「放寬」分不開。"""
    res = _rebuild(*ER_IRRELEVANT_GAME, mutation="wide_official_error_gate")
    assert res.reason == "official_error_unlocated", (
        "`wide_official_error_gate` 應還原窄化前的整場排除行為，"
        f"實得 reason={res.reason} detail={res.detail}"
    )
