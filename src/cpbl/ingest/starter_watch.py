"""#342：官網公布一軍先發後 1 小時內送到正式站——晚間鏈的「先發觀察窗」（規劃 1 路徑 ②，最小改動）。

需求方裁定（#342 6405294357 Q1–Q6、6405338318 最小改動、6405379650 今天上線）只做三件事：

1. **定時看官網**：每場依開賽時刻 S 推算觀察窗 ``[S−33h, S−30m)``，窗內每 30 分抓一次該賽別 www
   getgamedatas（整年一次）；台北 01:00–09:45 暫停（反爬紅線：深夜加嚴），09:45–10:15 照既有
   ``DAILY_GUARD`` 讓位。S 取狀態檔賽程（stats ``PreExeDate``，每次 probe 更新）⇒ 延賽改期後新 S 自動成為新窗口。
   範圍 A／E／C（晚間鏈設定的賽別），⛔ 不含 D。與既有事件／#292 時點共用 www 帳本：賽別冷卻 20 分、
   挑戰兩次停到隔日 12:00、halted、對帳不等停當晚。
2. **只寫先發**：:func:`write_starters` 只更新目標場的 ``games.home_starter_id``／``away_starter_id``
   （只補不清），並把該場賽前 entry 寫進 ``game_schedule_status_revisions``；⛔ 不寫比分、勝敗投、救援、MVP、
   日期、場地。寫入後走既有 ``POSTSEASON_RESULTS_ONLY`` 同步（晚間鏈 scrape → changed → sync）。
   因為寫入器保證不寫比分，觀察抓取**不受** ``P-A-FETCH-GATE`` 約束（閘門判定本身一字不改）。
3. **超時通知**：本站在窗內超過 45 分沒有成功看過官網（偵測中斷），或本機已有先發而 15 分內沒送到正式站
   （送達失敗）⇒ 本機通知需求方（重用 ``scripts/schedule_watch.py`` 的 ``notify``）＋持久告警檔；
   條件解除（事後補上／恢復偵測）時再通知一次並刪告警檔。

⚠️ 時間語意：本模組記的每個時刻都是**本機**觀測時刻，⛔ 不是官方公布時刻；本站只有「自己去看了」才知道
官網已公布，所以告警條件只能是「本站沒能按時看／沒能送達」，⛔ 不能是「官網已公布但本站未更新」。

旗標檔 ``logs/starter-watch.enabled``（存在＝開，下次喚醒生效）；不存在時本模組完全不被呼叫，晚間鏈行為
與 #365 基準相同。本模組不連網；DB 只在 :func:`write_starters`／:func:`local_starters` 碰。
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

log = logging.getLogger("cpbl.starter_watch")

TAIPEI = ZoneInfo("Asia/Taipei")
FLAG_ENV = "POSTSEASON_STARTER_WATCH_FLAG"
ALERT_ENV = "POSTSEASON_STARTER_WATCH_ALERT"

# —— 技術參數（PLAN 1 §2.2／§3.1 預設值；Q4 裁定 A）——
OPEN_BEFORE = timedelta(hours=33)        # P-SW-OPEN：S−33h 起（18:35 的場前一天 09:35 開窗）
CLOSE_BEFORE = timedelta(minutes=30)     # P-SW-CLOSE：S−30 分止（之後交 #292 A1 與隔日 J1）
INTERVAL = timedelta(minutes=30)         # P-SW-INTERVAL
INTERVAL_SLACK = timedelta(seconds=30)   # launchd 喚醒抖動（同 PROBE_SLACK）
NIGHT_PAUSE = (time(1, 0), time(9, 45))  # P-SW-NIGHT-PAUSE（之後的 09:45–10:15 由 DAILY_GUARD 讓位）
ALERT_GAP = timedelta(minutes=45)        # P-SW-ALERT-GAP：距上次成功觀察抓取（或開窗）
ALERT_SYNC = timedelta(minutes=15)       # P-SW-ALERT-SYNC：本機已有先發、仍未同步成功
KEEP_AFTER_CLOSE = timedelta(days=1)     # 紀錄保留：關窗後一天（已送達或無先發者才刪）
# 只有 stats 的「未開賽」才是觀察目標；START／FINISHED／POSTPONED／RESERVED／未知字串都不是。
WATCH_STATUSES = frozenset({"SCHEDULED"})


def flag_path() -> Path:
    return Path(os.environ.get(FLAG_ENV) or "logs/starter-watch.enabled")


def alert_path() -> Path:
    return Path(os.environ.get(ALERT_ENV) or "logs/starter-watch-alert.json")


def _iso(at: datetime | None) -> str | None:
    return at.astimezone(UTC).isoformat() if at else None


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    at = datetime.fromisoformat(ts)
    return at if at.tzinfo else at.replace(tzinfo=UTC)


def _starts(raw: object) -> datetime | None:
    """stats ``PreExeDate``（台北無時區字串）→ aware datetime；取不到 S ⇒ None（不納入目標）。"""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        at = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return at.replace(tzinfo=TAIPEI) if at.tzinfo is None else at


def in_pause(now: datetime) -> bool:
    t = now.astimezone(TAIPEI).time()
    return NIGHT_PAUSE[0] <= t < NIGHT_PAUSE[1]


def window(starts: datetime) -> tuple[datetime, datetime]:
    return starts - OPEN_BEFORE, starts - CLOSE_BEFORE


def _key(g: Mapping) -> str:
    return f"{g.get('year')}-{g.get('kind_code')}-{g.get('game_sno')}"


def kind_of(key: str) -> str:
    return key.split("-")[1]


def candidates(schedule: Iterable[Mapping], now: datetime, kinds: Iterable[str]) -> dict[str, datetime]:
    """狀態檔賽程中此刻在觀察窗內的未開賽場：``{key: S}``（純函式）。"""
    kinds = set(kinds)
    out: dict[str, datetime] = {}
    for g in schedule or []:
        if g.get("kind_code") not in kinds or str(g.get("status") or "") not in WATCH_STATUSES:
            continue
        starts = _starts(g.get("starts_at"))
        if starts is None:
            continue
        opens, closes = window(starts)
        if opens <= now < closes:
            out[_key(g)] = starts
    return out


def _sw(state: dict) -> dict:
    sw = state.get("starter_watch")
    if not isinstance(sw, dict):
        sw = state["starter_watch"] = {}
    for k in ("games", "fetches", "ok"):
        sw.setdefault(k, {})
    sw.setdefault("inflight", [])
    return sw


def gate_kinds(state: Mapping, now: datetime, kinds: Iterable[str]) -> set[str]:
    """#365 動作條件的擴充（只讀狀態檔，不連 DB）：窗內有尚未在本機看到先發的場 ⇒ 該賽別今晚要醒。"""
    games = ((state.get("starter_watch") or {}).get("games") or {})
    return {kind_of(k) for k in candidates(state.get("schedule") or [], now, kinds)
            if not (games.get(k) or {}).get("local_at")}


