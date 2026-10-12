"""本機同owner有限公告：真觀測先落有限佇列，既有refresh lock與保護同步。"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from cpbl.ingest.lineup_announcements import observe_projected, project


class AnnouncementOwner:
    def __init__(self, repo: Path, *, lock: Path | None = None, clock=time.time, runner=subprocess.run):
        self.repo = repo
        self.lock = lock or Path(os.getenv("REFRESH_LOCK_DIR", "/private/tmp/cpbl-analytics-refresh.lock"))
        self.path = repo / "logs/lineup-announcements/owner.json"
        self.clock, self.runner = clock, runner
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {
            "pending": [], "new_version": False, "last_seen": False,
            "last_sync": 0, "next_attempt": 0, "next_flush": 0, "failures": 0, "paused": False,
        }
        if self.state["paused"]:
            raise RuntimeError("announcement owner paused; require verified owner handoff")

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(dir=self.path.parent, prefix="owner-", suffix=".tmp")
        temp = Path(temp_name)
        with os.fdopen(fd, "w") as f:
            json.dump(self.state, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        temp.replace(self.path)

    @contextmanager
    def _writer(self):
        try:
            self.lock.mkdir(mode=0o700)
        except FileExistsError:
            yield False
            return
        marker = self.lock / "pid"
        marker.write_text(str(os.getpid()))
        (self.lock / "kind").write_text("lineup-announcements")
        try:
            yield True
        finally:
            # 逾時遠端結果未知時保留既有互斥，不能僅client退出就宣稱remote已停。
            if not self.state["paused"] and marker.read_text() == str(os.getpid()):
                marker.unlink()
                (self.lock / "kind").unlink()
                self.lock.rmdir()

    def observe(self, game_id: str, raw: dict, fetched_at: datetime):
        payload = project(game_id, raw)
        if fetched_at.tzinfo is None:
            raise ValueError("announcement observation must be timezone aware")
        self.state["pending"].append({"game_id": game_id, "payload": payload,
                                      "fetched_at": fetched_at.isoformat()})
        self._save()
        return {"action": "queued"}

    def after_cycle(self):
        now = self.clock()
        if now < self.state.get("next_flush", 0):
            return {"state": "deferred", "reason": "persistence_backoff"}
        if not self.state["pending"] and (now < self.state["next_attempt"] or not (
                self.state["new_version"] or self.state["last_seen"] and now-self.state["last_sync"] >= 21600)):
            return {"state": "idle", "pending": 0}
        with self._writer() as acquired:
            if not acquired:
                return {"state": "deferred", "reason": "refresh_lock", "pending": len(self.state["pending"])}
            # 對齊既有max8選場：每cycle最多8個短交易，保原觀測順序，不逐筆重型備份。
            for _ in range(min(8, len(self.state["pending"]))):
                event = self.state["pending"][0]
                try:
                    result = observe_projected(event["game_id"], event["payload"], datetime.fromisoformat(event["fetched_at"]))
                except ValueError:
                    self.state["paused"] = True
                    self._save()
                    raise  # 時序／不可變原證不符須owner核對，不反覆重試。
                except Exception as exc:  # noqa: BLE001 — 保留真觀測，下一正常cycle退避。
                    self.state["next_flush"] = now + 300
                    self._save()
                    return {"state": "persistence_failed", "error_type": type(exc).__name__}
                self.state["next_flush"] = 0
                self.state["new_version"] |= result["action"] in ("inserted", "replayed")
                self.state["last_seen"] |= result["action"] == "seen"
                self.state["pending"].pop(0)
                self._save()  # 每commit立即checkpoint；重播同自然鍵不造新的取得時間。
            now = self.clock()
            # 新內容／status合併至少5分鐘；單純last_seen最多6小時一次。
            due = (self.state["new_version"] or
                   self.state["last_seen"] and now - self.state["last_sync"] >= 21600)
            if not due or now < self.state["next_attempt"]:
                return {"state": "idle", "pending": len(self.state["pending"])}
            try:
                log_path = self.path.parent / f"sync-{int(now)}-{os.getpid()}.log"
                with os.fdopen(os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as log_file:
                    result = self.runner([str(self.repo / "scripts/refresh-cpbl-prod.sh")],
                                         cwd=self.repo, env={**os.environ, "LINEUP_ONLY": "1", "SKIP_SCRAPE": "1"},
                                         stdout=log_file, stderr=subprocess.STDOUT, timeout=1200, check=False)
            except subprocess.TimeoutExpired:
                self.state["paused"] = True
                self._save()
                raise RuntimeError("announcement sync timeout; remote stop must be verified") from None
            if result.returncode in (255, 130, 137, 143, -9, -15):
                self.state["paused"] = True
                self._save()
                raise RuntimeError("announcement sync connection/termination unknown; require remote stop verification")
            if result.returncode:
                self.state["failures"] += 1
                self.state["next_attempt"] = now + min(21600, 300 * 2 ** min(self.state["failures"], 6))
                self._save()
                return {"state": "sync_failed", "exit": result.returncode}
            self.state.update(new_version=False, last_seen=False, last_sync=now,
                              next_attempt=now + 300, failures=0)
            self._save()
            return {"state": "synced", "exit": 0}
