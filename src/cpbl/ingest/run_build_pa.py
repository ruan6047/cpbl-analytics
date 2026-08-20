"""CLI：物化 canonical PA build 並回填（GAME-RECAP-PA1-BUILD1）。

    uv run cpbl-build-pa --from-year 2018 --to-year 2026 --kind A --kind C --kind D --kind E
    uv run cpbl-build-pa --game 2026:A:162            # 單場
    uv run cpbl-build-pa --migrate --from-year 2026 --to-year 2026 --report docs/research/GAME-RECAP-PA1-BUILD1_QA.md

冪等可續跑：同一來源重跑為 no-op；晚到/修正來源產出 reconciliation_required build，
不覆寫已發布 pa_id（見 pa_build 模組 docstring 與契約）。逐球來源唯讀。

DATA-PA-REBUILD-GAP1 另加三個**互斥於回填**的子命令：

    uv run cpbl-build-pa --stale-report out.md        # 唯讀：過期偵測逐場對帳（Q1 命中率）
    uv run cpbl-build-pa --pa-snapshot out.tsv        # 唯讀：逐場 PA 數快照（對照組前後比對）
    uv run cpbl-build-pa --accept-reconciliation 2026:D:119   # 受控接受（Q2／Q6）

``--accept-reconciliation`` 是本模組唯一會寫 published 的收尾路徑，且**擋不住的那道鎖
在 pa_build 裡不在這裡**：`pa_build.ACCEPTED_RECONCILIATIONS` 封閉清單＋
``invariant_violations`` 非空硬拒，由 `build_game` 內層強制（任何 import 該模組的呼叫端
都繞不過）。CLI 這層只是入口。
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any

from cpbl.db import migrate
from cpbl.ingest.pa_build import (
    ReconciliationAcceptRejected,
    accept_reconciliation,
    build_scope,
    collect_qa,
)


def _parse_game(spec: str) -> tuple[int, str, int]:
    year, kind, sno = spec.split(":")
    return int(year), kind, int(sno)


# ---------------------------------------------------------------------------
# 唯讀 artifact：過期偵測對帳 ＋ 逐場 PA 數快照
# ---------------------------------------------------------------------------
# ⚠️ 這條 SQL 與 `run_refresh_recent._pa_build_targets` 第三分支**同一個判準**
# （最新 livelog revision 的 row_count vs 現行 game_livelog 列數）。分兩處寫是有代價的，
# 但目的不同：那邊是選集、這邊是逐場對帳報表，且這邊必須輸出兩側數字供人核對。
# 改動任一側請同步另一側；`tests/test_pa_accept_reconciliation.py` 釘住兩者形狀一致。
_STALE_SQL = """
WITH latest AS (
  SELECT DISTINCT ON (r.year, r.kind_code, r.game_sno)
         r.year, r.kind_code, r.game_sno, r.id AS revision_id, r.row_count
  FROM cpbl.game_recap_source_revisions r
  WHERE r.source_kind = 'livelog'
  ORDER BY r.year, r.kind_code, r.game_sno, r.id DESC
), live AS (
  SELECT l.year, l.kind_code, l.game_sno, count(*) AS live_rows
  FROM cpbl.game_livelog l GROUP BY l.year, l.kind_code, l.game_sno
)
SELECT latest.year, latest.kind_code, latest.game_sno, latest.revision_id,
       latest.row_count, COALESCE(live.live_rows, 0) AS live_rows,
       (latest.row_count IS DISTINCT FROM COALESCE(live.live_rows, 0)) AS stale,
       EXISTS (SELECT 1 FROM cpbl.game_recap_builds b
               WHERE b.year = latest.year AND b.kind_code = latest.kind_code
                 AND b.game_sno = latest.game_sno AND b.state = 'published') AS has_published
FROM latest
LEFT JOIN live
  ON live.year = latest.year AND live.kind_code = latest.kind_code
 AND live.game_sno = latest.game_sno