def refresh(state: dict, now: datetime, cands: Mapping[str, datetime], have: Iterable[str]) -> None:
    """把此刻的窗內目標併進紀錄（改期 ⇒ 以新 S 重算窗口），標記本機已有先發者；過期紀錄清掉。

    第一次看到就已有先發的場（J1 或既有路徑已寫入）記 ``via=preexisting`` 並視為已送達——那條路徑自己同步，
    本卡不重複告警。"""
    sw = _sw(state)
    have = set(have)
    for key, starts in cands.items():
        opens, closes = window(starts)
        rec = sw["games"].get(key)
        if rec is None:
            rec = sw["games"][key] = {"key": key, "first_target_at": _iso(now), "local_at": None,
                                      "synced_at": None, "via": None, "alert": None, "alerts": []}
            if key in have:
                rec.update(local_at=_iso(now), synced_at=_iso(now), via="preexisting")
        rec.update(starts_at=_iso(starts), open_at=_iso(opens), close_at=_iso(closes))
    note_local(state, now, have)
    for key in list(sw["games"]):
        rec = sw["games"][key]
        closes = _parse(rec.get("close_at"))
        done = rec.get("synced_at") or not rec.get("local_at")
        if closes is not None and now >= closes + KEEP_AFTER_CLOSE and done and not rec.get("alert"):
            del sw["games"][key]


def note_local(state: dict, now: datetime, have: Iterable[str]) -> None:
    """本機首見兩隊先發的時刻（``local_at``；本機觀測，不是官方公布時刻）。"""
    for key in have:
        rec = _sw(state)["games"].get(key)
        if rec is not None and not rec.get("local_at"):
            rec["local_at"] = _iso(now)
            rec["via"] = rec.get("via") or "starter_watch"


