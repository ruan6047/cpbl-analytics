"""連續無自責分出賽的取數層契約（需本機 DB 的項目在無 DB 時 skip）。

純函式的保守性紅線在 `tests/test_scoreless_streak.py`；本檔釘取數層（`cpbl.api.scoreless`）：
真實資料上的 R1 抽驗、載入層的 NULL 處理、輸入指紋與漂移分類。
兩支對外端點（`/api/v1/records/earned-run-free-streak`、`/run-free-streak`）已於 #443 下線，
只打端點的 payload 契約測試隨之移除；取數層由對帳／比較腳本沿用。
"""

from __future__ import annotations

import pytest

PATH = "/api/v1/records/earned-run-free-streak"


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
# ML-PITCHER-SCORELESS-CLAIM1：兩個口徑的主指標語意（Basis 純值；端點已於 #443 下線，
# 路徑只作為口徑標籤沿用）
# --------------------------------------------------------------------------

RUN_PATH = "/api/v1/records/run-free-streak"

# `build_item` 的 item key 集合（對帳／比較腳本的 artifact item 仍是這個形狀）；下方
# `test_every_artifact_item_key_is_traceable_to_a_digested_input` 以它判斷欄位來源分類。
FROZEN_ITEM_KEYS = {
    "player_id", "player_name", "team_code", "outs", "innings", "strict_outs",
    "strict_innings", "basis", "strict_basis", "appearances_counted",
    "tail_suffix_from_inning", "tail_reason", "tail_outs", "start", "through",
    "last_appearance", "boundary_limited", "boundary_note", "break_reason",
    "break_game", "skipped_postseason_appearances", "skipped_postseason_games",
}

# ML-PITCHER-SCORELESS-CLAIM1 前的公開主指標。這次沒有增減 key，卻把兩支已存在端點
# 從「局數下界」改成「零推論出賽數」；因此相容性破壞在值語意，不可被 key 集合不變掩蓋。
PRE_CLAIM_METRICS = {
    PATH: "consecutive_earned_run_free_innings",
    RUN_PATH: "consecutive_run_free_innings",
}
CLAIM_METRICS = {
    PATH: "consecutive_earned_run_free_appearances",
    RUN_PATH: "consecutive_run_free_appearances",
}


def test_claim_changes_only_declared_metric_semantics_for_both_bases():
    """這是刻意的相容性破壞：主值改為出賽，payload key 形狀則維持不變。"""
    from cpbl.models.scoreless_streak import EARNED_RUN_BASIS, RUN_BASIS

    actual = {PATH: EARNED_RUN_BASIS.metric, RUN_PATH: RUN_BASIS.metric}
    changed = {path: (PRE_CLAIM_METRICS[path], value)
               for path, value in actual.items() if value != PRE_CLAIM_METRICS[path]}

    assert changed == {path: (PRE_CLAIM_METRICS[path], CLAIM_METRICS[path])
                       for path in (PATH, RUN_PATH)}
    assert EARNED_RUN_BASIS.metric_label == "連續無自責分出賽"
    assert RUN_BASIS.metric_label == "連續無失分出賽"
    assert "零推論" in EARNED_RUN_BASIS.metric_note
    assert "零推論" in RUN_BASIS.metric_note


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


# --------------------------------------------------------------------------
# iteration 4：指紋涵蓋範圍必須由型別導出，不得靠手工列欄位
#
# R2 抓到的洞：iteration 3 的 `_appearance_digest` 手寫 12 個欄位、漏了 `opponent`，
# 而 `opponent` 會寫進 COMPARE_*.json——只把對手由甲隊改成乙隊，指紋不動，於是
# 「不同的輸入 ＋ 不同的 artifact」被判成 identical。
#
# **補上 opponent 不算修好**：下一個人往 `Appearance` 加欄位，同一個洞會再開一次。
# 下面這組測試的重點是**它們自己也走 `dataclasses.fields()` 迴圈**——守衛與被守衛的
# 東西共用同一個來源，所以新增欄位時：欄位自動進指紋；若沒進，測試自己就會失敗。
# --------------------------------------------------------------------------

