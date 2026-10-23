"""J1 每日鏈（10:10）的日型閘門、衍生步驟閘門與 VPS 訓練閘門（#364；#343 PLAN-r6 §3.2、§3.5、§3.8）。

**只決定「何時跑什麼」，不改觸發器、同步與備份路徑**（PLAN §2 方案甲）。呼叫端：

- ``scripts/scrape-daily.sh``：取鎖後 ``decide`` → 依日型分流；同步成功後 ``mark-synced``；
  爬完賽程後 ``today-schedule`` 覆寫今日賽程檔（失敗即刪檔）。
- ``cpbl-refresh-recent``：讀環境變數 ``DAILY_DAY_TYPE``；衍生步驟由本模組 :func:`derived_decision`
  依 §3.2.3 來源訊號決定。``cpbl-refresh-recent --plan --date YYYY-MM-DD`` 印出該日步驟清單（唯讀）。
- ``scripts/refresh-cpbl-prod.sh``：``train-gate`` 以「正式站最新 ``model_versions(task='outcome')``
  的訓練資料規模」對照本機完成場，決定 ``cpbl-build-features``＋``game_features`` 全鏡像＋
  ``cpbl-train-outcome`` 跑不跑（§3.5）。

日型（PLAN-r6 §3.2 表；判定只讀本機 ``cpbl.games``＋狀態檔，⛔ 不連 www）：

=============  =====================================================================
``full``       有賽型：昨天有任一 A／D／E／C 排定場 → 完整鏈（現況），4/4 套 §3.5 訓練閘門
``light``      乙型：昨天無、今天有 → 爬賽程／累計／戰績／升降／補缺／逐球自癒＋同步。
               「甲型但上次 J1 失敗」與「甲型但 stats 探測有新場／探測不明」也走這裡。
``sync_only``  甲型但本機自上次正式站同步後有寫入（J3／J4／手動）→ 不爬，只做衍生＋同步，不訓練
``skip``       甲型：昨今皆無＋上次 J1 成功＋本機無未同步寫入＋stats 探測確定無新場
               → 不爬、不備份、不同步；狀態寫「成功、skipped=true、reason=…」
=============  =====================================================================

衍生步驟（PA build、球種推算、當季衍生、分項＋生涯、改名同步；§3.2.3 整組讀法）：
``light``／``sync_only`` ⛔ 不依日型略過——任一來源訊號（本次 J1 寫入場／逐球、J3、J4、
前次衍生未成功）或判斷不了 → 跑整組（＝完整鏈在同一來源狀態下的集合）；全部為 0 才略過。
``build-features`` 與 4/4 訓練在 ``light``／``sync_only`` 一律略過（§3.2 表）。

逃生閥（§3.2.4）：``DAILY_FORCE_FULL=1`` 一律走 ``full``，衍生與訓練都不套閘門。

⚠️ fail closed 的方向一律是「多跑」：任何一項判定讀不到或讀不懂（歷史檔缺、同步標記缺、stats
回應不明、refresh_log 讀不到、正式站模型讀不到）都不得判成「可以略過」。判定程式本身失敗時
scrape-daily.sh 退回 ``full``（現況）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

# —— 參數（PLAN-r2 §3.8；技術參數，執行時可調，不涉成果方向）——
# P-DAYTYPE-KINDS：日型判定看的賽別。
DAYTYPE_KINDS: tuple[str, ...] = ("A", "D", "E", "C")
# P-PROBE-AHEAD：甲型探測看 [今天, 今天＋N 天]。
PROBE_AHEAD_DAYS = 7
# P-OFFSEASON-D：stats 不提供 D 時的退路。2026-10-23 實測 stats 賽程 API 對 kindCode=D 回
# 2026-08 共 51 場（#364 執行報告 D 查證），故 D 直接納入探測，退路**不啟用**。若日後 stats
# 對 D 改回空集合，把 D 移出這個 tuple 並改用「週一 J4 之後的下一個 J1 跑乙型」（§3.2.1）。
PROBE_KINDS: tuple[str, ...] = ("A", "D", "E", "C")

FULL, LIGHT, SYNC_ONLY, SKIP = "full", "light", "sync_only", "skip"
DAY_TYPES = (FULL, LIGHT, SYNC_ONLY, SKIP)
DAY_LABELS = {
    FULL: "有賽型",
    LIGHT: "乙型",
    SYNC_ONLY: "甲型但本機有未同步寫入（只同步）",
    SKIP: "甲型",
}
FORCE_ENV = "DAILY_FORCE_FULL"
DAY_TYPE_ENV = "DAILY_DAY_TYPE"
DEFAULT_HISTORY = Path("logs/schedule-history/com.cpbl.scrape-daily.jsonl")
DEFAULT_SYNC_MARKER = Path("logs/daily-sync-marker.json")
# 今日賽程檔（PLAN-r2 §3.1 J1 → J2、§3.3 動作條件、§3.6 J1 甲型列「只寫狀態與今日賽程檔」）。
# 消費端＝#365 WP2 晚間鏈：缺檔或 ``date`` 不是台北今天 → 退回連本機 DB（§3.3）。格式見
# :func:`today_schedule_payload`；⛔ 改欄位名或語意須同步 #365。
DEFAULT_TODAY_FILE = Path("logs/daily-schedule-today.json")
TODAY_FILE_SCHEMA = 1
TODAY_FILE_KINDS: tuple[str, ...] = ("A", "D", "E", "C")
TERMINAL_OK = ("succeeded", "skipped")


def force_full(env: Mapping[str, str] | None = None) -> bool:
    return (env if env is not None else os.environ).get(FORCE_ENV, "") == "1"


# =========================================================================== 判定（純函式）

@dataclass(frozen=True)
class ProbeResult:
    """§3.2.1 stats 探測結果。``status``：clean／new／unavailable／not_run。"""
    status: str
    detail: tuple[str, ...] = ()


@dataclass(frozen=True)
class DayInputs:
    day: date
    scheduled: Mapping[date, Mapping[str, int]]   # 本機 games：日期 → {賽別: 列數}
    last_j1_ok: bool | None                       # None＝讀不到（無歷史）
    last_j1_detail: str = ""
    unsynced_writes: bool | None = None           # None＝讀不到（無同步標記）
    unsynced_detail: str = ""
    force: bool = False


@dataclass(frozen=True)
class Decision:
    day_type: str
    reasons: tuple[str, ...]
    probe: ProbeResult = field(default_factory=lambda: ProbeResult("not_run"))

    @property
    def label(self) -> str:
        return DAY_LABELS[self.day_type]


def _games_on(scheduled: Mapping[date, Mapping[str, int]], day: date) -> dict[str, int]:
    return {k: n for k, n in (scheduled.get(day) or {}).items() if k in DAYTYPE_KINDS and n > 0}


def _fmt_games(games: Mapping[str, int]) -> str:
    return "、".join(f"{k}×{n}" for k, n in sorted(games.items())) or "無"


def classify(inputs: DayInputs, probe: Callable[[], ProbeResult]) -> Decision:
    """PLAN-r2 §3.2 表。``probe`` 只在前四項都指向甲型時才呼叫（省下不必要的 stats 請求）。"""
    yesterday = inputs.day - timedelta(days=1)
    y_games, t_games = _games_on(inputs.scheduled, yesterday), _games_on(inputs.scheduled, inputs.day)
    reasons = [
        f"昨天 {yesterday} 本機排定場：{_fmt_games(y_games)}（看 {','.join(DAYTYPE_KINDS)}）",
        f"今天 {inputs.day} 本機排定場：{_fmt_games(t_games)}",
    ]
    if inputs.force:
        return Decision(FULL, (f"{FORCE_ENV}=1：強制完整鏈（§3.2.3 逃生閥）", *reasons))
    if y_games:
        return Decision(FULL, tuple(reasons))
    if t_games:
        return Decision(LIGHT, tuple(reasons))
    reasons.append(f"上次 J1：{inputs.last_j1_detail or '未知'}")
    if inputs.last_j1_ok is not True:
        reasons.append("上次 J1 未確認成功 → 依乙型跑（兼任重試）")
        return Decision(LIGHT, tuple(reasons))
    result = probe()
    reasons.append(f"stats 探測 [{inputs.day}, {inputs.day + timedelta(days=PROBE_AHEAD_DAYS)}]："
                   + {"clean": "無新場／日期異動", "new": "有本機沒有的場次或日期異動",
                      "unavailable": "取不到（fail closed）", "not_run": "未執行"}[result.status]
                   + (f"（{'；'.join(result.detail)}）" if result.detail else ""))
    if result.status != "clean":
        reasons.append("探測未證明無新場 → 升級乙型跑一次 www")
        return Decision(LIGHT, tuple(reasons), result)
    reasons.append(f"本機自上次正式站同步後寫入：{inputs.unsynced_detail or '未知'}")
    if inputs.unsynced_writes is not False:
        return Decision(SYNC_ONLY, tuple(reasons), result)
    return Decision(SKIP, tuple(reasons), result)


# —— 步驟清單（PLAN-r2 §3.2 表逐列；--plan 印出、pytest 逐列比對）——
RUN, SKIP_STEP, COND, KEEP = "跑", "略過", "條件", "照跑（表未列，維持現況）"

STEPS: tuple[tuple[str, str], ...] = (
    ("ad_games", "A／D 賽程（含當天先發）"),
    ("ec_games", "E／C 賽程"),
    ("season_stats", "季累計"),
    ("standings", "戰績"),
    ("transactions", "升降"),
    ("championships", "總冠軍成員重建"),
    ("incremental", "[昨天,今天] 增量明細＋TrackMan 3 天落後自癒"),
    ("missing_gamelog", "補缺 gamelog（前日失敗重試）"),
    ("postseason_detail", "季後 E／C 明細"),
    ("pa_build", "PA build"),
    ("pitch_type", "球種推算整季重算"),
    ("derived", "當季衍生"),
    ("splits", "分項"),
    ("name_sync", "改名同步"),
    ("team_comparison", "隊伍比較摘要"),
    ("build_features", "cpbl-build-features＋game_features 全鏡像"),
    ("backup", "正式站整庫備份"),
    ("sync", "同步（migration＋整鏈 upsert）"),
    ("train_outcome", "4/4 cpbl-train-outcome"),
    ("train_simple", "4/4 cpbl-train-outcome-simple"),
    ("freshness", "正式站 freshness 對帳"),
    ("status_skipped", "狀態寫「成功、skipped=true」並 append 歷史"),
)

# —— PLAN-r5 §3.2.3：衍生步驟依來源變動決定 ——
# 完整鏈（run_refresh_recent.main）在爬取之後依序執行的衍生步驟；fast 模式不跑球種與當季衍生。
DERIVED_STEPS: tuple[str, ...] = ("pa_build", "pitch_type", "derived", "splits", "name_sync")
DERIVED_NOTE = ("§3.2.3：任一來源訊號（本次寫入場／逐球、J3 新逐球、J4 新修訂）或判斷不了 → "
                "跑與完整鏈同一組衍生步驟；全部訊號為 0 → 略過")
DEFAULT_J3_STATUS = Path("logs/last-weekly-pitches.json")
DEFAULT_J4_STATUS = Path("logs/last-weekly-box-revisions.json")

_SCRAPE = ("ad_games", "ec_games", "season_stats", "standings", "transactions", "championships",
           "incremental", "missing_gamelog", "postseason_detail", "pa_build", "pitch_type",
           "derived", "splits", "name_sync", "team_comparison")
_SYNC = ("backup", "sync", "freshness")


def plan_steps(day_type: str, *, force: bool = False) -> list[tuple[str, str, str, str]]:
    """日型 → [(key, 名稱, 動作, 說明)]。動作只有 跑／略過／條件／照跑（表未列）。"""
    gate_note = "" if force else "§3.5 訓練閘門"
    table: dict[str, tuple[str, str]] = {}
    if day_type == FULL:
        for key, _ in STEPS:
            table[key] = (RUN, "")
        if not force:
            table["build_features"] = (COND, f"{gate_note}：本機一軍完成場（含比分）自上次訓練後有變才跑")
            table["train_outcome"] = (COND, f"{gate_note}：同上")
            table["train_simple"] = (COND, f"{gate_note}：正式站 artifact 訓練上界季 < 今年−1 才跑")
        table["status_skipped"] = (SKIP_STEP, "")
    elif day_type == LIGHT:
        for key in ("ad_games", "ec_games", "season_stats", "standings", "transactions",
                    "incremental", "missing_gamelog", *_SYNC):
            table[key] = (RUN, "")
        for key in ("championships", "postseason_detail", "team_comparison"):
            table[key] = (KEEP, "")
        for key in DERIVED_STEPS:
            table[key] = (COND, DERIVED_NOTE)
        for key in ("build_features", "train_outcome", "train_simple", "status_skipped"):
            table[key] = (SKIP_STEP, "")
    elif day_type == SYNC_ONLY:
        for key in _SCRAPE + ("build_features", "train_outcome", "train_simple", "status_skipped"):
            table[key] = (SKIP_STEP, "")
        for key in DERIVED_STEPS:
            table[key] = (COND, DERIVED_NOTE + "（不爬，訊號主要來自 J3／J4）")
        table["team_comparison"] = (KEEP, "來源未變＝no-op")
        for key in _SYNC:
            table[key] = (RUN, "SKIP_SCRAPE=1" if key == "sync" else "")
    elif day_type == SKIP:
        for key, _ in STEPS:
            table[key] = (SKIP_STEP, "")
        table["status_skipped"] = (RUN, "")
    else:
        raise ValueError(f"未知日型：{day_type!r}")
    return [(key, name, *table[key]) for key, name in STEPS]


def render_plan(decision: Decision, *, force: bool = False) -> str:
    lines = [f"日型：{decision.label}（{decision.day_type}）", "判定依據："]
    lines += [f"  - {r}" for r in decision.reasons]
    lines.append("步驟：")
    for _, name, action, note in plan_steps(decision.day_type, force=force):
        lines.append(f"  [{action}] {name}" + (f"——{note}" if note else ""))
    return "\n".join(lines)


# =========================================================================== 輸入讀取

def _parse_ts(value: str) -> datetime:
    if len(value) >= 5 and value[-5] in "+-" and value[-3] != ":":
        value = f"{value[:-2]}:{value[-2:]}"
    return datetime.fromisoformat(value)


def last_j1_status(history: Path, *, exclude_started_at: str | None = None,
                   before: datetime | None = None) -> tuple[bool | None, str]:
    """上一次 J1（任何 trigger）是否成功。

    依 started_at 分組取**最新那一次**的最後一列：終態 succeeded／skipped＝成功；failed＝失敗；
    只剩 running（行程死掉、沒寫終態）＝失敗。``exclude_started_at`` 排除本次執行自己的
    running 列；``before`` 供 --plan 回放（只看那天 10:10 前寫下的列）。
    讀不到任何紀錄 → (None, …)，由 :func:`classify` 當成「未確認成功」。
    """
    try:
        raw = history.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, f"讀不到歷史檔 {history}"
    runs: dict[str, dict] = {}
    for line in raw.splitlines():
        try:
            record = json.loads(line)
            started = str(record["started_at"])
            started_dt = _parse_ts(started)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
        if started == exclude_started_at:
            continue
        if before is not None and started_dt >= before:
            continue
        runs[started] = record          # append-only：同一次執行的最後一列＝最新狀態
    if not runs:
        return None, f"歷史檔 {history} 沒有可用紀錄"
    latest_started = max(runs, key=_parse_ts)
    record = runs[latest_started]
    state = record.get("state")
    detail = f"{state}（started_at={latest_started}，exit_code={record.get('exit_code')}）"
    return state in TERMINAL_OK, detail


def local_write_counter(connection: Any) -> int:
    """本機 ``cpbl`` schema 的累計寫入列數（pg_stat 的 ins＋upd＋del）。

    用途：判「自上次正式站同步後本機有沒有新寫入」（J3／J4／手動都涵蓋，不必各自登記）。
    計數器只增不減；被 reset（stats reset、crash recovery）時與標記不等 → 判有寫入 → 多同步
    一次，方向安全。⚠️ 只讀 pg_stat 視圖，不寫任何表。
    """
    row = connection.execute(
        "SELECT COALESCE(sum(n_tup_ins + n_tup_upd + n_tup_del), 0)::bigint "
        "FROM pg_stat_user_tables WHERE schemaname = 'cpbl'"
    ).fetchone()
    return int(row[0])


def unsynced_writes(marker: Path, current: int | None) -> tuple[bool | None, str]:
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
        synced = int(payload["write_counter"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        return None, f"讀不到同步標記 {marker}（{type(error).__name__}）→ 視為有未同步寫入"
    if current is None:
        return None, "讀不到本機寫入計數器 → 視為有未同步寫入"
    if current == synced:
        return False, f"無（寫入計數器 {current} ＝ 上次同步 {payload.get('synced_at')} 時的 {synced}）"
    return True, f"有（寫入計數器 {current} ≠ 上次同步 {payload.get('synced_at')} 時的 {synced}）"


def local_schedule(connection: Any, days: Iterable[date]) -> dict[date, dict[str, int]]:
    rows = connection.execute(
        "SELECT game_date, kind_code, count(*) FROM cpbl.games "
        "WHERE game_date = ANY(%s) AND kind_code = ANY(%s) GROUP BY game_date, kind_code",
        (list(days), list(DAYTYPE_KINDS)),
    ).fetchall()
    out: dict[date, dict[str, int]] = {}
    for game_date, kind, n in rows:
        out.setdefault(game_date, {})[kind] = int(n)
    return out


# —— §3.2.1 stats 探測 ——

def parse_probe_rows(rows: Iterable[Mapping], year: int, kinds: Iterable[str], *,
                     strict: bool = False) -> list[Any]:
    """stats ``Data.Games[]`` → ``StatsGame``，賽別放寬到 ``kinds``。

    身分規則與 :func:`cpbl.ingest.postseason_evening.parse_stats_games` 逐條相同（``GameId`` 與
    ``KindCode``／``GameSno`` 不一致整列略過、主客取不到為 None），差別只有賽別白名單：
    那支綁死模組常數 ``KINDS=("E","C")``（晚間鏈的賽別，屬 #365 WP2 的檔），本卡不改它。
    一致性由 ``tests/test_daily_gate.py`` 以同一批列對 E／C 比對兩支輸出釘住。

    ``strict=True``（甲型探測用，#364 審核 F2）：身分欄位讀不懂、``GameId`` 與 ``KindCode``／
    ``GameSno`` 不一致、或賽別不在 ``kinds`` 的列一律 :class:`ProbeUnavailable`——探測的結論是
    「可以不爬」，讀不懂的列不能被安靜略過後算成「確定無新場」。
    """
    from cpbl.ingest.postseason_evening import ProbeUnavailable, StatsGame, _team_code

    allowed = set(kinds)
    out = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ProbeUnavailable("stats schedule schema drift: 列不是物件")
        parts = str(row.get("GameId") or "").split("-")
        try:
            gid = (int(parts[0]), parts[1], int(parts[2])) if len(parts) == 3 else None
            sno = int(row.get("GameSno"))
        except (TypeError, ValueError):
            if strict:
                raise ProbeUnavailable(f"stats schedule 列身分讀不懂：{dict(row)!r}"[:200]) from None
            continue
        kind = str(row.get("KindCode") or "")
        if gid is None or gid != (year, kind, sno) or kind not in allowed:
            if strict:
                raise ProbeUnavailable(f"stats schedule 列身分不一致或賽別不符：{dict(row)!r}"[:200])
            continue
        starts = row.get("PreExeDate")
        starts = str(starts) if starts else None
        if strict and not (starts and len(starts) >= 10):
            raise ProbeUnavailable(f"stats schedule 列缺 PreExeDate：{row.get('GameId')}")
        venue = row.get("Field")
        out.append(StatsGame(
            year=year, kind_code=kind, game_sno=sno,
            status=str(row.get("GameStatus") or ""),
            starts_at=starts,
            game_date=starts[:10] if starts and len(starts) >= 10 else None,
            away_code=_team_code(row.get("Visiting")),
            home_code=_team_code(row.get("Home")),
            venue=str(venue["Abbe"]) if isinstance(venue, Mapping) and venue.get("Abbe") else None,
        ))
    return out


def probe_months(day: date, ahead: int = PROBE_AHEAD_DAYS) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    for offset in range(ahead + 1):
        d = day + timedelta(days=offset)
        if (d.year, d.month) not in months:
            months.append((d.year, d.month))
    return months


def compare_probe(stats_games: Iterable[Any], local: Mapping[str, str | None],
                  day: date, ahead: int = PROBE_AHEAD_DAYS) -> list[str]:
    """純函式：窗口內「本機沒有的場次」或「日期異動」→ 差異清單（空＝clean）。

    ``local``：``"YYYY-K-SNO" → 本機 game_date（ISO 字串）``。stats 沒列到的本機場次不視為取消。
    """
    lo, hi = day.isoformat(), (day + timedelta(days=ahead)).isoformat()
    found: list[str] = []
    for g in stats_games:
        local_date = local.get(g.key, "<missing>")
        in_window = g.game_date is not None and lo <= g.game_date <= hi
        local_in_window = local_date not in (None, "<missing>") and lo <= str(local_date) <= hi
        if local_date == "<missing>":
            if in_window:
                found.append(f"新場次 {g.key}@{g.game_date}")
        elif g.game_date and local_date and g.game_date != str(local_date) and (in_window or local_in_window):
            found.append(f"日期異動 {g.key} 本機 {local_date} → stats {g.game_date}")
    return found


def probe_rows(body: Any) -> list[Any]:
    """stats 賽程回應 → ``Data.Games`` 列（#364 審核 F2：只接受確定的形狀）。

    只有 ``{"Data": {"Games": [...]}}``（list，可為空）算「成功取得」；其餘——非物件、缺 ``Data``、
    ``Data`` 為 null 或非物件、缺 ``Games``、``Games`` 為 null 或非 list——一律
    :class:`ProbeUnavailable`。⛔ 不得以 ``or []`` 把「讀不懂」折成「零場」：零場的結論是「可以不爬」。
    """
    from cpbl.ingest.postseason_evening import ProbeUnavailable

    if not isinstance(body, Mapping):
        raise ProbeUnavailable(f"stats schedule 回應不是物件：{type(body).__name__}")
    data = body.get("Data")
    if not isinstance(data, Mapping):
        raise ProbeUnavailable(f"stats schedule 回應 Data 不是物件：{type(data).__name__}")
    rows = data.get("Games")
    if not isinstance(rows, list):
        raise ProbeUnavailable(f"stats schedule 回應 Data.Games 不是 list：{type(rows).__name__}")
    return rows


def stats_probe(day: date, *, fetch: Callable[[str, dict], Mapping] | None = None,
                local_lookup: Callable[[list[Any]], Mapping[str, str | None]],
                timeout: float = 10.0) -> ProbeResult:
    """唯讀 GET stats 賽程（``PROBE_KINDS`` × 窗口涵蓋月份，約 4–8 請求），失敗 fail closed。"""
    from cpbl.ingest.postseason_evening import SCHEDULE_PATH, _httpx_fetch

    fetch = fetch or _httpx_fetch(timeout)
    games: list[Any] = []
    try:
        for year, month in probe_months(day):
            for kind in PROBE_KINDS:
                body = fetch(SCHEDULE_PATH, {"kindCode": kind, "year": str(year), "month": str(month)})
                games += parse_probe_rows(probe_rows(body), year, (kind,), strict=True)
    except Exception as exc:  # noqa: BLE001 — 逾時／HTTP／JSON／形狀漂移一律 fail closed
        return ProbeResult("unavailable", (f"{type(exc).__name__}: {exc}"[:200],))
    diffs = compare_probe(games, local_lookup(games), day)
    return ProbeResult("new" if diffs else "clean", tuple(diffs[:10]))


def _local_lookup_db(games: list[Any], day: date) -> dict[str, str | None]:
    from cpbl.db import conn

    hi = day + timedelta(days=PROBE_AHEAD_DAYS)
    keys = [(g.year, g.kind_code, g.game_sno) for g in games]
    with conn() as c:
        c.execute("SET TRANSACTION READ ONLY")
        rows = c.execute(
            "SELECT year, kind_code, game_sno, game_date FROM cpbl.games "
            "WHERE kind_code = ANY(%s) AND ((year, kind_code, game_sno) IN "
            "(SELECT * FROM unnest(%s::int[], %s::text[], %s::int[])) "
            "OR game_date BETWEEN %s AND %s)",
            (list(PROBE_KINDS), [k[0] for k in keys], [k[1] for k in keys], [k[2] for k in keys],
             day, hi),
        ).fetchall()
    return {f"{y}-{k}-{s}": (d.isoformat() if d else None) for y, k, s, d in rows}


# =========================================================================== 衍生步驟訊號（§3.2.3）

@dataclass(frozen=True)
class DerivedSignal:
    """一個來源訊號。``fired``：True＝有寫入、False＝確定沒有、None＝判斷不了（視同有，fail open）。"""
    key: str
    fired: bool | None
    detail: str = ""


def full_chain_derived(*, skip_detail: bool = False) -> set[str]:
    """完整鏈在同一模式下會執行的衍生步驟集合（run_refresh_recent.main 的現況）。"""
    steps = set(DERIVED_STEPS)
    if skip_detail:
        steps -= {"pitch_type", "derived"}       # fast 模式現況就不跑這兩步
    return steps


def derived_decision(signals: Iterable[DerivedSignal], full_set: set[str]) -> tuple[set[str], dict]:
    """任一訊號為 True／None → 與完整鏈同一組；全部 False → 空集合。

    ⚠️ 為什麼不是「訊號 → 子集合」：WP1 驗收 (g) 要求閘門下的衍生步驟集合與「同一來源狀態下
    完整鏈會執行的集合」相同；完整鏈對任何來源變動都跑整組。依來源細分（例如 J3 只跑球種）會
    與完整鏈不同，故只在「全為 0」時整組略過（#364 exec-2 報告第 7 節）。
    """
    signals = list(signals)
    fired = [s for s in signals if s.fired is not False]
    steps = set(full_set) if fired else set()
    return steps, {
        "gated": True,
        "steps": sorted(steps),
        "signals": [{"key": s.key, "fired": s.fired, "detail": s.detail} for s in signals],
    }


def _aware(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.astimezone()
    return _parse_ts(str(value))


# refresh_log.detail 中衍生步驟的鍵（形狀見 run_refresh_recent.main）。
_DERIVED_DETAIL_KEYS = {"pa_build": "pa_build", "pitch_type": "pitch_type", "derived": "derived",
                        "splits": "splits_built"}
# 回頭看幾列 refresh_log（每日一列＋手動＝一年以上）。窗內找不到整組成功 → 基準 None → 跑。
REFRESH_LOG_LOOKBACK = 400


def _step_tried(detail: Mapping[str, Any], step: str) -> bool:
    value = detail.get(_DERIVED_DETAIL_KEYS[step])
    return isinstance(value, Mapping) and "skipped" not in value


def _step_ok(detail: Mapping[str, Any], step: str) -> bool:
    """該步驟這次有跑而且成功：沒標 skipped、沒有 ``error``、``errors`` 為空。"""
    value = detail.get(_DERIVED_DETAIL_KEYS[step])
    if not isinstance(value, Mapping) or "skipped" in value or "error" in value:
        return False
    return not value.get("errors")


def derived_all_ok(detail: Mapping[str, Any]) -> bool:
    """PA build、球種推算、當季衍生、分項**同一次全部成功**（#364 審核 F3 的成功基準）。"""
    return isinstance(detail, Mapping) and all(_step_ok(detail, s) for s in _DERIVED_DETAIL_KEYS)


