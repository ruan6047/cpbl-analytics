"""逐球 TrackMan 追蹤資料爬蟲（stats.cpbl 官方 JSON API）。

**兩條 fetch path、共用同一 pure parser（`_record` / `parse_pitches`）**：

1. 逐投手 logs（`scrape_pitches`）：`/api/proxy/v1/players/logs`，依 kindCode
   server-side 過濾整季逐球。現行 refresh 正式路徑用此路（唯一正式 writer）。
2. 逐比賽單場（`scrape_game_pitches`，INGEST-GAME-TM-REFACTOR1）：
   `/api/proxy/v1/games/{year}-{kind}-{sno}`，解析 `Data.Game.LiveLog[]`。
   實測（2026-A-99）確認 LiveLog[] 每筆與 logs API 逐球**同 schema**（同欄位名
   Year/KindCode/GameSno/PitchCnt/PitcherAcnt/…/Trackman{Play,Pitch,Hit}），故
   `_record` 逐字沿用、不需欄位重映射。一場一請求，避免逐投手全季 logs 的名冊異動漏損。

兩路皆為官方 JSON（httpx 直連、無挑戰），支援 kindCode A/C/D/E（一軍/一軍季後/
二軍/二軍季後）。

逐球 Trackman 結構：{"Trackman":{"Play":{"PitchTag":{…}},
"Pitch":{"Release":{…},"Location":{…},"Flight":{"PolyFit":{"PitchTrajectory":{…}}}},
"Hit":{"Launch":{…},"LandingFlat":{…}}}}。
無 TrackMan 設備球場的球 Trackman=null → 不收（與舊版語意一致；單場 API 的牽制／換投／
暫停等非投球事件同樣 Trackman=null，自動略過）。冪等 UPSERT。

深層物理欄位（INGEST-DEEP-TRACKMAN1）：落地方位角/信心（LandingFlat.Bearing/Confidence）、
擊球自轉率（Launch.HitSpinRate）、投球軌跡九個原始多項式係數（PitchTrajectory.X/Y/Z[0..2]）。
九係數以 float8 原值保存，不 round（衍生 traj_accel_y/z 為 round(4) 不能反推）。
"""

from __future__ import annotations

import datetime as _dt
import logging
import time

import httpx

from cpbl.completion import completed_games_sql
from cpbl.db import conn

log = logging.getLogger("cpbl.pitch")

BASE = "https://stats.cpbl.com.tw"
LOGS_EP = f"{BASE}/api/proxy/v1/players/logs"
GAMES_EP = f"{BASE}/api/proxy/v1/games"  # 單場物件 /api/proxy/v1/games/{year}-{kind}-{sno}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


# ── 凍結例外清單（INGEST-GAME-TM-REFACTOR1-G4 紅線 1；需求方 2026-08-05 裁定）────────
#
# 語意：經逐場歸因**證實兩支官方端點互相矛盾、且單場 API 為較差來源**的場次，由**需求方
# 逐場核入**本清單。凍結場次由增量路徑與每週全季重跑**一律跳過不寫**（fail-closed），
# 使較差來源不會覆蓋既有較完整資料；其 mismatch 亦不計入紅線 1 母體。
#
# ⚠️ **執行者不得自行擴充本清單**——新增一律需求方明示核入並留 event。
#    這不是「發現差異就加進來」的白名單，加入前必須有三方比對證據
#    （logs 端點現值 vs 正式表 vs 單場 API）證明單場 API 較差，而非單純不一致。
#
# 首例 `(2026, "D", 180)`（2026-07-30 澄清湖）核入理由：
#   · logs 端點**現值** vs 正式表 0/109 列不一致 → 排除「正式表過期」。
#   · logs 端點現值 vs 單場 API 100/100 列不一致 → 兩支官方端點當下互相矛盾。
#   · 單場 API 全 105 列缺 `Trackman.Play.PitchTag`（`pitch_call`／`auto_pitch_type` 全 null）、
#     軌跡係數全異、2 球 `rel_speed` 差 > 1 km/h（最大 15.56）、且少 4 列 → 單場 API 較差。
#   證據：Phase A dry-run 三方比對
#   （docs/research/INGEST-GAME-TM-REFACTOR1-G4/redline_attribution.json）＋ 第 1 輪
#   跨家族查核（GPT-5.6@Codex）複驗；需求方 2026-08-05 裁定正文化入卡面紅線 1。
FROZEN_GAMES: frozenset[tuple[int, str, int]] = frozenset({
    (2026, "D", 180),
})


