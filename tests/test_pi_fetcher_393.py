"""#393 WP3：樹莓派 www 取源器（ops/pi-fetcher/cpbl_pi_fetch.py）的離線測試。

全部用假驅動，零網路、零 DB。重點：前兆第一格就停、不重試；間隔與時段窗守住；bundle 可驗證。
"""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "ops" / "pi-fetcher" / "cpbl_pi_fetch.py"
_spec = importlib.util.spec_from_file_location("cpbl_pi_fetch", _PATH)
assert _spec is not None and _spec.loader is not None
pf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pf)

TZ = pf.TZ
NOW = dt.datetime(2026, 10, 30, 13, 30, tzinfo=TZ)
HTML_A = "<script>RequestVerificationToken: 'tokA123'</script>"
HTML_B = '<input name="__RequestVerificationToken" type="hidden" value="tokB456" />'


def _manifest(requests: list[dict], **kw) -> dict:
    m = {"schema": pf.MANIFEST_SCHEMA, "manifest_id": "t-001",
         "window": {"start": "2026-10-30T13:00:00+08:00", "end": "2026-10-30T14:00:00+08:00"},
         "min_gap_s": 1.0, "max_requests": 50, "requests": requests}
    m.update(kw)
    return m


SCHEDULE = [
    {"id": "p1", "op": "page", "path": "/schedule", "require": r"RequestVerificationToken:\s*'"},
    {"id": "q1", "op": "post", "page": "p1", "api": "/schedule/getgamedatas",
     "form": {"calendar": "2026/01/01", "location": "", "kindCode": "A"},
     "headers": {"RequestVerificationToken": {"$token": "A"}}},
    {"id": "q2", "op": "post", "page": "p1", "api": "/schedule/getgamedatas",
     "form": {"calendar": "2026/01/01", "location": "", "kindCode": "D"},
     "headers": {"RequestVerificationToken": {"$token": "A"}}},
]


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.t += s


class FakeDriver:
    def __init__(self, navs: list[dict], posts: list[dict], clock: FakeClock,
                 cost_s: float = 0.2) -> None:
        self.navs, self.posts, self.c, self.cost = list(navs), list(posts), clock, cost_s
        self.calls: list[tuple] = []
        self.closed = False

    def goto(self, path, wait):
        self.calls.append(("goto", path))
        self.c.t += self.cost
        return self.navs.pop(0)

    def post(self, api, headers, body):
        self.calls.append(("post", api, dict(headers), body))
        self.c.t += self.cost
        return self.posts.pop(0)

    def close(self):
        self.closed = True


def _ok_nav(html=HTML_A, redirects=0):
    return {"http_status": 200, "redirects": redirects, "html": html, "error": None}


def _ok_post(text='{"Success": true, "GameDatas": "[]"}'):
    return {"status": 200, "type": "basic", "redirected": False, "text": text}


def _run(tmp_path, m, navs, posts, now=NOW, cost_s=0.2):
    c = FakeClock()
    d = FakeDriver(navs, posts, c, cost_s)
    logs: list[dict] = []
    run = pf.Run(pf.validate_manifest(m), "sha", tmp_path, d, clock=c.clock, sleep=c.sleep,
                 now=lambda: now, log=logs.append)
    return run.execute(), d, c, logs


# ------------------------------------------------------------------ manifest 驗證

@pytest.mark.parametrize("mut, msg", [
    (lambda m: m.update(min_gap_s=0.5), "min_gap_s"),
    (lambda m: m.update(max_requests=601), "max_requests"),
    (lambda m: m.update(max_requests=2), "超過"),
    (lambda m: m.update(schema="x"), "schema"),
    (lambda m: m.update(manifest_id="../x"), "manifest_id"),
    (lambda m: m["window"].update(start="2026-10-30T13:00:00"), "時區"),
    (lambda m: m["requests"][1].update(page="nope"), "最近一個"),
    (lambda m: m["requests"][1]["headers"].update(X={"$token": "C"}), "token"),
    (lambda m: m["requests"][0].update(path="https://evil/x"), "path"),
    (lambda m: m["requests"][1].update(api="//evil.example/x"), "api"),
    (lambda m: m["requests"][2].update(id="q1"), "重複"),
    (lambda m: m["requests"][0].update(require="("), "regex"),
])
def test_manifest_rejects(mut, msg):
    m = _manifest(json.loads(json.dumps(SCHEDULE)))
    mut(m)
    with pytest.raises(pf.ManifestError, match=msg):
        pf.validate_manifest(m)