def derived_attempted(detail: Mapping[str, Any]) -> bool:
    """這一列有嘗試任何衍生步驟，或整支以例外結束（``error`` 鍵）。"""
    if not isinstance(detail, Mapping):
        return True
    return "error" in detail or any(_step_tried(detail, s) for s in _DERIVED_DETAIL_KEYS)


def _recent_refresh_rows(connection: Any) -> list[tuple[datetime, Mapping[str, Any]]]:
    rows = connection.execute(
        "SELECT refreshed_at, detail FROM cpbl.refresh_log WHERE scope = 'recent-games' "
        "ORDER BY refreshed_at DESC LIMIT %s",
        (REFRESH_LOG_LOOKBACK,),
    ).fetchall()
    return [(_aware(t), d if isinstance(d, Mapping) else {}) for t, d in rows]


def last_refresh_marks(connection: Any) -> tuple[datetime | None, datetime | None]:
    """(上次成功的球種推算時刻, 上次**整組衍生成功**的時刻)，取自本機 ``refresh_log``（recent-games）。

    #364 審核 F3：「上次衍生」必須是 PA build、球種推算、當季衍生、分項四步**同一次都成功**；
    只看分項會讓「當季衍生失敗、分項成功」把基準往前推，J4 等來源訊號被提早消耗、隔日不再重試。
    refresh_log 在 main() 結尾才寫，時刻晚於該次衍生完成。
    """
    rows = _recent_refresh_rows(connection)
    pitch = max((t for t, d in rows if _step_ok(d, "pitch_type")), default=None)
    derived = max((t for t, d in rows if derived_all_ok(d)), default=None)
    return pitch, derived


