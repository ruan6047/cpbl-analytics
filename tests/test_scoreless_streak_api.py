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
# ML-PITCHER-RUNLESS1：兩支端點的 payload 形狀凍結（並列裁決後兩支對稱）
# --------------------------------------------------------------------------

RUN_PATH = "/api/v1/records/run-free-streak"

# **兩個口徑共用的凍結 key 集合。**
#
# iteration 1 的版本只凍結自責分口徑，因為當時卡面寫「既有端點行為不得改變」，兩個揭露
# 欄位只掛在失分口徑上。需求方 2026-08-08 裁決為**並列、失分為預設呈現面**，並定案把
# `basis_field`／`lower_bound_note` **回填到自責分端點**——理由是並列的前提就是兩支對外
# 語意對稱。回填**刻意破壞了既有 payload 的相容性**（對做嚴格 key 比對的消費者而言，
# 多一個 key 就是破壞），所以這份清單跟著改；改清單是留痕，不是繞過守衛。
#
# 斷言仍是**雙向**且**兩支都驗**：key 集合必須與清單**完全相等**，少一個或多一個都 fail。
# 未來要動 payload 形狀，必須連同這份清單一起改——不得只改實作讓測試自動跟著鬆。
FROZEN_TOP_LEVEL_KEYS = {
    "metric", "metric_label", "note", "basis_field", "lower_bound_note",
    "season", "kind_code", "kinds_counted", "kinds_in_scope", "scope_note",
    "tail_basis_note", "team", "data_from_year", "as_of", "items",
}
FROZEN_ITEM_KEYS = {
    "player_id", "player_name", "team_code", "outs", "innings", "strict_outs",
    "strict_innings", "basis", "strict_basis", "appearances_counted",
    "tail_suffix_from_inning", "tail_reason", "tail_outs", "start", "through",
    "last_appearance", "boundary_limited", "boundary_note", "break_reason",
    "break_game", "skipped_postseason_appearances", "skipped_postseason_games",
}

# iteration 1 的自責分 payload 形狀（回填前）。留著是為了讓「這次破壞了什麼」可被斷言，
# 而不是只存在於交付文件的敘述裡——差集由測試算出來，不是人工列的。
PRE_BACKFILL_ER_TOP_LEVEL_KEYS = FROZEN_TOP_LEVEL_KEYS - {"basis_field", "lower_bound_note"}


@pytest.mark.parametrize("path", [PATH, RUN_PATH])
def test_payload_shape_is_frozen_for_both_bases(path):
    """**兩支端點**的頂層與 item key 集合都必須與凍結清單完全相同（雙向）。

    只驗「沒有少 key」不夠：多一個 key 對嚴格比對的消費者同樣是破壞，而且會讓兩支
    端點悄悄不對稱——並列裁決要的正是對稱。故兩個方向都驗，且兩支都驗。
    """
    d = _get(f"{path}?limit=5")

    assert set(d) == FROZEN_TOP_LEVEL_KEYS
    for i in d["items"]:
        assert set(i) == FROZEN_ITEM_KEYS


def test_backfill_is_recorded_as_a_deliberate_breaking_change():
    """把「本次刻意破壞自責分端點相容性」釘成斷言，而不是只寫在交付文件裡。

    交付文件會過期、也可能被讀成「向後相容的新增欄位」。這條測試讓破壞的**範圍**
    （恰好兩個 key、且只多不少）可被機器複核：若哪天有人以為可以悄悄再加第三個欄位，
    上面的凍結斷言會擋下來，而這一條說明為什麼那需要另一次裁決。
    """
    d = _get(f"{PATH}?limit=1")
    added = set(d) - PRE_BACKFILL_ER_TOP_LEVEL_KEYS
    removed = PRE_BACKFILL_ER_TOP_LEVEL_KEYS - set(d)

    assert added == {"basis_field", "lower_bound_note"}, "破壞範圍與裁決不符"
    assert removed == set(), "回填不得移除任何既有欄位——那會是第二種破壞"
    assert d["basis_field"] == "earned_runs"


