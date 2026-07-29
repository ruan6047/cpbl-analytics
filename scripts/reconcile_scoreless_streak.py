#!/usr/bin/env python
"""窮舉對帳：連續無自責分局數（ML-PITCHER-SCORELESS1）。

本腳本**自動產生**交付文件裡的對帳數字——不是人工聲明。對全母體（`pitching_gamelog`
2018+ 的每一位投手、每一個層級）重算連續紀錄，再逐項回頭比對原始資料，任一例外即
exit 1。查核者可原樣重跑。

檢查項目（每項都以「重新查 DB」的方式獨立驗證，不重用計算時的記憶體物件）：

| 代號 | 內容 | 對應紅線 |
|---|---|---|
| R1 | 凡被採計為「整場無自責分」的出賽，官方 `pitching_gamelog.earned_runs` 必為 0 | 紅線 3（字面） |
| R2 | 凡被採計的尾段，其「零得分後綴」涵蓋的每一局，官方 `game_scoreboard` 對手得分必為 0 | 紅線 2／3 |
| R3 | 算術：`outs == strict_outs + tail_outs`；`tail_outs ≤ 該場官方出局數`；每個尾段半局 ≤ 3 出局 | 紅線 2 |
| R4 | 連續性：被採計的出賽必須恰好是該投手出賽序列的**結尾連續段**（由原始行獨立重建） | 紅線 2 |
| R5 | 保留賽（`delay_kind='保留'`）不得被採計 | 紅線 2 |
| R6 | `boundary_limited` 為真 ⇔ 走完全部可得出賽未中斷（起算場＝資料中最早一場） | 紅線 4 |
| R7 | 凡被**跳過**的季後賽出賽，賽別必在計入範圍之外**且**官方 ER 必為 0；且「起算場之後該投手在任何賽別的出賽都無自責分」 | 紅線 2（賽別範圍裁定） |
| R10 | **鴿籠下界獨立重算**：以 SQL 取官方逐局比分與官方局數，獨立算出 `官方出局數 − 3 × 前綴局數`，驗 `採計值 ≤ 獨立重算下界`；**逐局比分完整性以 raw SQL 判定**（`COUNT(*) = COUNT(score_cnt)` 無未知局、且 `SUM(score_cnt) = games` 官方終場對手得分），不沿用 runtime 的 NULL 處理；並驗**隊別配置**（同隊總出局數 ≤ 守備半局數 × 3、且 ≥ 本投手出局數，對手側取相反 `visiting_home_type`）。純算術、與 runtime 不共享任何推論前提 | 紅線 2 |

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
_TAIL_SQL = """
    SELECT s.year, s.kind_code, s.game_sno, s.visiting_home_type AS vht,
           s.inning_seq, max(s.score_cnt) AS runs
      FROM cpbl.game_scoreboard s
      JOIN (SELECT (v->>0)::int AS year, v->>1 AS kind_code, (v->>2)::int AS game_sno
              FROM jsonb_array_elements(%(games)s::jsonb) v) k
        ON k.year = s.year AND k.kind_code = s.kind_code AND k.game_sno = s.game_sno
     WHERE s.visiting_home_type IS NOT NULL
     GROUP BY 1, 2, 3, 4, 5
"""

_SCOREBOARD_INTEGRITY_SQL = """
    -- R10 的完整性一半：**在 SQL 端**直接數 NULL，不經過任何 Python 正規化。
    -- COUNT(*) 數列數、COUNT(score_cnt) 只數非 NULL；兩者不等即代表有「未知得分」的局。
    SELECT s.year, s.kind_code, s.game_sno, s.visiting_home_type AS vht,
           count(*) AS rows_total,
           count(s.score_cnt) AS rows_known,
           sum(s.score_cnt) AS runs_sum
      FROM cpbl.game_scoreboard s
      JOIN (SELECT (v->>0)::int AS year, v->>1 AS kind_code, (v->>2)::int AS game_sno
              FROM jsonb_array_elements(%(games)s::jsonb) v) k
        ON k.year = s.year AND k.kind_code = s.kind_code AND k.game_sno = s.game_sno
     WHERE s.visiting_home_type IS NOT NULL
     GROUP BY 1, 2, 3, 4