def derived_retry_signal(connection: Any, last_derived: datetime | None) -> DerivedSignal:
    """#364 審核 F3：上次整組衍生成功之後，若有任何一次嘗試過衍生（或整支失敗）→ 重試。

    把「前次衍生沒跑完」本身當成來源訊號：本次 J1 的寫入訊號（訊號 1、2）只活在那一次執行裡，
    衍生失敗後隔天若沒有新寫入，沒有這條就會整組略過、停在舊版本。
    """
    if last_derived is None:
        return DerivedSignal("derived_retry", None, "回看窗內沒有任何一次整組衍生成功 → 跑")
    failed = [t for t, d in _recent_refresh_rows(connection)
              if t > last_derived and derived_attempted(d)]
    return DerivedSignal("derived_retry", bool(failed),
                         f"上次整組衍生成功 {last_derived} 之後未成功的嘗試 {len(failed)} 次")


def _j3_pitches(status: Mapping[str, Any], base: Path) -> int | None:
    """J3 log 的 ``done: {... 'pitches': N ...}`` 加總（A＋D）。讀不到／沒有 done 行 → None。"""
    import re

    try:
        text = (base / str(status["log"])).read_text(encoding="utf-8", errors="replace")
    except (OSError, KeyError, TypeError):
        return None
    counts = [int(m.group(1)) for line in text.splitlines() if "done: {" in line
              for m in [re.search(r"'pitches': (\d+)", line)] if m]
    return sum(counts) if counts else None


