"""過 HiNet CDN 反爬挑戰的瀏覽器 session（www.cpbl.com.tw 專用）。

官網主站 2026-06 起加了 HiNet CDN「Anti-DDoS Flood Protection」JS 挑戰：純 httpx
（不執行 JS）對 /schedule 與 /schedule/getgamedatas 等一律回 **428**。實測唯一可行：
用 Playwright 開頁讓挑戰 JS 跑完（拿到 200 + token），再以 **page.evaluate(fetch)** 從
已過挑戰的頁面 context 發 AJAX（cookie/指紋一致才會 200；cookie 交接給 httpx 不行）。

⚠️ 挑戰是**機率性**的，且對「短時間連續冷啟動」會升級節流（2026-07 實測）：
- 首載可能回挑戰頁（無 token）→ `page_html(require=…)` 會重載退避重試。
- in-page fetch 可能被挑戰重定向攔截（TypeError: Failed to fetch）→ `post()` 會
  重載頁面退避重試。
- cookie 壞掉會導航進重定向迴圈（ERR_TOO_MANY_REDIRECTS）→ 換乾淨 context 重試。
- **CLI 整輪失敗時勿立刻重跑**：連續冷啟動會讓節流更嚴重，先冷卻 15–20 分鐘。

只在本機爬蟲用（生產不爬蟲）。Playwright 在 dependency group `scrape`：
    uv sync --group scrape && uv run playwright install chromium

模組級單例：整個爬蟲 run 共用一個 browser context（挑戰過一次即全程有效）。
"""

from __future__ import annotations

import atexit
import logging
import os
import re
from urllib.parse import urlencode

log = logging.getLogger("cpbl.browser")

# 反爬封鎖是「懲罰新訪客」：有舊挑戰 cookie 的瀏覽器暢通、無 cookie 新訪客被擋
# （2026-07-04 實測：同 IP 同時刻 Chrome(有cookie)全通、Safari(無cookie)全擋）。
# 對策：persistent profile 讓爬蟲過關一次後變「熟客」，cookie 跨 run 重用。
# CPBL_SCRAPE_PROFILE=<dir> → 持久化 profile；CPBL_SCRAPE_CHANNEL=chrome → 真 Chrome；
# CPBL_SCRAPE_HEADED=1 → 有頭模式（最像真人，過挑戰成功率最高）。
_CHANNEL = os.environ.get("CPBL_SCRAPE_CHANNEL", "")
_HEADED = os.environ.get("CPBL_SCRAPE_HEADED", "") == "1"
_PROFILE = os.environ.get("CPBL_SCRAPE_PROFILE", "")

