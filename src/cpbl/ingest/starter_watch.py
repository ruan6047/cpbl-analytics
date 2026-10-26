"""#342：每場比賽前一天 23:00 固定抓官網一次、只更新先發投手並同步正式站（晚間鏈的「先發 23:00 時點」）。

需求方裁定（#342 6405571814 退回需求、6405678916／6405698649 第 3 次確認：依中職「官網於比賽前一天公布」
慣例，前一天 23:00 固定時點；最小改動）：

1. **固定時點**：每場依開賽時刻 S 推算 ``F＝S 前一天 23:00``（台北）。F 起第一次喚醒抓該賽別 www getgamedatas
   一次（整年一次；同一晚多場同賽別合併）。S 取狀態檔賽程（stats ``PreExeDate``，每次 probe 更新）⇒ 延賽改期後
   新 S 的 F 自動成為新時點。範圍 A／E／C（晚間鏈設定的賽別），⛔ 不含 D。共用既有 www 帳本：賽別冷卻 20 分、
   挑戰兩次停到隔日 12:00、halted、對帳不等停當晚；被擋只延後、不計次，最遲到 01:00（深夜加嚴，
   ``docs/CPBL_SITE_MAP.md`` §2），過了記 ``missed``。本機已有兩隊先發的場不抓。
2. **只寫先發**：:func:`write_starters` 只更新目標場的 ``games.home_starter_id``／``away_starter_id``（只補不清），
   並把該場賽前 entry 寫進 ``game_schedule_status_revisions``；⛔ 不寫比分、勝敗投、救援、MVP、日期、場地。
   寫入後走既有 ``POSTSEASON_RESULTS_ONLY`` 同步（晚間鏈 scrape → changed → sync）。
   為什麼不用既有抓取（``evening_games_step``）：(a) A 在 23:00 仍可能被 ``P-A-FETCH-GATE`` 擋（延長賽、保留賽
   整晚不放行）；(b) 既有 A 晚間抓取經 ``marking_scrape_games`` 的 ``www_marker`` 只收 E／C，對 A 會 raise
   （#365 既有行為，本卡不改）；(c) 新路徑的 www 記帳要分得出是 #342（``WWW_REQ card=342``）。
   寫入器保證不寫比分，所以本路徑不受 ``P-A-FETCH-GATE`` 約束（閘門判定本身一字不改）。
3. **失敗通知**：抓取失敗、抓完先發仍空、到 01:00 都沒抓成（``missed``）、或寫入後同步失敗 ⇒ 本機通知需求方
   （重用 ``scripts/schedule_watch.py`` 的 ``notify``；⚠️ rc=0 不是送達證據）＋持久檔；由隔日 10:10 每日鏈補上。

log：本路徑寫進晚間鏈 log 的每一行都以 ``starter-watch`` 開頭（:func:`say`）；www 導頁記 ``WWW_REQ card=342``。

⚠️ 時間語意：本模組記的每個時刻都是**本機**觀測時刻，⛔ 不是官方公布時刻。

旗標檔 ``logs/starter-watch.enabled``（存在＝開，下次喚醒生效）；不存在時本模組完全不被呼叫，晚間鏈行為
與 #365 基準相同。本模組不連網；DB 只在 :func:`write_starters`／:func:`local_starters` 碰。
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")
FLAG_ENV = "POSTSEASON_STARTER_WATCH_FLAG"
ALERT_ENV = "POSTSEASON_STARTER_WATCH_ALERT"

FIRE_AT = time(23, 0)                  # 前一天 23:00（6405678916；研究 1 觀察最晚公布 22:41＋延遲）
FIRE_UNTIL = timedelta(hours=2)        # 被擋最遲延到 01:00（深夜加嚴，不往後排）
FIRE_END = time(1, 0)
KEEP_AFTER_START = timedelta(days=1)   # 紀錄保留到開賽後一天
# 只有 stats 的「未開賽」才是目標；START／FINISHED／POSTPONED／RESERVED／未知字串都不是。
WATCH_STATUSES = frozenset({"SCHEDULED"})
# 需要通知的結局（隔日 10:10 每日鏈補上）
PROBLEMS = ("failed", "empty", "missed", "sync_failed")


def flag_path() -> Path:
    return Path(os.environ.get(FLAG_ENV) or "logs/starter-watch.enabled")


def alert_path() -> Path:
    return Path(os.environ.get(ALERT_ENV) or "logs/starter-watch-alert.json")


def say(message: str) -> None:
    """寫一行到 stderr（晚間鏈 shell 把 stderr 接到 logs/postseason-evening-*.log）；固定 ``starter-watch`` 開頭。"""
    print(f"starter-watch {message}", file=sys.stderr, flush=True)


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


def fire_point(starts: datetime) -> datetime:
    """F＝開賽前一天 23:00（台北）。"""
    day = starts.astimezone(TAIPEI).date() - timedelta(days=1)
    return datetime.combine(day, FIRE_AT, tzinfo=TAIPEI)


def in_fire_hours(now: datetime) -> bool:
    """此刻是否在某個 F 的可抓區間（23:00～次日 01:00）。"""
    t = now.astimezone(TAIPEI).time()
    return t >= FIRE_AT or t < FIRE_END


def fire_game_date(now: datetime):
    """此刻（23:00～01:00）對應的比賽日（台北日期）：23:00 後是明天，00:00 後是今天。"""
    local = now.astimezone(TAIPEI)
    return local.date() + timedelta(days=1) if local.time() >= FIRE_AT else local.date()


def _key(g: Mapping) -> str:
    return f"{g.get('year')}-{g.get('kind_code')}-{g.get('game_sno')}"


def kind_of(key: str) -> str:
    return key.split("-")[1]


def candidates(schedule: Iterable[Mapping], now: datetime, kinds: Iterable[str]) -> dict[str, datetime]:
    """狀態檔賽程中此刻在 ``[F, F+2h)`` 的未開賽場：``{key: S}``（純函式）。"""
    kinds = set(kinds)
    out: dict[str, datetime] = {}
    for g in schedule or []:
        if g.get("kind_code") not in kinds or str(g.get("status") or "") not in WATCH_STATUSES:
            continue
        starts = _starts(g.get("starts_at"))
        if starts is None:
            continue
        fire = fire_point(starts)
        if fire <= now < fire + FIRE_UNTIL:
            out[_key(g)] = starts
    return out


def _sw(state: dict) -> dict:
    sw = state.get("starter_watch")
    if not isinstance(sw, dict):
        sw = state["starter_watch"] = {}
    sw.setdefault("games", {})
    sw.setdefault("inflight", [])
    sw.setdefault("watch_only", [])
    return sw


def gate_kinds(state: Mapping, now: datetime, kinds: Iterable[str]) -> set[str]:
    """#365 動作條件的擴充（只讀狀態檔，不連 DB）：此刻有尚未處理的 23:00 目標 ⇒ 該賽別今晚要醒。"""
    games = ((state.get("starter_watch") or {}).get("games") or {})
    # 還沒抓的（過 01:00 要記 missed）與還沒通知的問題場也要醒一次，否則休兵日 quiet 會吞掉通知。
    out = {kind_of(k) for k, r in games.items()
           if r.get("state") == "due" or (r.get("state") in PROBLEMS and not r.get("notified_at"))}
    for key, starts in candidates(state.get("schedule") or [], now, kinds).items():
        rec = games.get(key) or {}
        if rec.get("fire_at") != _iso(fire_point(starts)) or rec.get("state") == "due":
            out.add(kind_of(key))
    return out


