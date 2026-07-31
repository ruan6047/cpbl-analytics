"""canonical PA 合併邊界：修正 splits_calc 的代打誤切重複計數（INGEST-SPLITS-RECALC1）。

`INGEST-SPLITS-PA-SPLIT1`（merge cc339f5）定案：`calc_t2` 以 (inning, vht, hitter)
切島會把**打席中途代打**切成兩個 PA 重複計數（曝險 83 筆／82 場）。本模組以
canonical `pa_build`（pa-build-1.3.0，六輪跨家族查核定案）列舉跨打者 transition、
映射回 legacy 島界，輸出：

- 「不得切界」的邊界集合 {(game_sno, 次段首列 main_event_no)}；
- 每個邊界的歸屬解析：打者依規則 9.15(b)（`charged_hitter`）、投手責任依
  末球錨定＋9.16(h)(1) 四壞例外（`responsible_pitcher`）。

語意與 `scripts/verify_splits_pa_split1.py` 的 corrected 模擬器一致（該腳本經
18 pairs 保真閘＋逐投手投球數守恆不變量＋跨家族查核 APPROVE）；只合併
legacy 去向為 counted 的缺陷邊界，ghost／skipped 維持 legacy 行為，使重建 diff
嚴格對應已查核的預期 delta。

`pa_outcome` 以參數注入（避免與 splits_calc 循環 import）。
"""
from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from cpbl.db import conn
from cpbl.ingest.pa_build import (
    _clean,
    _terminal_event,
    build_islands,
    charged_hitter,
    event_sort_key,
)

Row = dict[str, Any]

# calc_t2 讀的 18 欄＋canonical 判準與 9.16(h) 需要的 4 欄（ball_cnt/strike_cnt/
# action_name/pitch_cnt）；列序必須與 calc_t2 相同
_FETCH_COLS = (
    "game_sno, inning_seq, visiting_home_type, main_event_no, hitter_acnt, "
    "pitcher_acnt, batting_order, out_cnt, first_base, second_base, third_base, "
    "batting_action_name, is_strike, is_ball, visiting_score, home_score, "
    "is_change_player, content, pitch_cnt, action_name, ball_cnt, strike_cnt"
)

# 9.16(h)(1)：後援投手接手時球數為 2-0/2-1/3-0/3-1/3-2 且該打席四壞 → 記前任投手
_WALK_OUTCOMES = frozenset({"四壞", "故四"})
_ADVANTAGE_COUNTS = frozenset({(2, 0), (2, 1), (3, 0), (3, 1), (3, 2)})


def _fetch(year: int, kind: str) -> list[Row]:
    with conn() as c:
        c.execute("SET TRANSACTION READ ONLY")
        cur = c.cursor(row_factory=dict_row)
        cur.execute(
            f"SELECT {_FETCH_COLS} FROM cpbl.game_livelog "  # noqa: S608
            "WHERE year = %s AND kind_code = %s "
            "ORDER BY game_sno, inning_seq, visiting_home_type, main_event_no",
            (year, kind),
        )
        return [dict(r) for r in cur.fetchall()]


def _legacy_islands(rows: list[Row]) -> list[list[Row]]:
    """重現 calc_t2 主迴圈的 (inning, vht, hitter) 切界（單場列）。"""
    out: list[list[Row]] = []
    island: list[Row] = []
    ikey = None
    for r in rows:
        if not r["hitter_acnt"]:
            continue
        key = (r["inning_seq"], r["visiting_home_type"], r["hitter_acnt"])
        if key != ikey:
            if island:
                out.append(island)
            island, ikey = [], key
        island.append(r)
    if island:
        out.append(island)
    return out


def _disposition(island: list[Row], pa_outcome: dict) -> tuple[str, str | None]:
    """flush() 的三道過濾：無結果 → 未登錄詞 → 幽靈島。回傳 (去向, outcome)。"""
    outcome = next((r["batting_action_name"] for r in reversed(island)
                    if r["batting_action_name"]), None)
    if not outcome:
        return "skipped_no_outcome", None
    if pa_outcome.get(outcome) is None:
        return "unknown_action", outcome
    if not any(r["is_strike"] or r["is_ball"] for r in island):
        return "ghost_island_no_pitch", outcome
    return "counted", outcome


