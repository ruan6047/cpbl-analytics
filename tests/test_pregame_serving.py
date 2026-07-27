"""賽前模型 serving 狀態與 artifact 晉升順序（ML-OUTCOME-SIMPLE-LEAK2 紅線 4／5）。

兩件事必須成立：
1. serving artifact 與 `model_versions` 對不上時，後端**明確回報** `serving_previous`，
   而不是只寫 log 讓前端照顯上一版模型的機率。
2. artifact 晉升是「先驗證暫存檔、再原子換名、最後才寫 DB」；中途失敗時 serving 不得
   被換成半成品，DB 也不得已經宣稱這一版可部署。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cpbl.api import pregame_serving
from cpbl.models import run_train_outcome_simple as trainer


class _FakeModel:
    def __init__(self, marker: str = "ok") -> None:
        self.marker = marker

    def predict(self, rows):  # noqa: ANN001, ANN201 - 測試替身
        return [0.5 for _ in rows]


def _artifact(version: str | None) -> dict:
    payload = {"gate": {"deployable": True}, "trained_through": 2025,
               "signals": {"strength": "prior_winpct_diff"}, "model": _FakeModel(),
               "ensemble": []}
    if version is not None:
        payload["version"] = version
    return payload


def _patch(monkeypatch, artifact: dict | None, latest: tuple[str | None, bool | None],
           *, exists: bool = True, load_raises: bool = False) -> None:
    monkeypatch.setattr(pregame_serving, "artifact_path", lambda: Path("/fake/a.joblib"))
    monkeypatch.setattr(Path, "exists", lambda self: exists)
    monkeypatch.setattr(pregame_serving, "_latest_backtest", lambda: latest)

    def _load(_path):
        if load_raises:
            raise ValueError("corrupt")
        return artifact

    monkeypatch.setattr(pregame_serving, "load_artifact", _load)


def test_matching_versions_report_serving_current(monkeypatch):
    _patch(monkeypatch, _artifact("v2"), ("v2", True))

    artifact, meta = pregame_serving.serving_state()

    assert artifact is not None
    assert meta["status"] == "serving_current"
    assert meta["serving_version"] == meta["backtest_version"] == "v2"
    assert meta["reason"] is None


def test_gate_failure_reports_serving_previous_with_both_versions(monkeypatch):
    """閘門未過：DB 已記 deployable=false，artifact 仍是上一版 ⇒ 必須明講沿用哪一版。"""
    _patch(monkeypatch, _artifact("v1"), ("v2", False))

    artifact, meta = pregame_serving.serving_state()

    # 機率仍算得出來（模型還在），但狀態必須是降級而非 serving_current。
    assert artifact is not None
    assert meta["status"] == "serving_previous"
    assert meta["serving_version"] == "v1"
    assert meta["backtest_version"] == "v2"
    assert meta["backtest_deployable"] is False
    assert meta["degradation"] == "gate_failed"
    assert "未通過部署閘門" in meta["reason"]


def test_legacy_artifact_without_version_is_not_assumed_current(monkeypatch):
    """去洩漏前的舊 artifact 沒有 version 欄；無法證明是最新就一律 fail-closed。"""
    _patch(monkeypatch, _artifact(None), ("v2", True))

    _, meta = pregame_serving.serving_state()

    assert meta["status"] == "serving_previous"
    assert meta["serving_version"] is None
    # 不是閘門失敗——最新回測其實 deployable=true，文案不得誣賴它。
    assert meta["degradation"] == "version_unknown"
    assert meta["backtest_deployable"] is True


def test_version_mismatch_while_backtest_claims_deployable_is_still_disclosed(monkeypatch):
    """artifact 已晉升但 DB 寫入失敗之類的異常：不得因為 deployable=true 就當正常。"""
    _patch(monkeypatch, _artifact("v3"), ("v2", True))

    _, meta = pregame_serving.serving_state()

    assert meta["status"] == "serving_previous"
    assert meta["degradation"] == "version_mismatch"
    assert meta["backtest_deployable"] is True
    assert meta["reason"] == "serving 版本與最新回測紀錄不一致"


@pytest.mark.parametrize(
    ("exists", "load_raises", "fault"),
    [(False, False, "artifact_missing"), (True, True, "error")],
)
def test_missing_or_corrupt_artifact_is_unavailable_with_per_game_fault(
    monkeypatch, exists, load_raises, fault,
):
    """`fault` 用逐場欄位既有字彙，避免 serving 語彙外洩到每一場比賽。"""
    _patch(monkeypatch, None, ("v2", True), exists=exists, load_raises=load_raises)

    artifact, meta = pregame_serving.serving_state()

    assert artifact is None
    assert meta["status"] == "unavailable"
    assert meta["fault"] == fault


# --- artifact 晉升的原子性 ----------------------------------------------------

def test_promotion_replaces_serving_only_after_reload_succeeds(tmp_path: Path):
    path = tmp_path / "outcome_simple.joblib"
    trainer.save_artifact({"version": "old"}, path)

    trainer.promote_artifact(_artifact("new"), path, [])

    assert trainer.artifact_version(path) == "new"
    assert list(tmp_path.glob("*.staged-*")) == []


def test_incomplete_artifact_never_reaches_serving(tmp_path: Path):
    """暫存檔驗證失敗 ⇒ 舊 artifact 原封不動、暫存檔清掉、例外上浮讓 refresh 中止。"""
    path = tmp_path / "outcome_simple.joblib"
    trainer.save_artifact({"version": "old"}, path)
    incomplete = {k: v for k, v in _artifact("new").items() if k != "ensemble"}

    with pytest.raises(ValueError, match="缺欄位"):
        trainer.promote_artifact(incomplete, path, [])

    assert trainer.artifact_version(path) == "old"
    assert list(tmp_path.glob("*.staged-*")) == []


def test_db_is_written_after_the_artifact_is_in_place(monkeypatch, tmp_path: Path):
    """順序紅線：DB 不得先於 artifact 落地，否則失敗時 DB 會宣稱一個沒在 serving 的版本。"""
    order: list[str] = []
    path = tmp_path / "outcome_simple.joblib"

    monkeypatch.setattr(trainer.settings, "artifact_dir", tmp_path)
    monkeypatch.setattr(trainer, "load_outcome_rows", lambda: [])
    monkeypatch.setattr(trainer, "walk_forward_backtest",
                        lambda *a, **k: {"n_test": 1, "models": []})
    monkeypatch.setattr(trainer, "deployment_gate", lambda *a, **k: {"deployable": True,
                                                                     "checks": {}})
    monkeypatch.setattr(trainer, "train_final_model",
                        lambda *a, **k: {"trained_through": 2025, "signals": {},
                                         "model": _FakeModel(), "ensemble": []})
    monkeypatch.setattr(trainer, "promote_artifact",
                        lambda artifact, p, probe: order.append("artifact"))
    monkeypatch.setattr(trainer, "_persist", lambda *a, **k: order.append("db"))

    trainer.main()

    assert order == ["artifact", "db"], "artifact 必須先就位，DB 最後才宣稱狀態"
    assert path.exists() is False  # promote 被替身攔下，確認測的是順序而非副作用


def test_only_a_failed_gate_is_labelled_gate_failed(monkeypatch):
    """四種 serving_previous 只有一種能標 gate_failed；前端據此選文案。

    iteration 2 的缺陷是前端只看 status，三種一律講「最新回測未通過部署閘門」——
    而 deploy→refresh 窗口恰好是 version_unknown，那個回測其實是 7/7 通過的。
    """
    cases = {
        ("v1", "v2", False): "gate_failed",
        (None, "v2", True): "version_unknown",
        ("v3", "v2", True): "version_mismatch",
        ("v3", "v2", None): "backtest_unknown",
    }
    for (serving_version, backtest_version, deployable), expected in cases.items():
        _patch(monkeypatch, _artifact(serving_version), (backtest_version, deployable))

        _, meta = pregame_serving.serving_state()

        assert meta["degradation"] == expected
        assert (meta["degradation"] == "gate_failed") == (deployable is False)


# --- 閘門結果未知的三條路徑（iteration 5 查核 F1）--------------------------------

class _FakeCursor:
    def __init__(self, row) -> None:
        self._row = row

    def fetchone(self):  # noqa: ANN201 - 測試替身
        return self._row


class _FakeConnection:
    def __init__(self, row=None, raises: bool = False) -> None:
        self._row = row
        self._raises = raises

    def execute(self, *_args, **_kwargs):  # noqa: ANN002, ANN003, ANN201 - 測試替身
        if self._raises:
            raise RuntimeError("connection refused")
        return _FakeCursor(self._row)

    def __enter__(self):  # noqa: ANN204 - 測試替身
        return self

    def __exit__(self, *_exc):  # noqa: ANN002, ANN204 - 測試替身
        return False


@pytest.mark.parametrize(
    ("label", "connection"),
    [
        ("DB 讀取例外", _FakeConnection(raises=True)),
        ("model_versions 無 row", _FakeConnection(row=None)),
        ("gate 欄缺失", _FakeConnection(row=("v2", {"cv": 1}))),
        ("gate.deployable 為 null", _FakeConnection(row=("v2", {"gate": {"deployable": None}}))),
    ],
)
def test_unknown_gate_paths_never_report_deployable(monkeypatch, label, connection):
    """三條未知路徑都必須回 deployable=None——不得因為「沒說失敗」就被當成通過。"""
    monkeypatch.setattr(pregame_serving, "conn", lambda: connection)

    latest = pregame_serving._latest_backtest()

    assert latest.deployable is None, label


@pytest.mark.parametrize(
    ("label", "connection"),
    [
        ("DB 讀取例外", _FakeConnection(raises=True)),
        ("model_versions 無 row", _FakeConnection(row=None)),
        ("gate 欄缺失", _FakeConnection(row=("v2", {"cv": 1}))),
        ("gate.deployable 為 null", _FakeConnection(row=("v2", {"gate": {"deployable": None}}))),
    ],
)
def test_unknown_gate_is_its_own_degradation_not_a_version_mismatch(
    monkeypatch, label, connection,
):
    """讀不到閘門結果 ⇒ backtest_unknown。

    iteration 5 查核 F1：這三條路徑原本全落到 version_mismatch，而前端對該判別碼固定
    附註「該次回測本身已通過閘門」——對一個根本沒讀到的回測宣稱 PASS。
    """
    monkeypatch.setattr(pregame_serving, "artifact_path", lambda: Path("/fake/a.joblib"))
    monkeypatch.setattr(Path, "exists", lambda self: True)
    monkeypatch.setattr(pregame_serving, "load_artifact", lambda _p: _artifact("v1"))
    monkeypatch.setattr(pregame_serving, "conn", lambda: connection)

    _, meta = pregame_serving.serving_state()

    assert meta["status"] == "serving_previous", label
    assert meta["degradation"] == "backtest_unknown", label
    assert meta["backtest_deployable"] is None, label
    assert "閘門" in meta["reason"] and "未通過" not in meta["reason"], label


def test_matching_versions_stay_current_even_when_the_gate_is_unreadable(monkeypatch):
    """版本相同＝serving 確實是最新回測的產出；閘門結果未知不改變這個事實。"""
    _patch(monkeypatch, _artifact("v2"), ("v2", None))

    _, meta = pregame_serving.serving_state()

    assert meta["status"] == "serving_current"
    assert meta["degradation"] is None


def test_legacy_artifact_wins_over_unknown_gate(monkeypatch):
    """兩側皆未知時取 version_unknown——它的文案不碰閘門，講得比較精確（分支序第 2 條）。"""
    _patch(monkeypatch, _artifact(None), (None, None))

    _, meta = pregame_serving.serving_state()

    assert meta["degradation"] == "version_unknown"