def refresh(state: dict, now: datetime, cands: Mapping[str, datetime], have: Iterable[str]) -> None:
    """把此刻的目標併進紀錄（改期 ⇒ 新 F 另起一筆）、本機已有先發者不抓、過 01:00 仍未抓記 ``missed``、清舊紀錄。"""
    sw = _sw(state)
    have = set(have)
    for key, starts in cands.items():
        fire = fire_point(starts)
        rec = sw["games"].get(key)
        if rec is None or rec.get("fire_at") != _iso(fire):
            rec = sw["games"][key] = {"key": key, "starts_at": _iso(starts), "fire_at": _iso(fire),
                                      "state": "due", "attempted_at": None, "local_at": None,
                                      "synced_at": None, "wait": None, "notified_at": None}
            if key in have:
                rec.update(state="already", local_at=_iso(now))
                say(f"{key} already_has_starters fire_at={rec['fire_at']}")
            else:
                say(f"{key} due fire_at={rec['fire_at']} starts_at={rec['starts_at']}")
    for key, rec in list(sw["games"].items()):
        fire, starts = _parse(rec.get("fire_at")), _parse(rec.get("starts_at"))
        if rec.get("state") == "due" and fire is not None and now >= fire + FIRE_UNTIL:
            rec["state"] = "missed"
            say(f"{key} missed wait={rec.get('wait')}")
        if starts is not None and now >= starts + KEEP_AFTER_START:
            del sw["games"][key]


def pending_keys(state: Mapping, kind: str | None = None) -> list[str]:
    """還沒抓的 23:00 目標場。"""
    return sorted(k for k, r in ((state.get("starter_watch") or {}).get("games") or {}).items()
                  if r.get("state") == "due" and (kind is None or kind_of(k) == kind))


def due_kinds(state: Mapping) -> set[str]:
    return {kind_of(k) for k in pending_keys(state)}


def note_wait(state: dict, kinds: Iterable[str], reason: str) -> None:
    """被閘門擋下（讓位、挑戰停、冷卻、鎖…）：只記原因、不計次。"""
    for kind in kinds:
        for key in pending_keys(state, kind):
            _sw(state)["games"][key]["wait"] = reason


