"""INGEST-SPLITS-PA-SPLIT1 查證（iteration 2）：`splits_calc` 重複計打席的範圍與選手層級影響。

**唯讀**（`SET TRANSACTION READ ONLY`；並記錄四張分項表執行前後筆數與 max(updated_at)
於 artifact 供查核），不寫任何表、不呼叫 `cpbl-build-splits`。

iteration 1 被退回的根因：直接拿 **legacy island 的 prev** 去呼叫
`continues_same_plate_appearance()`——但 `pinch_hit_slot` 判準要求換人公告列附掛於前一島，
而 legacy 切法把帶新打者 acnt 的公告列切進**後一島**，`_trailing_change_rows(prev)` 永遠是空，
該路徑全數漏判（61 筆為正確 83 筆的子集）。本版改為：

1. 以 canonical `build_islands()`（FIX1 定案判準的唯一入口）列舉全部跨打者 transition；
2. 把每個 transition 的前片段**映射回 `splits_calc.flush()` 實際切出的 legacy island**，
   依 flush 的原始順序執行三道過濾（無結果 → 未登錄詞 → 幽靈島）得去向；
3. H1 打序位移以正確的 spurious 集重算；
4. 選手層級量化：以「與 `calc_t2` 逐格相等」驗證過的模擬器，比較 legacy 與 corrected
   （僅合併 counted 的缺陷邊界，歸屬引用 canonical `charged_hitter`＝記錄規則 9.15(b)）
   的純記憶體計算結果，輸出 選手 × family × item_name × 欄位 的 delta。

    uv run python scripts/verify_splits_pa_split1.py \
        --out docs/research/ingest_splits_pa_split1_metrics.json \
        --delta-out docs/research/ingest_splits_pa_split1_player_delta.json
"""

from __future__ import annotations

import argparse
import collections
import datetime
import json
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
    _batter_side,
    _is_local,
    _load_bio,
    _month_of,
    _venue,
    calc_t2,
)

SCOPE_YEARS = (2018, 2026)
SCOPE_KINDS = ("A", "C", "D", "E")

# calc_t2 讀的 18 欄（順序語意見該函式）＋canonical 判準需要的 4 欄
FETCH_COLS = (
    "game_sno, inning_seq, visiting_home_type, main_event_no, hitter_acnt, "
    "pitcher_acnt, batting_order, out_cnt, first_base, second_base, third_base, "
    "batting_action_name, is_strike, is_ball, visiting_score, home_score, "
    "is_change_player, content, pitch_cnt, action_name, ball_cnt, strike_cnt"
)

Row = dict[str, Any]
Table = dict[tuple[str, str, str], Counter]


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
# canonical transition 列舉（跨打者但同一打席）
# ===========================================================================
def canonical_transitions(events: list[Row]) -> list[tuple[Row, Row]]:
    """以 canonical build_islands() 取跨打者 transition：(前片段末列, 新打者首列)。

    build_islands 只在 continues_same_plate_appearance 判定成立時才把不同打者
    留在同一島，故「島內相鄰兩個成員列打者不同」⇔ 一次被接受的合併。
    """
    out: list[tuple[Row, Row]] = []
    for island in build_islands(events):
        members = [e for e in sorted(island, key=event_sort_key)
                   if not e.get("is_change_player") and _clean(e.get("hitter_acnt"))]
        for a, b in zip(members, members[1:], strict=False):
            if _clean(a["hitter_acnt"]) != _clean(b["hitter_acnt"]):
                out.append((a, b))
    return out


