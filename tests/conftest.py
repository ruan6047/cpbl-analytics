"""tests/ 全域設施：DB 可用性一次性探測（DEV-CI-PYTEST-SLOW1）。

背景（計時證據，模擬 CI 無 DB：DATABASE_URL 指向無人監聽的埠）：
`uv run pytest -q --durations=50` 顯示 25 個測試／fixture 各花 ~30.00–30.09
秒，佔 781s 總時間的絕大部分；其餘 1000+ 測試合計不到 30 秒。這不是連線本身
慢——`psycopg.connect()` 對不可達位址近乎瞬間失敗（ECONNREFUSED）——而是
`cpbl.db.pool()` 建立的全域 `ConnectionPool`，其 `.connection()` 借連線在
真正借不到時會等到 pool 的 checkout timeout（`ConnectionPool` 預設
`timeout=30.0` 秒）才拋 `PoolTimeout`。因為沒有共用探測，每個各自
try/except 再 `pytest.skip()` 的測試檔（test_records_api.py、
test_daily_summary.py、test_coaches_history.py、test_scoreless_streak_api.py…）
都各自付一次 30 秒，不會因為背後是同一個全域單例池而變快——空池不會記得
「已知連不上」，每次借連線都重新等滿 timeout。

修法：整個 pytest session 只在最開始做一次探測——用一條「用完即丟」的原生
連線（不經過 pool、bounded connect_timeout=2s）快速確認 DB 是否可達。
- **DB 不可達**：把 `cpbl.db._pool` 直接換成一個「未開啟」的池
  （`ConnectionPool(..., open=False)`）——與 `tests/test_api_contract.py`
  既有 `broken_db` fixture 同一手法（見該檔內註解）：任何借連線立即拋
  `PoolClosed`，不必再等 30 秒 checkout timeout。
- **DB 可達**：完全不碰 `_pool`，讓它照舊由第一個真正使用它的測試惰性建立
  （`cpbl.db.pool()` 原本的行為）——與現行行為零差異，「有 DB 時照跑」。

各測試檔既有的 try/except pytest.skip 邏輯完全不變：收到的例外從
`PoolTimeout` 換成 `PoolClosed`，且幾乎瞬間發生；skip 條件維持等價，
只是不必再乾等。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import psycopg
from psycopg_pool import ConnectionPool

from cpbl import db
from cpbl.config import settings

# 探測逾時：遠低於 pool 預設 30 秒 checkout timeout，但足夠讓真實本機/CI DB
# （loopback 或近端網路）在正常情況下回應，避免把偶發的短暫延遲誤判為無 DB。
_PROBE_CONNECT_TIMEOUT_SECONDS = 2

# 與 tests/test_api_contract.py 的 broken_db fixture 同一手法：未開啟的池
# 借連線立即拋 PoolClosed，不會嘗試真的連線、不會等待。
_UNREACHABLE_DSN = "postgresql://x:x@127.0.0.1:1/x"


def _git_output(*args: str) -> str | None:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=Path.cwd(),
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def _location_header() -> list[str]:
    head = _git_output("rev-parse", "--short", "HEAD") or "unavailable"
    branch = _git_output("branch", "--show-current") or "detached"
    return [
        f"pytest location: cwd={Path.cwd()}",
        f"pytest location: git_head={head}",
        f"pytest location: git_branch={branch}",
    ]


# ---------------------------------------------- 排程告警的讀者（#132／OPS-SCHEDULE-FAILURE-BLIND1）
#
# 為什麼放在**這裡**：本專案不設推播管道（見 scripts/backup-prod-db.sh 檔頭），而
# 實測證明 macOS 通知這條路在本機是死的——專注模式把 osascript 通知全部 suppressed
# （量測見 scripts/schedule_watch.py 的 notify() 區段）。所以「誰會看到」必須落在一個
# **本來就會被執行**的表面上，而不是期待有人記得去翻檔案。
#
# `uv run pytest` 是本專案唯一被 CLAUDE.md 明訂為 push 前必跑的東西，且這個 header
# 連 `-q` 都會印（見 pytest_sessionstart）。因此讀者＝任何要動這個 repo 的人或 AI，
# 時機＝每次驗證迴圈——不需要新的紀律，也不需要任何人記得。
#
# ⚠️ 這是**目標 3（可稽核痕跡）不是目標 2（主動送達）**：它仍然要等人來跑 pytest。
# 刻意**不**做成 fail：排程壞掉不該擋住無關的程式碼工作（本專案已在「暫時服務截止」
# 那次吃過連坐的虧）。它只是讓訊號出現在眼前。
_SCHEDULE_ALERT = Path(__file__).resolve().parents[1] / "logs" / "schedule-alert.json"


def _schedule_alert_header() -> list[str]:
    """`logs/schedule-alert.json` 存在＝有未處理的排程異常。不存在就完全安靜。

    ⚠️ 任何讀取失敗都只降級成一行提示，絕不讓 pytest 因為它而爆——觀測器把被觀測的
    東西弄掛是本末倒置（與 schedule_watch.py 的歷史寫入同一條原則）。
    """
    try:
        if not _SCHEDULE_ALERT.exists():
            return []
        payload = json.loads(_SCHEDULE_ALERT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [f"⚠️ 排程告警：{_SCHEDULE_ALERT} 存在但讀不開——請直接看檔案"]
    lines = [f"⚠️ 排程告警未處理（{payload.get('observed_at', '時間不明')}）："
             f"{payload.get('message') or payload.get('verdict') or '詳見檔案'}",
             f"⚠️ 排程告警：詳見 {_SCHEDULE_ALERT}（修好後本檔會自動消失）"]
    # ⚠️ 三態講三種話。R2 這裡寫 `!= "presented"`，於是「查不到」被印成「沒有送達」
    # ——那是在宣稱自己沒有的確定性。查不到就說查不到。
    delivered = (payload.get("notification") or {}).get("delivered")
    if delivered == "suppressed":
        lines.append("⚠️ 排程告警：當時的推播被專注模式擋下，**確定沒有**出現在螢幕上"
                     "——所以除了這裡，沒有別人被通知到")
    elif delivered == "unverified":
        lines.append("⚠️ 排程告警：當時的推播查不到系統紀錄——**既不代表送到，"
                     "也不代表沒送到**，請自行確認需求方是否已知情")
    elif delivered == "presented":
        lines.append("ℹ️ 排程告警：當時的推播**已呈現在螢幕上**（系統紀錄）——"
                     "但那不保證有人讀了，這一行仍然是備援")
    return lines


def pytest_report_header(config) -> list[str]:  # noqa: ANN001 — pytest hook 簽名固定
    del config
    return _location_header() + _schedule_alert_header()


def pytest_sessionstart(session) -> None:  # noqa: ANN001 — pytest hook 簽名固定
    """整個 session 只探測一次；DB 不可達就讓全域池「預先壞掉」以避免逐測試等待。"""
    try:
        with psycopg.connect(
            settings.database_url, connect_timeout=_PROBE_CONNECT_TIMEOUT_SECONDS
        ):
            pass
    except Exception:  # noqa: BLE001 — 探測階段任何失敗都視為「無 DB」，交由各測試既有 skip 邏輯處理
        db._pool = ConnectionPool(_UNREACHABLE_DSN, open=False)

    if getattr(session.config.option, "quiet", 0):
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            for line in _location_header() + _schedule_alert_header():
                reporter.write_line(line)
