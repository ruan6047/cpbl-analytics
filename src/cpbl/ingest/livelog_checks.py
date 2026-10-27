"""CLI：livelog 同號多筆的兩支可重跑機械檢查（#357 WP2-c）。唯讀。

    uv run cpbl-check-livelog                                  # 全部場次
    uv run cpbl-check-livelog --year 2026 --kind A             # 限定範圍
    uv run cpbl-check-livelog --raw-dir DIR --require-verifiable --json-out out.json

(i) **最後事件非結束標記**：每場 `game_livelog` 最大事件號那一列的 content 不是「比賽結束／
    主審裁定比賽結束」（判定與寫入端共用 `cpbl_gamelog._is_end_marker`）。
    **唯一豁免＝結束標記自佔事件號**（`exempt_standalone_marker`；2018–2021 有 85 場）：原文
    最大事件號只有那一列標記，實際最後事件在前一號、沒被覆蓋。DB 只存主列分不出它與「同號
    但尚未回補」，所以豁免必須有原文證據——`--raw-dir` 原文檔，或該場最新 livelog revision
    的 `detail.standalone_end_marker`（寫入端記錄）＝該事件號。⛔ 沒有原文證據一律算違反。
(ii) **同號守恆**：每場主表列數＋附加表（`game_livelog_extra`）列數＝原文帶事件號的列數；
    且附加列的事件號都在主表。原文列數來源依序：`--raw-dir` 原文檔 → 該場最新 livelog
    revision 的 `detail.event_rows`（#357 起寫入端記錄）。兩者都沒有的場次記為
    **無法驗證**——⛔ 不得當成通過；`--require-verifiable` 時視為違反。

退出碼：任一違反回 1，全過回 0（供每日鏈與腳本判斷）。
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from cpbl.db import conn
from cpbl.ingest._cli import KIND_CODES, cli_parser
from cpbl.ingest.cpbl_gamelog import _is_end_marker, standalone_end_marker_no

GameKey = tuple[int, str, int]

# 最大事件號：數字者依數值、非數字排最後（同 pa_build.event_sort_key）。
_LAST_EVENT_SQL = """
SELECT DISTINCT ON (year, kind_code, game_sno) year, kind_code, game_sno, main_event_no, content
FROM cpbl.game_livelog
WHERE (%(year)s::int IS NULL OR year = %(year)s::int)
  AND (%(kinds)s::text[] IS NULL OR kind_code = ANY(%(kinds)s::text[]))
  AND (%(gy)s::int[] IS NULL OR (year, kind_code, game_sno) IN
       (SELECT * FROM unnest(%(gy)s::int[], %(gk)s::text[], %(gs)s::int[])))
ORDER BY year, kind_code, game_sno,
         (main_event_no !~ '^[0-9]+$') DESC,
         CASE WHEN main_event_no ~ '^[0-9]+$' THEN main_event_no::numeric END DESC NULLS LAST,
         main_event_no DESC
"""

# 寫入端記下的原文證據：最新一筆 available livelog revision 的 detail.standalone_end_marker。
# has_key=false＝舊 revision（#357 前寫入）沒記，視同沒有原文證據。
_STANDALONE_SQL = """
SELECT DISTINCT ON (year, kind_code, game_sno) year, kind_code, game_sno,
       detail ? 'standalone_end_marker' AS has_key, detail->>'standalone_end_marker' AS marker_no
FROM cpbl.game_source_revisions
WHERE source = 'livelog' AND outcome = 'available'
  AND (%(year)s::int IS NULL OR year = %(year)s::int)
  AND (%(kinds)s::text[] IS NULL OR kind_code = ANY(%(kinds)s::text[]))
  AND (%(gy)s::int[] IS NULL OR (year, kind_code, game_sno) IN
       (SELECT * FROM unnest(%(gy)s::int[], %(gk)s::text[], %(gs)s::int[])))