ORDER BY latest.year, latest.kind_code, latest.game_sno
"""


def _stale_report(path: Path) -> int:
    """逐場列出（年/kind/sno、最新 revision row_count、現行 livelog 列數、判定）。回傳命中數。"""
    from psycopg.rows import dict_row

    from cpbl.db import conn

    with conn() as c:
        rows = [dict(r) for r in c.cursor(row_factory=dict_row).execute(_STALE_SQL).fetchall()]
    hits = [r for r in rows if r["stale"]]
    lines = [
        "# DATA-PA-REBUILD-GAP1 過期偵測對帳（cpbl-build-pa --stale-report 產生）",
        "",
        f"- 產生時間：{date.today()}",
        f"- 有 livelog revision 的場次：{len(rows)}",
        f"- 判定 stale（最新 revision row_count ≠ 現行 livelog 列數）：{len(hits)}",
        "",
        "> 判準只看**列數**：抓得到增長，抓不到原地修改（列數不變的官方改判）——"
        "該盲區承接卡為 #109。",
        "",
        "| 年 | kind | sno | 最新 revision id | revision.row_count | 現行 livelog 列數 | "
        "有 published | 判定 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in hits:
        lines.append(
            f"| {r['year']} | {r['kind_code']} | {r['game_sno']} | {r['revision_id']} | "
            f"{r['row_count']} | {r['live_rows']} | {r['has_published']} | STALE |"
        )
    if not hits:
        lines.append("| — | — | — | — | — | — | — | 全庫零命中 |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return len(hits)


def _pa_snapshot(path: Path) -> int:
    """逐場 published build 的 PA 數快照（TSV），供改動前後 diff 出對照組零變動。"""
    from cpbl.db import conn

    sql = """
    SELECT pa.year, pa.kind_code, pa.game_sno,
           count(DISTINCT pa.pa_id) AS pa_rows,
           count(DISTINCT ev.pa_id) AS event_pa
    FROM cpbl.game_plate_appearances pa
    JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id AND b.state = 'published'
    LEFT JOIN cpbl.game_pa_events ev ON ev.pa_row_id = pa.pa_row_id
    GROUP BY pa.year, pa.kind_code, pa.game_sno
    ORDER BY pa.year, pa.kind_code, pa.game_sno
    """
    with conn() as c:
        rows = c.execute(sql).fetchall()
    path.write_text(
        "year\tkind\tsno\tpa_rows\tevent_pa\n"
        + "".join(f"{r[0]}\t{r[1]}\t{r[2]}\t{r[3]}\t{r[4]}\n" for r in rows),
        encoding="utf-8",
    )
    return len(rows)


def _render_qa(scope: dict[str, Any], qa: list[dict[str, Any]], params: dict[str, Any]) -> str:
    def cell(v: Any) -> str:
        return "—" if v is None else str(v)

    lines = [
        "---",
        'title: "GAME-RECAP-PA1-BUILD1 canonical PA 物化 QA 對帳"',
        "card_id: GAME-RECAP-PA1-BUILD1",
        "status: awaiting-independent-review",
        f"date: {date.today()}",
        "tags:",
        "  - cpbl",
        "  - game-recap",
        "  - pa-build",
        "  - data-migration",
        "---",
        "",
        "# GAME-RECAP-PA1-BUILD1 QA 對帳",
        "",
        "關聯：[[GAME-RECAP-PA1]]、[[GAME-RECAP-PA1_CONTRACT]]、[[GAME-RECAP-PA1-EXPAND1]]、"
        "[[GAME-RECAP-PA1-TAXONOMY1]]。",
        "",
        "> 由 `cpbl-build-pa` 自動產生。每列為 published build 之 validation_summary 聚合。",
        "",
        "## 執行摘要",
        "",
        f"- 範圍：{params['from_year']}–{params['to_year']}，kind={','.join(params['kinds'])}。",
        f"- 處理場次：{scope['games']}。",
        f"- build actions：{scope['actions']}。",
        f"- build states：{scope['build_states']}。",
        f"- 失敗場次：{len(scope['errors'])}。",
        "",
    ]
    if scope["errors"]:
        lines += ["### 失敗場次", ""]
        for e in scope["errors"][:30]:
            lines.append(f"- {e['game']}: {e['error']}")
        lines.append("")

    lines += [
        "## 每 年/賽制/球場 對帳",
        "",
        "box_pa=完成 PA（登錄 pa_terminal，含無投球 award）；candidate=全 island；"
        "ready/unreliable/truncated/non_pa=PA state；mapped/failed=逐球映射；"
        "orphan=無 PA 成員擁有的逐球（fail closed，不虛構歸屬）。",
        "",
        "| 年 | kind | 球場 | 場 | box_pa | candidate | ready | unreliable | truncated | "
        "non_pa | mapped | failed | orphan |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in qa:
        lines.append(
            "| " + " | ".join(cell(r.get(k)) for k in (
                "year", "kind_code", "venue", "games", "box_pa", "candidate_pa", "ready",
                "unreliable", "truncated", "non_pa", "mapped_pitch", "failed_pitch",
                "orphan_pitch")) + " |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s"
    )
    log = logging.getLogger("cpbl.build_pa")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-year", type=int, default=2018)
    parser.add_argument("--to-year", type=int, default=date.today().year)
    parser.add_argument("--kind", action="append", dest="kinds")
    parser.add_argument("--game", action="append", dest="games",
                        help="單場 year:kind:sno，可重複")
    parser.add_argument("--migrate", action="store_true", help="先套用 migrations（冪等）")
    parser.add_argument("--report", type=Path, help="QA 對帳 Markdown 輸出路徑")
    parser.add_argument("--stale-report", type=Path,
                        help="唯讀：過期偵測逐場對帳 Markdown 輸出路徑（不 build）")
    parser.add_argument("--pa-snapshot", type=Path,
                        help="唯讀：逐場 published PA 數快照 TSV（不 build）")
    parser.add_argument("--accept-reconciliation", action="append", dest="accepts",
                        metavar="YEAR:KIND:SNO",
                        help="受控接受單場 reconciliation 並 republish，可重複。"
                             "⚠️ 須在 pa_build.ACCEPTED_RECONCILIATIONS 清單內且 "
                             "invariant_violations 為空，否則拒絕。")
    args = parser.parse_args()

    if args.migrate:
        log.info("applying migrations…")
        log.info("migrations applied: %s", migrate())

    # 唯讀子命令與接受路徑都**不跑回填**：混在一起會讓「這次執行到底寫了什麼」說不清。
    if args.stale_report:
        hits = _stale_report(args.stale_report)
        log.info("stale report written to %s（命中 %d 場）", args.stale_report, hits)
        return
    if args.pa_snapshot:
        n = _pa_snapshot(args.pa_snapshot)
        log.info("PA snapshot written to %s（%d 場）", args.pa_snapshot, n)
        return
    if args.accepts:
        failed = 0
        for spec in args.accepts:
            y, k, g = _parse_game(spec)
            try:
                res = accept_reconciliation(y, k, g)
            except ReconciliationAcceptRejected as exc:
                failed += 1
                # 逐條印出所有拒絕理由（閘門刻意不短路），且退出碼要反映失敗。
                log.error("拒絕接受 %s：", spec)
                for reason in exc.reasons:
                    log.error("  - %s", reason)
                continue
            log.info("accepted %s → %s", spec, json.dumps(res, ensure_ascii=False, default=str))
            log.warning(
                "⚠️ 下游物化表現在過期（本卡不重算，見 #119）：%s",
                ", ".join(f"{s['table']}@{s['scope']}" for s in res["downstream_stale"]),
            )
        if failed:
            sys.exit(1)
        return

    kinds = args.kinds or ["A", "C", "D", "E"]
    only_games = [_parse_game(g) for g in args.games] if args.games else None
    scope = build_scope(args.from_year, args.to_year, kinds, only_games=only_games)
    log.info("build_scope done: %s", scope)

    qa = collect_qa(args.from_year, args.to_year, kinds)
    params = {"from_year": args.from_year, "to_year": args.to_year, "kinds": kinds}
    if args.report:
        args.report.write_text(_render_qa(scope, qa, params), encoding="utf-8")
        log.info("QA report written to %s", args.report)


if __name__ == "__main__":
    main()