def pending_keys(state: Mapping, now: datetime, kind: str | None = None) -> list[str]:
    """窗內、本機還沒有先發的目標場（觀察抓取要找的場）。"""
    out = []
    for key, rec in ((state.get("starter_watch") or {}).get("games") or {}).items():
        if kind is not None and kind_of(key) != kind:
            continue
        opens, closes = _parse(rec.get("open_at")), _parse(rec.get("close_at"))
        if rec.get("local_at") or opens is None or closes is None or not (opens <= now < closes):
            continue
        out.append(key)
    return sorted(out)


def due_kinds(state: Mapping, now: datetime) -> set[str]:
    """此刻該抓的賽別：有待找先發的目標、不在夜間暫停、距該賽別上次觀察抓取已滿 30 分。

    其餘閘門（讓位 10:10、挑戰停、賽別冷卻 20 分、halted、對帳不等）由晚間鏈判斷（同 #292 時點）。"""
    if in_pause(now):
        return set()
    fetches = (state.get("starter_watch") or {}).get("fetches") or {}
    out = set()
    for kind in {kind_of(k) for k in pending_keys(state, now)}:
        last = _parse(fetches.get(kind))
        if last is None or now - last >= INTERVAL - INTERVAL_SLACK:
            out.add(kind)
    return out


def record_fetch(state: dict, now: datetime, kinds: Iterable[str], failed: Iterable[str] = ()) -> None:
    """一次觀察抓取入帳：``fetches``＝最後嘗試（決定 30 分間隔），``ok``＝最後成功（決定偵測中斷告警）。"""
    sw = _sw(state)
    failed = set(failed)
    for kind in kinds:
        sw["fetches"][kind] = _iso(now)
        if kind not in failed:
            sw["ok"][kind] = _iso(now)


def record_sync(state: dict, now: datetime, code: int) -> None:
    """``POSTSEASON_RESULTS_ONLY`` 回 0 ⇒ 本機已有先發的目標場此刻已送到正式站（``synced_at``）。"""
    if code != 0:
        return
    for rec in _sw(state)["games"].values():
        if rec.get("local_at") and not rec.get("synced_at"):
            rec["synced_at"] = _iso(now)


def alert_reasons(state: Mapping, now: datetime) -> dict[str, str]:
    """此刻成立的超時條件（純函式）：``{key: detect_gap|sync_late}``。

    * ``sync_late``：本機已有先發、超過 15 分仍未同步成功（含 68、64–67、備份失敗、鎖被占）。
    * ``detect_gap``：窗內、本機無先發、距該賽別上次**成功**觀察抓取（或開窗時刻，取較晚）超過 45 分——原因可能是
      夜間暫停、挑戰停、鎖、抓取失敗、Mac 睡眠；本站在這段時間不知道官網有沒有公布。
    * 關窗時仍無先發：⛔ 不告警（官網可能真的沒公布，交 #292 A1 與隔日 J1）。"""
    sw = state.get("starter_watch") or {}
    ok = sw.get("ok") or {}
    out: dict[str, str] = {}
    for key, rec in (sw.get("games") or {}).items():
        if rec.get("synced_at"):
            continue
        local_at = _parse(rec.get("local_at"))
        if local_at is not None:
            if now - local_at > ALERT_SYNC:
                out[key] = "sync_late"
            continue
        opens, closes = _parse(rec.get("open_at")), _parse(rec.get("close_at"))
        if opens is None or closes is None or not (opens <= now < closes):
            continue
        ref = max([t for t in (_parse(ok.get(kind_of(key))), opens) if t is not None])
        if now - ref > ALERT_GAP:
            out[key] = "detect_gap"
    return out


Notifier = Callable[[str, str], Mapping]


