"""INGEST-GAME-TM-REFACTOR1-G4 Phase A：逐球抓取維度切換的離線測試（無 DB、無網路）。

覆蓋卡面〈驗證〉第一項：
- `CPBL_PITCH_INGEST` 兩條路徑（`game` 預設／`pitcher` 回退）皆可運作且互斥呼叫。
- `_lagging_pitch_games()` 的設備過濾與「與當日窗取聯集後**單次**送出」（不得成為第二條路徑）。
- 孤兒列（`only_prod_pk`）偵測。
- 單場 API 回空時不清空既有列。

CI 無真實 Postgres，故一律 monkeypatch `conn`／被呼叫函式（比照 tests/test_refresh_pa_daily.py）。
"""

from __future__ import annotations

import importlib.util
from contextlib import contextmanager
from pathlib import Path

import pytest
from pydantic import ValidationError

from cpbl.config import Settings
from cpbl.ingest import cpbl_pitch_tracking as pt
from cpbl.ingest import run_refresh_recent as rr

_DRYRUN_PATH = Path(__file__).parents[1] / "scripts" / "dryrun_game_tm_fullseason.py"
_SPEC = importlib.util.spec_from_file_location("dryrun_game_tm_fullseason", _DRYRUN_PATH)
assert _SPEC and _SPEC.loader
dryrun = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(dryrun)


class _FakeCursor:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows
        self.sql: str | None = None
        self.params: tuple | None = None

    def execute(self, sql: str, params: tuple | None = None) -> _FakeCursor:
        self.sql = sql
        self.params = params
        return self

    def fetchall(self) -> list[tuple]:
        return self._rows


def _fake_conn(rows: list[tuple]):
    cur = _FakeCursor(rows)

    class _C:
        def execute(self, sql, params=None):
            return cur.execute(sql, params)

    @contextmanager
    def factory():
        yield _C()

    return factory, cur


# ---------------------------------------------------------------------------
# CPBL_PITCH_INGEST：兩條路徑
# ---------------------------------------------------------------------------
def _spy(monkeypatch: pytest.MonkeyPatch) -> dict:
    calls: dict = {"game": [], "pitcher": []}

    def fake_game(games, delay=1.0):
        calls["game"].append({"games": list(games), "delay": delay})
        return {"games": len(games), "pitches": 7}

    def fake_pitcher(acnts, year=None, kind_code="A", delay=1.0):
        calls["pitcher"].append({"acnts": list(acnts), "kind_code": kind_code})
        return {"pitchers": len(acnts), "pitches": 5}

    monkeypatch.setattr(rr, "scrape_game_pitches", fake_game)
    monkeypatch.setattr(rr, "scrape_pitches", fake_pitcher)
    return calls


def test_game_mode_sends_day_window_union_lagging_in_one_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """預設 game 路徑：當日窗 ∪ 落後場，去重排序後**單次**送進 scrape_game_pitches。"""
    calls = _spy(monkeypatch)
    monkeypatch.setattr(rr.settings, "pitch_ingest", "game")
    monkeypatch.setattr(rr, "_lagging_pitch_games", lambda y, k: {51, 50})
    out = rr._refresh_pitches(2026, "A", [51, 52], ["p1"], delay=0.1)

    assert len(calls["game"]) == 1, "不得成為第二條抓取路徑：只能呼叫一次"
    assert calls["game"][0]["games"] == [(2026, "A", 50), (2026, "A", 51), (2026, "A", 52)]
    assert calls["pitcher"] == []           # 互斥：game 模式不得走 logs
    assert out["mode"] == "game" and out["lagging_games"] == 2


def test_pitcher_mode_falls_back_to_logs_with_same_lagging_criterion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """回退路徑：落後**場**經 `_pitchers_of_games` 映射回投手，不另立一套設備判準。"""
    calls = _spy(monkeypatch)
    monkeypatch.setattr(rr.settings, "pitch_ingest", "pitcher")
    monkeypatch.setattr(rr, "_lagging_pitch_games", lambda y, k: {77})
    monkeypatch.setattr(rr, "_pitchers_of_games", lambda y, k, s: {"p9"})
    out = rr._refresh_pitches(2026, "D", [10], ["p1"], delay=0.1)

    assert len(calls["pitcher"]) == 1
    assert calls["pitcher"][0]["acnts"] == ["p1", "p9"]
    assert calls["pitcher"][0]["kind_code"] == "D"
    assert calls["game"] == []              # 互斥：pitcher 模式不得走單場 API
    assert out["mode"] == "pitcher"


def test_no_targets_makes_no_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """當日窗與落後場皆空 → 不發任何請求（兩條路徑皆然）。"""
    calls = _spy(monkeypatch)
    monkeypatch.setattr(rr, "_lagging_pitch_games", lambda y, k: set())
    for mode in ("game", "pitcher"):
        monkeypatch.setattr(rr.settings, "pitch_ingest", mode)
        monkeypatch.setattr(rr, "_pitchers_of_games", lambda y, k, s: set())
        out = rr._refresh_pitches(2026, "A", [], [], delay=0.1)
        assert out["pitches"] == 0
    assert calls["game"] == [] and calls["pitcher"] == []


def test_config_flag_default_env_and_fail_loud() -> None:
    """預設 game；env `CPBL_PITCH_INGEST` 可切 pitcher；打錯值必須 fail loud（不得靜默落回預設）。"""
    assert Settings(_env_file=None).pitch_ingest == "game"
    assert Settings(_env_file=None, CPBL_PITCH_INGEST="pitcher").pitch_ingest == "pitcher"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, CPBL_PITCH_INGEST="pichter")


