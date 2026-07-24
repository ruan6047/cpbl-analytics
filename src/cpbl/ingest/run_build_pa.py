"""CLI：物化 canonical PA build 並回填（GAME-RECAP-PA1-BUILD1）。

    uv run cpbl-build-pa --from-year 2018 --to-year 2026 --kind A --kind C --kind D --kind E
    uv run cpbl-build-pa --game 2026:A:162            # 單場
    uv run cpbl-build-pa --migrate --from-year 2026 --to-year 2026 --report docs/research/GAME-RECAP-PA1-BUILD1_QA.md

冪等可續跑：同一來源重跑為 no-op；晚到/修正來源產出 reconciliation_required build，
不覆寫已發布 pa_id（見 pa_build 模組 docstring 與契約）。逐球來源唯讀。
"""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path
from typing import Any

from cpbl.db import migrate
from cpbl.ingest.pa_build import build_scope, collect_qa


def _parse_game(spec: str) -> tuple[int, str, int]:
    year, kind, sno = spec.split(":")
    return int(year), kind, int(sno)


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
    args = parser.parse_args()

    if args.migrate:
        log.info("applying migrations…")
        log.info("migrations applied: %s", migrate())

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