def weekly_signals(connection: Any | None = None, *, j3_status: Path = DEFAULT_J3_STATUS,
                   j4_status: Path = DEFAULT_J4_STATUS, base: Path = Path(".")) -> list[DerivedSignal]:
    """§3.2.3 訊號 3（J3）、4（J4），加上「前次衍生未成功」（#364 審核 F3）。

    任何讀取失敗 → fired=None（判斷不了就跑）。
    """
    if connection is None:
        with _readonly_conn() as c:
            return weekly_signals(c, j3_status=j3_status, j4_status=j4_status, base=base)
    try:
        last_pitch_type, last_derived = last_refresh_marks(connection)
        retry = derived_retry_signal(connection, last_derived)
    except Exception as error:  # noqa: BLE001 — fail open
        reason = f"讀不到 refresh_log（{type(error).__name__}）→ 跑"
        return [DerivedSignal("j3_pitches", None, reason), DerivedSignal("j4_box", None, reason),
                DerivedSignal("derived_retry", None, reason)]

    # 訊號 3：J3 成功、完成時刻晚於上次成功的球種推算、寫入球數 > 0。
    try:
        j3 = json.loads((base / j3_status).read_text(encoding="utf-8"))
        finished = _aware(j3.get("finished_at"))
        if j3.get("result") != "ok" or finished is None:
            j3_signal = DerivedSignal("j3_pitches", False, f"J3 狀態 result={j3.get('result')}")
        elif last_pitch_type is not None and finished <= last_pitch_type:
            j3_signal = DerivedSignal("j3_pitches", False,
                                      f"J3 完成 {finished} 早於上次球種推算 {last_pitch_type}")
        else:
            pitches = _j3_pitches(j3, base)
            if pitches is None:
                j3_signal = DerivedSignal("j3_pitches", None, f"J3 完成 {finished} 但讀不到球數 → 跑")
            else:
                j3_signal = DerivedSignal("j3_pitches", pitches > 0,
                                          f"J3 完成 {finished}（晚於 {last_pitch_type}），球數 {pitches}")
    except FileNotFoundError:
        j3_signal = DerivedSignal("j3_pitches", False, f"無 J3 狀態檔 {j3_status}")
    except (OSError, ValueError, TypeError) as error:
        j3_signal = DerivedSignal("j3_pitches", None, f"J3 狀態檔讀不懂（{type(error).__name__}）→ 跑")

    # 訊號 4：box_pitching_revisions 自上次衍生後有新列，或 J4 完成時刻晚於上次衍生。
    if last_derived is None:
        j4_signal = DerivedSignal("j4_box", None, "沒有上次衍生紀錄 → 跑")
    else:
        try:
            new_rows = int(connection.execute(
                "SELECT count(*) FROM cpbl.box_pitching_revisions WHERE fetched_at > %s",
                (last_derived,),
            ).fetchone()[0])
        except Exception as error:  # noqa: BLE001 — fail open
            new_rows = None
            j4_signal = DerivedSignal("j4_box", None, f"讀不到 box_pitching_revisions（{type(error).__name__}）→ 跑")
        if new_rows is not None:
            try:
                j4 = json.loads((base / j4_status).read_text(encoding="utf-8"))
                j4_finished = _aware(j4.get("finished_at")) if j4.get("result") == "ok" else None
            except FileNotFoundError:
                j4_finished = None
            except (OSError, ValueError, TypeError):
                j4_finished = last_derived + timedelta(seconds=1)   # 讀不懂 → 視同較新（fail open）
            newer = j4_finished is not None and j4_finished > last_derived
            j4_signal = DerivedSignal(
                "j4_box", new_rows > 0 or newer,
                f"box_pitching_revisions 自 {last_derived} 後新列 {new_rows}；J4 完成 {j4_finished}")
    return [j3_signal, j4_signal, retry]


