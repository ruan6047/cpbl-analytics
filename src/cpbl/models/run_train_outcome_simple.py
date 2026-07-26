"""固定語意群賽前模型：離線回測、閘門、artifact 與 metrics 持久化。"""

from __future__ import annotations

import json
import logging
import time
from datetime import date

from cpbl.config import settings
from cpbl.db import conn
from cpbl.models.outcome_simple import (
    deployment_gate,
    load_artifact,
    load_outcome_rows,
    save_artifact,
    train_final_model,
    walk_forward_backtest,
)

log = logging.getLogger("cpbl.models.outcome_simple")


def _persist(result: dict, gate: dict) -> str:
    version = f"outcome-simple-{int(time.time())}"
    payload = {**result, "gate": gate}
    with conn() as connection:
        connection.execute("DELETE FROM cpbl.model_versions WHERE task='outcome_simple'")
        connection.execute(
            "INSERT INTO cpbl.model_versions (id,task,algo,params,cv_metrics) "
            "VALUES (%s,'outcome_simple','logistic-semantic-v1',%s,%s)",
            (version, json.dumps({"groups": "one-signal-per-semantic-group"}),
             json.dumps(payload)),
        )
    return version


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    trained_through = date.today().year - 1
    rows = [row for row in load_outcome_rows() if row.season <= trained_through]
    test_years = sorted({row.season for row in rows})[-5:]
    result = walk_forward_backtest(rows, test_years, include_lightgbm=True)
    gate = deployment_gate(result, required_season_wins=min(3, len(test_years)))
    version = _persist(result, gate)
    log.info("model_version=%s test=%s n=%d", version, test_years, result["n_test"])
    for model in result["models"]:
        log.info("%-16s Accuracy=%.4f Brier=%.4f LogLoss=%.4f ECE=%.4f", model["name"],
                 model["accuracy"], model["brier"], model["log_loss"], model["ece"])
    log.info("gate=%s checks=%s", "PASS" if gate["deployable"] else "FAIL", gate["checks"])
    path = settings.artifact_dir / "outcome_simple.joblib"
    if not gate["deployable"]:
        # 沿用舊 artifact，但不得靜默：把「serving 的是哪一版、對不上哪一版回測」寫進
        # log 與 model_versions，讓 /methodology#pregame 的閘門面板與運維紀錄都對得上。
        served = _artifact_version(path)
        log.warning(
            "未通過上線閘門，不更新 serving artifact："
            "serving 仍為 %s，最新回測 %s 已記錄 deployable=false（兩者版本不一致）",
            served or "（無 artifact，賽前機率將顯示未建置）", version,
        )
        return
    artifact = {**train_final_model(rows, trained_through), "version": version, "gate": gate}
    save_artifact(artifact, path)
    log.info("artifact=%s version=%s signals=%s", path, version, artifact["signals"])


def _artifact_version(path) -> str | None:
    """既有 serving artifact 自陳的版本；缺席或舊格式（無 version 欄）皆回 None。"""
    if not path.exists():
        return None
    try:
        return load_artifact(path).get("version")
    except Exception:  # noqa: BLE001 — 讀不到就當未知，不讓訓練流程因此中斷
        return None


if __name__ == "__main__":
    main()