# ---------------------------------------------------------------------------
# _lagging_pitch_games：判準常數與輸出維度
# ---------------------------------------------------------------------------
def test_lagging_games_pins_operational_policy_constants(monkeypatch: pytest.MonkeyPatch) -> None:
    """紅線 4：窗口 10／門檻 0.80 是需求方裁定的營運政策，不得被靜默改動。

    此測試刻意檢查 SQL 字面：這兩個常數若被改掉，回歸測試必須紅，而不是等到
    生產行為變了才發現。修訂須先有需求方 event，屆時連同本測試一起改。
    """
    factory, cur = _fake_conn([(101,), (102,)])
    monkeypatch.setattr(rr, "conn", factory)
    out = rr._lagging_pitch_games(2026, "A")

    assert out == {101, 102}, "輸出必須是 game_sno 集合（場次維度）"
    sql = cur.sql or ""
    assert "rn<=10" in sql.replace(" ", ""), "設備判準窗口必須是最近 10 場"
    assert "pitches>=50andtracked>=pitches*0.80" in sql.lower().replace(" ", "")
    assert "row_number() over (partition by venue" in sql.lower(), "須為近期感知（每球場排序取近 N 場）"
    assert "distinct venue" not in sql.lower(), "不得退回『本季曾達』的舊判準"


def test_lagging_games_does_not_hardcode_venue_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """卡面明禁硬編場館名單：判準必須是資料推導的。"""
    factory, cur = _fake_conn([])
    monkeypatch.setattr(rr, "conn", factory)
    rr._lagging_pitch_games(2026, "D")
    for name in ("大巨蛋", "亞太主", "花蓮", "嘉義市", "台東"):
        assert name not in (cur.sql or "")


# ---------------------------------------------------------------------------
# 單場 API 回空 → 不得清空既有列
# ---------------------------------------------------------------------------
def test_empty_livelog_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """單場 API 回空（未開打／無 LiveLog）時完全不碰 DB——UPSERT 語意下沉默略過，不清列。"""
    def boom():
        raise AssertionError("回空時不得開啟 DB 連線")

    monkeypatch.setattr(pt, "conn", boom)
    monkeypatch.setattr(pt, "_fetch_game_livelog", lambda c, y, k, s: [])
    monkeypatch.setattr(pt.time, "sleep", lambda s: None)
    out = pt.scrape_game_pitches([(2026, "A", 1)], delay=0)
    assert out == {"games": 1, "pitches": 0}


def test_ingest_module_has_no_delete_statement() -> None:
    """紅線 3：本卡不授權任何 DELETE，增量與全季重跑一律純 UPSERT。"""
    src = Path(pt.__file__).read_text()
    assert "DELETE" not in src.upper()


# ---------------------------------------------------------------------------
# dry-run 純函式：去重語意、孤兒列偵測、float4 容差
# ---------------------------------------------------------------------------
def _rec(pitch_cnt: int, **over) -> tuple:
    d = dict.fromkeys(dryrun._COL_NAMES)
    d.update({"year": 2026, "kind_code": "A", "game_sno": 9, "pitcher_acnt": "p1",
              "pitch_cnt": pitch_cnt, "content": "壞球。", "rel_speed": 140.0})
    d.update(over)
    return tuple(d[c] for c in dryrun._COL_NAMES)


def test_rows_by_pk_keeps_first_like_upsert() -> None:
    """去重須與 `_upsert` 一致（保留第一筆），否則 dry-run 的『將寫入什麼』與實寫不同。"""
    by_pk, dup = dryrun.rows_by_pk_first_wins([_rec(1, content="第一筆"), _rec(1, content="第二筆")])
    assert dup == 1
    assert by_pk[(2026, "A", 9, "p1", 1)]["content"] == "第一筆"


def test_diff_game_detects_orphan_prod_rows() -> None:
    """孤兒列偵測：正式表有、單場 API 沒有 → only_prod_pk（紅線 3 母體）。"""
    api, _ = dryrun.rows_by_pk_first_wins([_rec(1)])
    prod, _ = dryrun.rows_by_pk_first_wins([_rec(1), _rec(2)])
    d = dryrun.diff_game(api, prod)
    assert d["only_prod_pk"] == [[2026, "A", 9, "p1", 2]]
    assert d["only_api_pk"] == [] and d["cell_mismatches"] == []


def test_diff_game_float4_roundtrip_is_not_a_mismatch() -> None:
    """float4 儲存精度不得被記為差異（Gate 3 踩過的假陽性）。"""
    api, _ = dryrun.rows_by_pk_first_wins([_rec(1, rel_speed=139.83480580608)])
    prod, _ = dryrun.rows_by_pk_first_wins([_rec(1, rel_speed=139.83481)])
    assert dryrun.diff_game(api, prod)["cell_mismatches"] == []


def test_diff_game_buckets_physical_and_text_separately() -> None:
    """紅線 1（物理，零容忍）與紅線 2（文字，須逐筆歸因）必須分桶，不得混為一談。"""
    api, _ = dryrun.rows_by_pk_first_wins([_rec(1, rel_speed=120.0, content="擊出界外球。")])
    prod, _ = dryrun.rows_by_pk_first_wins([_rec(1, rel_speed=140.0, content="壞球。")])
    buckets = sorted(c["bucket"] for c in dryrun.diff_game(api, prod)["cell_mismatches"])
    assert buckets == ["physical", "text"]
