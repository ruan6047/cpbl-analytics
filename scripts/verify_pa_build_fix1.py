# LIFECYCLE: oneshot · 卡片一次性產物——不要跑；刪除須需求方裁定（GAME-RECAP-PA1-FIX1）
"""GAME-RECAP-PA1-FIX1 對帳：修正前後的打席切分與出局數，全母體窮舉。

唯讀（`SET TRANSACTION READ ONLY`），不寫任何表。產出 JSON artifact 供查核者重跑對照——
卡面紅線要求「全部／零例外」等完整性宣稱**由腳本產生**，不得人工聲明。

修正前基線在本檔內以 `_legacy_islands()` 重建（＝FIX1 之前的 `build_islands`：
純以 `(inning, half, hitter)` 切界），故不需保留 builder 內的死碼即可對照。

    uv run python scripts/verify_pa_build_fix1.py --out docs/research/game_recap_pa1_fix1_metrics.json
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
    BATTER_OUT_FAMILIES,
    MAX_OUT_PA_PER_HALF_INNING,
    STATE_READY,
    STRIKEOUT_ACTIONS,
    Event,
    _clean,
    _is_real_pitch,
    _terminal_event,
    build_islands,
    continues_same_plate_appearance,
    derive_half_inning_outs,
    event_sort_key,
    load_taxonomy,
    plate_appearances,
)

COLS = (
    "year, kind_code, game_sno, main_event_no, inning_seq, visiting_home_type, "
    "batting_order, out_cnt, ball_cnt, strike_cnt, pitch_cnt, content, action_name, "
    "hitter_acnt, pitcher_acnt, is_strike, is_ball, is_change_player"
)


def _legacy_islands(events: list[Event]) -> list[list[Event]]:
    """FIX1 之前的切分：打者一變就切界（重建基線用，勿在正式路徑使用）。"""
    islands: list[list[Event]] = []
    prev_key = None
    for ev in sorted(events, key=event_sort_key):
        if ev.get("is_change_player") or not _clean(ev.get("hitter_acnt")):
            if islands:
                islands[-1].append(ev)
            continue
        key = (ev.get("inning_seq"), str(ev.get("visiting_home_type")),
               _clean(ev.get("hitter_acnt")))
        if key != prev_key:
            islands.append([])
            prev_key = key
        islands[-1].append(ev)
    return islands


def _half(ev: Event) -> tuple[Any, str]:
    return (ev.get("inning_seq"), str(ev.get("visiting_home_type")))


def _out_pa_slots(islands: list[list[Event]], taxonomy: Any,
                  outs_of: dict[str, tuple[int, int]] | None) -> tuple[
                      collections.Counter, collections.Counter]:
    """回傳 (每半局 out-PA 數, 每 (半局, pre_outs) 的 out-PA 數)。

    ``outs_of=None`` → 沿用 livelog ``out_cnt``（修正前的來源）。
    """
    per_half: collections.Counter = collections.Counter()
    per_slot: collections.Counter = collections.Counter()
    for island in islands:
        ordered = sorted(island, key=event_sort_key)
        term = _terminal_event(ordered)
        action = _clean(term.get("action_name")) if term else None
        entry = taxonomy.entry(action) if action else None
        if not entry or entry["role"] == "non_pa":
            continue
        if entry.get("outcome_family") not in BATTER_OUT_FAMILIES:
            continue
        members = [e for e in ordered if not e.get("is_change_player")]
        if not members:
            continue
        start = members[0]
        outs = (outs_of[str(start["main_event_no"])][0] if outs_of is not None
                else _clean(start.get("out_cnt")))
        per_half[_half(start)] += 1
        per_slot[(_half(start), outs)] += 1
    return per_half, per_slot


def _attribution_rows(year: int, kind: str, sno: int, events: list[Event],
                      taxonomy: Any) -> list[dict[str, Any]]:
    """跨打者打席的 9.15(b) 歸屬明細（走**正式**程式路徑，不另寫簡化判定）。

    iteration 2 的交付統計用簡化的 `action == "三振"` 自行判定，與正式的
    `STRIKEOUT_ACTIONS` 不一致而少算一筆（查核 Major）。此處直接消費
    `plate_appearances()` 的結果，杜絕統計與程式分家。
    """
    rows: list[dict[str, Any]] = []
    for pa in plate_appearances(year, kind, sno, events, taxonomy):
        member_hitters = [h for h in (m_h for m_h in _member_hitters(events, pa)) if h]
        if len(set(member_hitters)) < 2:
            continue
        rows.append({
            "game": f"{year}/{kind}/{sno}",
            "start_event_no": pa.start_event_no, "end_event_no": pa.end_event_no,
            "result_action": pa.result_action, "outcome_family": pa.outcome_family,
            "state": pa.state,
            "hitters_in_order": member_hitters,
            "charged_hitter_acnt": pa.hitter_acnt,
            "end_hitter_acnt": pa.end_hitter_acnt,
            "is_strikeout_action": pa.result_action in STRIKEOUT_ACTIONS,
            "verdict": ("charged_to_original" if pa.hitter_acnt != pa.end_hitter_acnt
                        else "charged_to_completing"),
        })
    return rows


def _member_hitters(events: list[Event], pa: Any) -> list[str | None]:
    """PA 成員事件的打者序（非換人列）。"""
    by_no = {str(e.get("main_event_no")): e for e in events}
    out: list[str | None] = []
    for m in pa.members:
        ev = by_no.get(m.event_no)
        if ev is not None and not ev.get("is_change_player"):
            out.append(_clean(ev.get("hitter_acnt")))
    return out


def collect(from_year: int, to_year: int, kinds: list[str]) -> dict[str, Any]:
    taxonomy = load_taxonomy()
    with conn() as c:
        c.execute("SET TRANSACTION READ ONLY")
        cur = c.cursor(row_factory=dict_row)
        cur.execute(
            f"SELECT {COLS} FROM cpbl.game_livelog "  # noqa: S608 (固定欄位常數)
            "WHERE year BETWEEN %s AND %s AND kind_code = ANY(%s)",
            (from_year, to_year, kinds),
        )
        rows = [dict(r) for r in cur.fetchall()]

    games: dict[tuple[int, str, int], list[Event]] = collections.defaultdict(list)
    for r in rows:
        games[(r["year"], r["kind_code"], r["game_sno"])].append(r)

    merges: list[dict[str, Any]] = []
    reason_counts: collections.Counter = collections.Counter()
    year_counts: collections.Counter = collections.Counter()
    before_over: list[str] = []
    after_over: list[dict[str, Any]] = []
    before_dup = after_dup = 0
    outs_changed: list[dict[str, Any]] = []
    baseline_islands = [0, 0]          # [有真實投球的 legacy island 數, 其中不一致數]
    baseline_hist: collections.Counter = collections.Counter()
    attribution: list[dict[str, Any]] = []

    for (year, kind, sno), events in sorted(games.items()):
        outs_of = derive_half_inning_outs(events)

        # 逐一列出被合併的 island 對（重跑 legacy 分組並套用判準）
        legacy = _legacy_islands(events)
        for prev, cur_isl in zip(legacy, legacy[1:], strict=False):
            pm = [e for e in prev if not e.get("is_change_player")]
            cm = [e for e in cur_isl if not e.get("is_change_player")]
            if not pm or not cm or _half(pm[-1]) != _half(cm[0]):
                continue
            reason = continues_same_plate_appearance(prev, cm[0])
            if not reason:
                continue
            reason_counts[reason] += 1
            year_counts[year] += 1
            merges.append({
                "game": f"{year}/{kind}/{sno}", "reason": reason,
                "inning": cm[0].get("inning_seq"), "half": str(cm[0].get("visiting_home_type")),
                "batting_order": cm[0].get("batting_order"),
                "from_event": str(pm[-1]["main_event_no"]),
                "to_event": str(cm[0]["main_event_no"]),
                "from_hitter": _clean(pm[-1].get("hitter_acnt")),
                "to_hitter": _clean(cm[0].get("hitter_acnt")),
                "result_action": _clean(cm[0].get("action_name")),
            })

        attribution += _attribution_rows(year, kind, sno, events, taxonomy)

        b_half, b_slot = _out_pa_slots(legacy, taxonomy, None)
        a_half, a_slot = _out_pa_slots(build_islands(events), taxonomy, outs_of)
        before_over += [f"{year}/{kind}/{sno} i{h[0]}h{h[1]} out_pa={n}"
                        for h, n in b_half.items() if n > MAX_OUT_PA_PER_HALF_INNING]
        after_over += [{"game": f"{year}/{kind}/{sno}", "inning": h[0], "half": h[1], "out_pa": n}
                       for h, n in a_half.items() if n > MAX_OUT_PA_PER_HALF_INNING]
        before_dup += sum(1 for n in b_slot.values() if n > 1)
        after_dup += sum(1 for n in a_slot.values() if n > 1)

        # pre_state.outs 由 out_cnt 改推導後**實際變動**的 canonical PA 起點。
        # 注意這與「修正前基線」是不同母體，兩者不可互相引用（iteration 1 查核 Major）：
        #   基線＝修正**前**的 island 起點且島內有真實投球（診斷用）；
        #   本項＝修正**後**的 island 起點、不限有無投球（canonical 實際變動）。
        for island in build_islands(events):
            members = [e for e in sorted(island, key=event_sort_key)
                       if not e.get("is_change_player")]
            if not members:
                continue
            start = members[0]
            src = _clean(start.get("out_cnt"))
            der = outs_of[str(start["main_event_no"])][0]
            if src is not None and int(src) != der:
                outs_changed.append({
                    "game": f"{year}/{kind}/{sno}", "event": str(start["main_event_no"]),
                    "out_cnt": int(src), "derived": der,
                })
        # 修正前基線（供與 GLOSSARY／卡面的診斷數字對帳，母體定義如上）
        for island in legacy:
            members = [e for e in sorted(island, key=event_sort_key)
                       if not e.get("is_change_player")]
            if not members or not any(_is_real_pitch(e) for e in island):
                continue
            start = members[0]
            src = _clean(start.get("out_cnt"))
            der = outs_of[str(start["main_event_no"])][0]
            baseline_islands[0] += 1
            if src is not None and int(src) != der:
                baseline_islands[1] += 1
                baseline_hist[int(src) - der] += 1

    return {
        "generated_at": datetime.datetime.now().astimezone().isoformat(),
        "scope_note": "所有數字對「生成當下的本機 game_livelog 母體」成立；母體隨每日爬蟲增長，"
                      "重跑須以 scope.games/events 對齊比較（iteration 5 查核 Major）",
        "scope": {"from_year": from_year, "to_year": to_year, "kinds": kinds,
                  "games": len(games), "events": len(rows)},
        "merge": {
            "total_pairs": len(merges),
            "by_reason": dict(reason_counts),
            "by_year": {str(k): v for k, v in sorted(year_counts.items())},
            "pairs": merges,
        },
        "half_inning_out_invariant": {
            "max_out_pa": MAX_OUT_PA_PER_HALF_INNING,
            "before": len(before_over),
            "after": len(after_over),
            "after_violations": after_over,   # 修正後仍違反者＝fail closed 隔離對象
            "before_samples": before_over[:20],
        },
        "pre_outs_duplicates": {"before": before_dup, "after": after_dup},
        "pre_outs_source_change": {
            "population": "修正後的 canonical PA 起點（不限有無投球）＝實際寫入 DB 的變動",
            "changed": len(outs_changed),
            "diff_histogram": dict(sorted(collections.Counter(
                d["out_cnt"] - d["derived"] for d in outs_changed).items())),
            "changes": outs_changed,          # 逐筆全列，不截斷（查核可窮舉稽核）
        },
        "pre_outs_baseline_diagnostic": {
            "population": "修正**前**的 island 起點且島內有真實投球＝診斷基線，"
                          "與上一項是不同母體，數字不可互相引用",
            "islands_with_real_pitch": baseline_islands[0],
            "mismatched": baseline_islands[1],
            "diff_histogram": dict(sorted(baseline_hist.items())),
        },
        "hitter_attribution": {
            "rule": "記錄規則 9.15(b)：9.15(a) 定義的三振（含 (a)(3) 不死三振）由代打者完成"
                    "→ 記被判第 2 好球者；其他結果（含四壞球）→ 記代打者。",
            "cross_batter_pas": len(attribution),
            "by_verdict": dict(collections.Counter(r["verdict"] for r in attribution)),
            "by_result_action": dict(collections.Counter(
                str(r["result_action"]) for r in attribution).most_common()),
            "rows": attribution,          # 逐筆全列，不截斷
        },
        "ready_state_note": (
            f"out-PA 判定以 taxonomy outcome_family in {sorted(BATTER_OUT_FAMILIES)} "
            f"且 island 可分類為 pa_terminal 為準（對應 state={STATE_READY}）。"
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from-year", type=int, default=2018)
    ap.add_argument("--to-year", type=int, default=2026)
    ap.add_argument("--kind", action="append", default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    kinds = args.kind or ["A", "C", "D", "E"]

    report = collect(args.from_year, args.to_year, kinds)
    s, m = report["scope"], report["merge"]
    inv, dup, oc = (report["half_inning_out_invariant"], report["pre_outs_duplicates"],
                    report["pre_outs_source_change"])
    print(f"scope: {s['games']} games / {s['events']} events "
          f"({s['from_year']}–{s['to_year']} kinds={','.join(kinds)})")
    print(f"合併 island 對：{m['total_pairs']}　by_reason={m['by_reason']}")
    print(f"　　by_year={m['by_year']}")
    print(f"半局 out-PA > {inv['max_out_pa']}：{inv['before']} → {inv['after']}")
    for v in inv["after_violations"]:
        print(f"　　仍違反（fail closed 隔離）：{v['game']} i{v['inning']}h{v['half']} "
              f"out_pa={v['out_pa']}")
    print(f"(半局, pre_outs) 重複：{dup['before']} → {dup['after']}")
    bl = report["pre_outs_baseline_diagnostic"]
    print(f"pre_outs 實際變動（修正後 PA 起點）：{oc['changed']} 差值分布={oc['diff_histogram']}")
    at = report["hitter_attribution"]
    print(f"跨打者打席（9.15(b) 歸屬）：{at['cross_batter_pas']} 筆　{at['by_verdict']}")
    print(f"　　診斷基線（修正前、有真實投球的 island）："
          f"{bl['mismatched']}/{bl['islands_with_real_pitch']} 差值分布={bl['diff_histogram']}")
    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
        print(f"→ {args.out}")


if __name__ == "__main__":
    main()
