"""INGEST-SPLITS-PA-SPLIT1 查證（iteration 3）：`splits_calc` 重複計打席的範圍與選手層級影響。

**唯讀**（`SET TRANSACTION READ ONLY`；並記錄四張分項表執行前後筆數與 max(updated_at)
於 artifact 供查核），不寫任何表、不呼叫 `cpbl-build-splits`。

方法（iteration 2 REVIEW-004 處置＋iteration 3 REVIEW-007 處置）：

1. 以 canonical `build_islands()` 列舉全部跨打者 transition（並記錄判準 criterion），
   映射回 `splits_calc.flush()` 實際切出的 legacy island，依 flush 原始順序過三道過濾；
2. H1 打序位移以正確 spurious 集重算；
3. 選手層級量化：named-column 模擬器重現 `calc_t2`（保真閘＝與 `calc_t2` 逐格相等），
   corrected 模式僅合併 counted 缺陷邊界。**投球數依每列實際 `pitcher_acnt` 保留**
   （REVIEW-007 F1）；打席結果責任依 9.16(h)；打者歸屬依 canonical `charged_hitter`。
4. **完整發布欄位 delta**（REVIEW-007 F2）：記憶體重現 `build_splits` 的 writer row
   （T1＋gofo＋T2 → `_meta`＋`_bat_rates`），輸出 batting/pitching_splits 全欄位
   （含 avg/obp/slg/ops/goao）的 legacy／corrected diff；並以「assembled legacy row
   對 DB 已發布列逐格比對」驗證組裝層保真。
5. corrected 路徑以**機器不變量**支撐（REVIEW-007 F1 的保真缺口）：逐投手 family-5
   投球數守恆、bat family-4／pit family-5 PA 總量 = legacy − spurious 數。

    uv run python scripts/verify_splits_pa_split1.py \
        --out docs/research/ingest_splits_pa_split1_metrics.json \
        --delta-out docs/research/ingest_splits_pa_split1_player_delta.json
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
import subprocess
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row

from cpbl.db import conn
from cpbl.ingest.pa_build import (
    STRIKEOUT_ACTIONS,
    _clean,
    _is_real_pitch,
    _terminal_event,
    build_islands,
    charged_hitter,
    continues_same_plate_appearance,
    event_sort_key,
)
from cpbl.ingest.splits_calc import (
    _BAT_COLS,
    _PIT_COLS,
    _RBI,
    BASE_NAMES,
    INNING_NAMES,
    ORDER_NAMES,
    OUT_NAMES,
    PA_OUTCOME,
    ROLE_VS,
    _bat_rates,
    _batter_side,
    _is_local,
    _load_bio,
    _meta,
    _month_of,
    _venue,
    calc_batting_t1,
    calc_pitching_t1,
    calc_t2,
)

SCOPE_YEARS = (2018, 2026)
SCOPE_KINDS = ("A", "C", "D", "E")
ITER1_SHA = "3b07d048c427b99d699a4f19c69600ff8d4352f5"  # 被 REJECT 的 iteration 1 交付

# calc_t2 讀的 18 欄（順序語意見該函式）＋canonical 判準需要的 4 欄
FETCH_COLS = (
    "game_sno, inning_seq, visiting_home_type, main_event_no, hitter_acnt, "
    "pitcher_acnt, batting_order, out_cnt, first_base, second_base, third_base, "
    "batting_action_name, is_strike, is_ball, visiting_score, home_score, "
    "is_change_player, content, pitch_cnt, action_name, ball_cnt, strike_cnt"
)

Row = dict[str, Any]
Table = dict[tuple[str, str, str], Counter]

# build_splits 寫回的發布欄位（同 INSERT 欄序；鍵欄與 updated_at 除外）
BAT_ROW_COLS = (
    "plate_appearances", "at_bats", "hits", "rbi", "singles", "doubles", "triples",
    "home_runs", "total_bases", "sac_hit", "sac_fly", "bb", "ibb", "hbp", "so",
    "ground_outs", "fly_outs", "goao", "avg", "obp", "slg", "ops",
)
PIT_ROW_COLS = (
    "wins", "loses", "starts", "complete_games", "shutouts", "save_ok",
    "inning_pitched_cnt", "inning_pitched_div3", "plate_appearances", "pitch_cnt",
    "strikes", "balls", "hits", "home_runs", "sac_hit", "sac_fly", "bb", "ibb",
    "hbp", "so", "wild_pitch", "balk", "runs", "earned_runs",
)

# 9.16(h)(1)：後援投手接手時球數為 2-0/2-1/3-0/3-1/3-2 且該打席四壞 → 記前任投手
_WALK_OUTCOMES = frozenset({"四壞", "故四"})
_ADVANTAGE_COUNTS = frozenset({(2, 0), (2, 1), (3, 0), (3, 1), (3, 2)})


def fetch_rows(year: int, kind: str) -> list[Row]:
    """與 calc_t2 相同的列序（ORDER BY game_sno, inning_seq, vht, main_event_no）。"""
    with conn() as c:
        c.execute("SET TRANSACTION READ ONLY")
        cur = c.cursor(row_factory=dict_row)
        cur.execute(
            f"SELECT {FETCH_COLS} FROM cpbl.game_livelog "  # noqa: S608
            "WHERE year = %s AND kind_code = %s "
            "ORDER BY game_sno, inning_seq, visiting_home_type, main_event_no",
            (year, kind),
        )
        return [dict(r) for r in cur.fetchall()]


def splits_guard() -> dict[str, Any]:
    """唯讀紅線佐證：四張分項表筆數與 max(updated_at)。"""
    out: dict[str, Any] = {}
    with conn() as c:
        c.execute("SET TRANSACTION READ ONLY")
        for tbl in ("batting_splits", "pitching_splits",
                    "batting_vs_team", "pitching_vs_team"):
            n, upd = c.execute(
                f"SELECT count(*), max(updated_at) FROM cpbl.{tbl}"  # noqa: S608
            ).fetchone()
            out[tbl] = {"rows": n, "max_updated_at": str(upd)}
    return out


# ===========================================================================
# legacy 分組與 flush 判定（逐行重現 calc_t2；保真由 simulate==calc_t2 釘住）
# ===========================================================================
def group_islands(
    rows: list[Row], merges: frozenset[tuple[Any, Any]] = frozenset()
) -> list[tuple[list[Row], tuple[int, int], bool]]:
    """重現 calc_t2 主迴圈的切界與比分追蹤，回傳 [(island, score_before, merged)]。

    `merges` 內的 (game_sno, 該島首列 main_event_no) 表示該島不切界、併入前一島
    （corrected 模式；legacy 傳空集合）。合併時 score_before 沿用前島起點。
    """
    out: list[tuple[list[Row], tuple[int, int], bool]] = []
    cur_game = None
    running = (0, 0)
    score_before = (0, 0)
    island: list[Row] = []
    island_sb = (0, 0)
    merged = False
    ikey = None
    for r in rows:
        sno, hitter = r["game_sno"], r["hitter_acnt"]
        if sno != cur_game:
            if island:
                out.append((island, island_sb, merged))
            cur_game, running, island, ikey, merged = sno, (0, 0), [], None, False
        if not hitter:
            v_sc, h_sc = r["visiting_score"], r["home_score"]
            if v_sc is not None and h_sc is not None:
                running = (v_sc, h_sc)
            continue
        key = (r["inning_seq"], r["visiting_home_type"], hitter)
        if key != ikey:
            if island and (sno, r["main_event_no"]) in merges:
                merged = True  # 缺陷邊界：不 flush、沿用前島與其 score_before
            else:
                if island:
                    out.append((island, island_sb, merged))
                island, merged, score_before = [], False, running
                island_sb = score_before
            ikey = key
        island.append(r)
        v_sc, h_sc = r["visiting_score"], r["home_score"]
        if v_sc is not None and h_sc is not None:
            running = (v_sc, h_sc)
    if island:
        out.append((island, island_sb, merged))
    return out


def flush_decision(island: list[Row]) -> tuple[int | None, str, str | None]:
    """flush() 的三道過濾，依原始順序：無結果 → 未登錄詞 → 幽靈島。回傳 (lp, 去向, outcome)。"""
    outcome = next((r["batting_action_name"] for r in reversed(island)
                    if r["batting_action_name"]), None)
    if not outcome:
        return None, "skipped_no_outcome", None
    if PA_OUTCOME.get(outcome) is None:
        return None, "unknown_action", outcome
    lp = next((i for i in range(len(island) - 1, -1, -1)
               if island[i]["is_strike"] or island[i]["is_ball"]), None)
    if lp is None:
        return None, "ghost_island_no_pitch", outcome
    return lp, "counted", outcome


# ===========================================================================
# canonical transition 列舉（跨打者但同一打席）＋判準記錄
# ===========================================================================
def canonical_transitions(events: list[Row]) -> list[tuple[Row, Row, str | None]]:
    """以 canonical build_islands() 取跨打者 transition：(前片段末列, 新打者首列, 判準)。

    build_islands 只在 continues_same_plate_appearance 判定成立時才把不同打者留在
    同一島，故「島內相鄰兩個成員列打者不同」⇔ 一次被接受的合併。判準（criterion）
    以與 build_islands 相同的島前綴重新呼叫該函式取得（count_continues／pinch_hit_slot），
    供 REVIEW-007 F3 的漏判分類。
    """
    out: list[tuple[Row, Row, str | None]] = []
    for island in build_islands(events):
        ordered = sorted(island, key=event_sort_key)
        prefix: list[Row] = []
        prev_usable: Row | None = None
        for ev in ordered:
            usable = (not ev.get("is_change_player")
                      and _clean(ev.get("hitter_acnt")) is not None)
            if (usable and prev_usable is not None
                    and _clean(ev["hitter_acnt"]) != _clean(prev_usable["hitter_acnt"])):
                out.append((prev_usable, ev,
                            continues_same_plate_appearance(prefix, ev)))
            if usable:
                prev_usable = ev
            prefix.append(ev)
    return out


# ===========================================================================
# calc_t2 模擬器（named-column 重寫；保真由「與 calc_t2 輸出逐格相等」驗證）
# ===========================================================================
def _count_after(row: Row) -> tuple[int, int]:
    b, s = row.get("ball_cnt"), row.get("strike_cnt")
    return (int(b) if b not in (None, "") else 0, int(s) if s not in (None, "") else 0)


def responsible_pitcher(island: list[Row], outcome: str) -> tuple[str, dict | None]:
    """打席結果的責任投手（僅 corrected 合併島使用）。

    預設＝最後一顆投球列的投手（與 calc_t2 錨定語意一致，legacy 完成段亦同）。
    例外＝記錄規則 9.16(h)(1)（`docs/reference/棒球規則.txt`）：後援投手接手時
    球數為 2-0／2-1／3-0／3-1／3-2，且該擊球員獲四壞 → 記**前任投手**；
    9.16(h)(2)：其他任何擊球行為皆為後援投手之責任。
    回傳 (責任投手, 若適用 9.16(h) 的說明 dict)。
    """
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


def simulate_t2(
    rows: list[Row],
    gmeta: dict[Any, tuple[date, str]],
    roles: dict[tuple[Any, str], str],
    bio: dict[str, tuple[str, str, str]],
    merges: frozenset[tuple[Any, Any]] = frozenset(),
    cross_pitcher_log: list[dict] | None = None,
) -> tuple[Table, Table, Table]:
    """逐行重現 calc_t2 的 flush 累加。merges 非空＝corrected 模式：

    - 打者歸屬：合併島全額記 canonical `charged_hitter`（規則 9.15(b)；官方 box
      逐場實證 PA 隨 AB 歸屬——2025/A/84：6738 PA=3=AB、7091 的 PA=1 是他自己的犧短）。
    - 投球數（REVIEW-007 F1）：合併島依**每列實際 `pitcher_acnt`** 保留，不隨島錨定
      搬移；legacy 與未合併島維持 calc_t2 原語意（整島記錨定投手）以維持保真閘。
    - 打席結果（投手側 PA/H/BB/SO…）：記責任投手＝`responsible_pitcher()`
      （calc_t2 錨定語意＋9.16(h) 四壞例外）。
    - 情境（壘上/出局/局數/比分/棒次）錨定合併島最後一顆投球列。
    未合併島維持 legacy 歸屬，使 delta 嚴格對應缺陷邊界。
    """
    bat: Table = {}
    pit: Table = {}
    bat_gofo: Table = {}
    pa_seq: dict[tuple, int] = {}

    for island, score_before, merged in group_islands(rows, merges):
        lp, _why, outcome = flush_decision(island)
        if lp is None:
            continue
        delta = PA_OUTCOME[outcome]
        first, last = island[0], island[lp]
        sno = first["game_sno"]
        inning, vh, hitter = last["inning_seq"], str(first["visiting_home_type"]), first["hitter_acnt"]
        pitcher, outs = last["pitcher_acnt"], last["out_cnt"]
        b1, b2, b3 = last["first_base"], last["second_base"], last["third_base"]
        seq = pa_seq.get((sno, vh), 0)
        pa_seq[(sno, vh)] = seq + 1
        order = seq % 9 + 1
        gd, venue = gmeta[sno]
        if gd > date.today():
            continue
        strikes = sum(1 for r in island if r["is_strike"])
        balls = sum(1 for r in island if r["is_ball"])
        rbi = sum(int(m.group(1)) for r in island
                  for m in _RBI.finditer(r["content"] or ""))
        bases = frozenset(n for n, v in ((1, b1), (2, b2), (3, b3))
                          if v not in (None, ""))
        if (lp > 0 and island[lp - 1]["visiting_score"] is not None
                and island[lp - 1]["home_score"] is not None):
            v_sc, h_sc = island[lp - 1]["visiting_score"], island[lp - 1]["home_score"]
        else:
            v_sc, h_sc = score_before
        my_sc, opp_sc = (h_sc, v_sc) if vh == "2" else (v_sc, h_sc)
        score_item = ("比分領先" if my_sc > opp_sc
                      else "比分落後" if my_sc < opp_sc else "相同比分")

        # 打者歸屬：legacy＝首列 hitter；corrected 合併島＝canonical charged_hitter
        charged = hitter
        if merged:
            non_change = [e for e in island if not e.get("is_change_player")]
            term = _terminal_event(island)
            act = _clean(term.get("action_name")) if term else None
            c_h, _cp_h = charged_hitter(non_change, act)
            charged = c_h or hitter

        p_bats, p_throws, p_country = bio.get(pitcher, ("", "", ""))
        h_bats, _h_throws, h_country = bio.get(charged, ("", "", ""))

        # ── 打者側 ──
        buckets: list[tuple[str, str]] = [
            ("4", BASE_NAMES[bases]),
            ("5", OUT_NAMES.get(outs, "二出局")),
            ("6", INNING_NAMES.get(inning, "")),
            ("7", score_item),
        ]
        if order in ORDER_NAMES:
            buckets.append(("10", ORDER_NAMES[order]))
        if p_throws:
            buckets.append(("3", f"VS. {'左投' if p_throws == '左投' else '右投'}"))
            buckets.append(("3", "VS. 本土投手" if _is_local(pitcher, p_country)
                            else "VS. 外籍投手"))
        role = roles.get((sno, pitcher))
        if role in ROLE_VS:
            buckets.append(("3", ROLE_VS[role]))
        for grp, item in buckets:
            cnt = bat.setdefault((charged, grp, item), Counter())
            for k, v in delta.items():
                cnt[_BAT_COLS[k]] += v
            cnt["rbi"] += rbi
        for grp, item in (("1", "主場" if vh == "2" else "客場"),
                          ("8", _month_of(gd)), ("9", _venue(venue))):
            cnt = bat_gofo.setdefault((charged, grp, item), Counter())
            cnt["ground_outs"] += delta.get("go", 0)
            cnt["fly_outs"] += delta.get("fo", 0)

        # ── 投手側（vh 反轉視角）──
        p_my, p_opp = opp_sc, my_sc
        p_score = ("比分領先" if p_my > p_opp
                   else "比分落後" if p_my < p_opp else "相同比分")
        base_pbuckets: list[tuple[str, str]] = [
            ("5", BASE_NAMES[bases]),
            ("6", OUT_NAMES.get(outs, "二出局")),
            ("7", INNING_NAMES.get(inning, "")),
            ("8", p_score),
        ]
        # 投球數歸屬（REVIEW-007 F1）：merged 島逐列記實際投手；否則整島記錨定投手
        if merged:
            pitch_by: dict[str, list[int]] = {}
            for r in island:
                if r["is_strike"] or r["is_ball"]:
                    d = pitch_by.setdefault(r["pitcher_acnt"], [0, 0])
                    if r["is_strike"]:
                        d[0] += 1
                    if r["is_ball"]:
                        d[1] += 1
            resp, rule_note = responsible_pitcher(island, outcome)
            pitch_by.setdefault(resp, [0, 0])
            if cross_pitcher_log is not None and len(pitch_by) > 1:
                cross_pitcher_log.append({
                    "game_sno": sno, "inning": inning, "half": vh,
                    "outcome": outcome,
                    "pitch_by": {p: {"strikes": v[0], "balls": v[1]}
                                 for p, v in pitch_by.items()},
                    "responsible": resp, "rule_916h": rule_note,
                })
        else:
            pitch_by = {pitcher: [strikes, balls]}
            resp = pitcher
        for p_acnt, (p_str, p_ball) in pitch_by.items():
            _pb, p_thr, _pc = bio.get(p_acnt, ("", "", ""))
            own_pbuckets = list(base_pbuckets)
            side = _batter_side(h_bats, p_thr)
            if side:
                own_pbuckets.append(("3", f"VS. {side}"))
            if h_country:
                own_pbuckets.append(("3", "VS. 本土打者" if _is_local(charged, h_country)
                                     else "VS. 外籍打者"))
            for grp, item in own_pbuckets:
                cnt = pit.setdefault((p_acnt, grp, item), Counter())
                if p_acnt == resp:
                    for k, v in delta.items():
                        if k in _PIT_COLS:
                            cnt[_PIT_COLS[k]] += v
                cnt["pitch_cnt"] += p_str + p_ball
                cnt["strikes"] += p_str
                cnt["balls"] += p_ball
    return bat, pit, bat_gofo


def load_ctx(year: int, kind: str) -> tuple[dict, dict]:
    with conn() as c:
        c.execute("SET TRANSACTION READ ONLY")
        roles = {(sno, a): r for sno, a, r in c.execute(
            "SELECT game_sno, pitcher_acnt, role_type FROM cpbl.pitching_gamelog "
            "WHERE year = %s AND kind_code = %s", (year, kind)).fetchall()}
        gmeta = {sno: (gd, venue) for sno, gd, venue in c.execute(
            "SELECT game_sno, game_date, venue FROM cpbl.games "
            "WHERE year = %s AND kind_code = %s", (year, kind)).fetchall()}
    return roles, gmeta


def assert_fidelity(year: int, kind: str, sim: tuple[Table, Table, Table]) -> dict:
    """模擬器 legacy 模式必須與 calc_t2 逐格相等，否則 delta 不可信，直接 fail。"""
    ref_bat, ref_pit, ref_gofo, _diag = calc_t2(year, kind, None, None)
    report = {}
    for name, mine, ref in (("bat", sim[0], ref_bat), ("pit", sim[1], ref_pit),
                            ("bat_gofo", sim[2], ref_gofo)):
        if mine != ref:
            bad = [k for k in set(mine) | set(ref)
                   if mine.get(k, Counter()) != ref.get(k, Counter())][:5]
            raise AssertionError(
                f"simulate_t2 與 calc_t2 不一致：{year}/{kind} {name}，樣本 key={bad}")
        report[name] = len(ref)
    return report


# ===========================================================================
# 完整發布 row 組裝（重現 build_splits writer；REVIEW-007 F2）
# ===========================================================================
def assemble_bat_rows(bat_t1: Table, bat_gofo: Table, bat_t2: Table) -> dict:
    """重現 build_splits L616–637：T1 ＋ gofo 併入 ＋ T2 覆蓋 → 發布欄位（含 rates）。"""
    t1 = {k: Counter(c) for k, c in bat_t1.items()}
    for key, cnt in bat_gofo.items():
        t1.setdefault(key, Counter()).update(cnt)
    t1.update(bat_t2)
    out: dict[tuple, dict] = {}
    for (acnt, grp, item), c in t1.items():
        idx, note = _meta("bat", grp, item)
        r = _bat_rates(c)
        row = {col: c[col] for col in BAT_ROW_COLS if col not in r}
        row.update(r)
        out[(acnt, grp, idx, item, note)] = row
    return out


def assemble_pit_rows(pit_t1: Table, pit_t2: Table) -> dict:
    """重現 build_splits L638–648：T1 ＋ T2 覆蓋 → 發布欄位（IP 由總出局數拆欄）。"""
    t1 = {k: Counter(c) for k, c in pit_t1.items()}
    t1.update(pit_t2)
    out: dict[tuple, dict] = {}
    for (acnt, grp, item), c in t1.items():
        idx, note = _meta("pit", grp, item)
        outs = c["inning_pitched_div3"]
        row = {col: c[col] for col in PIT_ROW_COLS
               if col not in ("inning_pitched_cnt", "inning_pitched_div3")}
        row["inning_pitched_cnt"] = outs // 3
        row["inning_pitched_div3"] = outs % 3
        out[(acnt, grp, idx, item, note)] = row
    return out


def published_rows(table: str, year: int, kind: str, cols: tuple[str, ...]) -> dict:
    """DB 已發布列（驗證組裝層保真用）。"""
    with conn() as c:
        c.execute("SET TRANSACTION READ ONLY")
        cur = c.cursor(row_factory=dict_row)
        cur.execute(
            f"SELECT acnt, item_group_code, item_index, item_name, item_note, "  # noqa: S608
            f"{', '.join(cols)} FROM cpbl.{table} WHERE year = %s AND kind_code = %s",
            (year, kind))
        out = {}
        for r in cur.fetchall():
            key = (r["acnt"], r["item_group_code"], r["item_index"],
                   r["item_name"], r["item_note"])
            out[key] = {col: (float(r[col]) if r[col] is not None
                              and col in ("goao", "avg", "obp", "slg", "ops")
                              else r[col]) for col in cols}
        return out


def diff_full_rows(legacy: dict, corrected: dict, cols: tuple[str, ...]) -> list[dict]:
    """發布 row 逐格 diff；只回傳有差異的 (key, {col: {legacy, corrected}})。"""
    out = []
    for key in set(legacy) | set(corrected):
        lrow, crow = legacy.get(key), corrected.get(key)
        changed = {}
        for col in cols:
            lv = lrow.get(col) if lrow else None
            cv = crow.get(col) if crow else None
            if lv != cv:
                changed[col] = {"legacy": lv, "corrected": cv}
        if changed:
            acnt, grp, idx, item, note = key
            out.append({"acnt": acnt, "group": grp, "item_index": idx,
                        "item_name": item, "item_note": note,
                        "in_legacy": lrow is not None, "in_corrected": crow is not None,
                        "cols": changed})
    return out


def check_invariants(year: int, kind: str, legacy: tuple[Table, Table, Table],
                     corrected: tuple[Table, Table, Table], n_spurious: int) -> dict:
    """corrected 路徑的機器不變量（單一 item／PA 的家族：bat 4、pit 5）。

    1. bat family 4 PA 總量：corrected == legacy − n_spurious（雙計移除、無憑空增減）。
    2. pit family 5 PA 總量：同上。
    3. **逐投手** family 5 投球數（strikes/balls/pitch_cnt）守恆：corrected == legacy
       ——投球數不得在投手間搬移（REVIEW-007 F1 的直接防護）。
    違反即 raise。
    """
    def fam_total(tbl: Table, grp: str, col: str) -> int:
        return sum(c.get(col, 0) for (_a, g, _i), c in tbl.items() if g == grp)

    bat_l = fam_total(legacy[0], "4", "plate_appearances")
    bat_c = fam_total(corrected[0], "4", "plate_appearances")
    pit_l = fam_total(legacy[1], "5", "plate_appearances")
    pit_c = fam_total(corrected[1], "5", "plate_appearances")
    if bat_c != bat_l - n_spurious or pit_c != pit_l - n_spurious:
        raise AssertionError(
            f"{year}/{kind} PA 總量不變量失敗：bat {bat_l}→{bat_c}、"
            f"pit {pit_l}→{pit_c}、spurious={n_spurious}")

    def per_pitcher(tbl: Table) -> dict[str, tuple[int, int, int]]:
        agg: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0, 0])
        for (a, g, _i), c in tbl.items():
            if g == "5":
                agg[a][0] += c.get("strikes", 0)
                agg[a][1] += c.get("balls", 0)
                agg[a][2] += c.get("pitch_cnt", 0)
        return {a: tuple(v) for a, v in agg.items()}

    pl, pc = per_pitcher(legacy[1]), per_pitcher(corrected[1])
    moved = {a: (pl.get(a, (0, 0, 0)), pc.get(a, (0, 0, 0)))
             for a in set(pl) | set(pc) if pl.get(a, (0, 0, 0)) != pc.get(a, (0, 0, 0))}
    if moved:
        raise AssertionError(f"{year}/{kind} 逐投手投球數守恆失敗：{moved}")
    return {"bat_f4_pa": [bat_l, bat_c], "pit_f5_pa": [pit_l, pit_c],
            "n_spurious": n_spurious, "per_pitcher_pitch_conserved": True}


def box_crosscheck(
    year: int, kind: str, snos: set, rows: list[Row],
    merges: frozenset[tuple[Any, Any]],
) -> list[dict]:
    """受影響場次逐場對照官方 box（`batting_gamelog`，爬蟲直寫、不經 splits_calc）。

    對每個受影響場次逐人計算單場 PA：legacy 歸屬 vs corrected 歸屬 vs 官方 box。
    box 是**未被重算污染的外部對照**（紅線 2：非自比）。寬過濾：凡 legacy≠box、
    corrected≠box 或 legacy≠corrected 的打者皆列（含只出現在 box 的）。
    """
    with conn() as c:
        c.execute("SET TRANSACTION READ ONLY")
        box = {(g, a): p for g, a, p in c.execute(
            "SELECT game_sno, hitter_acnt, plate_appearances FROM cpbl.batting_gamelog "
            "WHERE year = %s AND kind_code = %s AND game_sno = ANY(%s)",
            (year, kind, list(snos))).fetchall()}
    by_game: dict[Any, list[Row]] = collections.defaultdict(list)
    for r in rows:
        if r["game_sno"] in snos:
            by_game[r["game_sno"]].append(r)
    out: list[dict] = []
    for sno, game_rows in sorted(by_game.items()):
        legacy_pa: Counter = Counter()
        corr_pa: Counter = Counter()
        for isl, _sb, _m in group_islands(game_rows):
            if flush_decision(isl)[0] is not None:
                legacy_pa[isl[0]["hitter_acnt"]] += 1
        for isl, _sb, merged in group_islands(game_rows, merges):
            if flush_decision(isl)[0] is None:
                continue
            who = isl[0]["hitter_acnt"]
            if merged:
                non_change = [e for e in isl if not e.get("is_change_player")]
                term = _terminal_event(isl)
                act = _clean(term.get("action_name")) if term else None
                who = charged_hitter(non_change, act)[0] or who
            corr_pa[who] += 1
        box_players = {a for (g, a) in box if g == sno}
        for acnt in sorted(set(legacy_pa) | set(corr_pa) | box_players):
            b = box.get((sno, acnt))
            lv, cv = legacy_pa[acnt], corr_pa[acnt]
            if b is not None and lv == b and cv == b:
                continue
            out.append({
                "game": f"{year}/{kind}/{sno}", "acnt": acnt,
                "legacy_pa": lv, "corrected_pa": cv, "box_pa": b,
                "corrected_matches_box": (b is not None and cv == b),
                "legacy_matches_box": (b is not None and lv == b),
            })
    return out


def iter1_missed_classification(exposed: list[dict]) -> dict:
    """REVIEW-007 F3：iteration 1（`3b07d04` artifact）漏掉哪些筆、canonical 判準各為何。"""
    try:
        raw = subprocess.run(
            ["git", "show", f"{ITER1_SHA}:docs/research/ingest_splits_pa_split1_metrics.json"],
            capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        return {"error": f"無法讀取 iteration 1 artifact：{exc}"}
    old = {(r["game"], r["spurious_event_no"])
           for r in json.loads(raw)["exposure"]["rows"]}
    new = {(e["game"], e["spurious_event_no"]): e for e in exposed}
    missed = sorted(k for k in new if k not in old)
    not_in_new = sorted(k for k in old if k not in new)
    return {
        "iter1_found": len(old), "iter2_total": len(new),
        "iter1_subset_of_iter2": not not_in_new,
        "missed": len(missed),
        "missed_by_criterion": dict(Counter(
            new[k]["criterion"] for k in missed)),
        "rows": [{"game": k[0], "spurious_event_no": k[1],
                  "criterion": new[k]["criterion"], "outcome": new[k]["outcome"]}
                 for k in missed],
    }


# ===========================================================================
# 主流程
# ===========================================================================
def collect(out_delta: Path | None) -> dict[str, Any]:
    guard_before = splits_guard()
    bio = _load_bio()
    with conn() as c:
        c.execute("SET TRANSACTION READ ONLY")
        names = dict(c.execute("SELECT id, name FROM cpbl.players").fetchall())
        published_pairs = {(y, k) for y, k in c.execute(
            "SELECT DISTINCT year, kind_code FROM cpbl.batting_splits").fetchall()}

    disposition: Counter = Counter()
    transitions: list[dict] = []
    exposed: list[dict] = []
    order_shift: list[dict] = []
    outcome_counter: Counter = Counter()
    anomalies: list[dict] = []
    scope_games = 0
    scope_events = 0
    pair_merges: dict[tuple[int, str], set[tuple[Any, Any]]] = collections.defaultdict(set)
    pair_spurious: Counter = Counter()   # (year, kind) → counted 缺陷邊界數

    for year in range(SCOPE_YEARS[0], SCOPE_YEARS[1] + 1):
        for kind in SCOPE_KINDS:
            rows = fetch_rows(year, kind)
            if not rows:
                continue
            scope_events += len(rows)
            by_game: dict[Any, list[Row]] = collections.defaultdict(list)
            for r in rows:
                by_game[r["game_sno"]].append(r)
            scope_games += len(by_game)
            for sno, game_rows in by_game.items():
                trans = canonical_transitions(game_rows)
                if not trans:
                    continue
                islands = group_islands(game_rows)
                idx_of = {r["main_event_no"]: i
                          for i, (isl, _sb, _m) in enumerate(islands) for r in isl}
                spurious: set[int] = set()
                for a, b, criterion in trans:
                    i, j = idx_of[a["main_event_no"]], idx_of[b["main_event_no"]]
                    prev_isl = islands[i][0]
                    lp, why, outcome = flush_decision(prev_isl)
                    disposition[why] += 1
                    _nlp, next_why, _no = flush_decision(islands[j][0])
                    rec = {
                        "game": f"{year}/{kind}/{sno}",
                        "inning": prev_isl[-1]["inning_seq"],
                        "half": str(prev_isl[-1]["visiting_home_type"]),
                        "prev_first_event_no": str(prev_isl[0]["main_event_no"]),
                        "prev_hitter": _clean(prev_isl[0]["hitter_acnt"]),
                        "next_hitter": _clean(b["hitter_acnt"]),
                        "criterion": criterion,
                        "prev_disposition": why,
                        "next_disposition": next_why,
                        "outcome": outcome,
                        "islands_between": j - i - 1,
                    }
                    transitions.append(rec)
                    if criterion is None:
                        anomalies.append({**rec, "why": "criterion 重建為 None"})
                    if j - i != 1:
                        anomalies.append({**rec, "why": "transition 跨越中介島"})
                    if next_why != "counted" and why == "counted":
                        anomalies.append({**rec, "why": "prev counted 但 next 未計"})
                    if why != "counted":
                        continue
                    spurious.add(i)
                    outcome_counter[str(outcome)] += 1
                    pair_spurious[(year, kind)] += 1
                    non_change = [e for e in sorted(
                        (r for isl_i in range(i, j + 1) for r in islands[isl_i][0]),
                        key=event_sort_key) if not e.get("is_change_player")]
                    term = _terminal_event(non_change)
                    act = _clean(term.get("action_name")) if term else None
                    ch, cp = charged_hitter(non_change, act)
                    exposed.append({
                        **{k: rec[k] for k in ("game", "inning", "half", "outcome",
                                               "criterion")},
                        "game_date": None,  # 補於 gmeta 載入後
                        "spurious_event_no": rec["prev_first_event_no"],
                        "spurious_hitter": rec["prev_hitter"],
                        "completing_hitter": cp,
                        "charged_hitter": ch,
                        "strikeout_charged_to_prev": bool(
                            act in STRIKEOUT_ACTIONS and ch != cp),
                        "has_real_pitch": any(_is_real_pitch(e) for e in prev_isl),
                        "_year_kind": (year, kind), "_sno": sno,
                    })
                    for m in range(i + 1, j + 1):
                        pair_merges[(year, kind)].add(
                            (sno, islands[m][0][0]["main_event_no"]))
                # H1：以正確 spurious 集重現 iteration 1 的位移語意
                if spurious:
                    seq: Counter = Counter()
                    shift: Counter = Counter()
                    after: Counter = Counter()
                    for i, (isl, _sb, _m) in enumerate(islands):
                        lp, why, _o = flush_decision(isl)
                        if lp is None:
                            continue
                        vh = str(isl[0]["visiting_home_type"])
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

    # 補 game_date
    gmeta_cache: dict[tuple[int, str], dict] = {}
    for e in exposed:
        yk = e.pop("_year_kind")
        sno = e.pop("_sno")
        if yk not in gmeta_cache:
            _r, gm = load_ctx(*yk)
            gmeta_cache[yk] = gm
        e["game_date"] = str(gmeta_cache[yk][sno][0])

    # ── 選手層級 delta（完整發布欄位）：僅對已發布 splits 的 (year, kind) ──
    affected_pairs = sorted({(int(e["game"].split("/")[0]), e["game"].split("/")[1])
                             for e in exposed})
    fidelity: dict[str, Any] = {}
    assembly_fidelity: dict[str, Any] = {}
    invariants: dict[str, Any] = {}
    delta_rows: list[dict] = []
    delta_skipped_pairs: list[str] = []
    box_rows: list[dict] = []
    cross_pitcher: list[dict] = []
    for year, kind in affected_pairs:
        rows = fetch_rows(year, kind)
        merges = frozenset(pair_merges[(year, kind)])
        snos = {int(e["game"].split("/")[2]) for e in exposed
                if e["game"].startswith(f"{year}/{kind}/")}
        box_rows.extend(box_crosscheck(year, kind, snos, rows, merges))
        if (year, kind) not in published_pairs:
            delta_skipped_pairs.append(f"{year}/{kind}")
            continue
        roles, gmeta = load_ctx(year, kind)
        legacy = simulate_t2(rows, gmeta, roles, bio)
        fidelity[f"{year}/{kind}"] = assert_fidelity(year, kind, legacy)
        log: list[dict] = []
        corrected = simulate_t2(rows, gmeta, roles, bio, merges, cross_pitcher_log=log)
        for entry in log:
            cross_pitcher.append({"game": f"{year}/{kind}/{entry.pop('game_sno')}",
                                  **entry})
        invariants[f"{year}/{kind}"] = check_invariants(
            year, kind, legacy, corrected, pair_spurious[(year, kind)])

        # 完整發布 row（T1 兩版共用；T2 換 legacy/corrected）
        bat_t1, _bvt = calc_batting_t1(year, kind, None)
        pit_t1, _pvt = calc_pitching_t1(year, kind, None)
        legacy_bat = assemble_bat_rows(bat_t1, legacy[2], legacy[0])
        legacy_pit = assemble_pit_rows(pit_t1, legacy[1])
        corrected_bat = assemble_bat_rows(bat_t1, corrected[2], corrected[0])
        corrected_pit = assemble_pit_rows(pit_t1, corrected[1])

        # 組裝層保真（資訊性）：assembled legacy row 對 DB 已發布列逐格比對
        for table, mine, cols in (("batting_splits", legacy_bat, BAT_ROW_COLS),
                                  ("pitching_splits", legacy_pit, PIT_ROW_COLS)):
            pub = published_rows(table, year, kind, cols)
            common = set(mine) & set(pub)
            equal = sum(1 for k in common if all(
                (mine[k][c] == pub[k][c]
                 or (mine[k][c] is None and pub[k][c] is None))
                for c in cols))
            assembly_fidelity[f"{year}/{kind}/{table}"] = {
                "assembled": len(mine), "published": len(pub),
                "common": len(common), "equal_rows": equal,
            }

        for table, l_rows, c_rows, cols in (
                ("batting_splits", legacy_bat, corrected_bat, BAT_ROW_COLS),
                ("pitching_splits", legacy_pit, corrected_pit, PIT_ROW_COLS)):
            for d in diff_full_rows(l_rows, c_rows, cols):
                delta_rows.append({"year": year, "kind": kind, "table": table,
                                   "player": names.get(d["acnt"], "?"), **d})

    guard_after = splits_guard()
    if guard_before != guard_after:
        raise AssertionError(f"唯讀紅線失守：{guard_before} != {guard_after}")

    # 摘要（REVIEW-008 F1：affected_players 以唯一 acnt 計、排行跨表聚合）
    n_cells = sum(len(d["cols"]) for d in delta_rows)
    count_cols = set(BAT_ROW_COLS + PIT_ROW_COLS) - {"goao", "avg", "obp", "slg", "ops"}
    by_player: Counter = Counter()          # acnt → Σ|delta|（整數計數欄，跨表）
    by_player_table: dict = collections.defaultdict(Counter)  # acnt → {table: Σ|delta|}
    for d in delta_rows:
        for col, v in d["cols"].items():
            if col in count_cols:
                dv = abs((v["corrected"] or 0) - (v["legacy"] or 0))
                by_player[d["acnt"]] += dv
                by_player_table[d["acnt"]][d["table"]] += dv
    delta_summary = {
        "rows": len(delta_rows),
        "changed_cells": n_cells,
        "affected_players": len({d["acnt"] for d in delta_rows}),
        "affected_table_players": dict(Counter(
            d["table"] for d in
            {(d["table"], d["acnt"]): d for d in delta_rows}.values()).most_common()),
        "by_table_family": dict(Counter(
            f"{d['table']}/{d['group']}" for d in delta_rows).most_common()),
        "by_col": dict(Counter(
            col for d in delta_rows for col in d["cols"]).most_common()),
        "skipped_pairs_no_published_splits": delta_skipped_pairs,
        "note_ranking": "top_players 以整數計數欄位的 Σ|delta| 排序、跨表聚合到唯一 acnt"
                        "（rate 欄不入排名）",
        "top_players_by_abs_delta": [
            {"acnt": a, "player": names.get(a, "?"), "sum_abs_delta": v,
             "by_table": dict(by_player_table[a])}
            for a, v in by_player.most_common(15)],
        "vs_team_note": "batting_vs_team／pitching_vs_team 來自 T1（gamelog 加總，"
                        "不經 livelog 島重建），本缺陷零影響，不列 diff",
    }
    # 摘要一致性 assertion（REVIEW-008 F1）：摘要數字必須可由 rows 重算
    assert delta_summary["affected_players"] == len({d["acnt"] for d in delta_rows})
    assert delta_summary["changed_cells"] == sum(len(d["cols"]) for d in delta_rows)
    assert sum(delta_summary["by_col"].values()) == delta_summary["changed_cells"]
    assert (sum(e["sum_abs_delta"] for e in delta_summary["top_players_by_abs_delta"])
            <= sum(by_player.values()))

    if out_delta is not None:
        out_delta.write_text(json.dumps({
            "generated_at": datetime.datetime.now().astimezone().isoformat(),
            "note": "完整發布欄位 diff（batting/pitching_splits 全欄含 goao/avg/obp/slg/ops）。"
                    "corrected＝legacy＋僅合併 counted 缺陷邊界；打者歸屬 canonical "
                    "charged_hitter（9.15(b)）；投球數依每列實際 pitcher_acnt 保留、"
                    "打席結果責任依 9.16(h)；只列有差異的 row 與欄。",
            "summary": delta_summary,
            "rows": sorted(delta_rows, key=lambda d: (
                d["year"], d["kind"], d["table"], d["acnt"], d["group"], d["item_name"])),
        }, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    return {
        "generated_at": datetime.datetime.now().astimezone().isoformat(),
        "scope": {"from_year": SCOPE_YEARS[0], "to_year": SCOPE_YEARS[1],
                  "kinds": list(SCOPE_KINDS), "games": scope_games,
                  "events": scope_events},
        "judgement_source": "canonical build_islands / charged_hitter"
                            "（GAME-RECAP-PA1-FIX1，builder 1.3.0／taxonomy 1.1.0）",
        "readonly_guard": {"before": guard_before, "after": guard_after,
                           "unchanged": guard_before == guard_after},
        "canonical_transitions": {
            "total": len(transitions),
            "prev_disposition": dict(disposition),
            "by_criterion": dict(Counter(
                t["criterion"] for t in transitions).most_common()),
            "anomalies": anomalies,
        },
        "iteration1_missed_classification": iter1_missed_classification(exposed),
        "exposure": {
            "double_counted_pas": len(exposed),
            "affected_games": len({e["game"] for e in exposed}),
            "by_year": dict(sorted(Counter(
                e["game"].split("/")[0] for e in exposed).items())),
            "by_kind": dict(sorted(Counter(
                e["game"].split("/")[1] for e in exposed).items())),
            "by_outcome": dict(outcome_counter.most_common()),
            "by_criterion": dict(Counter(
                e["criterion"] for e in exposed).most_common()),
            "strikeout_charged_to_prev_cases": sum(
                1 for e in exposed if e["strikeout_charged_to_prev"]),
            "rows": exposed,
        },
        "h1_batting_order_shift": {
            "hypothesis": "多出的 PA 使 pa_seq 進位，該場該隊其後所有 PA 的打序歸屬整體位移"
                          "（splits_calc: order = seq %% 9 + 1，家族 10 ORDER_NAMES）；"
                          "此為『相對 corrected』的量化，非絕對真實打序保證（REVIEW-007）",
            "affected_team_games": len(order_shift),
            "total_pas_misattributed": sum(r["pas_after_shift"] for r in order_shift),
            "max_shift": max((r["shift"] for r in order_shift), default=0),
            "rows": order_shift,
        },
        "simulator_fidelity_vs_calc_t2": fidelity,
        "assembly_fidelity_vs_published": assembly_fidelity,
        "corrected_invariants": invariants,
        "cross_pitcher_cases": {
            "note": "合併島內投球列跨投手的案例：投球數逐投手保留（守恆由不變量強制），"
                    "打席結果責任依 9.16(h)",
            "cases": cross_pitcher,
        },
        "box_crosscheck": {
            "note": "受影響場次逐場逐人 PA 對照官方 box（batting_gamelog，未經 splits_calc"
                    "，非自比）；寬過濾：凡任一版本不等於 box 或兩版互異者皆列",
            "rows_total": len(box_rows),
            "corrected_matches_box": sum(1 for r in box_rows if r["corrected_matches_box"]),
            "legacy_matches_box": sum(1 for r in box_rows if r["legacy_matches_box"]),
            "no_box_data": sum(1 for r in box_rows if r["box_pa"] is None),
            "corrected_mismatches": [r for r in box_rows
                                     if r["box_pa"] is not None
                                     and not r["corrected_matches_box"]],
            "rows": box_rows,
        },
        "player_delta_summary": delta_summary,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--delta-out", type=Path, default=None)
    args = ap.parse_args()

    rep = collect(args.delta_out)
    s, ex, h1 = rep["scope"], rep["exposure"], rep["h1_batting_order_shift"]
    tr = rep["canonical_transitions"]
    m1 = rep["iteration1_missed_classification"]
    print(f"scope: {s['games']} games / {s['events']} events")
    print(f"canonical transitions：{tr['total']}，prev 去向：{tr['prev_disposition']}")
    print(f"  判準分布（全 transition）：{tr['by_criterion']}")
    if tr["anomalies"]:
        print(f"⚠️ anomalies：{len(tr['anomalies'])} 筆（詳 artifact）")
    print(f"**實際重複計為 PA**：{ex['double_counted_pas']} 筆／{ex['affected_games']} 場")
    print(f"  逐年：{ex['by_year']}  kind：{ex['by_kind']}")
    print(f"  重複記的結果詞：{dict(list(ex['by_outcome'].items())[:8])}")
    print(f"  counted 的判準分布：{ex['by_criterion']}")
    print(f"  9.15(b) 三振歸原打者（被判第 2 好球者）案例："
          f"{ex['strikeout_charged_to_prev_cases']}")
    print(f"iteration 1 漏判分類：漏 {m1.get('missed')} 筆，"
          f"判準 {m1.get('missed_by_criterion')}，61⊂83={m1.get('iter1_subset_of_iter2')}")
    print(f"H1 打序位移：{h1['affected_team_games']} 個 (場次,球隊)，"
          f"其後被錯誤歸類打序的 PA 共 **{h1['total_pas_misattributed']}** 筆，"
          f"最大位移 {h1['max_shift']}")
    print(f"模擬器保真（==calc_t2）：{list(rep['simulator_fidelity_vs_calc_t2'])}")
    af = rep["assembly_fidelity_vs_published"]
    eq = sum(v["equal_rows"] for v in af.values())
    common = sum(v["common"] for v in af.values())
    print(f"組裝層保真（assembled legacy vs DB 已發布列）：{eq}/{common} rows 逐格相等")
    print(f"corrected 不變量：{len(rep['corrected_invariants'])} pairs 全過"
          f"（PA 總量、逐投手投球數守恆）")
    cp = rep["cross_pitcher_cases"]["cases"]
    print(f"跨投手合併島：{len(cp)} 例（{[c['game'] for c in cp]}）")
    bc = rep["box_crosscheck"]
    print(f"box 交叉驗證：{bc['rows_total']} 筆逐場逐人，corrected 吻合 "
          f"{bc['corrected_matches_box']}／legacy 吻合 {bc['legacy_matches_box']}"
          f"／無 box 資料 {bc['no_box_data']}"
          f"／corrected 不吻合 {len(bc['corrected_mismatches'])}")
    ds = rep["player_delta_summary"]
    print(f"選手層級 delta（完整發布欄位）：{ds['rows']} rows／{ds['changed_cells']} "
          f"格（含 rate 欄）／唯一選手 {ds['affected_players']} 位"
          f"（逐表 {ds['affected_table_players']}）")
    print(f"  欄位分布 top：{dict(list(ds['by_col'].items())[:10])}")
    print(f"唯讀紅線：分項表前後不變 = {rep['readonly_guard']['unchanged']}")
    if args.out:
        args.out.write_text(json.dumps(rep, ensure_ascii=False, indent=2, default=str) + "\n",
                            encoding="utf-8")
        print(f"→ {args.out}")


if __name__ == "__main__":
    main()