BASE = "https://www.cpbl.com.tw"
# CPBL_SCRAPE_UA：借用真瀏覽器 cookie 時 UA 必須一致，否則挑戰可能識破
UA = os.environ.get("CPBL_SCRAPE_UA") or (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# page context 內發 POST；fetch 被挑戰攔截時回 status=-1 交由 post() 重試，不讓 evaluate 拋錯
_JS_POST = """async ({path, headers, body}) => {
  try {
    const r = await fetch(path, { method: 'POST', headers, body, credentials: 'include' });
    const text = await r.text();
    return { status: r.status, text };
  } catch (e) {
    return { status: -1, text: String(e) };
  }
}"""

# 重試退避（ms）：挑戰/節流恢復需要時間，快打只會讓 HiNet 節流升級
_BACKOFF_MS = (2000, 6000, 15000)


class _Session:
    def __init__(self) -> None:
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        # AutomationControlled 會讓 navigator.webdriver=true——挑戰升級戒備時據此攔自動化
        # 瀏覽器（2026-07-04：同 IP 真瀏覽器可過、Playwright 有頭/無頭全被重定向迴圈）
        self._kw: dict = {"headless": not _HEADED,
                          "args": ["--disable-blink-features=AutomationControlled"]}
        if _CHANNEL:
            self._kw["channel"] = _CHANNEL
        self._browser = None if _PROFILE else self._pw.chromium.launch(**self._kw)
        self._new_context()
        atexit.register(self.close)

    def _new_context(self) -> None:
        """建（或換）context：cookie 壞掉（重定向迴圈）時的復原手段。

        persistent profile 模式下 context 即 browser（cookie 落地 _PROFILE 目錄，
        跨 run 重用 = 對反爬而言是「熟客」）；重建時整個 relaunch。
        """
        if getattr(self, "_ctx", None) is not None:
            try:
                self._ctx.close()
            except Exception:  # noqa: BLE001 — 舊 context 關閉容錯
                pass
        # CPBL_SCRAPE_UA=default → 不覆寫 UA（避免與 Sec-CH-UA client hints 不一致被判機器人）
        ctx_kw: dict = {"locale": "zh-TW"}
        if os.environ.get("CPBL_SCRAPE_UA") != "default":
            ctx_kw["user_agent"] = UA
        if _PROFILE:
            self._ctx = self._pw.chromium.launch_persistent_context(
                _PROFILE, **ctx_kw, **self._kw)
            self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        else:
            self._ctx = self._browser.new_context(**ctx_kw)
            self._page = self._ctx.new_page()
        self._loaded: str | None = None

    def _goto(self, page_path: str, wait: str) -> None:
        """單次導航；失敗（如 ERR_TOO_MANY_REDIRECTS = 挑戰 cookie 壞掉）→ 換新 context 重試一次。"""
        from playwright.sync_api import Error
        url = f"{BASE}{page_path}"
        try:
            self._page.goto(url, wait_until=wait, timeout=45000)
        except Error as e:
            log.warning("導航失敗（%s），換乾淨 context 於 5s 後重試：%s", page_path, str(e)[:120])
            self._new_context()
            self._page.wait_for_timeout(5000)
            self._page.goto(url, wait_until=wait, timeout=45000)

    def _ensure(self, page_path: str, wait: str = "networkidle", force: bool = False) -> None:
        """確保目前停在 page_path（過挑戰）。換頁才重載。

        wait="networkidle"（預設）：等 SPA/AJAX 靜止 + 1.5s，過挑戰最穩，但老頁面
        常因背景請求不絕而吃滿 45s timeout。wait="domcontentloaded"：僅等 DOM，
        適用伺服器端渲染的靜態頁（如 person 頁 bio），快 4-5 倍；挑戰未過時由
        page_html(require=…) 重載補救。
        """
        if self._loaded == page_path and not force:
            return
        self._loaded = None  # 導航中/失敗皆視為未載入
        self._goto(page_path, wait)
        self._page.wait_for_timeout(1500 if wait == "networkidle" else 400)
        self._loaded = page_path

    def page_html(self, page_path: str, wait: str = "networkidle", force: bool = False,
                  require: str | re.Pattern | None = None) -> str:
        """取頁面 HTML。require（str/regex）＝頁面必含樣式（如 token）；
        未含視為挑戰頁未過 → 重載退避重試（挑戰是機率性的，重載通常就過）。"""
        last_len = 0
        for i, backoff in enumerate((0, *_BACKOFF_MS)):
            if backoff:
                log.warning("頁面缺必要內容（挑戰未過？len=%d）%s：%dms 後重載（第 %d 次）",
                            last_len, page_path, backoff, i)
                self._page.wait_for_timeout(backoff)
            self._ensure(page_path, wait, force=force or i > 0)
            html = self._page.content()
            if require is None or re.search(require, html):
                return html
            last_len = len(html)
            wait = "networkidle"  # 重試一律等到底，給挑戰 JS 時間
        raise RuntimeError(f"{page_path} 重試後仍缺必要內容（反爬挑戰未過或官網改版）")

    def post(self, page_path: str, api_path: str, form: dict[str, str],
             headers: dict[str, str] | None = None) -> tuple[int, str]:
        """於 page_path（已過挑戰）context 內 POST api_path。回 (status, text)。

        fetch 被挑戰攔截（status=-1）或回 428 → 重載頁面退避重試（挑戰 cookie 需重新生效）。
        """
        h = {"X-Requested-With": "XMLHttpRequest",
             "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}
        if headers:
            h.update(headers)
        body = urlencode(form)
        status, text = -1, ""
        for i, backoff in enumerate((0, *_BACKOFF_MS)):
            if backoff:
                log.warning("POST %s 失敗（status=%s）：%dms 後重載頁面重試（第 %d 次）",
                            api_path, status, backoff, i)
                self._page.wait_for_timeout(backoff)
            self._ensure(page_path, force=i > 0)
            res = self._page.evaluate(_JS_POST, {"path": api_path, "headers": h, "body": body})
            status, text = int(res["status"]), res["text"]
            if status not in (-1, 428):
                return status, text
        raise RuntimeError(
            f"POST {api_path} 重試後仍失敗（status={status}，反爬節流？先冷卻再跑）：{text[:200]}")

    def close(self) -> None:
        try:
            if self._browser is not None:
                self._browser.close()
            else:
                self._ctx.close()  # persistent 模式：關 context 即落地 cookie
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
