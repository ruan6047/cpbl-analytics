"""stats.cpbl 單場資料的 canonical live snapshot 與集中式 polling worker。

本模組先把外部 payload 正規化成 fail-closed contract；網路、cache 與排程於後續 slice
接在同一 contract 上。官方 raw status 未觀測過時一律保留為 ``unknown``。
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx

_STATUS_PHASE = {
    "START": "live",
    "FINISHED": "final",
    "POSTPONED": "postponed",
    "RESERVED": "reserved",
}
_TAIPEI = ZoneInfo("Asia/Taipei")
_BASE = "https://stats.cpbl.com.tw"
_UA = "cpbl-analytics/0.1 (https://cpbl.ruan-ruan.com)"
_RELEASE_LOCK = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""
_LIVELOG_FIELDS = {
    "MainEventNo", "InningSeq", "VisitingHomeType", "BattingOrder", "OutCnt",
    "BallCnt", "StrikeCnt", "PitchCnt", "IsBall", "IsStrike", "Content", "ActionName", "BattingActionName",
    "HitterAcnt", "HitterName", "PitcherAcnt", "PitcherName", "FirstBase", "SecondBase",
    "ThirdBase", "VisitingScore", "HomeScore", "IsChangePlayer", "IsSpecialEvent",
}


def _trackman_snapshot(raw: Any) -> dict[str, Any] | None:
    """保留賽中 UI 必要的官方直接值；缺欄維持 None，絕不推算。"""
    if not isinstance(raw, dict):
        return None
    play = raw.get("Play") if isinstance(raw.get("Play"), dict) else {}
    tag = play.get("PitchTag") if isinstance(play.get("PitchTag"), dict) else {}
    pitch = raw.get("Pitch") if isinstance(raw.get("Pitch"), dict) else {}
    release = pitch.get("Release") if isinstance(pitch.get("Release"), dict) else {}
    location = pitch.get("Location") if isinstance(pitch.get("Location"), dict) else {}
    hit = raw.get("Hit") if isinstance(raw.get("Hit"), dict) else {}
    launch = hit.get("Launch") if isinstance(hit.get("Launch"), dict) else {}
    landing = hit.get("LandingFlat") if isinstance(hit.get("LandingFlat"), dict) else {}
    snapshot = {
        "pitch_call": tag.get("PitchCall"),
        "tagged_pitch_type": tag.get("TaggedPitchType"),
        "rel_speed": release.get("RelSpeed"),
        "plate_loc_side": location.get("PlateLocSide"),
        "plate_loc_height": location.get("PlateLocHeight"),
        "exit_speed": launch.get("ExitSpeed"),
        "launch_angle": launch.get("Angle"),
        "hit_spin_rate": launch.get("HitSpinRate"),
        "hit_distance": landing.get("Distance"),
        "hit_hang_time": landing.get("HangTime"),
    }
    return snapshot if any(value is not None for value in snapshot.values()) else None


class SnapshotCache(Protocol):
    def is_killed(self) -> bool: ...

    def acquire_lock(self) -> bool: ...

    def release_lock(self) -> None: ...

    def get_snapshot(self, year: int, kind: str, sno: int) -> dict | None: ...

    def set_snapshot(self, snapshot: dict) -> None: ...

    def record_source_error(self, year: int, kind: str, sno: int, *,
                            observed_at: datetime, error_type: str) -> None: ...


class RedisLiveGameCache:
    """Redis JSON cache；鎖以 SET NX EX 取得、Lua token compare 後釋放。"""

    def __init__(self, client: Any, *, prefix: str = "cpbl:live",
                 snapshot_ttl_seconds: int = 172_800, lock_ttl_seconds: int = 300,
                 token_factory: Callable[[], str] | None = None) -> None:
        self.client = client
        self.prefix = prefix.rstrip(":")
        self.snapshot_ttl_seconds = snapshot_ttl_seconds
        self.lock_ttl_seconds = lock_ttl_seconds
        self.token_factory = token_factory or (lambda: uuid4().hex)
        self._lock_token: str | None = None

    @property
    def lock_key(self) -> str:
        return f"{self.prefix}:lock"

    def _key(self, year: int, kind: str, sno: int) -> str:
        return f"{self.prefix}:{year}:{kind}:{sno}"

    def _health_key(self, year: int, kind: str, sno: int) -> str:
        return f"{self._key(year, kind, sno)}:health"

    def acquire_lock(self) -> bool:
        token = self.token_factory()
        acquired = bool(self.client.set(
            self.lock_key, token, nx=True, ex=self.lock_ttl_seconds,
        ))
        if acquired:
            self._lock_token = token
        return acquired

    def is_killed(self) -> bool:
        raw = self.client.get(f"{self.prefix}:kill")
        if isinstance(raw, bytes):
            raw = raw.decode()
        return str(raw or "").lower() in {"1", "true", "on"}

    def release_lock(self) -> None:
        if self._lock_token is None:
            return
        self.client.eval(_RELEASE_LOCK, 1, self.lock_key, self._lock_token)
        self._lock_token = None

    def get_snapshot(self, year: int, kind: str, sno: int) -> dict | None:
        raw = self.client.get(self._key(year, kind, sno))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode()
        value = json.loads(raw)
        if not isinstance(value, dict):
            return None
        health_raw = self.client.get(self._health_key(year, kind, sno))
        if health_raw is not None:
            if isinstance(health_raw, bytes):
                health_raw = health_raw.decode()
            health = json.loads(health_raw)
            if isinstance(health, dict):
                value["source"] = {**(value.get("source") or {}), **health}
        return value

    def set_snapshot(self, snapshot: dict) -> None:
        identity = _identity({"GameId": snapshot.get("game_id")})
        if identity is None:
            raise ValueError("snapshot game_id 格式錯誤")
        year, kind, sno = identity
        self.client.set(
            self._key(year, kind, sno),
            json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
            ex=self.snapshot_ttl_seconds,
        )
        self.client.delete(self._health_key(year, kind, sno))

    def record_source_error(self, year: int, kind: str, sno: int, *,
                            observed_at: datetime, error_type: str) -> None:
        self.client.set(
            self._health_key(year, kind, sno),
            json.dumps({
                "last_error_at": _iso(observed_at),
                "last_error_type": error_type,
            }, separators=(",", ":")),
            ex=self.snapshot_ttl_seconds,
        )


class StatsLiveSource:
    """已驗證的 stats schedule + single-game JSON endpoints。"""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(
            base_url=_BASE,
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": _UA},
        )

    def close(self) -> None:
        self.client.close()

    def fetch_schedule(self, year: int, month: int) -> list[dict]:
        response = self.client.get(
            f"{_BASE}/api/proxy/v1/games/schedule",
            params={"kindCode": "A", "year": str(year), "month": str(month)},
        )
        response.raise_for_status()
        games = (response.json().get("Data") or {}).get("Games") or []
        if not isinstance(games, list):
            raise ValueError("stats schedule schema drift: Games 不是 list")
        return games

    def fetch_game(self, game_id: str) -> dict:
        response = self.client.get(f"{_BASE}/api/proxy/v1/games/{game_id}")
        response.raise_for_status()
        game = (response.json().get("Data") or {}).get("Game") or {}
        if not isinstance(game, dict) or not game.get("GameId"):
            raise ValueError("stats single-game schema drift: Game 無識別欄位")
        return game


def _iso(value: datetime) -> str:
    return value.isoformat()


def _int_or_none(value: Any) -> int | None:
    """缺值必須是 None 而非 0——記分板要能區分「沒有資料」與「值為零」。"""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _person(raw: object) -> dict | None:
    """官方 {Acnt, Name[, YearlyCount]} → canonical；缺席或無 Acnt 一律 None。"""
    if not isinstance(raw, dict) or not raw.get("Acnt"):
        return None
    person = {"player_id": raw.get("Acnt"), "name": raw.get("Name")}
    if raw.get("YearlyCount") is not None:
        person["yearly_count"] = _int_or_none(raw.get("YearlyCount"))
    return person


def _team_snapshot(raw: dict, fetched_at: datetime, previous: dict | None) -> dict:
    pitchers = raw.get("Pitchers") if isinstance(raw.get("Pitchers"), list) else []
    # A-226～228 的跨時點觀測證實 Pitchers[] 僅在 START 後出現，屬 box
    # 投手資料，不能倒推為賽前預告先發。真正來源完成 Design Gate 前保持 fail closed。
    probable = {
        "availability": "not_announced",
        "player_id": None,
        "name": None,
        "first_observed_at": None,
    }

    hitters = raw.get("Hitters") if isinstance(raw.get("Hitters"), list) else []
    items = [
        {
            "batting_order": h.get("Lineup"),
            "player_id": h.get("HitterAcnt"),
            "name": h.get("HitterName"),
            "position": h.get("DefendStation"),
        }
        for h in hitters
        if h.get("Lineup") is not None and h.get("HitterAcnt")
    ]
    items.sort(key=lambda row: int(row["batting_order"]))
    orders = {int(row["batting_order"]) for row in items}
    availability = "announced" if set(range(1, 10)) <= orders else (
        "partial" if items else "not_announced"
    )
    lineup_first = None
    if items:
        previous_lineup = (previous or {}).get("lineup") or {}
        lineup_first = previous_lineup.get("first_observed_at") or _iso(fetched_at)

    team = raw.get("Team") if isinstance(raw.get("Team"), dict) else {}
    record = raw.get("AccumulationScore") if isinstance(raw.get("AccumulationScore"), dict) else {}
    return {
        "team": {"code": team.get("Code"), "name": team.get("Name")},
        "score": raw.get("Score"),
        # 隊伍層級 H/E：記分板 R/H/E 欄的唯一來源。stats 站的 InningScore 只有
        # {Seq, Score}，逐局 H/E 只有主站 box/getlive 才有，故本 snapshot 不供逐局值。
        "hits": _int_or_none(raw.get("HittingCnt")),
        "errors": _int_or_none(raw.get("ErrorCnt")),
        "record": {
            "w": _int_or_none(record.get("W")),
            "l": _int_or_none(record.get("L")),
            "t": _int_or_none(record.get("T")),
        },
        "probable_pitcher": probable,
        "lineup": {
            "availability": availability,
            "items": items,
            "first_observed_at": lineup_first,
        },
        "inning_score": raw.get("InningScore") if isinstance(raw.get("InningScore"), list) else [],
        "hitters": hitters,
        "pitchers": pitchers,
    }


def _phase(raw_status: str, away: dict, home: dict) -> str:
    mapped = _STATUS_PHASE.get(raw_status)
    if mapped:
        return mapped
    if raw_status != "SCHEDULED":
        return "unknown"
    if any(side["lineup"]["availability"] != "not_announced" for side in (away, home)):
        return "lineup_announced"
    if any(side["probable_pitcher"]["availability"] == "announced" for side in (away, home)):
        return "probable_announced"
    return "scheduled"


def build_snapshot(raw_game: dict[str, Any], *, fetched_at: datetime,
                   previous: dict | None = None) -> dict[str, Any]:
    """把 stats ``Data.Game`` 轉為前後端共用的 canonical snapshot。"""
    raw_status = str(raw_game.get("GameStatus") or "")
    away = _team_snapshot(
        raw_game.get("Visiting") if isinstance(raw_game.get("Visiting"), dict) else {},
        fetched_at,
        (previous or {}).get("away"),
    )
    home = _team_snapshot(
        raw_game.get("Home") if isinstance(raw_game.get("Home"), dict) else {},
        fetched_at,
        (previous or {}).get("home"),
    )
    raw_livelog = raw_game.get("LiveLog") if isinstance(raw_game.get("LiveLog"), list) else []
    livelog = []
    for event in raw_livelog:
        row = {key: value for key, value in event.items() if key in _LIVELOG_FIELDS}
        row["trackman"] = _trackman_snapshot(event.get("Trackman"))
        livelog.append(row)
    # 只有可呈現的官方直接值才算可用；空 Trackman 物件不能把 UI 誤導成有逐球資料。
    tracked = sum(1 for row in livelog if row["trackman"] is not None)
    phase = _phase(raw_status, away, home)
    previous_count = int((previous or {}).get("event_count") or 0)
    if (
        (previous or {}).get("phase") in {"live", "final"}
        and len(livelog) < previous_count
    ):
        raise ValueError(f"LiveLog regressed from {previous_count} to {len(livelog)}")
    if tracked:
        tracking = "available"
    elif phase in {"live", "final"}:
        tracking = "pending"
    elif phase in {"scheduled", "probable_announced", "lineup_announced"}:
        tracking = "not_announced"
    else:
        tracking = "unknown"

    canonical = json.dumps(raw_game, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "game_id": raw_game.get("GameId"),
        "game_sno": raw_game.get("GameSno"),
        "kind_code": raw_game.get("KindCode"),
        "starts_at": raw_game.get("PreExeDate"),
        "phase": phase,
        "raw_status": raw_status or None,
        "inning": raw_game.get("InningSeq"),
        "half": raw_game.get("VisitingHomeType"),
        "away": away,
        "home": home,
        # 決勝：官方頂層本來就給，缺席時整個為 None（不可用空 dict 冒充「沒有決勝」）。
        "decisions": {
            "winning_pitcher": _person(raw_game.get("WinningPitcher")),
            "losing_pitcher": _person(raw_game.get("LoserPitcher")),
            "closer": _person(raw_game.get("Closer")),
            "mvp": _person(raw_game.get("MVP")),
        },
        "venue": (raw_game.get("Field") or {}).get("Abbe")
        if isinstance(raw_game.get("Field"), dict) else None,
        "umpires": [
            {"job": u.get("Job"), "name": u.get("Name")}
            for u in (raw_game.get("Referee") or [])
            if isinstance(u, dict) and u.get("Name")
        ],
        # 官方權威的球場設備旗標；不再由 tracking_count 推測球場有無 TrackMan。
        "skip_trackman": raw_game.get("SkipTrackman"),
        "livelog": livelog,
        "event_count": len(livelog),
        "tracking_count": tracked,
        "tracking_availability": tracking,
        "source": {
            "fetched_at": _iso(fetched_at),
            "version": hashlib.sha256(canonical.encode()).hexdigest(),
        },
    }


def _starts_at(row: dict) -> datetime | None:
    raw = row.get("PreExeDate")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return parsed.replace(tzinfo=_TAIPEI) if parsed.tzinfo is None else parsed


def _identity(row: dict) -> tuple[int, str, int] | None:
    game_id = str(row.get("GameId") or "")
    parts = game_id.split("-")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), parts[1], int(parts[2])
    except ValueError:
        return None


def _select_candidates(rows: list[dict], now: datetime) -> list[dict]:
    local_now = now.astimezone(_TAIPEI)
    lower, upper = local_now - timedelta(hours=8), local_now + timedelta(hours=30)
    latest: dict[tuple[int, str, int], dict] = {}
    for row in sorted(rows, key=lambda item: str(item.get("PreExeDate") or "")):
        identity, starts = _identity(row), _starts_at(row)
        if identity is None or starts is None or not lower <= starts <= upper:
            continue
        latest[identity] = row
    return list(latest.values())


def poll_interval_seconds(*, now: datetime, phases: set[str],
                          next_start: datetime | None) -> int:
    """回傳無 jitter 的 base interval；CLI loop 再加 bounded jitter。"""
    if "live" in phases:
        return 12
    if next_start is not None:
        delta = next_start - now
        if delta <= timedelta(minutes=90):
            return 60
        if delta <= timedelta(hours=30):
            return 600
    return 1800


def next_delay_seconds(result: dict, *, failures: int,
                       jitter: Callable[[], float]) -> int:
    """將 cycle result 轉成 sleep；正常 bounded jitter，錯誤指數退避至 5 分鐘。"""
    state = result.get("state")
    if state == "ok":
        base = int(result.get("next_poll_seconds") or 1800)
        return max(1, round(base * min(1.1, max(0.9, jitter()))))
    if state == "locked":
        return 5
    return min(300, 5 * (2 ** max(0, failures - 1)))


class LiveGameWorker:
    """單 cycle worker；loop／sleep 與 Redis 實作保持在 I/O adapter。"""

    def __init__(
        self,
        *,
        cache: SnapshotCache,
        fetch_schedule: Callable[[int, int], list[dict]],
        fetch_game: Callable[[str], dict],
        enabled: bool = True,
        max_games_per_cycle: int = 8,
    ) -> None:
        self.cache = cache
        self.fetch_schedule = fetch_schedule
        self.fetch_game = fetch_game
        self.enabled = enabled
        self.max_games_per_cycle = max_games_per_cycle

    def run_cycle(self, now: datetime) -> dict[str, Any]:
        if not self.enabled:
            return {"state": "disabled"}
        if self.cache.is_killed():
            return {"state": "killed"}
        if not self.cache.acquire_lock():
            return {"state": "locked"}

        try:
            local = now.astimezone(_TAIPEI)
            month_keys = {(local.year, local.month)}
            edge = local + timedelta(hours=30)
            month_keys.add((edge.year, edge.month))
            schedule_rows = [
                row
                for year, month in sorted(month_keys)
                for row in self.fetch_schedule(year, month)
            ]
            selected = _select_candidates(schedule_rows, now)[: self.max_games_per_cycle]
            phases: Counter[str] = Counter()
            game_summaries: list[dict[str, Any]] = []
            cached = errors = skipped_final = 0
            starts: list[datetime] = []
            for row in selected:
                identity = _identity(row)
                starts_at = _starts_at(row)
                if identity is None:
                    continue
                if starts_at is not None:
                    starts.append(starts_at.astimezone(now.tzinfo))
                year, kind, sno = identity
                game_id = f"{year}-{kind}-{sno}"
                try:
                    previous = self.cache.get_snapshot(year, kind, sno)
                    if (previous or {}).get("phase") == "final":
                        skipped_final += 1
                        phases["final"] += 1
                        continue
                    raw_game = self.fetch_game(game_id)
                    snapshot = build_snapshot(
                        raw_game,
                        fetched_at=now,
                        previous=previous,
                    )
                    self.cache.set_snapshot(snapshot)
                except (OSError, ValueError, httpx.HTTPError) as exc:
                    self.cache.record_source_error(
                        year, kind, sno,
                        observed_at=now,
                        error_type=type(exc).__name__,
                    )
                    errors += 1
                    continue
                cached += 1
                phases[snapshot["phase"]] += 1
                game_summaries.append({
                    "game_id": snapshot["game_id"],
                    "phase": snapshot["phase"],
                    "raw_status": snapshot["raw_status"],
                    "away_probable": snapshot["away"]["probable_pitcher"]["availability"],
                    "home_probable": snapshot["home"]["probable_pitcher"]["availability"],
                    "away_lineup": snapshot["away"]["lineup"]["availability"],
                    "home_lineup": snapshot["home"]["lineup"]["availability"],
                    "event_count": snapshot["event_count"],
                    "tracking_count": snapshot["tracking_count"],
                })
            next_start = min((start for start in starts if start >= now), default=None)
            return {
                "state": "ok",
                "selected": len(selected),
                "cached": cached,
                "errors": errors,
                "skipped_final": skipped_final,
                "phases": dict(phases),
                "games": game_summaries,
                "next_poll_seconds": poll_interval_seconds(
                    now=now, phases=set(phases), next_start=next_start,
                ),
            }
        finally:
            self.cache.release_lock()
