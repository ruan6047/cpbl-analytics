"""INGEST-GAME-TM-REFACTOR1-G4 Phase A：唯讀量測三件套（全部產 artifact，不得人工轉述）。

**唯讀**：全檔只下 SELECT，不寫任何表、不爬網。

子命令：
- `equipped`：以**卡面字面 SQL** 重跑近期感知設備判準（A＋D），輸出逐球場 `hit/window`
  與 `equipped`，並機械檢核卡面〈驗收條件〉列出的兩項不變量。
  判準常數（窗口 10／門檻 0.80）是需求方 2026-08-04 裁定的營運政策（紅線 4），
  本腳本只**驗證**不選定，任何不符一律照實輸出，不調參。
- `requests`：請求量實測。回放最近 N 個 refresh 日的當日窗（`[昨天, 今天]`），對同一組
  場次分別數兩個維度的請求數：場次維度＝場數；投手維度＝那些場的出賽投手數。
  另攤提每週全季重跑，輸出兩個降幅數字。
- `rollback`：回滾門檻的**降級版預先登錄回測**——不做參數搜尋，只回放現行暫定值
  （切換前 p05 地板、連續 2 個 eligible day）會觸發幾次。
  **容忍度（每季 ≤2 次）於裁定時固定，回放結果不得反過來修改門檻或容忍度。**

    uv run python scripts/g4_phase_a_metrics.py all --year 2026
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
from collections import defaultdict
from pathlib import Path

from cpbl.db import conn

# ── 需求方 2026-08-04 裁定的營運政策常數（紅線 4：門檻先固定，事後不得放寬）────────
EQUIPPED_WINDOW = 10      # 近 N 場完成場
EQUIPPED_RATIO = 0.80     # 達標門檻（沿用既有 COVER_OK；沿用不等於推導）
MIN_PITCHES = 50          # 場次納入達標判定的最低投球數
FLOOR_PERCENTILE = 0.05   # 切換前單場覆蓋率分布的第 5 百分位數 → 日聚合地板
CONSECUTIVE_ELIGIBLE = 2  # 連續 N 個 eligible day 低於地板才觸發
MIN_FLOOR_POPULATION = 30 # 地板母體不足此數 → 該 kind 不得切換（fail closed）
FALSE_ALARM_TOLERANCE = 2 # 每季誤報容忍度（≥2 須回報需求方，不得自行調參）

# 卡面〈驗收條件〉釘死的兩項不變量（2026-08-03 資料截點的期望值）。
# 執行時資料已前進，故**以性質檢核為主、數值對照為輔**：性質＝「死設備要掉出」與
# 「單場 downtime 不得失去自癒」，數值若因新場次而變動屬正常，照實輸出不修飾。
_INVARIANT_EXPECT = {
    "A": {"false": ["大巨蛋", "台東", "嘉義市", "花蓮"], "true": ["新莊", "洲際", "亞太主", "斗六"]},
    "D": {"false": ["亞太副", "嘉義市", "場地未定"],
          "true": ["園區", "青埔", "樂天桃園", "皇鷹學院", "斗六", "澄清湖"]},
}


def _now() -> str:
    return _dt.datetime.now().astimezone().isoformat()


def _write(outdir: Path, name: str, obj: dict) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    p = outdir / name
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str) + "\n")
    print(f"  → {p}")
    return p


# ── 共用：逐場覆蓋率（cov）─────────────────────────────────────────────────────
_COV_SQL = """
SELECT gm.venue, gm.game_sno, gm.game_date,
  (SELECT count(*) FROM cpbl.game_livelog ll WHERE ll.year=gm.year
     AND ll.kind_code=gm.kind_code AND ll.game_sno=gm.game_sno
     AND (ll.is_ball OR ll.is_strike)) AS pitches,
  (SELECT count(*) FROM cpbl.pitch_tracking pt WHERE pt.year=gm.year
     AND pt.kind_code=gm.kind_code AND pt.game_sno=gm.game_sno) AS tracked
