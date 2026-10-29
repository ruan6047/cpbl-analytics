"""#393 WP3：樹莓派 www 取源器（住宅出口代取 www.cpbl.com.tw 原始回應）。

定位（PLAN §2.1 P1）：VPS 產生請求清單（manifest），樹莓派依清單用 Chromium 取回**原始回應**，
連同 sha256 打包成 bundle，送進 VPS 收件匣；VPS 以回放 session 餵給既有解析／寫入程式。
樹莓派⛔ 沒有 DB 憑證、⛔ 不解析、⛔ 不寫 DB——構造上不可能成為第二個 writer。

依賴：只用標準庫＋Playwright（arm64）。⛔ 不 import 本 repo 任何模組（樹莓派上不裝 cpbl）。

爬蟲紅線（#382 PLAN §3、docs/CPBL_SITE_MAP.md）：
- 單線：上一個回應回來才送下一個；請求「開始到開始」間隔 ≥ manifest.min_gap_s（下限 1.0 s）。
- **⛔ 不重試**：S1–S6 任一前兆出現＝本 run 立即停，不再送任何 www 請求、不重載、不換 context。
  這與 repo 內 ``_browser.py`` 的自癒重試**刻意不同**：取源器無人值守，第一格就停才不會把節流打深。
- 只在 manifest 的時段窗內送請求；窗外＝拒跑（不等待）。
- 不記 token 值、cookie；log 只放中繼資料。回應原文只進 bundle（VPS 收件匣要的就是原文）。

manifest（JSON，schema ``cpbl-www-manifest/1``）::

    {"schema": "cpbl-www-manifest/1", "manifest_id": "20261030-daily-a1b2",
     "window": {"start": "2026-10-30T13:00:00+08:00", "end": "2026-10-30T14:00:00+08:00"},
     "min_gap_s": 1.0, "max_requests": 50,
     "requests": [
       {"id": "p1", "op": "page", "path": "/schedule", "wait": "networkidle",
        "require": "RequestVerificationToken:\\s*'([^']+)'"},
       {"id": "q1", "op": "post", "page": "p1", "api": "/schedule/getgamedatas",
        "form": {"calendar": "2026/01/01", "location": "", "kindCode": "A"},
        "headers": {"RequestVerificationToken": {"$token": "A"}}}]}

- ``op=page``：導頁取 HTML；``require``（regex）不中＝S1（挑戰頁未過）。
- ``op=post``：在 ``page`` 指向的 page 請求所載入的頁面 context 內 in-page fetch POST（同 ``_browser.post``）。
  form／headers 的值可為 ``{"$token": "A"|"B"}``：取該頁 HTML 的 A 型（inline header token）／
  B 型（hidden input）token。``page`` 必須是**最近一個** page 請求（不交錯導頁：回放端
  ``_browser`` 的 token 取自該頁第一次載入的 HTML，交錯導頁會讓 token 與頁面 context 對不上）。

bundle（目錄 ``<out>/<manifest_id>/``）：``index.json``（schema ``cpbl-www-bundle/1``）＋
``responses/<id>.body``（原文 UTF-8）。index 每列含 sha256／bytes，VPS 收件匣以此驗證。
停止（前兆、超量、窗外）時照樣寫出 index，``stopped`` 標明原因與停在哪個請求；已取得的回應保留。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import socket
import statistics
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode

FETCHER_VERSION = "393-wp3.1"
MANIFEST_SCHEMA = "cpbl-www-manifest/1"
BUNDLE_SCHEMA = "cpbl-www-bundle/1"
BASE = "https://www.cpbl.com.tw"
TZ = dt.timezone(dt.timedelta(hours=8))

MIN_GAP_FLOOR_S = 1.0          # #393 PLAN §8：≥1 s；manifest 不得低於此值
MAX_REQUESTS_CEILING = 600     # PLAN §8 WP6：單段 ≤600
MAX_BODY_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
NAV_TIMEOUT_MS = 45_000

# #382 PLAN §3 S6
S6_SINGLE_MS = 10_000
S6_BASE_N, S6_RECENT_N, S6_RATIO = 50, 20, 2.0

# SITE_MAP §3：A＝inline header-token、B＝hidden-input
TOKEN_RES = {
    "A": re.compile(r"RequestVerificationToken:\s*'([^']+)'"),
    "B": re.compile(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"'),
}
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
# 只收同站絕對路徑；"//host/x" 是 protocol-relative，in-page fetch 會打到別站，必須擋。
PATH_RE = re.compile(r"^/(?!/)[A-Za-z0-9/_\-.?=&%]*$")
WAITS = ("networkidle", "domcontentloaded", "load")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# _browser._JS_POST 加上 redirect:'manual'（#382 S3 要看得到轉址）
JS_POST = """async ({path, headers, body}) => {
  try { const r = await fetch(path, {method:'POST', headers, body, credentials:'include',
                                     redirect:'manual'});
        return {status: r.status, type: r.type, redirected: r.redirected, text: await r.text()}; }
  catch (e) { return {status: -1, type: 'error', redirected: false, text: String(e)}; } }"""


class ManifestError(ValueError):
    """清單不合法：一個請求都不送。"""


# =========================================================================== manifest 驗證

def _check_value(v: Any, where: str) -> None:
    if isinstance(v, str):
        return
    if isinstance(v, dict) and set(v) == {"$token"} and v["$token"] in TOKEN_RES:
        return
    raise ManifestError(f"{where}：值只能是字串或 {{\"$token\": \"A\"|\"B\"}}")


def validate_manifest(m: Any) -> dict:
    """驗證清單形狀；不合法拋 ManifestError。回傳原物件（不改寫）。"""
    if not isinstance(m, dict) or m.get("schema") != MANIFEST_SCHEMA:
        raise ManifestError(f"schema 必須是 {MANIFEST_SCHEMA}")
    mid = m.get("manifest_id")
    if not isinstance(mid, str) or not ID_RE.match(mid):
        raise ManifestError("manifest_id 不合法")
    w = m.get("window") or {}
    try:
        ws = dt.datetime.fromisoformat(w["start"])
        we = dt.datetime.fromisoformat(w["end"])
    except (KeyError, TypeError, ValueError) as e:
        raise ManifestError(f"window 不合法：{e}") from e
    if ws.tzinfo is None or we.tzinfo is None or not ws < we:
        raise ManifestError("window 需含時區且 start < end")
    gap = m.get("min_gap_s")
    if not isinstance(gap, (int, float)) or gap < MIN_GAP_FLOOR_S:
        raise ManifestError(f"min_gap_s 必須 ≥ {MIN_GAP_FLOOR_S}")
    cap = m.get("max_requests")
    if not isinstance(cap, int) or not 1 <= cap <= MAX_REQUESTS_CEILING:
        raise ManifestError(f"max_requests 必須在 1..{MAX_REQUESTS_CEILING}")
    reqs = m.get("requests")
    if not isinstance(reqs, list) or not reqs:
        raise ManifestError("requests 必須是非空 list")
    if len(reqs) > cap:
        raise ManifestError(f"requests {len(reqs)} 筆超過 max_requests {cap}")
    seen: dict[str, str] = {}
    last_page: str | None = None
    for i, r in enumerate(reqs):
        where = f"requests[{i}]"
        if not isinstance(r, dict):
            raise ManifestError(f"{where} 不是物件")
        rid = r.get("id")
        if not isinstance(rid, str) or not ID_RE.match(rid) or rid in seen:
            raise ManifestError(f"{where}.id 不合法或重複")
        op = r.get("op")
        if op == "page":
            if not isinstance(r.get("path"), str) or not PATH_RE.match(r["path"]):
                raise ManifestError(f"{where}.path 不合法")
            if r.get("wait", "networkidle") not in WAITS:
                raise ManifestError(f"{where}.wait 不合法")
            req = r.get("require")
            if req is not None:
                if not isinstance(req, str):
                    raise ManifestError(f"{where}.require 必須是字串")
                try:
                    re.compile(req)
                except re.error as e:
                    raise ManifestError(f"{where}.require 不是合法 regex：{e}") from e
        elif op == "post":
            if r.get("page") is None or r.get("page") != last_page:
                raise ManifestError(f"{where}.page 必須指向最近一個 page 請求")
            if not isinstance(r.get("api"), str) or not PATH_RE.match(r["api"]):
                raise ManifestError(f"{where}.api 不合法")
            for key in ("form", "headers"):
                d = r.get(key, {})
                if not isinstance(d, dict):
                    raise ManifestError(f"{where}.{key} 必須是物件")
                for k, v in d.items():
                    if not isinstance(k, str):
                        raise ManifestError(f"{where}.{key} 鍵必須是字串")
                    _check_value(v, f"{where}.{key}.{k}")
        else:
            raise ManifestError(f"{where}.op 只接受 page／post")
        seen[rid] = op
        if op == "page":
            last_page = rid
    return m


def manifest_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


# =========================================================================== 前兆判定（純函式）

def judge_nav(rec: dict, base: dict | None) -> str | None:
    """#382 PLAN §3 的導頁判定。base＝本 run 第一次導頁（自己就是第一次時為 None）。"""
    if rec.get("error"):
        return "S3:goto_error " + str(rec["error"])[:120]
    if rec.get("http_status") != 200:
        return f"S5:nav_status={rec.get('http_status')}"
    if not rec.get("require_ok"):
        return "S1:require_missing"
    if base is None:
        if rec.get("redirects", 0) > 2:
            return f"S3:redirects={rec['redirects']}>2(first)"
        return None
    if rec.get("redirects", 0) > base.get("redirects", 0):
        return f"S3:redirects={rec['redirects']}>base={base.get('redirects')}"
    if rec.get("path") == base.get("path") and (
            (rec.get("token_a"), rec.get("token_b")) != (base.get("token_a"), base.get("token_b"))):
        # S4 快取頁變體：同一頁的 token 型態組合與本 run 第一次不同。不同頁本來就可能不同，不比。
        return (f"S4:token_combo A={rec.get('token_a')},B={rec.get('token_b')} "
                f"!= base A={base.get('token_a')},B={base.get('token_b')}")
    return None