# ===========================================================================
# calc_t2 模擬器（named-column 重寫；保真由「與 calc_t2 輸出逐格相等」驗證）
# ===========================================================================
def simulate_t2(
    rows: list[Row],
    gmeta: dict[Any, tuple[date, str]],
    roles: dict[tuple[Any, str], str],
    bio: dict[str, tuple[str, str, str]],
    merges: frozenset[tuple[Any, Any]] = frozenset(),
) -> tuple[Table, Table, Table]:
    """逐行重現 calc_t2 的 flush 累加。merges 非空＝corrected 模式：

    被合併的島以 canonical `charged_hitter`（記錄規則 9.15(b)；與 FIX1 canonical PA 表
    的 `hitter_acnt` 同一語意）決定歸屬——三振（STRIKEOUT_ACTIONS，含不死三振變體）
    整個打席（PA/AB/SO）記「被判第 2 好球者」，其他結果全記替代擊球員。
    **官方 box 實證 PA 也隨 AB 歸屬**（2025/A/84：6738 PA=3=AB=3 含被中斷打席、
    7091 的 PA=1 是他稍後自己的打席；若 PA 記完成者會得出 PA<AB 的矛盾）。
    情境（壘上/出局/局數/比分/棒次）錨定合併後島的最後一顆投球列。
    未被合併的島維持 legacy 歸屬（首列 hitter），使 delta 嚴格對應缺陷邊界。
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

        # 歸屬：legacy＝首列 hitter；corrected 且為合併島＝canonical charged_hitter
        # （全額記 charged：三振歸被判第 2 好球者、其他歸替代擊球員，box 逐場實證）
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
        pbuckets: list[tuple[str, str]] = [
            ("5", BASE_NAMES[bases]),
            ("6", OUT_NAMES.get(outs, "二出局")),
            ("7", INNING_NAMES.get(inning, "")),
            ("8", p_score),
        ]
        side = _batter_side(h_bats, p_throws)
        if side:
            pbuckets.append(("3", f"VS. {side}"))
        if h_country:
            pbuckets.append(("3", "VS. 本土打者" if _is_local(charged, h_country)
                             else "VS. 外籍打者"))
        for grp, item in pbuckets:
            cnt = pit.setdefault((pitcher, grp, item), Counter())
            for k, v in delta.items():
                if k in _PIT_COLS:
                    cnt[_PIT_COLS[k]] += v
            cnt["pitch_cnt"] += strikes + balls
            cnt["strikes"] += strikes
            cnt["balls"] += balls
    return bat, pit, bat_gofo


def box_crosscheck(
    year: int, kind: str, snos: set, rows: list[Row],
    merges: frozenset[tuple[Any, Any]],
) -> list[dict]:
    """受影響場次逐場對照官方 box（`batting_gamelog`，爬蟲直寫、不經 splits_calc）。

    對每個受影響場次逐人計算單場 PA：legacy 歸屬 vs corrected 歸屬 vs 官方 box。
    box 是**未被重算污染的外部對照**（紅線 2：非自比）。寬過濾：凡 legacy≠box、
    corrected≠box 或 legacy≠corrected 的打者皆列（含只出現在 box 的），
    避免「兩版同值但皆不等於 box」的列被遮蔽。
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


