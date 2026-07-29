"""INGEST-SPLITS-PA-SPLIT1 查證：`splits_calc` 是否因 FIX1 同型的島切分缺陷而重複計打席。

**唯讀**（`SET TRANSACTION READ ONLY`），不寫任何表、不呼叫 `cpbl-build-splits`。
逐項對應卡面驗收：曝險範圍界定、H1 打序位移、以及重複計數對選手層級的影響量。

判準不重新定義：直接引用 FIX1 的 `cpbl.ingest.pa_build.continues_same_plate_appearance`
（canonical，taxonomy 1.1.0／builder 1.3.0 定案）。

    uv run python scripts/verify_splits_pa_split1.py --out docs/research/ingest_splits_pa_split1_metrics.json
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

from cpbl.db import conn
from cpbl.ingest.pa_build import (
    Event,
    _clean,
    _is_real_pitch,
    continues_same_plate_appearance,
    event_sort_key,
)
from cpbl.ingest.splits_calc import PA_OUTCOME

# splits_calc.flush() 讀的欄位（見 splits_calc 的 rows 查詢）；此處欄序無關，用 dict。
COLS = (
    "year, kind_code, game_sno, main_event_no, inning_seq, visiting_home_type, "
    "batting_order, out_cnt, ball_cnt, strike_cnt, pitch_cnt, content, action_name, "
    "batting_action_name, hitter_acnt, pitcher_acnt, is_strike, is_ball, is_change_player"
)


def _legacy_islands(events: list[Event]) -> list[list[Event]]:
    """`splits_calc.flush()` 的切界：`(inning, vh, hitter)` 一變就切（空 hitter 列不切界）。"""
    islands: list[list[Event]] = []
    prev_key = None
    for ev in sorted(events, key=event_sort_key):
        if not _clean(ev.get("hitter_acnt")):
            continue  # splits_calc：空 hitter 只推進比分、不切界也不入島
        key = (ev.get("inning_seq"), str(ev.get("visiting_home_type")),
               _clean(ev.get("hitter_acnt")))
        if key != prev_key:
            islands.append([])
            prev_key = key
        islands[-1].append(ev)
    return islands


def _counts_as_pa(island: list[Event]) -> tuple[bool, str, str | None]:
    """重現 `splits_calc.flush()` 的三道過濾，回傳 (是否計為 PA, 去向, outcome)。"""
    outcome = next((_clean(e.get("batting_action_name")) for e in reversed(island)
                    if _clean(e.get("batting_action_name"))), None)
    if not outcome:
        return False, "skipped_no_outcome", None
    if not any(e.get("is_strike") or e.get("is_ball") for e in island):
        return False, "ghost_island_no_pitch", outcome     # 幽靈島規則
    if PA_OUTCOME.get(outcome) is None:
        return False, "unknown_action", outcome            # 紅線：會 loud
    return True, "counted", outcome


def collect(from_year: int, to_year: int, kinds: list[str]) -> dict[str, Any]:
    with conn() as c:
        c.execute("SET TRANSACTION READ ONLY")
        cur = c.cursor(row_factory=dict_row)
        cur.execute(
            f"SELECT {COLS} FROM cpbl.game_livelog "  # noqa: S608
            "WHERE year BETWEEN %s AND %s AND kind_code = ANY(%s)",
            (from_year, to_year, kinds),
        )
        rows = [dict(r) for r in cur.fetchall()]

    games: dict[tuple[int, str, int], list[Event]] = collections.defaultdict(list)
    for r in rows:
        games[(r["year"], r["kind_code"], r["game_sno"])].append(r)

    disposition: collections.Counter = collections.Counter()
    exposed: list[dict[str, Any]] = []
    order_shift: list[dict[str, Any]] = []
    outcome_counter: collections.Counter = collections.Counter()

    for (year, kind, sno), events in sorted(games.items()):
        islands = _legacy_islands(events)

        # 標出「應合併但 splits_calc 會切開」的相鄰島對
        spurious: set[int] = set()   # 索引 i 表示 islands[i] 是多出來的那一段的前段
        for i, (prev, cur_isl) in enumerate(zip(islands, islands[1:], strict=False)):
            if not prev or not cur_isl:
                continue
            if ((prev[-1].get("inning_seq"), str(prev[-1].get("visiting_home_type")))
                    != (cur_isl[0].get("inning_seq"), str(cur_isl[0].get("visiting_home_type")))):
                continue
            if not continues_same_plate_appearance(prev, cur_isl[0]):
                continue
            counted, why, outcome = _counts_as_pa(prev)
            disposition[why] += 1
            if counted:
                spurious.add(i)
                outcome_counter[str(outcome)] += 1
                exposed.append({
                    "game": f"{year}/{kind}/{sno}",
                    "inning": prev[-1].get("inning_seq"),
                    "half": str(prev[-1].get("visiting_home_type")),
                    "batting_order": prev[-1].get("batting_order"),
                    "spurious_event_no": str(prev[0]["main_event_no"]),
                    "spurious_hitter": _clean(prev[0].get("hitter_acnt")),
                    "completing_hitter": _clean(cur_isl[0].get("hitter_acnt")),
                    "double_counted_outcome": outcome,
                    "has_real_pitch": any(_is_real_pitch(e) for e in prev),
                })

        # H1：`pa_seq` 位移——重現 flush() 的計數順序，量測每隊在多出 PA 之後的位移
        if spurious:
            seq: collections.Counter = collections.Counter()   # (vh) → 已計 PA 數
            shift: collections.Counter = collections.Counter() # (vh) → 累計位移
            after: collections.Counter = collections.Counter() # (vh) → 位移後仍被計的 PA 數
            for i, island in enumerate(islands):
                counted, _why, _o = _counts_as_pa(island)
                if not counted:
                    continue
                vh = str(island[0].get("visiting_home_type"))
                if shift[vh]:
                    after[vh] += 1
                seq[vh] += 1
                if i in spurious:
                    shift[vh] += 1
            for vh, s in shift.items():
                if s:
                    order_shift.append({
                        "game": f"{year}/{kind}/{sno}", "half": vh,
                        "shift": s, "pas_after_shift": after[vh],
                        "team_pa_total": seq[vh],
                    })

    return {
        "generated_at": datetime.datetime.now().astimezone().isoformat(),
        "scope": {"from_year": from_year, "to_year": to_year, "kinds": kinds,
                  "games": len(games), "events": len(rows)},
        "judgement_source": "cpbl.ingest.pa_build.continues_same_plate_appearance"
                            "（GAME-RECAP-PA1-FIX1 canonical，builder 1.3.0／taxonomy 1.1.0）",
        "disposition_of_fix1_merges": dict(disposition),
        "exposure": {
            "double_counted_pas": len(exposed),
            "affected_games": len({e["game"] for e in exposed}),
            "by_year": dict(sorted(collections.Counter(
                e["game"].split("/")[0] for e in exposed).items())),
            "by_outcome": dict(outcome_counter.most_common()),
            "rows": exposed,
        },
        "h1_batting_order_shift": {
            "hypothesis": "多出的 PA 使 pa_seq 進位，該場該隊其後所有 PA 的打序歸屬整體位移 1"
                          "（splits_calc: order = seq %% 9 + 1，家族 10 ORDER_NAMES）",
            "affected_team_games": len(order_shift),
            "total_pas_misattributed": sum(r["pas_after_shift"] for r in order_shift),
            "rows": order_shift,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from-year", type=int, default=2018)
    ap.add_argument("--to-year", type=int, default=2026)
    ap.add_argument("--kind", action="append", default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    kinds = args.kind or ["A", "C", "D", "E"]

    rep = collect(args.from_year, args.to_year, kinds)
    s, ex, h1 = rep["scope"], rep["exposure"], rep["h1_batting_order_shift"]
    print(f"scope: {s['games']} games / {s['events']} events")
    print(f"FIX1 誤切在 splits_calc 的去向：{rep['disposition_of_fix1_merges']}")
    print(f"**實際重複計為 PA**：{ex['double_counted_pas']} 筆／{ex['affected_games']} 場")
    print(f"  逐年：{ex['by_year']}")
    print(f"  重複記的結果詞：{dict(list(ex['by_outcome'].items())[:8])}")
    print(f"H1 打序位移：{h1['affected_team_games']} 個 (場次,球隊) 受影響，"
          f"其後被錯誤歸類打序的 PA 共 **{h1['total_pas_misattributed']}** 筆")
    if args.out:
        args.out.write_text(json.dumps(rep, ensure_ascii=False, indent=2, default=str) + "\n",
                            encoding="utf-8")
        print(f"→ {args.out}")


if __name__ == "__main__":
    main()