def is_frozen(year: int | None, kind_code: str | None, game_sno: int | None) -> bool:
    """該場是否在凍結例外清單內（任何寫入路徑都必須先問這一句）。"""
    return (year, kind_code, game_sno) in FROZEN_GAMES


def _client() -> httpx.Client:
    return httpx.Client(timeout=60.0, headers={"User-Agent": UA}, follow_redirects=True)


def _f(v) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _i(v) -> int | None:
    try:
        return int(float(v)) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


_ZT_FALLBACK = 0.42  # ZoneTime 缺值時的飛行秒數估計（見 docs/PITCH_TYPE_PLAN.md §2）


def _traj(pit: dict) -> tuple[float | None, float | None, float | None, float | None, float | None]:
    """由 Flight.PolyFit.PitchTrajectory（二次多項式係數）+ ZoneTime 導出
    (accel_y, accel_z, zone_time, ivb_cm, hb_cm)。TM 球 100% 有；缺任一則回 None 群。

    座標軸（已實證）：Y=垂直（含重力），Z=水平（Z[0]≈−RelSide）。
    IVB=0.5·(2Y₂+9.81)·t²·100 cm（正=四縫線上飄）；HB=0.5·(2Z₂)·t²·100 cm（未翻左右手）。
    """
    traj = ((pit.get("Flight") or {}).get("PolyFit") or {}).get("PitchTrajectory") or {}
    y2 = _f((traj.get("Y") or [None, None, None])[2] if traj.get("Y") else None)
    z2 = _f((traj.get("Z") or [None, None, None])[2] if traj.get("Z") else None)
    if y2 is None or z2 is None:
        return (None, None, None, None, None)
    ay, az = 2.0 * y2, 2.0 * z2
    zt = _f((pit.get("Location") or {}).get("ZoneTime"))
    t = zt if zt else _ZT_FALLBACK
    ivb = 0.5 * (ay + 9.81) * t * t * 100.0
    hb = 0.5 * az * t * t * 100.0
    return (round(ay, 4), round(az, 4), zt, round(ivb, 2), round(hb, 2))


def _polyfit(pit: dict) -> tuple[float | None, ...]:
    """官方 PitchTrajectory 九個原始多項式係數 (X0,X1,X2,Y0,Y1,Y2,Z0,Z1,Z2)。

    紅線：原值保存不 round（衍生 traj_accel_y/z 為 round(4) 不能反推）。缺軸／缺項回 None。
    與 _traj 的衍生 IVB/HB 各自獨立：這裡只搬原始係數，不受 ZoneTime 或 y2/z2 缺值影響。
    """
    traj = ((pit.get("Flight") or {}).get("PolyFit") or {}).get("PitchTrajectory") or {}
    out: list[float | None] = []
    for axis in ("X", "Y", "Z"):
        arr = traj.get(axis)
        for i in range(3):
            out.append(_f(arr[i]) if isinstance(arr, list) and len(arr) > i else None)
    return tuple(out)


def _fetch_logs(client: httpx.Client, acnt: str, year: int, kind_code: str) -> list[dict]:
    r = client.get(LOGS_EP, params={
        "playerType": "pitcher", "acnt": acnt, "year": str(year), "kindCode": kind_code})
    r.raise_for_status()
    return (r.json().get("Data") or {}).get("Logs") or []


def _fetch_game_livelog(client: httpx.Client, year: int, kind_code: str, game_sno: int) -> list[dict]:
    """單場 API 的 `Data.Game.LiveLog[]`（逐事件；含逐球 Trackman、換投/牽制等非投球事件）。

    LiveLog 每筆與 logs API 逐球同 schema，故可直接餵給共用 parser。無 LiveLog（未開打／
    端點結構變）回空列，由呼叫端當 0 球處理（不視為錯誤）。
    """
    r = client.get(f"{GAMES_EP}/{year}-{kind_code}-{game_sno}")
    r.raise_for_status()
    game = ((r.json().get("Data") or {}).get("Game") or {})
    return game.get("LiveLog") or []


