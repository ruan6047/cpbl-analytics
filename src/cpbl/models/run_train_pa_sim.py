"""單一打席模型：覆蓋率、走查、artifact 與 metrics 持久化。"""

from __future__ import annotations

import json
import logging
import time
from datetime import date

from cpbl.config import settings
from cpbl.db import conn
from cpbl.models.pa_backtest import (
    select_prior_strengths,
    transition_walk_forward,
    walk_forward_backtest,
)
from cpbl.models.pa_sim import (
    assert_audit_coverage,
    load_pa_dataset,
    save_pa_artifact,
    train_pa_artifact,
)

log = logging.getLogger("cpbl.models.pa_sim")


def _persist(result: dict, coverage: dict) -> str:
    version = f"pa-sim-{int(time.time())}"
    payload = {**result, "coverage": coverage}
    with conn() as connection:
        connection.execute("DELETE FROM cpbl.model_versions WHERE task='pa_sim'")
        connection.execute(
            "INSERT INTO cpbl.model_versions (id,task,algo,params,cv_metrics) "
            "VALUES (%s,'pa_sim','empirical-bayes-v1',%s,%s)",
            (version, json.dumps({"outcomes": 7}), json.dumps(payload)),
        )
    return version


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    trained_through = date.today().year - 1
    dataset = load_pa_dataset(2018, trained_through)
    assert_audit_coverage(dataset.audits)
    test_years = sorted(dataset.audits)[-5:]
    result = walk_forward_backtest(dataset.snapshots, test_years)
    strengths_by_year = {fold["year"]: tuple(fold["strengths"]) for fold in result["folds"]}
    result["transition_validation"] = transition_walk_forward(
        dataset.snapshots, test_years, strengths_by_year,
    )
    coverage = {
        str(year): {"pa": audit.total_pa, "classification": audit.classification_rate,
                    "rebuild": audit.rebuild_rate, "unknown": audit.unknown_actions}
        for year, audit in dataset.audits.items()
    }
    version = _persist(result, coverage)
    combined = next(model for model in result["models"] if model["name"] == "combined")
    league = next(model for model in result["models"] if model["name"] == "league")
    log.info("model_version=%s test=%s n=%d", version, test_years, result["n_test"])
    log.info("league  LogLoss=%.4f Brier=%.4f ECE=%.4f", league["log_loss"],
             league["brier"], league["ece"])
    log.info("combined LogLoss=%.4f Brier=%.4f ECE=%.4f", combined["log_loss"],
             combined["brier"], combined["ece"])
    transition = result["transition_validation"]
    log.info("transition LogLoss=%.4f next-WP MAE=%.4f weighted-WP Brier=%.4f current-WP Brier=%.4f",
             transition["transition_log_loss"], transition["next_wp_mae"],
             transition["weighted_wp_brier"], transition["current_wp_brier"])
    strengths = select_prior_strengths(dataset.snapshots, [(100.0, 400.0, 200.0),
                                                            (200.0, 400.0, 200.0)])
    artifact = train_pa_artifact(dataset.snapshots, trained_through, strengths)
    save_pa_artifact(artifact, settings.artifact_dir / "pa_sim.joblib")
    log.info("artifact=%s strengths=%s", settings.artifact_dir / "pa_sim.joblib", strengths)


if __name__ == "__main__":
    main()
