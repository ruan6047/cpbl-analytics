"""#393 WP4：固定 manifest/1、bundle/1 的離線回放，不持有網路或 DB 能力。

候選契約：7ac2b0d619d35741d699f82beb768c40102ee389 的
ops/pi-fetcher/cpbl_pi_fetch.py（只沿 JSON／原文契約，不搬 transport）。
一次收齊並驗證後保留記憶體快照；同一請求只回同一原文，未收錄就拒絕。
"""

from __future__ import annotations

import hashlib
import json
import re
import stat
from datetime import datetime
from functools import lru_cache
from pathlib import Path

MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_REQUESTS = 600
_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_PATH = re.compile(r"/(?!/)[A-Za-z0-9/_\-.?=&%]*")
_TOKENS = {
    "A": re.compile(r"RequestVerificationToken:\s*'([^']+)'"),
    "B": re.compile(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"'),
}
_HEADERS = {"X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}


class ReplayError(RuntimeError):
    """收件或請求不合法；訊息不含原文、token 或表單值。"""


def _read(path: Path, limit: int) -> bytes:
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ReplayError("收件必須是一般檔案")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ReplayError("收件超過大小上限")
    return raw


def _pairs(values: dict) -> tuple:
    if not isinstance(values, dict) or any(
        not isinstance(k, str) or not isinstance(v, str) for k, v in values.items()
    ):
        raise ReplayError("表單／標頭必須是字串映射")
    return tuple(sorted(values.items()))


def _resolve(values: dict, html: str) -> dict:
    resolved = {}
    for key, value in values.items():
        if isinstance(value, dict):
            if set(value) != {"$token"} or value["$token"] not in _TOKENS:
                raise ReplayError("token 參照不合法")
            match = _TOKENS[value["$token"]].search(html)
            if match is None:
                raise ReplayError("原文缺少指定 token")
            value = match.group(1)
        resolved[key] = value
    _pairs(resolved)
    return resolved


class ReplaySession:
    """只接受完整且與指定清單 hash 相符的私有 bundle；不落地任何原文。"""

    def __init__(self, manifest: str | Path, bundle: str | Path) -> None:
        self._pages: dict[str, str] = {}
        self._posts: dict[tuple, tuple[int, str]] = {}
        try:
            self._load(Path(manifest), Path(bundle))
        except (OSError, ValueError, TypeError, KeyError, AttributeError, re.error):
            raise ReplayError("清單或 bundle 格式不合法／缺件") from None

    def _load(self, manifest: Path, bundle: Path) -> None:
        raw = _read(manifest, MAX_TOTAL_BYTES)
        m = json.loads(raw)
        if not isinstance(m, dict) or m.get("schema") != "cpbl-www-manifest/1":
            raise ReplayError("manifest schema 不符")
        if not isinstance(m.get("manifest_id"), str) or not _ID.fullmatch(m["manifest_id"]):
            raise ReplayError("manifest_id 不合法")
        requests = m.get("requests")
        cap = m.get("max_requests")
        if (type(cap) is not int or not 1 <= cap <= MAX_REQUESTS
                or not isinstance(requests, list) or not 1 <= len(requests) <= cap):
            raise ReplayError("manifest 請求清單不合法")
        start, end = (datetime.fromisoformat(m["window"][k]) for k in ("start", "end"))
        if start.tzinfo is None or end.tzinfo is None or not start < end:
            raise ReplayError("manifest window 不合法")
        if not isinstance(m.get("min_gap_s"), (int, float)) or not m["min_gap_s"] >= 1.0:
            raise ReplayError("manifest min_gap_s 不合法")
        if not stat.S_ISDIR(bundle.lstat().st_mode) or not stat.S_ISDIR((bundle / "responses").lstat().st_mode):
            raise ReplayError("bundle／responses 必須是實體目錄")
        index = json.loads(_read(bundle / "index.json", MAX_TOTAL_BYTES))
        if (index.get("schema") != "cpbl-www-bundle/1"
                or index.get("manifest_id") != m["manifest_id"]
                or index.get("manifest_sha256") != hashlib.sha256(raw).hexdigest()):
            raise ReplayError("bundle schema／manifest 識別不符")
        entries = index.get("entries")
        if (index.get("complete") is not True or "stopped" not in index or index["stopped"] is not None
                or type(index.get("requests_sent")) is not int or index["requests_sent"] != len(requests)
                or not isinstance(entries, list) or len(entries) != len(requests)):
            raise ReplayError("bundle 未完整取得")
        seen, pages = set(), {}
        total, current_page = 0, None
        for req, entry in zip(requests, entries, strict=True):
            rid = req["id"]
            if not isinstance(rid, str) or not _ID.fullmatch(rid) or rid in seen:
                raise ReplayError("請求 id 不合法或重複")
            seen.add(rid)
            if (entry.get("id") != rid or entry.get("op") != req["op"]
                    or entry.get("http_status") != 200 or entry.get("signal") or entry.get("error")
                    or entry.get("body") != f"responses/{rid}.body"):
                raise ReplayError("回應與清單不符或非成功回應")
            size = entry.get("bytes")
            if type(size) is not int or not 0 <= size <= MAX_BODY_BYTES:
                raise ReplayError("原文大小不合法")
            total += size
            if total > MAX_TOTAL_BYTES:
                raise ReplayError("bundle 超過總大小上限")
            body = _read(bundle / entry["body"], size)
            if len(body) != size or hashlib.sha256(body).hexdigest() != entry.get("sha256"):
                raise ReplayError("原文 bytes／sha256 不符")
            text = body.decode("utf-8")
            if req["op"] == "page":
                path = req["path"]
                if (not isinstance(path, str) or not _PATH.fullmatch(path)
                        or entry.get("path") != path
                        or req.get("wait", "networkidle") not in ("networkidle", "domcontentloaded", "load")
                        or (req.get("require") is not None and not re.search(req["require"], text))):
                    raise ReplayError("page 路徑／必要內容不符")
                self._remember(self._pages, path, text)
                pages[rid] = (path, text)
                current_page = rid
            elif req["op"] == "post":
                if req.get("page") != current_page or current_page is None:
                    raise ReplayError("post 未指向最近的 page")
                path, html = pages[current_page]
                api = req["api"]
                if not isinstance(api, str) or not _PATH.fullmatch(api) or entry.get("api") != api:
                    raise ReplayError("post 路徑不符")
                form = _resolve(req.get("form", {}), html)
                headers = _resolve(req.get("headers", {}), html)
                self._remember(self._posts, self._key(path, api, form, headers), (200, text))
            else:
                raise ReplayError("未知回放操作")

    @staticmethod
    def _remember(mapping: dict, key, value) -> None:
        if key in mapping and mapping[key] != value:
            raise ReplayError("同一請求有不同原文，無法固定回放")
        mapping[key] = value

    @staticmethod
    def _key(page_path: str, api_path: str, form: dict, headers: dict) -> tuple:
        return page_path, api_path, _pairs(form), _pairs({**_HEADERS, **headers})

    def page_html(self, page_path: str, wait: str = "networkidle", force: bool = False,
                  require: str | re.Pattern | None = None) -> str:
        # wait／force 是瀏覽器導航提示；回放快照不導航，也不重試。
        text = self._pages.get(page_path)
        if text is None or (require is not None and not re.search(require, text)):
            raise ReplayError("清單無此 page 或必要內容不符")
        return text

    def post(self, page_path: str, api_path: str, form: dict[str, str],
             headers: dict[str, str] | None = None) -> tuple[int, str]:
        result = self._posts.get(self._key(page_path, api_path, form, headers or {}))
        if result is None:
            raise ReplayError("清單無此 post／表單／標頭組合")
        return result

    def close(self) -> None:
        """沒有瀏覽器／連線需要關閉。"""


@lru_cache(maxsize=1)
def replay_session(manifest: str, bundle: str) -> ReplaySession:
    """同一組固定路徑在程序內共用已驗證快照；換批次須使用新的 bundle 目錄。"""
    return ReplaySession(manifest, bundle)
