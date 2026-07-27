"""固定語意群賽前模型：離線回測、閘門、artifact 與 metrics 持久化。

**晉升順序是安全性的一部分**（ML-OUTCOME-SIMPLE-LEAK2 紅線 4）：先把新 artifact 寫到
暫存檔並驗證可載入、可預測，再以 `os.replace` 原子換上 serving 指標，**最後**才寫
`model_versions`。反過來（先 commit DB 再寫檔）只要中間任一步失敗，DB 就會宣稱
`deployable=true` 而 serving 仍是舊模型——那正是本卡要消除的狀態。
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import date
from pathlib import Path

from cpbl.config import settings
from cpbl.db import conn
from cpbl.models.outcome_simple import (
    OutcomeRow,
    deployment_gate,
    load_artifact,
    load_outcome_rows,
    save_artifact,
    train_final_model,
    walk_forward_backtest,
)

log = logging.getLogger("cpbl.models.outcome_simple")

ARTIFACT_NAME = "outcome_simple.joblib"


def _persist(version: str, result: dict, gate: dict) -> None:
    payload = {**result, "gate": gate}
    with conn() as connection:
        connection.execute("DELETE FROM cpbl.model_versions WHERE task='outcome_simple'")
        connection.execute(
            "INSERT INTO cpbl.model_versions (id,task,algo,params,cv_metrics) "
            "VALUES (%s,'outcome_simple','logistic-semantic-v1',%s,%s)",
            (version, json.dumps({"groups": "one-signal-per-semantic-group"}),
             json.dumps(payload)),
        )


def artifact_version(path: Path) -> str | None:
    """既有 serving artifact 自陳的版本；缺席或舊格式（無 version 欄）皆回 None。"""
    if not path.exists():
        return None
    try:
        return load_artifact(path).get("version")
    except Exception:  # noqa: BLE001 — 讀不到就當未知，不讓訓練流程因此中斷
        return None


def promote_artifact(artifact: dict, path: Path, probe: list[OutcomeRow]) -> None:
    """寫暫存檔 → 重新載入並實際預測一次 → 原子換上 serving 指標。

    驗證用重新載入而非直接信任記憶體物件：序列化壞掉、欄位缺漏、scaler／classifier 沒被
    正確 pickle，都只有在「讀回來再跑一次」時才會現形。暫存檔與 serving 檔同目錄，
    確保 `os.replace` 落在同一個檔案系統上、是真的原子換名而非複製。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(f"{path.name}.staged-{os.getpid()}")
    try:
        save_artifact(artifact, staged)
        restored = load_artifact(staged)
        required = {"version", "gate", "trained_through", "signals", "model", "ensemble"}
        missing = required - restored.keys()
        if missing:
            raise ValueError(f"暫存 artifact 缺欄位：{sorted(missing)}")
        if probe:
            restored["model"].predict(probe[:1])
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    trained_through = date.today().year - 1
    rows = [row for row in load_outcome_rows() if row.season <= trained_through]
    test_years = sorted({row.season for row in rows})[-5:]
    result = walk_forward_backtest(rows, test_years, include_lightgbm=True)
    gate = deployment_gate(result, required_season_wins=min(3, len(test_years)))
    # 版本 id 在此產生而非在 _persist 內，因為 artifact 必須帶著同一個 id 先落地。
    version = f"outcome-simple-{int(time.time())}"
    path = settings.artifact_dir / ARTIFACT_NAME

    log.info("model_version=%s test=%s n=%d", version, test_years, result["n_test"])
    for model in result["models"]:
        log.info("%-16s Accuracy=%.4f Brier=%.4f LogLoss=%.4f ECE=%.4f", model["name"],
                 model["accuracy"], model["brier"], model["log_loss"], model["ece"])
    log.info("gate=%s checks=%s", "PASS" if gate["deployable"] else "FAIL", gate["checks"])

    if gate["deployable"]:
        artifact = {**train_final_model(rows, trained_through),
                    "version": version, "gate": gate}
        promote_artifact(artifact, path, rows)
        log.info("artifact=%s version=%s signals=%s", path, version, artifact["signals"])
    else:
        # 沿用舊 artifact，但不得靜默：DB 仍記下這次的 deployable=false，於是
        # artifact.version 與 model_versions 最新列對不上，API 據此回報 serving_previous，
        # 首頁與方法頁同時揭露「最新回測未過閘門、現正沿用版本 X」。
        served = artifact_version(path)
        log.warning(
            "未通過上線閘門，不更新 serving artifact："
            "serving 仍為 %s，最新回測 %s 將記錄 deployable=false（兩者版本不一致）",
            served or "（無 artifact，賽前機率將顯示未建置）", version,
        )

    # DB 最後才寫：artifact 已就位（或已確定不動）才讓 model_versions 宣稱這一版的狀態。
    _persist(version, result, gate)


if __name__ == "__main__":
    main()