def judge_post(rec: dict, ms_history: list[int]) -> str | None:
    """#382 PLAN §3 的 POST 判定。ms_history＝本 run 已完成 POST 的 ms（不含本筆）。"""
    st = rec.get("http_status")
    if st in (-1, 428):
        return f"S2:fetch_status={st}"
    if rec.get("redirected") or rec.get("resp_type") != "basic":
        return f"S3:post_redirected={rec.get('redirected')} type={rec.get('resp_type')}"
    if st != 200:
        return f"S5:post_status={st}"
    if not rec.get("json_ok"):
        return "S5:non_json"
    ms = rec.get("ms") or 0
    if ms > S6_SINGLE_MS:
        return f"S6:single_ms={ms}>{S6_SINGLE_MS}"
    hist = [*ms_history, ms]
    if len(hist) >= S6_BASE_N + S6_RECENT_N:
        base_med = statistics.median(hist[:S6_BASE_N])
        rec_med = statistics.median(hist[-S6_RECENT_N:])
        if rec_med > base_med * S6_RATIO:
            return f"S6:recent20_median={rec_med}>2x_base50_median={base_med}"
    return None


def _json_ok(text: str) -> bool:
    try:
        json.loads(text)
    except (ValueError, TypeError):
        return False
    return True


# =========================================================================== 瀏覽器驅動

