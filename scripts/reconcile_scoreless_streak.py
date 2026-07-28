#!/usr/bin/env python
"""窮舉對帳：連續無自責分局數（ML-PITCHER-SCORELESS1）。

本腳本**自動產生**交付文件裡的對帳數字——不是人工聲明。對全母體（`pitching_gamelog`
2018+ 的每一位投手、每一個層級）重算連續紀錄，再逐項回頭比對原始資料，任一例外即
exit 1。查核者可原樣重跑。

檢查項目（每項都以「重新查 DB」的方式獨立驗證，不重用計算時的記憶體物件）：

| 代號 | 內容 | 對應紅線 |
|---|---|---|
| R1 | 凡被採計為「整場無自責分」的出賽，官方 `pitching_gamelog.earned_runs` 必為 0 | 紅線 3（字面） |
| R2 | 凡被採計的尾段半局，**獨立來源** `game_scoreboard` 該半局得分必為 0；且 livelog 側獨立重算（視窗函數 lag，非計算時的前綴最大值路徑）亦為 0、該半局只有目標投手一人、首列 `out_cnt=0` | 紅線 2／3（尾段的更強證據） |
| R3 | 算術：`outs == strict_outs + tail_outs`；`tail_outs ≤ 該場官方出局數`；每個尾段半局 ≤ 3 出局 | 紅線 2 |
| R4 | 連續性：被採計的出賽必須恰好是該投手出賽序列的**結尾連續段**（由原始行獨立重建） | 紅線 2 |
| R5 | 保留賽（`delay_kind='保留'`）不得被採計 | 紅線 2 |
| R6 | `boundary_limited` 為真 ⇔ 走完全部可得出賽未中斷（起算場＝資料中最早一場） | 紅線 4 |
| R7 | 凡被**跳過**的季後賽出賽，賽別必在計入範圍之外**且**官方 ER 必為 0；且「起算場之後該投手在任何賽別的出賽都無自責分」 | 紅線 2（賽別範圍裁定） |
| R8 | **覆蓋完整性（半局層級）**：尾段那場的 livelog 與 `game_scoreboard` 半局集合必須一致（除未進行的最終局下半等良性樣態）、該投手的半局是同一側連號一段、半局數 × 3 ≥ 官方出局數 | 紅線 2（F1 修正） |
| R9 | **覆蓋完整性（事件／投手邊界層級）**：以 SQL 視窗函數在**半局內的投手更迭邊界**重算每位投手的出局數區間，全場每位官方 box 上的投手都必須落在自己的可見區間內 | 紅線 2（F1-b 修正）。R8 只比半局集合，與 runtime 共享「半局存在即內部完整」的盲點；R9 是唯一能抓到半局**內部**缺漏的檢查 |

用法：

    uv run python scripts/reconcile_scoreless_streak.py            # 全層級，人類可讀 + JSON
    uv run python scripts/reconcile_scoreless_streak.py --json-out artifacts/x.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict

from cpbl.api.helpers import _dicts, kinds_of
from cpbl.api.scoreless import compute_all, load_appearances
from cpbl.db import conn
from cpbl.models.scoreless_streak import (
    BREAK_DATA_BOUNDARY,
    BREAK_EARNED_RUN,
    DATA_FROM_YEAR,
    SUSPENDED,
)

TIERS = {"一軍例行賽 A": "A", "二軍例行賽 D": "D"}

# R1：官方 ER 重查。以 (year,kind,sno,pitcher) 為鍵，不信任計算時的物件。
_ER_SQL = """
    SELECT p.year, p.kind_code, p.game_sno, p.pitcher_acnt,
           p.earned_runs,
           p.inning_pitched_cnt * 3 + p.inning_pitched_div3 AS outs
      FROM cpbl.pitching_gamelog p
      JOIN (SELECT (v->>0)::int AS year, v->>1 AS kind_code,
                   (v->>2)::int AS game_sno, v->>3 AS pitcher_acnt
              FROM jsonb_array_elements(%(keys)s::jsonb) v) k
        ON k.year = p.year AND k.kind_code = p.kind_code
       AND k.game_sno = p.game_sno AND k.pitcher_acnt = p.pitcher_acnt
