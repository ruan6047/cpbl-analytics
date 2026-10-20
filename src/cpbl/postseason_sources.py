"""#293 S12 WP1：季後目標場三來源（final／box／PA）送達狀態的唯讀分類器。

只從**既有資料**推導，不新增表、不改 completion 判準、不改 PA builder、不改 S02 契約檔（PLAN r2 §5 WP1）：

* **final**：``cpbl.completion``（:func:`~cpbl.completion.completed_games_sql_with_evidence`，與 API 同一支）。
  ⛔ 非零比分、日期已過、refresh 成功都**不等於**完賽（G03）——本模組根本不讀那些訊號。
* **box**：本機 box 核心六表（與 ``run_refresh_recent._POSTSEASON_CORE_DETAIL_TABLES`` 同一組）是否都有列；
  逐球 ``pitch_tracking`` 官方可能 0 球，不列入「到齊」條件（不擋 box 核心先送），但照樣對帳列數。
  ⭐ 逐球晚到（#293 fix-5，需求方裁定 6293763437）：box 核心已送達、但該場依既有逐球覆蓋判準
  （:func:`cpbl.pitch_coverage.lagging_pitch_games_sql`：近期實證有設備的球場、逐球覆蓋 < 85%）仍落後
  → ``pending_update``／``tracking_pending``，⛔ 不得判 ``delivered``（G3 實例：box 送出時 0 球、官方事後
  才發布 291 球）。球場近期沒有設備的場不落後，照常判送達、不等。
* **PA**：本機是否有 published build；有待收尾的 ``reconciliation_required``（官方更正）時照實記
  ``official_correction_pending``，不算完成（舊 published 保留）。
* **production 端**：只認 scoped 同步的對帳 manifest（``cpbl.ingest.boxpa_sync reconcile`` 的輸出）。
  沒有 manifest＝沒有證據＝``unknown``，不推定已送達（例：E1–E4 由隔日 10:10 每日鏈送達，本模組看不到）。

狀態值：``delivered``（本機到齊且 production 對帳相等）／``pending_update``（附 ``reason``）／
``delivered_conflict``（重送一次後對帳仍不等）／``unknown``（沒有 production 證據）。

**同晚**＝台北「賽事日」的隔日 00:00 之前（需求方裁定 Q2：台北當日 24:00 前）。送達時刻晚於界線，或
界線已過仍未送達 → ``same_night=False``（同晚未達）；界線未到且未送達 → ``None``（未定）。
沒有鐘點截止：跨過 24:00 照常處理，只是如實記成同晚未達。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")

# 與 run_refresh_recent._POSTSEASON_CORE_DETAIL_TABLES 同一組（tests/test_postseason_sources.py 釘住）。
BOX_CORE_TABLES: tuple[str, ...] = (
    "batting_gamelog", "pitching_gamelog", "game_livelog", "game_scoreboard",
    "game_detail", "pitching_game_flags",
)
BOX_ALL_TABLES: tuple[str, ...] = (*BOX_CORE_TABLES, "pitch_tracking")
PA_TABLES: tuple[str, ...] = (
    "game_recap_source_revisions", "game_recap_builds", "game_plate_appearances",
    "game_pa_events", "game_pa_pitch_mappings",
)

DELIVERED = "delivered"
PENDING = "pending_update"
CONFLICT = "delivered_conflict"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class LocalFacts:
    """一場比賽在本機的既有事實（由 :func:`load_local_facts` 讀出，或由測試從真實資料快照載入）。"""
    key: str                                   # YYYY-K-SNO
    game_date: str | None                      # ISO
    completed: bool                            # cpbl.completion 正式判準
    final_first_seen: str | None               # 官方 final 狀態列首次觀測（ISO, 帶時區）
    box_counts: Mapping[str, int]              # BOX_ALL_TABLES 逐表列數
    box_local_at: str | None                   # box 來源本機最後到達時刻（livelog／scoreboard revision、detail、flags 取最大）
    published_build: str | None
    published_at: str | None
    reconciliation_outstanding: int = 0
    pa_counts: Mapping[str, int] = field(default_factory=dict)
    # 依既有逐球覆蓋判準（cpbl.pitch_coverage）此場逐球仍落後：設備球場、覆蓋 < 85%（#293 fix-5）。
    tracking_lagging: bool = False


@dataclass(frozen=True)
class SourceStatus:
    status: str
    reason: str | None
    local_at: str | None
    prod_at: str | None
    same_night: bool | None


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    at = datetime.fromisoformat(ts)
    return at if at.tzinfo else at.replace(tzinfo=TAIPEI)


def same_night_deadline(game_date: str | date) -> datetime:
    """台北賽事日的隔日 00:00（＝當日 24:00）。"""
    d = date.fromisoformat(game_date) if isinstance(game_date, str) else game_date
    return datetime.combine(d + timedelta(days=1), time(0, 0), tzinfo=TAIPEI)


def same_night(game_date: str | None, delivered_at: str | None, now: datetime) -> bool | None:
    if not game_date:
        return None
    deadline = same_night_deadline(game_date)
    at = _parse(delivered_at)
    if at is not None:
        return at < deadline
    return False if now >= deadline else None


def _latest(*stamps: str | None) -> str | None:
    parsed = [p for p in (_parse(s) for s in stamps) if p is not None]
    return max(parsed).isoformat() if parsed else None


def classify(facts: LocalFacts, manifest: Mapping[str, Any] | None, now: datetime, *,
             exhausted: Iterable[str] = (), final_prod_at: str | None = None) -> dict[str, SourceStatus]:
    """單場三來源分類（純函式）。

    ``manifest``＝該場最近一次 scoped 同步對帳結果（``boxpa_sync reconcile`` 輸出中 ``games[key]``，
    加上 ``at``）；``exhausted``＝同來源重送一次也已用掉的來源（``"box"``／``"pa"``）。
    ``final_prod_at``＝production 端首次確認完賽的時刻（scoped 同步自檢通過或晚間結果鏈 T3），沒有就 ``None``。
    """
    exhausted = set(exhausted)
    sync_at = (manifest or {}).get("at")
    # ---- final
    if not facts.completed:
        final = SourceStatus(PENDING, "not_final", None, None,
                             same_night(facts.game_date, None, now))
    else:
        final = SourceStatus(DELIVERED if final_prod_at else UNKNOWN,
                             None if final_prod_at else "no_prod_evidence",
                             facts.final_first_seen, final_prod_at,
                             same_night(facts.game_date, final_prod_at, now))
    # ---- box
    missing = [t for t in BOX_CORE_TABLES if not facts.box_counts.get(t)]
    if not facts.completed:
        box = SourceStatus(PENDING, "not_final", None, None, same_night(facts.game_date, None, now))
    elif missing:
        box = SourceStatus(PENDING, "local_box_incomplete:" + "/".join(missing), None, None,
                           same_night(facts.game_date, None, now))
    else:
        box = _prod_side(facts, manifest, sync_at, now, "box" in exhausted, kind="box",
                         local_at=facts.box_local_at,
                         local_counts={t: facts.box_counts.get(t, 0) for t in BOX_ALL_TABLES})
        # 逐球晚到（#293 fix-5）：box 核心已送達而逐球仍落後 → 待更新，⛔ 不判送達（假齊備）。
        # 只覆寫 delivered：尚未送過的 box 照常送（逐球不擋 box 核心先到）。
        if facts.tracking_lagging and box.status == DELIVERED:
            box = SourceStatus(PENDING, "tracking_pending", box.local_at, None,
                               same_night(facts.game_date, None, now))
    # ---- PA（只有真正依賴 PA 的讀取面看這一格）
    if not facts.completed:
        pa = SourceStatus(PENDING, "not_final", None, None, same_night(facts.game_date, None, now))
    elif not facts.published_build:
        pa = SourceStatus(PENDING, "no_local_published_build", None, None,
                          same_night(facts.game_date, None, now))
    else:
        pa = _prod_side(facts, manifest, sync_at, now, "pa" in exhausted, kind="pa",
                        local_at=facts.published_at,
                        local_counts={t: facts.pa_counts.get(t, 0) for t in PA_TABLES})
        if facts.reconciliation_outstanding and pa.status == DELIVERED:
            pa = SourceStatus(PENDING, "official_correction_pending", pa.local_at, pa.prod_at, pa.same_night)
    return {"final": final, "box": box, "pa": pa}


def _prod_side(facts: LocalFacts, manifest: Mapping[str, Any] | None, sync_at: str | None,
               now: datetime, retries_exhausted: bool, *, kind: str, local_at: str | None,
               local_counts: Mapping[str, int]) -> SourceStatus:
    if not manifest:
        return SourceStatus(UNKNOWN, "no_prod_evidence", local_at, None,
                            same_night(facts.game_date, None, now)
                            if not _after_deadline(facts.game_date, local_at) else False)
    sync_at = manifest.get(f"{kind}_at") or sync_at   # 依來源合併的 manifest 各自帶送達時刻
    ok = manifest.get(f"{kind}_ok")
    tables = manifest.get(kind) or {}
    synced_counts = {t: (tables.get(t) or {}).get("local") for t in local_counts}
    if ok is None:
        return SourceStatus(PENDING, "not_synced", local_at, None, same_night(facts.game_date, None, now))
    if not ok:
        status, reason = (CONFLICT, "reconcile_mismatch") if retries_exhausted else (
            PENDING, "reconcile_mismatch_retrying")
        return SourceStatus(status, reason, local_at, None, same_night(facts.game_date, None, now))
    if synced_counts != dict(local_counts) or (
            kind == "pa" and manifest.get("published_build_local") != facts.published_build):
        return SourceStatus(PENDING, "local_changed_since_sync", local_at, None,
                            same_night(facts.game_date, None, now))
    return SourceStatus(DELIVERED, None, local_at, sync_at, same_night(facts.game_date, sync_at, now))


def _after_deadline(game_date: str | None, at: str | None) -> bool:
    parsed = _parse(at)
    return bool(game_date and parsed and parsed >= same_night_deadline(game_date))


def as_dict(statuses: Mapping[str, SourceStatus]) -> dict[str, dict]:
    return {k: asdict(v) for k, v in statuses.items()}


# =========================================================================== 本機讀取（唯讀）

def load_local_facts(cur: Any, keys: Iterable[tuple[int, str, int]]) -> dict[str, LocalFacts]:
    """讀本機既有資料組成 :class:`LocalFacts`。``cur`` 為一般 psycopg cursor（tuple row）。只 SELECT。"""
    from cpbl.completion import completed_games_sql_with_evidence
    from cpbl.pitch_coverage import lagging_pitch_games_sql

    keys = sorted(set(keys))
    if not keys:
        return {}
    out: dict[str, LocalFacts] = {}
    done = completed_games_sql_with_evidence("g")
    # 逐球落後：每個 (year, kind) 跑一次既有判準；days_back=1 涵蓋晚間鏈的目標窗（台北今日／昨日）。
    lagging = {(y, k): {int(r[0]) for r in cur.execute(lagging_pitch_games_sql(), (y, k, 1)).fetchall()}
               for y, k in sorted({(y, k) for y, k, _ in keys})}
    for year, kind, sno in keys:
        p = (year, kind, sno)
        row = cur.execute(
            f"SELECT g.game_date, COALESCE({done}, FALSE) FROM cpbl.games g "
            "WHERE g.year = %s AND g.kind_code = %s AND g.game_sno = %s", p).fetchone()
        if row is None:
            continue
        game_date, completed = row
        final_seen = cur.execute(
            "SELECT min(fetched_at) FROM cpbl.game_schedule_status_revisions "
            "WHERE year = %s AND kind_code = %s AND game_sno = %s "
            "AND raw_present_status = 1 AND raw_game_result = '0'", p).fetchone()[0]
        box_counts = {}
        for t in BOX_ALL_TABLES:   # 表名來自模組常數
            box_counts[t] = cur.execute(
                f"SELECT count(*) FROM cpbl.{t} WHERE year = %s AND kind_code = %s AND game_sno = %s",
                p).fetchone()[0]
        pa_counts = {}
        for t in PA_TABLES:
            pa_counts[t] = cur.execute(
                f"SELECT count(*) FROM cpbl.{t} WHERE year = %s AND kind_code = %s AND game_sno = %s",
                p).fetchone()[0]
        rev_at, detail_at, flags_at = cur.execute(
            """SELECT (SELECT max(fetched_at) FROM cpbl.game_source_revisions
                        WHERE year = %(y)s AND kind_code = %(k)s AND game_sno = %(s)s
                          AND source IN ('livelog', 'scoreboard')),
                      (SELECT max(updated_at) FROM cpbl.game_detail
                        WHERE year = %(y)s AND kind_code = %(k)s AND game_sno = %(s)s),
                      (SELECT max(source_fetched_at) FROM cpbl.pitching_game_flags
                        WHERE year = %(y)s AND kind_code = %(k)s AND game_sno = %(s)s)""",
            {"y": year, "k": kind, "s": sno}).fetchone()
        pub = cur.execute(
            "SELECT build_id::text, built_at FROM cpbl.game_recap_builds WHERE year = %s AND kind_code = %s "
            "AND game_sno = %s AND state = 'published'", p).fetchone()
        recon = cur.execute(
            "SELECT count(*) FROM cpbl.game_recap_builds WHERE year = %s AND kind_code = %s "
            "AND game_sno = %s AND state = 'reconciliation_required'", p).fetchone()[0]
        key = f"{year}-{kind}-{sno}"
        out[key] = LocalFacts(
            key=key, game_date=game_date.isoformat() if game_date else None, completed=bool(completed),
            final_first_seen=final_seen.isoformat() if final_seen else None,
            box_counts=box_counts,
            box_local_at=_latest(*(x.isoformat() if x else None for x in (rev_at, detail_at, flags_at))),
            published_build=pub[0] if pub else None,
            published_at=pub[1].isoformat() if pub else None,
            reconciliation_outstanding=int(recon), pa_counts=pa_counts,
            tracking_lagging=sno in lagging[(year, kind)])
    return out


def facts_to_json(facts: LocalFacts) -> dict:
    return {**asdict(facts), "box_counts": dict(facts.box_counts), "pa_counts": dict(facts.pa_counts)}


def facts_from_json(raw: Mapping[str, Any]) -> LocalFacts:
    return LocalFacts(**{**raw, "box_counts": dict(raw["box_counts"]), "pa_counts": dict(raw.get("pa_counts") or {})})