FROM cpbl.games gm
WHERE gm.year=%s AND gm.kind_code=%s AND gm.home_score+gm.away_score>0
ORDER BY gm.game_date, gm.game_sno
"""


def _cov(year: int, kind: str) -> list[dict]:
    with conn() as c:
        rows = c.execute(_COV_SQL, (year, kind)).fetchall()
    return [{"venue": r[0], "game_sno": r[1], "game_date": r[2],
             "pitches": r[3], "tracked": r[4]} for r in rows]


# ── equipped：卡面字面 SQL ────────────────────────────────────────────────────
# 逐字取自 docs/tasks/INGEST-GAME-TM-REFACTOR1-G4.md〈驗收條件〉的驗證查詢。
# 僅在最外層 SELECT 追加兩個計數欄（hit／window），用來呈現「N/10」；
# `equipped` 本身的運算式與 WHERE/PARTITION/ORDER 一字未改。
_EQUIPPED_SQL = """
WITH cov AS (
  SELECT gm.venue, gm.game_sno, gm.game_date,
    (SELECT count(*) FROM cpbl.game_livelog ll WHERE ll.year=gm.year
       AND ll.kind_code=gm.kind_code AND ll.game_sno=gm.game_sno
       AND (ll.is_ball OR ll.is_strike)) AS pitches,
    (SELECT count(*) FROM cpbl.pitch_tracking pt WHERE pt.year=gm.year
       AND pt.kind_code=gm.kind_code AND pt.game_sno=gm.game_sno) AS tracked
  FROM cpbl.games gm
  WHERE gm.year=%s AND gm.kind_code=%s AND gm.home_score+gm.away_score>0),
r AS (SELECT *, row_number() OVER (PARTITION BY venue
        ORDER BY game_date DESC, game_sno DESC) rn FROM cov)
SELECT venue, bool_or(pitches>=50 AND tracked>=pitches*0.80) AS equipped,
       count(*) FILTER (WHERE pitches>=50 AND tracked>=pitches*0.80) AS hit,
       count(*) AS window_games
