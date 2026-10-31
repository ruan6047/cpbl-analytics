"""#393 WP4：沿 WP3 固定契約逐筆回放，未收錄請求不 fallback 官網。

收件驗證唯一來源是 www_fetch.verify_bundle/read_response；只保留索引，
每次讀取重驗當筆原文，不整包載入。來源為 WP3 10f6f159 的未改動模組。
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from cpbl.ingest import www_fetch

_HEADERS = {"X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}


class ReplayError(RuntimeError):
    """不含原文、token 或表單值的回放錯誤。"""


def _pairs(values: dict) -> tuple:
    return tuple(sorted(values.items()))


class ReplaySession:
    """固定清單的回放入口；index 保留原 HTTP metadata，包括 page 的 null。"""

    def __init__(self, manifest: str | Path, bundle: str | Path) -> None:
        self.bundle = Path(bundle)
        try:
            with Path(manifest).open("rb") as stream:
                raw = stream.read(www_fetch.MAX_INDEX_BYTES + 1)
            self.index = www_fetch.verify_bundle(self.bundle, raw)
            m = www_fetch.parse_manifest(raw)
        except (OSError, ValueError):
            raise ReplayError("清單或 bundle 不合法／缺件") from None
        self._pages, self._posts = {}, {}
        pages = {}
        for req, entry in zip(m["requests"], self.index["entries"], strict=True):
            if req["op"] == "page":
                path = req["path"]
                if path in self._pages and self._identity(self._pages[path][1]) != self._identity(entry):
                    raise ReplayError("同一 page 有不同原文，無法固定回放")
                self._pages[path] = (req, entry)
                pages[req["id"]] = path
            else:
                self._posts.setdefault((pages[req["page"]], req["api"]), []).append((req, entry))

    @staticmethod
    def _identity(entry: dict) -> tuple:
        return entry["sha256"], entry["bytes"], entry["http_status"]

    def _text(self, entry: dict) -> str:
        try:
            return www_fetch.read_response(self.bundle, entry).decode("utf-8")
        except (OSError, ValueError):
            raise ReplayError("原文不合法／缺件／hash 不符") from None

    def page_html(self, page_path: str, wait: str = "networkidle", force: bool = False,
                  require: str | re.Pattern | None = None) -> str:
        # wait／force 是原 session 的導航提示；回放不導航、不重試。
        record = self._pages.get(page_path)
        if record is None:
            raise ReplayError("清單無此 page")
        text = self._text(record[1])
        for pattern in (record[0].get("require"), require):
            if pattern is not None and not re.search(pattern, text):
                raise ReplayError("page 缺必要內容")
        return text

    def _values(self, request: dict, page_path: str) -> tuple[dict, dict]:
        html = self.page_html(page_path)
        values = []
        for field in ("form", "headers"):
            resolved = {}
            for key, value in request.get(field, {}).items():
                if isinstance(value, dict):
                    match = www_fetch.TOKEN_RES[value["$token"]].search(html)
                    if match is None:
                        raise ReplayError("原文缺少指定 token")
                    value = match.group(1)
                resolved[key] = value
            values.append(resolved)
        return values[0], values[1]

    def post(self, page_path: str, api_path: str, form: dict[str, str],
             headers: dict[str, str] | None = None) -> tuple[int | None, str]:
        match = None
        for req, entry in self._posts.get((page_path, api_path), []):
            expected_form, expected_headers = self._values(req, page_path)
            if (form != expected_form
                    or _pairs({**_HEADERS, **(headers or {})}) != _pairs({**_HEADERS, **expected_headers})):
                continue
            if match is not None and self._identity(match) != self._identity(entry):
                raise ReplayError("同一 post 有不同原文，無法固定回放")
            match = entry
        if match is None:
            raise ReplayError("清單無此 post／表單／標頭組合")
        return match["http_status"], self._text(match)

    def close(self) -> None:
        """沒有瀏覽器／連線需要關閉。"""


@lru_cache(maxsize=1)
def replay_session(manifest: str, bundle: str) -> ReplaySession:
    """同一固定路徑共用索引；每筆原文仍逐次驗證，新批次使用新目錄。"""
    return ReplaySession(manifest, bundle)
