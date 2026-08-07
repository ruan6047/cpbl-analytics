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

    try:
        by_player, _ = load_appearances(["A", "E", "C"])
    except Exception as exc:  # noqa: BLE001 — 無 DB 時跳過（CI 無 Postgres）
        pytest.skip(f"需本機 DB：{exc}")
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


class _FakeCursor:
    """最小的 DB cursor 替身：`_dicts()` 只用到 `description` 與 `fetchall()`。"""

    def __init__(self, cols, rows):
        self.description = [(c,) for c in cols]
        self._rows = rows

    def execute(self, *_args, **_kwargs):
        return None

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def _patch_conn(monkeypatch, cols, rows):
    from contextlib import contextmanager

    from cpbl.api import scoreless

    @contextmanager
    def fake_conn():
        yield _FakeConn(_FakeCursor(cols, rows))

    monkeypatch.setattr(scoreless, "conn", fake_conn)


def test_loader_preserves_null_inning_scores(monkeypatch):
    """**F-NULL 迴歸（iteration 9／11）**：載入層不得把 `score_cnt` 的 NULL 折成 0。

    NULL 的意思是「這一局得幾分**不知道**」，不是「這一局 0 分」。折成 0 之後，當官方
    終場得分恰為 0 時總和對帳會以 `0 == 0` 通過，缺值的局被當成零得分而採計。

    **測行為，不測原始碼長什麼樣**：以假 cursor 實際跑 `load_opponent_runs()`。
    iteration 10 的版本用 `inspect.getsource()` 搜字串，那種寫法既擋不住
    `value if value is not None else 0`（照樣通過），又會被純重構打掛（抽出 mapper 後
    字串就不在該函式裡了）——**它驗的是標記，不是性質**。
    """
    from cpbl.api.scoreless import load_opponent_runs

    cols = ["year", "kind_code", "game_sno", "vht", "inning_seq", "runs"]
    rows = [(2026, "A", 1, "1", 1, None), (2026, "A", 1, "1", 2, 0),
            (2026, "A", 1, "1", 3, 0)]
    _patch_conn(monkeypatch, cols, rows)

    got = load_opponent_runs([(2026, "A", 1)])

    assert got[(2026, "A", 1)]["1"] == {1: None, 2: 0, 3: 0}


def test_loader_to_tail_null_inning_fails_closed(monkeypatch):
    """載入層 → factory 全串接：官方終場對手 0 分（`0 == 0` 會放行的那一格）時仍須歸零。"""
    from cpbl.api.scoreless import load_opponent_runs, tail_lookup_factory
    from cpbl.models.scoreless_streak import Appearance

    cols = ["year", "kind_code", "game_sno", "vht", "inning_seq", "runs"]
    app = Appearance(year=2026, kind_code="A", game_sno=1, game_date=None,
                     earned_runs=1, outs=9, vht="2", opponent_score=0)

    _patch_conn(monkeypatch, cols, [(2026, "A", 1, "1", i, 0) for i in (1, 2, 3)])
    clean = tail_lookup_factory(load_opponent_runs([(2026, "A", 1)]))(app)

    _patch_conn(monkeypatch, cols,
                [(2026, "A", 1, "1", 1, None), (2026, "A", 1, "1", 2, 0),
                 (2026, "A", 1, "1", 3, 0)])
    with_null = tail_lookup_factory(load_opponent_runs([(2026, "A", 1)]))(app)

    assert clean.outs == 9                       # 全部已知且零得分 → 可採計
    assert with_null.outs == 0                   # 有一局未知 → fail-closed
    assert with_null.reason == "scoreboard_has_null_inning"


def test_row_mapper_keeps_none_for_every_null_row():
    """邊界轉換本身：任何一列 `runs=None` 都必須原樣保留。"""
    from cpbl.api.scoreless import map_opponent_runs

    rows = [{"year": 2026, "kind_code": "A", "game_sno": 1, "vht": "2",
             "inning_seq": i, "runs": None if i == 2 else i} for i in (1, 2, 3)]

    got = map_opponent_runs(rows)

    assert got[(2026, "A", 1)]["2"] == {1: 1, 2: None, 3: 3}


# --------------------------------------------------------------------------
# ML-PITCHER-RUNLESS1：失分口徑端點 ＋ 既有端點的「不得改變」守衛
# --------------------------------------------------------------------------

RUN_PATH = "/api/v1/records/run-free-streak"

# 自責分口徑 payload 的**凍結 key 集合**（ML-PITCHER-RUNLESS1 之前的形狀）。
# 卡面驗證明文「既有 earned-run-free-streak 端點行為不得改變（除非裁決為取代）」——
# 加一個 key 也是改變。這份清單把那條紅線變成可執行的斷言，而不是交付文件裡的一句話。
# 需求方裁決為「取代」或同意回填新欄位時，連同這份清單一起改，不得只改實作。
FROZEN_ER_TOP_LEVEL_KEYS = {
    "metric", "metric_label", "note", "season", "kind_code", "kinds_counted",
    "kinds_in_scope", "scope_note", "tail_basis_note", "team", "data_from_year",
    "as_of", "items",
}
FROZEN_ER_ITEM_KEYS = {
    "player_id", "player_name", "team_code", "outs", "innings", "strict_outs",
    "strict_innings", "basis", "strict_basis", "appearances_counted",
    "tail_suffix_from_inning", "tail_reason", "tail_outs", "start", "through",
    "last_appearance", "boundary_limited", "boundary_note", "break_reason",
    "break_game", "skipped_postseason_appearances", "skipped_postseason_games",
}


