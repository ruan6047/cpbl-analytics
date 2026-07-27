"""賽前模型 serving 狀態：serving 的 artifact 是不是最新那一次回測產出的？

ML-OUTCOME-SIMPLE-LEAK2 紅線 5：閘門未過時 `cpbl-train-outcome-simple` 會沿用舊 artifact
而 `model_versions` 仍記下這次的 `deployable=false`，兩者版本因此對不上。這個落差**必須由
後端明確回傳**、並在首頁與方法頁同時呈現，不得只寫進 log——否則使用者看到的仍是上一版
模型給的機率，卻沒有任何提示。

**`status` 與 `degradation` 是兩個正交的維度**，別把它們當成同一件事：

`status` 只回答「serving 是不是最新那一次回測的產出」：
- `serving_current`  是。
- `serving_previous` 不是，或無法證明是。
- `unavailable`      沒有 artifact 或讀不起來，賽前機率整段不提供。

`degradation` 才是**揭露與否的唯一開關**（非 null 就要在介面上講）。兩者正交，因為
`serving_current` 也可能要揭露：`serving_gate_failed`＝serving 確實就是最新回測那一版，
而那一次回測**沒過閘門**——此時機率正是該次回測那一版模型的輸出，講「沿用上一版」
反而是假話，但它比沿用上一版更嚴重，絕不能因為 status 正常就靜默（iteration 6 查核 F1）。

fail-closed：任何無法證明「serving＝最新」的情況一律報 `serving_previous`，包含舊格式
（無 `version` 欄）的 artifact——它正是去洩漏前訓練出來的那一種。反過來說，
**證明得了「serving＝最新」不等於沒事**，閘門結果是另一個維度。
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

    先分「serving 是不是最新回測的產出」（版本是否相等），再在各自底下依 `deployable`
    分流——**版本比對與閘門結果是兩個維度，不是同一條優先序上的兩格**。iteration 6 把
    它們排成一條序，於是版本相同時吃掉了明確的閘門失敗（查核 F1）。

    版本相等（serving 就是最新回測那一版，`status="serving_current"`）：

    - `deployable is False` → `serving_gate_failed`。**正在提供機率的就是那個沒過閘門的
      模型**，比沿用上一版更嚴重。status 仍為 `serving_current`（謊報成 previous 就是
      說假話：機率確實出自最新回測那一版），揭露靠 `degradation`。
    - `True`／`None` → 無 `degradation`。`None`（閘門結果未知）在此刻意不揭露：serving
      與最新回測是同一版這件事本身已證明，沒有「使用者看到的不是這一版」的風險。

    版本不等（`status="serving_previous"`）依下列**固定順序**判定，順序是「從能證明的
    事實排到不能證明的」，因為每個判別碼決定前端能說出口的話：

    1. `deployable is False` → `gate_failed`。DB 明確記下這次回測沒過閘門，是四者中
       唯一有正面證據的宣稱，**也是唯一能講「未通過部署閘門且已沿用上一版」的分支**。
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
        # serving＝最新回測那一版。這仍不足以說「沒事」：那一次回測可能沒過閘門，
        # 而正在服務的就是它（iteration 6 查核 F1；trainer 正常流程不該產生此狀態，
        # 但 version 由 int(time.time()) 鑄造會碰撞、並行訓練與資料修復都可能到達，
        # fail-closed 契約不得建立在「正常流程不會這樣」之上）。
        meta = _meta(
            "serving_current",
            "最新回測未通過部署閘門，而 serving 就是該次回測產出的模型"
            if deployable is False else None,
            serving_version, backtest_version, deployable,
            degradation="serving_gate_failed" if deployable is False else None,
        )
    elif deployable is False:
        # **唯一**能宣稱「閘門失敗且已沿用上一版」的分支。其餘版本不一致與閘門結果無關，
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

    `degradation` 是降級成因判別碼，也是**介面揭露與否的唯一開關**（非 None 就要講）。
    它**不限於 `serving_previous`**：`serving_gate_failed` 掛在 `serving_current` 上
    （serving 就是最新回測那一版，但那一次沒過閘門）。其餘四碼（`gate_failed`／
    `version_unknown`／`backtest_unknown`／`version_mismatch`）屬 `serving_previous`。
    `unavailable` 的 degradation 恆為 None——整段不可用由各介面自己的不可用文案負責，
    不再多疊一句告示。

    **判別在後端做一次**，前端只做映射——iteration 2 讓前端自己看 status 猜成因，結果
    三種情形全被講成閘門失敗。新增判別碼時前端必須同步新增 case：其 default 分支刻意
    只給不含閘門宣稱的中性文案。
    """
    return {"status": status, "reason": reason, "serving_version": serving_version,
            "backtest_version": backtest_version, "backtest_deployable": deployable,
            "fault": fault, "degradation": degradation,
            "trained_through": None, "signals": None}