FROM r WHERE rn<=10 GROUP BY venue ORDER BY venue
"""


def cmd_equipped(year: int, outdir: Path) -> dict:
    out: dict = {"card": "INGEST-GAME-TM-REFACTOR1-G4", "metric": "equipped_recency_aware",
                 "generated_at": _now(),
                 "policy": {"window": EQUIPPED_WINDOW, "ratio": EQUIPPED_RATIO,
                            "min_pitches": MIN_PITCHES,
                            "source": "需求方 2026-08-04 裁定（營運政策，非資料推導）"},
                 "sql": _EQUIPPED_SQL.strip(), "by_kind": {}}
    for kind in ("A", "D"):
        with conn() as c:
            rows = c.execute(_EQUIPPED_SQL, (year, kind)).fetchall()
        venues = [{"venue": r[0], "equipped": r[1], "hit": r[2], "window_games": r[3]}
                  for r in rows]
        got_true = {v["venue"] for v in venues if v["equipped"]}
        got_false = {v["venue"] for v in venues if not v["equipped"]}
        exp = _INVARIANT_EXPECT[kind]
        checks = []
        for v in exp["false"]:
            present = v in got_true or v in got_false
            checks.append({"venue": v, "expect": False, "observed": v in got_true,
                           "present_in_data": present,
                           "ok": (not present) or (v in got_false)})
        for v in exp["true"]:
            present = v in got_true or v in got_false
            checks.append({"venue": v, "expect": True, "observed": v in got_true,
                           "present_in_data": present,
                           "ok": present and v in got_true})
        out["by_kind"][kind] = {
            "venues": venues,
            "equipped_true": sorted(got_true), "equipped_false": sorted(got_false),
            "invariant_checks": checks,
            "invariants_all_ok": all(c["ok"] for c in checks),
        }
        print(f"[equipped {kind}] " + "  ".join(
            f"{v['venue']}={v['hit']}/{v['window_games']}{'✓' if v['equipped'] else '✗'}"
            for v in venues))
        print(f"           equipped=true: {sorted(got_true)}")
        print(f"           不變量全通過：{out['by_kind'][kind]['invariants_all_ok']}")
    _write(outdir, "equipped_invariants.json", out)
    return out


# ── requests：請求量實測 ──────────────────────────────────────────────────────
def _window_games(year: int, kind: str, days: list[_dt.date]) -> list[int]:
    """當日窗完成場（與 `_completed_snos` 同一條件）。"""
    with conn() as c:
        rows = c.execute(
            "SELECT game_sno FROM cpbl.games WHERE year=%s AND kind_code=%s "
            "AND game_date = ANY(%s) AND home_score+away_score>0 ORDER BY game_sno",
            (year, kind, days),
        ).fetchall()
    return [r[0] for r in rows]


def _pitchers_of(year: int, kind: str, snos: list[int]) -> set[str]:
    if not snos:
        return set()
    with conn() as c:
        rows = c.execute(
            "SELECT DISTINCT pitcher_acnt FROM cpbl.pitching_gamelog "
            "WHERE year=%s AND kind_code=%s AND game_sno = ANY(%s)",
            (year, kind, snos),
        ).fetchall()
    return {r[0] for r in rows}


def _live_worker_background() -> dict:
    """live worker 對**同一端點**的請求量（容量模型，非實測流量）。

    卡面要求附此數字當背景。來源為碼內常數（`live_game_worker.poll_interval_seconds`
    與 `settings.live_game_max_games_per_cycle`），**不是**生產實測——本機無法觀測
    生產 worker 流量，故明示為模型並列出全部假設，不冒充量測值。
    """
    from cpbl.config import settings
    live_interval, pre_interval = 12, 60      # poll_interval_seconds：live / 開賽前 90 分
    live_hours, pre_minutes = 3.5, 90          # 單場典型時長與開賽前加密輪詢窗
    concurrent = 5                             # 一軍典型同日場數（上限 max_games_per_cycle）
    cycles_live = live_hours * 3600 / live_interval
    cycles_pre = pre_minutes * 60 / pre_interval
    per_day = (cycles_live + cycles_pre) * concurrent
    return {
        "kind": "capacity_model_not_measured",
        "assumptions": {"live_poll_interval_s": live_interval,
                        "pregame_poll_interval_s": pre_interval,
                        "live_hours_per_game": live_hours,
                        "pregame_window_min": pre_minutes,
                        "concurrent_games": concurrent,
                        "max_games_per_cycle": settings.live_game_max_games_per_cycle,
                        "worker_enabled_default": settings.live_game_worker_enabled},
        "same_endpoint_requests_per_game_day": round(per_day),
        "note": ("live worker 打的是同一支 /api/proxy/v1/games/{id}。此模型顯示該端點的"
                 "既有請求量比本卡增量路徑高出兩個數量級，故切換與週跑的絕對請求量"
                 "在該端點的整體負載中屬雜訊等級。"),
    }


def cmd_requests(year: int, outdir: Path, replay_days: int = 30) -> dict:
    """回放最近 N 個 refresh 日：同一組場次，兩個維度各要幾次請求。

    **兩種窗模型都算，並以 `prev_day` 為主**：
    - `prev_day`（生產實況）：refresh 每日 10:10 跑，當天的比賽是晚上才打、當下未完成，
      故當日窗 `[昨天,今天]` 實際產出的完成場＝**昨天**那批。每場一生只被抓一次。
    - `as_run`（上界）：直接用現在的 DB 狀態數整個 `[昨天,今天]` 窗，因為今天的場**現在**
      已完成，同一場會在相鄰兩個 refresh 日各被數一次 → 兩個維度**同時**約略加倍。
      比值不受影響，但絕對日均會高估約一倍，故不能拿來跟週跑攤提相加。

    **只計當日窗**（可完整由 DB 重建）。落後場補抓的加項在兩個維度同時存在
    （場次維度加 |落後場|、投手維度加 |落後場的出賽投手|），故排除它是保守估計
    而非有利於新路徑的挑選；當日落後場的兩維度大小另列於 `lagging_today` 供對照。
    """
    today = _dt.date.today()
    per_day = []
    tot_games = tot_pitchers = 0
    as_run_games = as_run_pitchers = 0
    for back in range(replay_days):
        d = today - _dt.timedelta(days=back)
        prev = d - _dt.timedelta(days=1)
        g_req = p_req = 0
        ar_g = ar_p = 0
        detail = {}
        for kind in ("A", "D"):
            snos = _window_games(year, kind, [prev])           # prev_day 模型
            pit = _pitchers_of(year, kind, snos)
            g_req += len(snos)
            p_req += len(pit)
            w_snos = _window_games(year, kind, [prev, d])      # as_run 上界
            ar_g += len(w_snos)
            ar_p += len(_pitchers_of(year, kind, w_snos))
            detail[kind] = {"games": len(snos), "pitchers": len(pit)}
        as_run_games += ar_g
        as_run_pitchers += ar_p
        if g_req == 0 and p_req == 0:
            continue  # 無完成場之日：兩維度皆 0 請求，計入只會稀釋比值
        per_day.append({"refresh_date": d.isoformat(),
                        "prev_day": prev.isoformat(),
                        "game_dim_requests": g_req, "pitcher_dim_requests": p_req,
                        "as_run_game_dim": ar_g, "as_run_pitcher_dim": ar_p,
                        "by_kind": detail})
        tot_games += g_req
        tot_pitchers += p_req

    lagging_today = {}
    from cpbl.ingest.run_refresh_recent import _lagging_pitch_games, _pitchers_of_games
    for kind in ("A", "D"):
        lg = sorted(_lagging_pitch_games(year, kind))
        lagging_today[kind] = {"games": len(lg), "game_snos": lg,
                               "pitchers": len(_pitchers_of_games(year, kind, lg))}

    # 每週全季重跑攤提：全季完成場數 ÷ 7
    with conn() as c:
        season = {k: c.execute(
            "SELECT count(*) FROM cpbl.games WHERE year=%s AND kind_code=%s "
            "AND home_score+away_score>0 AND game_date<=CURRENT_DATE", (year, k)
        ).fetchall()[0][0] for k in ("A", "D")}
    weekly_total = season["A"] + season["D"]
    days = len(per_day)
    inc_daily = tot_games / days if days else 0.0
    old_daily = tot_pitchers / days if days else 0.0
    amortised_daily = inc_daily + weekly_total / 7

    pure = (1 - tot_games / tot_pitchers) if tot_pitchers else 0.0
    amort = (1 - amortised_daily / old_daily) if old_daily else 0.0
    as_run_pure = (1 - as_run_games / as_run_pitchers) if as_run_pitchers else 0.0
    out = {
        "card": "INGEST-GAME-TM-REFACTOR1-G4", "metric": "request_volume",
        "generated_at": _now(),
        "method": ("回放最近 %d 個 refresh 日；場次維度=場數、投手維度=那些場的 "
                   "pitching_gamelog 出賽投手數（A+D 合計）。主模型 prev_day＝"
                   "當日窗實際產出的完成場為昨天那批（10:10 跑、今日賽事晚間才打）；"
                   "as_run＝直接數 [昨天,今天] 窗的上界（同一場相鄰兩日各數一次）。"
                   "無完成場之日不計入。" % replay_days),
        "replay_days_with_games": days,
        "totals": {"game_dim_requests": tot_games, "pitcher_dim_requests": tot_pitchers,
                   "as_run_game_dim": as_run_games, "as_run_pitcher_dim": as_run_pitchers},
        "daily_mean": {"game_dim": round(inc_daily, 2), "pitcher_dim": round(old_daily, 2)},
        "weekly_full_season": {"completed_games_A": season["A"], "completed_games_D": season["D"],
                               "requests_per_week": weekly_total,
                               "amortised_per_day": round(weekly_total / 7, 1)},
        "amortised_daily_game_dim": round(amortised_daily, 2),
        "reduction_pct": {"pure_incremental": round(pure * 100, 1),
                          "pure_incremental_as_run_model": round(as_run_pure * 100, 1),
                          "with_weekly_full_season": round(amort * 100, 1)},
        "live_worker_background": _live_worker_background(),
        "lagging_today": lagging_today,
        "per_day": per_day,
    }
    lw = out["live_worker_background"]["same_endpoint_requests_per_game_day"]
    out["weekly_rerun_vs_live_worker_pct"] = round(100 * (weekly_total / 7) / lw, 2) if lw else None
    print(f"[requests] 純增量：場次維度 {tot_games} vs 投手維度 {tot_pitchers} "
          f"→ 降幅 {out['reduction_pct']['pure_incremental']}%"
          f"（as_run 上界模型 {out['reduction_pct']['pure_incremental_as_run_model']}%）")
    print(f"[requests] 含週跑攤提：日均 {amortised_daily:.1f} vs {old_daily:.1f} "
          f"→ 降幅 {out['reduction_pct']['with_weekly_full_season']}%"
          f"（週跑 {weekly_total} 請求 → 日均 {weekly_total / 7:.1f}）")
    print(f"[requests] 背景：live worker 對同一端點容量模型 ~{lw} 請求/賽事日；"
          f"週跑攤提僅佔其 {out['weekly_rerun_vs_live_worker_pct']}%")
    _write(outdir, "request_volume.json", out)
    return out


# ── rollback：降級版預先登錄回測 ──────────────────────────────────────────────
def _percentile(sorted_vals: list[float], q: float) -> float:
    """最近秩 [nearest-rank] 百分位數：第 ceil(q*N) 個（1-indexed）。

    刻意用最近秩而非插值：地板是「要有這麼多場真的低於它」的營運門檻，
    取實際觀測值比取內插的虛擬值更好解釋，也不會落在任何真實場次之外。
    """
    if not sorted_vals:
        return 0.0
    import math
    idx = max(1, math.ceil(q * len(sorted_vals)))
    return sorted_vals[idx - 1]


def _equipped_as_of(cov: list[dict], as_of: _dt.date) -> set[str]:
    """截至 as_of（含當日）的近期感知 equipped 集合——回測必須用當時可得的資料判定，
    否則等於用未來資訊決定當日母體。"""
    by_venue: dict[str, list[dict]] = defaultdict(list)
    for g in cov:
        if g["game_date"] <= as_of:
            by_venue[g["venue"]].append(g)
    out = set()
    for venue, games in by_venue.items():
        games.sort(key=lambda g: (g["game_date"], g["game_sno"]), reverse=True)
        window = games[:EQUIPPED_WINDOW]
        if any(g["pitches"] >= MIN_PITCHES and g["tracked"] >= g["pitches"] * EQUIPPED_RATIO
               for g in window):
            out.add(venue)
    return out


def cmd_rollback(year: int, outdir: Path) -> dict:
    out: dict = {"card": "INGEST-GAME-TM-REFACTOR1-G4", "metric": "rollback_threshold_backtest",
                 "generated_at": _now(),
                 "pre_registration": {
                     "note": ("降級版：不做參數搜尋，只回放現行暫定值的誤觸發次數。"
                              "容忍度於需求方 2026-08-04 裁定時固定，"
                              "**回放結果不得反過來修改門檻或容忍度**。"),
                     "floor_percentile": FLOOR_PERCENTILE,
                     "consecutive_eligible_days": CONSECUTIVE_ELIGIBLE,
                     "false_alarm_tolerance_per_season": FALSE_ALARM_TOLERANCE,
                     "min_floor_population": MIN_FLOOR_POPULATION},
                 "by_kind": {}}
    for kind in ("A", "D"):
        # 保留賽會掛未來日期卻已有比分（見記憶 completed-game-judgment），且其已打完的
        # 局數留有 livelog → pitches>0、tracked=0，會在「當日新完成場」聚合裡假造一個
        # 比率 0.0 的 eligible day。回滾規則的母體是「**當日新完成**且 equipped 的場」，
        # 未來日期的保留賽依定義不屬之，故此處套用 canonical 完成場界線排除。
        # 注意：`equipped` CTE 本身維持卡面字面 SQL（不加此界線），兩者範圍刻意不同。
        today_ = _dt.date.today()
        cov = [g for g in _cov(year, kind) if g["game_date"] <= today_]
        # 地板母體：切換前、同 kind、pitches>=50 AND tracked>0 的全部場次之單場覆蓋率
        pop = sorted((g["tracked"] / g["pitches"]) for g in cov
                     if g["pitches"] >= MIN_PITCHES and g["tracked"] > 0)
        floor = _percentile(pop, FLOOR_PERCENTILE)
        # 日聚合回放：eligible day = 當日有 equipped=true 球場的完成場且 sum(pitches)>0
        by_date: dict[_dt.date, list[dict]] = defaultdict(list)
        for g in cov:
            by_date[g["game_date"]].append(g)
        daily = []
        for d in sorted(by_date):
            eq = _equipped_as_of(cov, d)
            games = [g for g in by_date[d] if g["venue"] in eq]
            sp = sum(g["pitches"] for g in games)
            if not games or sp == 0:
                continue  # 非 eligible day：不算通過也不算失敗
            st = sum(g["tracked"] for g in games)
            ratio = st / sp
            daily.append({"date": d.isoformat(), "games": len(games), "pitches": sp,
                          "tracked": st, "ratio": round(ratio, 4), "below_floor": ratio < floor,
                          "venues": sorted({g["venue"] for g in games})})
        # 連續 CONSECUTIVE_ELIGIBLE 個 eligible day 低於地板 → 觸發（eligible day 相接，非日曆日）
        triggers = []
        run = 0
        for i, day in enumerate(daily):
            run = run + 1 if day["below_floor"] else 0
            if run == CONSECUTIVE_ELIGIBLE:
                triggers.append({"trigger_on": day["date"],
                                 "eligible_days": [daily[j]["date"]
                                                   for j in range(i - CONSECUTIVE_ELIGIBLE + 1, i + 1)],
                                 "ratios": [daily[j]["ratio"]
                                            for j in range(i - CONSECUTIVE_ELIGIBLE + 1, i + 1)],
                                 "venues": sorted({v for j in range(i - CONSECUTIVE_ELIGIBLE + 1, i + 1)
                                                   for v in daily[j]["venues"]})})
        out["by_kind"][kind] = {
            "floor_population_games": len(pop),
            "floor_population_sufficient": len(pop) >= MIN_FLOOR_POPULATION,
            "floor_p05": round(floor, 4),
            "single_game_distribution": {
                "min": round(pop[0], 4) if pop else None,
                "p05": round(floor, 4),
                "median": round(_percentile(pop, 0.5), 4) if pop else None,
                "max": round(pop[-1], 4) if pop else None},
            "eligible_days": len(daily),
            "days_below_floor": sum(1 for d in daily if d["below_floor"]),
            "trigger_count": len(triggers),
            "within_tolerance": len(triggers) <= 1,
            "triggers": triggers,
            "daily": daily,
        }
        k = out["by_kind"][kind]
        print(f"[rollback {kind}] 地板母體={k['floor_population_games']} 場"
              f"（足夠={k['floor_population_sufficient']}）p05={k['floor_p05']:.4f} "
              f"中位={k['single_game_distribution']['median']} 最低={k['single_game_distribution']['min']}")
        print(f"[rollback {kind}] eligible day={k['eligible_days']} "
              f"低於地板={k['days_below_floor']} → 觸發 {k['trigger_count']} 次"
              f"（容忍度 ≤1 採用／≥2 回報需求方）")
        for t in k["triggers"]:
            print(f"              · {t['trigger_on']} ratios={t['ratios']} venues={t['venues']}")
    total = sum(v["trigger_count"] for v in out["by_kind"].values())
    out["verdict"] = {
        "total_trigger_count": total,
        "tolerance": FALSE_ALARM_TOLERANCE,
        "action": ("採用暫定值並留痕（≤1/季）" if all(v["trigger_count"] <= 1
                                                    for v in out["by_kind"].values())
                   else "逾越裁定容忍度 → 回報需求方裁定，執行者不得自行調參"),
        # 需求方 2026-08-05 裁定（第 1 輪跨家族查核後正文化入卡面〈驗證〉）：
        "requester_ruling_2026_08_05": {
            "decision": ("回放 8 次觸發（A7／D1）**重分類為環境告警記錄**，暫定值照案採用；"
                         "成因為已文件化的場館事件（亞太主早季未裝機、大巨蛋衰退），"
                         "非門檻設計缺陷。"),
            "parameter_changes": "無——p05 地板、連續 2 eligible day 語意與任何參數皆不改動",
            "effect": "上線後回滾規則原樣生效；本回測不重跑、不調參",
            "source": "docs/tasks/INGEST-GAME-TM-REFACTOR1-G4.md〈驗證〉回測結果裁定條目",
        },
    }
    print(f"[rollback] 合計觸發 {total} 次 → {out['verdict']['action']}")
    _write(outdir, "rollback_backtest.json", out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["equipped", "requests", "rollback", "all"])
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--replay-days", type=int, default=30)
    ap.add_argument("--outdir", default="docs/research/INGEST-GAME-TM-REFACTOR1-G4")
    args = ap.parse_args()
    outdir = Path(args.outdir)
    if args.cmd in ("equipped", "all"):
        cmd_equipped(args.year, outdir)
    if args.cmd in ("requests", "all"):
        cmd_requests(args.year, outdir, args.replay_days)
    if args.cmd in ("rollback", "all"):
        cmd_rollback(args.year, outdir)


if __name__ == "__main__":
    main()
