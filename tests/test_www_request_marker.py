"""#293 r3（PLAN r3.1 §16）：官網 www 導頁固定標記 ``WWW_REQ card=293 …``。

`_browser.py` 是共用檔，本檔先釘「未啟用時行為不變」（共同主 PM 條件 1），再驗啟用時的行數、
kind／src／status 寫法、獨立的 Playwright 導頁計數（WWW_NAV），以及晚間鏈兩個入口的接線。
全部用假 page 物件：不開瀏覽器、不連網。
"""

from __future__ import annotations

import hashlib
import inspect
import logging
import re
import textwrap
from pathlib import Path

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


class FakeContext:
    def __init__(self, page):
        self.page = page

    def new_page(self):
        return self.page

    def close(self):
        self.page.calls.append(("ctx_close",))


class FakeBrowser:
    def __init__(self, page):
        self.page = page

    def new_context(self, **kw):
        self.page.calls.append(("new_context",))
        return FakeContext(self.page)


def make_session(page):
    """真的 _Session._new_context（假 browser）：換 context 的旗標處理要跑到受測碼本身。"""
    s = object.__new__(br._Session)
    s._browser = FakeBrowser(page)
    s._ctx = None
    s._new_context()
    page.calls.clear()
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


# ------------------------------------------------------------------ 條件 1：與基準原文逐位元比對（#293 審核席 2 F1）
#
# 基準＝af4eda62 的 _browser.py 原文（tests/fixtures/browser_baseline_af4eda62.py.txt，sha256
# 8e48b580…5c05；51c65d1d／a1ca55bc 此檔相同）。同一份假 page 腳本分別跑基準與現行模組，未啟用標記時
# 回傳值（或例外型別＋訊息）、page 呼叫序列、**全部** cpbl.browser* log 紀錄（logger、等級、訊息）、
# _loaded 與 context 重建次數都必須逐位元相同。

BASELINE = Path(__file__).parent / "fixtures" / "browser_baseline_af4eda62.py.txt"


def _baseline_module():
    import types
    src = BASELINE.read_text(encoding="utf-8")
    assert hashlib.sha256(src.encode()).hexdigest() == (
        "8e48b580b70fefc610031792f788a05f2d831826a995f9bcda9aa00cea255c05")
    mod = types.ModuleType("browser_baseline_af4eda62")
    exec(compile(src, str(BASELINE), "exec"), mod.__dict__)
    return mod


def _plain_session(module, page):
    s = object.__new__(module._Session)
    s._page = page
    s._loaded = None
    box = {"contexts": 0}

    def new_context():
        box["contexts"] += 1
        s._page = page
        s._loaded = None
    s._new_context = new_context
    return s, box


def _post_page(script, results):
    page = FakePage(script)
    it = iter(results)
    page.evaluate = lambda js, arg: (page.calls.append(("evaluate", arg["path"])), next(it))[1]
    return page


SCENARIOS = {
    "page_html_ok": (lambda: FakePage([200]), lambda s: s.page_html("/schedule", require="token")),
    "page_html_no_require": (lambda: FakePage([200], "<html>x</html>"), lambda s: s.page_html("/x")),
    "page_html_regex": (lambda: FakePage([200]), lambda s: s.page_html("/x", require=re.compile("tok.n"))),
    "page_html_dom": (lambda: FakePage([200]), lambda s: s.page_html("/p", wait="domcontentloaded")),
    "page_html_force": (lambda: FakePage([200, 200]),
                        lambda s: (s.page_html("/x"), s.page_html("/x", force=True))),
    "page_html_cached": (lambda: FakePage([200]), lambda s: (s.page_html("/x"), s.page_html("/x"))),
    "page_html_challenge_then_ok": (lambda: FakePage([200, 200], ["<html>no</html>", "<html>token</html>"]),
                                    lambda s: s.page_html("/schedule", require="token")),
    "page_html_challenge_exhausted": (lambda: FakePage([200] * 4, ["<html>no</html>"] * 4),
                                      lambda s: s.page_html("/schedule", require="token")),
    "goto_error_then_ok": (lambda: FakePage(["raise", 200]), lambda s: s.page_html("/x", require="token")),
    "goto_error_twice": (lambda: FakePage(["raise", "raise"]), lambda s: s.page_html("/x")),
    "goto_error_then_challenge": (lambda: FakePage(["raise", 200, 200], ["<html>no</html>", "<html>token</html>"]),
                                  lambda s: s.page_html("/x", require="token")),
    "post_ok": (lambda: _post_page([200], [{"status": 200, "text": "{}"}]),
                lambda s: s.post("/schedule", "/api", {"a": "1"})),
    "post_retry": (lambda: _post_page([200, 200], [{"status": -1, "text": "e"}, {"status": 200, "text": "ok"}]),
                   lambda s: s.post("/schedule", "/api", {"a": "1"}, headers={"X": "1"})),
    "post_exhausted": (lambda: _post_page([200] * 4, [{"status": 428, "text": "blocked"}] * 4),
                       lambda s: s.post("/schedule", "/api", {})),
}


