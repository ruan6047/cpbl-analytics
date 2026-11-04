"""#393 VPS端：原manifest/1逐批供給與相符新包回放；不做傳輸或排程。"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import math
import os
import stat
import tempfile
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cpbl.ingest import www_fetch
from cpbl.ingest._replay import ReplayError, ReplaySession

WWW_JOBS = {"scrape-daily", "postseason-evening", "weekly-box-revisions"}
_ACTIVE = contextvars.ContextVar("cpbl_job_source", default=None)
_TOKEN_FOR_API = {
    "/team/getfightingoptsaction": "getSelectOpts",
    "/team/getfightingscore": "getFightingScore",
    "/team/getfighterscore": "getFighterScore",
    "/team/getapartscore": "getApartScore",
}


def _root(variable):
    value = Path(os.environ.get(variable, ""))
    if not value.is_absolute() or value.resolve() != value or not value.is_dir():
        raise ReplayError("source_root_required")
    return value


class JobSource:
    """一個既有工作的供給上下文；初次WWW呼叫才讀設定或落檔。"""

    def __init__(self, job, state):
        self.job, self.state = job, state
        self.prefix = f"{job}-{uuid.uuid4().hex[:20]}"
        self.failed = False
        self.backend = None

    def session(self):
        if self.failed:
            raise ReplayError("source_stopped")
        try:
            if self.backend is None:
                self.backend = SourceSession(self)
            return self.backend
        except Exception:
            self.failed = True
            raise ReplayError("source_configuration") from None


@contextlib.contextmanager
def job_source(job, state):
    source = JobSource(job, state)
    token = _ACTIVE.set(source if job in WWW_JOBS else None)
    try:
        yield source
    finally:
        try:
            if source.backend is not None:
                source.backend.close()
        finally:
            _ACTIVE.reset(token)


def active_session():
    source = _ACTIVE.get()
    if source is None:
        raise ReplayError("jobs_requires_source_context")
    return source.session()


def reject_fixed_replay():
    source = _ACTIVE.get()
    if source is not None:
        source.failed = True
    raise ReplayError("scheduled jobs 不得以固定包冒新供給")


class SourceSession:
    """只接原session的page/post；每批等收條及完整性gate才回傳原文。"""

    def __init__(self, source):
        self.source = source
        self.requests = _root("CPBL_JOBS_REQUESTS_ROOT")
        self.inbox = _root("CPBL_JOBS_INBOX_ROOT")
        info = self.requests.stat()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o2750:
            raise ReplayError("request_export_owner_or_mode")
        self.originals = source.state / "source"
        if self.originals.is_symlink():
            raise ReplayError("private_source_root")
        self.originals.mkdir(mode=0o700, exist_ok=True)
        for other in (source.state.resolve(), self.inbox):
            if self.requests.is_relative_to(other) or other.is_relative_to(self.requests):
                raise ReplayError("independent_source_roots_required")
        if self.inbox.is_relative_to(source.state.resolve()) or source.state.resolve().is_relative_to(self.inbox):
            raise ReplayError("independent_source_roots_required")
        self.max_ops = int(os.environ["CPBL_JOBS_SOURCE_MAX_OPERATIONS"])
        budget = float(os.environ["CPBL_JOBS_SOURCE_MAX_SECONDS"])
        if not 1 <= self.max_ops <= 600 or not math.isfinite(budget) or budget <= 10:
            raise ReplayError("source_budget_required")
        self.deadline = time.monotonic() + budget
        self.window_end = datetime.now(UTC) + timedelta(seconds=budget)
        self.operations, self.batch, self.pages = 0, 0, {}
        self.exported = None

    def _fetch(self, requests):
        if self.source.failed:
            raise ReplayError("source_stopped")
        try:
            remaining = self.deadline - time.monotonic()
            if remaining <= 10 or self.operations + len(requests) > self.max_ops:
                raise ReplayError("source_budget_exhausted")
            self.batch += 1
            run_id = f"{self.source.prefix}-{self.batch:04d}"
            manifest = {
                "schema": www_fetch.MANIFEST_SCHEMA, "manifest_id": run_id,
                "window": {"start": datetime.now(UTC).isoformat(),
                           "end": self.window_end.isoformat()},
                "min_gap_s": 1.0, "max_requests": len(requests),
                "max_duration_s": min(300, remaining - 10), "requests": requests,
            }
            raw = (json.dumps(manifest, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
            www_fetch.parse_manifest(raw)
            folder = self.originals / run_id
            folder.mkdir(mode=0o700)  # 新id只建一次，從不覆原件或續跑失敗批。
            original = folder / "manifest.json"
            with original.open("xb") as stream:
                stream.write(raw)
            original.chmod(0o600)
            self.operations += len(requests)
            fd, temp = tempfile.mkstemp(prefix=f".{self.source.job}-", dir=self.requests)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(raw); stream.flush(); os.fsync(stream.fileno())
                    os.fchmod(stream.fileno(), 0o640)
                os.replace(temp, self.requests / f"{self.source.job}.json")
                info = (self.requests / f"{self.source.job}.json").stat()
                self.exported = (info.st_dev, info.st_ino, www_fetch.digest(raw))
            finally:
                Path(temp).unlink(missing_ok=True)
            bundle = self.inbox / "incoming" / run_id
            receipt = bundle / "delivery.json"
            while not receipt.exists():
                if time.monotonic() >= self.deadline:
                    raise ReplayError("source_delivery_timeout")
                time.sleep(min(1.0, self.deadline - time.monotonic()))
            # 完成收條由可信sender在raw native wait/rc0之後發布；不是server不可變保證。
            if receipt.is_symlink() or bundle.resolve() != bundle or receipt.stat().st_size > 4096:
                raise ReplayError("source_delivery_receipt")
            with receipt.open("rb") as stream:
                receipt_raw = stream.read(4097)
            if len(receipt_raw) > 4096:
                raise ReplayError("source_delivery_receipt")
            delivered = www_fetch._json(receipt_raw)
            if (not isinstance(delivered, dict)
                    or set(delivered) != {"manifest_id", "manifest_sha256", "index_sha256",
                                          "raw_batch_rc", "raw_batch_waited"}
                    or delivered["manifest_id"] != run_id
                    or delivered["manifest_sha256"] != www_fetch.digest(raw)
                    or type(delivered["raw_batch_rc"]) is not int or delivered["raw_batch_rc"] != 0
                    or delivered["raw_batch_waited"] is not True):
                raise ReplayError("source_delivery_receipt")
            index_path = bundle / "index.json"
            if index_path.is_symlink():
                raise ReplayError("source_index_symlink")
            with index_path.open("rb") as stream:
                index_raw = stream.read(www_fetch.MAX_INDEX_BYTES + 1)
            if (len(index_raw) > www_fetch.MAX_INDEX_BYTES
                    or hashlib.sha256(index_raw).hexdigest() != delivered["index_sha256"]):
                raise ReplayError("source_index_hash")
            replay = ReplaySession(original, bundle)  # 沿既有整包verify與逐筆read_response。
            with index_path.open("rb") as stream:
                if stream.read(www_fetch.MAX_INDEX_BYTES + 1) != index_raw:
                    raise ReplayError("source_index_changed")
            if time.monotonic() >= self.deadline:
                raise ReplayError("source_delivery_timeout")
            return replay
        except Exception:
            self.source.failed = True
            raise ReplayError("source_batch_failed") from None

    def page_html(self, page_path, wait="networkidle", force=False, require=None):
        try:
            if self.source.failed:
                raise ReplayError("source_stopped")
            pattern = require.pattern if hasattr(require, "pattern") else require
            key = (page_path, wait, pattern)
            if force or page_path not in self.pages or self.pages[page_path][0] != key:
                page = {"id": "p1", "op": "page", "path": page_path, "wait": wait}
                if pattern is not None:
                    page["require"] = pattern
                self.pages[page_path] = (key, page, self._fetch([page]))
            return self.pages[page_path][2].page_html(page_path, require=require)
        except Exception:
            self.source.failed = True
            raise ReplayError("source_page_failed") from None

    def _symbolic(self, values, html, api):
        result = {}
        preferred = _TOKEN_FOR_API.get(api)
        for key, value in values.items():
            if key.lower() not in www_fetch.TOKEN_KEYS:
                result[key] = value
                continue
            names = [preferred] if preferred else ["B", "A"]
            for name in names:
                regex = www_fetch.TOKEN_RES.get(name)
                match = regex.search(html) if regex is not None else None
                if match and match.group(1) == value:
                    result[key] = {"$token": name}
                    break
            else:
                raise ReplayError("unsupported_source_token")
        return result

    def post(self, page_path, api_path, form, headers=None):
        try:
            if self.source.failed or page_path not in self.pages:
                raise ReplayError("source_page_required")
            _, page, old = self.pages[page_path]
            html = old.page_html(page_path)
            request = {"id": "q1", "op": "post", "page": "p1", "api": api_path,
                       "form": self._symbolic(form, html, api_path),
                       "headers": self._symbolic(headers or {}, html, api_path)}
            replay = self._fetch([page, request])
            # 新manifest在Pi重新取得page；用該頁token解析原符號，不送caller的過期literal。
            resolved_form, resolved_headers = replay._values(request, page_path)
            return replay.post(page_path, api_path, resolved_form, resolved_headers)
        except Exception:
            self.source.failed = True
            raise ReplayError("source_post_failed") from None

    def close(self):
        self.pages.clear()  # 不刪原件或代清理sender傳輸。
        if self.exported is not None:
            path = self.requests / f"{self.source.job}.json"
            if path.is_symlink():
                raise ReplayError("source_export_owner_changed")
            if not path.exists():
                return
            info = path.stat()
            with path.open("rb") as stream:
                raw = stream.read(www_fetch.MAX_INDEX_BYTES + 1)
            if (info.st_dev, info.st_ino, www_fetch.digest(raw)) != self.exported:
                raise ReplayError("source_export_owner_changed")
            path.unlink()  # job仍持writer鎖；只撤自身最後出口，Pi已開始的傳輸仍由原owner結清。