ORDER BY year, kind_code, game_sno, last_seen_at DESC
"""

_COUNTS_SQL = """
WITH m AS (
    SELECT year, kind_code, game_sno, count(*) AS n FROM cpbl.game_livelog
    WHERE (%(year)s::int IS NULL OR year = %(year)s::int)
  AND (%(kinds)s::text[] IS NULL OR kind_code = ANY(%(kinds)s::text[]))
  AND (%(gy)s::int[] IS NULL OR (year, kind_code, game_sno) IN
       (SELECT * FROM unnest(%(gy)s::int[], %(gk)s::text[], %(gs)s::int[])))
    GROUP BY 1, 2, 3
), x AS (
    SELECT e.year, e.kind_code, e.game_sno, count(*) AS n,
           count(*) FILTER (WHERE l.main_event_no IS NULL) AS orphan
    FROM cpbl.game_livelog_extra e
    LEFT JOIN cpbl.game_livelog l USING (year, kind_code, game_sno, main_event_no)
    WHERE (%(year)s::int IS NULL OR e.year = %(year)s::int)
  AND (%(kinds)s::text[] IS NULL OR e.kind_code = ANY(%(kinds)s::text[]))
  AND (%(gy)s::int[] IS NULL OR (e.year, e.kind_code, e.game_sno) IN
       (SELECT * FROM unnest(%(gy)s::int[], %(gk)s::text[], %(gs)s::int[])))
    GROUP BY 1, 2, 3
), rev AS (
    SELECT DISTINCT ON (year, kind_code, game_sno) year, kind_code, game_sno,
           (detail->>'event_rows')::int AS event_rows
    FROM cpbl.game_source_revisions
    WHERE source = 'livelog' AND outcome = 'available' AND (%(year)s::int IS NULL OR year = %(year)s::int)
  AND (%(kinds)s::text[] IS NULL OR kind_code = ANY(%(kinds)s::text[]))
  AND (%(gy)s::int[] IS NULL OR (year, kind_code, game_sno) IN
       (SELECT * FROM unnest(%(gy)s::int[], %(gk)s::text[], %(gs)s::int[])))
    ORDER BY year, kind_code, game_sno, last_seen_at DESC
)
SELECT coalesce(m.year, x.year), coalesce(m.kind_code, x.kind_code), coalesce(m.game_sno, x.game_sno),
       coalesce(m.n, 0), coalesce(x.n, 0), coalesce(x.orphan, 0), rev.event_rows
FROM m FULL JOIN x USING (year, kind_code, game_sno)
LEFT JOIN rev ON rev.year = coalesce(m.year, x.year) AND rev.kind_code = coalesce(m.kind_code, x.kind_code)
             AND rev.game_sno = coalesce(m.game_sno, x.game_sno)