def _full_appearance():
    """每個欄位都有值的 `Appearance`——欄位全滿才能逐欄位做變異檢驗。

    新增欄位而沒在這裡給值時，下面的斷言會失敗並指名該欄位，逼作者回來補；
    這是刻意的 fail-closed，不是維護負擔。
    """
    import dataclasses
    from datetime import date

    from cpbl.models.scoreless_streak import Appearance

    a = Appearance(year=2026, kind_code="A", game_sno=5, game_date=date(2026, 5, 1),
                   earned_runs=1, outs=9, delay_kind="延賽", opponent="味全龍",
                   team_code="AJL011", vht="2", opponent_score=3, runs=2)
    missing = [f.name for f in dataclasses.fields(Appearance)
               if getattr(a, f.name) is None]
    assert not missing, (
        f"`Appearance` 新增了欄位但這個 fixture 沒給值：{missing}。"
        "欄位全滿才能逐欄位變異，請補上再跑。")
    return a


def _mutated(value):
    """給一個與原值必不相同的同型值。未知型別直接失敗——不要靜默跳過某個欄位。"""
    from datetime import date, timedelta

    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, date):
        return value + timedelta(days=1)
    if isinstance(value, str):
        return value + "_X"
    raise AssertionError(f"未知型別 {type(value)!r}，請在 `_mutated` 補一個變異規則，"
                         "否則該欄位的指紋涵蓋就沒有被真正驗過")


def _appearance_field_names():
    import dataclasses

    from cpbl.models.scoreless_streak import Appearance

    return [f.name for f in dataclasses.fields(Appearance)]


@pytest.mark.parametrize("field_name", _appearance_field_names())
def test_every_appearance_field_moves_the_digest(field_name):
    """**逐欄位變異**：`Appearance` 的每一個欄位改值，指紋都必須跟著變。

    參數化的清單來自 `dataclasses.fields(Appearance)`，所以**新增欄位會自動被測到**
    ——這就是「指紋涵蓋範圍不再依賴任何人記得更新」的可執行形式。若有人加了欄位卻沒
    讓它進指紋，這條會以該欄位名失敗。

    `opponent` 是 R2 的原案：它在 iteration 3 被漏掉，這裡不特別對待，因為特別對待
    正是上一版的做法。
    """
    import dataclasses

    from cpbl.api.scoreless import _appearance_digest

    base = _full_appearance()
    changed = dataclasses.replace(
        base, **{field_name: _mutated(getattr(base, field_name))})

    assert _appearance_digest({"P1": [base]}) != _appearance_digest({"P1": [changed]}), (
        f"改了 `Appearance.{field_name}` 指紋卻沒變——該欄位不在指紋涵蓋範圍內，"
        "會讓不同的輸入被判成 identical")


def test_opponent_change_is_classified_as_input_drift():
    """R2 的原案，端到端走一次：**只改對手隊名** → 必須判 `input_drift`，不是 identical。

    查核者的變異就是這個：把對手由甲隊改成乙隊，artifact 的 `opponent` 欄跟著變，
    指紋若不動，歸因就會漏報。
    """
    import dataclasses

    from cpbl.api import scoreless
    from cpbl.api.scoreless import DRIFT_INPUT, classify_artifact_drift

    base = _full_appearance()
    other = dataclasses.replace(base, opponent="統一7-ELEVEn獅")
    fake_board = {"rows_total": 1, "digest": "same-board"}

    def fp(app):
        return scoreless.population_fingerprint({"P1": [app]}, ["A"], names={"P1": "某投手"})

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(scoreless, "_fetch_scoreboard_digest",
                   lambda kinds, cutoff=None: fake_board)
        before = {"fingerprint": fp(base), "rows": 1}
        after = {"fingerprint": fp(other), "rows": 1}

    got = classify_artifact_drift(before, after, ("rows",))

    assert got["verdict"] == DRIFT_INPUT
    assert got["digest_changed"]["appearance"] is True
    assert got["digest_changed"]["scoreboard"] is False