def _observe(module, scenario, caplog):
    make_page, act = SCENARIOS[scenario]
    page = make_page()
    s, box = _plain_session(module, page)
    caplog.clear()
    try:
        outcome = ("return", act(s))
    except Exception as exc:  # noqa: BLE001 — 例外本身也是被比對的行為
        outcome = ("raise", type(exc).__name__, str(exc))
    logs = [(r.name, r.levelno, r.getMessage()) for r in caplog.records if r.name.startswith("cpbl.browser")]
    return {"outcome": outcome, "calls": page.calls, "logs": logs, "loaded": s._loaded,
            "contexts": box["contexts"]}


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_unmarked_behaviour_is_bit_identical_to_baseline(caplog, scenario):
    caplog.set_level(logging.DEBUG)
    base = _observe(_baseline_module(), scenario, caplog)
    now = _observe(br, scenario, caplog)
    assert now == base


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


def test_challenge_after_context_switch_is_still_marked_challenge(caplog):
    """#293 審核席 1 F4：導頁拋錯 → 換 context → 第二次導頁拿到挑戰頁 → 重載通過。
    換 context 不得清掉延後寫入，第二行必須是 challenge，不是 200。"""
    caplog.set_level(logging.INFO, logger="cpbl.browser.www")
    s = make_session(FakePage(["raise", 200, 200], ["<html>挑戰頁</html>", "<html>token</html>"]))
    with br.www_marker("box", "293", "2026/C/2"):
        s.page_html("/box", require="token")
    assert [x.rsplit("status=", 1)[1] for x in lines(caplog)] == ["error", "challenge", "200"]


def test_retry_is_every_navigation_after_the_first_in_one_logical_fetch(caplog):
    """#293 審核席 1 F5：PLAN r3.1 §16.1 字面——同一次邏輯抓取（一個 www_marker 區塊）的第一個導頁記
    區塊 kind，第二個以後一律 retry，即使是不同頁。"""
    caplog.set_level(logging.INFO, logger="cpbl.browser.www")
    s = make_session(FakePage([200, 200]))
    with br.www_marker("box", "293", "2026/C/2"):
        s.page_html("/box/index?gameSno=2&year=2026&kindCode=C", require="token")
        s.page_html("/box?year=2026&KindCode=C&gameSno=2")
    assert [re.search(r"kind=(\w+)", x).group(1) for x in lines(caplog)] == ["box", "retry"]
    with br.www_marker("box", "293", "2026/C/3"):
        s.page_html("/box?year=2026&KindCode=C&gameSno=3", force=True)
    assert re.search(r"kind=(\w+)", lines(caplog)[-1]).group(1) == "box", "新的邏輯抓取重新起算"


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