# =========================================================================== 今日賽程檔

def taipei_today() -> date:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Asia/Taipei")).date()


def today_games(connection: Any, day: date) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT year, kind_code, game_sno, game_date, venue, away_team_code, home_team_code, "
        "present_status FROM cpbl.games WHERE game_date = %s AND kind_code = ANY(%s) "
        "ORDER BY kind_code, game_sno",
        (day, list(TODAY_FILE_KINDS)),
    ).fetchall()
    return [
        {"key": f"{y}-{k}-{s}", "year": y, "kind_code": k, "game_sno": s,
         "game_date": d.isoformat() if d else None, "venue": venue,
         "away_team_code": away, "home_team_code": home, "present_status": status}
        for y, k, s, d, venue, away, home, status in rows
    ]


def today_schedule_payload(day: date, games: list[dict[str, Any]], *, day_type: str | None,
                           stage: str) -> dict[str, Any]:
    """今日賽程檔內容（#364 → #365 介面）。

    - ``date``：**台北日期** ``YYYY-MM-DD``（``timezone`` 固定 ``Asia/Taipei``）。消費端只在
      ``schema_version`` 認得且 ``date`` ＝ 台北今天時採信，否則退回連 DB。
    - ``games``：本機 ``cpbl.games`` 中 ``game_date = date`` 且賽別屬 ``kinds`` 的列（含延賽保留列；
      ``present_status`` 原樣帶出，是否算「排定場」由消費端決定）。空清單＝本機今天無場。
    - ``counts``：各賽別列數（``kinds`` 每個都有鍵，0 也寫）。
    - ``stage``：``decide``（J1 開頭、爬取前）或 ``after_scrape``（J1 爬完賽程後覆寫）。
    """
    counts = {k: 0 for k in TODAY_FILE_KINDS}
    for g in games:
        counts[g["kind_code"]] = counts.get(g["kind_code"], 0) + 1
    return {
        "schema_version": TODAY_FILE_SCHEMA,
        "date": day.isoformat(),
        "timezone": "Asia/Taipei",
        "generated_at": _now_text(),
        "source": "local cpbl.games",
        "stage": stage,
        "day_type": day_type,
        "kinds": list(TODAY_FILE_KINDS),
        "counts": counts,
        "games": games,
    }