"""


def _params(year: int | None, kinds: list[str] | None,
            games: set[GameKey] | None = None) -> dict[str, Any]:
    g = sorted(games) if games is not None else None
    return {"year": year, "kinds": list(kinds) if kinds else None,
            "gy": [x[0] for x in g] if g is not None else None,
            "gk": [x[1] for x in g] if g is not None else None,
            "gs": [x[2] for x in g] if g is not None else None}


def _scope_key(key: GameKey) -> str:
    return f"{key[0]}/{key[1]}"


def check_last_event(cur: Any, *, year: int | None = None, kinds: list[str] | None = None,
                     games: set[GameKey] | None = None,
                     standalone: dict[GameKey, str | None] | None = None) -> dict[str, Any]:
    """(i) 每場最後事件 content 非結束標記。回傳涵蓋場數、違反／豁免清單與逐年／賽別計數。

    `standalone`：原文檔判出的「自佔標記事件號」（無則 None）；優先於 revision 記錄。
    """
    params = _params(year, kinds, games)
    cur.execute(_STANDALONE_SQL, params)
    evidence: dict[GameKey, tuple[str | None, str]] = {
        (int(y), k, int(s)): (no, "revision") for y, k, s, has_key, no in cur.fetchall() if has_key}
    for key, no in (standalone or {}).items():
        evidence[key] = (no, "raw")
    cur.execute(_LAST_EVENT_SQL, params)
    covered: Counter[str] = Counter()
    bad: Counter[str] = Counter()
    exempt_n: Counter[str] = Counter()
    violations: list[dict[str, Any]] = []
    exempt: list[dict[str, Any]] = []
    for y, k, s, no, content in cur.fetchall():
        key = (int(y), k, int(s))
        covered[_scope_key(key)] += 1
        if not _is_end_marker(content):
            continue
        name = f"{y}-{k}-{s}"
        marker_no, source = evidence.get(key, (None, None))
        if marker_no is not None and marker_no == no:
            exempt_n[_scope_key(key)] += 1
            exempt.append({"game": name, "main_event_no": no, "reason": "exempt_standalone_marker",
                           "evidence": source})
            continue
        bad[_scope_key(key)] += 1
        violations.append({"game": name, "main_event_no": no, "content": content,
                           "evidence": source or "none"})
    return {"check": "last_event_not_end_marker", "games": sum(covered.values()),
            "violations": len(violations), "exempt": len(exempt),
            "by_scope": {sc: {"games": covered[sc], "violations": bad[sc], "exempt": exempt_n[sc]}
                         for sc in sorted(covered)},
            "violation_games": violations, "exempt_games": exempt}


def check_conservation(cur: Any, *, year: int | None = None, kinds: list[str] | None = None,
                       games: set[GameKey] | None = None,
                       expected: dict[GameKey, int] | None = None,
                       require_verifiable: bool = False) -> dict[str, Any]:
    """(ii) 主表＋附加表列數＝原文帶事件號列數；附加列不得孤立於主表。

    `expected` 優先（原文檔或寫入端當場計數）；否則用最新 livelog revision 的 `event_rows`。
    """
    cur.execute(_COUNTS_SQL, _params(year, kinds, games))
    violations: list[dict[str, Any]] = []
    unverifiable: list[str] = []
    present: set[GameKey] = set()
    for y, k, s, n_main, n_extra, orphan, rev_rows in cur.fetchall():
        key = (int(y), k, int(s))
        present.add(key)
        name = f"{y}-{k}-{s}"
        if orphan:
            violations.append({"game": name, "reason": "orphan_extra_rows", "orphan": int(orphan)})
            continue
        want = (expected or {}).get(key, rev_rows)
        if want is None:
            unverifiable.append(name)
            continue
        if int(n_main) + int(n_extra) != int(want):
            violations.append({"game": name, "reason": "count_mismatch", "main": int(n_main),
                               "extra": int(n_extra), "expected": int(want)})
    # 指定場次（每日鏈＝本次寫入的場）卻完全不在兩表＝寫入沒落地。
    for g in sorted((games or set()) - present):
        violations.append({"game": "-".join(map(str, g)), "reason": "game_missing_from_livelog"})
    n_games = len(present)
    out = {"check": "same_number_conservation", "games": n_games, "violations": len(violations),
           "unverifiable": len(unverifiable), "violation_games": violations,
           "unverifiable_games": unverifiable[:50]}
    if require_verifiable and unverifiable:
        out["violations"] += len(unverifiable)
    return out


def raw_evidence(raw_dir: Path, sums_path: Path | None = None
                 ) -> tuple[dict[GameKey, int], dict[GameKey, str | None]]:
    """原文目錄（含 SHA256SUMS 驗證）→ (每場帶事件號的列數, 每場自佔標記事件號或 None)。"""
    from cpbl.ingest.livelog_replay import load_raw_games

    games, _rejected = load_raw_games(raw_dir, sums_path=sums_path)
    return ({k: sum(1 for r in g.livelog if r.get("MainEventNo")) for k, g in games.items()},
            {k: standalone_end_marker_no(g.livelog) for k, g in games.items()})


def run_checks(*, year: int | None = None, kinds: list[str] | None = None,
               games: set[GameKey] | None = None, expected: dict[GameKey, int] | None = None,
               standalone: dict[GameKey, str | None] | None = None,
               require_verifiable: bool = False) -> dict[str, Any]:
    with conn() as c:
        cur = c.cursor()
        last = check_last_event(cur, year=year, kinds=kinds, games=games, standalone=standalone)
        cons = check_conservation(cur, year=year, kinds=kinds, games=games, expected=expected,
                                  require_verifiable=require_verifiable)
    return {"last_event": last, "conservation": cons,
            "ok": last["violations"] == 0 and cons["violations"] == 0}


def main(argv: list[str] | None = None) -> None:
    p = cli_parser("cpbl-check-livelog", __doc__)
    p.add_argument("--year", type=int)
    p.add_argument("--kind", action="append", choices=KIND_CODES)
    p.add_argument("--raw-dir", type=Path, help="原文目錄（YEAR-KIND-SNO.json.gz＋SHA256SUMS）")
    p.add_argument("--sha256sums", type=Path, help="SHA256SUMS 位置（預設 RAW_DIR/SHA256SUMS）")
    p.add_argument("--require-verifiable", action="store_true",
                   help="守恆檢查無原文列數可比的場次視為違反")
    p.add_argument("--json-out", type=Path)
    args = p.parse_args(argv)
    expected, standalone = raw_evidence(args.raw_dir, args.sha256sums) if args.raw_dir else (None, None)
    result = run_checks(year=args.year, kinds=args.kind, expected=expected, standalone=standalone,
                        require_verifiable=args.require_verifiable)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.json_out:
        args.json_out.write_text(text + "\n", encoding="utf-8")
    summary = {name: {k: result[name][k] for k in ("games", "violations")}
               | ({"unverifiable": result[name]["unverifiable"]} if name == "conservation"
                  else {"exempt": result[name]["exempt"]})
               for name in ("last_event", "conservation")}
    print(json.dumps(summary | {"ok": result["ok"]}, ensure_ascii=False))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