def diff_tables(legacy: Table, corrected: Table) -> list[dict]:
    rows = []
    for key in set(legacy) | set(corrected):
        cols = set(legacy.get(key, ())) | set(corrected.get(key, ()))
        for col in sorted(cols):
            a = legacy.get(key, Counter()).get(col, 0)
            b = corrected.get(key, Counter()).get(col, 0)
            if a != b:
                rows.append({"acnt": key[0], "group": key[1], "item_name": key[2],
                             "col": col, "legacy": a, "corrected": b, "delta": b - a})
    return rows


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
    # (year, kind) → {game_sno → merges 邊界列}（counted 缺陷邊界，供 corrected 模式）
    pair_merges: dict[tuple[int, str], set[tuple[Any, Any]]] = collections.defaultdict(set)

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
                for a, b in trans:
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
                        "prev_disposition": why,
                        "next_disposition": next_why,
                        "outcome": outcome,
                        "islands_between": j - i - 1,
                    }
                    transitions.append(rec)
                    if j - i != 1:
                        anomalies.append({**rec, "why": "transition 跨越中介島"})
                    if next_why != "counted" and why == "counted":
                        anomalies.append({**rec, "why": "prev counted 但 next 未計"})
                    if why != "counted":
                        continue
                    spurious.add(i)
                    outcome_counter[str(outcome)] += 1
                    # canonical 歸屬（僅供報告；模擬器另行計算）
                    non_change = [e for e in sorted(
                        (r for isl_i in range(i, j + 1) for r in islands[isl_i][0]),
                        key=event_sort_key) if not e.get("is_change_player")]
                    term = _terminal_event(non_change)
                    act = _clean(term.get("action_name")) if term else None
                    ch, cp = charged_hitter(non_change, act)
                    exposed.append({
                        **{k: rec[k] for k in ("game", "inning", "half", "outcome")},
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

    # 補 game_date（affected pair 才需要 gmeta）
    gmeta_cache: dict[tuple[int, str], dict] = {}
    for e in exposed:
        yk = e.pop("_year_kind")
        sno = e.pop("_sno")
        if yk not in gmeta_cache:
            _r, gm = load_ctx(*yk)
            gmeta_cache[yk] = gm
        e["game_date"] = str(gmeta_cache[yk][sno][0])

    # ── 選手層級 delta：僅對已發布 splits 的 (year, kind)（歷年僅 A/D 有表）──
    affected_pairs = sorted({(int(e["game"].split("/")[0]), e["game"].split("/")[1])
                             for e in exposed})
    fidelity: dict[str, Any] = {}
    delta_rows: list[dict] = []
    delta_skipped_pairs: list[str] = []
    box_rows: list[dict] = []
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
        corrected = simulate_t2(rows, gmeta, roles, bio, merges)
        for side, a, b in (("bat", legacy[0], corrected[0]),
                           ("pit", legacy[1], corrected[1]),
                           ("bat_gofo", legacy[2], corrected[2])):
            for d in diff_tables(a, b):
                delta_rows.append({"year": year, "kind": kind, "side": side,
                                   "player": names.get(d["acnt"], "?"), **d})

    guard_after = splits_guard()
    if guard_before != guard_after:
        raise AssertionError(f"唯讀紅線失守：{guard_before} != {guard_after}")

    by_player: Counter = Counter()
    for d in delta_rows:
        by_player[(d["side"], d["acnt"], d["player"])] += abs(d["delta"])
    delta_summary = {
        "rows": len(delta_rows),
        "affected_players": len({(d["side"], d["acnt"]) for d in delta_rows}),
        "by_family": dict(Counter(f"{d['side']}/{d['group']}" for d in delta_rows)),
        "by_col_abs": dict(Counter()),
        "skipped_pairs_no_published_splits": delta_skipped_pairs,
        "top_players_by_abs_delta": [
            {"side": s, "acnt": a, "player": p, "sum_abs_delta": v}
            for (s, a, p), v in by_player.most_common(15)],
    }
    col_abs: Counter = Counter()
    for d in delta_rows:
        col_abs[f"{d['side']}/{d['col']}"] += abs(d["delta"])
    delta_summary["by_col_abs"] = dict(col_abs.most_common())

    if out_delta is not None:
        out_delta.write_text(json.dumps({
            "generated_at": datetime.datetime.now().astimezone().isoformat(),
            "note": "corrected＝legacy＋僅合併 counted 缺陷邊界；合併島全額歸屬 canonical "
                    "charged_hitter（規則 9.15(b)：三振歸被判第 2 好球者、其他歸替代擊球員；"
                    "官方 box 逐場實證 PA 隨 AB 歸屬）；delta=corrected−legacy，只列非零格",
            "summary": delta_summary,
            "rows": sorted(delta_rows, key=lambda d: (
                d["year"], d["kind"], d["side"], d["acnt"], d["group"], d["item_name"], d["col"])),
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
            "anomalies": anomalies,
        },
        "exposure": {
            "double_counted_pas": len(exposed),
            "affected_games": len({e["game"] for e in exposed}),
            "by_year": dict(sorted(Counter(
                e["game"].split("/")[0] for e in exposed).items())),
            "by_kind": dict(sorted(Counter(
                e["game"].split("/")[1] for e in exposed).items())),
            "by_outcome": dict(outcome_counter.most_common()),
            "strikeout_charged_to_prev_cases": sum(
                1 for e in exposed if e["strikeout_charged_to_prev"]),
            "rows": exposed,
        },
        "h1_batting_order_shift": {
            "hypothesis": "多出的 PA 使 pa_seq 進位，該場該隊其後所有 PA 的打序歸屬整體位移"
                          "（splits_calc: order = seq %% 9 + 1，家族 10 ORDER_NAMES）",
            "affected_team_games": len(order_shift),
            "total_pas_misattributed": sum(r["pas_after_shift"] for r in order_shift),
            "max_shift": max((r["shift"] for r in order_shift), default=0),
            "rows": order_shift,
        },
        "simulator_fidelity_vs_calc_t2": fidelity,
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
    print(f"scope: {s['games']} games / {s['events']} events")
    print(f"canonical transitions：{tr['total']}，prev 去向：{tr['prev_disposition']}")
    if tr["anomalies"]:
        print(f"⚠️ anomalies：{len(tr['anomalies'])} 筆（詳 artifact）")
    print(f"**實際重複計為 PA**：{ex['double_counted_pas']} 筆／{ex['affected_games']} 場")
    print(f"  逐年：{ex['by_year']}  kind：{ex['by_kind']}")
    print(f"  重複記的結果詞：{dict(list(ex['by_outcome'].items())[:8])}")
    print(f"  9.15(b) 三振歸原打者（被判第 2 好球者）案例："
          f"{ex['strikeout_charged_to_prev_cases']}")
    print(f"H1 打序位移：{h1['affected_team_games']} 個 (場次,球隊)，"
          f"其後被錯誤歸類打序的 PA 共 **{h1['total_pas_misattributed']}** 筆，"
          f"最大位移 {h1['max_shift']}")
    print(f"模擬器保真（==calc_t2）：{list(rep['simulator_fidelity_vs_calc_t2'])}")
    bc = rep["box_crosscheck"]
    print(f"box 交叉驗證：{bc['rows_total']} 筆逐場逐人，corrected 吻合 "
          f"{bc['corrected_matches_box']}／legacy 吻合 {bc['legacy_matches_box']}"
          f"／無 box 資料 {bc['no_box_data']}"
          f"／corrected 不吻合 {len(bc['corrected_mismatches'])}")
    ds = rep["player_delta_summary"]
    print(f"選手層級 delta：{ds['rows']} 格非零／{ds['affected_players']} 位選手"
          f"（family 分布 {ds['by_family']}）")
    print(f"唯讀紅線：分項表前後不變 = {rep['readonly_guard']['unchanged']}")
    if args.out:
        args.out.write_text(json.dumps(rep, ensure_ascii=False, indent=2, default=str) + "\n",
                            encoding="utf-8")
        print(f"→ {args.out}")


if __name__ == "__main__":
    main()