def invalidate_today_schedule(path: Path) -> None:
    """刪掉今日賽程檔，讓消費端（#365）退回連 DB。刪不掉只能交給 shell 再試一次。"""
    try:
        path.unlink(missing_ok=True)
    except OSError as error:
        print(f"WARN 今日賽程檔刪除失敗：{path}（{error}）", file=sys.stderr)


def write_today_schedule(path: Path, day: date, *, day_type: str | None, stage: str) -> dict[str, Any]:
    """寫今日賽程檔；查詢或寫檔任何一步失敗都先刪掉舊檔再外拋（#364 審核 F4）。

    為什麼刪：同一天稍早（decide 階段、或稍早一次手動執行）寫下的檔 ``date`` 也是今天，消費端會
    照單全收。爬取可能剛補進今天的新場，覆寫失敗若留下舊檔，晚間鏈會把有賽日判成無賽日。
    缺檔＝消費端退回 DB，是唯一安全的失敗形狀。
    """
    try:
        with _readonly_conn() as c:
            games = today_games(c, day)
        payload = today_schedule_payload(day, games, day_type=day_type, stage=stage)
        _write_json(path, payload)
    except BaseException:
        invalidate_today_schedule(path)
        raise
    return payload


# =========================================================================== 訓練閘門（§3.5）