def test_run_free_metric_wording_says_run_not_earned_run():
    """**紅線 5 的鏡像**：失分口徑的文案必須明講它不是「無自責分」。"""
    d = _get(f"{RUN_PATH}?limit=5")

    assert d["metric"] == "consecutive_run_free_innings"
    assert "無失分" in d["metric_label"]
    assert "失分" in d["note"] and "自責" in d["note"]      # 明講兩者不同
    assert d["basis_field"] == "runs"
    assert d["data_from_year"] == DATA_FROM_YEAR


@pytest.mark.parametrize("path", [PATH, RUN_PATH])
def test_payload_discloses_the_lower_bound_limit(path):
    """誠實揭露：中途登板／退場的下界限制**不因換口徑而消失**，兩支 payload 都要自己講。"""
    d = _get(f"{path}?limit=1")

    assert "下界" in d["lower_bound_note"]
    assert "換口徑不會" in d["lower_bound_note"] or "無關" in d["lower_bound_note"]


def test_both_endpoints_are_shape_symmetric():
    """並列裁決的可執行形式：兩支端點的 key 集合**完全相同**，差異只在值。

    回填之前失分口徑多帶兩個揭露欄位，讀者無從判斷自責分那支的判準與下界性質——
    這條斷言把「對稱」釘死，任何一支單方面增減欄位都會 fail。
    """
    er = _get(f"{PATH}?limit=5")
    run = _get(f"{RUN_PATH}?limit=5")
    if not er["items"] or not run["items"]:
        pytest.skip("本季無資料")

    assert set(run) == set(er)                          # 頂層對稱
    assert set(run["items"][0]) == set(er["items"][0])  # item 對稱
    # 對稱的是形狀不是內容：判準欄位與指標名必須不同，否則兩支端點就是同一個東西。
    assert (er["basis_field"], run["basis_field"]) == ("earned_runs", "runs")
    assert er["metric"] != run["metric"]


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


# --------------------------------------------------------------------------
# ML-PITCHER-RUNLESS1 iteration 3：輸入指紋與漂移分類
#
# 背景：本紀錄的母體每天都會長大，所以 artifact 重跑後數字不同是**常態**
# （canonical statistical-redline 第 9 條：標注 as-of、不凍結數字）。守衛要能區分
# 「輸入變了」與「同一份輸入卻算出不同結果」——後者才是缺陷。
# --------------------------------------------------------------------------

def _fp(digest="d1", board="b1", asof="2026-08-07", pitchers=390, appearances=22000,
        rows=77000):
    return {"data_asof": asof, "latest_game_date_any": asof, "pitchers": pitchers,
            "appearances": appearances, "appearance_digest": digest,
            "scoreboard_rows": rows, "scoreboard_digest": board}


def _snapshot(fingerprint, **stats):
    return {"fingerprint": fingerprint, **stats}


def test_drift_without_fingerprint_is_unclassifiable_not_pass():
    """舊格式 artifact（沒有指紋）→ **明講無從分類**，不得靜默當成通過。

    「看起來差不多」是這類守衛最容易退化成的樣子；無從比對就要說無從比對。
    """
    from cpbl.api.scoreless import classify_artifact_drift

    got = classify_artifact_drift({"appearances_total": 1}, _snapshot(_fp()),
                                  ("appearances_total",))

    assert got["verdict"] is None
    assert "fingerprint" in got["reason"]


def test_drift_identical_input_and_output():
    from cpbl.api.scoreless import DRIFT_IDENTICAL, classify_artifact_drift

    snap = _snapshot(_fp(), appearances_total=22000, tail_outs=126)

    got = classify_artifact_drift(snap, snap, ("appearances_total", "tail_outs"))

    assert got["verdict"] == DRIFT_IDENTICAL
    assert got["changed_fields"] == []


def test_input_drift_reports_the_magnitude_and_is_not_a_failure():
    """母體長大：指紋變了 ⇒ `input_drift`，**並報出漂移量**。

    只回一個「不一樣」沒有用——查核者要的是「差多少、差在哪」，才能判斷這是新比賽
    入庫還是別的事。
    """
    from cpbl.api.scoreless import DRIFT_INPUT, classify_artifact_drift

    before = _snapshot(_fp(digest="d1", appearances=22521, pitchers=392),
                       appearances_total=22521, tail_outs=126)
    after = _snapshot(_fp(digest="d2", appearances=22540, pitchers=392,
                          asof="2026-08-08"),
                      appearances_total=22540, tail_outs=156)

    got = classify_artifact_drift(before, after, ("appearances_total", "tail_outs"))

    assert got["verdict"] == DRIFT_INPUT
    assert got["input_delta"]["appearances"]["delta"] == 19
    assert got["input_delta"]["pitchers"]["delta"] == 0
    assert got["digest_changed"] == {"appearance": True, "scoreboard": False}
    assert (got["data_asof_before"], got["data_asof_after"]) == ("2026-08-07", "2026-08-08")
    assert {f["field"]: f["delta"] for f in got["changed_fields"]} == {
        "appearances_total": 19, "tail_outs": 30}


