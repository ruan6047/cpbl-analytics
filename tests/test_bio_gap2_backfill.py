"""INGEST-PLAYER-BIO-GAP2 的寫入邊界與範圍閘門斷言。

為什麼要這些測試：本卡涵蓋的 batch 1 六人**有值可失**（height／weight／debut／
birthplace 來自更早的解析器），而生產端 `sync_table players` 是無條件覆蓋——本機寫錯
什麼，隔天 10:10 生產照抄。GAP1 的查核者實測證明「以徵狀列舉哪些情況不可寫」會漏
（漏掉部分解析頁與姓名不符頁），故本卡改以**語句本身的性質**保證邊界，而這些測試
釘的就是那個性質。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "backfill_player_bio_gap2",
    Path(__file__).resolve().parents[1] / "scripts" / "backfill_player_bio_gap2.py")
assert _SPEC and _SPEC.loader
gap2 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gap2)


# ── 寫入邊界：靠語句範圍，不靠守衛判斷 ────────────────────────────────────

def test_fill_sql_touches_only_the_eight_bio_columns_and_timestamp():
    sql = gap2.FILL_SQL
    assert sql.startswith("UPDATE cpbl.players SET ")
    for col in gap2.FILL_COLS:
        assert f"{col} = COALESCE({col}, %s)" in sql, f"{col} 必須是 COALESCE 只補缺"
    assert "bio_updated_at = now()" in sql
    assert sql.rstrip().endswith("WHERE id = %s")


@pytest.mark.parametrize("col", ["name", "country", "birthday"])
def test_fill_sql_cannot_touch_name_country_or_birthday(col):
    """country／birthday 是 GAP1 的交付值，name 會合法過期——三者都不得被本卡碰到。

    這不是「守衛擋住」而是「語句裡沒有」：欄名根本不出現，結構上不可能寫到。
    """
    assert f"{col} =" not in gap2.FILL_SQL
    assert col not in gap2.FILL_COLS


def test_fill_sql_placeholder_count_matches_columns():
    """參數數量對不上會在執行時才炸；這裡先釘住，避免改欄位時漏改參數組裝。"""
    assert gap2.FILL_SQL.count("%s") == len(gap2.FILL_COLS) + 1  # 八欄 + WHERE id


def test_fill_gap_passes_values_in_column_order(monkeypatch):
    """實際驅動 fill_gap，斷言傳入 SQL 的參數順序與 FILL_COLS 一致（非只驗字串）。"""
    captured: dict[str, object] = {}

    class _Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql, params):
            captured["sql"], captured["params"] = sql, params
            return type("R", (), {"rowcount": 1})()

    monkeypatch.setattr("cpbl.db.conn", lambda: _Conn())
    bio = {c: f"v_{c}" for c in gap2.FILL_COLS}
    bio["name"] = "不該被傳進去"
    assert gap2.fill_gap("0000007573", bio) == 1
    assert captured["params"] == (*[f"v_{c}" for c in gap2.FILL_COLS], "0000007573")
    assert captured["sql"] == gap2.FILL_SQL


def test_missing_page_fields_become_none_not_dropped(monkeypatch):
    """頁面缺某欄時要傳 None（讓 COALESCE 保留既有值），不是把該欄從參數裡漏掉。"""
    captured: dict[str, object] = {}

    class _Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql, params):
            captured["params"] = params
            return type("R", (), {"rowcount": 1})()

    monkeypatch.setattr("cpbl.db.conn", lambda: _Conn())
    gap2.fill_gap("0000007573", {"bats": "右打", "throws": "右投"})
    params = captured["params"]
    assert len(params) == len(gap2.FILL_COLS) + 1
    assert params[:2] == ("右打", "右投")
    assert all(p is None for p in params[2:-1]), "缺的欄位必須是 None"


# ── 寫入判定：只擋「值不是這個人的」 ──────────────────────────────────────

def test_name_mismatch_refuses_write():
    ok, reason = gap2.write_decision({"name": "別人", "bats": "右打"}, "李博登")
    assert (ok, reason) == (False, "name_mismatch")


def test_no_person_on_page_refuses_write():
    ok, reason = gap2.write_decision({"name": None}, "李博登")
    assert (ok, reason) == (False, "no_person_on_page")


def test_page_with_no_fillable_field_refuses_write():
    bio = {"name": "李博登", **{c: None for c in gap2.FILL_COLS}}
    assert gap2.write_decision(bio, "李博登") == (False, "nothing_to_fill")


def test_matching_name_with_any_field_may_write():
    bio = {"name": "李博登", **{c: None for c in gap2.FILL_COLS}, "throws": "左投"}
    assert gap2.write_decision(bio, "李博登") == (True, "ok")


# ── 範圍閘門：非對稱 ──────────────────────────────────────────────────────

def test_unauthorized_id_aborts_hard():
    """DB 出現卡面沒有的缺 handedness 球員＝未授權擴張，硬中止。"""
    with pytest.raises(SystemExit):
        gap2.check_scope(set(gap2.EXPECTED_GAP_IDS) | {"0000009999"})


def test_unauthorized_id_still_aborts_when_others_completed():
    """已完成者不得稀釋未授權 ID 的中止（GAP1 查核者點名過的方向）。"""
    with pytest.raises(SystemExit):
        gap2.check_scope({"0000009999"})


def test_partial_completion_is_progress_not_failure():
    """斷路器中止後冷卻續跑：剩下的人數必然少於 14，不得因此 ABORT。"""
    remaining = set(list(gap2.EXPECTED_GAP_IDS)[:9])
    done = gap2.check_scope(remaining)
    assert done == set(gap2.EXPECTED_GAP_IDS) - remaining


def test_full_completion_is_a_successful_noop():
    """全部補完後重跑是成功的 no-op，不是失敗（卡面驗收：寫入冪等、可重跑）。"""
    assert gap2.check_scope(set()) == set(gap2.EXPECTED_GAP_IDS)


# ── 名單本身 ──────────────────────────────────────────────────────────────

def test_expected_ids_are_exactly_the_fourteen_from_spec_v2():
    assert len(gap2.EXPECTED_GAP_IDS) == 14
    assert len(gap2.BATCH1_IDS) == 6
    assert len(gap2.BATCH2_IDS) == 8
    assert not set(gap2.BATCH1_IDS) & set(gap2.BATCH2_IDS)