class Driver(Protocol):
    def goto(self, path: str, wait: str) -> dict:
        """回 {"http_status", "redirects", "html", "error"}；error 非 None 時其餘可缺。"""
        ...

    def post(self, api: str, headers: dict[str, str], body: str) -> dict:
        """回 {"status", "type", "redirected", "text"}（同 JS_POST）。"""
        ...

    def close(self) -> None: ...


class PlaywrightDriver:
    """單一 browser、單一 context、單一 page；⛔ 不換 context、不重載（前兆即停）。"""

    def __init__(self, headed: bool = False) -> None:
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=not headed, args=["--disable-blink-features=AutomationControlled"])
        self._ctx = self._browser.new_context(locale="zh-TW", user_agent=UA)
        self._page = self._ctx.new_page()

    def goto(self, path: str, wait: str) -> dict:
        from playwright.sync_api import Error
        try:
            res = self._page.goto(f"{BASE}{path}", wait_until=wait, timeout=NAV_TIMEOUT_MS)
        except Error as e:
            return {"error": str(e)}
        redirects = 0
        req = res.request if res is not None else None
        while req is not None and req.redirected_from is not None:
            redirects += 1
            req = req.redirected_from
        self._page.wait_for_timeout(1500 if wait == "networkidle" else 400)
        return {"http_status": res.status if res is not None else None,
                "redirects": redirects, "html": self._page.content(), "error": None}

    def post(self, api: str, headers: dict[str, str], body: str) -> dict:
        return self._page.evaluate(JS_POST, {"path": api, "headers": headers, "body": body})

    def close(self) -> None:
        try:
            self._browser.close()
            self._pw.stop()
        except Exception:  # noqa: BLE001 — 關閉容錯
            pass


# =========================================================================== 執行

