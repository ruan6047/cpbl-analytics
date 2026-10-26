#!/usr/bin/env python3
# LIFECYCLE: standing · 常設工具——每日鏈與主站部署都會呼叫；不要刪
"""正式站可用性偵測器（#353 WP4）：每日鏈哨兵（sentinel）＋部署後首請求探針（probe）。

用法：
  python3 scripts/prod_availability.py --help
  python3 scripts/prod_availability.py sentinel --stop-file F --out TSV [--base-url URL] [--env-file .env]
  python3 scripts/prod_availability.py probe [--base-url URL] [--env-file .env]

只量正式站 HTTP（``curl -m 10``），不讀 DB、不在 VPS 加常駐行程。判準與 #353 驗收同一條：任一筆
http=000 或耗時 ≥5s 即不合格；**樣本數 0 也是不合格**（fail-closed：量不到不能讀成沒事）。
不合格 ⇒ 送告警到 #358 的同一個收件處（healthchecks 類 check 的 ``/fail``，email 推手機）；合格 ⇒ 送
一次成功 ping，讓 check 從 down 恢復、下一次事故才會再通知。

⛔ 兩個子命令一律以 0 結束：哨兵／探針失敗不得讓每日鏈或部署失敗（規劃 r2 §3 WP4a／WP4b）。
⛔ 告警內容只放計數、最慢值、時段與端點代號，不放 URL、金鑰、check 位址或信箱。
⛔ 輪詢間隔不得小於 15 秒：被卡住的請求會占用一條伺服器端連線，量測本身就是擾動（研究 2）。

告警通道設定（值由需求方建立，本工具只讀鍵、從不印出值）：
  CPBL_AVAILABILITY_PING_URL  healthchecks check 的 ping URL。先讀環境變數，沒有才讀 --env-file 的同名鍵；
                              都沒有 ⇒ 只寫 log、不送（印出「未設定告警通道」）。
只用 Python 標準庫：主站 GitHub Actions runner 直接以 python3 執行（不裝本專案依賴）。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DEFAULT_BASE_URL = "https://cpbl.ruan-ruan.com"
PING_ENV = "CPBL_AVAILABILITY_PING_URL"
THRESHOLD_SECONDS = 5.0          # 驗收門檻：≥5s 即不合格（主站 InfoPoller 5 秒 timeout）
CURL_MAX_TIME = 10               # curl -m 10
MIN_INTERVAL_SECONDS = 15.0
SENTINEL_INTERVAL_SECONDS = 15.0
SENTINEL_TAIL_SECONDS = 120.0    # 第 4 步結束後再量 120 秒（規劃 r2 §3 WP4a）
SENTINEL_MAX_SECONDS = 6 * 3600  # 保險絲：收不到停止訊號時最多跑 6 小時
PROBE_REPEATS = 5
PROBE_SPACING_SECONDS = 10.0

# D1 A：端點代號 → 路徑。recap-wp 取一場固定已完賽場：全年都會讀 PA 表（季後賽結束後 watch 可能不再讀）。
SENTINEL_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("info", "/api/info"),
    ("watch", "/api/v1/playoffs/watch"),
    ("recap-wp", "/api/v1/games/1/recap-wp?season=2026&kind_code=A"),
)
PROBE_FIRST: tuple[tuple[str, str], ...] = (
    ("health", "/health"),
    ("healthz", "/healthz"),
    ("info", "/api/info"),
)


@dataclass(frozen=True)
class Sample:
    at: float
    label: str
    code: str        # curl 的 %{http_code}；連不上／逾時為 "000"
    seconds: float   # %{time_total}
    connect: float = 0.0
    starttransfer: float = 0.0


def curl_sample(base_url: str, label: str, path: str) -> Sample:
    at = time.time()
    try:
        out = subprocess.run(
            ["curl", "-sS", "-o", "/dev/null", "-m", str(CURL_MAX_TIME),
             "-w", "%{http_code} %{time_connect} %{time_starttransfer} %{time_total}", base_url + path],
            capture_output=True, text=True, timeout=CURL_MAX_TIME + 5, check=False,
        ).stdout.split()
        code, connect, start, total = out[0], float(out[1]), float(out[2]), float(out[3])
    except Exception:  # noqa: BLE001 — 任何量不到的情形都是 000
        code, connect, start, total = "000", 0.0, 0.0, time.time() - at
    return Sample(at, label, code, total, connect, start)


def judge(samples: Sequence[Sample], labels: set[str] | None = None) -> dict:
    """``labels`` 指定納入判定的端點（None＝全部）。回傳 ok 與摘要（不含任何 URL）。"""
    pool = [s for s in samples if labels is None or s.label in labels]
    n000 = sum(1 for s in pool if s.code == "000")
    slow = sum(1 for s in pool if s.code != "000" and s.seconds >= THRESHOLD_SECONDS)
    non2xx = sum(1 for s in pool if s.code != "000" and not s.code.startswith("2"))
    worst = max(pool, key=lambda s: s.seconds, default=None)
    return {
        "ok": bool(pool) and n000 == 0 and slow == 0,
        "samples": len(pool), "n000": n000, "slow": slow, "non2xx": non2xx,
        "slowest_seconds": round(worst.seconds, 3) if worst else None,
        "slowest_label": worst.label if worst else None,
        "first": _hm(pool[0].at) if pool else None, "last": _hm(pool[-1].at) if pool else None,
    }


def _hm(epoch: float) -> str:
    return datetime.fromtimestamp(epoch).strftime("%H:%M:%S")


def summary_text(kind: str, verdict: dict) -> str:
    state = "OK" if verdict["ok"] else "FAIL"
    return (f"cpbl prod availability {kind} {state}: samples={verdict['samples']} "
            f"http000={verdict['n000']} ge{THRESHOLD_SECONDS:g}s={verdict['slow']} "
            f"non2xx={verdict['non2xx']} slowest={verdict['slowest_seconds']}s({verdict['slowest_label']}) "
            f"window={verdict['first']}-{verdict['last']}")


def ping_url(env_file: str | None, environ: Mapping[str, str] | None = None) -> str | None:
    env: Mapping[str, str] = os.environ if environ is None else environ
    value = (env.get(PING_ENV) or "").strip()
    if value:
        return value
    if env_file and Path(env_file).is_file():
        for line in Path(env_file).read_text(encoding="utf-8").splitlines():
            key, sep, raw = line.strip().partition("=")
            if sep and key.strip() == PING_ENV:
                return raw.strip().strip('"').strip("'") or None
    return None


def send(url: str | None, ok: bool, body: str, opener: Callable = urllib.request.urlopen) -> str:
    """送 ping；回傳寫進 log 的一句話（⛔ 不含 URL）。任何失敗只回報、不拋。"""
    if not url:
        return "未設定告警通道（CPBL_AVAILABILITY_PING_URL）：只寫 log、未送"
    target = url.rstrip("/") + ("" if ok else "/fail")
    try:
        req = urllib.request.Request(target, data=body.encode("utf-8"), method="POST",
                                     headers={"Content-Type": "text/plain; charset=utf-8"})
        with opener(req, timeout=10) as resp:
            return f"已送{'成功 ping' if ok else '告警'}（HTTP {getattr(resp, 'status', '?')}）"
    except Exception as exc:  # noqa: BLE001
        return f"送{'成功 ping' if ok else '告警'}失敗（{type(exc).__name__}）：只寫 log"


def write_tsv(path: Path, samples: Sequence[Sample]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write("epoch\tlocal_time\tendpoint\thttp_code\ttime_total\ttime_connect\ttime_starttransfer\n")
        for s in samples:
            fh.write(f"{s.at:.3f}\t{_hm(s.at)}\t{s.label}\t{s.code}\t{s.seconds:.6f}\t"
                     f"{s.connect:.6f}\t{s.starttransfer:.6f}\n")


def run_sentinel(*, base_url: str, stop_file: Path, interval: float = SENTINEL_INTERVAL_SECONDS,
                 tail: float = SENTINEL_TAIL_SECONDS, max_seconds: float = SENTINEL_MAX_SECONDS,
                 sample: Callable[[str, str, str], Sample] = curl_sample,
                 now: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
                 parent_alive: Callable[[], bool] = lambda: True) -> list[Sample]:
    """每 ``interval`` 秒對 D1 端點各打一次，直到停止訊號後再 ``tail`` 秒。"""
    interval = max(float(interval), MIN_INTERVAL_SECONDS)
    started = now()
    stop_at: float | None = None
    samples: list[Sample] = []
    while True:
        tick = now()
        for label, path in SENTINEL_ENDPOINTS:
            samples.append(sample(base_url, label, path))
        while now() - tick < interval:
            if stop_at is None and (stop_file.exists() or not parent_alive()
                                    or now() - started >= max_seconds):
                stop_at = now()
            if stop_at is not None and now() - stop_at >= tail:
                return samples
            sleep(0.5)
        if stop_at is not None and now() - stop_at >= tail:
            return samples


def run_probe(*, base_url: str, sample: Callable[[str, str, str], Sample] = curl_sample,
              sleep: Callable[[float], None] = time.sleep) -> list[Sample]:
    samples = [sample(base_url, label, path) for label, path in PROBE_FIRST]
    for _ in range(PROBE_REPEATS):
        sleep(PROBE_SPACING_SECONDS)
        samples.append(sample(base_url, "info", "/api/info"))
    return samples


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="prod_availability.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("sentinel", "probe"):
        s = sub.add_parser(name)
        s.add_argument("--base-url", default=DEFAULT_BASE_URL)
        s.add_argument("--env-file", default=None)
        if name == "sentinel":
            s.add_argument("--stop-file", required=True)
            s.add_argument("--out", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    base = args.base_url.rstrip("/")
    try:
        if args.command == "sentinel":
            parent = os.getppid()
            samples = run_sentinel(base_url=base, stop_file=Path(args.stop_file),
                                   parent_alive=lambda: os.getppid() == parent)
            write_tsv(Path(args.out), samples)
            verdict = judge(samples)
        else:
            samples = run_probe(base_url=base)
            for s in samples:
                print(f"probe {s.label} http={s.code} connect={s.connect:.3f}s "
                      f"starttransfer={s.starttransfer:.3f}s total={s.seconds:.3f}s", flush=True)
            verdict = judge(samples, labels={"info"})
        text = summary_text(args.command, verdict)
        print(f"    ⓘ {text}", flush=True)
        print(f"    ⓘ {send(ping_url(args.env_file), verdict['ok'], text)}", flush=True)
    except Exception as exc:  # noqa: BLE001 — 偵測器自身失敗：不改變呼叫端成敗，但照樣告警
        # fail-closed：量測沒完成＝沒有「全部合格」的證據，與 0 樣本同等處理。
        print(f"    ⚠ prod_availability {args.command} 自身失敗（{type(exc).__name__}）；"
              "不影響呼叫端", file=sys.stderr, flush=True)
        try:
            text = f"cpbl prod availability {args.command} FAIL: detector error {type(exc).__name__}"
            print(f"    ⓘ {send(ping_url(args.env_file), False, text)}", flush=True)
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
