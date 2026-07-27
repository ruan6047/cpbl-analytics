"""賽前模型 serving 狀態：serving 的 artifact 是不是最新那一次回測產出的？

ML-OUTCOME-SIMPLE-LEAK2 紅線 5：閘門未過時 `cpbl-train-outcome-simple` 會沿用舊 artifact
而 `model_versions` 仍記下這次的 `deployable=false`，兩者版本因此對不上。這個落差**必須由
後端明確回傳**、並在首頁與方法頁同時呈現，不得只寫進 log——否則使用者看到的仍是上一版
模型給的機率，卻沒有任何提示。

三個狀態：
- `serving_current`  serving artifact 就是最新回測產出的那一版（正常）。
- `serving_previous` serving 沿用上一版。`degradation` 分辨四種成因，見 `serving_state()`。
- `unavailable`      沒有 artifact 或讀不起來，賽前機率整段不提供。

fail-closed：任何無法證明「serving＝最新」的情況一律報 `serving_previous`，
包含舊格式（無 `version` 欄）的 artifact——它正是去洩漏前訓練出來的那一種。
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from cpbl.config import settings
from cpbl.db import conn
from cpbl.models.outcome_simple import load_artifact

ARTIFACT_NAME = "outcome_simple.joblib"


def artifact_path() -> Path:
    return settings.artifact_dir / ARTIFACT_NAME


class LatestBacktest(NamedTuple):
    """`model_versions` 最新一次 `outcome_simple` 回測列的兩個事實。

    `deployable` 的 `None` **一律是「未知」，不是「沒說失敗就算通過」**：DB 讀不到、
    沒有任何回測列、該列的 `cv_metrics.gate` 沒寫 `deployable`——三種情形都無法證明
    閘門通過，因此在這裡就必須與 `True` 分開表達，不能讓呼叫端只做 `is False` 的判斷。

    iteration 5 查核 F1 的成因正是這個未知被吞進「版本不一致但回測已通過」那條分支，
    於是 UI 對一個根本沒讀到的回測宣稱「該次回測本身已通過閘門」——未知被呈現成 PASS。
    """

    version: str | None
    deployable: bool | None


def _latest_backtest() -> LatestBacktest:
    """model_versions 最新列 → (version, gate.deployable)。表缺席不阻塞賽程。

    三條「未知」路徑（DB 例外／無 row／`gate.deployable` 缺席或為 null）都回
    `deployable=None`。它們對使用者的意義相同（無從確認閘門結果），故不再細分；
    但與 `True`／`False` 一定要分得開，見 `LatestBacktest`。
    """
    try:
        with conn() as connection:
            row = connection.execute(
                "SELECT id, cv_metrics FROM cpbl.model_versions "
                "WHERE task='outcome_simple' ORDER BY trained_at DESC LIMIT 1"
            ).fetchone()
    except Exception:  # noqa: BLE001 — DB 讀不到時退回「未知」，由呼叫端 fail-closed
        return LatestBacktest(None, None)
    if not row:
        return LatestBacktest(None, None)
    gate = (row[1] or {}).get("gate") or {}
    deployable = gate.get("deployable")
    return LatestBacktest(row[0], bool(deployable) if deployable is not None else None)


def serving_state() -> tuple[dict | None, dict]:
    """→ (artifact 或 None, serving meta)。meta 一律可序列化，供兩個 router 共用。

    `serving_previous` 的四種成因由下面這個**固定順序**判定，順序本身是「從能證明的
    事實排到不能證明的」，因為每個判別碼決定前端能說出口的話：

    1. `deployable is False` → `gate_failed`。DB 明確記下這次回測沒過閘門，是四者中
       唯一有正面證據的宣稱，**也是唯一能講「未通過部署閘門」的分支**，故排最前面。
    2. `serving_version is None` → `version_unknown`。這是手上這個 artifact 自身的性質
       （去洩漏前的舊格式），與回測那一側讀不讀得到無關；即使回測側同時未知，
       「serving 沒有版本可比對」仍是更貼近使用者所見那個機率的事實，且其文案本來就
       不碰閘門結果，兩側皆未知時照樣講得精確。這正是部署→refresh 窗口的狀態。
    3. `deployable is None` → `backtest_unknown`。artifact 自陳了版本，但回測那一側
       讀不到（DB 例外／無紀錄／gate 欄缺席），閘門結果無從得知。
    4. 其餘（`deployable is True` 且版本不一致）→ `version_mismatch`。**只有這條**是
       兩側都讀到、且回測確實通過閘門，前端才可以附註「該次回測本身已通過閘門」。
    """
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
        # **唯一**能宣稱「閘門失敗」的分支。其餘版本不一致與閘門結果無關，
        # 前端若一律講成閘門失敗就是說錯話（ML-OUTCOME-SIMPLE-LEAK2 iteration 2 缺陷）。
        meta = _meta("serving_previous", "最新回測未通過部署閘門，serving 沿用上一版模型",
                     serving_version, backtest_version, deployable,
                     degradation="gate_failed")
    elif serving_version is None:
        meta = _meta("serving_previous", "serving artifact 未記錄版本（去洩漏前的舊格式）",
                     serving_version, backtest_version, deployable,
                     degradation="version_unknown")
    elif deployable is None:
        # 讀不到最新回測的閘門結果。**不得**因為「沒說失敗」就滑進 version_mismatch，
        # 那條分支的文案會宣稱該次回測已通過閘門（iteration 5 查核 F1）。
        meta = _meta("serving_previous",
                     "無法確認最新回測的閘門結果（紀錄讀不到或未記載）",
                     serving_version, backtest_version, deployable,
                     degradation="backtest_unknown")
    else:
        meta = _meta("serving_previous", "serving 版本與最新回測紀錄不一致",
                     serving_version, backtest_version, deployable,
                     degradation="version_mismatch")
    meta["trained_through"] = artifact.get("trained_through")
    meta["signals"] = artifact.get("signals")
    return artifact, meta


def _meta(status: str, reason: str | None, serving_version: str | None,
          backtest_version: str | None, deployable: bool | None,
          fault: str | None = None, degradation: str | None = None) -> dict:
    """`fault` 只在 `unavailable` 時有值，用既有的**逐場**欄位字彙（`artifact_missing`／
    `error`）表達成因。serving 狀態語彙屬模型層級，不外洩到逐場 pregame 欄位。

    `degradation` 是 `serving_previous` 的成因判別碼（`gate_failed`／`version_unknown`／
    `backtest_unknown`／`version_mismatch`），供前端選文案。**判別在後端做一次**，前端只做
    映射——iteration 2 讓前端自己看 status 猜成因，結果三種情形全被講成閘門失敗。
    新增判別碼時前端必須同步新增 case：其 default 分支刻意只給不含閘門宣稱的中性文案。
    """
    return {"status": status, "reason": reason, "serving_version": serving_version,
            "backtest_version": backtest_version, "backtest_deployable": deployable,
            "fault": fault, "degradation": degradation,
            "trained_through": None, "signals": None}