def test_manifest_rejects_interleaved_page():
    reqs = [SCHEDULE[0], {"id": "p2", "op": "page", "path": "/box"}, SCHEDULE[1]]
    with pytest.raises(pf.ManifestError, match="最近一個"):
        pf.validate_manifest(_manifest(reqs))


def test_check_mode_zero_network(tmp_path, capsys):
    p = tmp_path / "m.json"
    p.write_text(json.dumps(_manifest(SCHEDULE)))
    assert pf.main([str(p), "--out", str(tmp_path / "o"), "--check"]) == 0
    assert json.loads(capsys.readouterr().out)["requests"] == 3
    assert not (tmp_path / "o").exists()


def test_invalid_manifest_exit_65(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps(_manifest(SCHEDULE, min_gap_s=0.2)))
    assert pf.main([str(p), "--out", str(tmp_path / "o")]) == 65


# ------------------------------------------------------------------ 正常路徑

def test_happy_path_bundle_and_token(tmp_path):
    idx, d, c, _ = _run(tmp_path, _manifest(SCHEDULE), [_ok_nav()], [_ok_post(), _ok_post()])
    assert idx["complete"] and idx["stopped"] is None and idx["requests_sent"] == 3
    # token 由頁面 HTML 解出並放進 header；form 原樣
    post = d.calls[1]
    assert post[2]["RequestVerificationToken"] == "tokA123"
    assert "kindCode=A" in post[3]
    assert d.closed
    # bundle：index 每列 sha256 與檔案一致
    bdir = tmp_path / "t-001"
    on_disk = json.loads((bdir / "index.json").read_text())
    assert on_disk == idx
    for e in on_disk["entries"]:
        raw = (bdir / e["body"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == e["sha256"] and len(raw) == e["bytes"]
    # 不在 index／log 裡留 token 值
    assert "tokA123" not in json.dumps(on_disk["entries"])


def test_gap_start_to_start(tmp_path):
    _, _, c, _ = _run(tmp_path, _manifest(SCHEDULE), [_ok_nav()], [_ok_post(), _ok_post()],
                      cost_s=0.3)
    # 每次回應耗 0.3 s，間隔 1.0 s ⇒ 每次補睡 0.7 s（第一個請求不睡）
    assert c.sleeps == pytest.approx([0.7, 0.7])


def test_token_b_into_form(tmp_path):
    reqs = [{"id": "p1", "op": "page", "path": "/box?year=2026&KindCode=A&gameSno=1"},
            {"id": "q1", "op": "post", "page": "p1", "api": "/box/getlive",
             "form": {"GameSno": "1", "__RequestVerificationToken": {"$token": "B"}}}]
    _, d, _, _ = _run(tmp_path, _manifest(reqs), [_ok_nav(HTML_B)], [_ok_post()])
    assert "__RequestVerificationToken=tokB456" in d.calls[1][3]


# ------------------------------------------------------------------ 前兆：第一格就停、不重試

@pytest.mark.parametrize("nav, signal", [
    ({"error": "net::ERR_TOO_MANY_REDIRECTS"}, "S3:goto_error"),
    ({"http_status": 404, "redirects": 0, "html": "x", "error": None}, "S5:nav_status=404"),
    ({"http_status": 200, "redirects": 0, "html": "<html>challenge</html>", "error": None},
     "S1:require_missing"),
    ({"http_status": 200, "redirects": 3, "html": HTML_A, "error": None}, "S3:redirects=3>2"),
])
def test_nav_precursor_stops_without_retry(tmp_path, nav, signal):
    idx, d, _, logs = _run(tmp_path, _manifest(SCHEDULE), [nav], [])
    assert idx["stopped"]["signal"].startswith(signal)
    assert idx["requests_sent"] == 1 and not idx["complete"]
    assert d.calls == [("goto", "/schedule")]          # 沒有重載、沒有 POST
    assert any("stop" in rec for rec in logs)


@pytest.mark.parametrize("post, signal", [
    ({"status": -1, "type": "error", "redirected": False, "text": "TypeError"}, "S2"),
    ({"status": 428, "type": "basic", "redirected": False, "text": ""}, "S2"),
    ({"status": 0, "type": "opaqueredirect", "redirected": False, "text": ""}, "S3"),
    ({"status": 403, "type": "basic", "redirected": False, "text": ""}, "S5:post_status=403"),
    ({"status": 200, "type": "basic", "redirected": False, "text": "<html>"}, "S5:non_json"),
])
def test_post_precursor_stops_without_retry(tmp_path, post, signal):
    idx, d, _, _ = _run(tmp_path, _manifest(SCHEDULE), [_ok_nav()], [post])
    assert idx["stopped"]["signal"].startswith(signal) and idx["stopped"]["at"] == "q1"
    assert [c[0] for c in d.calls] == ["goto", "post"]   # q2 未送、未重載
    # 前兆回應不入 bundle
    assert not (tmp_path / "t-001" / "responses" / "q1.body").exists()


def test_missing_token_does_not_send_post(tmp_path):
    reqs = [{"id": "p1", "op": "page", "path": "/box"},
            {"id": "q1", "op": "post", "page": "p1", "api": "/box/getlive",
             "form": {"__RequestVerificationToken": {"$token": "B"}}}]
    idx, d, _, _ = _run(tmp_path, _manifest(reqs), [_ok_nav(HTML_A)], [])
    assert idx["stopped"]["signal"] == "S1:token_B"
    assert [c[0] for c in d.calls] == ["goto"]


def test_s4_token_combo_change_on_same_page(tmp_path):
    reqs = [{"id": "p1", "op": "page", "path": "/schedule"},
            {"id": "p2", "op": "page", "path": "/schedule"}]
    idx, _, _, _ = _run(tmp_path, _manifest(reqs), [_ok_nav(HTML_A), _ok_nav(HTML_B)], [])
    assert idx["stopped"]["signal"].startswith("S4")


def test_s6_slow_single(tmp_path):
    idx, _, _, _ = _run(tmp_path, _manifest(SCHEDULE), [_ok_nav()], [_ok_post()], cost_s=11)
    assert idx["stopped"]["signal"].startswith("S6:single_ms")


# ------------------------------------------------------------------ 時段窗、上限、大小

def test_outside_window_sends_nothing(tmp_path):
    late = dt.datetime(2026, 10, 30, 14, 0, tzinfo=TZ)
    idx, d, _, _ = _run(tmp_path, _manifest(SCHEDULE), [_ok_nav()], [], now=late)
    assert idx["requests_sent"] == 0 and d.calls == []
    assert idx["stopped"]["signal"].startswith("window:outside")


def test_body_size_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(pf, "MAX_BODY_BYTES", 10)
    idx, d, _, _ = _run(tmp_path, _manifest(SCHEDULE), [_ok_nav()], [])
    assert idx["stopped"]["signal"].startswith("size:body")
    assert [c[0] for c in d.calls] == ["goto"]


def test_existing_bundle_not_overwritten(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps(_manifest(SCHEDULE)))
    (tmp_path / "o" / "t-001").mkdir(parents=True)
    (tmp_path / "o" / "t-001" / "index.json").write_text("{}")
    assert pf.main([str(p), "--out", str(tmp_path / "o")]) == 75


def test_no_repo_imports():
    """樹莓派上不裝 cpbl：取源器只能 import 標準庫＋playwright。"""
    import ast
    tree = ast.parse(_PATH.read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            mods.add((node.module or "").split(".")[0])
    import sys
    third = {m for m in mods if m and m not in sys.stdlib_module_names and m != "__future__"}
    assert third == {"playwright"}