def test_scoreboard_revision_alone_still_counts_as_input_drift():
    """既有場次被修訂（逐局比分變了、出賽列沒變）同樣是輸入變動，不是算錯。"""
    from cpbl.api.scoreless import DRIFT_INPUT, classify_artifact_drift

    before = _snapshot(_fp(board="b1"), tail_outs=126)
    after = _snapshot(_fp(board="b2"), tail_outs=120)

    got = classify_artifact_drift(before, after, ("tail_outs",))

    assert got["verdict"] == DRIFT_INPUT
    assert got["digest_changed"] == {"appearance": False, "scoreboard": True}


def test_same_input_different_output_is_the_only_failure_case():
    """指紋相同、輸出卻不同 ⇒ `mismatch_same_input`——資料面已被排除，這才該紅。"""
    from cpbl.api.scoreless import DRIFT_MISMATCH, classify_artifact_drift

    before = _snapshot(_fp(), tail_outs=126)
    after = _snapshot(_fp(), tail_outs=133)

    got = classify_artifact_drift(before, after, ("tail_outs",))

    assert got["verdict"] == DRIFT_MISMATCH
    assert got["changed_fields"][0]["delta"] == 7


def test_data_asof_excludes_suspended_games_but_the_digest_does_not(monkeypatch):
    """as-of 不得被保留賽的**改期後未來日期**帶著跑，但指紋仍要涵蓋它。

    實例 2026/D/165：`orig_date` 07-17、`game_date` 09-15、比分已記上。直接取
    `max(game_date)` 會把 as-of 標成九月，讀起來像「資料到九月」——那是把排程日期
    誤讀成資料新鮮度。原始最大值仍以 `latest_game_date_any` 揭露，不做沉默捨棄。
    """
    from datetime import date

    from cpbl.api import scoreless
    from cpbl.models.scoreless_streak import SUSPENDED, Appearance

    monkeypatch.setattr(scoreless, "_fetch_scoreboard_digest",
                        lambda kinds, cutoff=None: {"rows_total": 0, "digest": "x"})

    def app(sno, day, delay=None, runs=0):
        return Appearance(year=2026, kind_code="D", game_sno=sno,
                          game_date=date(2026, day[0], day[1]), earned_runs=0,
                          outs=3, delay_kind=delay, runs=runs)

    played, suspended = app(1, (8, 7)), app(165, (9, 15), SUSPENDED, runs=3)
    base = scoreless.population_fingerprint({"P1": [played, suspended]}, ["D"])
    revised = scoreless.population_fingerprint(
        {"P1": [played, app(165, (9, 15), SUSPENDED, runs=4)]}, ["D"])

    assert base["data_asof"] == "2026-08-07"           # 保留賽不參與 as-of
    assert base["latest_game_date_any"] == "2026-09-15"  # 但也不隱藏
    # 只改保留賽那一列的失分，指紋必須跟著變——否則它就不是輸入的完整指紋。
    assert revised["appearance_digest"] != base["appearance_digest"]


def test_digest_does_not_fold_unknown_into_zero():
    """`None` 與 `0` 不得撞出同一個指紋——把未知折成已知會讓兩份不同的輸入看起來相同。"""
    from datetime import date

    from cpbl.api.scoreless import _appearance_digest
    from cpbl.models.scoreless_streak import Appearance

    def app(runs):
        return Appearance(year=2026, kind_code="A", game_sno=1, game_date=date(2026, 5, 1),
                          earned_runs=0, outs=3, runs=runs)

    assert _appearance_digest({"P1": [app(None)]}) != _appearance_digest({"P1": [app(0)]})
