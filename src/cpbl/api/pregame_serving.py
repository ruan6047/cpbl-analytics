"""賽前模型 serving 狀態：serving 的 artifact 是不是最新那一次回測產出的？

ML-OUTCOME-SIMPLE-LEAK2 紅線 5：閘門未過時 `cpbl-train-outcome-simple` 會沿用舊 artifact
而 `model_versions` 仍記下這次的 `deployable=false`，兩者版本因此對不上。這個落差**必須由
後端明確回傳**、並在首頁與方法頁同時呈現，不得只寫進 log——否則使用者看到的仍是上一版
模型給的機率，卻沒有任何提示。

三個狀態：
- `serving_current`  serving artifact 就是最新回測產出的那一版（正常）。
- `serving_previous` serving 沿用上一版。`reason` 分辨兩種成因：最新回測沒過閘門
                     （設計內的降級），或版本對不上但最新回測宣稱可部署（異常，
                     例如 artifact 晉升後 DB 寫入失敗）。兩者都要揭露。
- `unavailable`      沒有 artifact 或讀不起來，賽前機率整段不提供。

fail-closed：任何無法證明「serving＝最新」的情況一律報 `serving_previous`，
包含舊格式（無 `version` 欄）的 artifact——它正是去洩漏前訓練出來的那一種。
"""

from __future__ import annotations

from pathlib import Path

from cpbl.config import settings
from cpbl.db import conn
from cpbl.models.outcome_simple import load_artifact

ARTIFACT_NAME = "outcome_simple.joblib"


def artifact_path() -> Path:
    return settings.artifact_dir / ARTIFACT_NAME


def _latest_backtest() -> tuple[str | None, bool | None]:
    """model_versions 最新列 → (version, gate.deployable)。表缺席不阻塞賽程。"""
    try:
        with conn() as connection:
            row = connection.execute(
                "SELECT id, cv_metrics FROM cpbl.model_versions "
                "WHERE task='outcome_simple' ORDER BY trained_at DESC LIMIT 1"
            ).fetchone()
    except Exception:  # noqa: BLE001 — DB 讀不到時退回「未知」，由呼叫端 fail-closed
        return None, None
    if not row:
        return None, None
    gate = (row[1] or {}).get("gate") or {}
    deployable = gate.get("deployable")
    return row[0], (bool(deployable) if deployable is not None else None)


def serving_state() -> tuple[dict | None, dict]:
    """→ (artifact 或 None, serving meta)。meta 一律可序列化，供兩個 router 共用。"""
    path = artifact_path()
    if not path.exists():
        return None, _meta("unavailable", "outcome_simple artifact 未建置",
                           None, *_latest_backtest(), fault="artifact_missing")
    try:
        artifact = load_artifact(path)
    except Exception as exc:  # noqa: BLE001 — artifact 損毀時回傳賽程，不回 50% 假數字
        return None, _meta("unavailable", f"artifact 無法載入（{type(exc).__name__}）",
                           None, *_latest_backtest(), fault="error")

    serving_version = artifact.get("version")
    backtest_version, deployable = _latest_backtest()
    if serving_version is not None and serving_version == backtest_version:
        meta = _meta("serving_current", None, serving_version, backtest_version, deployable)
    elif deployable is False:
        meta = _meta("serving_previous", "最新回測未通過部署閘門，serving 沿用上一版模型",
                     serving_version, backtest_version, deployable)
    elif serving_version is None:
        meta = _meta("serving_previous", "serving artifact 未記錄版本（去洩漏前的舊格式）",
                     serving_version, backtest_version, deployable)
    else:
        meta = _meta("serving_previous", "serving 版本與最新回測紀錄不一致",
                     serving_version, backtest_version, deployable)
    meta["trained_through"] = artifact.get("trained_through")
    meta["signals"] = artifact.get("signals")
    return artifact, meta


def _meta(status: str, reason: str | None, serving_version: str | None,
          backtest_version: str | None, deployable: bool | None,
          fault: str | None = None) -> dict:
    """`fault` 只在 `unavailable` 時有值，用既有的**逐場**欄位字彙（`artifact_missing`／
    `error`）表達成因。serving 狀態語彙屬模型層級，不外洩到逐場 pregame 欄位。"""
    return {"status": status, "reason": reason, "serving_version": serving_version,
            "backtest_version": backtest_version, "backtest_deployable": deployable,
            "fault": fault, "trained_through": None, "signals": None}
