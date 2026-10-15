"""#293 r3（PLAN r3.1 §16）：官網 www 導頁固定標記 ``WWW_REQ card=293 …``。

`_browser.py` 是共用檔，本檔先釘「未啟用時行為不變」（共同主 PM 條件 1），再驗啟用時的行數、
kind／src／status 寫法、獨立的 Playwright 導頁計數（WWW_NAV），以及晚間鏈兩個入口的接線。
全部用假 page 物件：不開瀏覽器、不連網。
"""

from __future__ import annotations

import inspect
import logging
import re
import textwrap

import pytest

from cpbl.ingest import _browser as br
from cpbl.ingest import postseason_evening as pe


class FakeError(Exception):
    pass


class FakeResponse:
    def __init__(self, status):
        self.status = status


class FakePage:
    """記錄呼叫序列；goto 依腳本回 status、或拋 FakeError。"""

    def __init__(self, script, html="<html>token</html>"):
        self.script = list(script)
        self.calls = []
        self.html = html
        self.listeners = []

    def goto(self, url, wait_until, timeout):
        self.calls.append(("goto", url, wait_until, timeout))
        step = self.script.pop(0) if self.script else 200
        if step == "raise":
            raise FakeError("net::ERR_TOO_MANY_REDIRECTS")
        return FakeResponse(step)

    def wait_for_timeout(self, ms):
        self.calls.append(("wait", ms))

    def content(self):
        self.calls.append(("content",))
        return self.html.pop(0) if isinstance(self.html, list) else self.html

    def on(self, event, fn):
        self.calls.append(("on", event))
        self.listeners.append(fn)


def make_session(page):
    s = object.__new__(br._Session)
    s._page = page
    s._loaded = None
    s._listening = False
    s._defer_marks = False
    s.contexts = 0

    def new_context():
        s.contexts += 1
        s._page = page
        s._loaded = None
        s._listening = False
        s._defer_marks = False
    s._new_context = new_context
    return s


@pytest.fixture(autouse=True)
def fake_playwright_error(monkeypatch):
    import sys
    import types
    mod = types.ModuleType("playwright.sync_api")
    mod.Error = FakeError
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", mod)
    br._MARKER = None
    yield
    br._MARKER = None


def lines(caplog, tag="WWW_REQ"):
    return [r.getMessage() for r in caplog.records if r.name == "cpbl.browser.www" and r.getMessage().startswith(tag)]


# ------------------------------------------------------------------ 條件 1：未啟用時行為不變

# 405bc2bb 的 `_Session._goto` 本文（逐字）。未啟用分支必須與它相同。
ORIGINAL_GOTO_BODY = '''\
try:
    self._page.goto(url, wait_until=wait, timeout=45000)
except Error as e:
    log.warning("導航失敗（%s），換乾淨 context 於 5s 後重試：%s", page_path, str(e)[:120])
    self._new_context()
    self._page.wait_for_timeout(5000)
    self._page.goto(url, wait_until=wait, timeout=45000)
'''


def test_unmarked_goto_branch_is_verbatim_the_original_body():
    src = inspect.getsource(br._Session._goto)
    m = re.search(r"if _MARKER is None:[^\n]*\n(.*?)\n\s*return\n", src, re.S)
    assert m, src
    assert textwrap.dedent(m.group(1)) + "\n" == ORIGINAL_GOTO_BODY


@pytest.mark.parametrize(("script", "html", "expected"), [
    ([200], "<html>token</html>",
     [("goto", "https://www.cpbl.com.tw/schedule", "networkidle", 45000), ("wait", 1500), ("content",)]),
    (["raise", 200], "<html>token</html>",
     [("goto", "https://www.cpbl.com.tw/schedule", "networkidle", 45000), ("wait", 5000),
      ("goto", "https://www.cpbl.com.tw/schedule", "networkidle", 45000), ("wait", 1500), ("content",)]),
    ([200, 200], ["<html>no</html>", "<html>token</html>"],
     [("goto", "https://www.cpbl.com.tw/schedule", "networkidle", 45000), ("wait", 1500), ("content",),
      ("wait", 2000),
      ("goto", "https://www.cpbl.com.tw/schedule", "networkidle", 45000), ("wait", 1500), ("content",)]),
])
def test_unmarked_page_html_call_sequence_and_zero_lines(caplog, script, html, expected):
    caplog.set_level(logging.INFO, logger="cpbl.browser.www")
    page = FakePage(script, html)
    s = make_session(page)
    assert "token" in s.page_html("/schedule", require="token")
    assert page.calls == expected, "未啟用時呼叫序列與原本相同（不註冊監聽、不多任何一步）"
    assert not page.listeners and lines(caplog) == [] and lines(caplog, "WWW_NAV") == []