def test_player_name_change_is_classified_as_input_drift():
    """`player_name` 不參與演算法，但**會寫進 artifact**，改名同樣必須判 `input_drift`。

    players.name 會被每日 gamelog 同步覆寫（記憶 `player-name-authority`），所以這不是
    假想情境。凡是會改變 artifact 的輸入都要有自己的 digest。
    """
    from cpbl.api import scoreless
    from cpbl.api.scoreless import DRIFT_INPUT, classify_artifact_drift

    app = _full_appearance()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(scoreless, "_fetch_scoreboard_digest",
                   lambda kinds, cutoff=None: {"rows_total": 1, "digest": "same"})
        before = {"fingerprint": scoreless.population_fingerprint(
            {"P1": [app]}, ["A"], names={"P1": "舊名"}), "rows": 1}
        after = {"fingerprint": scoreless.population_fingerprint(
            {"P1": [app]}, ["A"], names={"P1": "新名"}), "rows": 1}

    got = classify_artifact_drift(before, after, ("rows",))

    assert got["verdict"] == DRIFT_INPUT
    assert got["digest_changed"] == {"appearance": False, "name": True, "scoreboard": False}


def test_classifier_compares_every_digest_key_not_a_hardcoded_pair():
    """新增一條輸入通道（多一個 `*_digest`）必須**自動**納入比對，不必改分類器。

    iteration 3 的分類器寫死比對 `appearance_digest` 與 `scoreboard_digest` 兩個名字，
    那和手寫欄位清單是同一種病。現在取兩邊 fingerprint 中所有 `_digest` 結尾的鍵聯集。
    """
    from cpbl.api.scoreless import DRIFT_INPUT, classify_artifact_drift

    before = {"fingerprint": {"future_source_digest": "a"}, "rows": 1}
    after = {"fingerprint": {"future_source_digest": "b"}, "rows": 1}

    got = classify_artifact_drift(before, after, ("rows",))

    assert got["verdict"] == DRIFT_INPUT
    assert got["digest_changed"] == {"future_source": True}


def test_a_missing_digest_key_in_an_old_artifact_is_not_read_as_identical():
    """舊 artifact 少了某個 digest 鍵 ⇒ **無法證明輸入相同** ⇒ 偏 `input_drift`。

    偏向 `identical` 才是危險的那一邊：它會讓「新加了一條輸入通道」的第一次比對靜默通過。
    """
    from cpbl.api.scoreless import DRIFT_INPUT, classify_artifact_drift

    before = {"fingerprint": {"appearance_digest": "a"}, "rows": 1}
    after = {"fingerprint": {"appearance_digest": "a", "name_digest": "n"}, "rows": 1}

    got = classify_artifact_drift(before, after, ("rows",))

    assert got["verdict"] == DRIFT_INPUT
    assert got["digest_changed"] == {"appearance": False, "name": True}


# artifact 的 item 欄位裡，**不是**直接來自輸入的那些（由演算法算出或由常數文案組成）。
# 這份清單是**fail-closed 的提示**，不是涵蓋範圍的證明：下面那條測試會在出現任何未分類
# 的新欄位時失敗，逼加欄位的人回答「這個值從哪來、那個來源在指紋裡嗎」。
_DERIVED_ITEM_KEYS = {
    "innings", "strict_outs", "strict_innings", "basis", "strict_basis",
    "appearances_counted", "tail_suffix_from_inning", "tail_reason", "tail_outs",
    "start", "through", "last_appearance", "boundary_limited", "boundary_note",
    "break_reason", "break_game", "skipped_postseason_appearances",
    "skipped_postseason_games",
}


def test_every_artifact_item_key_is_traceable_to_a_digested_input():
    """artifact 的每個 item 欄位都要能追到**指紋涵蓋的**輸入，否則測試失敗。

    這是防「有人新增一個 artifact 欄位、其來源不在任何 digest 裡」的守衛——那正是本輪
    `opponent` 事件的一般形。分三類：`Appearance` 欄位（走 `appearance_digest`，隨型別
    自動長）、`player_name`（走 `name_digest`）、演算法算出的衍生值（`_DERIVED_ITEM_KEYS`）。

    **這條測試不宣稱涵蓋完整**——它宣稱的是「未分類的欄位不會靜默通過」。
    """
    fields = set(_appearance_field_names())
    unclassified = (FROZEN_ITEM_KEYS - fields - _DERIVED_ITEM_KEYS
                    - {"player_id", "player_name"})

    assert not unclassified, (
        f"artifact item 出現未分類的欄位：{sorted(unclassified)}。"
        "請確認它的來源在某個 *_digest 涵蓋範圍內；若是演算法算出的衍生值，"
        "加進 `_DERIVED_ITEM_KEYS` 並在該處說明來源。")
