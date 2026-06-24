"""過 HiNet CDN 反爬挑戰的瀏覽器 session（www.cpbl.com.tw 專用）。

官網主站 2026-06 起加了 HiNet CDN「Anti-DDoS Flood Protection」JS 挑戰：純 httpx
（不執行 JS）對 /schedule 與 /schedule/getgamedatas 等一律回 **428**。實測唯一可行：
用 Playwright 開頁讓挑戰 JS 跑完（拿到 200 + token），再以 **page.evaluate(fetch)** 從
已過挑戰的頁面 context 發 AJAX（cookie/指紋一致才會 200；cookie 交接給 httpx 不行）。

只在本機爬蟲用（生產不爬蟲）。Playwright 在 dependency group `scrape`：
    uv sync --group scrape && uv run playwright install chromium

模組級單例：整個爬蟲 run 共用一個 browser context（挑戰過一次即全程有效）。
"""

from __future__ import annotations

import atexit
import logging
from urllib.parse import urlencode

log = logging.getLogger("cpbl.browser")

BASE = "https://www.cpbl.com.tw"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# page context 內發 POST，回 {status, text}
_JS_POST = """async ({path, headers, body}) => {
  const r = await fetch(path, { method: 'POST', headers, body });
  const text = await r.text();
  return { status: r.status, text };
}"""


class _Session:
    def __init__(self) -> None:
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self._ctx = self._browser.new_context(user_agent=UA, locale="zh-TW")
        self._page = self._ctx.new_page()
        self._loaded: str | None = None
        atexit.register(self.close)

    def _ensure(self, page_path: str) -> None:
        """確保目前停在 page_path（過挑戰）。換頁才重載。"""
        if self._loaded == page_path:
            return
        self._page.goto(f"{BASE}{page_path}", wait_until="networkidle", timeout=45000)
        self._page.wait_for_timeout(1500)  # 讓挑戰 JS / SPA 初始化完成
        self._loaded = page_path

    def page_html(self, page_path: str) -> str:
        self._ensure(page_path)
        return self._page.content()

    def post(self, page_path: str, api_path: str, form: dict[str, str],
             headers: dict[str, str] | None = None) -> tuple[int, str]:
        """於 page_path（已過挑戰）context 內 POST api_path。回 (status, text)。"""
        self._ensure(page_path)
        h = {"X-Requested-With": "XMLHttpRequest",
             "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
        if headers:
            h.update(headers)
        res = self._page.evaluate(_JS_POST, {"path": api_path, "headers": h, "body": urlencode(form)})
        return int(res["status"]), res["text"]

    def close(self) -> None:
        try:
            self._browser.close()
            self._pw.stop()
        except Exception:  # noqa: BLE001 — 關閉容錯
            pass


_session: _Session | None = None


def session() -> _Session:
    """取得（或建立）共用瀏覽器 session。"""
    global _session
    if _session is None:
        log.info("啟動 Playwright 瀏覽器以過官網反爬挑戰…")
        _session = _Session()
    return _session