def _resolve(d: dict, html: str) -> tuple[dict[str, str], str | None]:
    """把 {"$token": X} 換成該頁 HTML 的 token 值。缺 token 回 (…, 型態) 讓呼叫端判 S1。"""
    out: dict[str, str] = {}
    for k, v in d.items():
        if isinstance(v, dict):
            m = TOKEN_RES[v["$token"]].search(html)
            if not m:
                return out, v["$token"]
            out[k] = m.group(1)
        else:
            out[k] = v
    return out, None


class Run:
    def __init__(self, manifest: dict, manifest_raw_sha: str, out_dir: Path, driver: Driver, *,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep,
                 now: Callable[[], dt.datetime] = lambda: dt.datetime.now(TZ),
                 log: Callable[[dict], None] = lambda rec: None) -> None:
        self.m = manifest
        self.sha = manifest_raw_sha
        self.dir = out_dir / manifest["manifest_id"]
        self.driver = driver
        self.clock, self.sleep, self.now, self.log = clock, sleep, now, log
        self.entries: list[dict] = []
        self.stopped: dict | None = None
        self.sent = 0
        self.total_bytes = 0
        self.base_nav: dict | None = None
        self.post_ms: list[int] = []
        self.page_html: dict[str, str] = {}      # page 請求 id → 該次取得的 HTML
        self.current_page: str | None = None     # 目前停在哪個 page 請求 id
        self._last_start: float | None = None
        self.window = (dt.datetime.fromisoformat(manifest["window"]["start"]),
                       dt.datetime.fromisoformat(manifest["window"]["end"]))

    # ---- 共用閘門：每送一個 www 請求前都要過
    def _gate(self, rid: str) -> bool:
        if self.stopped:
            return False
        if self.sent >= self.m["max_requests"]:
            self._stop("cap:max_requests", rid)
            return False
        t = self.now()
        if not self.window[0] <= t < self.window[1]:
            self._stop(f"window:outside now={t.isoformat(timespec='seconds')}", rid)
            return False
        if self._last_start is not None:
            wait = self.m["min_gap_s"] - (self.clock() - self._last_start)
            if wait > 0:
                self.sleep(wait)
        self._last_start = self.clock()
        self.sent += 1
        return True

    def _stop(self, signal: str, rid: str) -> None:
        self.stopped = {"signal": signal, "at": rid, "ts": self.now().isoformat(timespec="seconds")}
        self.log({"stop": self.stopped})

    def _store(self, rid: str, text: str) -> dict | None:
        raw = text.encode("utf-8")
        if len(raw) > MAX_BODY_BYTES:
            self._stop(f"size:body {len(raw)}>{MAX_BODY_BYTES}", rid)
            return None
        if self.total_bytes + len(raw) > MAX_TOTAL_BYTES:
            self._stop(f"size:total>{MAX_TOTAL_BYTES}", rid)
            return None
        self.total_bytes += len(raw)
        rel = f"responses/{rid}.body"
        (self.dir / rel).write_bytes(raw)
        return {"body": rel, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

    def _nav(self, page_req: dict) -> bool:
        """導頁並判前兆；成功回 True 並記住 HTML。"""
        rid = page_req["id"]
        if not self._gate(rid):
            return False
        t0 = self.clock()
        at = self.now().isoformat(timespec="seconds")
        res = self.driver.goto(page_req["path"], page_req.get("wait", "networkidle"))
        ms = int((self.clock() - t0) * 1000)
        html = res.get("html") or ""
        require = page_req.get("require")
        rec = {"id": rid, "op": "page", "path": page_req["path"], "at": at, "ms": ms,
               "http_status": res.get("http_status"), "redirects": res.get("redirects", 0),
               "error": (str(res["error"])[:200] if res.get("error") else None),
               "require_ok": bool(html) and (require is None or re.search(require, html) is not None),
               "token_a": bool(TOKEN_RES["A"].search(html)),
               "token_b": bool(TOKEN_RES["B"].search(html))}
        signal = judge_nav(rec, self.base_nav)
        if self.base_nav is None and not rec["error"]:
            self.base_nav = rec
        self.current_page = None
        if signal:
            rec["signal"] = signal
            self.entries.append(rec)
            self.log(rec)
            self._stop(signal, rid)
            return False
        stored = self._store(rid, html)
        if stored is None:
            self.entries.append(rec)
            return False
        rec.update(stored)
        self.page_html[rid] = html
        self.entries.append(rec)
        self.log(rec)
        self.current_page = page_req["id"]
        return True

    def _post(self, r: dict) -> bool:
        rid = r["id"]
        if self.current_page != r["page"]:   # validate_manifest 已保證；防禦性停（不導頁）
            self._stop("manifest:page_not_current", rid)
            return False
        html = self.page_html.get(r["page"], "")
        form, missing = _resolve(r.get("form", {}), html)
        headers, missing_h = _resolve(r.get("headers", {}), html)
        if missing or missing_h:
            # token 在 page 請求取得的 HTML 裡找不到：等同挑戰頁未過（S1）。⛔ 不送 POST。
            rec = {"id": rid, "op": "post", "api": r["api"], "signal": f"S1:token_{missing or missing_h}"}
            self.entries.append(rec)
            self._stop(rec["signal"], rid)
            return False
        if not self._gate(rid):
            return False
        h = {"X-Requested-With": "XMLHttpRequest",
             "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8", **headers}
        t0 = self.clock()
        at = self.now().isoformat(timespec="seconds")
        res = self.driver.post(r["api"], h, urlencode(form))
        ms = int((self.clock() - t0) * 1000)
        text = res.get("text") or ""
        status = int(res.get("status", -1))
        rec = {"id": rid, "op": "post", "api": r["api"], "at": at, "ms": ms, "http_status": status,
               "resp_type": res.get("type"), "redirected": bool(res.get("redirected")),
               "json_ok": status == 200 and _json_ok(text)}
        signal = judge_post(rec, self.post_ms)
        self.post_ms.append(ms)
        if signal:
            rec["signal"] = signal
            self.entries.append(rec)
            self.log(rec)
            self._stop(signal, rid)
            return False
        stored = self._store(rid, text)
        if stored is None:
            self.entries.append(rec)
            return False
        rec.update(stored)
        self.entries.append(rec)
        self.log(rec)
        return True

    def execute(self) -> dict:
        (self.dir / "responses").mkdir(parents=True, exist_ok=True)
        started = self.now().isoformat(timespec="seconds")
        try:
            for r in self.m["requests"]:
                ok = self._nav(r) if r["op"] == "page" else self._post(r)
                if not ok:
                    break
        finally:
            self.driver.close()
        index = {
            "schema": BUNDLE_SCHEMA, "manifest_id": self.m["manifest_id"],
            "manifest_sha256": self.sha, "fetcher_version": FETCHER_VERSION,
            "host": socket.gethostname(), "started_at": started,
            "ended_at": self.now().isoformat(timespec="seconds"),
            "requests_sent": self.sent, "stopped": self.stopped,
            "complete": self.stopped is None and len(self.entries) == len(self.m["requests"]),
            "entries": self.entries,
        }
        tmp = self.dir / "index.json.tmp"
        tmp.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.dir / "index.json")   # index 最後才出現＝bundle 寫完的標記
        return index


