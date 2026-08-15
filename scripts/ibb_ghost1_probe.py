# LIFECYCLE: oneshot · 卡片一次性產物——不要跑；刪除須需求方裁定（INGEST-SPLITS-IBB-GHOST1）
"""INGEST-SPLITS-IBB-GHOST1 探針：零投球「故四」幽靈島的官方語意查證。

子指令：
  seats     枚舉 2025 A/D 被幽靈島規則丟棄、結果為「故四」的島（逐席證據）。
  expect    對受影響打者：印出我方 `batting_splits` 家族 1/3 現值，
            以及「若官方計入」應多出的精確數（逐格）。
  official  以既有 apart 爬蟲（`cpbl_player_detail._Session`）取官方分項原始值。
            **單次嘗試**：失敗即 exit 1，不重試（HiNet 節流紅線）。
  compare   官方 JSON × 我方 DB 逐格對照，輸出差額表。
  recalc1   RECALC1 期望 grid（`ingest_splits_pa_split1_player_delta.json`）
            對受影響打者家族 3 格的涵蓋率——重驗「全命中」宣稱的適用範圍。

只讀 DB，不寫任何表。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from cpbl.db import conn

ROOT = Path(__file__).resolve().parents[1]
YEAR = 2025
KINDS = ("A", "D")
IBB_OUTCOME = "故四"

# 家族 3 = vs 投手（左/右投、本土/外籍投手）；家族 1 = 主客場（整島被丟時同樣少算）
FAMILY_ITEMS = {
    "1": ("主場", "客場"),
    "3": ("VS. 左投", "VS. 右投", "VS. 本土投手", "VS. 外籍投手"),
}


# ── 幽靈島枚舉（切島邏輯與 splits_calc.calc_t2 同源）──────────────────────────

def ghost_seats(outcome_filter: str | None = IBB_OUTCOME,
                year: int = YEAR, kinds: tuple = KINDS) -> list[dict]:
    """整島無投球列、但帶合法結果詞彙的島。outcome_filter=None → 全部結果詞彙。"""
    from cpbl.ingest.splits_calc import PA_OUTCOME
    from cpbl.ingest.splits_pa_merge import merge_plan

    found: list[dict] = []
    for kind in kinds:
        merges, merge_info = merge_plan(year, kind, PA_OUTCOME)
        with conn() as c:
            rows = c.execute(
                "SELECT game_sno, inning_seq, visiting_home_type, main_event_no, "
                "       hitter_acnt, pitcher_acnt, batting_action_name, is_strike, is_ball "
                "FROM cpbl.game_livelog WHERE year = %s AND kind_code = %s "
                "ORDER BY game_sno, inning_seq, visiting_home_type, main_event_no",
                (year, kind)).fetchall()

        def flush(island: list, info: dict | None, kind: str = kind) -> None:
            outcome = next((r[6] for r in reversed(island) if r[6]), None)
            if not outcome or PA_OUTCOME.get(outcome) is None:
                return
            if any(r[7] or r[8] for r in island):     # 有投球列 → 非幽靈島
                return
            if outcome_filter is not None and outcome != outcome_filter:
                return
            hitter = (info or {}).get("charged_hitter") or island[0][4]
            found.append({
                "kind_code": kind, "game_sno": island[0][0],
                "start_event_no": island[0][3], "end_event_no": island[-1][3],
                "hitter_acnt": hitter, "pitcher_acnt": island[-1][5],
                "outcome": outcome, "merged": info is not None,
                "vht": island[0][2], "inning_seq": island[0][1],
            })

        cur_game, island, ikey, cur_info = None, [], None, None
        for r in rows:
            sno = r[0]
            if sno != cur_game:
                if island:
                    flush(island, cur_info)
                cur_game, island, ikey, cur_info = sno, [], None, None
            if not r[4]:
                continue
            key = (r[1], r[2], r[4])
            if key != ikey:
                if island and (sno, r[3]) in merges:
                    cur_info = merge_info[(sno, r[3])]
                    ikey = key
                else:
                    if island:
                        flush(island, cur_info)
                    island, ikey, cur_info = [], key, None
            island.append(r)
        if island:
            flush(island, cur_info)
    return found


def _enrich(seats: list[dict]) -> list[dict]:
    """補球員姓名／投手慣用手／國籍／比賽日期，並標出應加計的家族 3 item。"""
    from cpbl.ingest.splits_calc import _is_local

    with conn() as c:
        bio = {r[0]: (r[1] or "", r[2] or "", r[3] or "", r[4] or "")
               for r in c.execute(
                   "SELECT id, name, bats, throws, country FROM cpbl.players").fetchall()}
        gdates = {(r[0], r[1]): r[2] for r in c.execute(
            "SELECT kind_code, game_sno, game_date FROM cpbl.games WHERE year = %s",
            (YEAR,)).fetchall()}
        pa_rows = {(r[0], r[1], r[2]) for r in c.execute(
            """
            SELECT pa.kind_code, pa.game_sno, pa.start_event_no
            FROM cpbl.game_plate_appearances pa
            JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id
            WHERE pa.year = %s AND b.state = 'published' AND pa.state = 'ready'
            """, (YEAR,)).fetchall()}

    out = []
    for s in seats:
        hname, _hb, _ht, hcountry = bio.get(s["hitter_acnt"], ("", "", "", ""))
        pname, _pb, pthrows, pcountry = bio.get(s["pitcher_acnt"], ("", "", "", ""))
        items = []
        if pthrows in ("左投", "右投"):
            items.append(f"VS. {pthrows}")
        if pcountry:
            items.append("VS. 本土投手" if _is_local(s["pitcher_acnt"], pcountry)
                         else "VS. 外籍投手")
        gd = gdates.get((s["kind_code"], s["game_sno"]))
        out.append({**s, "hitter_name": hname, "hitter_country": hcountry,
                    "pitcher_name": pname, "pitcher_throws": pthrows,
                    "pitcher_country": pcountry, "family3_items": items,
                    "family1_item": "主場" if s["vht"] == "2" else "客場",
                    "game_date": gd.isoformat() if gd else None,
                    "in_canonical_pa": (s["kind_code"], s["game_sno"],
                                        s["start_event_no"]) in pa_rows})
    return out


# ── 我方現值 ────────────────────────────────────────────────────────────────

def all_islands(kind: str, year: int = YEAR) -> list[dict]:
    """全部島（含幽靈島），帶 has_pitch／outcome／delta——供逐場 PA 對帳。"""
    from cpbl.ingest.splits_calc import PA_OUTCOME
    from cpbl.ingest.splits_pa_merge import merge_plan

    merges, merge_info = merge_plan(year, kind, PA_OUTCOME)
    with conn() as c:
        rows = c.execute(
            "SELECT game_sno, inning_seq, visiting_home_type, main_event_no, "
            "       hitter_acnt, pitcher_acnt, batting_action_name, is_strike, is_ball "
            "FROM cpbl.game_livelog WHERE year = %s AND kind_code = %s "
            "ORDER BY game_sno, inning_seq, visiting_home_type, main_event_no",
            (year, kind)).fetchall()

    out: list[dict] = []

    def flush(island: list, info: dict | None) -> None:
        outcome = next((r[6] for r in reversed(island) if r[6]), None)
        delta = PA_OUTCOME.get(outcome) if outcome else None
        if delta is None:
            return
        hitter = (info or {}).get("charged_hitter") or island[0][4]
        # 末球錨定：計入島取「最後一顆投球列」的投手（與 calc_t2 同源）；
        # 無投球島退回末列（手勢故四的結果列即末列）
        lp = next((i for i in range(len(island) - 1, -1, -1)
                   if island[i][7] or island[i][8]), None)
        anchor = island[lp] if lp is not None else island[-1]
        out.append({"game_sno": island[0][0], "hitter_acnt": hitter,
                    "pitcher_acnt": anchor[5],
                    "outcome": outcome, "delta": delta,
                    "has_pitch": lp is not None,
                    "start_event_no": island[0][3]})

    cur_game, island, ikey, cur_info = None, [], None, None
    for r in rows:
        sno = r[0]
        if sno != cur_game:
            if island:
                flush(island, cur_info)
            cur_game, island, ikey, cur_info = sno, [], None, None
        if not r[4]:
            continue
        key = (r[1], r[2], r[4])
        if key != ikey:
            if island and (sno, r[3]) in merges:
                cur_info = merge_info[(sno, r[3])]
                ikey = key
            else:
                if island:
                    flush(island, cur_info)
                island, ikey, cur_info = [], key, None
        island.append(r)
    if island:
        flush(island, cur_info)
    return out


def cmd_impact(args: argparse.Namespace) -> int:
    """跨年影響面：以官方逐場 box 為準，逐年逐賽別算「被幽靈島規則丟掉的真打席」。

    `official_extra = 官方 box PA − 我方計入島 PA`（僅統計含幽靈島的 場次×打者）。
    判準 `has_result_row` 的預測數同時輸出，供跨年一致性檢查。
    """
    NOISE = ("更換", "教練暫停", "暫停", "抗議", "裁判")
    out: list[dict] = []
    for year in range(args.from_year, args.to_year + 1):
        for kind in args.kinds:
            with conn() as c:
                n_log = c.execute(
                    "SELECT count(*) FROM cpbl.game_livelog "
                    "WHERE year = %s AND kind_code = %s", (year, kind)).fetchone()[0]
            if not n_log:
                continue
            isl = all_islands(kind, year)
            ghosts = ghost_seats(None, year, (kind,))
            with conn() as c:
                off = {(r[0], r[1]): r[2] for r in c.execute(
                    "SELECT game_sno, hitter_acnt, plate_appearances "
                    "FROM cpbl.batting_gamelog WHERE year = %s AND kind_code = %s",
                    (year, kind)).fetchall()}
                content: dict[int, list[tuple]] = {}
                for r in c.execute(
                        "SELECT game_sno, main_event_no, content FROM cpbl.game_livelog "
                        "WHERE year = %s AND kind_code = %s", (year, kind)).fetchall():
                    content.setdefault(r[0], []).append((r[1], r[2] or ""))
            for g in ghosts:
                seq = [c2 for ev, c2 in sorted(content.get(g["game_sno"], []))
                       if g["start_event_no"] <= ev <= g["end_event_no"]]
                g["has_result_row"] = any(
                    c2.strip() and not any(n in c2 for n in NOISE) for c2 in seq)
            pairs: dict[tuple, dict] = {}
            for g in ghosts:
                pairs.setdefault((g["game_sno"], g["hitter_acnt"]),
                                 {"ghosts": [], "counted": 0})["ghosts"].append(g)
            for i in isl:
                key = (i["game_sno"], i["hitter_acnt"])
                if key in pairs and i["has_pitch"]:
                    pairs[key]["counted"] += i["delta"].get("pa", 0)
            extra = pred = matched = pairs_with_off = 0
            by_outcome: dict[str, int] = {}
            misses: list[dict] = []
            for (sno, acnt), v in sorted(pairs.items()):
                o = off.get((sno, acnt))
                if o is None:
                    continue
                pairs_with_off += 1
                k = o - v["counted"]
                p = sum(1 for g in v["ghosts"] if g["has_result_row"])
                extra += k
                pred += p
                if k == p:
                    matched += 1
                else:
                    misses.append({
                        "year": year, "kind": kind, "game_sno": sno, "acnt": acnt,
                        "official_pa": o, "counted_pa": v["counted"],
                        "official_extra": k, "predicted": p,
                        "ghosts": [{"outcome": g["outcome"],
                                    "ev": g["start_event_no"],
                                    "has_result_row": g["has_result_row"]}
                                   for g in v["ghosts"]]})
                for g in v["ghosts"]:
                    if g["has_result_row"]:
                        by_outcome[g["outcome"]] = by_outcome.get(g["outcome"], 0) + 1
            out.append({
                "year": year, "kind": kind,
                "ghost_islands": len(ghosts),
                "pairs_with_official_box": pairs_with_off,
                "official_extra_pa": extra,
                "predicted_by_has_result_row": pred,
                "pairs_criterion_matched": matched,
                "criterion_exact": matched == pairs_with_off,
                "real_pa_by_outcome": dict(sorted(by_outcome.items(),
                                                  key=lambda kv: -kv[1])),
                "criterion_mismatches": misses,
            })
    _emit({"scope": f"{args.from_year}–{args.to_year} {'/'.join(args.kinds)}",
           "ground_truth": "cpbl.batting_gamelog（官方逐場 box）",
           "total_ghost_islands": sum(r["ghost_islands"] for r in out),
           "total_real_pa_dropped": sum(r["official_extra_pa"] for r in out),
           "total_pairs": sum(r["pairs_with_official_box"] for r in out),
           "pairs_criterion_matched": sum(r["pairs_criterion_matched"] for r in out),
           "years_criterion_exact": sum(1 for r in out if r["criterion_exact"]),
           "years_total": len(out),
           "criterion_mismatches": [m for r in out for m in r["criterion_mismatches"]],
           "rows": out}, args.out)
    return 0


def cmd_label(args: argparse.Namespace) -> int:
    """以官方逐場 box 當 ground truth，驗證「哪些幽靈島是真打席」的判準。

    對每個含幽靈島的 (場次, 打者)：`k = 官方 box PA − 我方計入島 PA`
    ＝官方認定為真打席的幽靈島數。逐判準比對預測數與 k，全母體逐對檢查。

    候選判準：
      A. `has_result_row`：島內任一列 content 不只是換人／教練暫停，而帶結果敘述。
      B. `in_canonical_pa`：canonical PA builder（pa-build-1.3.0）自己的判定。
      C. `is_ibb`：島的結果詞彙 ＝ 故四（現行卡面假設的窄口徑）。
    """
    NOISE = ("更換", "教練暫停", "暫停", "抗議", "裁判")
    rows: list[dict] = []
    for kind in KINDS:
        isl = all_islands(kind)
        ghosts = _enrich([g for g in ghost_seats(None) if g["kind_code"] == kind])
        with conn() as c:
            off = {(r[0], r[1]): r[2] for r in c.execute(
                "SELECT game_sno, hitter_acnt, plate_appearances "
                "FROM cpbl.batting_gamelog WHERE year = %s AND kind_code = %s",
                (YEAR, kind)).fetchall()}
            content: dict[tuple, list[tuple]] = {}
            for r in c.execute(
                    "SELECT game_sno, main_event_no, content, is_change_player "
                    "FROM cpbl.game_livelog WHERE year = %s AND kind_code = %s",
                    (YEAR, kind)).fetchall():
                content.setdefault(r[0], []).append((r[1], r[2] or "", r[3]))
        for g in ghosts:
            seq = [c2 for ev, c2, _chg in sorted(content.get(g["game_sno"], []))
                   if g["start_event_no"] <= ev <= g["end_event_no"]]
            body = " ".join(seq).strip()
            stripped = body
            for n in NOISE:
                stripped = stripped.replace(n, "")
            g["has_result_row"] = bool(
                [c2 for c2 in seq
                 if c2.strip() and not any(n in c2 for n in NOISE)])
            g["contents"] = seq
        pairs: dict[tuple, dict] = {}
        for g in ghosts:
            k = pairs.setdefault((g["game_sno"], g["hitter_acnt"]),
                                 {"ghosts": [], "counted": 0})
            k["ghosts"].append(g)
        for i in isl:
            key = (i["game_sno"], i["hitter_acnt"])
            if key in pairs and i["has_pitch"]:
                pairs[key]["counted"] += i["delta"].get("pa", 0)
        for (sno, acnt), v in sorted(pairs.items()):
            o = off.get((sno, acnt))
            if o is None:
                continue
            k = o - v["counted"]
            gs = v["ghosts"]
            rows.append({
                "kind": kind, "game_sno": sno, "acnt": acnt,
                "hitter": gs[0]["hitter_name"], "official_pa": o,
                "counted_pa": v["counted"], "official_extra": k,
                "ghosts": len(gs),
                "pred_result_row": sum(1 for g in gs if g["has_result_row"]),
                "pred_canonical": sum(1 for g in gs if g["in_canonical_pa"]),
                "pred_ibb": sum(1 for g in gs if g["outcome"] == IBB_OUTCOME),
                "outcomes": [g["outcome"] for g in gs],
            })
    def acc(field: str) -> dict:
        hit = sum(1 for r in rows if r[field] == r["official_extra"])
        return {"pairs_matched": hit, "pairs_total": len(rows),
                "mismatches": [r for r in rows if r[field] != r["official_extra"]][:20]}
    _emit({"scope": f"{YEAR} A/D 全部含幽靈島的 (場次, 打者)",
           "ground_truth": "cpbl.batting_gamelog（官方逐場 box）PA − 我方計入島 PA",
           "pairs": len(rows),
           "official_extra_total": sum(r["official_extra"] for r in rows),
           "ghost_islands_total": sum(r["ghosts"] for r in rows),
           "criterion_has_result_row": acc("pred_result_row"),
           "criterion_in_canonical_pa": acc("pred_canonical"),
           "criterion_is_ibb": acc("pred_ibb"),
           "rows": rows}, args.out)
    return 0


def cmd_gamelog(args: argparse.Namespace) -> int:
    """官方逐場 box（`batting_gamelog`，官網 getlive Batting）× 我方島級重建。

    每個受影響的 (場次, 打者)：官方 PA/BB/IBB 對我方「計入島」與「幽靈島」的加總。
    官方 == 計入島 → 官方排除；官方 == 計入島 + 幽靈島 → 官方計入。
    """
    seats = _enrich(ghost_seats())
    rows: list[dict] = []
    for kind in KINDS:
        ks = [s for s in seats if s["kind_code"] == kind]
        if not ks:
            continue
        isl = all_islands(kind)
        targets = {(s["game_sno"], s["hitter_acnt"]) for s in ks}
        with conn() as c:
            off = {(r[0], r[1]): (r[2], r[3], r[4], r[5]) for r in c.execute(
                "SELECT game_sno, hitter_acnt, plate_appearances, bb, ibb, at_bats "
                "FROM cpbl.batting_gamelog WHERE year = %s AND kind_code = %s",
                (YEAR, kind)).fetchall()}
        for sno, acnt in sorted(targets):
            mine = [i for i in isl if i["game_sno"] == sno and i["hitter_acnt"] == acnt]
            counted = [i for i in mine if i["has_pitch"]]
            ghost = [i for i in mine if not i["has_pitch"]]
            o = off.get((sno, acnt))
            name = next(s["hitter_name"] for s in ks
                        if s["game_sno"] == sno and s["hitter_acnt"] == acnt)

            def _sum(sel: list[dict], key: str) -> int:
                return sum(i["delta"].get(key, 0) for i in sel)

            rows.append({
                "kind": kind, "game_sno": sno, "acnt": acnt, "name": name,
                "official_pa": o[0] if o else None,
                "official_bb": o[1] if o else None,
                "official_ibb": o[2] if o else None,
                "ours_counted_pa": _sum(counted, "pa"),
                "ours_counted_ibb": _sum(counted, "ibb"),
                "ghost_pa": _sum(ghost, "pa"), "ghost_ibb": _sum(ghost, "ibb"),
                "ghost_outcomes": sorted({i["outcome"] for i in ghost}),
                "pa_gap_vs_counted": (None if not o else o[0] - _sum(counted, "pa")),
                "ibb_gap_vs_counted": (None if not o else o[2] - _sum(counted, "ibb")),
            })
    ok_excl = [r for r in rows if r["pa_gap_vs_counted"] == 0]
    ok_incl = [r for r in rows
               if r["pa_gap_vs_counted"] == r["ghost_pa"] and r["ghost_pa"] > 0]
    _emit({"scope": f"{YEAR} A/D 受幽靈故四影響的 (場次, 打者)",
           "source": "cpbl.batting_gamelog（官網 getlive Batting，官方逐場 box）",
           "pairs": len(rows),
           "official_equals_counted_only": len(ok_excl),
           "official_equals_counted_plus_ghost": len(ok_incl),
           "ibb_gap_zero": sum(1 for r in rows if r["ibb_gap_vs_counted"] == 0),
           "ibb_gap_equals_ghost": sum(1 for r in rows
                                       if r["ibb_gap_vs_counted"] == r["ghost_ibb"]
                                       and r["ghost_ibb"] > 0),
           "rows": rows}, args.out)
    return 0


def cmd_selfcheck(args: argparse.Namespace) -> int:
    """全母體內部一致性：家族 1（官方 gamelog 來源）vs 家族 3（livelog 島來源）。

    `calc_batting_t1` 的家族 1/8/9 直接加總官方單場 box（`batting_gamelog`），
    `calc_t2` 的家族 3 由 livelog 島重建——幽靈島規則只砍得到後者。故同一張表內
    「家族 1 總 PA」與「家族 3 左投＋右投」本應相等，差額即被規則丟掉的席次。
    本子指令對 2025 A/D **全體打者**掃描，證明差額集合恰等於幽靈島集合。
    """
    rows: list[dict] = []
    for kind in KINDS:
        isl = all_islands(kind)
        with conn() as c:
            f1 = {r[0]: r[1] for r in c.execute(
                "SELECT acnt, SUM(plate_appearances) FROM cpbl.batting_splits "
                "WHERE year = %s AND kind_code = %s AND item_group_code = '1' "
                "GROUP BY acnt", (YEAR, kind)).fetchall()}
            f3 = {r[0]: r[1] for r in c.execute(
                "SELECT acnt, SUM(plate_appearances) FROM cpbl.batting_splits "
                "WHERE year = %s AND kind_code = %s AND item_group_code = '3' "
                "  AND item_name = ANY(%s) GROUP BY acnt",
                (YEAR, kind, ["VS. 左投", "VS. 右投"])).fetchall()}
            throws = {r[0] for r in c.execute(
                "SELECT id FROM cpbl.players WHERE throws IS NOT NULL "
                "AND throws <> ''").fetchall()}
            future = {r[0] for r in c.execute(
                "SELECT game_sno FROM cpbl.games WHERE year = %s AND kind_code = %s "
                "  AND game_date > CURRENT_DATE", (YEAR, kind)).fetchall()}

        # 逐打者：計入島 PA、幽靈島 PA、計入島中投手缺 throws 的 PA
        agg: dict[str, dict[str, int]] = {}
        for i in isl:
            if i["game_sno"] in future:      # 保留賽殘段：兩側同樣排除
                continue
            a = agg.setdefault(i["hitter_acnt"],
                               {"counted": 0, "ghost_ibb": 0, "ghost_other": 0,
                                "no_throws": 0})
            pa = i["delta"].get("pa", 0)
            if not i["has_pitch"]:
                a["ghost_ibb" if i["outcome"] == IBB_OUTCOME else "ghost_other"] += pa
            else:
                a["counted"] += pa
                if i["pitcher_acnt"] not in throws:
                    a["no_throws"] += pa

        for acnt in sorted(set(f1) | set(f3) | set(agg)):
            a = agg.get(acnt, {"counted": 0, "ghost_ibb": 0, "ghost_other": 0,
                               "no_throws": 0})
            f1v, f3v = f1.get(acnt) or 0, f3.get(acnt) or 0
            gap = f1v - f3v
            row = {"kind": kind, "acnt": acnt, "family1_pa": f1v,
                   "family3_hand_pa": f3v, "counted_pa": a["counted"], "gap": gap,
                   "ghost_ibb_pa": a["ghost_ibb"], "ghost_other_pa": a["ghost_other"],
                   "missing_throws_pa": a["no_throws"],
                   # 官方 box（家族1）− 我方計入島 − 手勢故四 ＝ 0 表示「島級重建
                   # 與官方逐場 box 完全一致，唯一差額就是手勢故四」
                   "resid_box_vs_islands": f1v - a["counted"] - a["ghost_ibb"],
                   # 計入島 − 缺 throws 的島 − 家族3 ＝ 0 表示家族3 無其他漏算
                   "resid_family3": a["counted"] - a["no_throws"] - f3v}
            if gap or a["ghost_ibb"] or a["ghost_other"] or a["no_throws"]:
                rows.append(row)
    def _k(k: str, f: str) -> int:
        return sum(r[f] for r in rows if r["kind"] == k)

    _emit({
        "scope": f"{YEAR} A/D 全體打者（family1＝官方 gamelog；family3＝livelog 島）",
        "identity": "family1_pa − counted_pa − ghost_ibb_pa = 0  且  "
                    "counted_pa − missing_throws_pa − family3_hand_pa = 0",
        "rows_reported": len(rows),
        "by_kind": {k: {
            "rows": sum(1 for r in rows if r["kind"] == k),
            "gap_total": _k(k, "gap"),
            "ghost_ibb_total": _k(k, "ghost_ibb_pa"),
            "ghost_other_total": _k(k, "ghost_other_pa"),
            "missing_throws_total": _k(k, "missing_throws_pa"),
            "resid_box_vs_islands_total": _k(k, "resid_box_vs_islands"),
            "resid_box_vs_islands_nonzero_rows": sum(
                1 for r in rows if r["kind"] == k and r["resid_box_vs_islands"]),
            "resid_family3_total": _k(k, "resid_family3"),
            "resid_family3_nonzero_rows": sum(
                1 for r in rows if r["kind"] == k and r["resid_family3"]),
        } for k in KINDS},
        "resid_rows": [r for r in rows
                       if r["resid_box_vs_islands"] or r["resid_family3"]],
        "rows": rows}, args.out)
    return 0


def cmd_discriminate(args: argparse.Namespace) -> int:
    """幽靈島二分判準候選：島內是否含「結果敘述列」（content 帶結果句）。

    A/240 林岱安 是真幽靈（教練暫停列被結果字串傳播），A/240 胡金龍 是真手勢故四。
    對全部 26 席逐席印出島內 content，供第二階段修正方案設計判準。
    """
    seats = _enrich(ghost_seats())
    out = []
    for s in seats:
        with conn() as c:
            rows = c.execute(
                "SELECT main_event_no, hitter_acnt, is_change_player, content "
                "FROM cpbl.game_livelog WHERE year = %s AND kind_code = %s "
                "  AND game_sno = %s AND main_event_no >= %s AND main_event_no <= %s "
                "ORDER BY main_event_no",
                (YEAR, s["kind_code"], s["game_sno"],
                 s["start_event_no"], s["end_event_no"])).fetchall()
        contents = [(r[0], r[2], (r[3] or "").strip()) for r in rows]
        has_result = any("故意四壞球上壘" in c2 for _, _, c2 in contents)
        out.append({"kind": s["kind_code"], "game_sno": s["game_sno"],
                    "hitter": s["hitter_name"], "acnt": s["hitter_acnt"],
                    "start_event_no": s["start_event_no"],
                    "rows": [{"ev": e, "chg": ch, "content": c2}
                             for e, ch, c2 in contents],
                    "has_ibb_result_row": has_result,
                    "in_canonical_pa": s["in_canonical_pa"]})
    _emit({"seats": len(out),
           "with_ibb_result_row": sum(1 for o in out if o["has_ibb_result_row"]),
           "without_ibb_result_row": sum(1 for o in out
                                         if not o["has_ibb_result_row"]),
           "detail": out}, args.out)
    return 0


def our_values(acnts: list[str], kind: str, year: int = YEAR) -> dict:
    with conn() as c:
        rows = c.execute(
            "SELECT acnt, item_group_code, item_name, plate_appearances, at_bats, "
            "       bb, ibb, hits, rbi "
            "FROM cpbl.batting_splits "
            "WHERE year = %s AND kind_code = %s AND acnt = ANY(%s) "
            "  AND item_group_code IN ('1','3') ORDER BY acnt, item_group_code, item_name",
            (year, kind, acnts)).fetchall()
    return {f"{r[0]}|{r[1]}|{r[2]}": {"pa": r[3], "ab": r[4], "bb": r[5],
                                      "ibb": r[6], "hits": r[7], "rbi": r[8]}
            for r in rows}


def cmd_seats(args: argparse.Namespace) -> int:
    seats = _enrich(ghost_seats(None if args.all_outcomes else IBB_OUTCOME))
    payload = {"year": YEAR, "kinds": list(KINDS),
               "outcome_filter": None if args.all_outcomes else IBB_OUTCOME,
               "total": len(seats),
               "by_kind": {k: sum(1 for s in seats if s["kind_code"] == k) for k in KINDS},
               "by_outcome": _count(seats, "outcome"),
               "distinct_hitters": len({s["hitter_acnt"] for s in seats}),
               "in_canonical_pa": sum(1 for s in seats if s["in_canonical_pa"]),
               "seats": seats}
    _emit(payload, args.out)
    return 0


def _count(rows: list[dict], key: str) -> dict:
    out: dict[str, int] = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def cmd_expect(args: argparse.Namespace) -> int:
    seats = _enrich(ghost_seats())
    targets = args.acnt or sorted({s["hitter_acnt"] for s in seats})
    out: dict[str, Any] = {"year": YEAR, "batters": []}
    for acnt in targets:
        mine = [s for s in seats if s["hitter_acnt"] == acnt]
        for kind in sorted({s["kind_code"] for s in mine}):
            ks = [s for s in mine if s["kind_code"] == kind]
            ours = our_values([acnt], kind)
            cells = []
            for grp, items in FAMILY_ITEMS.items():
                for item in items:
                    n = sum(1 for s in ks
                            if (item in s["family3_items"] if grp == "3"
                                else item == s["family1_item"]))
                    cur = ours.get(f"{acnt}|{grp}|{item}")
                    cells.append({
                        "group": grp, "item": item,
                        "ours_pa": None if cur is None else cur["pa"],
                        "ours_bb": None if cur is None else cur["bb"],
                        "ours_ibb": None if cur is None else cur["ibb"],
                        "ghost_ibb_seats": n,
                        "expected_if_official_counts":
                            None if cur is None else cur["pa"] + n,
                    })
            out["batters"].append({
                "acnt": acnt, "name": ks[0]["hitter_name"], "kind_code": kind,
                "ghost_seats": len(ks),
                "seats": [{"game_sno": s["game_sno"], "game_date": s["game_date"],
                           "pitcher": s["pitcher_name"], "throws": s["pitcher_throws"],
                           "in_canonical_pa": s["in_canonical_pa"]} for s in ks],
                "cells": cells})
    _emit(out, args.out)
    return 0


# ── 官方值實查（單次嘗試）────────────────────────────────────────────────────

def cmd_official(args: argparse.Namespace) -> int:
    """官網 /team/apart 實查。單次嘗試，失敗 exit 1（不得連續重試）。"""
    from cpbl.ingest.cpbl_player_detail import _Session

    results: dict[str, Any] = {"year": args.year, "kind": args.kind,
                               "source": "www.cpbl.com.tw POST /team/getapartscore",
                               "players": {}}
    for acnt in args.acnt:
        sess = _Session(acnt, delay=args.delay)
        raw = sess.apart(args.year, args.kind, "01")
        results["players"][acnt] = raw
        print(f"[official] {acnt}: {len(raw)} 列", file=sys.stderr)
    _emit(results, args.out)
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    raw = json.loads(Path(args.official).read_text())
    year, kind = raw["year"], raw["kind"]
    seats = _enrich(ghost_seats())
    rows: list[dict] = []
    for acnt, items in raw["players"].items():
        ours = our_values([acnt], kind, year)
        ks = [s for s in seats
              if s["hitter_acnt"] == acnt and s["kind_code"] == kind]
        name = ks[0]["hitter_name"] if ks else acnt
        for it in items:
            grp, item = str(it.get("ItemGroupCode")), (it.get("ItemName") or "").strip()
            if grp not in FAMILY_ITEMS or item not in FAMILY_ITEMS[grp]:
                continue
            off_pa = it.get("PlateAppearances")
            off_bb, off_ibb = it.get("BasesONBallsCnt"), it.get("IntentionalBasesONBallsCnt")
            cur = ours.get(f"{acnt}|{grp}|{item}") or {}
            n = sum(1 for s in ks
                    if (item in s["family3_items"] if grp == "3"
                        else item == s["family1_item"]))
            rows.append({
                "acnt": acnt, "name": name, "group": grp, "item": item,
                "official_pa": off_pa, "ours_pa": cur.get("pa"),
                "diff_pa": (None if off_pa is None or cur.get("pa") is None
                            else off_pa - cur["pa"]),
                "official_bb": off_bb, "ours_bb": cur.get("bb"),
                "official_ibb": off_ibb, "ours_ibb": cur.get("ibb"),
                "diff_ibb": (None if off_ibb is None or cur.get("ibb") is None
                             else off_ibb - cur["ibb"]),
                "ghost_ibb_seats": n})
    verdict = _verdict(rows)
    _emit({"year": year, "kind": kind, "rows": rows, "verdict": verdict}, args.out)
    return 0


def _verdict(rows: list[dict]) -> dict:
    """可證偽判定。兩個混淆因子必須先隔離，否則差額會被誤讀：

    1. **家族 1（主客場）不是 livelog 來源**：`calc_batting_t1` 直接加總官方逐場 box
       （`batting_gamelog`），幽靈島規則碰不到它，故家族 1 兩側本來就已含這些席次
       ——它是「我方 == 官方」的對照組，不是待測格。
    2. **缺場 box**：我方 `batting_gamelog` 若少了某場，該打者所有格都會少，與幽靈島
       無關。以家族 1 的差額 (`box_gap`) 量測之；`box_gap == 0` 的打者才可用 PA 檢定。

    故：IBB 檢定（缺場未貢獻 IBB，全員可用）＋ PA 檢定（限 box_gap == 0 的打者）。
    """
    f1 = [r for r in rows if r["group"] == "1"]
    f3 = [r for r in rows if r["group"] == "3"]
    box_gap = {}
    for r in f1:
        box_gap[r["acnt"]] = box_gap.get(r["acnt"], 0) + (r["diff_pa"] or 0)
    clean = {a for a, g in box_gap.items() if g == 0}

    ibb_hit = [r for r in f3 if r["diff_ibb"] == r["ghost_ibb_seats"]]
    pa_cells = [r for r in f3 if r["acnt"] in clean]
    pa_hit = [r for r in pa_cells if r["diff_pa"] == r["ghost_ibb_seats"]]
    return {
        "family1_control_cells": len(f1),
        "family1_ibb_diff_zero": sum(1 for r in f1 if r["diff_ibb"] == 0),
        "box_gap_by_player": box_gap,
        "players_without_box_gap": sorted(clean),
        "ibb_test_cells": len(f3),
        "ibb_test_matched": len(ibb_hit),
        "ibb_test_mismatches": [r for r in f3 if r not in ibb_hit],
        "pa_test_cells": len(pa_cells),
        "pa_test_matched": len(pa_hit),
        "pa_test_mismatches": [r for r in pa_cells if r not in pa_hit],
        "control_cells_zero_ghost": sum(1 for r in f3 if r["ghost_ibb_seats"] == 0),
        "control_cells_zero_ghost_zero_diff": sum(
            1 for r in f3 if r["ghost_ibb_seats"] == 0 and r["diff_ibb"] == 0),
        "verdict": ("official_counts_gesture_ibb"
                    if ibb_hit and len(ibb_hit) == len(f3)
                       and any(r["ghost_ibb_seats"] for r in f3)
                    else "inconclusive"),
    }


# ── RECALC1 grid 涵蓋率重驗 ─────────────────────────────────────────────────

def cmd_recalc1(args: argparse.Namespace) -> int:
    delta = json.loads((ROOT / "docs/research/ingest_splits_pa_split1_player_delta.json")
                       .read_text())
    seats = _enrich(ghost_seats())
    affected = {(s["kind_code"], s["hitter_acnt"]) for s in seats}
    grid_keys = {(r["table"], r["year"], r["kind"], r["acnt"], r["group"], r["item_name"])
                 for r in delta["rows"]}
    covered, missing = [], []
    for kind, acnt in sorted(affected):
        ks = [s for s in seats if s["kind_code"] == kind and s["hitter_acnt"] == acnt]
        for grp, items in FAMILY_ITEMS.items():
            for item in items:
                n = sum(1 for s in ks
                        if (item in s["family3_items"] if grp == "3"
                            else item == s["family1_item"]))
                if n == 0:
                    continue
                key = ("batting_splits", YEAR, kind, acnt, grp, item)
                (covered if key in grid_keys else missing).append(
                    {"kind": kind, "acnt": acnt, "name": ks[0]["hitter_name"],
                     "group": grp, "item": item, "ghost_seats": n})
    _emit({
        "grid_rows_total": len(delta["rows"]),
        "grid_generated_at": delta["generated_at"],
        "grid_note": delta["note"],
        "affected_batter_kind_pairs": len(affected),
        "affected_cells_total": len(covered) + len(missing),
        "affected_cells_in_grid": len(covered),
        "affected_cells_not_in_grid": len(missing),
        "covered": covered, "missing": missing,
    }, args.out)
    return 0


def _emit(payload: dict, out: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if out:
        Path(out).write_text(text)
        print(f"→ {out}", file=sys.stderr)
    print(text)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("seats")
    p.add_argument("--all-outcomes", action="store_true")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_seats)

    p = sub.add_parser("expect")
    p.add_argument("--acnt", nargs="*")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_expect)

    p = sub.add_parser("official")
    p.add_argument("--acnt", nargs="+", required=True)
    p.add_argument("--year", type=int, default=YEAR)
    p.add_argument("--kind", default="A")
    p.add_argument("--delay", type=float, default=1.5)
    p.add_argument("--out")
    p.set_defaults(fn=cmd_official)

    p = sub.add_parser("compare")
    p.add_argument("--official", required=True)
    p.add_argument("--out")
    p.set_defaults(fn=cmd_compare)

    p = sub.add_parser("selfcheck")
    p.add_argument("--all-outcomes", action="store_true")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_selfcheck)

    p = sub.add_parser("discriminate")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_discriminate)

    p = sub.add_parser("impact")
    p.add_argument("--from-year", type=int, default=2018)
    p.add_argument("--to-year", type=int, default=2026)
    p.add_argument("--kinds", nargs="+", default=["A", "D"])
    p.add_argument("--out")
    p.set_defaults(fn=cmd_impact)

    p = sub.add_parser("label")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_label)

    p = sub.add_parser("gamelog")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_gamelog)

    p = sub.add_parser("recalc1")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_recalc1)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