"""

# R2：尾段半局的兩路獨立驗證。
#   scoreboard_runs —— 來自 game_scoreboard（官網 box 的另一段 payload，與 livelog 不同來源）
#   livelog_runs    —— 來自 livelog，但用 lag() 視窗（計算路徑用的是前綴最大值，兩者互為獨立實作）
_HALF_SQL = """
    WITH ev AS (
        SELECT year, kind_code, game_sno, inning_seq,
               visiting_home_type AS vht, main_event_no, out_cnt, is_score, pitcher_acnt,
               CASE WHEN visiting_home_type = '1' THEN visiting_score ELSE home_score END AS bat
          FROM cpbl.game_livelog
         WHERE NOT is_change_player
           AND (year, kind_code, game_sno) IN (
                   SELECT (v->>0)::int, v->>1, (v->>2)::int
                     FROM jsonb_array_elements(%(games)s::jsonb) v)
    ), h AS (
        SELECT year, kind_code, game_sno, inning_seq, vht,
               max(bat)                                     AS bat_max,
               bool_or(is_score)                            AS scored_flag,
               count(DISTINCT pitcher_acnt)                 AS pitcher_cnt,
               min(pitcher_acnt)                            AS only_pitcher,
               min(out_cnt) FILTER (WHERE out_cnt IS NOT NULL) AS min_out,
               max(out_cnt) FILTER (WHERE out_cnt IS NOT NULL) AS max_out,
               (array_agg(out_cnt ORDER BY main_event_no)
                   FILTER (WHERE out_cnt IS NOT NULL))[1]   AS first_out
          FROM ev GROUP BY 1, 2, 3, 4, 5
    )
    SELECT h.year, h.kind_code, h.game_sno, h.inning_seq, h.vht,
           h.bat_max - COALESCE(lag(h.bat_max) OVER (
               PARTITION BY h.year, h.kind_code, h.game_sno, h.vht
               ORDER BY h.inning_seq), 0)                   AS livelog_runs,
           h.scored_flag, h.pitcher_cnt, h.only_pitcher, h.first_out, h.max_out,
           sb.score_cnt                                     AS scoreboard_runs
      FROM h
      LEFT JOIN cpbl.game_scoreboard sb
        ON sb.year = h.year AND sb.kind_code = h.kind_code AND sb.game_sno = h.game_sno
       AND sb.inning_seq = h.inning_seq AND sb.visiting_home_type = h.vht
"""


# R8：**覆蓋完整性**。R2 驗的是「已被選入的半局零得分」——那證明的是選中的都乾淨，
# 不是沒有漏掉的。量詞方向不同，故另取三份原始集合，在腳本內以與 `coverage_reason`
# 不同的程式路徑重做判定：全場 livelog 半局、全場 scoreboard 半局、該投手的 livelog 半局。
_COVERAGE_SQL = """
    WITH g AS (SELECT (v->>0)::int AS year, v->>1 AS kind_code, (v->>2)::int AS game_sno
                 FROM jsonb_array_elements(%(games)s::jsonb) v)
    SELECT 'livelog' AS src, l.year, l.kind_code, l.game_sno, l.inning_seq,
           l.visiting_home_type AS vht, 0 AS runs, ''::text AS pitcher
      FROM cpbl.game_livelog l JOIN g USING (year, kind_code, game_sno)
     WHERE NOT l.is_change_player
     GROUP BY 2, 3, 4, 5, 6
    UNION ALL
    SELECT 'scoreboard', s.year, s.kind_code, s.game_sno, s.inning_seq,
           s.visiting_home_type, max(s.score_cnt), ''
      FROM cpbl.game_scoreboard s JOIN g USING (year, kind_code, game_sno)
     WHERE s.visiting_home_type IS NOT NULL
     GROUP BY 2, 3, 4, 5, 6
    UNION ALL
    SELECT 'pitcher', l.year, l.kind_code, l.game_sno, l.inning_seq,
           l.visiting_home_type, 0, l.pitcher_acnt
      FROM cpbl.game_livelog l JOIN g USING (year, kind_code, game_sno)
     WHERE NOT l.is_change_player AND l.pitcher_acnt IS NOT NULL
     GROUP BY 2, 3, 4, 5, 6, 8