def _schedule_watch_notify(title: str, message: str) -> Mapping:
    """重用 ``scripts/schedule_watch.py`` 的 ``notify``（osascript＋推播管道量測；⚠️ rc=0 不是送達證據）。"""
    path = Path(__file__).resolve().parents[3] / "scripts" / "schedule_watch.py"
    spec = importlib.util.spec_from_file_location("cpbl_schedule_watch", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"載入不到 {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.notify(title, message)


def _describe(state: Mapping, keys: Iterable[str]) -> str:
    games = (state.get("starter_watch") or {}).get("games") or {}
    parts = []
    for key in sorted(keys):
        starts = _parse((games.get(key) or {}).get("starts_at"))
        parts.append(f"{key}（開賽 {starts.astimezone(TAIPEI):%m/%d %H:%M}）" if starts else key)
    return "、".join(parts)


def apply_alerts(state: dict, now: datetime, *, notify: Notifier | None = None,
                 path: Path | None = None) -> dict[str, Any]:
    """依 :func:`alert_reasons` 更新各場告警、在**轉變時**通知（新增超時／解除），並維持持久告警檔。

    解除原因：``delivered``（事後補上：已送到正式站）／``detection_resumed``（恢復偵測、仍未公布）／
    ``window_closed``。通知失敗只記在 ``starter_watch.notify_error``，不影響晚間鏈。"""
    sw = _sw(state)
    notify = notify or _schedule_watch_notify
    path = path or alert_path()
    current = alert_reasons(state, now)
    raised, resolved = [], []
    for key, rec in sw["games"].items():
        active = rec.get("alert")
        reason = current.get(key)
        if reason and not active:
            rec["alert"] = {"reason": reason, "since": _iso(now)}
            raised.append(key)
        elif reason and active and active.get("reason") != reason:
            active["reason"] = reason
        elif not reason and active:
            how = ("delivered" if rec.get("synced_at") else
                   "window_closed" if now >= (_parse(rec.get("close_at")) or now) else "detection_resumed")
            rec.setdefault("alerts", []).append({**active, "until": _iso(now), "resolution": how})
            rec["alert"] = None
            resolved.append((key, how))
    messages = []
    if raised:
        messages.append(("CPBL 先發超時", f"官網先發觀察超時：{_describe(state, raised)}（詳見 {path}）"))
    if resolved:
        filled = [k for k, how in resolved if how == "delivered"]
        other = [k for k, how in resolved if how != "delivered"]
        text = "；".join(x for x in (f"已補上 {_describe(state, filled)}" if filled else "",
                                     f"已恢復偵測 {_describe(state, other)}" if other else "") if x)
        messages.append(("CPBL 先發告警解除", text))
    deliveries = []
    for title, text in messages:
        try:
            deliveries.append({"title": title, "message": text, "verdict": dict(notify(title, text))})
            sw["notify_error"] = None
        except Exception as exc:  # noqa: BLE001 — 通知失敗不得連坐晚間鏈；照實留在狀態檔與告警檔
            log.exception("先發超時通知失敗")
            sw["notify_error"] = {"at": _iso(now), "error": f"{type(exc).__name__}: {exc}"[:300]}
            deliveries.append({"title": title, "message": text, "error": sw["notify_error"]})
    if deliveries:
        sw.setdefault("notifications", []).extend({"at": _iso(now), **d} for d in deliveries)
        sw["notifications"] = sw["notifications"][-20:]
    active = {k: r["alert"] for k, r in sw["games"].items() if r.get("alert")}
    try:
        if active:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"observed_at": _iso(now), "alerts": active,
                                        "games": {k: sw["games"][k] for k in active},
                                        "last_notifications": sw.get("notifications", [])[-3:],
                                        "notify_error": sw.get("notify_error")},
                                       ensure_ascii=False, indent=2), encoding="utf-8")
        elif path.exists():
            path.unlink()
    except OSError:
        log.exception("先發告警檔寫入失敗：%s", path)
    return {"raised": raised, "resolved": resolved, "active": sorted(active)}


# =========================================================================== 只寫先發寫入器（WP-A）

def _i(v: Any) -> int | None:
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _result(e: Mapping) -> str:
    return str(e.get("GameResult") if e.get("GameResult") is not None else "")


def _scored(e: Mapping) -> bool:
    return bool(_i(e.get("HomeScore")) or _i(e.get("VisitingScore")))