def _count_after(row: Row) -> tuple[int, int]:
    b, s = row.get("ball_cnt"), row.get("strike_cnt")
    return (int(b) if b not in (None, "") else 0, int(s) if s not in (None, "") else 0)


def responsible_pitcher(island: list[Row], outcome: str) -> tuple[str, dict | None]:
    """合併島打席結果的責任投手：末球錨定；例外＝9.16(h)(1) 特定球數接手且四壞。"""
    pitch_rows = [r for r in island if r["is_strike"] or r["is_ball"]]
    last_p = pitch_rows[-1]["pitcher_acnt"]
    if outcome not in _WALK_OUTCOMES:
        return last_p, None
    prev_p, entry = None, None
    for a, b in zip(pitch_rows, pitch_rows[1:], strict=False):
        if a["pitcher_acnt"] != b["pitcher_acnt"]:
            prev_p, entry = a["pitcher_acnt"], _count_after(a)
    if prev_p is not None and entry in _ADVANTAGE_COUNTS:
        return prev_p, {"rule": "9.16(h)(1)", "entry_count": list(entry),
                        "charged_to_prev": prev_p, "relief": last_p}
    return last_p, None


def merge_plan(
    year: int, kind: str, pa_outcome: dict,
) -> tuple[frozenset[tuple[Any, Any]], dict[tuple[Any, Any], dict]]:
    """輸出 (合併邊界集合, 邊界 → 歸屬解析)。

    邊界 key＝(game_sno, 次段首列 main_event_no)，與 calc_t2 主迴圈在 key 變更列
    看到的 (sno, r[3]) 對齊。只收 legacy 去向 counted 的缺陷邊界。
    """
    boundaries: set[tuple[Any, Any]] = set()
    info: dict[tuple[Any, Any], dict] = {}
    rows = _fetch(year, kind)
    by_game: dict[Any, list[Row]] = {}
    for r in rows:
        by_game.setdefault(r["game_sno"], []).append(r)

    for sno, game_rows in by_game.items():
        islands = _legacy_islands(game_rows)
        idx_of = {r["main_event_no"]: i
                  for i, isl in enumerate(islands) for r in isl}
        # canonical：島內相鄰兩個成員列打者相異 ⇔ 一次被接受的合併
        for c_isl in build_islands(game_rows):
            ordered = sorted(c_isl, key=event_sort_key)
            prev_usable: Row | None = None
            pairs: list[tuple[Row, Row]] = []
            for ev in ordered:
                usable = (not ev.get("is_change_player")
                          and _clean(ev.get("hitter_acnt")) is not None)
                if (usable and prev_usable is not None
                        and _clean(ev["hitter_acnt"])
                        != _clean(prev_usable["hitter_acnt"])):
                    pairs.append((prev_usable, ev))
                if usable:
                    prev_usable = ev
            for a, b in pairs:
                i, j = idx_of[a["main_event_no"]], idx_of[b["main_event_no"]]
                if i == j:
                    continue
                why, _o = _disposition(islands[i], pa_outcome)
                if why != "counted":
                    continue  # ghost／skipped 維持 legacy，delta 嚴格對應缺陷邊界
                merged_rows = sorted(
                    (r for k in range(i, j + 1) for r in islands[k]),
                    key=event_sort_key)
                m_why, m_outcome = _disposition(merged_rows, pa_outcome)
                non_change = [e for e in merged_rows
                              if not e.get("is_change_player")]
                term = _terminal_event(non_change)
                act = _clean(term.get("action_name")) if term else None
                ch, _cp = charged_hitter(non_change, act)
                resp, rule_note = (responsible_pitcher(merged_rows, m_outcome)
                                   if m_why == "counted" else (None, None))
                entry = {"charged_hitter": ch, "responsible_pitcher": resp,
                         "rule_916h": rule_note}
                for m in range(i + 1, j + 1):
                    key = (sno, islands[m][0]["main_event_no"])
                    boundaries.add(key)
                    info[key] = entry
    return frozenset(boundaries), info