# ------------------------------------------------------------------ 啟用時

def test_one_goto_one_line_with_fixed_key_order(caplog):
    caplog.set_level(logging.INFO, logger="cpbl.browser.www")
    s = make_session(FakePage([200]))
    with br.www_marker("box", "293", "2026/C/2"):
        s.page_html("/box/index?gameSno=2&year=2026&kindCode=C", require="token")
    (line,) = lines(caplog)
    assert br.WWW_REQ_RE.fullmatch(line), line
    assert line.startswith("WWW_REQ card=293 kind=box src=293 at=") and line.endswith(" game=2026/C/2 status=200")
    assert "gameSno" not in line and "?" not in line, "不含 URL query"


def test_reload_backoff_is_retry_and_challenge_is_marked(caplog):
    caplog.set_level(logging.INFO, logger="cpbl.browser.www")
    s = make_session(FakePage([200, 200], ["<html>挑戰頁</html>", "<html>token</html>"]))
    with br.www_marker("event", "293", "2026/C/-"):
        s.page_html("/schedule", require="token")
    got = lines(caplog)
    assert [re.search(r"kind=(\w+)", x).group(1) for x in got] == ["event", "retry"]
    assert [x.rsplit("status=", 1)[1] for x in got] == ["challenge", "200"]


def test_goto_error_then_context_retry(caplog):
    caplog.set_level(logging.INFO, logger="cpbl.browser.www")
    s = make_session(FakePage(["raise", 200]))
    with br.www_marker("box", "293", "2026/C/2"):
        s.page_html("/schedule", require="token")
    got = lines(caplog)
    assert [x.rsplit("status=", 1)[1] for x in got] == ["error", "200"]
    assert [re.search(r"kind=(\w+)", x).group(1) for x in got] == ["box", "retry"]
    assert all(br.WWW_REQ_RE.fullmatch(x) for x in got)


def test_post_reloads_count_as_navigations_but_the_post_itself_is_not_counted(caplog):
    """C4（r3.1）：同頁 fetch POST 不記；post() 失敗後的重載是導頁，照記。"""
    caplog.set_level(logging.INFO, logger="cpbl.browser.www")
    page = FakePage([200, 200])
    results = iter([{"status": -1, "text": "Failed to fetch"}, {"status": 200, "text": "{}"}])
    page.evaluate = lambda js, arg: (page.calls.append(("evaluate",)), next(results))[1]
    s = make_session(page)
    with br.www_marker("other", "292", "2026/C/-"):
        assert s.post("/schedule", "/schedule/getgamedatas", {"a": "1"}) == (200, "{}")
    got = lines(caplog)
    assert [re.search(r"kind=(\w+) src=(\d+)", x).groups() for x in got] == [("other", "292"), ("retry", "292")]
    assert sum(1 for c in page.calls if c[0] == "evaluate") == 2


def test_navigation_listener_is_independent_and_counts_main_frame_www_only(caplog):
    caplog.set_level(logging.INFO, logger="cpbl.browser.www")
    page = FakePage([200])
    s = make_session(page)

    class Req:
        def __init__(self, url, nav=True, redirected=None, sub=False):
            self.url, self._nav, self.redirected_from = url, nav, redirected
            self.frame = type("F", (), {"parent_frame": object() if sub else None})()

        def is_navigation_request(self):
            return self._nav

    with br.www_marker("box", "293", "2026/C/2"):
        s.page_html("/box", require="token")
        (listener,) = page.listeners
        listener(Req("https://www.cpbl.com.tw/box?x=1"))                    # 計
        listener(Req("https://www.cpbl.com.tw/box", redirected=object()))   # 重定向中間跳：不計
        listener(Req("https://www.cpbl.com.tw/x.js", nav=False))            # 子資源：不計
        listener(Req("https://www.cpbl.com.tw/ad", sub=True))               # iframe：不計
        listener(Req("https://stats.cpbl.com.tw/"))                         # 非 www：不計
    nav = lines(caplog, "WWW_NAV")
    assert len(nav) == 1 and nav[0].startswith("WWW_NAV card=293 src=293 at=") and "?" not in nav[0]
    br._MARKER = None
    listener(Req("https://www.cpbl.com.tw/box"))
    assert len(lines(caplog, "WWW_NAV")) == 1, "區塊外不計"