def starter_rows(games: Iterable[Mapping], keys: Iterable[str]) -> tuple[list[tuple], list[Mapping]]:
    """getgamedatas 原始 entry → (games 先發更新列, 要記修訂的 entry)（純函式）。

    只處理 ``keys``（窗內目標場）。同 sno 多筆 entry 整組判斷，任一筆是終局（``GameResult`` 0）、保留（2）或帶非零比分
    ⇒ 整組不碰（已開打的場一列都不寫、也不記修訂）。⚠️ ``PresentStatus``＝1 不代表已開打——實測賽前 entry 也是 1
    （本機修訂表 2026-C-6 10/26 賽前列），所以不用它判斷。主 entry＝``GameResult`` 空白者中 ``GameDate`` 最新的一筆
    （改期後的新排程）；兩隊先發都空 ⇒ 不更新 games，但仍記修訂（「看過、尚未公布」的證據）。"""
    from cpbl.ingest.cpbl_site import _parse_date

    keys = set(keys)
    groups: dict[tuple, list[Mapping]] = {}
    for g in games:
        y, sno = _i(g.get("Year")), _i(g.get("GameSno"))
        if y is None or sno is None or f"{y}-{g.get('KindCode')}-{sno}" not in keys:
            continue
        groups.setdefault((y, g.get("KindCode"), str(g.get("GameSeasonCode") or ""), sno), []).append(g)
    rows: list[tuple] = []
    revisions: list[Mapping] = []
    for (y, kind, season, sno), entries in groups.items():
        if any(_result(e) in ("0", "2") or _scored(e) for e in entries):
            continue
        pregame = [e for e in entries if _result(e) == ""]
        if not pregame:
            continue
        revisions.extend(entries)
        primary = max(pregame, key=lambda e: _parse_date(e.get("GameDate")) or datetime.min.date())
        home, away = primary.get("HomePitcherAcnt") or None, primary.get("VisitingPitcherAcnt") or None
        if home or away:
            rows.append((home, away, y, kind, season, sno))
    return rows, revisions


_STARTER_SQL = """
    UPDATE cpbl.games SET home_starter_id = COALESCE(%s, home_starter_id),
                          away_starter_id = COALESCE(%s, away_starter_id)
    WHERE year = %s AND kind_code = %s AND game_season_code = %s AND game_sno = %s
      AND COALESCE(home_score, 0) = 0 AND COALESCE(away_score, 0) = 0
      AND delay_kind IS DISTINCT FROM '保留'
"""


def write_starters(games: Iterable[Mapping], keys: Iterable[str]) -> dict[str, int]:
    """只寫先發：``games`` 只動兩隊先發欄（只補不清；本機已有比分或保留的列不動），修訂表只記目標場賽前 entry。

    ⛔ 不新增 games 列（新場次由既有事件路徑／J1 處理）、⛔ 不呼叫 ``upsert_games``。"""
    from cpbl.db import conn
    from cpbl.ingest.game_source_revisions import record_schedule_revisions

    rows, revisions = starter_rows(games, keys)
    updated = 0
    if rows:
        with conn() as c:
            cur = c.cursor()
            for row in rows:
                cur.execute(_STARTER_SQL, row)
                updated += cur.rowcount or 0
    recorded = record_schedule_revisions([dict(e) for e in revisions]) if revisions else 0
    return {"games_updated": updated, "revisions": recorded}


def local_starters(year: int, keys: Iterable[str]) -> set[str]:
    """本機 games 兩隊先發都已有值的場（唯讀）。"""
    from cpbl.db import conn

    wanted = sorted(set(keys))
    if not wanted:
        return set()
    with conn() as c:
        rows = c.execute(
            """SELECT year, kind_code, game_sno FROM cpbl.games
               WHERE year = %s AND (kind_code || '-' || game_sno::text) = ANY(%s)
                 AND home_starter_id IS NOT NULL AND away_starter_id IS NOT NULL""",
            (year, [k.split("-", 1)[1] for k in wanted])).fetchall()
    return {f"{y}-{k}-{s}" for y, k, s in rows}


def fetch_step(year: int, kinds: Iterable[str], keys: Iterable[str],
               fetch: Callable[[int, str], list[dict]] | None = None) -> dict[str, Any]:
    """觀察抓取：每賽別 getgamedatas 一次（既有 ``cpbl_site.fetch_year``），只交 :func:`write_starters` 寫目標場。
    錯誤形狀同 ``_postseason_games_step``（``{"kind", "error"}``；單一賽別失敗不連坐）。"""
    if fetch is None:
        from cpbl.ingest.cpbl_site import fetch_year as fetch
    keys = list(keys)
    out: dict[str, Any] = {"games": {}, "errors": []}
    for kind in kinds:
        try:
            games = fetch(year, kind)
            out["games"][kind] = write_starters(games, [k for k in keys if kind_of(k) == kind])
        except Exception as exc:  # noqa: BLE001 — 單一賽別失敗不連坐
            log.exception("先發觀察抓取失敗 kind=%s", kind)
            out["errors"].append({"kind": kind, "error": str(exc)})
    return out
