#!/usr/bin/env python3
# #342 驗收重播引擎（tests/ 內的輔助模組，非 pytest 收集檔）；不連網、不碰 DB、不寫 logs/（只寫 --out 指定的報告）
"""#342 先發觀察窗重播：用本機修訂表匯出的**真實** getgamedatas payload，以模擬時鐘驅動真的晚間鏈 CLI。

驗收（#342 Issue body）：
1. 官網公布 → 正式站顯示先發 ≤ 1 小時（重播證據）。
2. 個別場次超時要有可見告警、事後補上（重播證明告警與補上機制會觸發）。

做法
----
* 素材＝``tests/fixtures/starter_watch_replay/revisions-2026.json``（本機 ``cpbl.game_schedule_status_revisions``
  2026 A／E／C 唯讀匯出）：每場取一筆真實「賽前、無先發」payload（E）與一筆真實「賽前、有先發」payload（X）。
  開賽時刻 S＝X 的 ``PreExeDate``。⛔ 不手寫 payload；兩版之間的切換時刻 P（官網公布時刻）未知，所以掃描。
* 每次喚醒照 ``scripts/postseason-evening.sh`` 的次序呼叫**真的** ``postseason_evening.main()``：
  ``plan`` →（鎖）→ ``scrape`` →（changed 時）同步 → ``record-sync`` → ``finish``。換掉的只有外部 I/O：
  時鐘、stats（以 S 建 SCHEDULED 列）、www（回傳 t 時已公布的那版真實 payload）、本機 DB（記憶體表；
  只寫先發的判斷仍是真的 :func:`starter_watch.starter_rows`）、同步（耗時取晚間鏈 log 實測最大值）、通知（記錄）。
* 公布時刻掃描：P 從開窗到關窗每 5 分一點。偵測時刻只取決於「未公布時的抓取時間軸」，故每場先跑一次
  「從未公布」的完整模擬取時間軸，再對每個 P 算延遲；另對每場抽樣數個 P 跑**完整**模擬，核對兩種算法
  的延遲逐筆相等（``equivalence``）。
* 故障注入 F1–F5（驗收 2）與「不寫比分」變異檢驗另見 :func:`run_faults`、``tests/test_starter_watch_replay.py``。

證明不了：官網真實公布時刻分布（只掃描）、HiNet 對每 30 分一次的真實反應、真實網路與備份速度、
Mac 睡眠頻率、多場同賽別互相影響（每場單獨模擬）、正式站前端實際快取（以 120 秒計）。

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
import sys
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
STEP = timedelta(minutes=5)                   # P 掃描步長
LIMIT = timedelta(minutes=60)


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

    @property
    def window(self) -> tuple[datetime, datetime]:
        from cpbl.ingest import starter_watch as sw
        return sw.window(self.starts)


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
                          empties[-1]["raw_payload"], pub["raw_payload"]))
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
    """把晚間鏈的外部 I/O 換成 :class:`World`；其餘（plan、閘門、先發觀察窗、寫入判斷、告警）都是真的碼。"""
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
            key = f"{y}-{kind}-{sno}"
            cur = world.local.setdefault(key, [None, None])
            new = [home or cur[0], away or cur[1]]     # 同 _STARTER_SQL 的 COALESCE（只補不清）
            updated += 1
            world.local[key] = new
        for e in revs:
            world.revisions.add(canonical_source_version(e))
        return {"games_updated": updated, "revisions": len(revs)}

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
            and now.astimezone(TAIPEI).date() <= g.starts.date() <= (now + timedelta(hours=33)).astimezone(TAIPEI).date()
            else set()),
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
             until: datetime | None = None, setup=None) -> tuple[World, dict]:
    """從開窗前 10 分到 ``until``（預設：正式站有先發後 30 分，或關窗）逐次喚醒。回 (世界, 狀態檔)。"""
    from cpbl.ingest import postseason_evening as pe

    rng = random.Random(seed)
    opens, closes = game.window
    world = World(game, publish_at, noise, now=opens - timedelta(minutes=10))
    from cpbl.ingest.game_source_revisions import canonical_source_version
    world.revisions.add(canonical_source_version(game.empty))   # J1 早已記過的「無先發」版（同 payload 不算變化）
    day = opens.astimezone(TAIPEI).replace(hour=0, minute=0, second=0, microsecond=0)
    for d in range(-1, 4):
        start = day + timedelta(days=d) + J1_LOCK[0]
        world.lock_busy.append((start, start + J1_LOCK[1]))
    if setup:
        setup(world)
    end = until or closes
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        with patched(world, tmp):
            while world.now < end:
                if not world.sleeping():
                    wake(world, tmp)
                if until is None and world.prod_at and world.now >= world.prod_at + timedelta(minutes=30):
                    break
                world.now += WAKE + timedelta(seconds=rng.randint(0, 30))
            state = pe.load_state(tmp / "state.json")
    return world, state


def _alert_windows(state: Mapping, key: str, now: datetime) -> list[tuple[datetime, datetime, str]]:
    rec = ((state.get("starter_watch") or {}).get("games") or {}).get(key) or {}
    out = [(_ts(a["since"]), _ts(a["until"]), a["reason"]) for a in rec.get("alerts") or []]
    if rec.get("alert"):
        out.append((_ts(rec["alert"]["since"]), now, rec["alert"]["reason"]))
    return out


def sweep(game: Game, noise: list[dict], *, seed: int = 0) -> dict:
    """「從未公布」完整模擬取抓取時間軸，對開窗到關窗每 5 分的 P 算延遲與告警可見性。"""
    world, state = simulate(game, None, noise, seed=seed)
    opens, closes = game.window
    ok_fetches = sorted(t for t, _path, ok in world.fetch_log if ok)
    alerts = _alert_windows(state, game.key, closes)
    points = []
    p = opens
    while p < closes:
        detect = next((t for t in ok_fetches if t >= p), None)
        if detect is None:
            points.append({"p": p.isoformat(), "detected": None})
        else:
            visible = detect + timedelta(seconds=SYNC_SECONDS) + FRONT_CACHE
            latency = (visible - p).total_seconds() / 60
            alert = next((a for a in alerts if a[0] <= p + LIMIT and a[1] > p), None)
            points.append({"p": p.isoformat(), "detected": detect.isoformat(), "latency_min": round(latency, 2),
                           "alert_by_limit": alert is not None and alert[0] <= p + LIMIT,
                           "alert_reason": alert[2] if alert else None})
        p += STEP
    return {"key": game.key, "starts": game.starts.isoformat(), "window": [opens.isoformat(), closes.isoformat()],
            "fetches_ok": len(ok_fetches), "fetches_failed": sum(1 for _t, _p, ok in world.fetch_log if not ok),
            "alerts": [[a.isoformat(), b.isoformat(), r] for a, b, r in alerts],
            "notifications": len(world.notifications), "points": points}


def full_check(game: Game, noise: list[dict], publish_at: datetime, *, seed: int = 0) -> dict:
    """完整模擬：官網在 ``publish_at`` 換成真實有先發 payload，量正式站實際出現先發的時刻。"""
    world, state = simulate(game, publish_at, noise, seed=seed)
    visible = world.prod_at + FRONT_CACHE if world.prod_at else None
    rec = ((state.get("starter_watch") or {}).get("games") or {}).get(game.key) or {}
    return {"p": publish_at.isoformat(), "prod_at": world.prod_at.isoformat() if world.prod_at else None,
            "latency_min": round((visible - publish_at).total_seconds() / 60, 2) if visible else None,
            "prod_starters": world.prod.get(game.key), "expected": [game.published.get("HomePitcherAcnt"),
                                                                     game.published.get("VisitingPitcherAcnt")],
            "synced_at": rec.get("synced_at"), "local_at": rec.get("local_at")}


def summarize(sweeps: list[dict]) -> dict:
    active, late = [], []
    for s in sweeps:
        for pt in s["points"]:
            if pt.get("detected") is None:
                late.append({"key": s["key"], **pt, "class": "undetected_before_close"})
                continue
            if pt["latency_min"] <= 60:
                active.append(pt["latency_min"])
            else:
                late.append({"key": s["key"], **pt,
                             "class": "late_with_alert" if pt["alert_by_limit"] else "late_without_alert"})
    by_class: dict[str, int] = {}
    for x in late:
        by_class[x["class"]] = by_class.get(x["class"], 0) + 1
    return {"points": sum(len(s["points"]) for s in sweeps), "within_60": len(active),
            "max_latency_within": max(active) if active else None, "late": by_class,
            "late_without_alert": [x for x in late if x["class"] == "late_without_alert"],
            "undetected_before_close": [x for x in late if x["class"] == "undetected_before_close"]}


# =========================================================================== 故障注入（驗收 2）

def run_faults(game: Game, noise: list[dict]) -> dict:
    """F1–F5：每案看「告警出現 → 通知 → 條件解除 → 補上（正式站有先發）→ 告警清除」。"""
    opens, closes = game.window
    # 公布時刻固定在開窗後第一個白天 14:00（非暫停時段），讓故障落在公布之後
    day = opens.astimezone(TAIPEI)
    p = day.replace(hour=14, minute=0, second=0, microsecond=0)
    if p < opens:
        p += timedelta(days=1)
    cases = {
        "F1_challenge": lambda w: setattr(w, "challenge", (p, p + timedelta(minutes=95))),
        "F2_lock_60m": lambda w: w.lock_busy.append((p, p + timedelta(minutes=60))),
        "F3_sleep_2h": lambda w: w.asleep.append((p, p + timedelta(hours=2))),
        "F4_sync_68": lambda w: w.sync_codes.extend([68]),
        "F5_backup_fail": lambda w: (w.sync_codes.extend([66]),
                                     setattr(w, "clear_halt_after", timedelta(minutes=50))),
    }
    out = {}
    for name, setup in cases.items():
        world, state = simulate(game, p, noise, setup=setup, until=closes)
        rec = ((state.get("starter_watch") or {}).get("games") or {}).get(game.key) or {}
        out[name] = {"publish_at": p.isoformat(),
                     "prod_at": world.prod_at.isoformat() if world.prod_at else None,
                     "latency_min": round((world.prod_at + FRONT_CACHE - p).total_seconds() / 60, 2)
                     if world.prod_at else None,
                     "alerts": rec.get("alerts") or [], "alert_open_at_end": rec.get("alert"),
                     "notifications": [[t.isoformat(), title, msg] for t, title, msg in world.notifications],
                     "halted_at_end": state.get("halted"), "www_blocked_at": state.get("www_blocked_at"),
                     "sync_blocked_at": state.get("sync_blocked_at")}
    return out


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--samples", type=int, default=4, help="每場完整模擬抽樣的 P 個數（等價核對）")
    args = ap.parse_args(list(argv) if argv is not None else None)
    games, noise, meta = load_games()
    sweeps, equivalence = [], []
    rng = random.Random(342)
    for game in games:
        s = sweep(game, noise)
        sweeps.append(s)
        detected = [pt for pt in s["points"] if pt.get("detected")]
        worst = max(detected, key=lambda pt: pt["latency_min"]) if detected else None
        picks = {pt["p"] for pt in rng.sample(detected, min(args.samples, len(detected)))}
        if worst:
            picks.add(worst["p"])
        for raw in sorted(picks):
            full = full_check(game, noise, datetime.fromisoformat(raw))
            want = next(pt for pt in s["points"] if pt["p"] == raw)
            equivalence.append({"key": game.key, **full, "sweep_latency_min": want["latency_min"],
                                "equal": full["latency_min"] == want["latency_min"]
                                and full["prod_starters"] == full["expected"]})
        print(f"{game.key} points={len(s['points'])} fetches={s['fetches_ok']}", file=sys.stderr)
    fault_game = next(g for g in games if g.kind == "A")
    report = {"generated_at": datetime.now(UTC).isoformat(), "fixture": meta,
              "params": {"wake_seconds": WAKE.total_seconds(), "wake_jitter_seconds": [0, 30],
                         "sync_seconds": SYNC_SECONDS, "front_cache_seconds": FRONT_CACHE.total_seconds(),
                         "j1_lock": ["10:10", J1_LOCK[1].total_seconds() / 60], "p_step_min": 5},
              "games": len(games), "summary": summarize(sweeps),
              "equivalence": {"checked": len(equivalence), "all_equal": all(e["equal"] for e in equivalence),
                              "rows": equivalence},
              "faults": {"game": fault_game.key, "cases": run_faults(fault_game, noise)},
              "sweeps": sweeps}
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("games", "summary")} | {"equivalence_all_equal":
                     report["equivalence"]["all_equal"]}, ensure_ascii=False, default=str)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
