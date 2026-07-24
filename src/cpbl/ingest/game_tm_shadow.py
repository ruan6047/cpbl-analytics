"""INGEST-GAME-TM-REFACTOR1 Gate 3：單場 API shadow harness（14 天觀測，唯讀對正式表）。

**不重寫 Gate 1-2 產物**：本模組只 import `cpbl_pitch_tracking` 既有的 pure parser
（`parse_pitches`）、單場 fetch（`_fetch_game_livelog`）與完成場判定（`completed_game_snos`），
自己不重新實作抓取/解析邏輯，避免兩套 parser 分岔。

**寫入邊界（紅線）**：本模組唯一寫入的是四張隔離 shadow 表（`cpbl.game_tm_shadow_*`），
**絕不 INSERT/UPDATE `cpbl.pitch_tracking`**；讀取正式表僅用於對帳比較，唯讀。

**流程**（`run_shadow_cycle`，供 CLI 每日呼叫）：
1. 抓賽程 shadow（`/api/proxy/v1/games/schedule`），依 `GameStatus` 分桶：
   FINISHED / SCHEDULED／POSTPONED／RESERVED／未知狀態（原樣保存、記異常、不當完成場）。
   `SkipTrackman=false` 不映射成 tracking available（見 OFFICIAL_DATA_GAP1_RESULTS §3.4）。
2. 與本機 `cpbl.games` 的完成場判定（`completed_game_snos`）交叉核對：本機已判完成但官方
   狀態非 FINISHED（保留賽/延期誤判完成的紅線案例）記為 `schedule_status_mismatch`。
3. 只對官方 FINISHED 場打單場 API，寫入隔離 `game_tm_shadow_pitch_tracking`（不影響正式表）。
4. 讀正式 `cpbl.pitch_tracking`（唯讀）做同一組場次的 PK 集合與逐格欄位對帳（沿用
   `scripts/reconcile_game_tm.py` 相同的比對邏輯：PK only_shadow/only_prod + cell mismatch）。
5. 差異寫入 `game_tm_shadow_diffs`（該 run 的列＝目前未解差異），run 摘要寫入
   `game_tm_shadow_runs`。

觀測窗期間（14 天）本模組本身也在凍結範圍內：一旦啟動觀測，不得改動這裡的比較邏輯，
否則等於重置觀測窗（見 docs/tasks/INGEST-GAME-TM-REFACTOR1.md 紅線）。
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import struct
import time
from dataclasses import dataclass, field

import httpx

from cpbl.db import conn
from cpbl.ingest.cpbl_pitch_tracking import (
    _COLS,
    _client,
    _fetch_game_livelog,
    completed_game_snos,
    parse_pitches,
)

log = logging.getLogger("cpbl.shadow")

BASE = "https://stats.cpbl.com.tw"
SCHEDULE_EP = f"{BASE}/api/proxy/v1/games/schedule"

_COL_NAMES = [c.strip() for c in _COLS.split(",")]
_PK_COLS = ("year", "kind_code", "game_sno", "pitcher_acnt", "pitch_cnt")

# 官網賽程狀態已實測值（2026-07-24，httpx 直連 `games/schedule` 12 個月份抽樣）：
# FINISHED / SCHEDULED / POSTPONED / RESERVED（保留賽，Score 恆 0-0、WinningPitcher=None，
# 與 SCHEDULED 同形但語意不同——延期／保留／未開打三態官方本就分開標示，不需自行用比分猜）。
_KNOWN_STATUSES = frozenset({"FINISHED", "SCHEDULED", "POSTPONED", "RESERVED"})

# migration 018 這些欄位是 `real`（float4）存入 cpbl.pitch_tracking；shadow 的 jsonb 保存
# parse_pitches 算出的原生 Python float（float64）。同一數值兩邊比對若用 `==` 必然逐格不等
# （float4 只有 ~7 位有效數字），並非真差異。比對前把 shadow 值也做一次 float4 round-trip，
# 模擬正式表實際存入後的精度，才是蘋果比蘋果。migration 064 新增的 double precision 欄位
# （traj_x0..z2、hit_landing_bearing、hit_spin_rate）不在此列，全精度直接比對。
_REAL_F4_COLS = frozenset({
    "rel_speed", "spin_rate", "rel_side", "rel_height", "extension",
    "zone_speed", "plate_loc_side", "plate_loc_height",
    "hit_exit_speed", "hit_launch_angle", "hit_direction", "hit_distance", "hit_hang_time",
    "traj_accel_y", "traj_accel_z", "zone_time", "ivb_cm", "hb_cm",
})


def _as_f4(x: float) -> float:
    return struct.unpack("<f", struct.pack("<f", x))[0]


def _cell_equal(col: str, shadow_v: object, prod_v: object) -> bool:
    if col in _REAL_F4_COLS and isinstance(shadow_v, int | float) and isinstance(prod_v, int | float):
        return _as_f4(shadow_v) == _as_f4(prod_v)
    return shadow_v == prod_v


@dataclass
class ScheduleRow:
    year: int
    kind_code: str
    game_sno: int
    game_status: str
    skip_trackman: bool | None
    pre_exe_date: str | None
    visiting_score: int | None
    home_score: int | None
    venue_abbe: str | None
    raw: dict = field(repr=False)


def parse_schedule_row(g: dict, fallback_year: int) -> ScheduleRow | None:
    """把官方賽程單場物件轉為扁平 `ScheduleRow`（pure，不做 IO）。

    `GameId`（如 `"2026-A-167"`）是年份的權威來源，優先於呼叫端傳入的查詢年；
    解析失敗時退回 `fallback_year` 並記警告，不整批中止。
    """
    game_id = g.get("GameId") or ""
    year = fallback_year
    parts = game_id.split("-")
    if len(parts) == 3 and parts[0].isdigit():
        year = int(parts[0])
    kind_code = g.get("KindCode")
    sno = g.get("GameSno")
    status = g.get("GameStatus")
    if kind_code is None or sno is None or not status:
        return None
    visiting = g.get("Visiting") or {}
    home = g.get("Home") or {}
    field_ = g.get("Field") or {}
    return ScheduleRow(
        year=year, kind_code=kind_code, game_sno=int(sno), game_status=status,
        skip_trackman=g.get("SkipTrackman"), pre_exe_date=g.get("PreExeDate"),
        visiting_score=visiting.get("Score"), home_score=home.get("Score"),
        venue_abbe=field_.get("Abbe"), raw=g,
    )


def classify_schedule(rows: list[ScheduleRow]) -> dict[str, list[ScheduleRow]]:
    """依 `game_status` 分桶。未知狀態（官方新增值）進 `UNKNOWN`，不當完成場處理、不崩潰。"""
    buckets: dict[str, list[ScheduleRow]] = {s: [] for s in _KNOWN_STATUSES}
    buckets["UNKNOWN"] = []
    for r in rows:
        buckets.setdefault(r.game_status if r.game_status in _KNOWN_STATUSES else "UNKNOWN", []).append(r)
    return buckets


def _months_in_window(today: _dt.date, window_days: int) -> list[tuple[int, int]]:
    """窗口 `[today-window_days, today]` 涵蓋的 (year, month) 去重清單（跨月/跨年防呆）。"""
    start = today - _dt.timedelta(days=window_days)
    seen: list[tuple[int, int]] = []
    d = start
    while d <= today:
        ym = (d.year, d.month)
        if ym not in seen:
            seen.append(ym)
        d += _dt.timedelta(days=1)
    return seen


def dedupe_latest_per_game(rows: list[ScheduleRow]) -> list[ScheduleRow]:
    """同一 `game_sno` 在賽程 feed 可能有多筆歷史記錄——延期/保留賽改期都會各留一筆，
    `PreExeDate` 不同（2026-07-24 實測 2026-A-151：POSTPONED@06-09 → RESERVED@06-25 →
    FINISHED@06-28 三筆同時存在同月回應）。若直接 `{r.game_sno: r for r in rows}` 覆寫，
    保留哪一筆取決於 API 回傳順序，可能讓已解決的 FINISHED 被較舊的 POSTPONED/RESERVED
    蓋掉。以 `PreExeDate` 最新者為現況判定依據——ISO 8601 字串可直接字典序排序，不必先
    parse。schedule_obs 仍保存全部原始列（不去重），只有分類/交叉核對用去重後結果。"""
    canonical: dict[tuple[int, str, int], ScheduleRow] = {}
    for r in sorted(rows, key=lambda r: r.pre_exe_date or ""):
        canonical[(r.year, r.kind_code, r.game_sno)] = r
    return list(canonical.values())


def fetch_schedule_month(client: httpx.Client, year: int, kind_code: str, month: int) -> list[dict]:
    r = client.get(SCHEDULE_EP, params={"kindCode": kind_code, "year": str(year), "month": str(month)})
    r.raise_for_status()
    return (r.json().get("Data") or {}).get("Games") or []


def diff_schedule_status(
    local_completed: set[int],
    schedule_by_sno: dict[int, ScheduleRow],
) -> list[dict]:
    """本機完成場判定 vs 官方賽程狀態的交叉核對。回傳 diff dict 清單（pure）。

    危險方向：本機已判完成（`completed_game_snos`，score>0 且 date<=今日）但官方狀態
    非 FINISHED——對應記憶 `completed-game-judgment` 點名的保留賽/延期誤判風險。
    官方 FINISHED 但本機尚未同步（正常時間差，非資料錯誤）另記 `local_lag`，僅供觀察。
    """
    out: list[dict] = []
    for sno in sorted(local_completed):
        sched = schedule_by_sno.get(sno)
        if sched is None:
            continue  # 賽程 shadow 窗口未涵蓋此場（例如窗口邊界差一天），非本卡對帳範圍
        if sched.game_status != "FINISHED":
            out.append({
                "diff_type": "schedule_status_mismatch",
                "game_sno": sno,
                "detail": {"local_judged": "completed", "official_status": sched.game_status,
                           "visiting_score": sched.visiting_score, "home_score": sched.home_score},
            })
    finished_snos = {sno for sno, s in schedule_by_sno.items() if s.game_status == "FINISHED"}
    for sno in sorted(finished_snos - local_completed):
        out.append({
            "diff_type": "local_lag", "game_sno": sno,
            "detail": {"official_status": "FINISHED", "local_judged": "not_yet_completed"},
        })
    return out


def _row_to_dict(rec: tuple) -> dict:
    return dict(zip(_COL_NAMES, rec, strict=True))


def _pk(d: dict) -> tuple:
    return tuple(d[c] for c in _PK_COLS)


def diff_rows(shadow_rows: list[dict], prod_rows: list[dict]) -> list[dict]:
    """單場的 shadow vs 正式表逐格對帳（pure；沿用 `reconcile_game_tm.py` 同一套比較邏輯：
    PK 集合差異 + 共同 PK 逐欄位值比對）。"""
    shadow_by_pk = {_pk(d): d for d in shadow_rows}
    prod_by_pk = {_pk(d): d for d in prod_rows}
    out: list[dict] = []
    only_shadow = set(shadow_by_pk) - set(prod_by_pk)
    only_prod = set(prod_by_pk) - set(shadow_by_pk)
    for pk in sorted(only_shadow):
        out.append({"diff_type": "only_shadow_pk", "game_sno": pk[2], "detail": {"pk": list(pk)}})
    for pk in sorted(only_prod):
        out.append({"diff_type": "only_prod_pk", "game_sno": pk[2], "detail": {"pk": list(pk)}})
    for pk in sorted(set(shadow_by_pk) & set(prod_by_pk)):
        s, p = shadow_by_pk[pk], prod_by_pk[pk]
        mismatched = {c: {"shadow": s.get(c), "prod": p.get(c)} for c in _COL_NAMES
                     if not _cell_equal(c, s.get(c), p.get(c))}
        if mismatched:
            out.append({"diff_type": "cell_mismatch", "game_sno": pk[2],
                        "detail": {"pk": list(pk), "fields": mismatched}})
    return out


def skip_trackman_anomaly(sched: ScheduleRow, shadow_rows: list[dict], prod_rows: list[dict]) -> dict | None:
    """`SkipTrackman=true` 卻仍觀測到逐球資料——只記錄供人工檢視，不視為錯誤（官方旗標
    語意本就單向：true=明確 skip，不代表 false 就保證有資料，反之出現資料也未必矛盾，
    但值得留痕觀察）。"""
    if sched.skip_trackman and (shadow_rows or prod_rows):
        return {"diff_type": "skip_trackman_anomaly", "game_sno": sched.game_sno,
                "detail": {"shadow_rows": len(shadow_rows), "prod_rows": len(prod_rows)}}
    return None


def _production_rows(year: int, kind_code: str, snos: list[int]) -> dict[int, list[dict]]:
    if not snos:
        return {}
    with conn() as c:
        rows = c.execute(
            f"SELECT {_COLS} FROM cpbl.pitch_tracking "
            "WHERE year=%s AND kind_code=%s AND game_sno = ANY(%s)",
            (year, kind_code, snos),
        ).fetchall()
    out: dict[int, list[dict]] = {sno: [] for sno in snos}
    for r in rows:
        d = _row_to_dict(tuple(r))
        out[d["game_sno"]].append(d)
    return out


def _stage_shadow_rows(run_id: int, year: int, kind_code: str, sno: int, rows: list[dict]) -> None:
    if not rows:
        return
    with conn() as c:
        c.cursor().executemany(
            "INSERT INTO cpbl.game_tm_shadow_pitch_tracking "
            "(year, kind_code, game_sno, pitcher_acnt, pitch_cnt, row, run_id) "
            "VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s) "
            "ON CONFLICT (year, kind_code, game_sno, pitcher_acnt, pitch_cnt) "
            "DO UPDATE SET row=EXCLUDED.row, run_id=EXCLUDED.run_id, written_at=now()",
            [(year, kind_code, sno, d["pitcher_acnt"], d["pitch_cnt"],
              _json_dumps(d), run_id) for d in rows],
        )


def _json_dumps(d: dict) -> str:
    return json.dumps(d, ensure_ascii=False)


def _record_schedule_obs(run_id: int, rows: list[ScheduleRow]) -> None:
    if not rows:
        return
    with conn() as c:
        c.cursor().executemany(
            "INSERT INTO cpbl.game_tm_shadow_schedule_obs "
            "(run_id, year, kind_code, game_sno, game_status, skip_trackman, pre_exe_date, "
            " visiting_score, home_score, venue_abbe, raw) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)",
            [(run_id, r.year, r.kind_code, r.game_sno, r.game_status, r.skip_trackman,
              r.pre_exe_date, r.visiting_score, r.home_score, r.venue_abbe, _json_dumps(r.raw))
             for r in rows],
        )


def _record_diffs(run_id: int, year: int, kind_code: str, diffs: list[dict]) -> None:
    if not diffs:
        return
    with conn() as c:
        c.cursor().executemany(
            "INSERT INTO cpbl.game_tm_shadow_diffs (run_id, year, kind_code, game_sno, diff_type, detail) "
            "VALUES (%s,%s,%s,%s,%s,%s::jsonb)",
            [(run_id, year, kind_code, d["game_sno"], d["diff_type"], _json_dumps(d["detail"]))
             for d in diffs],
        )


def _insert_run(year: int, kind_code: str, window_days: int) -> int:
    with conn() as c:
        row = c.execute(
            "INSERT INTO cpbl.game_tm_shadow_runs (year, kind_code, window_days) "
            "VALUES (%s,%s,%s) RETURNING id",
            (year, kind_code, window_days),
        ).fetchone()
    return row[0]


def _finish_run(run_id: int, summary: dict, ok: bool, note: str | None) -> None:
    with conn() as c:
        c.execute(
            """
            UPDATE cpbl.game_tm_shadow_runs SET
                finished_at = now(),
                games_schedule_seen = %(games_schedule_seen)s,
                games_finished = %(games_finished)s,
                games_fetched = %(games_fetched)s,
                games_skipped_postponed = %(games_skipped_postponed)s,
                games_skipped_reserved = %(games_skipped_reserved)s,
                games_skipped_scheduled = %(games_skipped_scheduled)s,
                games_skipped_unknown_status = %(games_skipped_unknown_status)s,
                requests_schedule = %(requests_schedule)s,
                requests_game_api = %(requests_game_api)s,
                diffs_found = %(diffs_found)s,
                ok = %(ok)s,
                note = %(note)s,
                summary = %(summary)s::jsonb
            WHERE id = %(run_id)s
            """,
            {**summary, "run_id": run_id, "ok": ok, "note": note, "summary": _json_dumps(summary)},
        )


def run_shadow_cycle(
    year: int | None = None,
    kind_code: str = "A",
    window_days: int = 3,
    delay: float = 0.4,
) -> dict:
    """執行一次 shadow 觀測週期（供 CLI 每日呼叫；冪等重跑安全，可續跑）。"""
    today = _dt.date.today()
    year = year or today.year
    run_id = _insert_run(year, kind_code, window_days)
    log.info("shadow run 開始 id=%s year=%s kind=%s window_days=%s", run_id, year, kind_code, window_days)

    client = _client()
    req_schedule = req_game = 0
    try:
        window_start = today - _dt.timedelta(days=window_days)
        all_rows: list[ScheduleRow] = []
        for y, m in _months_in_window(today, window_days):
            raw = fetch_schedule_month(client, y, kind_code, m)
            req_schedule += 1
            all_rows += [r for r in (parse_schedule_row(g, y) for g in raw) if r is not None]

        def _in_window(r: ScheduleRow) -> bool:
            if not r.pre_exe_date:
                return False
            d = _dt.date.fromisoformat(r.pre_exe_date[:10])
            return window_start <= d <= today and r.kind_code == kind_code

        rows = [r for r in all_rows if _in_window(r)]
        _record_schedule_obs(run_id, rows)  # 完整歷史列，不去重（延期/保留賽狀態演變留痕）

        canonical = dedupe_latest_per_game(rows)  # 分類/抓取一律用「最新一筆」判定現況
        buckets = classify_schedule(canonical)
        finished = buckets["FINISHED"]
        schedule_by_sno = {r.game_sno: r for r in canonical}

        local_completed = set(completed_game_snos(year, kind_code, since_days=window_days))
        diffs: list[dict] = diff_schedule_status(local_completed, schedule_by_sno)
        for r in buckets["UNKNOWN"]:
            diffs.append({"diff_type": "unknown_schedule_status", "game_sno": r.game_sno,
                          "detail": {"game_status": r.game_status}})

        games_fetched = 0
        for r in finished:
            time.sleep(delay)
            try:
                livelog = _fetch_game_livelog(client, r.year, r.kind_code, r.game_sno)
                req_game += 1
            except (httpx.HTTPError, ValueError) as e:
                log.warning("shadow fetch 失敗 %s-%s-%s：%s", r.year, r.kind_code, r.game_sno, e)
                continue
            recs = parse_pitches(livelog, r.kind_code)
            shadow_rows = [_row_to_dict(rec) for rec in recs]
            _stage_shadow_rows(run_id, r.year, r.kind_code, r.game_sno, shadow_rows)
            games_fetched += 1

            prod_by_sno = _production_rows(r.year, r.kind_code, [r.game_sno])
            prod_rows = prod_by_sno.get(r.game_sno, [])
            diffs += diff_rows(shadow_rows, prod_rows)
            anomaly = skip_trackman_anomaly(r, shadow_rows, prod_rows)
            if anomaly:
                diffs.append(anomaly)

        _record_diffs(run_id, year, kind_code, diffs)

        summary = {
            "games_schedule_seen": len(rows),
            "games_finished": len(finished),
            "games_fetched": games_fetched,
            "games_skipped_postponed": len(buckets["POSTPONED"]),
            "games_skipped_reserved": len(buckets["RESERVED"]),
            "games_skipped_scheduled": len(buckets["SCHEDULED"]),
            "games_skipped_unknown_status": len(buckets["UNKNOWN"]),
            "requests_schedule": req_schedule,
            "requests_game_api": req_game,
            "diffs_found": len(diffs),
        }
        _finish_run(run_id, summary, ok=True, note=None)
        log.info("shadow run 完成 id=%s %s", run_id, summary)
        return {"run_id": run_id, **summary, "diffs": diffs}
    except Exception as e:  # noqa: BLE001 — 失敗也要留痕，避免無聲缺漏（比照 run_refresh_recent）
        note = f"shadow run 失敗：{e}"
        log.error(note)
        _finish_run(run_id, {
            "games_schedule_seen": 0, "games_finished": 0, "games_fetched": 0,
            "games_skipped_postponed": 0, "games_skipped_reserved": 0,
            "games_skipped_scheduled": 0, "games_skipped_unknown_status": 0,
            "requests_schedule": req_schedule, "requests_game_api": req_game, "diffs_found": 0,
        }, ok=False, note=note)
        raise
    finally:
        client.close()


def latest_run_report(kind_code: str = "A") -> dict | None:
    """最近一次 run 的摘要 + 該 run 的未解差異清單（不重跑，純查詢）。"""
    with conn() as c:
        run = c.execute(
            "SELECT id, started_at, finished_at, year, kind_code, window_days, ok, note, summary "
            "FROM cpbl.game_tm_shadow_runs WHERE kind_code=%s ORDER BY started_at DESC LIMIT 1",
            (kind_code,),
        ).fetchone()
        if not run:
            return None
        run_id = run[0]
        diffs = c.execute(
            "SELECT diff_type, game_sno, detail FROM cpbl.game_tm_shadow_diffs "
            "WHERE run_id=%s ORDER BY diff_type, game_sno",
            (run_id,),
        ).fetchall()
    return {
        "run_id": run_id, "started_at": run[1], "finished_at": run[2],
        "year": run[3], "kind_code": run[4], "window_days": run[5],
        "ok": run[6], "note": run[7], "summary": run[8],
        "diffs": [{"diff_type": d[0], "game_sno": d[1], "detail": d[2]} for d in diffs],
    }


def observation_window_days(kind_code: str = "A") -> int:
    """自第一筆 run 至今的天數（供判斷 14 天觀測窗是否滿足）。無 run 回 0。"""
    with conn() as c:
        row = c.execute(
            "SELECT min(started_at) FROM cpbl.game_tm_shadow_runs WHERE kind_code=%s", (kind_code,),
        ).fetchone()
    if not row or not row[0]:
        return 0
    first = row[0]
    if first.tzinfo is not None:
        now = _dt.datetime.now(first.tzinfo)
    else:
        now = _dt.datetime.now()
    return (now - first).days