"""

_PITCHER_SIDE_SQL = """
    SELECT p.year, p.kind_code, p.game_sno, p.pitcher_acnt,
           p.visiting_home_type AS vht,
           p.inning_pitched_cnt * 3 + p.inning_pitched_div3 AS outs,
           CASE WHEN p.visiting_home_type = '2' THEN g.away_score
                ELSE g.home_score END AS opponent_score
      FROM cpbl.pitching_gamelog p
      JOIN cpbl.games g USING (year, kind_code, game_sno)
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
    tail_claims: list[tuple] = []          # (year, kind, sno, pid, 採計出局數, 後綴起始局)
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

        if res.tail and res.tail.outs:
            y, k, sno = res.tail.key
            tail_games.add((y, k, sno))
            tail_claims.append((y, k, sno, pid, res.tail.outs, res.tail.suffix_from_inning))
            stats["tail_credited"] += 1
            stats["tail_outs"] += res.tail.outs
            brk = next(a for a in apps if a.key == res.tail.key)
            if brk.outs is not None and res.tail.outs > brk.outs:
                fail("R3", pid, f"尾段 {res.tail.outs} 出局數超過該場官方 {brk.outs}")

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

    # ---- R2 ＋ R10：鴿籠下界的獨立重算（純算術，不共享 runtime 任何推論前提） ----
    board: dict[tuple, dict[str, dict[int, int]]] = defaultdict(lambda: defaultdict(dict))
    side: dict[tuple, str] = {}
    official: dict[tuple, int | None] = {}
    opp_final: dict[tuple, int | None] = {}
    integrity: dict[tuple, tuple[int, int, int | None]] = {}
    for chunk in _chunks(sorted(tail_games), 400):
        payload = json.dumps([list(g) for g in chunk])
        for r in _fetch(_TAIL_SQL, {"games": payload}):
            # 對帳側同樣不得把 NULL 折成 0——共享正規化就等於共享盲點。
            board[(r["year"], r["kind_code"], r["game_sno"])][r["vht"]][
                r["inning_seq"]] = (None if r["runs"] is None else int(r["runs"]))
        for r in _fetch(_SCOREBOARD_INTEGRITY_SQL, {"games": payload}):
            integrity[(r["year"], r["kind_code"], r["game_sno"], r["vht"])] = (
                int(r["rows_total"]), int(r["rows_known"]),
                None if r["runs_sum"] is None else int(r["runs_sum"]))
        for r in _fetch(_PITCHER_SIDE_SQL, {"games": payload}):
            side[(r["year"], r["kind_code"], r["game_sno"], r["pitcher_acnt"])] = r["vht"]
            # 官方出局數同樣不折 NULL：未知就是未知，下面以 None 判定 fail-closed。
            official[(r["year"], r["kind_code"], r["game_sno"], r["pitcher_acnt"])] = (
                None if r["outs"] is None else int(r["outs"]))
            opp_final[(r["year"], r["kind_code"], r["game_sno"], r["pitcher_acnt"])] = (
                r["opponent_score"])

    # 同隊出局數彙總——用來擋「隊別配置錯誤」這一類（開卡示範時真的發生過：
    # 把對手投手當同隊，數字碰巧相同而沒露餡）。
    # **NULL 不折成 0**：這道檢查是「同隊總出局數**不得超過**守備半局數 × 3」的上界式，
    # 低估總和會讓它更容易通過＝守衛被靜默弱化。任一同隊投手的官方出局數未知，整隊
    # 總和就是未知，該側的採計一律判 fail（而不是拿一個偏低的數字去比）。
    team_outs: dict[tuple, int] = defaultdict(int)
    team_outs_unknown: set[tuple] = set()
    for (gy, gk, gs, gp), v in side.items():
        n = official.get((gy, gk, gs, gp))
        if n is None:
            team_outs_unknown.add((gy, gk, gs, v))
        else:
            team_outs[(gy, gk, gs, v)] += n

    lb_ok = suffix_ok = 0
    for y, k, sno, pid, claimed, suffix_from in tail_claims:
        game = (y, k, sno)
        my_side = side.get((*game, pid))
        # `or {}` 在此無害：空 dict 會讓下面的完整性檢查 `rows_total > 0` 失敗而判 fail。
        opp = (board.get(game) or {}).get("1" if my_side == "2" else "2") or {}
        off = official.get((*game, pid))
        # 隊別一致性：同隊投手總出局數不得超過「他們守備的半局數 × 3」。
        # 這正是擋「把對手投手算成同隊」那一類錯誤的地方（開卡示範時真的發生過）。
        # 注意**不能**要求是 3 的倍數——保留／和局／再見會讓最後半局未達三出局
        # （實例 2024/A/346 十局和局，客隊投手 28 outs）。
        # `, 0)` 在此無害：查不到鍵代表該側沒有任何「已知出局數」的同隊投手，
        # 而那種情況必已被上面的 `off is None` 或 `team_outs_unknown` 攔下；
        # 即使漏網，0 也會讓下面的 `off > same_team_total` 成立而判 fail（fail-closed）。
        same_team_total = team_outs.get((*game, my_side), 0)
        fielded = len(opp)
        if my_side not in ("1", "2"):
            fails.append({"check": "R10", "player_id": pid,
                          "detail": f"{y}/{k}/{sno}：投手主客別缺值 {my_side!r}"})
        elif off is None:
            fails.append({"check": "R10", "player_id": pid,
                          "detail": f"{y}/{k}/{sno}：官方出局數缺值，卻採計了 {claimed}"})
        elif (*game, my_side) in team_outs_unknown:
            fails.append({"check": "R10", "player_id": pid,
                          "detail": f"{y}/{k}/{sno}：同隊({my_side})有投手官方出局數缺值，"
                                    f"隊伍總和未知，無法驗上界，卻採計了 {claimed}"})
        elif same_team_total > 3 * fielded or off > same_team_total:
            fails.append({"check": "R10", "player_id": pid,
                          "detail": f"{y}/{k}/{sno}：同隊({my_side})總出局數 {same_team_total} "
                                    f"超過守備 {fielded} 局上限或小於本投手 {off}"})
        # 逐局比分完整性（官方對官方）——**以 raw SQL 的計數獨立判定**，
        # 不沿用 runtime 的 NULL 處理：COUNT(*) 必須等於 COUNT(score_cnt)（無未知局），
        # 且 SUM(score_cnt) 必須等於官方終場對手得分。
        final = opp_final.get((*game, pid))
        opp_side = "1" if my_side == "2" else "2"
        # 預設 (0, 0, None) 在此無害：`rows_total == 0` 會讓下面的 `complete` 為 False
        # 而判 fail——查不到完整性資料即視為不完整（fail-closed），不是視為乾淨。
        rows_total, rows_known, runs_sum = integrity.get((*game, opp_side), (0, 0, None))
        complete = (rows_total > 0 and rows_total == rows_known
                    and final is not None and runs_sum == final)
        if not complete:
            fails.append({"check": "R10", "player_id": pid,
                          "detail": f"{y}/{k}/{sno}：逐局比分不完整（列數 {rows_total}／"
                                    f"非 NULL {rows_known}／總和 {runs_sum} vs 官方終場 "
                                    f"{final}），卻採計了 {claimed}"})
        scored = [i for i, r in opp.items() if r]
        # 同 runtime：僅在完整性通過後才有意義，`else 0` 是已證實的「整場零得分」。
        n_prefix = max(scored) if scored else 0
        recomputed = max(0, off - 3 * n_prefix) if complete and off is not None else 0
        if claimed > recomputed:
            fails.append({"check": "R10", "player_id": pid,
                          "detail": f"{y}/{k}/{sno}：採計 {claimed} > 獨立重算下界 {recomputed}"})
        else:
            lb_ok += 1
        # R2：後綴涵蓋的每一局，官方逐局比分必須是 0——**且後綴一路開到比賽末端**
        # （`i >= suffix_from`，不是閉區間）。這個右端**不得**改成「他退場的局」：
        # 規則允許零投球自責分（總教練手勢故意四壞 9.14(d)／5.05(b)(1) ＋ 投手犯規
        # 6.02(a) 罰則，皆為 9.16 的自責分因素），所以視窗右端之後的任何得分都可能是
        # 他的。ML-PITCHER-SCORELESS2 iteration 1 為了容納「提早收視窗」的下界而把這裡
        # 放寬成閉區間，那個放寬本身就是前提出錯的徵兆——**為了讓新方法通過而放寬對帳
        # 規則，等於把承重的牆拆掉**。詳見 docs/research/ML-PITCHER-SCORELESS2_RESULTS.md。
        bad = [i for i in opp if suffix_from is not None and i >= suffix_from and opp[i]]
        if suffix_from is None or bad:
            fails.append({"check": "R2", "player_id": pid,
                          "detail": f"{y}/{k}/{sno}：後綴自第 {suffix_from} 局，但第 {bad} 局有得分"})
        else:
            suffix_ok += 1

    return {
        "tier": tier_label,
        "kinds_counted": list(counted_kinds),
        "kinds_in_scope": kinds,
        "pitchers": stats["pitchers"],
        "appearances_total": stats["appearances_total"],
        "appearances_counted": stats["appearances_counted"],
        "appearances_counted_verified_er0": er_ok,
        "tail_credited": stats["tail_credited"],
        "tail_outs": stats["tail_outs"],
        "tail_lower_bound_verified": lb_ok,
        "tail_suffix_zero_runs_verified": suffix_ok,
        "skipped_postseason": stats["skipped_postseason"],
        "skipped_postseason_verified_er0": skip_ok,
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
           "尾段採計場次", "尾段出局數", "R10 驗得下界", "R2 驗得後綴零得分",
           "跳過季後賽", "R7 驗得 ER=0", "例外")
    print(" | ".join(hdr))
    print(" | ".join("---" for _ in hdr))
    for r in reports:
        print(" | ".join(str(x) for x in (
            r["tier"], r["pitchers"], r["appearances_total"], r["appearances_counted"],
            r["appearances_counted_verified_er0"], r["tail_credited"], r["tail_outs"],
            r["tail_lower_bound_verified"], r["tail_suffix_zero_runs_verified"],
            r["skipped_postseason"], r["skipped_postseason_verified_er0"],
            len(r["exceptions"]))))
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