# cpbl-train-outcome（models/outcome_gbm.backtest）的走查季數；與該模組 _WALK_SEASONS 同值，
# 由 tests/test_daily_gate.py 對照模組常數釘住（不 import 它：那會連帶載入 LightGBM／sklearn）。
OUTCOME_WALK_SEASONS = 5


def outcome_dataset_signature(per_season: Mapping[int, int]) -> dict[str, Any] | None:
    """各季「完成且非和局」的一軍場數 → 與 ``backtest()`` 寫進 ``cv_metrics`` 相同定義的三個值。

    ``backtest()``：rows＝``game_features`` 中 ``completed AND home_win IN (0,1)``；
    ``test_seasons``＝最近 ``_WALK_SEASONS`` 季中「有更早季」者；``n_train``＝最後一折的訓練列數
    （season < 最後一個 test 季）；``n_test``＝全部 test 季的列數。任何一季多一場完成場，
    ``n_train`` 或 ``n_test`` 必變；新球季則 ``test_seasons`` 變。只有一季（退化 80/20）回 None。
    """
    seasons = sorted(s for s, n in per_season.items() if n > 0)
    test = [s for s in seasons[-OUTCOME_WALK_SEASONS:] if any(o < s for o in seasons)]
    if not test:
        return None
    return {
        "test_seasons": test,
        "n_train": sum(n for s, n in per_season.items() if s < test[-1]),
        "n_test": sum(n for s, n in per_season.items() if s in test),
    }


def local_outcome_signature(connection: Any) -> dict[str, Any] | None:
    """本機 ``cpbl.games`` 依 ``cpbl-build-features`` 的語意算出的 :func:`outcome_dataset_signature`。

    完成判準與 ``features/outcome.py`` 同一支（``completed_games_sql_with_evidence``）；``home_win``
    只有比分不等時才是 0／1（和局為 NULL，被 ``_load`` 排除）。本機特徵尚未重建也無妨：這裡算的是
    「這次若重建＋鏡像，正式站 trainer 會讀到的資料規模」。
    """
    from cpbl.completion import completed_games_sql_with_evidence

    cond = completed_games_sql_with_evidence("g")
    rows = connection.execute(
        "SELECT g.year, count(*) FROM cpbl.games g "
        "WHERE g.kind_code = 'A' AND g.game_date IS NOT NULL "
        "AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL AND g.home_score <> g.away_score "
        f"AND {cond} GROUP BY g.year ORDER BY g.year"
    ).fetchall()
    return outcome_dataset_signature({int(y): int(n) for y, n in rows})


def outcome_train_decision(local: Mapping[str, Any] | None,
                           prod_metrics: Mapping[str, Any] | None) -> tuple[bool, str]:
    """§3.5：本機完成場集合自正式站上次 ``model_versions(task='outcome')`` 後有新增 → 跑。

    比對對象是**正式站**最新那一列的 ``cv_metrics``（trainer 自己寫下的訓練資料規模），所以正式站
    還原到舊模型 → 規模不同 → 跑；VPS 上已手動重訓 → 規模相同 → 不重跑（#364 審核 F1）。
    任一側讀不到或形狀不對 → 跑（fail open 到現況）。
    """
    if local is None:
        return True, "本機訓練資料規模算不出來（不足兩季）→ 照跑"
    if not isinstance(prod_metrics, Mapping):
        return True, "讀不到正式站最新 model_versions(task='outcome') → 照跑"
    try:
        prod = {"test_seasons": [int(s) for s in prod_metrics["test_seasons"]],
                "n_train": int(prod_metrics["n_train"]), "n_test": int(prod_metrics["n_test"])}
    except (KeyError, TypeError, ValueError):
        return True, "正式站 model_versions(task='outcome') 的 cv_metrics 形狀不符 → 照跑"
    if prod == dict(local):
        return False, (f"本機一軍完成場自正式站上次回測後無新增（test={prod['test_seasons']}、"
                       f"n_train={prod['n_train']}、n_test={prod['n_test']}）")
    return True, (f"本機一軍完成場與正式站上次回測不同（正式站 {prod} → 本機 {dict(local)}）")