def _record(p: dict, kind_default: str) -> tuple | None:
    tm = p.get("Trackman")
    if not tm:  # 無 TrackMan 設備球場 → 不收（同舊版）
        return None
    tag = (tm.get("Play") or {}).get("PitchTag") or {}
    pit = tm.get("Pitch") or {}
    rel = pit.get("Release") or {}
    loc = pit.get("Location") or {}
    hit = tm.get("Hit") or {}
    launch = hit.get("Launch") or {}
    land = hit.get("LandingFlat") or {}
    sno, pcnt, pacnt = _i(p.get("GameSno")), _i(p.get("PitchCnt")), p.get("PitcherAcnt")
    if sno is None or pcnt is None or not pacnt:
        return None
    accel_y, accel_z, zone_time, ivb, hb = _traj(pit)
    x0, x1, x2, y0, y1, y2, z0, z1, z2 = _polyfit(pit)
    return (
        _i(p.get("Year")), p.get("KindCode") or kind_default, sno, pacnt, pcnt,
        p.get("PitcherName"), p.get("HitterAcnt"), p.get("HitterName"),
        _i(p.get("InningSeq")), _i(p.get("BallCnt")), _i(p.get("StrikeCnt")), _i(p.get("OutCnt")),
        _i(p.get("BattingOrder")), p.get("Content"),
        tag.get("PitchCall"), tag.get("AutoPitchType"), tag.get("TaggedPitchType"),
        _f(rel.get("RelSpeed")), _f(rel.get("SpinRate")), _f(rel.get("RelSide")),
        _f(rel.get("RelHeight")), _f(rel.get("Extension")),
        _f(loc.get("ZoneSpeed")), _f(loc.get("PlateLocSide")), _f(loc.get("PlateLocHeight")),
        _f(launch.get("ExitSpeed")), _f(launch.get("Angle")), _f(launch.get("Direction")),
        _f(land.get("Distance")), _f(land.get("HangTime")),
        accel_y, accel_z, zone_time, ivb, hb,
        _f(land.get("Bearing")), land.get("Confidence"), _f(launch.get("HitSpinRate")),
        x0, x1, x2, y0, y1, y2, z0, z1, z2,
    )


_COLS = ("year,kind_code,game_sno,pitcher_acnt,pitch_cnt,pitcher_name,hitter_acnt,hitter_name,"
         "inning_seq,ball_cnt,strike_cnt,out_cnt,batting_order,content,pitch_call,auto_pitch_type,"
         "tagged_pitch_type,rel_speed,spin_rate,rel_side,rel_height,extension,zone_speed,"
         "plate_loc_side,plate_loc_height,hit_exit_speed,hit_launch_angle,hit_direction,"
         "hit_distance,hit_hang_time,traj_accel_y,traj_accel_z,zone_time,ivb_cm,hb_cm,"
         "hit_landing_bearing,hit_landing_confidence,hit_spin_rate,"
         "traj_x0,traj_x1,traj_x2,traj_y0,traj_y1,traj_y2,traj_z0,traj_z1,traj_z2")


def _upsert(records: list[tuple]) -> int:
    # 凍結例外（紅線 1，fail-closed）：在**唯一寫入口**過濾，故 logs 路徑、單場路徑、
    # 每週全季重跑、手動 CLI ——**任何**路徑都不可能寫進凍結場，不必逐個呼叫點記得擋。
    # 放在去重之前：凍結列連去重都不參與，避免任何後續步驟看見它們。
    records = [r for r in records if not is_frozen(r[0], r[1], r[2])]
    # 去重：同一 PK (year,kind,game,pitcher,pitch_cnt) 只留一筆
    seen, uniq = set(), []
    for r in records:
        key = (r[0], r[1], r[2], r[3], r[4])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    if not uniq:
        return 0
    cols = [c.strip() for c in _COLS.split(",")]
    ph = "(" + ",".join(["%s"] * len(cols)) + ")"
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols[5:])
    with conn() as c:
        c.cursor().executemany(
            f"INSERT INTO cpbl.pitch_tracking ({_COLS}) VALUES {ph} "
            f"ON CONFLICT (year, kind_code, game_sno, pitcher_acnt, pitch_cnt) DO UPDATE SET {updates}",
            uniq,
        )
    return len(uniq)


def parse_pitches(entries: list[dict], kind_default: str) -> list[tuple]:
    """共用 pure parser：把逐球事件（logs API `Data.Logs[]` 或單場 API `Data.Game.LiveLog[]`，
    兩者同 schema）經 `_record` 轉為入庫 tuple。Trackman=null 事件（無設備／牽制／換投／暫停）
    自動略過。無副作用、不碰 DB／網路——供兩條 fetch path 與對帳工具共用。"""
    return [t for t in (_record(p, kind_default) for p in entries) if t]