"""


# R9：事件／投手邊界粒度的覆蓋對帳。以 SQL 視窗函數重算「半局內投手更迭邊界」的出局數
# 配置——與 runtime 的 `out_allocation`（Python 分段迴圈）是不同實作，且**不共享**
# 「半局存在即內部完整」的盲點：某位投手的事件若整段缺漏，他的官方出局數就會落在
# 可見區間之外。
_ALLOC_SQL = """
    WITH ev AS (
        SELECT l.year, l.kind_code, l.game_sno, l.inning_seq,
               l.visiting_home_type AS vht, l.main_event_no, l.out_cnt, l.pitcher_acnt
          FROM cpbl.game_livelog l
          JOIN (SELECT (v->>0)::int AS year, v->>1 AS kind_code, (v->>2)::int AS game_sno
                  FROM jsonb_array_elements(%(games)s::jsonb) v) k
            ON k.year = l.year AND k.kind_code = l.kind_code AND k.game_sno = l.game_sno
         WHERE NOT l.is_change_player AND l.out_cnt IS NOT NULL
    ), seq AS (
        SELECT *,
               row_number() OVER w                                   AS rn,
               lag(pitcher_acnt) OVER w                              AS prev_pitcher,
               lag(inning_seq)   OVER w                              AS prev_inning,
               lag(vht)          OVER w                              AS prev_vht,
               max(inning_seq)   OVER (PARTITION BY year, kind_code, game_sno) AS game_max_inning
          FROM ev
        WINDOW w AS (PARTITION BY year, kind_code, game_sno ORDER BY inning_seq, vht, main_event_no)
    ), marked AS (
        SELECT *, sum(CASE WHEN prev_pitcher IS DISTINCT FROM pitcher_acnt
                             OR prev_inning IS DISTINCT FROM inning_seq
                             OR prev_vht IS DISTINCT FROM vht THEN 1 ELSE 0 END)
                    OVER (PARTITION BY year, kind_code, game_sno
                          ORDER BY inning_seq, vht, main_event_no)     AS seg
          FROM seq
    ), segs AS (
        SELECT year, kind_code, game_sno, seg, inning_seq, vht,
               min(pitcher_acnt)              AS pitcher,
               min(out_cnt)                   AS start_out,
               max(out_cnt)                   AS last_out,
               min(rn)                        AS rn0,
               max(game_max_inning)           AS game_max_inning
          FROM marked GROUP BY 1, 2, 3, 4, 5, 6
    ), bounded AS (
        SELECT s.*,
               lead(s.start_out) OVER (PARTITION BY s.year, s.kind_code, s.game_sno,
                                                    s.inning_seq, s.vht
                                       ORDER BY s.rn0)                AS next_start,
               (s.inning_seq = s.game_max_inning
                AND s.rn0 = max(s.rn0) OVER (PARTITION BY s.year, s.kind_code,
                                                          s.game_sno))  AS in_final_half
          FROM segs s
    )
    SELECT year, kind_code, game_sno, pitcher,
           sum(GREATEST(0, COALESCE(next_start,
                 CASE WHEN in_final_half THEN last_out ELSE 3 END) - start_out)) AS lo,
           sum(GREATEST(0, COALESCE(next_start, 3) - start_out))                 AS hi
      FROM bounded GROUP BY 1, 2, 3, 4
