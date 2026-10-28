#!/usr/bin/env python3
# LIFECYCLE: standing · 常設工具——這就是給你跑的；不要刪
"""外部心跳服務（healthchecks.io）的 ping／Management API 小模組（#358 WP1）。

用途：讓每日鏈（`refresh_status.py` 的 start／finish）與本機 watcher job（`com.cpbl.alert-watch`）
把「開始／結束碼／失敗」送到 Mac 以外的服務；告警由該服務在**期限到還沒收到成功**時發出
（沉默就告警，需求方裁定 #358 6348735853 第 1、2 項）。Mac 睡著、斷網、程序被砍都表現成
「沒有 ping」，偵測端不受睡眠影響。

## 三條硬約束

1. **fail-open**（驗收 6，需求方 6429229525）：本模組任何函式都**不往外拋例外**。逾時、
   斷網、服務錯誤、金鑰缺席只回傳 `Result(ok=False)`；呼叫端照常寫狀態、照常退出。
   ping 遺失只會變成稍晚的期限告警，不會變成假成功（判斷看的是沉默）。
2. **金鑰只住 `.env`**（規劃 1 §3.3、裁定 8）：只從 `.env` 檔讀 `CPBL_HC_PING_KEY`／
   `CPBL_HC_API_KEY`，⛔ 不從行程環境讀金鑰。行程環境只能指定讀哪一份 `.env`
   （`CPBL_ALERT_ENV_FILE`）與把所有 ping 改道到 TEST check（`CPBL_ALERT_SLUG_OVERRIDE`，
   故障注入專用）。`.env` 預設是**當下工作目錄**的 `.env`：launchd 的 WorkingDirectory 與
   `scrape-daily.sh` 的 `cd "$REPO_DIR"` 都是 repo 根；測試在暫存目錄跑，天然讀不到正式金鑰。
   ⛔ 不改成「腳本所在 repo 的 .env」：`tests/test_refresh_status.py` 直接執行主 checkout 的
   腳本，那樣 pytest 會打正式 check。
3. **只送狀態與 exit code，不送 log 內容**；輸出的任何字串都先遮罩金鑰與 ping URL。

stdlib only、相容 Python 3.9（launchd 走系統 `/usr/bin/python3`）。

## 呼叫

    python3 scripts/alert_ping.py status             # 只印各設定「有／沒有」，不印值
    python3 scripts/alert_ping.py status --env-file <path>

程式內：`load_config()` → `ping(config, CHECK_DAILY, "start", rid=...)`／
`arm_schedule(config, CHECK_EVENING, cron=..., tz=..., grace_seconds=...)`。

已實測（#358 exec-2a §1.4，TEST check）：Management API v3 以 `?slug=` 篩選、可寫金鑰的回應帶
`update_url`、POST `schedule`／`tz`／`grace` 可改排程；timeout／grace 上限 31536000 秒。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

# check 名（slug）——需求方在 healthchecks 建立的四個 check（#358 規劃 2 §9）。
# 須與 scripts/schedule-registry.json 各 job 的 alert.check 一致（對帳測試隨登記段落提供）。
CHECK_DAILY = "daily"
CHECK_EVENING = "evening"
CHECK_SERVICES = "services"
CHECK_TEST = "test"

ENV_PING_KEY = "CPBL_HC_PING_KEY"
ENV_API_KEY = "CPBL_HC_API_KEY"
ENV_PING_BASE = "CPBL_HC_PING_BASE"
ENV_API_BASE = "CPBL_HC_API_BASE"
ENV_TIMEOUT = "CPBL_HC_TIMEOUT_SECONDS"
PROC_ENV_FILE = "CPBL_ALERT_ENV_FILE"
PROC_SLUG_OVERRIDE = "CPBL_ALERT_SLUG_OVERRIDE"

DEFAULT_PING_BASE = "https://hc-ping.com"
DEFAULT_API_BASE = "https://healthchecks.io/api/v3"
# 規劃 1 §3.3：timeout 約 10 秒、少量重試。最壞 3×10 秒＋退避 3 秒，每日鏈多等約半分鐘。
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 2.0)
MAX_BODY_BYTES = 1000
USER_AGENT = "cpbl-alert-ping/1.0 (+#358)"
_MASK = "***"
_PING_URL_RE = re.compile(r"https?://[^\s'\"]*hc-ping[^\s'\"]*")

Opener = Callable[..., object]


@dataclass(frozen=True)
class Config:
    ping_key: str
    api_key: str
    ping_base: str
    api_base: str
    timeout: float
    slug_override: str
    source: str

    @property
    def ping_ready(self) -> bool:
        return bool(self.ping_key)

    @property
    def api_ready(self) -> bool:
        return bool(self.api_key)

    def slug(self, check: str) -> str:
        return self.slug_override or check

    def mask(self, text: object) -> str:
        out = str(text)
        for secret in (self.ping_key, self.api_key):
            if secret:
                out = out.replace(secret, _MASK)
        return _PING_URL_RE.sub("<ping-url>", out)


@dataclass(frozen=True)
class Result:
    action: str
    check: str
    attempted: bool
    ok: bool
    status: int | None = None
    detail: str = ""

    def summary(self) -> str:
        state = "ok" if self.ok else ("skipped" if not self.attempted else "failed")
        code = f" http={self.status}" if self.status is not None else ""
        return f"alert {self.action} check={self.check} {state}{code} {self.detail}".rstrip()


def parse_env_file(path: Path) -> dict:
    """`.env` 的最小解析：`KEY=VALUE`、`#` 註解、空行、`export `、成對引號。讀不到回 {}。"""
    values: dict = {}
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return values
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_config(env_file: Path | None = None,
                environ: Mapping[str, str] | None = None) -> Config:
    environ = os.environ if environ is None else environ
    if env_file is None:
        env_file = Path(environ.get(PROC_ENV_FILE) or ".env")
    values = parse_env_file(Path(env_file))
    try:
        timeout = float(values.get(ENV_TIMEOUT) or DEFAULT_TIMEOUT_SECONDS)
        if timeout <= 0:
            timeout = DEFAULT_TIMEOUT_SECONDS
    except ValueError:
        timeout = DEFAULT_TIMEOUT_SECONDS
    return Config(
        ping_key=values.get(ENV_PING_KEY, "").strip(),
        api_key=values.get(ENV_API_KEY, "").strip(),
        ping_base=(values.get(ENV_PING_BASE) or DEFAULT_PING_BASE).rstrip("/"),
        api_base=(values.get(ENV_API_BASE) or DEFAULT_API_BASE).rstrip("/"),
        timeout=timeout,
        slug_override=(environ.get(PROC_SLUG_OVERRIDE) or "").strip(),
        source=str(env_file),
    )


def missing_settings(config: Config, need_api: bool = False) -> list:
    missing = [] if config.ping_ready else [ENV_PING_KEY]
    if need_api and not config.api_ready:
        missing.append(ENV_API_KEY)
    return missing


def run_id(seed: str) -> str:
    """start／結束配對用的 `rid`：同一 seed（每日鏈的 started_at）恆得同一個 UUID。"""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"cpbl-analytics/358/{seed}"))


def _retryable(error: BaseException) -> bool:
    if isinstance(error, urllib.error.HTTPError):
        return error.code >= 500 or error.code == 429
    return isinstance(error, (urllib.error.URLError, socket.timeout, TimeoutError,
                              ConnectionError, OSError))


def _request(config: Config, request: urllib.request.Request, *, opener: Opener | None,
             sleep: Callable[[float], None]) -> tuple:
    """回 (ok, http_status, detail, body_bytes)。⛔ 不拋例外。"""
    opener = opener or urllib.request.urlopen
    last_detail = ""
    status: int | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            with opener(request, timeout=config.timeout) as response:
                status = int(getattr(response, "status", None) or response.getcode())
                body = response.read()
            if 200 <= status < 300:
                return True, status, "", body
            last_detail = f"unexpected status {status}"
        except Exception as error:  # noqa: BLE001 — fail-open 是驗收 6 本身
            status = error.code if isinstance(error, urllib.error.HTTPError) else None
            last_detail = f"{type(error).__name__}: {getattr(error, 'reason', None) or error}"
            if not _retryable(error):
                break
        if attempt + 1 < MAX_ATTEMPTS:
            try:
                sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
            except Exception:  # noqa: BLE001
                pass
    return False, status, config.mask(last_detail), b""


def ping(config: Config, check: str, signal: object, *, rid: str | None = None,
         body: str = "", opener: Opener | None = None,
         sleep: Callable[[float], None] = time.sleep) -> Result:
    """送一個 ping。`signal`：`"start"`／`"success"`／`"fail"`／整數 exit code（0＝成功）。"""
    action = f"ping:{signal}"
    try:
        if not config.ping_ready:
            return Result(action, check, False, False, None, f"{ENV_PING_KEY} 未設定，不動作")
        if signal == "success":
            suffix = ""
        elif signal in ("start", "fail"):
            suffix = f"/{signal}"
        elif isinstance(signal, int) and not isinstance(signal, bool) and 0 <= signal <= 255:
            suffix = f"/{signal}"
        else:
            return Result(action, check, False, False, None, f"未知訊號 {signal!r}")
        url = f"{config.ping_base}/{config.ping_key}/{config.slug(check)}{suffix}"
        if rid:
            url += "?" + urllib.parse.urlencode({"rid": rid})
        data = body.encode("utf-8", errors="replace")[:MAX_BODY_BYTES]
        request = urllib.request.Request(url, data=data, method="POST",
                                         headers={"User-Agent": USER_AGENT})
        ok, status, detail, _ = _request(config, request, opener=opener, sleep=sleep)
        return Result(action, config.slug(check), True, ok, status, detail)
    except Exception as error:  # noqa: BLE001 — fail-open
        return Result(action, check, True, False, None, config.mask(f"{type(error).__name__}: {error}"))


def arm_schedule(config: Config, check: str, *, cron: str, tz: str, grace_seconds: int,
                 opener: Opener | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> Result:
    """以 Management API 把 check 改成 `cron`／`tz`／`grace`（晚間鏈的「當天有賽才武裝」）。

    先以 slug 查出**唯一**一個可寫的 check（回應須帶 `update_url`）才 POST；查無、不唯一、
    唯讀金鑰一律不寫（fail closed＝不武裝，結果由每日鏈 `daily` 與既有本機偵測承接）。
    """
    action = "arm"
    slug = config.slug(check)
    try:
        if not config.api_ready:
            return Result(action, slug, False, False, None, f"{ENV_API_KEY} 未設定，不動作")
        headers = {"User-Agent": USER_AGENT, "X-Api-Key": config.api_key}
        lookup = urllib.request.Request(
            f"{config.api_base}/checks/?" + urllib.parse.urlencode({"slug": slug}),
            headers=headers, method="GET")
        ok, status, detail, body = _request(config, lookup, opener=opener, sleep=sleep)
        if not ok:
            return Result(action, slug, True, False, status, f"查詢失敗 {detail}".strip())
        try:
            checks = json.loads(body.decode("utf-8")).get("checks") or []
        except (ValueError, AttributeError):
            return Result(action, slug, True, False, status, "查詢回應不是預期的 JSON")
        matched = [c for c in checks if isinstance(c, dict) and c.get("slug") == slug]
        if len(matched) != 1:
            return Result(action, slug, True, False, status, f"slug={slug} 符合 {len(matched)} 個 check")
        update_url = matched[0].get("update_url")
        if not update_url:
            return Result(action, slug, True, False, status, "回應沒有 update_url（唯讀金鑰？）")
        payload = json.dumps({"schedule": cron, "tz": tz, "grace": int(grace_seconds)}).encode("utf-8")
        update = urllib.request.Request(update_url, data=payload, method="POST",
                                        headers={**headers, "Content-Type": "application/json"})
        ok, status, detail, _ = _request(config, update, opener=opener, sleep=sleep)
        note = f"schedule={cron} tz={tz} grace={int(grace_seconds)}"
        return Result(action, slug, True, ok, status, f"{note} {detail}".strip())
    except Exception as error:  # noqa: BLE001 — fail-open
        return Result(action, slug, True, False, None, config.mask(f"{type(error).__name__}: {error}"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alert_ping.py",
        description="外部心跳服務的 ping 模組（#358）。CLI 只提供唯讀的設定檢查。",
        epilog=("在做什麼：status 只讀 .env，印出告警設定各鍵「set／missing」，不印值、不連網。\n"
                "會寫什麼：不寫任何檔案。\n"
                "怎麼呼叫：python3 scripts/alert_ping.py status [--env-file .env]"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="印出各設定鍵是否存在（不印值）")
    status.add_argument("--env-file", type=Path, default=None)
    return parser


def main(argv: list | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.env_file)
    print(f"env_file={config.source}")
    for key, present in ((ENV_PING_KEY, config.ping_ready), (ENV_API_KEY, config.api_ready)):
        print(f"{key}={'set' if present else 'missing'}")
    if config.slug_override:
        print(f"{PROC_SLUG_OVERRIDE}={config.slug_override}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