def scrape_pitches(pitcher_acnts: list[str], year: int | None = None,
                   kind_code: str = "A", delay: float = 1.0) -> dict:
    """逐投手抓其該季/該 kind 每球 TrackMan（logs API）。回傳 {pitchers, pitches}。

    year 預設本季；kind_code=A 一軍例行 / C 一軍季後 / D 二軍 / E 二軍季後。
    """
    year = year or _dt.date.today().year
    client = _client()
    out = {"pitchers": 0, "pitches": 0}
    try:
        for idx, acnt in enumerate(pitcher_acnts, 1):
            time.sleep(delay)
            try:
                logs = _fetch_logs(client, acnt, year, kind_code)
            except (httpx.HTTPError, ValueError) as e:
                log.warning("[%d/%d] acnt=%s API 失敗：%s", idx, len(pitcher_acnts), acnt, e)
                continue
            n = _upsert(parse_pitches(logs, kind_code))
            out["pitchers"] += 1
            out["pitches"] += n
            log.info("[%d/%d] acnt=%s %d/%s → %d 球（累計 %d）",
                     idx, len(pitcher_acnts), acnt, year, kind_code, n, out["pitches"])
    finally:
        client.close()
    return out


def scrape_game_pitches(games: list[tuple[int, str, int]], delay: float = 1.0) -> dict:
    """以比賽為單位抓單場 API 的逐球 TrackMan（INGEST-GAME-TM-REFACTOR1）。回傳 {games, pitches}。

    games：`[(year, kind_code, game_sno), ...]`。一場一請求，與 `scrape_pitches` 共用同一
    pure parser（`parse_pitches`）與冪等 UPSERT；故入庫欄位／PK 與逐投手 logs 路徑完全一致，
    不產生 schema 衝突。單場失敗略過不中斷（比照 logs 路徑逐投手容錯）。

    相對逐投手全季 logs 的優勢：請求量 = 場數（而非兩隊上場投手數），且不受球員賽後下放／
    改名／註銷造成的 acnt 對帳漏損。無 Trackman 設備球場之球 Trackman=null → 不收（既有語意）。
    """
    client = _client()
    out = {"games": 0, "pitches": 0, "skipped_frozen": 0}
    try:
        for idx, (year, kind_code, sno) in enumerate(games, 1):
            if is_frozen(year, kind_code, sno):
                # 凍結場連請求都不發（_upsert 仍會再擋一次；這裡只是省掉無用請求）
                out["skipped_frozen"] += 1
                log.info("[%d/%d] %d-%s-%s 在凍結例外清單內 → 跳過不抓不寫",
                         idx, len(games), year, kind_code, sno)
                continue
            time.sleep(delay)
            try:
                livelog = _fetch_game_livelog(client, year, kind_code, sno)
            except (httpx.HTTPError, ValueError) as e:
                log.warning("[%d/%d] %d-%s-%s API 失敗：%s", idx, len(games), year, kind_code, sno, e)
                continue
            n = _upsert(parse_pitches(livelog, kind_code))
            out["games"] += 1
            out["pitches"] += n
            log.info("[%d/%d] %d-%s-%s → %d 球（累計 %d）",
                     idx, len(games), year, kind_code, sno, n, out["pitches"])
    finally:
        client.close()
    return out


def pitchers_by_kind(year: int, kind_code: str) -> list[str]:
    """有在該 year/kind 出賽的投手（自 pitching_gamelog）。供二軍/季後回填用。"""
    with conn() as c:
        return [r[0] for r in c.execute(
            "SELECT DISTINCT pitcher_acnt FROM cpbl.pitching_gamelog "
            "WHERE year=%s AND kind_code=%s ORDER BY 1", (year, kind_code)).fetchall()]


def completed_game_snos(year: int, kind_code: str, since_days: int | None = None) -> list[int]:
    """該 year/kind 已完成場的 game_sno（比分>0 且日期不晚於今日）。供單場路徑回填/對帳。

    since_days 給定時只取近 N 天（refresh 窗口式增量用）；否則整季。
    completed 判定走 canonical helper `cpbl.completion.completed_games_sql()`（**舊判準**：
    比分自證＋日期界線），取代先前手寫的同一串條件——語意一字不改，產生的 SQL 逐字相同
    （DATA-COMPLETION-MIGRATE-CHAIN1）。日期界線的用途不變：避免保留賽掛未來日卻有比分被誤判。
    日界用 helper 的預設（`completion.UTC_TODAY_SQL` ＝ `CURRENT_DATE`），本檔不再自留複本；
    ⚠️ 該預設刻意凍結、切換授權在 `#53` G4 Phase B，見 `cpbl.completion` 模組說明。
    """
    sql = ("SELECT game_sno FROM cpbl.games WHERE year=%s AND kind_code=%s "
           f"AND {completed_games_sql()}")
    params: list = [year, kind_code]
    if since_days is not None:
        sql += " AND game_date >= (CURRENT_DATE - %s::int)"
        params.append(since_days)
    sql += " ORDER BY game_sno"
    with conn() as c:
        return [r[0] for r in c.execute(sql, tuple(params)).fetchall()]
