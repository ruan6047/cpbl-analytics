"""ML-OUTCOME-LEAK1 一次性留痕：跑走查回測但**不寫入** model_versions。

用途：以同一份程式碼路徑，在「修正前（含洩漏）」與「修正後（賽前 as-of）」兩份
game_features 上各跑一次，輸出可並排的對照 JSON。

    uv run python scripts/outcome_leak_compare.py <out.json>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from cpbl.models.outcome_gbm import backtest
from cpbl.models.outcome_simple import (
    deployment_gate,
    load_outcome_rows,
    walk_forward_backtest,
)


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("outcome_leak_compare.json")
    gbm = backtest()
    gbm.pop("importance", None)

    rows = [r for r in load_outcome_rows() if r.season <= 2025]
    years = sorted({r.season for r in rows})[-5:]
    simple = walk_forward_backtest(rows, years, include_lightgbm=True)
    gate = deployment_gate(simple, required_season_wins=min(3, len(years)))
    for model in simple["models"]:
        model.pop("reliability", None)
    for fold in simple["folds"]:
        for model in fold["models"].values():
            model.pop("reliability", None)

    payload = {"outcome_gbm": gbm,
               "outcome_simple": {k: v for k, v in simple.items() if k != "folds"},
               "outcome_simple_folds": simple["folds"],
               "outcome_simple_gate": gate}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload["outcome_gbm"], ensure_ascii=False, indent=2))
    print(json.dumps(payload["outcome_simple"], ensure_ascii=False, indent=2))
    print(json.dumps(gate, ensure_ascii=False))


if __name__ == "__main__":
    main()
