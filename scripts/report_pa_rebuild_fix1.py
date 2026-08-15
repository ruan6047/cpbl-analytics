# LIFECYCLE: oneshot · 卡片一次性產物——不要跑；刪除須需求方裁定（GAME-RECAP-PA1-FIX1）
"""GAME-RECAP-PA1-FIX1 全庫重建驗收報告：對 DB 實際狀態窮舉（非 dry-run）。

唯讀。產出查核者要求的四類證據：build 版本分布、published/reconciliation 數量、
逐場隔離清單與原因、以及卡面驗收查詢（半局出局 PA > 3、(半局, pre_outs) 重複）
對 **published + ready** 母體實測。

    uv run python scripts/report_pa_rebuild_fix1.py --out docs/research/game_recap_pa1_fix1_rebuild.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

from cpbl.db import conn


def collect() -> dict[str, Any]:
    import datetime as _dt
    with conn() as c:
        c.execute("SET TRANSACTION READ ONLY")
        cur = c.cursor(row_factory=dict_row)

        cur.execute(
            "SELECT builder_version, taxonomy_version, state, count(*) AS n "
            "FROM cpbl.game_recap_builds GROUP BY 1,2,3 ORDER BY 1,2,3"
        )
        version_dist = [dict(r) for r in cur.fetchall()]

        # 每場恰一個 published（partial unique index 的實測驗證）
        cur.execute(
            "SELECT count(*) AS games, count(*) FILTER (WHERE n_pub = 1) AS exactly_one "
            "FROM (SELECT year, kind_code, game_sno, "
            "             count(*) FILTER (WHERE state='published') AS n_pub "
            "      FROM cpbl.game_recap_builds GROUP BY 1,2,3) t"
        )
        pub_uniqueness = dict(cur.fetchone())

        # 逐場隔離清單：最新 build 為 reconciliation_required 的場次與原因
        cur.execute(
            """
            SELECT b.year, b.kind_code, b.game_sno, b.builder_version,
                   b.validation_summary->'invariant_violations' AS invariant_violations,
                   b.validation_summary->'reconcile'->>'action' AS reconcile_action,
                   jsonb_array_length(
                       COALESCE(b.validation_summary->'reconcile'->'changed', '[]'::jsonb)
                   ) AS changed_pas
            FROM cpbl.game_recap_builds b
            WHERE b.state = 'reconciliation_required'
              AND b.builder_version = 'pa-build-1.3.0'
              AND b.built_at = (SELECT max(b2.built_at) FROM cpbl.game_recap_builds b2
                                WHERE (b2.year, b2.kind_code, b2.game_sno)
                                    = (b.year, b.kind_code, b.game_sno))
            ORDER BY b.year, b.kind_code, b.game_sno
            """
        )
        isolated = [dict(r) for r in cur.fetchall()]

        # 卡面驗收 1：published + ready 母體的半局出局 PA > 3
        cur.execute(
            """
            SELECT count(*) AS n FROM (
                SELECT pa.year, pa.kind_code, pa.game_sno,
                       pa.pre_state->>'half', (pa.pre_state->>'inning')::int
                FROM cpbl.game_plate_appearances pa
                JOIN cpbl.game_recap_builds b
                  ON b.build_id = pa.build_id AND b.state = 'published'
                WHERE pa.state = 'ready' AND pa.outcome_family IN ('out','sacrifice')
                  AND pa.pre_state->>'half' IN ('1','2')
                  AND pa.pre_state->>'inning' IS NOT NULL
                GROUP BY 1,2,3,4,5 HAVING count(*) > 3
            ) t
            """
        )
        over3 = int(cur.fetchone()["n"])

        # 卡面驗收 2：published + ready 母體的 (半局, pre_outs) 多筆出局 PA
        cur.execute(
            """
            SELECT count(*) AS n FROM (
                SELECT pa.year, pa.kind_code, pa.game_sno,
                       pa.pre_state->>'half', (pa.pre_state->>'inning')::int,
                       pa.pre_state->>'outs'
                FROM cpbl.game_plate_appearances pa
                JOIN cpbl.game_recap_builds b
                  ON b.build_id = pa.build_id AND b.state = 'published'
                WHERE pa.state = 'ready' AND pa.outcome_family IN ('out','sacrifice')
                  AND pa.pre_state->>'half' IN ('1','2')
                  AND pa.pre_state->>'inning' IS NOT NULL
                GROUP BY 1,2,3,4,5,6 HAVING count(*) > 1
            ) t
            """
        )
        dup_outs = int(cur.fetchone()["n"])

        # published 1.2.0 的 PA state 分布 + 9.15(b) 跨打者歸屬實測
        cur.execute(
            """
            SELECT pa.state, count(*) AS n
            FROM cpbl.game_plate_appearances pa
            JOIN cpbl.game_recap_builds b
              ON b.build_id = pa.build_id AND b.state = 'published'
                 AND b.builder_version = 'pa-build-1.3.0'
            GROUP BY 1 ORDER BY 1
            """
        )
        pa_states = {r["state"]: r["n"] for r in cur.fetchall()}
        cur.execute(
            """
            SELECT count(*) AS cross_batter,
                   count(*) FILTER (WHERE pa.hitter_acnt <> pa.end_hitter_acnt)
                       AS charged_to_original
            FROM cpbl.game_plate_appearances pa
            JOIN cpbl.game_recap_builds b
              ON b.build_id = pa.build_id AND b.state = 'published'
                 AND b.builder_version = 'pa-build-1.3.0'
            WHERE pa.end_hitter_acnt IS NOT NULL
              AND EXISTS (SELECT 1 FROM cpbl.game_pa_events e
                          JOIN cpbl.game_livelog l
                            ON (l.year, l.kind_code, l.game_sno, l.main_event_no)
                             = (e.year, e.kind_code, e.game_sno, e.event_no)
                          WHERE e.pa_row_id = pa.pa_row_id
                            AND NOT l.is_change_player
                            AND l.hitter_acnt IS NOT NULL AND l.hitter_acnt <> ''
                            AND l.hitter_acnt <> pa.end_hitter_acnt)
            """
        )
        attribution = dict(cur.fetchone())

    return {
        "generated_at": _dt.datetime.now().astimezone().isoformat(),
        "build_version_distribution": version_dist,
        "published_uniqueness": pub_uniqueness,
        "isolated_games": isolated,
        "acceptance": {
            "half_innings_with_out_pa_gt_3": over3,
            "half_inning_pre_outs_duplicates": dup_outs,
        },
        "published_current_pa_states": pa_states,
        "cross_batter_attribution_in_db": attribution,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    report = collect()
    print(json.dumps({k: v for k, v in report.items() if k != "isolated_games"},
                     ensure_ascii=False, indent=2, default=str))
    print(f"isolated_games: {len(report['isolated_games'])} 場")
    for g in report["isolated_games"]:
        print(f"  {g['year']}/{g['kind_code']}/{g['game_sno']} "
              f"invariant={g['invariant_violations']} changed_pas={g['changed_pas']}")
    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str)
                            + "\n", encoding="utf-8")
        print(f"→ {args.out}")


if __name__ == "__main__":
    main()