# ------------------------------------------------------------------ 正規式與負控

GOOD = "WWW_REQ card=293 kind=box src=293 at=2026-10-18T21:40:02+08:00 game=2026/C/2 status=200"


@pytest.mark.parametrize("bad", [
    "WWW_REQ card=293 kind=box src=293 at=2026-10-18T21:40:02+08:00 game=2026/C/2 status=200 url=/box?gameSno=2",
    "WWW_REQ card=293 kind=box at=2026-10-18T21:40:02+08:00 game=2026/C/2 status=200",            # 缺 src
    "WWW_REQ card=293 src=293 kind=box at=2026-10-18T21:40:02+08:00 game=2026/C/2 status=200",    # src 位置錯
    "WWW_REQ card=293 kind=box src=293 at=2026-10-18T13:40:02+00:00 game=2026/C/2 status=200",    # 非 +08:00
    "WWW_REQ card=293 kind=box src=292 at=2026-10-18T21:40:02+08:00 game=2026/A/2 status=200",    # 非季後
])
def test_format_regex_accepts_good_and_rejects_negative_controls(bad):
    assert br.WWW_REQ_RE.fullmatch(GOOD)
    assert not br.WWW_REQ_RE.fullmatch(bad)


def test_marker_rejects_bad_arguments():
    for args in (("box", "294", "2026/C/2"), ("boxx", "293", "2026/C/2"), ("box", "293", "2026/C/2?x")):
        with pytest.raises(ValueError), br.www_marker(*args):
            pass


# ------------------------------------------------------------------ 晚間鏈接線

def test_scrape_marker_args_event_retry_and_292_other():
    state = pe.empty_state()
    assert pe.scrape_marker_args(state, "C") == ("other", "292"), "只有 #292 先發時點觸發"
    state["events"] = {"final_not_ingested:2026-C-2": {"key": "2026-C-2", "state": "open", "attempts": []}}
    assert pe.scrape_marker_args(state, "C") == ("event", "293")
    state["events"]["final_not_ingested:2026-C-2"]["attempts"] = ["2026-10-18T13:00:00+00:00"]
    assert pe.scrape_marker_args(state, "C") == ("retry", "293")
    assert pe.scrape_marker_args(state, "E") == ("other", "292")


def test_boxpa_detail_marks_each_game_and_restores_entry_points(monkeypatch):
    from cpbl.ingest import run_refresh_recent as rr

    seen = []
    orig_g = rr.scrape_gamelogs
    monkeypatch.setattr(rr, "scrape_gamelogs", lambda y, snos, kind, **kw: seen.append(("g", dict(br._MARKER))) or {})
    monkeypatch.setattr(rr, "scrape_game_details", lambda y, snos, kind: seen.append(("d", dict(br._MARKER))) or 1)
    patched_g, patched_d = rr.scrape_gamelogs, rr.scrape_game_details

    def fake_step(year, kinds, days):
        rr.scrape_gamelogs(year, [2], "C", allow_partial=True)
        rr.scrape_game_details(year, [2], "C")
        return {"errors": []}

    monkeypatch.setattr(rr, "_postseason_detail_step", fake_step)
    monkeypatch.setattr(pe, "boxpa_game_dates", lambda keys: ["2026-10-18"])
    state = {"boxpa": {"2026-C-2": {"detail_attempts": []}}}
    pe.boxpa_detail(2026, ["2026-C-2"], state)
    assert [(k, m["kind"], m["src"], m["game"]) for k, m in seen] == [
        ("g", "box", "293", "2026/C/2"), ("d", "box", "293", "2026/C/2")]
    state["boxpa"]["2026-C-2"]["detail_attempts"] = ["x"]
    seen.clear()
    pe.boxpa_detail(2026, ["2026-C-2"], state)
    assert {m["kind"] for _, m in seen} == {"retry"}, "同一場後續喚醒的再抓記 retry"
    assert (rr.scrape_gamelogs, rr.scrape_game_details) == (patched_g, patched_d), "呼叫後原樣還原"
    assert br._MARKER is None
    assert orig_g is not patched_g


def test_daily_chain_never_enables_the_marker():
    """§16.3：每日鏈不寫標記——www_marker 只在 postseason_evening 內被使用。"""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "src" / "cpbl"
    users = sorted(str(p.relative_to(root)) for p in root.rglob("*.py")
                   if "www_marker(" in p.read_text(encoding="utf-8") and p.name != "_browser.py")
    assert users == ["ingest/postseason_evening.py"]