# =========================================================================== CLI

def _jsonl_logger(path: Path) -> Callable[[dict], None]:
    def write(rec: dict) -> None:
        line = {k: v for k, v in rec.items() if k not in ("html", "text")}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return write


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="#393 樹莓派 www 取源器（依 manifest 取原始回應）")
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--out", type=Path, required=True, help="bundle 輸出根目錄")
    ap.add_argument("--log", type=Path, help="逐請求中繼資料 jsonl（預設 <out>/fetch-log.jsonl）")
    ap.add_argument("--check", action="store_true", help="只驗 manifest，不開瀏覽器、零網路")
    ap.add_argument("--headed", action="store_true")
    a = ap.parse_args(argv)
    raw = a.manifest.read_bytes()
    try:
        m = validate_manifest(json.loads(raw))
    except (ManifestError, ValueError) as e:
        print(f"manifest 不合法，未送任何請求：{e}", file=sys.stderr)
        return 65
    if a.check:
        print(json.dumps({"ok": True, "manifest_id": m["manifest_id"],
                          "requests": len(m["requests"]), "sha256": manifest_sha256(raw)}))
        return 0
    if (a.out / m["manifest_id"] / "index.json").exists():
        print("同一 manifest_id 已有 bundle；⛔ 不覆寫、不重跑", file=sys.stderr)
        return 75
    a.out.mkdir(parents=True, exist_ok=True)
    log = _jsonl_logger(a.log or a.out / "fetch-log.jsonl")
    run = Run(m, manifest_sha256(raw), a.out, PlaywrightDriver(headed=a.headed), log=log)
    index = run.execute()
    print(json.dumps({k: index[k] for k in ("manifest_id", "requests_sent", "complete", "stopped")},
                     ensure_ascii=False))
    return 0 if index["complete"] else 3


if __name__ == "__main__":
    sys.exit(main())
