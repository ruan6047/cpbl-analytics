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
import os
import subprocess
import time
from pathlib import Path

import ci_base
import psycopg
from psycopg import conninfo, sql
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
    # ⚠️ 三態講三種話，而且**不得把「管道通」講成「有人看到」**。
    # 本卡在「rc=0 講成送達」上栽過一次；`push_channel` 量的是管道能力，不是投遞結果。
    notification = payload.get("notification") or {}
    # ⚠️ 指令失敗優先於管道狀態：「沒送出」與「送了但被擋」是兩件事，讀者摘要必須分得開。
    # R6 誤刪這個守衛後，osascript 非零退出只剩 JSON 裡一個數字，摘要完全不提。
    if notification.get("command_failed"):
        return lines + [
            f"⚠️ 排程告警：通知指令**失敗**（{notification.get('command_error') or '原因未記錄'}）"
            "——這則告警完全沒有送出，只有這裡看得到"]
    channel = (notification.get("push_channel") or {}).get("state")
    if channel == "blocked":
        kind = (notification.get("push_channel") or {}).get("suppression_type") or "（未記錄）"
        lines.append(f"⚠️ 排程告警：當時推播被抑制（型態 {kind}），這則告警**當晚沒有送到**"
                     "——別預設有人已經知道了；之後會不會補送依型態而異，"
                     "未知型態一律當作可能永遠不會出現")
    elif channel == "unknown":
        lines.append("⚠️ 排程告警：當時量不到專注模式狀態——**既不代表送到，"
                     "也不代表沒送到**，請自行確認需求方是否已知情")
    elif channel == "open":
        lines.append("ℹ️ 排程告警：當時推播管道沒有被擋（**這不代表有人看到**，"
                     "只代表沒有東西擋著）——這一行仍然是備援")
    return lines


def pytest_report_header(config) -> list[str]:  # noqa: ANN001 — pytest hook 簽名固定
    del config
    return _location_header() + _schedule_alert_header()


# 需要按 xdist worker 拆庫的「自行擁有的隔離 Postgres」環境變數。CI 以 Postgres service 提供
# （.github/workflows/ci.yml）。只列會被**多個測試檔**共用、且各檔都在同一個 `cpbl` schema 上
# 自建自刪的 DSN；`PA_BUILD_LOCK_TEST_DATABASE_URL`／`PROD_SYNC_SEQ_TEST_DATABASE_URL` 各只有一個
# 測試檔使用、且測試自己釘死 dbname（`cpbl_pa_lock1`／`cpbl_prod_sync_seq1`），`--dist loadfile` 下
# 同檔同 worker、不會互撞，所以**不**拆庫、也不能改名。主 DSN（DATABASE_URL）不在此列：它指向
# 有真實資料的庫（本機正式庫，或 CI 的資料基底 cpbl_ci_base），只有偵測到基底標記時才由
# ``_per_worker_ci_base`` 按 worker 複製（#413）；本機正式庫沒有標記，維持原行為。
THROWAWAY_DB_ENVS = (
    "CPBL_ISOLATED_TEST_DSN",   # test_*_isolated.py、test_daily_chain_completion、test_evening_a_fetch_gate
)


def _per_worker_throwaway_dbs(config) -> None:  # noqa: ANN001 — pytest Config
    """xdist 下為每個 worker 配自己的拋棄式資料庫。

    這些測試檔都在環境變數所指的庫上自建 schema、結束時 ``DROP SCHEMA … CASCADE``，而且 schema 已存在時
    拒跑（怕踩到真實資料庫）。單執行緒下它們依序共用一個空庫沒問題；``-n 4`` 時四個 worker 同時建、
    同時刪同一個 schema 就互相撞成假紅。

    這裡在 **xdist worker 內**、且使用者**本來就設了**該環境變數時，把 dbname 改成 ``<dbname>_<workerid>``，
    不存在就經維護庫 ``postgres`` ``CREATE DATABASE``；單執行緒或未設時完全不動。這些 DSN 依各測試檔檔頭只該
    指向拋棄式伺服器，在同一台伺服器建兄弟庫在這個前提下是安全的；沒有 CREATEDB 權限就讓它在這裡炸開，
    而不是靜默退回共用庫去撞。
    """
    # 只認 pytest Config 上 xdist 放的 workerinput；⛔ 不退回 PYTEST_XDIST_WORKER 環境變數——
    # 替身 config 的單元測試（test_pytest_location_header）就跑在 worker 行程裡，退回去會讓它誤連 DB。
    worker = (getattr(config, "workerinput", None) or {}).get("workerid")
    if not worker:
        return
    for name in THROWAWAY_DB_ENVS:
        dsn = os.environ.get(name)
        if not dsn:
            continue
        base = conninfo.conninfo_to_dict(dsn).get("dbname") or "postgres"
        target = f"{base}_{worker}"
        maintenance = conninfo.make_conninfo(dsn, dbname="postgres")
        with psycopg.connect(maintenance, autocommit=True,
                             connect_timeout=_PROBE_CONNECT_TIMEOUT_SECONDS) as c:
            if c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target,)).fetchone() is None:
                c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target)))
        os.environ[name] = conninfo.make_conninfo(dsn, dbname=target)


