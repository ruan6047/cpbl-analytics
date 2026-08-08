"""ML-PITCHER-ER-REBUILD1 R1-001 回歸：比分欄的延後**會跨 island**。

`docs/research/ML-PITCHER-ER-REBUILD1/rebuild_er.py` iteration 1–6 以
「本 island 比分 − 前一 island 比分」當作該 island 的得分數，等於假設比分欄的更新
一定落在同一個 island 內。跨家族查核以 `2026/A/81` 三局下打穿該假設：

    0320019000（劉基鴻，**單列 island**）犧牲飛球，content 已寫
                 「三壘跑者郭天信回本壘得分」，home_score 仍為 2
    0320021000（朱育賢，下一個 island 的首列）無任何得分敘述，home_score 變 3

舊版因此在朱育賢那個 island 判 `unnarrated_run` 把**整場**排除；就算放行，主迴圈
在劉基鴻那個 island 也會得到 `island_runs=0` 卻有 1 位具名跑者而落入
`run_count_mismatch`。fail-closed 排得太多與排得太少一樣是問題——它會讓剩下的
母體看起來比實際乾淨。

本檔釘住修正後的行為：三局下不得再成為排除原因。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "docs" / "research" / "ML-PITCHER-ER-REBUILD1"
sys.path.insert(0, str(RESEARCH))

GAME = (2026, "A", 81)


def _rebuild(year: int, kind: str, sno: int):
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
                "SELECT inning_seq, visiting_home_type, error_cnt "
                "FROM cpbl.game_scoreboard "
                "WHERE year=%s AND kind_code=%s AND game_sno=%s",
                (year, kind, sno),
            )
            official_errors: dict[tuple[int, str], int] = {}
            for r in cur.fetchall():
                if r["inning_seq"] is None or r["error_cnt"] is None:
                    continue
                half = "2" if _s(r["visiting_home_type"]) == "1" else "1"
                key = (int(r["inning_seq"]), half)
                official_errors[key] = official_errors.get(key, 0) + int(r["error_cnt"])
    except Exception as exc:  # noqa: BLE001 - 無 DB／無 livelog 皆非本測試要驗的事
        pytest.skip(f"DB 不可達或資料未就緒：{type(exc).__name__}: {exc}")

    if not events:
        pytest.skip(f"{year}/{kind}/{sno} 無 livelog 資料")
    return rebuild_game(
        year, kind, sno, events, taxonomy, official_errors=official_errors
    )


def test_cross_island_score_deferral_does_not_exclude_inning3() -> None:
    """三局下的犧牲飛球不得再造成排除。

    斷言刻意**不**綁定「整場通過」——`2026/A/81` 十一局下的再見分在 livelog 裡
    確實沒有任何敘述（比分 3:3→3:5，逐球紀錄只有「比賽結束」），那是另一個成因，
    依需求方 7.4 裁定不得用「主隊獲勝」去猜，故整場仍應 fail-closed。
    """
    res = _rebuild(*GAME)
    detail = res.detail or ""

    assert res.reason != "run_count_mismatch", (
        f"三局下的延後比分又把具名跑者與 island 得分數對不上：{detail}"
    )
    assert not detail.startswith("i3/"), (
        f"三局下重新成為排除原因，R1-001 已回歸：reason={res.reason} detail={detail}"
    )


def test_walkoff_without_narration_is_still_failed_closed() -> None:
    """修正 R1-001 不得順手放寬「分數增加卻無人描述」這道閘門。

    若哪天 livelog 補上了該 play 的敘述，本場會整場通過——屆時 `res.ok` 為真也
    合格，本斷言只禁止「有未敘述得分卻仍判通過」。
    """
    res = _rebuild(*GAME)
    if res.ok:
        return
    assert res.reason == "unnarrated_run", (
        f"預期十一局下的未敘述再見分被 fail-closed，實得 {res.reason}: {res.detail}"
    )
