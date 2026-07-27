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
    assert "未通過部署閘門" in meta["reason"]


def test_legacy_artifact_without_version_is_not_assumed_current(monkeypatch):
    """去洩漏前的舊 artifact 沒有 version 欄；無法證明是最新就一律 fail-closed。"""
    _patch(monkeypatch, _artifact(None), ("v2", True))

    _, meta = pregame_serving.serving_state()

    assert meta["status"] == "serving_previous"
    assert meta["serving_version"] is None


def test_version_mismatch_while_backtest_claims_deployable_is_still_disclosed(monkeypatch):
    """artifact 已晉升但 DB 寫入失敗之類的異常：不得因為 deployable=true 就當正常。"""
    _patch(monkeypatch, _artifact("v3"), ("v2", True))

    _, meta = pregame_serving.serving_state()

    assert meta["status"] == "serving_previous"
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
