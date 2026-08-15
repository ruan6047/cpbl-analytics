# LIFECYCLE: oneshot · 卡片一次性產物——不要跑；刪除須需求方裁定（INGEST-SPLITS-PA-SPLIT1）
"""RESULTS 引用數字 ↔ artifact 一致性檢查（REVIEW-008 F1 的防再犯守衛）。

iteration 2 的教訓：RESULTS 的排行榜數字取自較早一輪的中間輸出，與最終 artifact
漂移（鄭鎧文 156 vs 166）。本守衛把報告裡的關鍵數字逐一對回兩份 artifact，
任何一項不符即 exit 1。查核者可直接重跑：

    uv run python scripts/check_splits_pa_split1_results.py
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

from cpbl.ingest.cpbl_player_detail import APART_COMBOS

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    doc = (ROOT / "docs/research/INGEST-SPLITS-PA-SPLIT1_RESULTS.md").read_text()
    m = json.loads((ROOT / "docs/research/ingest_splits_pa_split1_metrics.json").read_text())
    d = json.loads(
        (ROOT / "docs/research/ingest_splits_pa_split1_player_delta.json").read_text())
    ds = m["player_delta_summary"]
    h1 = m["h1_batting_order_shift"]
    af = m["assembly_fidelity_vs_published"]
    bc = m["box_crosscheck"]

    tr = m["canonical_transitions"]
    checks = {
        "296（transition 總數，baseline 窗 ≤2026-07-28）":
            tr["baseline"]["total"] == 296
            and tr["baseline"]["prev_disposition"]
            == {"counted": 83, "ghost_island_no_pitch": 210, "skipped_no_outcome": 3}
            and tr["baseline"]["by_criterion"]
            == {"pinch_hit_slot": 216, "count_continues": 80}
            and "**296**" in doc,
        "窗外新增全數歸因且未增曝險（as-of 原則）":
            tr["total"] - tr["baseline"]["total"] == len(tr["post_baseline_rows"])
            and all(t["game_date"] > tr["baseline_cutoff"]
                    for t in tr["post_baseline_rows"])
            and m["exposure"]["baseline"]["double_counted_pas"]
            == m["exposure"]["double_counted_pas"]
            and m["exposure"]["baseline"]["affected_games"]
            == m["exposure"]["affected_games"],
        "83 筆／82 場":
            f'**{m["exposure"]["double_counted_pas"]} 筆／'
            f'{m["exposure"]["affected_games"]} 場**' in doc,
        "counted 判準 79/4":
            m["exposure"]["by_criterion"] == {"count_continues": 79, "pinch_hit_slot": 4}
            and "count_continues` 79／`pinch_hit_slot` 4" in doc,
        "漏判 22＝18 cc＋4 phs":
            m["iteration1_missed_classification"]["missed_by_criterion"]
            == {"count_continues": 18, "pinch_hit_slot": 4}
            and "`count_continues` 18＋`pinch_hit_slot` 4" in doc,
        "H1 1,291":
            f"**{h1['total_pas_misattributed']:,} 筆**" in doc,
        "H1 分布 81×1＋1×2":
            collections.Counter(r["shift"] for r in h1["rows"])
            == collections.Counter({1: 81, 2: 1})
            and "81 組位移 1、1 組位移 2" in doc,
        "delta rows／cells／唯一選手":
            f'**{ds["rows"]:,} 個發布 row 受影響／{ds["changed_cells"]:,} 個格／'
            f'{ds["affected_players"]} 位唯一選手**' in doc,
        "逐表選手數":
            ds["affected_table_players"]
            == {"batting_splits": 249, "pitching_splits": 65}
            and "batting_splits 249、pitching_splits 65" in doc,
        "組裝層保真全等":
            sum(v["equal_rows"] for v in af.values())
            == sum(v["common"] for v in af.values())
            and f'{sum(v["equal_rows"] for v in af.values()):,}／'
                f'{sum(v["common"] for v in af.values()):,}' in doc,
        "box legacy 88 → corrected 7":
            bc["rows_total"] - bc["legacy_matches_box"] == 88
            and len(bc["corrected_mismatches"]) == 7
            and "88 筆逐人不吻合；corrected 後只剩 7 筆" in doc,
        "排行榜（含跨表聚合）":
            all(any(e["player"] == p and e["sum_abs_delta"] == v
                    for e in ds["top_players_by_abs_delta"]) and f"{p} {v}" in doc
                for p, v in (("高國麟", 174), ("鄭鎧文", 166),
                             ("李宗賢", 157), ("江坤宇", 133))),
        "兩份 artifact 摘要一致":
            d["summary"] == ds,
        "9.15(b) 歸原打者 22 例":
            m["exposure"]["strikeout_charged_to_prev_cases"] == 22
            and "22 筆原打者已被判第 2" in doc,
        "H2 不可重現證據（artifact 化，REVIEW-017）":
            (lambda h2, hist: (
                h2["apart_combos_in_code"] == [list(t) for t in APART_COMBOS]
                and all(v["distinct_updated_dates"] == ["2026-07-14"]
                        for v in hist.values())
                and hist["batting_splits"]["rows_before_2026"] > 0
                and hist["pitching_splits"]["rows_before_2026"] > 0
                and h2["phase0_harness_commit"].get("sha", "").startswith("3a66169")
                and h2["phase1_overwrite_commit"].get("sha", "").startswith("36e3334")
                and h2["prod_evidence_recorded"]["earliest_backup"] == "2026-07-25"
                and h2["conclusion"] == {"never_reconciled_2018_2025": True,
                                         "snapshot_reproducible": False}
                and f'{hist["batting_splits"]["rows_before_2026"]:,}' in doc
                and f'{hist["pitching_splits"]["rows_before_2026"]:,}' in doc
                and "updated_at` = 2026-07-14" in doc
                and "`3a66169`" in doc
                and "不可重現" in doc
            ))(m["h2_reconciliation_evidence"],
               m["h2_reconciliation_evidence"]["historical_rows_updated_at"]),
    }
    bad = [k for k, ok in checks.items() if not ok]
    for k, ok in checks.items():
        print(("✓" if ok else "✗"), k)
    if bad:
        print(f"\n✗ {len(bad)} 項不一致：{bad}")
        return 1
    print(f"\n✓ 全部 {len(checks)} 項一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
