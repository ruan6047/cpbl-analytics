#!/usr/bin/env python3
# #342 驗收重播引擎（tests/ 內的輔助模組，非 pytest 收集檔）；不連網、不碰 DB、不寫 logs/（只寫 --out 指定的報告）
"""#342 先發 23:00 時點重播：用本機修訂表匯出的**真實** getgamedatas payload，以模擬時鐘驅動真的晚間鏈 CLI。

驗收（#342 Issue body，6405678916）：
* 每場比賽前一天 23:00 晚間鏈固定抓官網一次、只更新先發投手並同步正式站；改期依新賽程自動跟上。
* 抓取失敗或先發仍空時有本機可見通知，並於下一個既有時點（隔日 10:10 每日鏈）補上。
* 以本機修訂表既有公布紀錄重播證明 23:00 時點會抓到並寫入。

做法
----
* 素材＝``tests/fixtures/starter_watch_replay/revisions-2026.json``（本機 ``cpbl.game_schedule_status_revisions``
  2026 A／E／C 唯讀匯出）：每場取一筆真實「賽前、無先發」payload（E）與一筆真實「賽前、有先發」payload（X）。
  開賽時刻 S＝X 的 ``PreExeDate``；F＝S 前一天 23:00。⛔ 不手寫 payload。
* 每次喚醒照 ``scripts/postseason-evening.sh`` 的次序呼叫**真的** ``postseason_evening.main()``：
  ``plan`` →（鎖）→ ``scrape`` →（changed 時）同步 → ``record-sync`` → ``finish``。換掉的只有外部 I/O：
  時鐘、stats（以 S 建 SCHEDULED 列）、www（公布時刻後回 X、之前回 E）、本機 DB（記憶體表；只寫先發的判斷仍是
  真的 :func:`starter_watch.starter_rows`）、同步（耗時取晚間鏈 log 實測最大值）、通知（記錄）。
* 一般情境：官網依慣例前一天公布（23:00 前已是 X）。故障情境：挑戰（抓取失敗）、仍空（官網未公布）、
  23:00–01:00 鎖被占（沒抓成）、同步 68。

證明不了：官網真實公布時刻（只有本機首見時刻；``real_first_seen_*`` 只是並列）、HiNet 反應、真實網路與備份速度、
Mac 睡眠、正式站前端實際快取（以 120 秒計）。隔日 10:10 每日鏈補上是既有路徑，本重播不模擬。

用法::

    uv run python tests/starter_watch_replay_harness.py --out ~/.wf-evidence/cpbl-analytics/342/exec-1/replay.json
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import logging
import os
import random
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "starter_watch_replay" / "revisions-2026.json"
WAKE = timedelta(seconds=300)                 # launchd StartInterval 300
SYNC_SECONDS = 203                            # 晚間鏈 log 實測 RESULTS_ONLY 同步耗時最大值（n=11，2026-10）
FRONT_CACHE = timedelta(seconds=120)          # 前端 revalidate（PLAN 研究 1，讀碼）
J1_LOCK = (timedelta(hours=10, minutes=10), timedelta(minutes=21))   # 10:10 起，持鎖時長中位數（n=56）


def _ts(raw: str) -> datetime:
    at = datetime.fromisoformat(raw)
    return at if at.tzinfo else at.replace(tzinfo=UTC)


def _result(p: Mapping) -> str:
    return str(p.get("GameResult") if p.get("GameResult") is not None else "")


def _pregame(p: Mapping) -> bool:
    return _result(p) == "" and not (int(p.get("HomeScore") or 0) or int(p.get("VisitingScore") or 0))


def _has_starters(p: Mapping) -> bool:
    return bool(p.get("HomePitcherAcnt")) and bool(p.get("VisitingPitcherAcnt"))


@dataclass
class Game:
    key: str
    kind: str
    sno: int
    starts: datetime
    empty: dict          # 真實賽前、無先發 payload
    published: dict      # 真實賽前、有先發 payload
    published_seen: str  # 本機首見 X 的 fetched_at（本機觀測，不是官方公布時刻）

    @property
    def fire(self) -> datetime:
        from cpbl.ingest import starter_watch as sw
        return sw.fire_point(self.starts)


def load_games(path: Path = FIXTURE) -> tuple[list[Game], list[dict], dict]:
    """fixture → (重播場次, 其他真實 payload（已開打／保留，混進每次 www 回應）, 中繼資料)。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    by_key: dict[str, list[dict]] = {}
    for row in data["rows"]:
        by_key.setdefault(f"{row['year']}-{row['kind_code']}-{row['game_sno']}", []).append(row)
    games, noise = [], []
    for key, rows in sorted(by_key.items()):
        rows.sort(key=lambda r: r["fetched_at"])
        pub = next((r for r in rows if _pregame(r["raw_payload"]) and _has_starters(r["raw_payload"])), None)
        empties = [r for r in rows if _pregame(r["raw_payload"]) and not _has_starters(r["raw_payload"])
                   and (pub is None or r["fetched_at"] <= pub["fetched_at"])]
        if pub is None or not empties:
            noise.extend(r["raw_payload"] for r in rows)
            continue
        starts = datetime.fromisoformat(pub["raw_payload"]["PreExeDate"]).replace(tzinfo=TAIPEI)
        games.append(Game(key, rows[0]["kind_code"], rows[0]["game_sno"], starts,
                          empties[-1]["raw_payload"], pub["raw_payload"], pub["fetched_at"]))
    meta = {k: v for k, v in data.items() if k != "rows"}
    meta["rows"] = len(data["rows"])
    meta["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return games, noise, meta


# =========================================================================== 世界（外部 I/O 替身）

@dataclass
class World:
    game: Game
    publish_at: datetime | None               # None＝整個窗口都沒公布
    noise: list[dict]
    now: datetime = field(default_factory=lambda: datetime.now(UTC))
    local: dict[str, list[str | None]] = field(default_factory=dict)   # key → [home, away]（本機 games）
    revisions: set[str] = field(default_factory=set)
    prod: dict[str, list[str | None]] = field(default_factory=dict)
    prod_at: datetime | None = None
    fetch_log: list[tuple[datetime, str, bool]] = field(default_factory=list)   # (時刻, 路徑, 成功)
    notifications: list[tuple[datetime, str, str]] = field(default_factory=list)
    # 故障注入
    challenge: tuple[datetime, datetime] | None = None   # F1：此區間 www 回挑戰錯誤
    lock_busy: list[tuple[datetime, datetime]] = field(default_factory=list)   # F2（＋每日 J1）
    asleep: list[tuple[datetime, datetime]] = field(default_factory=list)      # F3
    sync_codes: list[int] = field(default_factory=list)                       # F4／F5：依序回這些碼
    clear_halt_after: timedelta | None = None   # F5：人工清除 halted 的延遲
    halted_since: datetime | None = None

    def payload(self, kind: str) -> list[dict]:
        out = [dict(p) for p in self.noise if p.get("KindCode") == kind]
        if self.game.kind == kind:
            pub = self.publish_at is not None and self.now >= self.publish_at
            out.append(dict(self.game.published if pub else self.game.empty))
        return out

    def fetch(self, year: int, kind: str) -> list[dict]:
        if self.challenge and self.challenge[0] <= self.now < self.challenge[1]:
            self.fetch_log.append((self.now, "watch", False))
            raise RuntimeError("反爬挑戰未過（REDIRECT 迴圈）")
        self.fetch_log.append((self.now, "watch", True))
        return self.payload(kind)

    def locked(self) -> bool:
        return any(a <= self.now < b for a, b in self.lock_busy)

    def sleeping(self) -> bool:
        return any(a <= self.now < b for a, b in self.asleep)


def _signature(world: World) -> str:
    return hashlib.sha256(repr((sorted(world.local.items()), sorted(world.revisions))).encode()).hexdigest()


@contextlib.contextmanager
def patched(world: World, tmp: Path):
    """把晚間鏈的外部 I/O 換成 :class:`World`；其餘（plan、閘門、先發 23:00 時點、寫入判斷、通知）都是真的碼。"""
    from cpbl.ingest import cpbl_site
    from cpbl.ingest import postseason_evening as pe
    from cpbl.ingest import starter_watch as sw
    from cpbl.ingest.game_source_revisions import canonical_source_version

    g = world.game

    def stats_probe(year, months, *, kinds=pe.EVENING_KINDS, fetch=None, timeout=10.0):
        rows = [] if g.kind not in kinds else [pe.StatsGame(
            year=2026, kind_code=g.kind, game_sno=g.sno, status="SCHEDULED",
            starts_at=g.starts.strftime("%Y-%m-%dT%H:%M:%S"), game_date=g.starts.date().isoformat(),
            away_code=g.published.get("VisitingTeamCode"), home_code=g.published.get("HomeTeamCode"),
            venue=g.published.get("FieldAbbe"))]
        return pe.ProbeRows(rows, all_rows=rows)

    def load_local_games(year, now, kinds=None):
        return {g.key: pe.LocalGame(2026, g.kind, g.sno, g.starts.date().isoformat(),
                                    g.published.get("VisitingTeamCode"), g.published.get("HomeTeamCode"),
                                    g.published.get("FieldAbbe"), False)}

    def write_starters(games, keys):
        rows, revs = sw.starter_rows(games, keys)
        updated = 0
        for home, away, y, kind, _season, sno in rows:
            world.local[f"{y}-{kind}-{sno}"] = [home, away]     # 同 _STARTER_SQL：設成目前賽前 entry 的值
            updated += 1
        for e in revs:
            world.revisions.add(canonical_source_version(e))
        found = sorted(f"{y}-{k}-{sno}" for home, away, y, k, _s, sno in rows if home and away)
        return {"games_updated": updated, "revisions": len(revs), "with_starters": found}

    def evening_games_step(year, kinds):   # 既有路徑（事件／#292 時點）：比照 upsert_games 也會寫先發
        out: dict[str, Any] = {"games": {}, "errors": []}
        for kind in kinds:
            try:
                games = world.fetch(year, kind)
            except RuntimeError as exc:
                out["errors"].append({"kind": kind, "error": str(exc)})
                continue
            world.fetch_log[-1] = (world.now, "regular", True)
            for e in games:
                key = f"{e.get('Year')}-{e.get('KindCode')}-{e.get('GameSno')}"
                if key == g.key and _pregame(e) and (e.get("HomePitcherAcnt") or e.get("VisitingPitcherAcnt")):
                    world.local[key] = [e.get("HomePitcherAcnt") or None, e.get("VisitingPitcherAcnt") or None]
                world.revisions.add(canonical_source_version(e))
            out["games"][kind] = len(games)
        return out

    saved = {}
    patches = {
        (pe, "_now"): lambda: world.now,
        (pe, "stats_probe"): stats_probe,
        (pe, "load_local_games"): load_local_games,
        (pe, "local_first_seen"): lambda year, kinds=None: {},
        (pe, "local_signature"): lambda year, kinds=None: _signature(world),
        (pe, "local_www_starts"): lambda year, kinds=None: {},
        (pe, "local_scheduled_kinds"): lambda night, kinds=None: set(),
        (pe, "local_watch_kinds"): lambda now, kinds=None: (
            {g.kind} if not all(world.local.get(g.key) or [None, None])
            and sw.fire_game_date(now) == g.starts.astimezone(TAIPEI).date() else set()),
        (pe, "publish_signals"): lambda state, year, now: None,
        (pe, "log_local_refresh"): lambda state, ok, note: None,
        (pe, "evening_games_step"): evening_games_step,
        (pe, "marking_scrape_games"): lambda state, year: contextlib.nullcontext(),
        (sw, "write_starters"): write_starters,
        (sw, "local_starters"): lambda year, keys: {k for k in keys if all(world.local.get(k) or [None, None])},
        (sw, "_schedule_watch_notify"): lambda title, msg: (world.notifications.append((world.now, title, msg))
                                                           or {"attempted": True, "replay": True}),
        (cpbl_site, "fetch_year"): world.fetch,
    }
    env = {"POSTSEASON_STATE": str(tmp / "state.json"), "POSTSEASON_STATUS": str(tmp / "status.json"),
           "POSTSEASON_STARTER_WATCH_FLAG": str(tmp / "starter-watch.enabled"),
           "POSTSEASON_STARTER_WATCH_ALERT": str(tmp / "starter-watch-alert.json"),
           "POSTSEASON_STARTER_FLAG": str(tmp / "no-starter-checkpoints.enabled"),
           "POSTSEASON_TODAY_SCHEDULE": str(tmp / "no-today-schedule.json"),
           "POSTSEASON_YEAR": "2026", "POSTSEASON_EVENING_KINDS": "", "POSTSEASON_TM_RECHECK_MIN": ""}
    (tmp / "starter-watch.enabled").write_text("", encoding="utf-8")
    old_env = {k: os.environ.get(k) for k in env}
    logging.disable(logging.CRITICAL)
    try:
        for (mod, name), fn in patches.items():
            saved[(mod, name)] = getattr(mod, name)
            setattr(mod, name, fn)
        os.environ.update(env)
        yield
    finally:
        logging.disable(logging.NOTSET)
        for (mod, name), fn in saved.items():
            setattr(mod, name, fn)
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _cli(*argv: str) -> str:
    from cpbl.ingest import postseason_evening as pe

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        code = pe.main(list(argv))
    if code != 0:
        raise RuntimeError(f"{argv} exit {code}")
    return buf.getvalue().strip().splitlines()[-1] if buf.getvalue().strip() else ""


def wake(world: World, tmp: Path) -> None:
    """一次 launchd 喚醒，次序同 ``scripts/postseason-evening.sh``（⛔ 不跑 box／PA 階段：與先發無關）。"""
    from cpbl.ingest import postseason_evening as pe

    if world.halted_since and world.clear_halt_after and world.now >= world.halted_since + world.clear_halt_after:
        state = pe.load_state(tmp / "state.json")      # F5：人工清除 halted（Runbook §10 回復程序）
        state["halted"] = None
        pe.save_json(tmp / "state.json", state)
        world.halted_since = None
    action = _cli("plan")
    if action in ("quiet", "idle", "halted"):
        return
    if world.locked():
        return                                         # shell：refresh lock busy → exit 75（plan 已寫狀態）
    sync = False
    if action == "scrape":
        sync = _cli("scrape") == "changed" or _cli("sync-due") == "signals"
    elif action == "sync":
        sync = True
    if sync:
        # 故障只注入在公布之後的同步（之前的同步與本卡無關）
        due = world.sync_codes and world.publish_at is not None and world.now >= world.publish_at
        code = world.sync_codes.pop(0) if due else 0
        world.now += timedelta(seconds=SYNC_SECONDS)
        if code == 0:
            world.prod = {k: list(v) for k, v in world.local.items()}
            if all(world.prod.get(world.game.key) or [None, None]) and world.prod_at is None:
                world.prod_at = world.now
        recorded = _cli("record-sync", "--code", str(code))
        if recorded == "halted":
            world.halted_since = world.now
    _cli("finish")


def simulate(game: Game, publish_at: datetime | None, noise: list[dict], *, seed: int = 0,
             setup=None) -> tuple[World, dict]:
    """從 F−20 分到 F＋3 小時逐次喚醒（F＝開賽前一天 23:00）。回 (世界, 狀態檔)。"""
    from cpbl.ingest import postseason_evening as pe
    from cpbl.ingest.game_source_revisions import canonical_source_version

    rng = random.Random(seed)
    fire = game.fire
    world = World(game, publish_at, noise, now=fire - timedelta(minutes=20))
    world.revisions.add(canonical_source_version(game.empty))   # J1 早已記過的「無先發」版（同 payload 不算變化）
    if setup:
        setup(world)
    end = fire + timedelta(hours=3)
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        with patched(world, tmp):
            while world.now < end:
                if not world.sleeping():
                    wake(world, tmp)
                world.now += WAKE + timedelta(seconds=rng.randint(0, 30))
            state = pe.load_state(tmp / "state.json")
    return world, state


def _rec(state: Mapping, key: str) -> dict:
    return ((state.get("starter_watch") or {}).get("games") or {}).get(key) or {}


def normal(game: Game, noise: list[dict], *, seed: int = 0, publish_at: datetime | None = None) -> dict:
    """23:00 抓一次、寫入、同步。``publish_at``＝www 開始回「有先發」版的時刻；預設＝假設情境 F−1 分。"""
    publish_at = publish_at or game.fire - timedelta(minutes=1)
    world, state = simulate(game, publish_at, noise, seed=seed)
    rec = _rec(state, game.key)
    visible = world.prod_at + FRONT_CACHE if world.prod_at else None
    return {"key": game.key, "starts": game.starts.isoformat(), "fire": game.fire.isoformat(),
            "state": rec.get("state"), "attempted_at": rec.get("attempted_at"), "synced_at": rec.get("synced_at"),
            "www_fetches": len(world.fetch_log),
            "prod_starters": world.prod.get(game.key),
            "expected": [game.published.get("HomePitcherAcnt"), game.published.get("VisitingPitcherAcnt")],
            "minutes_from_fire_to_visible": round((visible - game.fire).total_seconds() / 60, 2) if visible else None,
            "notifications": len(world.notifications), "publish_at": publish_at.isoformat(),
            "real_first_seen_with_starters": game.published_seen,
            "real_first_seen_before_fire": _ts(game.published_seen) <= game.fire}


def run_faults(game: Game, noise: list[dict]) -> dict:
    """抓取失敗（挑戰）、先發仍空、23:00–01:00 被鎖占（沒抓成）、同步 68：每案都要有一則本機通知，並記補上路徑。"""
    fire = game.fire
    cases = {
        "challenge": (fire - timedelta(minutes=1), lambda w: setattr(w, "challenge", (fire, fire + timedelta(hours=3)))),
        "still_empty": (None, None),
        "lock_until_0100": (fire - timedelta(minutes=1),
                            lambda w: w.lock_busy.append((fire - timedelta(minutes=5), fire + timedelta(hours=2)))),
        "sync_68": (fire - timedelta(minutes=1), lambda w: w.sync_codes.extend([68])),
    }
    out = {}
    for name, (publish_at, setup) in cases.items():
        world, state = simulate(game, publish_at, noise, setup=setup)
        rec = _rec(state, game.key)
        out[name] = {"state": rec.get("state"), "wait": rec.get("wait"), "notified_at": rec.get("notified_at"),
                     "www_fetches": len(world.fetch_log), "prod_starters": world.prod.get(game.key),
                     "notifications": [[t.isoformat(), title, msg] for t, title, msg in world.notifications]}
    return out


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    args = ap.parse_args(list(argv) if argv is not None else None)
    games, noise, meta = load_games()

    def section(rows: list[dict]) -> dict:
        ok = [r for r in rows if r["state"] == "fetched" and r["synced_at"] and r["prod_starters"] == r["expected"]]
        lat = [r["minutes_from_fire_to_visible"] for r in ok]
        return {"games": len(rows), "fetched_written_synced": len(ok),
                "not_ok": [r["key"] for r in rows if r not in ok],
                "max_minutes_fire_to_visible": max(lat) if lat else None,
                "min_minutes_fire_to_visible": min(lat) if lat else None,
                "www_fetches_per_game": sorted({r["www_fetches"] for r in rows}),
                "notifications": sum(r["notifications"] for r in rows),
                "by_kind": {k: sum(1 for r in ok if r["key"].split("-")[1] == k) for k in "AEC"},
                "keys": [r["key"] for r in rows]}

    # 歷史可證子集（審核 review-1 重播判定）：本機首見「賽前、有先發」的真實時刻 ≤ F 的場——www 自那個真實時刻起
    # 回有先發版（真實公布時刻只會更早，所以是保守情境）。其餘場次真實公布時刻未知。
    proven = [g for g in games if _ts(g.published_seen) <= g.fire]
    hist = [normal(g, noise, seed=i, publish_at=_ts(g.published_seen)) for i, g in enumerate(proven)]
    # 假設情境：假設 F−1 分已公布（條件式行為，⛔ 不是 117 場歷史上都能在該時點抓到的證據）。
    rows = [normal(g, noise, seed=i) for i, g in enumerate(games)]
    fault_games = [next(g for g in games if g.kind == "A"), next(g for g in games if g.kind == "C")]
    report = {"generated_at": datetime.now(UTC).isoformat(), "fixture": meta,
              "params": {"wake_seconds": WAKE.total_seconds(), "wake_jitter_seconds": [0, 30],
                         "sync_seconds": SYNC_SECONDS, "front_cache_seconds": FRONT_CACHE.total_seconds()},
              "games": len(games),
              "historical_provable": section(hist),
              "hypothetical_published_at_f_minus_1": section(rows),
              "unknown_publication_time": len(games) - len(proven),
              "faults": {g.key: run_faults(g, noise) for g in fault_games},
              "rows_historical": hist, "rows_hypothetical": rows}
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("games", "historical_provable", "hypothetical_published_at_f_minus_1",
                                              "unknown_publication_time")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