def record_fetch(state: dict, now: datetime, kinds: Iterable[str], failed: Iterable[str],
                 have: Iterable[str]) -> None:
    """一次抓取入帳：失敗 ``failed``；抓到且本機有兩隊先發 ``fetched``；抓到但仍空 ``empty``。每場只抓這一次。"""
    failed, have = set(failed), set(have)
    for kind in kinds:
        for key in pending_keys(state, kind):
            rec = _sw(state)["games"][key]
            rec["attempted_at"] = _iso(now)
            if kind in failed:
                rec["state"] = "failed"
            elif key in have:
                rec.update(state="fetched", local_at=_iso(now))
            else:
                rec["state"] = "empty"
            say(f"{key} {rec['state']} kind={kind}")


def record_sync(state: dict, now: datetime, code: int) -> None:
    """``POSTSEASON_RESULTS_ONLY`` 結果：0 ⇒ 已送到正式站；非 0 ⇒ ``sync_failed``（通知、隔日補上）。"""
    for key, rec in _sw(state)["games"].items():
        if rec.get("state") not in ("fetched", "sync_failed") or rec.get("synced_at"):
            continue
        if code == 0:
            rec["synced_at"] = _iso(now)
            say(f"{key} synced")
        elif rec["state"] == "fetched":
            rec["state"] = "sync_failed"
            say(f"{key} sync_failed code={code}")


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


_REASON_TEXT = {"failed": "抓取失敗", "empty": "官網先發仍空", "missed": "23:00–01:00 沒抓成",
                "sync_failed": "正式站同步失敗"}


def notify_problems(state: dict, now: datetime, *, notify: Notifier | None = None,
                    path: Path | None = None) -> list[str]:
    """尚未通知過的問題場合併成一則本機通知；持久檔列出開賽前仍未解決的問題場（沒有就刪檔）。

    通知失敗只記在 ``starter_watch.notify_error``，不影響晚間鏈（不重送：持久檔仍在）。"""
    sw = _sw(state)
    notify = notify or _schedule_watch_notify
    path = path or alert_path()
    new = sorted(k for k, r in sw["games"].items() if r.get("state") in PROBLEMS and not r.get("notified_at"))
    if new:
        text = "；".join(f"{k}（開賽 {_parse(sw['games'][k]['starts_at']).astimezone(TAIPEI):%m/%d %H:%M}，"
                        f"{_REASON_TEXT[sw['games'][k]['state']]}）" for k in new)
        message = f"先發未於前一天 23:00 更新：{text}；隔日 10:10 每日鏈補上（詳見 {path}）"
        try:
            verdict = dict(notify("CPBL 先發未更新", message))
            sw["notify_error"] = None
        except Exception as exc:  # noqa: BLE001 — 通知失敗不得連坐晚間鏈；照實留在狀態檔與持久檔
            verdict = {}
            sw["notify_error"] = {"at": _iso(now), "error": f"{type(exc).__name__}: {exc}"[:300]}
        for k in new:
            sw["games"][k]["notified_at"] = _iso(now)
        sw["last_notification"] = {"at": _iso(now), "message": message, "verdict": verdict,
                                   "error": sw.get("notify_error")}
        say(f"notify games={','.join(new)} error={bool(sw.get('notify_error'))}")
    open_problems = {k: r for k, r in sw["games"].items()
                     if r.get("state") in PROBLEMS and (_parse(r.get("starts_at")) or now) > now}
    try:
        if open_problems:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"observed_at": _iso(now), "games": open_problems,
                                        "last_notification": sw.get("last_notification"),
                                        "fill_by": "隔日 10:10 每日鏈"}, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        elif path.exists():
            path.unlink()
    except OSError as exc:
        say(f"alert_file_error {type(exc).__name__}: {exc}")
    return new


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
    """23:00 抓取：每賽別 getgamedatas 一次（既有 ``cpbl_site.fetch_year``），只交 :func:`write_starters` 寫目標場。
    www 導頁記 ``WWW_REQ card=342``。錯誤形狀同 ``_postseason_games_step``（``{"kind", "error"}``；單一賽別失敗不連坐）。"""
    from cpbl.ingest._browser import www_marker

    if fetch is None:
        from cpbl.ingest.cpbl_site import fetch_year as fetch
    keys = list(keys)
    out: dict[str, Any] = {"games": {}, "errors": []}
    for kind in kinds:
        try:
            with www_marker("other", "342", f"{year}/{kind}/-", card="342"):
                games = fetch(year, kind)
            out["games"][kind] = result = write_starters(games, [k for k in keys if kind_of(k) == kind])
            say(f"fetch kind={kind} games_updated={result['games_updated']} revisions={result['revisions']}")
        except Exception as exc:  # noqa: BLE001 — 單一賽別失敗不連坐
            say(f"fetch kind={kind} error={type(exc).__name__}: {str(exc)[:200]}")
            out["errors"].append({"kind": kind, "error": str(exc)})
    return out