def _clone_database(dsn: str, template: str, target: str) -> None:
    """經維護庫以 ``template`` 為模板重建 ``target``（已存在就先刪，確保每個 session 從乾淨基底開始）。

    多個 worker 幾乎同時從同一個模板複製：模板只要有任何連線掛著，``CREATE DATABASE … TEMPLATE``
    就回 ``ObjectInUse``——那是暫態，退避重試；其他錯誤照常炸開。
    """
    maintenance = conninfo.make_conninfo(dsn, dbname="postgres")
    for attempt in range(20):
        try:
            with psycopg.connect(maintenance, autocommit=True,
                                 connect_timeout=_PROBE_CONNECT_TIMEOUT_SECONDS) as c:
                c.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(target)))
                c.execute(sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    sql.Identifier(target), sql.Identifier(template)))
            return
        except psycopg.errors.ObjectInUse:
            if attempt == 19:
                raise
            time.sleep(0.25 * (attempt + 1))


def _per_worker_ci_base(config) -> None:  # noqa: ANN001 — pytest Config
    """主 DSN 指向已載入的 CI 基底（#413，``tests/ci_base.py``）時，xdist 下每個 worker 用自己的複本。

    為什麼：主 DSN 一連得上，至少三個檔會刪掉整個 year=1900 的 livelog、另有兩組檔共用同一個哨兵鍵，
    不同 worker 會互刪——與預載什麼資料無關。所以只在**偵測到基底標記**時，以 ``CREATE DATABASE …
    TEMPLATE`` 複製成 ``<庫名>_<workerid>``，並同步改寫 ``DATABASE_URL`` 與 ``settings.database_url``。

    ⛔ 沒有標記（本機正式庫、CI 舊形狀的不可達埠）就完全不動：環境、settings 與連線池都維持原樣。
    標記經維護庫 ``postgres`` 讀取，不連模板庫本身（連著它就無法被複製）。
    """
    marker = ci_base.marker_of(settings.database_url, connect_timeout=_PROBE_CONNECT_TIMEOUT_SECONDS)
    ci_base.set_active(marker)
    if marker is None:
        return
    worker = (getattr(config, "workerinput", None) or {}).get("workerid")
    if not worker:
        return
    dsn = settings.database_url
    template = conninfo.conninfo_to_dict(dsn).get("dbname") or "postgres"
    target = f"{template}_{worker}"
    _clone_database(dsn, template, target)
    clone = conninfo.make_conninfo(dsn, dbname=target)
    os.environ["DATABASE_URL"] = clone
    settings.database_url = clone
    if db._pool is not None:
        db._pool.close()
        db._pool = None


def pytest_sessionstart(session) -> None:  # noqa: ANN001 — pytest hook 簽名固定
    """整個 session 只探測一次；DB 不可達就讓全域池「預先壞掉」以避免逐測試等待。"""
    _per_worker_throwaway_dbs(session.config)
    _per_worker_ci_base(session.config)
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


# ---------------------------------------------- #391 聯盟收官的讀取隔離
#
# 每日閘門與晚間鏈會在執行中讀 `cpbl.season_close`（另開唯讀交易）。腳本化／替身測試若剛好跑在 DB
# 可達的機器上，這一讀會拿到**本機共享 DB 的當下收官狀態**（例：2026 一軍已收官），讓「2026-10-21 有賽型」
# 這類固定日期的測試隨牆鐘與資料漂移。預設一律回 None（＝讀不到＝未收官的舊行為）；要測收官的測試自己再
# monkeypatch 成指定值。
import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_season_closure(monkeypatch):
    from cpbl.ingest import daily_gate, postseason_evening

    monkeypatch.setattr(daily_gate, "read_closure", lambda at=None: None)
    monkeypatch.setattr(postseason_evening, "read_closure", lambda now=None: None)


@pytest.fixture(autouse=True)
def _isolate_calendar_closure(monkeypatch):
    """#391 審核 F1：月曆端點的收官判定同理（預設讀不到＝不標 not_needed）。"""
    from cpbl.api.routers import games

    monkeypatch.setattr(games, "_season_closure", lambda season: None)


# ---------------------------------------------- #442 行程內回應快取的測試隔離
#
# `cpbl.api.response_cache.CACHE` 是行程全域的；不清掉的話，前一個測試以替身資料算出的回應會被下一個
# 測試讀到（同鍵命中），測試結果就取決於執行順序。每個測試開始前清空。
# lifespan 的預熱／背景刷新執行緒在測試中預設不啟動：它會真的連 DB（本機可達時讀本機 DB、不可達時在池上
# 排隊讓 G4 讓路判定為忙），讓不相干的 lifespan 測試變慢或依環境而變。要測它的測試直接呼叫
# `response_cache.Refresher`／`run_prewarm`（tests/test_api_swr_cache_442.py）。
@pytest.fixture(autouse=True)
def _isolate_response_cache(monkeypatch):
    from cpbl.api import response_cache

    monkeypatch.setattr(response_cache, "start", lambda jobs_factory=None: None)
    response_cache.CACHE.clear()
    yield
    response_cache.CACHE.clear()
