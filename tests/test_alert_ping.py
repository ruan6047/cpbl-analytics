"""#358 WP1：外部心跳服務 ping／Management API 模組的行為守衛。

驗收 6（需求方 2026-10-27 裁定 6429229525）：所有告警 ping 一律 fail-open——逾時、斷網、
服務錯誤、金鑰缺席都不得往外拋，呼叫端（每日鏈／watcher）的退出碼與狀態寫入不受影響。
本檔逐類各釘一個 case；「接到呼叫端之後 rc 與狀態檔不變」另由 `tests/test_refresh_status.py`
（PR-1）與 `tests/test_alert_watch.py`（PR-2）以真實子行程證明。

決定性：全部用注入的 opener／sleep，**不觸網、不呼叫任何告警服務**。金鑰一律是合成值。
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
MODULE = ROOT / "scripts" / "alert_ping.py"

FAKE_PING_KEY = "pk-synthetic-0123456789abcdef"
FAKE_API_KEY = "ak-synthetic-fedcba9876543210"


def _load():
    spec = importlib.util.spec_from_file_location("_alert_ping", MODULE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclass 需要模組已登記
    spec.loader.exec_module(module)
    return module


ap = _load()


def _env(tmp_path: Path, **values: str) -> Path:
    path = tmp_path / ".env"
    lines = ["# 既有設定（真實 .env 的形狀：註解、空行、無引號、有引號）", "",
             "DATABASE_URL=postgresql://cpbl:cpbl@localhost:5433/cpbl"]
    lines += [f"{k}={v}" for k, v in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _config(tmp_path: Path, **extra: str):
    values = {ap.ENV_PING_KEY: FAKE_PING_KEY, ap.ENV_API_KEY: f'"{FAKE_API_KEY}"'}
    values.update(extra)
    return ap.load_config(_env(tmp_path, **values), environ={})


class _Response(io.BytesIO):
    def __init__(self, status: int = 200, body: bytes = b"OK") -> None:
        super().__init__(body)
        self.status = status

    def getcode(self) -> int:
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class _Recorder:
    """依序回傳／拋出預先排好的結果，並記下每個請求。"""

    def __init__(self, *outcomes) -> None:
        self.outcomes = list(outcomes)
        self.requests = []

    def __call__(self, request, timeout):  # noqa: ANN001
        self.requests.append((request, timeout))
        outcome = self.outcomes.pop(0) if self.outcomes else _Response()
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _no_sleep(_seconds: float) -> None:
    return None


# ----------------------------------------------------------------- 設定讀取

def test_env_file_parsing_tolerates_real_shapes(tmp_path: Path) -> None:
    config = _config(tmp_path)
    assert config.ping_key == FAKE_PING_KEY
    assert config.api_key == FAKE_API_KEY  # 引號被剝掉
    assert config.ping_ready and config.api_ready
    assert config.ping_base == ap.DEFAULT_PING_BASE
    assert config.timeout == ap.DEFAULT_TIMEOUT_SECONDS


def test_missing_env_file_is_not_configured_and_never_raises(tmp_path: Path) -> None:
    config = ap.load_config(tmp_path / "nope.env", environ={})
    assert not config.ping_ready and not config.api_ready
    assert ap.missing_settings(config, need_api=True) == [ap.ENV_PING_KEY, ap.ENV_API_KEY]


def test_process_env_cannot_supply_keys(tmp_path: Path) -> None:
    """金鑰只住 `.env`（規劃 1 §3.3）；行程環境只能指定 `.env` 路徑與 TEST 改道。"""
    config = ap.load_config(tmp_path / "nope.env", environ={ap.ENV_PING_KEY: FAKE_PING_KEY})
    assert not config.ping_ready


def test_env_file_override_and_slug_override(tmp_path: Path) -> None:
    other = tmp_path / "fi" / "test.env"
    other.parent.mkdir()
    other.write_text(f"{ap.ENV_PING_KEY}={FAKE_PING_KEY}\n", encoding="utf-8")
    config = ap.load_config(None, environ={ap.PROC_ENV_FILE: str(other),
                                           ap.PROC_SLUG_OVERRIDE: ap.CHECK_TEST})
    assert config.ping_ready and config.slug_override == ap.CHECK_TEST
    opener = _Recorder(_Response())
    ap.ping(config, ap.CHECK_DAILY, "start", opener=opener, sleep=_no_sleep)
    assert opener.requests[0][0].full_url.endswith(f"/{FAKE_PING_KEY}/{ap.CHECK_TEST}/start")


# ------------------------------------------------------------------- URL 形狀

@pytest.mark.parametrize(("signal", "suffix"), [
    ("start", "/start"), ("success", ""), ("fail", "/fail"), (0, "/0"), (69, "/69"), (127, "/127"),
])
def test_ping_url_per_signal(tmp_path: Path, signal, suffix: str) -> None:
    config = _config(tmp_path)
    opener = _Recorder(_Response())
    result = ap.ping(config, ap.CHECK_DAILY, signal, rid="r-1", opener=opener, sleep=_no_sleep)
    assert result.ok and result.attempted
    url = opener.requests[0][0].full_url
    assert url == f"{ap.DEFAULT_PING_BASE}/{FAKE_PING_KEY}/{ap.CHECK_DAILY}{suffix}?rid=r-1"
    assert opener.requests[0][1] == ap.DEFAULT_TIMEOUT_SECONDS


def test_run_id_is_deterministic_uuid(tmp_path: Path) -> None:
    a = ap.run_id("2026-10-22T10:14:35+0800")
    assert a == ap.run_id("2026-10-22T10:14:35+0800")
    assert a != ap.run_id("2026-10-23T10:10:01+0800")
    assert len(a) == 36 and a.count("-") == 4


def test_fail_body_is_sent_but_truncated(tmp_path: Path) -> None:
    config = _config(tmp_path)
    opener = _Recorder(_Response())
    ap.ping(config, ap.CHECK_SERVICES, "fail", body="x" * 5000, opener=opener, sleep=_no_sleep)
    assert len(opener.requests[0][0].data) == ap.MAX_BODY_BYTES


# ---------------------------------------------------- 驗收 6：fail-open 四類

def test_missing_key_does_nothing(tmp_path: Path) -> None:
    config = ap.load_config(tmp_path / "nope.env", environ={})
    opener = _Recorder()
    result = ap.ping(config, ap.CHECK_DAILY, "start", opener=opener, sleep=_no_sleep)
    assert result.attempted is False and result.ok is False
    assert "未設定" in result.detail
    assert opener.requests == []


def test_timeout_is_retried_then_swallowed(tmp_path: Path) -> None:
    config = _config(tmp_path)
    opener = _Recorder(TimeoutError("timed out"), TimeoutError("timed out"),
                       TimeoutError("timed out"))
    result = ap.ping(config, ap.CHECK_DAILY, 0, opener=opener, sleep=_no_sleep)
    assert result.attempted and not result.ok
    assert len(opener.requests) == ap.MAX_ATTEMPTS
    assert "timed out" in result.detail


def test_connection_failure_is_swallowed(tmp_path: Path) -> None:
    config = _config(tmp_path)
    refused = urllib.error.URLError(ConnectionRefusedError(61, "Connection refused"))
    opener = _Recorder(refused, refused, refused)
    result = ap.ping(config, ap.CHECK_DAILY, "start", opener=opener, sleep=_no_sleep)
    assert not result.ok and len(opener.requests) == ap.MAX_ATTEMPTS


def test_http_5xx_is_retried_and_4xx_is_not(tmp_path: Path) -> None:
    config = _config(tmp_path)

    def http_error(code: int) -> urllib.error.HTTPError:
        return urllib.error.HTTPError("https://x", code, "err", {}, io.BytesIO(b""))

    opener = _Recorder(http_error(503), http_error(503), _Response())
    assert ap.ping(config, ap.CHECK_DAILY, 0, opener=opener, sleep=_no_sleep).ok
    assert len(opener.requests) == 3

    opener = _Recorder(http_error(404))
    result = ap.ping(config, ap.CHECK_DAILY, 0, opener=opener, sleep=_no_sleep)
    assert not result.ok and result.status == 404 and len(opener.requests) == 1


def test_unexpected_exception_is_swallowed(tmp_path: Path) -> None:
    config = _config(tmp_path)
    opener = _Recorder(RuntimeError("boom"))
    result = ap.ping(config, ap.CHECK_DAILY, 0, opener=opener, sleep=_no_sleep)
    assert result.attempted and not result.ok and "boom" in result.detail


def test_secrets_never_appear_in_detail(tmp_path: Path) -> None:
    config = _config(tmp_path)
    leak = urllib.error.URLError(f"cannot reach {ap.DEFAULT_PING_BASE}/{FAKE_PING_KEY}/daily "
                                 f"key={FAKE_API_KEY}")
    result = ap.ping(config, ap.CHECK_DAILY, 0, opener=_Recorder(leak, leak, leak), sleep=_no_sleep)
    assert FAKE_PING_KEY not in result.detail and FAKE_API_KEY not in result.detail
    assert FAKE_PING_KEY not in result.summary() and "***" in result.detail


# ------------------------------------------------------- Management API 武裝

def _checks_response(*checks: dict) -> _Response:
    return _Response(200, json.dumps({"checks": list(checks)}).encode("utf-8"))


def test_arm_schedule_looks_up_by_slug_then_updates(tmp_path: Path) -> None:
    config = _config(tmp_path)
    update_url = "https://healthchecks.io/api/v3/checks/00000000-0000-0000-0000-000000000000"
    opener = _Recorder(_checks_response({"slug": "evening", "update_url": update_url}), _Response())
    result = ap.arm_schedule(config, ap.CHECK_EVENING, cron="35 18 27 10 *",
                             tz="Asia/Taipei", grace_seconds=18000, opener=opener, sleep=_no_sleep)
    assert result.ok, result.detail
    lookup, update = opener.requests[0][0], opener.requests[1][0]
    assert lookup.full_url == f"{ap.DEFAULT_API_BASE}/checks/?slug=evening"
    assert lookup.get_header("X-api-key") == FAKE_API_KEY
    assert update.full_url == update_url and update.get_method() == "POST"
    assert json.loads(update.data) == {"schedule": "35 18 27 10 *", "tz": "Asia/Taipei",
                                       "grace": 18000}


@pytest.mark.parametrize("checks", [
    (),                                                     # 查無此 check
    ({"slug": "evening"}, {"slug": "evening"}),             # 不唯一
    ({"slug": "evening", "unique_key": "abc"},),            # 唯讀金鑰：沒有 update_url
])
def test_arm_schedule_fails_closed_without_a_unique_writable_check(tmp_path: Path, checks) -> None:
    config = _config(tmp_path)
    opener = _Recorder(_checks_response(*checks))
    result = ap.arm_schedule(config, ap.CHECK_EVENING, cron="35 18 27 10 *", tz="Asia/Taipei",
                             grace_seconds=18000, opener=opener, sleep=_no_sleep)
    assert result.attempted and not result.ok
    assert len(opener.requests) == 1  # 不會盲目 POST


def test_arm_schedule_without_api_key_does_nothing(tmp_path: Path) -> None:
    config = ap.load_config(_env(tmp_path, **{ap.ENV_PING_KEY: FAKE_PING_KEY}), environ={})
    opener = _Recorder()
    result = ap.arm_schedule(config, ap.CHECK_EVENING, cron="35 18 27 10 *", tz="Asia/Taipei",
                             grace_seconds=18000, opener=opener, sleep=_no_sleep)
    assert not result.attempted and opener.requests == []


def test_arm_schedule_network_failure_is_swallowed(tmp_path: Path) -> None:
    config = _config(tmp_path)
    opener = _Recorder(TimeoutError("t"), TimeoutError("t"), TimeoutError("t"))
    result = ap.arm_schedule(config, ap.CHECK_EVENING, cron="35 18 27 10 *", tz="Asia/Taipei",
                             grace_seconds=18000, opener=opener, sleep=_no_sleep)
    assert result.attempted and not result.ok


def test_slug_override_redirects_api_lookup_too(tmp_path: Path) -> None:
    config = ap.load_config(_env(tmp_path, **{ap.ENV_PING_KEY: FAKE_PING_KEY,
                                              ap.ENV_API_KEY: FAKE_API_KEY}),
                            environ={ap.PROC_SLUG_OVERRIDE: ap.CHECK_TEST})
    opener = _Recorder(_checks_response())
    ap.arm_schedule(config, ap.CHECK_EVENING, cron="35 18 27 10 *", tz="Asia/Taipei",
                    grace_seconds=18000, opener=opener, sleep=_no_sleep)
    assert opener.requests[0][0].full_url.endswith("?slug=test")


# ------------------------------------------------------------------- CLI

def test_cli_status_reports_presence_without_values(tmp_path: Path, capsys) -> None:
    env = _env(tmp_path, **{ap.ENV_PING_KEY: FAKE_PING_KEY})
    rc = ap.main(["status", "--env-file", str(env)])
    out = capsys.readouterr().out
    assert rc == 0
    assert FAKE_PING_KEY not in out
    assert f"{ap.ENV_PING_KEY}=set" in out and f"{ap.ENV_API_KEY}=missing" in out


def test_module_is_python39_stdlib_only() -> None:
    """launchd 走系統 /usr/bin/python3（3.9）；不得 import 第三方套件。"""
    import ast
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    allowed = {"__future__", "argparse", "collections", "dataclasses", "json", "os", "re", "socket", "sys",
               "time", "typing", "urllib", "uuid", "pathlib"}
    assert imported <= allowed, imported - allowed