def test_earned_run_payload_shape_is_frozen():
    """**既有端點不得改變**：頂層與 item 的 key 集合必須與凍結清單完全相同。

    只驗「沒有少 key」不夠——本卡新增的兩個揭露欄位如果不小心也掛到自責分口徑上，
    那就是在需求方裁決之前擅自改了已上線端點的契約。故兩個方向都驗。
    """
    d = _get(f"{PATH}?limit=5")

    assert set(d) == FROZEN_ER_TOP_LEVEL_KEYS
    for i in d["items"]:
        assert set(i) == FROZEN_ER_ITEM_KEYS


def test_run_free_metric_wording_says_run_not_earned_run():
    """**紅線 5 的鏡像**：失分口徑的文案必須明講它不是「無自責分」。"""
    d = _get(f"{RUN_PATH}?limit=5")

    assert d["metric"] == "consecutive_run_free_innings"
    assert "無失分" in d["metric_label"]
    assert "失分" in d["note"] and "自責" in d["note"]      # 明講兩者不同
    assert d["basis_field"] == "runs"
    assert d["data_from_year"] == DATA_FROM_YEAR


def test_run_free_payload_discloses_the_lower_bound_limit():
    """誠實揭露：中途登板／退場的下界限制**不因換口徑而消失**，payload 要自己講。"""
    d = _get(f"{RUN_PATH}?limit=1")

    assert "下界" in d["lower_bound_note"]
    assert "換口徑不會" in d["lower_bound_note"] or "無關" in d["lower_bound_note"]


def test_run_free_shares_the_item_shape_with_earned_run():
    """兩支端點的 item 形狀相同，前端可用同一個元件消費（差異只在頂層 metadata）。"""
    er = _get(f"{PATH}?limit=5")
    run = _get(f"{RUN_PATH}?limit=5")
    if not er["items"] or not run["items"]:
        pytest.skip("本季無資料")

    assert set(run["items"][0]) == set(er["items"][0])
    assert set(run) - set(er) == {"basis_field", "lower_bound_note"}


def test_run_free_kind_code_domain_rejects_non_regular_season():
    """值域與自責分口徑同理鎖在例行賽——新端點不得比舊端點鬆。"""
    try:
        from fastapi.testclient import TestClient

        from cpbl.api.main import app

        client = TestClient(app)
        for bad in ("C", "E", "F", "Z", "", "a"):
            assert client.get(f"{RUN_PATH}?kind_code={bad}").status_code == 422, bad
    except AssertionError:
        raise
    except Exception as exc:  # noqa: BLE001 — 無 DB 時跳過
        pytest.skip(f"需本機 DB：{exc}")


def test_every_run_free_counted_appearance_is_officially_run_zero():
    """**紅線 3 的失分版**：宣稱無失分的整場出賽，官方 `runs` 必為 0（真實資料抽驗）。

    全母體窮舉版在 `scripts/reconcile_scoreless_streak.py`（兩個口徑各跑一次 R1–R10）。
    """
    from cpbl.api.scoreless import RUN_BASIS, compute_all, load_appearances

    try:
        by_player, _ = load_appearances(["A", "E", "C"])
    except Exception as exc:  # noqa: BLE001 — 無 DB 時跳過（CI 無 Postgres）
        pytest.skip(f"需本機 DB：{exc}")
    if not by_player:
        pytest.skip("無出賽資料")
    results = compute_all(by_player, ("A",), basis=RUN_BASIS)

    for pid, res in results.items():
        for a in res.counted:
            assert a.runs == 0, f"{pid} {a.key} 官方 runs={a.runs} 卻被採計"
            assert a.kind_code == "A", f"{pid} {a.key} 非例行賽卻被計入局數"
        for a in res.skipped:
            assert a.runs == 0 and a.kind_code != "A"


def test_run_free_streak_never_exceeds_earned_run_free_streak_on_real_data():
    """真實資料上的大小關係（含尾段）——窮舉版是對帳腳本的 X3。

    尾段可能落在**不同的場次**，所以這條不能只靠純函式推；必須在真實資料上比。
    """
    from cpbl.api.scoreless import (
        EARNED_RUN_BASIS,
        RUN_BASIS,
        compute_all,
        load_appearances,
    )

    try:
        by_player, _ = load_appearances(["A", "E", "C"])
    except Exception as exc:  # noqa: BLE001 — 無 DB 時跳過
        pytest.skip(f"需本機 DB：{exc}")
    if not by_player:
        pytest.skip("無出賽資料")

    er = compute_all(by_player, ("A",), basis=EARNED_RUN_BASIS)
    run = compute_all(by_player, ("A",), basis=RUN_BASIS)

    assert set(er) == set(run)
    for pid in er:
        assert run[pid].outs <= er[pid].outs, (
            f"{pid} 失分口徑 {run[pid].outs} > 自責分口徑 {er[pid].outs}")
