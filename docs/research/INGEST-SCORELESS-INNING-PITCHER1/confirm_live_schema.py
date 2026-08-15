"""單次確認請求：對一場「未落在 G4 保存樣本內」的完成場重取 schema。

**冪等且不重打**：`payloads/<gid>.json.gz` 已存在就直接讀檔，不發任何請求
（artifact 須在交付 HEAD 可重現，重跑不得產生新請求）。

存在的理由：G4 保存的 10 份 payload 是**有差異的場次**才保存，屬偏差樣本
（選擇條件為 TrackMan 逐格差異）。該選擇條件與「回應是否帶逐局責任投手」正交，
但為**降低**抽樣偏差質疑，對一場中性完成場補一次確認，並對照 schema 是否一致。
作用域限制：**一場中性場只能削弱抽樣偏差，不能消除它**——語料仍是 11 場、非全季窮舉。

請求紀律：對 `stats.cpbl.com.tw` 直連（該站無反爬挑戰），單場一次，無重試。
逐筆時間與次數寫入 `request_log.json`。

    uv run python docs/research/INGEST-SCORELESS-INNING-PITCHER1/confirm_live_schema.py 2026-A-246
"""

from __future__ import annotations

import argparse
import datetime as _dt
import gzip
import hashlib
import json
import pathlib

BASE = "https://stats.cpbl.com.tw"
OUTDIR = pathlib.Path("docs/research/INGEST-SCORELESS-INNING-PITCHER1")

USAGE = """\
confirm_live_schema.py — 對一場完成場向官方取一次 schema（本卡的單次確認請求）

在做什麼
  對 stats.cpbl.com.tw 的 /api/proxy/v1/games/<gid> 直連取一次 payload，
  落檔成 payloads/<gid>.json.gz，並把逐筆請求紀錄寫進 request_log.json。
  冪等：payloads/<gid>.json.gz 已存在就直接讀檔、不發任何請求。

會寫什麼（⚠️ 沒有 dry-run）
  · 對 stats.cpbl.com.tw 發出一次**真實** HTTP GET
  · 本目錄：payloads/<gid>.json.gz（新的 gid ＝ 新的請求 ＋ 新的檔案）
  · 本目錄：**覆寫 request_log.json** ——⚠️ 那份 artifact 逐字宣稱
    「本卡總共發出 1 次請求」（total_requests_issued_by_this_card: 1）。
    用一個新的 gid 跑它，那句宣稱就不再為真，而檔案看起來仍然完全正常。

怎麼呼叫
  uv run python docs/research/INGEST-SCORELESS-INNING-PITCHER1/confirm_live_schema.py 2026-A-246

⚠️ 母卡 INGEST-SCORELESS-INNING-PITCHER1 已結案，本檔是凍結的一次性產物。
   除非你正在重現該卡的數字，否則**不要跑它**。
"""


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="confirm_live_schema",
        description=USAGE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "gid", nargs="?", default="2026-A-246",
        help="game ID，例如 2026-A-246（省略＝本卡當初取的那一場）")
    return p


def main() -> None:
    # ⚠️ argv 必須在任何 I/O 之前解析。改版前是
    # `gid = sys.argv[1] if len(sys.argv) > 1 else "2026-A-246"`：
    # `--help` 會直接變成 game ID 拼進 URL，對官方發出一次真實請求。
    gid = _parser().parse_args().gid
    OUTDIR.joinpath("payloads").mkdir(parents=True, exist_ok=True)
    dest = OUTDIR / f"payloads/{gid}.json.gz"
    log_path = OUTDIR / "request_log.json"
    url = f"{BASE}/api/proxy/v1/games/{gid}"

    if dest.exists():
        print(f"payload 已存在，未發出請求：{dest}")
        return

    import httpx

    started = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=8))).isoformat()
    with httpx.Client(timeout=30, headers={"User-Agent": "Mozilla/5.0"}) as c:
        r = c.get(url)
        status = r.status_code
        raw = r.content
    finished = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=8))).isoformat()
    r.raise_for_status()

    with gzip.open(dest, "wb") as f:
        f.write(raw)

    log = {
        "card": "INGEST-SCORELESS-INNING-PITCHER1",
        "policy": "單次確認，無重試；冪等腳本（payload 存在即不重打）",
        "total_requests_issued_by_this_card": 1,
        "requests": [{
            "seq": 1,
            "url": url,
            "method": "GET",
            "started_at": started,
            "finished_at": finished,
            "http_status": status,
            "bytes": len(raw),
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "retries": 0,
        }],
    }
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n")
    print(f"HTTP {status} bytes={len(raw)} → {dest}")
    print(f"request log → {log_path}")


if __name__ == "__main__":
    main()
