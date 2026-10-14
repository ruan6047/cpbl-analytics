"""#268 WP3：事件觸發的晚間季後鏈（A7）。**只製作，不安裝、不啟用**——啟用屬 P1 共享操作。

用法（由 ``scripts/postseason-evening.sh`` 依序呼叫；一般不需手動跑）::

    python -m cpbl.ingest.postseason_evening --help
    python -m cpbl.ingest.postseason_evening plan          # 讀狀態檔、必要時唯讀讀 stats、決定下一步
    python -m cpbl.ingest.postseason_evening scrape        # 跑既有 _postseason_games_step（www）
    python -m cpbl.ingest.postseason_evening sync-due      # 三表沒變時，異動訊號表是否仍需同步
    python -m cpbl.ingest.postseason_evening record-sync --code N
    python -m cpbl.ingest.postseason_evening finish

設計（核定規劃 revision4 §4）：

* **偵測不寫賽程**：只以 httpx 唯讀讀官方 ``stats.cpbl.com.tw`` 賽程 API（無挑戰、不帶憑證），與本機
  DB 比對。stats 資料**不寫進賽程／狀態表**、不作完賽依據——判準仍是 ``cpbl.completion``（官方 final／
  完賽證據），唯一賽程寫入來源仍是 www getgamedatas（既有 ``_postseason_games_step``）。唯一例外是
  #268 D1（需求方裁定 6142259348）的**待更新訊號**：新場次／異動寫進本機
  ``cpbl.official_change_signals``，同步對帳通過或偵測不再成立後寫 ``resolved_at``（見 :func:`signal_rows`）。
  本表隨季後三表一起同步到正式站；本機表變了而三表沒變時，另走一次「僅訊號變動」的同步
  （#268 B1，需求方裁定 6142744045；見 :func:`signals_sync_due`）。
* **只在事件發生時連 www**：三類事件——stats FINISHED 但本機未完成；stats 有本機沒有的
  ``(year, kind, sno)``；日期或主客異動。沒有事件就不 import 爬蟲模組、不碰 www。
* **沒有鐘點截止**：:func:`probe_due` 與 :func:`www_decision` 不含任何「幾點以後不做」的條件；
  跨過 24:00 照常處理，四個時點（T1 官方發佈上界／T2 本站首見／T3 同步完成／T4 使用者可見）
  以實際日期時刻記錄，不改寫成賽事日。唯一的時刻規則是**讓位給每日 10:10 鏈**
  （:data:`DAILY_GUARD`）：那是避免與既有排程搶同一把鎖，不是縮短晚間要求。
* **www 次數上限與冷卻**：每事件最多 3 次、間隔至少 20 分鐘；挑戰類失敗第二次即停止當晚所有
  www 嘗試（``blocked``）。www 請求以賽別為單位，冷卻也以賽別計，只抓冷卻已過的賽別（:func:`www_kinds`）。
* **跨月界**：偵測窗口含上月與未結事件月份；stats 沒回到的場次不視為已解決（:func:`apply_detection`）。
* **錯誤即停**（核定規劃 §4.3）：data-only 對帳不等（refresh 回 68）→ 記失敗並停止當晚
  （``sync_blocked_at``，隔日 12:00 後才再試）；其他同步非零（64–67、psql／schema 錯誤、備份失敗）
  → ``halted``，之後每次喚醒都直接退出，直到人工清除狀態檔的 ``halted``；不調時段補洞。

狀態檔（預設 ``logs/postseason-evening-state.json``）是唯一的跨次記憶；最終狀態另寫
``logs/last-postseason-evening.json``。prod 不寫任何 refresh 標記；本機 ``refresh_log`` 以 scope
``postseason-evening`` 記一列（只在實際嘗試 www 或同步時）。
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from cpbl.ingest._cli import cli_parser

log = logging.getLogger("cpbl.postseason_evening")

TAIPEI = ZoneInfo("Asia/Taipei")
STATS_BASE = "https://stats.cpbl.com.tw"
SCHEDULE_PATH = "/api/proxy/v1/games/schedule"
USER_AGENT = "cpbl-analytics/0.1 (https://cpbl.ruan-ruan.com)"   # 同 live_game_worker
KINDS = ("E", "C")

# —— 節奏參數（設計值，實測後交需求方；不是量測結果）——
GAME_HOT_AFTER = timedelta(minutes=90)        # 當日場次 PreExeDate＋90 分鐘起每次喚醒都讀 stats
IDLE_PROBE_EVERY = timedelta(minutes=15)      # 窗口內一般輪詢
AFTER_SEASON_PROBE_EVERY = timedelta(minutes=60)
PROBE_SLACK = timedelta(seconds=30)           # launchd 喚醒抖動
WWW_MAX_ATTEMPTS = 3
WWW_COOLDOWN = timedelta(minutes=20)
CHALLENGE_LIMIT = 2                            # 挑戰類失敗第 2 次即停當晚
PROBE_UNAVAILABLE_AFTER = 3                    # stats 連續 3 次取不到
# 讓位給每日 10:10 鏈：10:10 前 25 分鐘到 10:15 不取鎖、不連 www（只讓位，不影響晚間）。
DAILY_GUARD = (time(9, 45), time(10, 15))
# 被挑戰擋下後，等到隔日中午（每日鏈已跑過）才重新允許 www；不是晚間截止。
BLOCK_RELEASE_AT = time(12, 0)

CHALLENGE_MARKERS = ("反爬", "挑戰", "REDIRECT", "428", "token")
# D1 訊號只收「官方賽程異動」兩類；完賽未入庫已由 coverage 的完賽軸處理（過日／即時 final）。
SIGNAL_EVENT_TYPES = ("new_game", "schedule_changed")


# =========================================================================== 資料形狀

@dataclass(frozen=True)
class StatsGame:
    """stats 賽程 API 的一列（只取偵測需要的欄位；**不寫入**任何表）。"""
    year: int
    kind_code: str
    game_sno: int
    status: str                 # SCHEDULED／START／FINISHED／POSTPONED／RESERVED…（官方原字）
    starts_at: str | None       # PreExeDate（台北無時區字串）
    game_date: str | None
    away_code: str | None
    home_code: str | None
    venue: str | None

    @property
    def key(self) -> str:
        return f"{self.year}-{self.kind_code}-{self.game_sno}"


@dataclass(frozen=True)
class LocalGame:
    year: int
    kind_code: str
    game_sno: int
    game_date: str | None
    away_code: str | None
    home_code: str | None
    venue: str | None
    completed: bool              # cpbl.completion 正式判準

    @property
    def key(self) -> str:
        return f"{self.year}-{self.kind_code}-{self.game_sno}"


@dataclass(frozen=True)
class Event:
    type: str                    # final_not_ingested／new_game／schedule_changed
    key: str
    game_date: str | None
    detail: tuple[str, ...] = field(default_factory=tuple)
    # 異動欄位的官方新值（D1 訊號用）：new_game → (("game", 開賽時刻),)；schedule_changed → 逐欄。
    official: tuple[tuple[str, str | None], ...] = field(default_factory=tuple)


class ProbeUnavailable(RuntimeError):
    """stats 讀取失敗（逾時、非 200、形狀漂移）。fail closed：當次不判任何事件。"""


# =========================================================================== stats 唯讀偵測

def _team_code(side: object) -> str | None:
    if not isinstance(side, Mapping):
        return None
    team = side.get("Team")
    if isinstance(team, Mapping) and team.get("Code"):
        return str(team["Code"])
    return str(side["Code"]) if side.get("Code") else None


def parse_stats_games(rows: Iterable[Mapping], year: int) -> list[StatsGame]:
    """``Data.Games[]`` → :class:`StatsGame`。身分以 ``GameId``（``YYYY-K-SNO``）為準，與
    ``KindCode``／``GameSno`` 不一致的列**整列略過**（不猜）。主客隊碼取不到時為 None，
    偵測端就不比主客（不把未知當異動）。"""
    out: list[StatsGame] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ProbeUnavailable("stats schedule schema drift: 列不是物件")
        parts = str(row.get("GameId") or "").split("-")
        try:
            gid = (int(parts[0]), parts[1], int(parts[2])) if len(parts) == 3 else None
            sno = int(row.get("GameSno"))
        except (TypeError, ValueError):
            continue
        kind = str(row.get("KindCode") or "")
        if gid is None or gid != (year, kind, sno) or kind not in KINDS:
            continue
        starts = row.get("PreExeDate")
        starts = str(starts) if starts else None
        venue = row.get("Field")
        out.append(StatsGame(
            year=year, kind_code=kind, game_sno=sno,
            status=str(row.get("GameStatus") or ""),
            starts_at=starts,
            game_date=starts[:10] if starts and len(starts) >= 10 else None,
            away_code=_team_code(row.get("Visiting")),
            home_code=_team_code(row.get("Home")),
            venue=str(venue["Abbe"]) if isinstance(venue, Mapping) and venue.get("Abbe") else None,
        ))
    return out


Fetcher = Callable[[str, dict], Mapping]


def _httpx_fetch(timeout: float) -> Fetcher:
    def fetch(path: str, params: dict) -> Mapping:
        import httpx

        with httpx.Client(base_url=STATS_BASE, timeout=timeout, follow_redirects=True,
                          headers={"User-Agent": USER_AGENT}) as client:
            response = client.get(path, params=params)
            response.raise_for_status()
            return response.json()
    return fetch


def stats_probe(year: int, months: Iterable[int], *, fetch: Fetcher | None = None,
                timeout: float = 10.0) -> list[StatsGame]:
    """唯讀讀 stats 賽程（E、C × 指定月份）。任一請求失敗即整批 :class:`ProbeUnavailable`——
    半套結果會讓「這場不在 stats」被誤讀成取消，故 fail closed；每次只送 GET、不重試。"""
    fetch = fetch or _httpx_fetch(timeout)
    games: dict[str, StatsGame] = {}
    for kind in KINDS:
        for month in months:
            try:
                body = fetch(SCHEDULE_PATH, {"kindCode": kind, "year": str(year), "month": str(month)})
                rows = ((body or {}).get("Data") or {}).get("Games") or []
            except ProbeUnavailable:
                raise
            except Exception as exc:  # noqa: BLE001 — 逾時／HTTP／JSON 一律 fail closed
                raise ProbeUnavailable(f"{kind}/{month}: {type(exc).__name__}") from exc
            if not isinstance(rows, list):
                raise ProbeUnavailable("stats schedule schema drift: Games 不是 list")
            for g in parse_stats_games(rows, year):
                games[g.key] = g
    return sorted(games.values(), key=lambda g: (g.starts_at or "", g.kind_code, g.game_sno))


def detect_events(stats: Iterable[StatsGame], local: Mapping[str, LocalGame]) -> list[Event]:
    """純函式：stats 與本機的差 → 事件。stats 沒有列不代表取消（不產生事件）。

    異動依核定規劃比日期、主客、球場三項；任一側缺值就不比（不把未知當異動）。球場只去前後
    空白後逐字比——stats ``Field.Abbe`` 與本機 ``venue`` 在公開資料上同為短名（大巨蛋／洲際），
    若實測出現命名不一致，代價受每事件 3 次 www 上限約束，並在時點紀錄中可見。"""
    events: list[Event] = []
    for g in stats:
        loc = local.get(g.key)
        if loc is None:
            events.append(Event("new_game", g.key, g.game_date,
                                official=(("game", g.starts_at or g.game_date),)))
            continue
        if g.status == "FINISHED" and not loc.completed:
            events.append(Event("final_not_ingested", g.key, g.game_date or loc.game_date))
        changed = []
        if g.game_date and loc.game_date and g.game_date != loc.game_date:
            changed.append("date")
        if g.away_code and g.home_code and loc.away_code and loc.home_code and (
                (g.away_code, g.home_code) != (loc.away_code, loc.home_code)):
            changed.append("teams")
        if g.venue and loc.venue and g.venue.strip() != loc.venue.strip():
            changed.append("venue")
        if changed:
            values = {"date": g.game_date, "teams": f"{g.away_code}@{g.home_code}", "venue": g.venue}
            events.append(Event("schedule_changed", g.key, g.game_date, tuple(changed),
                                official=tuple((f, values[f]) for f in changed)))
    return events


# =========================================================================== 狀態與節奏（純函式）

def _now() -> datetime:
    return datetime.now(UTC)


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    at = datetime.fromisoformat(ts)
    return at if at.tzinfo else at.replace(tzinfo=UTC)


def _iso(at: datetime | None) -> str | None:
    return at.astimezone(UTC).isoformat() if at else None


def taipei(at: datetime) -> datetime:
    return at.astimezone(TAIPEI)


def empty_state() -> dict[str, Any]:
    return {"version": 1, "last_probe_at": None, "probe_failures": 0, "probe_status": "ok",
            "schedule": [], "events": {}, "challenge_failures": [], "www_blocked_at": None,
            "pending_sync": False, "sync_blocked_at": None, "halted": None,
            "needs_owner_decision": None, "last_run": None,
            "detected_changes": [], "signals_dirty": False, "signals_error": None,
            "signals_unsynced": False, "www_requests": {}, "scrape_kinds": []}


def _starts(g: Mapping) -> datetime | None:
    raw = g.get("starts_at")
    if not raw:
        return None
    try:
        at = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return at.replace(tzinfo=TAIPEI) if at.tzinfo is None else at


def open_events(state: Mapping) -> dict[str, dict]:
    return {k: e for k, e in (state.get("events") or {}).items() if e.get("state") == "open"}


def in_daily_guard(now: datetime) -> bool:
    t = taipei(now).time()
    return DAILY_GUARD[0] <= t < DAILY_GUARD[1]


def probe_due(state: Mapping, now: datetime) -> tuple[bool, str]:
    """這一次喚醒要不要讀 stats。**不含任何晚間鐘點截止**。

    * halted → 不讀（等人工）。
    * 有未結事件、或本機已有變化尚未同步 → 每次喚醒都讀（hot）。
    * 今天（台北日）有場次且已過 PreExeDate＋90 分鐘、而當天場次仍有未結 → 每次喚醒都讀。
    * 已知賽程全部過去、沒有未結事件 → 每 60 分鐘（只為了接住改期／新公告）。
    * 其他 → 每 15 分鐘。
    """
    if state.get("halted"):
        return False, "halted"
    last = _parse(state.get("last_probe_at"))
    schedule = state.get("schedule") or []
    if last is None or not schedule:
        return True, "bootstrap"
    today = taipei(now).date()
    if open_events(state) or state.get("pending_sync"):
        return True, "hot_open_events"
    for g in schedule:
        starts = _starts(g)
        if starts and starts.date() == today and now >= starts + GAME_HOT_AFTER and g.get("status") != "FINISHED":
            return True, "hot_game_day"
    last_day = max((_starts(g).date() for g in schedule if _starts(g)), default=None)
    every = AFTER_SEASON_PROBE_EVERY if last_day is not None and last_day < today else IDLE_PROBE_EVERY
    return (now - last >= every - PROBE_SLACK), ("after_season" if every == AFTER_SEASON_PROBE_EVERY else "idle")


def www_blocked(state: Mapping, now: datetime) -> bool:
    blocked = _parse(state.get("www_blocked_at"))
    if blocked is None:
        return False
    local = taipei(blocked)
    release_day = local.date() + timedelta(days=0 if local.time() < BLOCK_RELEASE_AT else 1)
    release = datetime.combine(release_day, BLOCK_RELEASE_AT, tzinfo=TAIPEI)
    return now < release


def _kind_of(key: str) -> str:
    return key.split("-")[1]


def www_kinds(state: Mapping, now: datetime) -> tuple[str, ...]:
    """這次可以抓的賽別（#268 審核 F2）。

    www 的實際請求單位是**賽別**（既有 ``_postseason_games_step(year, kinds)`` 對每個賽別抓整年，
    不能只抓單場），所以冷卻也以賽別計：某賽別上一次請求（或該賽別任一未結事件的上一次嘗試）未滿
    20 分鐘，整個賽別都不得再抓——否則新事件會讓同賽別仍在冷卻的舊事件被再抓一次。賽別內至少要有
    一個未結且未用盡 3 次的事件。不同賽別互不連坐（E 冷卻中，C 的新公告仍可立即抓 C）。"""
    requests = state.get("www_requests") or {}
    out = []
    for kind in KINDS:
        evs = [e for e in open_events(state).values() if _kind_of(e["key"]) == kind]
        if not any(len(e.get("attempts") or []) < WWW_MAX_ATTEMPTS for e in evs):
            continue
        stamps = [_parse(requests.get(kind))] + [_parse(a) for e in evs for a in e.get("attempts") or []]
        stamps = [s for s in stamps if s is not None]
        if stamps and now - max(stamps) < WWW_COOLDOWN:
            continue
        out.append(kind)
    return tuple(out)


def www_decision(state: Mapping, now: datetime) -> tuple[bool, str]:
    """有未結事件時，這次喚醒能不能連 www（每事件 ≤3 次、間隔 ≥20 分鐘、挑戰兩次停當晚）。
    可抓的賽別見 :func:`www_kinds`。"""
    if state.get("halted"):
        return False, "halted"
    if in_daily_guard(now):
        return False, "yield_to_daily"
    if www_blocked(state, now):
        return False, "blocked"
    if not www_kinds(state, now):
        return False, "cooldown_or_exhausted" if open_events(state) else "no_events"
    return True, "event"


def apply_detection(state: dict, events: list[Event], now: datetime,
                    local_first_seen: Mapping[str, str | None] | None = None, *,
                    resolved_by_chain: bool = False,
                    observed_keys: Iterable[str] | None = None,
                    chain_kinds: Iterable[str] | None = None) -> dict:
    """偵測結果併入狀態：新事件記 T1（stats 首次觀測＝官方發佈上界）；不再被偵測到的
    未結事件依來源結清。

    ``resolved_by_chain=True`` 只在**本鏈剛跑完 www** 之後的那次比對使用：此時消失的事件
    是本鏈處理的 → ``ingested``（等同步補 T3）。其他時候（下一次 plan 才發現消失）代表是
    別的路徑（例如隔日 10:10）補上的 → ``unreached``／``resolved_outside_evening_chain``，
    **不得算成同晚達成**，即使本鏈先前試過 www。

    ``observed_keys``＝本次 stats 實際回了哪些場次（#268 審核 F3）。「這一場這次沒被看到」不等於
    「差異已消失」：只有 stats 看得到該場、且不再報差異，才算結清；看不到的場次事件維持原狀、其異動
    訊號也保留上一輪的值（不因查詢窗口或來源漏列而被結清）。``None``＝呼叫端不提供（視同全部看得到）。
    ``chain_kinds``＝本鏈這次實際抓的賽別（F2）：只有這些賽別的事件可記為本鏈 ``ingested``。"""
    events_state = state.setdefault("events", {})
    current = {f"{e.type}:{e.key}": e for e in events}
    observed = None if observed_keys is None else set(observed_keys)
    # D1：本次偵測仍成立的異動（含已記未達者）＝應維持開啟的訊號；見 signal_rows。
    # 本次沒看到的場次沿用上一輪的異動（F3）。
    carried = [] if observed is None else [
        c for c in state.get("detected_changes") or [] if c["key"] not in observed]
    state["detected_changes"] = carried + [
        {"key": e.key, "field": f, "official_value": v}
        for e in events if e.type in SIGNAL_EVENT_TYPES for f, v in e.official]
    state["signals_dirty"] = True
    for ident, e in current.items():
        if ident in events_state and events_state[ident].get("state") == "open":
            events_state[ident]["official"] = dict(e.official)
        if ident not in events_state or events_state[ident].get("state") != "open":
            if ident in events_state and events_state[ident].get("state") in ("unreached",):
                continue  # 已記未達的事件不重開，避免同一事件無限重試
            events_state[ident] = {"type": e.type, "key": e.key, "game_date": e.game_date,
                                   "detail": list(e.detail), "official": dict(e.official),
                                   "state": "open",
                                   "t1_stats_first_seen": _iso(now), "t2_local_first_seen": None,
                                   "t3_synced": None, "attempts": [], "reason": None}
    for ident, rec in events_state.items():
        if rec.get("state") != "open" or ident in current:
            continue
        if observed is not None and rec["key"] not in observed:
            continue   # 本次 stats 沒有這一場：無從判斷差異是否消失，維持未結（F3）
        rec["t2_local_first_seen"] = (local_first_seen or {}).get(rec["key"]) or rec.get("t2_local_first_seen")
        by_chain = resolved_by_chain and (chain_kinds is None or _kind_of(rec["key"]) in set(chain_kinds))
        if by_chain and rec.get("attempts"):
            rec["state"] = "ingested"
        else:
            rec["state"] = "unreached"
            rec["reason"] = "resolved_outside_evening_chain"
    for rec in open_events(state).values():
        if len(rec.get("attempts") or []) >= WWW_MAX_ATTEMPTS:
            rec["state"] = "unreached"
            rec["reason"] = "www_no_final_after_max_attempts"
    return state


def plan(state: dict, now: datetime, *, probe: Callable[[], list[StatsGame]],
         load_local: Callable[[], dict[str, LocalGame]],
         local_first_seen: Callable[[], dict[str, str | None]] = dict) -> tuple[str, str]:
    """一次喚醒的決策。回 (action, reason)；action ∈ idle／halted／scrape／sync。

    **沒有事件就不會回 scrape**（＝不連 www）；stats 讀不到時也不回 scrape（fail closed）。
    原本會閒置、但本機異動訊號表待同步時回 ``("sync", "signals_only")``（B1；不連 www）。
    """
    if state.get("halted"):
        return "halted", state["halted"].get("reason", "halted")
    due, why = probe_due(state, now)
    probe_failed = False
    if due:
        try:
            stats = probe()
        except ProbeUnavailable as exc:
            state["probe_failures"] = int(state.get("probe_failures") or 0) + 1
            state["last_probe_at"] = _iso(now)
            if state["probe_failures"] >= PROBE_UNAVAILABLE_AFTER:
                state["probe_status"] = "probe_unavailable"
            log.warning("stats 讀取失敗（第 %s 次）：%s", state["probe_failures"], exc)
            stats, probe_failed = None, True
        if stats is not None:
            state["probe_failures"] = 0
            state["probe_status"] = "ok"
            state["last_probe_at"] = _iso(now)
            state["schedule"] = [asdict(g) for g in stats]
            apply_detection(state, detect_events(stats, load_local()), now, local_first_seen(),
                            observed_keys=[g.key for g in stats])
    # 對帳不等已停止當晚：只記錄偵測（T1），不再連 www、不再同步。
    if sync_blocked(state, now):
        return "idle", "sync_blocked_tonight"
    # 本機已變、尚未同步：不需要再碰 www，可直接同步（仍讓位 10:10）。
    if state.get("pending_sync") and not in_daily_guard(now):
        return "sync", "pending_sync"
    if probe_failed:
        return with_signal_sync(state, now, "idle", "probe_unavailable")   # 讀不到 stats 就不連 www
    if open_events(state):
        ok, reason = www_decision(state, now)
        # 能連 www 就先抓（之後同一次喚醒的同步會一併帶上訊號表）；不能連時才單獨同步訊號。
        if ok:
            state["scrape_kinds"] = list(www_kinds(state, now))   # scrape 只抓這些賽別（F2）
            return "scrape", reason
        return with_signal_sync(state, now, "idle", reason)
    return with_signal_sync(state, now, "idle", why if not due else "no_events")


def signals_sync_due(state: Mapping, now: datetime) -> bool:
    """#268 B1：本機異動訊號表已與上次成功同步時不同，且此刻允許同步。

    與三表同一條路徑（已驗證備份→限定同步→data-only 對帳），也同樣受錯誤即停約束：halted 不做、
    對帳不等後當晚不做、讓位 10:10。``signals_unsynced`` 只由 :func:`publish_signals`（實際寫出變動）
    設定、由 :func:`record_sync`（同步成功）清除。"""
    return (bool(state.get("signals_unsynced")) and not state.get("halted")
            and not sync_blocked(state, now) and not in_daily_guard(now))


def with_signal_sync(state: Mapping, now: datetime, action: str, reason: str) -> tuple[str, str]:
    """閒置的決定遇上「訊號表待同步」→ 改為一次僅訊號變動的同步；其他決定原樣回傳。"""
    if action == "idle" and signals_sync_due(state, now):
        return "sync", "signals_only"
    return action, reason


def record_scrape(state: dict, now: datetime, *, errors: list[dict], changed: bool,
                  stats_has_c: bool, local_c_rows: int, kinds: Iterable[str] = KINDS) -> str:
    """一次 www 嘗試的結果入帳。回 changed／unchanged／failed。

    ``kinds``＝這次實際抓的賽別：只有這些賽別的未結事件記一次嘗試，並記賽別的請求時刻
    （:func:`www_kinds` 據此冷卻；#268 審核 F2）。沒抓到的賽別事件不記、不耗次數。

    「www 抓取成功（C 無錯）但本機 C 列仍為 0」依規劃 §4.6 **只停該項**：C 的 new_game 事件
    記未達並標 ``needs_owner_decision``，不換工具、不繞道，也不連坐 E 或同步。"""
    kinds = tuple(kinds)
    requests = state.setdefault("www_requests", {})
    for kind in kinds:
        requests[kind] = _iso(now)
    for rec in open_events(state).values():
        if _kind_of(rec["key"]) in kinds:
            rec.setdefault("attempts", []).append(_iso(now))
    challenge = any(any(m.lower() in str(e.get("error", "")).lower() for m in CHALLENGE_MARKERS)
                    for e in errors)
    if challenge:
        state.setdefault("challenge_failures", []).append(_iso(now))
        # 「當晚」＝尚未到該次失敗的釋放時刻（隔日中午）的那幾次。
        tonight = [t for t in state["challenge_failures"] if www_blocked({"www_blocked_at": t}, now)]
        state["challenge_failures"] = tonight
        if len(tonight) >= CHALLENGE_LIMIT:
            state["www_blocked_at"] = _iso(now)
    if changed:
        state["pending_sync"] = True
    c_error = any(e.get("kind") == "C" for e in errors)
    if "C" in kinds and stats_has_c and not c_error and local_c_rows == 0:   # 這次真的抓了 C 才算
        for rec in open_events(state).values():
            if rec["type"] == "new_game" and rec["key"].split("-")[1] == "C":
                rec["state"] = "unreached"
                rec["reason"] = "c_rows_still_zero_after_www_success"
        state["needs_owner_decision"] = {"at": _iso(now), "reason": "c_rows_still_zero_after_www_success"}
    if errors:
        return "failed"
    return "changed" if changed else "unchanged"


SYNC_RECONCILE_MISMATCH = 68   # refresh-cpbl-prod.sh POSTSEASON_RESULTS_ONLY 的 data-only 對帳不等


def sync_blocked(state: Mapping, now: datetime) -> bool:
    """對帳不等後「停止當晚」：與挑戰類封鎖同一個釋放時刻（隔日 12:00，每日鏈已跑過）。"""
    return www_blocked({"www_blocked_at": state.get("sync_blocked_at")}, now)


def record_sync(state: dict, now: datetime, code: int) -> str:
    """同步結果入帳（核定規劃 §4.3 錯誤即停）。

    * 0 → 補 T3、結清 pending。
    * 68（data-only 對帳不等）→ 記失敗並**停止當晚**（``blocked``）；pending 保留，隔日 12:00 後重試。
    * 其他非零（64–67、psql／schema 錯誤、備份失敗…）→ ``halted``：立即停、bootout、交人工。
    """
    if code == SYNC_RECONCILE_MISMATCH:
        state["sync_blocked_at"] = _iso(now)
        return "blocked"
    if code != 0:
        state["halted"] = {"at": _iso(now), "reason": f"sync_exit_{code}"}
        return "halted"
    state["pending_sync"] = False
    # B1：這次同步已把當下的本機訊號表帶到正式站。下一行的解決若再改動本機表，會由
    # publish_signals 重新標記，下次喚醒再走一次僅訊號變動的同步（對帳通過才解決＝裁定 D1 的順序）。
    state["signals_unsynced"] = False
    for rec in (state.get("events") or {}).values():
        if rec.get("state") == "ingested" and not rec.get("t3_synced"):
            rec["t3_synced"] = _iso(now)
            rec["state"] = "synced"
    state["signals_dirty"] = True   # 同步對帳通過：本鏈入庫的異動訊號在這一刻解決（D1）
    return "synced"


def signal_rows(state: Mapping) -> list[dict]:
    """D1：應維持「未解決」的官方異動訊號（純函式；其餘由 ``change_signals.write_signals`` 解決）。

    * 最近一次偵測仍成立的新場次／異動——包括已記未達（www 次數用盡、C 列仍為 0）者：官方已變、
      本站仍未反映，頁面就必須說待更新。
    * 本鏈已把它抓進本機、但同步對帳尚未通過（``ingested``）者：正式站還沒有，等 :func:`record_sync`
      回 synced 才解決（需求方裁定：同步對帳通過寫 resolved_at）。

    其他（已 synced、或由隔日 10:10 等其他路徑補上而偵測不再成立）都不在集合內＝解決。
    """
    rows: dict[tuple[str, str], str | None] = {}
    for change in state.get("detected_changes") or []:
        rows[(change["key"], change["field"])] = change.get("official_value")
    for rec in (state.get("events") or {}).values():
        if rec.get("state") == "ingested" and rec.get("type") in SIGNAL_EVENT_TYPES:
            for fld, value in (rec.get("official") or {}).items():
                rows.setdefault((rec["key"], fld), value)
    out = []
    for (key, fld), value in sorted(rows.items()):
        _, kind, sno = key.split("-")
        out.append({"kind_code": kind, "game_sno": int(sno), "field": fld, "official_value": value})
    return out


def timeline(state: Mapping) -> list[dict]:
    """狀態檔的四時點摘要（T4 需正式 Chrome 抽樣，這裡恆為 None）。日期照實，不改寫成賽事日。"""
    out = []
    for rec in (state.get("events") or {}).values():
        out.append({"key": rec["key"], "type": rec["type"], "game_date": rec.get("game_date"),
                    "state": rec.get("state"), "reason": rec.get("reason"),
                    "t1_stats_first_seen": rec.get("t1_stats_first_seen"),
                    "t2_local_first_seen": rec.get("t2_local_first_seen"),
                    "t3_synced": rec.get("t3_synced"), "t4_user_visible": None,
                    "www_attempts": len(rec.get("attempts") or [])})
    return sorted(out, key=lambda r: (r["t1_stats_first_seen"] or "", r["key"]))


# =========================================================================== 本機 DB（唯讀＋本機 refresh_log）

def load_local_games(year: int, now: datetime) -> dict[str, LocalGame]:
    from cpbl.completion import completed_games_sql_with_evidence
    from cpbl.coverage import taipei_date
    from cpbl.db import conn

    done = completed_games_sql_with_evidence("g", "%(as_of)s")
    with conn() as c:
        rows = c.execute(
            f"""SELECT g.year, g.kind_code, g.game_sno, g.game_date, g.away_team_code,
                       g.home_team_code, g.venue, COALESCE({done}, FALSE)
                FROM cpbl.games g WHERE g.year = %(year)s AND g.kind_code IN ('E', 'C')""",
            {"year": year, "as_of": taipei_date(now)},
        ).fetchall()
    out = {}
    for y, k, s, d, away, home, venue, completed in rows:
        g = LocalGame(int(y), k, int(s), d.isoformat() if d else None, away, home, venue, bool(completed))
        out[g.key] = g
    return out


def local_first_seen(year: int) -> dict[str, str | None]:
    """T2：本機狀態修訂表首次出現 final 列（沒有 final 時取首次出現任一列）的 fetched_at。"""
    from cpbl.db import conn

    with conn() as c:
        rows = c.execute(
            """SELECT year, kind_code, game_sno,
                      min(fetched_at) FILTER (WHERE raw_present_status = 1 AND raw_game_result = '0'),
                      min(fetched_at)
               FROM cpbl.game_schedule_status_revisions
               WHERE year = %s AND kind_code IN ('E', 'C') GROUP BY 1, 2, 3""", (year,),
        ).fetchall()
    return {f"{y}-{k}-{s}": _iso(final or first) for y, k, s, final, first in rows}


def local_signature(year: int) -> str:
    """本機 E／C 的可同步狀態指紋（games 列＋各場狀態修訂筆數與最新取得時刻）。"""
    import hashlib

    from cpbl.db import conn

    with conn() as c:
        games = c.execute(
            """SELECT year, kind_code, game_sno, game_date, venue, away_team_code, home_team_code,
                      away_score, home_score, present_status, delay_kind, orig_date
               FROM cpbl.games WHERE year = %s AND kind_code IN ('E', 'C')
               ORDER BY 1, 2, 3""", (year,)).fetchall()
        revs = c.execute(
            """SELECT year, kind_code, game_sno, count(*), max(fetched_at)
               FROM cpbl.game_schedule_status_revisions
               WHERE year = %s AND kind_code IN ('E', 'C') GROUP BY 1, 2, 3 ORDER BY 1, 2, 3""",
            (year,)).fetchall()
    return hashlib.sha256(repr((games, revs)).encode()).hexdigest()


def log_local_refresh(state: Mapping, ok: bool, note: str | None) -> None:
    """只寫**本機** refresh_log（scope postseason-evening）；prod 不寫任何標記。"""
    from cpbl.db import conn

    with conn() as c:
        c.execute(
            """INSERT INTO cpbl.refresh_log (scope, from_date, to_date, detail, ok, note)
               VALUES ('postseason-evening', %s, %s, %s::jsonb, %s, %s)""",
            (taipei(_now()).date(), taipei(_now()).date(),
             json.dumps({"timeline": timeline(state), "halted": state.get("halted"),
                         "www_blocked_at": state.get("www_blocked_at")}), ok, note),
        )


def publish_signals(state: dict, year: int, now: datetime) -> None:
    """D1：把 :func:`signal_rows` 寫成本機 ``cpbl.official_change_signals`` 的現況（只在狀態有變時）。

    寫入失敗不改變本次動作的結果（賽程鏈本身比訊號重要），但照實記在狀態檔 ``signals_error``、
    保留 dirty 旗標下次再寫——⛔ 不吞成成功。"""
    if not state.get("signals_dirty"):
        return
    from cpbl.change_signals import write_signals
    from cpbl.db import conn

    try:
        with conn() as c:
            changed = write_signals(c.cursor(), year, signal_rows(state), now)
    except Exception as exc:  # noqa: BLE001 — 見 docstring
        log.exception("official_change_signals 寫入失敗")
        state["signals_error"] = {"at": _iso(now), "error": type(exc).__name__}
        return
    state["signals_dirty"] = False
    state["signals_error"] = None
    if changed:
        state["signals_unsynced"] = True   # B1：本機表已變，正式站還是舊的（見 signals_sync_due）


# =========================================================================== 狀態檔 I/O

def state_path() -> Path:
    return Path(os.environ.get("POSTSEASON_STATE", "logs/postseason-evening-state.json"))


def status_path() -> Path:
    return Path(os.environ.get("POSTSEASON_STATUS", "logs/last-postseason-evening.json"))


def load_state(path: Path) -> dict:
    if not path.exists():
        return empty_state()
    return {**empty_state(), **json.loads(path.read_text(encoding="utf-8"))}


def save_json(path: Path, data: Mapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _season_year(now: datetime) -> int:
    return int(os.environ.get("POSTSEASON_YEAR") or taipei(now).year)


def _months(now: datetime, state: Mapping | None = None) -> list[int]:
    """stats 偵測窗口（月份）。當月、下月（公告新場次）、**上月**，以及任何未結／待同步事件的賽事月份。

    #268 審核 F3：原本只查當月／下月，10/31 深夜未完成的事件在 11/1 00:00 起就不在查詢結果中，
    被誤當成「已由其他路徑解決」；月末深夜才公布的前月終場也會漏偵測。不設截止＝跨過月界也要
    繼續看前月。只限同一季年度（1 月不回頭查前一年 12 月）。"""
    m = taipei(now).month
    months = {m}
    if m < 12:
        months.add(m + 1)
    if m > 1:
        months.add(m - 1)
    for rec in ((state or {}).get("events") or {}).values():
        day = str(rec.get("game_date") or "")
        if rec.get("state") in ("open", "ingested") and len(day) >= 7 and day[5:7].isdigit():
            months.add(int(day[5:7]))
    return sorted(months)


# =========================================================================== CLI

def _parser():
    p = cli_parser("python -m cpbl.ingest.postseason_evening", __doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="讀狀態、必要時唯讀讀 stats，印出 idle／halted／scrape／sync")
    sub.add_parser("scrape", help="既有 _postseason_games_step（www）；印 changed／unchanged／failed／halted")
    sub.add_parser("sync-due", help="印 signals（本機異動訊號表待同步且允許）或 no；唯讀狀態檔")
    rs = sub.add_parser("record-sync", help="記錄 refresh-cpbl-prod.sh 的結果")
    rs.add_argument("--code", type=int, required=True)
    sub.add_parser("finish", help="寫最終狀態檔（與必要時的本機 refresh_log）")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    now = _now()
    year = _season_year(now)
    path = state_path()
    state = load_state(path)

    if args.command == "plan":
        action, reason = plan(
            state, now,
            probe=lambda: stats_probe(year, _months(now, state)),
            load_local=lambda: load_local_games(year, now),
            local_first_seen=lambda: local_first_seen(year),
        )
        publish_signals(state, year, now)
        # 本次偵測剛改動本機訊號表、而這次本來只會閒置（www 不能連）→ 同一次喚醒就送出（B1）。
        action, reason = with_signal_sync(state, now, action, reason)
        state["last_run"] = {"at": _iso(now), "action": action, "reason": reason}
        save_json(path, state)
        print(action)
        return 0

    if args.command == "sync-due":
        # scrape 之後由 postseason-evening.sh 詢問：三表沒變（或 www 失敗）時，訊號表是否仍需同步（B1）。
        print("signals" if signals_sync_due(state, now) else "no")
        return 0

    if args.command == "scrape":
        # 只有這裡會 import 爬蟲（Playwright／www）；plan 階段一律不載入。
        from cpbl.config import parse_postseason_kinds, settings
        from cpbl.ingest.run_refresh_recent import _postseason_games_step

        configured = parse_postseason_kinds(settings.refresh_postseason_kinds) or KINDS
        # F2：只抓 plan 判定冷卻已過的賽別（既有 helper 的 kinds 參數，helper 本身不改）。
        kinds = tuple(k for k in configured if k in (state.get("scrape_kinds") or ()))
        if not kinds:
            state["last_run"] = {"at": _iso(now), "action": "scrape", "outcome": "unchanged", "errors": []}
            save_json(path, state)
            print("unchanged")
            return 0
        before = local_signature(year)
        result = _postseason_games_step(year, kinds)
        after = local_signature(year)
        stats_has_c = any(g.get("kind_code") == "C" for g in state.get("schedule") or [])
        local_c = sum(1 for k in load_local_games(year, now) if k.split("-")[1] == "C")
        outcome = record_scrape(state, now, errors=result.get("errors") or [],
                                changed=before != after, stats_has_c=stats_has_c,
                                local_c_rows=local_c, kinds=kinds)
        schedule = [StatsGame(**g) for g in state.get("schedule") or []]
        apply_detection(state, detect_events(schedule, load_local_games(year, now)),
                        now, local_first_seen(year), resolved_by_chain=True,
                        observed_keys=[g.key for g in schedule], chain_kinds=kinds)
        state["last_run"] = {"at": _iso(now), "action": "scrape", "outcome": outcome,
                             "errors": result.get("errors") or []}
        publish_signals(state, year, now)
        save_json(path, state)
        print(outcome)
        return 0

    if args.command == "record-sync":
        outcome = record_sync(state, now, args.code)
        state["last_run"] = {"at": _iso(now), "action": "sync", "outcome": outcome, "code": args.code}
        publish_signals(state, year, now)
        save_json(path, state)
        print(outcome)
        return 0

    # finish
    last = state.get("last_run") or {}
    attempted = last.get("action") in ("scrape", "sync")
    summary = {"finished_at": _iso(now), "last_run": last, "halted": state.get("halted"),
               "www_blocked_at": state.get("www_blocked_at"), "probe_status": state.get("probe_status"),
               "sync_blocked_at": state.get("sync_blocked_at"),
               "needs_owner_decision": state.get("needs_owner_decision"),
               "signals_error": state.get("signals_error"),
               "pending_sync": state.get("pending_sync"), "timeline": timeline(state)}
    save_json(status_path(), summary)
    if attempted:
        ok = not state.get("halted") and last.get("outcome") in ("changed", "unchanged", "synced")
        ok = bool(ok)
        try:
            log_local_refresh(state, ok, None if ok else str(last.get("outcome")))
        except Exception:  # noqa: BLE001 — 本機紀錄失敗不改變結果；狀態檔已寫
            log.exception("本機 refresh_log 寫入失敗")
    print("halted" if state.get("halted") else "ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