def parse_prod_metrics(text: str) -> Mapping[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        value = json.loads(text.splitlines()[-1])
    except (ValueError, IndexError):
        return None
    return value if isinstance(value, Mapping) else None


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _now_text() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


# =========================================================================== CLI

def _readonly_conn():
    from contextlib import contextmanager

    from cpbl.db import conn

    @contextmanager
    def ro():
        with conn() as c:
            c.execute("SET TRANSACTION READ ONLY")
            yield c
    return ro()


def build_decision(day: date, *, history: Path, marker: Path, exclude_started_at: str | None,
                   before: datetime | None, probe_mode: str, unsynced_override: str | None,
                   env: Mapping[str, str] | None = None) -> Decision:
    force = force_full(env)
    yesterday = day - timedelta(days=1)
    with _readonly_conn() as c:
        scheduled = local_schedule(c, [yesterday, day])
        counter = local_write_counter(c) if unsynced_override is None else None
    last_ok, last_detail = last_j1_status(history, exclude_started_at=exclude_started_at, before=before)
    if unsynced_override is None:
        unsynced, unsynced_detail = unsynced_writes(marker, counter)
    else:
        unsynced = unsynced_override == "yes"
        unsynced_detail = f"{'有' if unsynced else '無'}（--assume-unsynced {unsynced_override}）"

    def probe() -> ProbeResult:
        if probe_mode != "live":
            return ProbeResult(probe_mode, ("--assume-probe",))
        return stats_probe(day, local_lookup=lambda games: _local_lookup_db(games, day))

    return classify(DayInputs(day, scheduled, last_ok, last_detail, unsynced, unsynced_detail, force),
                    probe)


def _parser() -> argparse.ArgumentParser:
    from cpbl.ingest._cli import cli_parser

    parser = cli_parser("python -m cpbl.ingest.daily_gate", __doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_decide_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
        p.add_argument("--sync-marker", type=Path, default=DEFAULT_SYNC_MARKER)
        p.add_argument("--assume-probe", choices=("live", "clean", "new", "unavailable"), default="live")
        p.add_argument("--assume-unsynced", choices=("yes", "no"))

    decide = sub.add_parser("decide", help="判今天日型，印 DAY_TYPE=<full|light|sync_only|skip>")
    add_decide_args(decide)
    decide.add_argument("--started-at", help="本次執行的 started_at（排除自己那列 running）")
    decide.add_argument("--today-file", type=Path, default=DEFAULT_TODAY_FILE,
                        help="判定後順手寫今日賽程檔（stage=decide）")

    today = sub.add_parser("today-schedule", help="寫今日賽程檔（J1 爬完賽程後覆寫，stage=after_scrape）")
    today.add_argument("--out", type=Path, default=DEFAULT_TODAY_FILE)
    today.add_argument("--day-type", choices=DAY_TYPES)

    plan = sub.add_parser("plan", help="印出某日的日型與步驟清單（唯讀）")
    add_decide_args(plan)
    plan.add_argument("--date", type=date.fromisoformat, help="預設今天；回放時只看該日 10:10 前的歷史")

    mark = sub.add_parser("mark-synced", help="同步成功後記下本機寫入計數器")
    mark.add_argument("--sync-marker", type=Path, default=DEFAULT_SYNC_MARKER)

    gate = sub.add_parser("train-gate", help="§3.5：對照正式站 model_versions，印 RUN_OUTCOME=0|1")
    gate.add_argument("--prod-metrics", type=Path, required=True,
                      help="正式站最新 model_versions(task='outcome').cv_metrics 的 JSON 檔（- ＝stdin；空＝讀不到）")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command in ("decide", "plan"):
        if args.command == "plan" and args.date is not None:
            day = args.date
            before = datetime.combine(day, datetime.min.time()).astimezone().replace(hour=10, minute=10)
            started = None
        else:
            day, before = taipei_today(), None
            started = getattr(args, "started_at", None)
        decision = build_decision(
            day, history=args.history, marker=args.sync_marker, exclude_started_at=started,
            before=before, probe_mode=args.assume_probe, unsynced_override=args.assume_unsynced,
        )
        if args.command == "plan":
            print(f"cpbl-refresh-recent --plan  日期 {day}")
            print(render_plan(decision, force=force_full()))
        else:
            for reason in decision.reasons:
                print(f"REASON={reason}")
            try:
                write_today_schedule(args.today_file, day, day_type=decision.day_type, stage="decide")
                print(f"TODAY_FILE={args.today_file}")
            except Exception as error:  # noqa: BLE001 — 已刪檔，消費端退回 DB；不擋日型判定
                print(f"WARN 今日賽程檔寫入失敗（已刪檔）：{type(error).__name__}: {error}", file=sys.stderr)
            print(f"DAY_TYPE={decision.day_type}")
        return 0
    if args.command == "today-schedule":
        payload = write_today_schedule(args.out, taipei_today(), day_type=args.day_type,
                                       stage="after_scrape")
        print(f"today schedule {args.out} date={payload['date']} counts={payload['counts']}")
        return 0
    if args.command == "mark-synced":
        with _readonly_conn() as c:
            counter = local_write_counter(c)
        _write_json(args.sync_marker, {"write_counter": counter, "synced_at": _now_text()})
        print(f"sync marker write_counter={counter}")
        return 0
    if args.command == "train-gate":
        raw = sys.stdin.read() if str(args.prod_metrics) == "-" else args.prod_metrics.read_text(
            encoding="utf-8")
        with _readonly_conn() as c:
            local = local_outcome_signature(c)
        run, reason = outcome_train_decision(local, parse_prod_metrics(raw))
        print(f"OUTCOME_LOCAL={json.dumps(local, ensure_ascii=False)}")
        print(f"OUTCOME_REASON={reason}")
        print(f"RUN_OUTCOME={1 if run else 0}")
        return 0
    return 64


if __name__ == "__main__":
    sys.exit(main())