def _stub_detail_leaves(monkeypatch, calls):
    from cpbl.ingest import cpbl_pitch_tracking as pt
    from cpbl.ingest import run_refresh_recent as rr

    def gamelogs(y, snos, kind, **kw):
        calls.append(("gamelog", y, kind, list(snos), dict(br._MARKER) if br._MARKER else None))
        return {"scoreboard": 18, "livelog": 300, "batting_box": 20, "pitching_box": 8}

    def details(y, snos, kind):
        calls.append(("detail", y, kind, list(snos), dict(br._MARKER) if br._MARKER else None))
        return 1

    def pitches(games, delay):
        calls.append(("pitches", games, None, None, dict(br._MARKER) if br._MARKER else None))
        return {"games": 1, "pitches": 250, "pitcher_flags": 8}

    monkeypatch.setattr(rr, "scrape_gamelogs", gamelogs)
    monkeypatch.setattr(rr, "scrape_game_details", details)
    monkeypatch.setattr(rr, "_postseason_detail_gaps", lambda y, k, snos, tables: {})
    # 每日補洞的選場來源：若被用到就會把歷史 C1 帶進來（席 1 F1 的重現條件）。
    monkeypatch.setattr(rr, "_missing_postseason_detail_snos", lambda *a, **k: [1])
    monkeypatch.setattr(rr, "_completed_snos", lambda *a, **k: [1, 2])
    monkeypatch.setattr(rr, "_lagging_pitch_games", lambda *a, **k: {1})
    monkeypatch.setattr(rr, "_postseason_detail_step",
                        lambda *a, **k: pytest.fail("boxpa_detail 不得走每日補洞的 _postseason_detail_step"))
    monkeypatch.setattr(pt, "scrape_game_pitches", pitches)
    monkeypatch.setattr(pt, "is_frozen", lambda *a: False)


def test_boxpa_detail_fetches_only_target_games_and_marks_one_block_per_game(monkeypatch, caplog):
    """#293 審核席 1 F1＋F5：只抓傳入的目標場（歷史缺口 C1 不被帶入）；每場一個標記區塊。"""
    calls = []
    _stub_detail_leaves(monkeypatch, calls)
    state = {"boxpa": {"2026-C-2": {"detail_attempts": []}}}
    out = pe.boxpa_detail(2026, ["2026-C-2"], state)
    assert out["errors"] == []
    assert [(c[0], c[3]) for c in calls] == [("gamelog", [2]), ("detail", [2]), ("pitches", None)]
    assert calls[2][1] == [(2026, "C", 2)], "逐球只帶目標場，不帶 lagging 場"
    assert [(c[4]["kind"], c[4]["src"], c[4]["game"]) for c in calls[:2]] == [
        ("box", "293", "2026/C/2"), ("box", "293", "2026/C/2")], "gamelog 與 details 在同一個區塊（同一次邏輯抓取）"
    assert calls[2][4] is None, "逐球是 stats 站，不在 www 標記區塊內"
    state["boxpa"]["2026-C-2"]["detail_attempts"] = ["x"]
    calls.clear()
    pe.boxpa_detail(2026, ["2026-C-2"], state)
    assert calls[0][4]["kind"] == "retry", "同一場後續喚醒的再抓記 retry"
    assert br._MARKER is None


def test_results_scrape_marks_each_kind_without_changing_the_call_interface(monkeypatch):
    from cpbl.ingest import run_refresh_recent as rr

    seen = []
    monkeypatch.setattr(rr, "scrape_games", lambda y1, y2, kind: seen.append(dict(br._MARKER)) or {y1: 1})
    patched = rr.scrape_games
    state = pe.empty_state()
    state["events"] = {"final_not_ingested:2026-C-2": {"key": "2026-C-2", "state": "open", "attempts": []}}
    with pe.marking_scrape_games(state, 2026):
        out = rr._postseason_games_step(2026, ("E", "C"))
    assert out["errors"] == []
    assert [(m["kind"], m["src"], m["game"]) for m in seen] == [
        ("other", "292", "2026/E/-"), ("event", "293", "2026/C/-")]
    assert rr.scrape_games is patched and br._MARKER is None


def test_daily_chain_never_enables_the_marker():
    """§16.3：每日鏈不寫標記——www_marker 只在 postseason_evening 內被使用。"""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "src" / "cpbl"
    users = sorted(str(p.relative_to(root)) for p in root.rglob("*.py")
                   if "www_marker(" in p.read_text(encoding="utf-8") and p.name != "_browser.py")
    assert users == ["ingest/postseason_evening.py"]