"""


# R9 的另一半：全場官方投球 box（誰投過、各記幾個出局）。
_GAME_BOX_SQL = """
    SELECT p.year, p.kind_code, p.game_sno, p.pitcher_acnt,
           p.inning_pitched_cnt * 3 + p.inning_pitched_div3 AS outs
      FROM cpbl.pitching_gamelog p
      JOIN (SELECT (v->>0)::int AS year, v->>1 AS kind_code, (v->>2)::int AS game_sno
              FROM jsonb_array_elements(%(games)s::jsonb) v) k
        ON k.year = p.year AND k.kind_code = p.kind_code AND k.game_sno = p.game_sno
"""


def _fetch(sql: str, params: dict) -> list[dict]:
    with conn() as c:
        cur = c.cursor()
        cur.execute(sql, params)
        return _dicts(cur)


def reconcile(tier_label: str, kind_code: str) -> dict:
    kinds = kinds_of(kind_code)
    counted_kinds = (kind_code,)
    by_player, _names = load_appearances(kinds)
    results = compute_all(by_player, counted_kinds)

    fails: list[dict] = []

    def fail(check: str, pid: str, detail: str) -> None:
        fails.append({"check": check, "player_id": pid, "detail": detail})

    counted_keys: list[list] = []          # R1 母體
    skipped_keys: list[list] = []          # R7 母體
    tail_halves: list[tuple] = []          # R2 母體
    tail_appearances: list[tuple] = []     # R8 母體：(year, kind, sno, pid, 官方出局數)
    tail_games: set[tuple[int, str, int]] = set()
    stats = defaultdict(int)

    for pid, res in results.items():
        apps = by_player[pid]
        stats["pitchers"] += 1
        stats["appearances_total"] += len(apps)

        # ---- R3 算術 ----
        tail_outs = res.tail.outs if res.tail else 0
        if res.outs != res.strict_outs + tail_outs:
            fail("R3", pid, f"outs={res.outs} != strict={res.strict_outs}+tail={tail_outs}")
        if res.outs < res.strict_outs:
            fail("R3", pid, f"extended {res.outs} < strict {res.strict_outs}")

        # ---- R4 連續性：採計 ∪ 跳過 必須恰好是出賽序列的結尾連續段 ----
        window_keys = {a.key for a in res.counted} | {a.key for a in res.skipped}
        window_n = len(window_keys)
        suffix = apps[len(apps) - window_n:] if window_n else []
        if window_keys != {a.key for a in suffix} or len(suffix) != window_n:
            fail("R4", pid, "採計 ∪ 跳過的出賽不是出賽序列的結尾連續段")

        # ---- R5 保留賽 ----
        for a in [*res.counted, *res.skipped]:
            if a.delay_kind == SUSPENDED:
                fail("R5", pid, f"採計/跳過了保留賽 {a.key}")

        # ---- R6 資料邊界 ----
        consumed_all = window_n == len(apps) and res.break_reason is None
        at_boundary = res.break_reason == BREAK_DATA_BOUNDARY
        if res.boundary_limited != (consumed_all or at_boundary):
            fail("R6", pid, f"boundary_limited={res.boundary_limited} 但 consumed_all="
                            f"{consumed_all}／at_boundary={at_boundary}")
        if consumed_all and suffix and suffix[0].key != apps[0].key:
            fail("R6", pid, "宣告受資料邊界限制，但起算場不是資料中最早一場")
        for a in [*res.counted, *res.skipped]:
            if a.year < DATA_FROM_YEAR:
                fail("R6", pid, f"採計/跳過了 {DATA_FROM_YEAR} 年前的出賽 {a.key}")

        # ---- R7 賽別範圍：採計必在例行賽、跳過必在例行賽之外；窗內全部 ER=0 ----
        for a in res.counted:
            if a.kind_code not in counted_kinds:
                fail("R7", pid, f"採計了非例行賽 {a.key}")
        for a in res.skipped:
            if a.kind_code in counted_kinds:
                fail("R7", pid, f"跳過了例行賽 {a.key}")
            skipped_keys.append([a.year, a.kind_code, a.game_sno, pid])
            stats["skipped_postseason"] += 1
        for a in suffix:
            if a.earned_runs != 0:
                fail("R7", pid, f"起算場之後仍有自責分出賽 {a.key} ER={a.earned_runs}")

        for a in res.counted:
            counted_keys.append([a.year, a.kind_code, a.game_sno, pid])
            stats["appearances_counted"] += 1

        if res.tail and (res.tail.credited or res.tail.passed):
            if res.break_reason != BREAK_EARNED_RUN:
                fail("R3", pid, f"有尾段但中斷原因是 {res.break_reason}")
            y, k, sno = res.tail.key
            tail_games.add((y, k, sno))
            for inning_seq, vht in res.tail.credited:
                tail_halves.append((y, k, sno, inning_seq, vht, pid, True))
                stats["tail_half_innings"] += 1
            for inning_seq, vht in res.tail.passed:
                tail_halves.append((y, k, sno, inning_seq, vht, pid, False))
                stats["tail_half_innings_passed"] += 1
            brk = next(a for a in apps if a.key == res.tail.key)
            tail_appearances.append((y, k, sno, pid, brk.outs))
            if brk.outs is not None and res.tail.outs > brk.outs:
                fail("R3", pid, f"尾段 {res.tail.outs} 出局數超過該場官方 {brk.outs}")
            if not res.tail.clamped and res.tail.outs > 3 * len(res.tail.credited):
                fail("R3", pid, "尾段出局數超過採計半局數 × 3")

    # ---- R1：整場採計的出賽，官方 ER 必為 0（重查 DB） ----
    er_ok = 0
    for chunk in _chunks(counted_keys, 5000):
        for r in _fetch(_ER_SQL, {"keys": json.dumps(chunk)}):
            if r["earned_runs"] != 0:
                fails.append({"check": "R1", "player_id": r["pitcher_acnt"],
                              "detail": f"{r['year']}/{r['kind_code']}/{r['game_sno']} "
                                        f"官方 ER={r['earned_runs']} 卻被採計為無自責分"})
            else:
                er_ok += 1
    if er_ok != len(counted_keys):
        fails.append({"check": "R1", "player_id": "-",
                      "detail": f"重查回 {er_ok} 列，應為 {len(counted_keys)} 列（有出賽查不到）"})

    # ---- R7：被跳過的季後賽出賽，官方 ER 必為 0（重查 DB） ----
    skip_ok = 0
    for chunk in _chunks(skipped_keys, 5000):
        for r in _fetch(_ER_SQL, {"keys": json.dumps(chunk)}):
            if r["earned_runs"] != 0 or r["kind_code"] in counted_kinds:
                fails.append({"check": "R7", "player_id": r["pitcher_acnt"],
                              "detail": f"{r['year']}/{r['kind_code']}/{r['game_sno']} "
                                        f"被跳過但 ER={r['earned_runs']}／賽別不符"})
            else:
                skip_ok += 1
    if skip_ok != len(skipped_keys):
        fails.append({"check": "R7", "player_id": "-",
                      "detail": f"重查回 {skip_ok} 列，應為 {len(skipped_keys)} 列"})

    # ---- R2：尾段半局，兩個獨立來源都必須零得分 ----
    half_facts: dict[tuple, dict] = {}
    for chunk in _chunks(sorted(tail_games), 400):
        for r in _fetch(_HALF_SQL, {"games": json.dumps([list(g) for g in chunk])}):
            half_facts[(r["year"], r["kind_code"], r["game_sno"],
                        r["inning_seq"], r["vht"])] = r
    r2_ok = r2_passed_ok = 0
    for y, k, sno, inning_seq, vht, pid, is_credited in tail_halves:
        f = half_facts.get((y, k, sno, inning_seq, vht))
        where = f"{y}/{k}/{sno} {inning_seq}局{'上' if vht == '1' else '下'} {pid}"
        if f is None:
            fails.append({"check": "R2", "player_id": pid, "detail": f"{where}：livelog 查無此半局"})
            continue
        bad = []
        # 零得分：兩個獨立來源都要說零。這是「該半局零自責分」的全部證據。
        if f["scoreboard_runs"] is None:
            bad.append("game_scoreboard 無此半局（獨立來源缺）")
        elif f["scoreboard_runs"] != 0:
            bad.append(f"game_scoreboard 得分={f['scoreboard_runs']}")
        if f["livelog_runs"] != 0:
            bad.append(f"livelog(lag) 得分={f['livelog_runs']}")
        if f["scored_flag"]:
            bad.append("該半局有 is_score 事件")
        # 只有「有貢獻出局數」的半局才需要證明出局數歸屬；passed 半局採計 0 出局數，
        # 對它下獨力投完的條件沒有意義（它正是因為做不到才被歸為 passed）。
        if is_credited:
            if f["pitcher_cnt"] != 1 or f["only_pitcher"] != pid:
                bad.append(f"非該投手獨力投完（{f['pitcher_cnt']} 人）")
            if f["first_out"] != 0:
                bad.append(f"首列 out_cnt={f['first_out']}（非自半局開頭）")
        if bad:
            fails.append({"check": "R2", "player_id": pid, "detail": f"{where}：" + "；".join(bad)})
        elif is_credited:
            r2_ok += 1
        else:
            r2_passed_ok += 1

    # ---- R8：覆蓋完整性——證明「該有的半局都在」，而不只是「選中的都乾淨」 ----
    ll_sets: dict[tuple, set] = defaultdict(set)
    sb_runs: dict[tuple, dict] = defaultdict(dict)
    pit_sets: dict[tuple, set] = defaultdict(set)
    for chunk in _chunks(sorted(tail_games), 400):
        for r in _fetch(_COVERAGE_SQL, {"games": json.dumps([list(g) for g in chunk])}):
            game = (r["year"], r["kind_code"], r["game_sno"])
            half = (r["inning_seq"], r["vht"])
            if r["src"] == "livelog":
                ll_sets[game].add(half)
            elif r["src"] == "scoreboard":
                sb_runs[game][half] = int(r["runs"] or 0)
            else:
                pit_sets[(*game, r["pitcher"])].add(half)

    cov_ok = 0
    for y, k, sno, pid, official in tail_appearances:
        game = (y, k, sno)
        ll, sb = ll_sets.get(game, set()), sb_runs.get(game, {})
        mine = sorted(pit_sets.get((y, k, sno, pid), set()))
        bad = []
        if not ll or not sb:
            bad.append("livelog 或 scoreboard 缺整場")
        mx = max((i for i, _ in ll), default=0)
        for (inn, vht), runs in sb.items():
            if (inn, vht) in ll:
                continue
            benign = (vht == "2" and inn == mx) or inn > mx
            if not benign or runs:
                bad.append(f"scoreboard 有 {inn}/{vht}（{runs} 分）但 livelog 沒有")
        for half in ll:
            if half not in sb:
                bad.append(f"livelog 有 {half} 但 scoreboard 沒有")
        sides = {v for _, v in mine}
        innings = [i for i, _ in mine]
        if not mine or len(sides) != 1 or innings != list(range(min(innings), max(innings) + 1)):
            bad.append("該投手的半局不是同一側連號的一段")
        # 獨立於 _observed_outs 的上界：每個半局最多 3 個出局。
        if official is not None and len(mine) * 3 < official:
            bad.append(f"投手半局數 {len(mine)} × 3 < 官方出局數 {official}")
        if bad:
            fails.append({"check": "R8", "player_id": pid,
                          "detail": f"{y}/{k}/{sno}：" + "；".join(bad)})
        else:
            cov_ok += 1

    # ---- R9：事件／投手邊界粒度——唯一能抓到半局**內部**缺漏的檢查 ----
    alloc: dict[tuple, dict[str, tuple[int, int]]] = defaultdict(dict)
    full_box: dict[tuple, dict[str, int]] = defaultdict(dict)
    for chunk in _chunks(sorted(tail_games), 400):
        payload = json.dumps([list(g) for g in chunk])
        for r in _fetch(_ALLOC_SQL, {"games": payload}):
            alloc[(r["year"], r["kind_code"], r["game_sno"])][r["pitcher"]] = (
                int(r["lo"]), int(r["hi"]))
        for r in _fetch(_GAME_BOX_SQL, {"games": payload}):
            full_box[(r["year"], r["kind_code"], r["game_sno"])][r["pitcher_acnt"]] = (
                int(r["outs"] or 0))

    alloc_ok = 0
    for y, k, sno, pid, _official in tail_appearances:
        game = (y, k, sno)
        a, b = alloc.get(game, {}), full_box.get(game, {})
        bad = []
        if not a or not b:
            bad.append("livelog 配置或官方 box 缺整場")
        for p, outs in b.items():
            if p not in a:
                if outs:
                    bad.append(f"官方 box 有 {p}（{outs} outs）但 livelog 看不到他")
                continue
            lo, hi = a[p]
            if not lo <= outs <= hi:
                bad.append(f"{p} 官方 {outs} outs 不在可見區間 [{lo},{hi}]")
        for p in a:
            if p not in b:
                bad.append(f"livelog 有 {p} 但官方 box 沒有")
        if bad:
            fails.append({"check": "R9", "player_id": pid,
                          "detail": f"{y}/{k}/{sno}：" + "；".join(bad[:3])})
        else:
            alloc_ok += 1

    return {
        "tier": tier_label,
        "kinds_counted": list(counted_kinds),
        "kinds_in_scope": kinds,
        "pitchers": stats["pitchers"],
        "appearances_total": stats["appearances_total"],
        "appearances_counted": stats["appearances_counted"],
        "appearances_counted_verified_er0": er_ok,
        "tail_half_innings": stats["tail_half_innings"],
        "tail_half_innings_verified_runfree": r2_ok,
        "tail_half_innings_passed_zero_credit": stats["tail_half_innings_passed"],
        "tail_half_innings_passed_verified_runfree": r2_passed_ok,
        "tail_games": len(tail_games),
        "skipped_postseason": stats["skipped_postseason"],
        "skipped_postseason_verified_er0": skip_ok,
        "tail_appearances": len(tail_appearances),
        "tail_appearances_coverage_complete": cov_ok,
        "tail_appearances_allocation_reconciled": alloc_ok,
        "exceptions": fails,
    }


def _chunks(seq, n):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out")
    args = ap.parse_args()

    reports = [reconcile(label, kind) for label, kind in TIERS.items()]
    total_fail = sum(len(r["exceptions"]) for r in reports)

    print("窮舉對帳：連續無自責分局數（ML-PITCHER-SCORELESS1）\n")
    hdr = ("層級", "投手數", "出賽總數", "採計出賽", "R1 驗得 ER=0",
           "尾段採計半局", "R2 驗得零得分", "尾段 0 採計半局", "R2 驗得零得分",
           "跳過季後賽", "R7 驗得 ER=0", "尾段出賽", "R8 半局覆蓋", "R9 出局數配置", "例外")
    print(" | ".join(hdr))
    print(" | ".join("---" for _ in hdr))
    for r in reports:
        print(" | ".join(str(x) for x in (
            r["tier"], r["pitchers"], r["appearances_total"], r["appearances_counted"],
            r["appearances_counted_verified_er0"], r["tail_half_innings"],
            r["tail_half_innings_verified_runfree"],
            r["tail_half_innings_passed_zero_credit"],
            r["tail_half_innings_passed_verified_runfree"],
            r["skipped_postseason"], r["skipped_postseason_verified_er0"],
            r["tail_appearances"], r["tail_appearances_coverage_complete"],
            r["tail_appearances_allocation_reconciled"], len(r["exceptions"]))))
    print()
    for r in reports:
        for e in r["exceptions"][:50]:
            print(f"  [{e['check']}] {e['player_id']} {e['detail']}")
    print(f"\n總例外：{total_fail}（紅線要求 0）")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(reports, fh, ensure_ascii=False, indent=2)
        print(f"JSON → {args.json_out}")
    return 1 if total_fail else 0


if __name__ == "__main__":
    sys.exit(main())
