"""連續無自責分局數的 API 契約（需本機 DB；無 DB 時 skip）。

純函式的保守性紅線在 `tests/test_scoreless_streak.py`；本檔只釘 API 對外契約：
名詞（紅線 5）、下界關係、資料邊界標示（紅線 4），以及真實資料上的 R1 抽驗。
"""

from __future__ import annotations

import pytest

from cpbl.models.scoreless_streak import DATA_FROM_YEAR

PATH = "/api/v1/records/earned-run-free-streak"


def _get(path: str):
    try:
        from fastapi.testclient import TestClient

        from cpbl.api.main import app

        r = TestClient(app).get(path)
    except Exception as exc:  # noqa: BLE001 — 無 DB 時跳過（CI 無 Postgres）
        pytest.skip(f"需本機 DB：{exc}")
    if r.status_code != 200:
        pytest.skip(f"需本機 DB（{r.status_code}）")
    return r.json()


def test_metric_wording_says_earned_run():
    """**紅線 5**：對外文案必須明確是「無自責分」，不可被讀成「無失分」。"""
    d = _get(f"{PATH}?limit=5")

    assert "自責" in d["metric_label"]
    assert "自責" in d["note"] and "無失分" in d["note"]      # 明講兩者不同
    assert d["metric"] == "consecutive_earned_run_free_innings"
    assert d["data_from_year"] == DATA_FROM_YEAR


def test_extended_is_never_below_strict():
    """`outs` 是 `strict_outs` 加上尾段，兩者都是下界，前者不得小於後者。"""
    d = _get(f"{PATH}?limit=25")
    if not d["items"]:
        pytest.skip("本季無資料")

    for i in d["items"]:
        assert i["outs"] >= i["strict_outs"] >= 0
        assert i["outs"] == i["strict_outs"] + i["tail_outs"]


def test_every_counted_appearance_is_officially_er_zero():
    """**紅線 3**：宣稱無自責分的整場出賽，官方 ER 必為 0（真實資料抽驗）。

    全母體窮舉版在 `scripts/reconcile_scoreless_streak.py`，本測試只做輕量守門，
    讓 pytest 迴圈也會踩到這條線。
    """
    from cpbl.api.scoreless import compute_all, load_appearances

    by_player, _ = load_appearances(["A", "E", "C"])
    if not by_player:
        pytest.skip("無出賽資料")
    results = compute_all(by_player, ("A",))

    for pid, res in results.items():
        for a in res.counted:
            assert a.earned_runs == 0, f"{pid} {a.key} 官方 ER={a.earned_runs} 卻被採計"
            assert a.kind_code == "A", f"{pid} {a.key} 非例行賽卻被計入局數"
        for a in res.skipped:
            assert a.earned_runs == 0 and a.kind_code != "A"


def test_kind_code_domain_rejects_non_regular_season():
    """**F2 迴歸**：`kind_code` 值域必須鎖在例行賽。

    放行任意值時 payload 會自打嘴巴——帶 `C` 會產生 `kinds_counted=['C']` 而
    `scope_note` 仍宣稱「只計例行賽」，回傳資料與自身宣稱矛盾；不存在的代碼（`Z`）
    更會靜默回空榜。契約層擋掉，而不是靠呼叫端自律。
    """
    try:
        from fastapi.testclient import TestClient

        from cpbl.api.main import app

        client = TestClient(app)
        for bad in ("C", "E", "F", "Z", "", "a"):
            assert client.get(f"{PATH}?kind_code={bad}").status_code == 422, bad
        for good in ("A", "D"):
            assert client.get(f"{PATH}?kind_code={good}&limit=1").status_code in (200, 500), good
    except AssertionError:
        raise
    except Exception as exc:  # noqa: BLE001 — 無 DB 時跳過
        pytest.skip(f"需本機 DB：{exc}")


def test_scope_is_regular_season_only():
    """需求方裁定：只計例行賽局數；季後賽仍在載入範圍內（乾淨跳過、掉分中斷）。"""
    d = _get(f"{PATH}?limit=5")

    assert d["kinds_counted"] == ["A"]
    assert set(d["kinds_in_scope"]) >= {"A", "E", "C"}
    assert "例行賽" in d["scope_note"] and "季後賽" in d["scope_note"]
    for i in d["items"]:
        assert i["skipped_postseason_appearances"] == len(i["skipped_postseason_games"])


def test_boundary_note_present_exactly_when_limited():
    """**紅線 4**：受 2018 資料邊界限制時必須明說，不得沉默截斷。"""
    d = _get(f"{PATH}?limit=25")

    for i in d["items"]:
        assert (i["boundary_note"] is not None) == i["boundary_limited"]


def test_single_player_lookup():
    d = _get(f"{PATH}?limit=1")
    if not d["items"]:
        pytest.skip("本季無資料")
    pid = d["items"][0]["player_id"]

    one = _get(f"{PATH}?player_id={pid}")

    assert len(one["items"]) == 1
    assert one["items"][0]["player_id"] == pid
    assert one["items"][0]["outs"] == d["items"][0]["outs"]


def test_loader_preserves_null_inning_scores():
    """**F-NULL 迴歸（iteration 9）**：載入層不得把 `score_cnt` 的 NULL 折成 0。

    `game_scoreboard.score_cnt` 允許 NULL，ingest 遇來源缺值就寫 NULL。NULL 的意思是
    「這一局得幾分**不知道**」，不是「這一局 0 分」。折成 0 之後，當官方終場得分恰為 0
    時總和對帳會以 `0 == 0` 通過，缺值的局被當成零得分而採計＝**把未知當成已知**。

    **這一條必須測在載入層**：只測 `pigeonhole_tail_outs()` 抓不到轉換錯誤——純函式是
    對的，bug 在餵它的那個邊界。
    """
    import inspect

    from cpbl.api import scoreless

    src = inspect.getsource(scoreless.load_opponent_runs)
    assert 'r["runs"] or 0' not in src and "runs or 0" not in src, (
        "載入層不得把 NULL 正規化為 0")
    assert "None if runs is None" in src


def test_tail_lookup_fails_closed_on_null_inning_score():
    """factory 層：逐局比分含 NULL 時，尾段必須歸零而不是採計。

    情境刻意設成「官方終場對手得 0 分」——正是總和對帳 `0 == 0` 會放行的那一格。
    """
    from cpbl.api.scoreless import tail_lookup_factory
    from cpbl.models.scoreless_streak import Appearance

    key = (2026, "A", 1)
    app = Appearance(year=2026, kind_code="A", game_sno=1, game_date=None,
                     earned_runs=1, outs=9, vht="2", opponent_score=0)

    clean = tail_lookup_factory({key: {"1": {1: 0, 2: 0, 3: 0}}})(app)
    with_null = tail_lookup_factory({key: {"1": {1: None, 2: 0, 3: 0}}})(app)

    assert clean.outs == 9                       # 全部已知且零得分 → 可採計
    assert with_null.outs == 0                   # 有一局未知 → fail-closed
    assert with_null.reason == "scoreboard_has_null_inning"
