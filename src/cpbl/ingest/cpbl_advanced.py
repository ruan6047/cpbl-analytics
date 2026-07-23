"""官方進階數據爬蟲（stats.cpbl.com.tw 官方 leaderboard JSON API）。

端點：`/api/proxy/v1/leaderboards/{pr-table,exit-velocity,batted-ball,pitch-tracking,summary}`
（免瀏覽器，支援 `gameKind=A/D`、`searchType=batter/pitcher`）。

INGEST-ADV-RECONCILE1 後的資料流：
- **scalar 三表**（pr-table / exit-velocity / batted-ball）依 `Player.Acnt` 合併 →
  `advanced_stats`（dataset=`player_stats`）。**不再併入 pitch-tracking**（避免以 acnt 為唯一 key
  覆寫多球種列）。
- **pitch-tracking**（每投手最多 fastball/breakingball 兩列）→ `advanced_pitch_type_stats`，
  natural key `(year,kind_code,role,acnt,pitch_type)`。
- **summary**（聯盟基準）→ `advanced_league_summary`，key `(year,kind_code,category,pitch_type)`。

兩種寫入路徑：
- `run_full_snapshot()`：全量 fetch → run manifest 驗證 → 單一 transaction 原子晉升（見
  `advanced_snapshot`）。供 `cpbl-scrape-advanced` 與 `cpbl-reconcile-advanced`。
- `scrape_advanced_result()`：daily partial refresh（refresh_recent 用）；只刷新已觀測 acnt 的
  scalar 值 + last_seen_at，掛在現行 promoted pointer 底下，不晉升、不刪列。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from cpbl.db import conn
from cpbl.ingest import advanced_snapshot as snap
from cpbl.ingest.advanced_snapshot import RunSpec, ValidationReport

log = logging.getLogger("cpbl.advanced")

BASE = "https://stats.cpbl.com.tw"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# scalar leaderboards（合併成一位球員一列）。pitch-tracking 另走 pitch_type dataset。
_SCALAR_LEADERBOARDS = ("pr-table", "exit-velocity", "batted-ball")
_PITCH_TRACKING = "pitch-tracking"
_SUMMARY = "summary"
# PascalCase → 既有 lowerCamel 例外修正（少數不規則鍵）。
_KEY_FIX = {"Ev50th": "ev50Th", "Ev90th": "ev90Th", "DistanceAvgHR": "distanceAvgHr", "BrlsBBEp": "brlsBbEp"}


def _norm_key(k: str) -> str:
    if k in _KEY_FIX:
        return _KEY_FIX[k]
    return (k[0].lower() + k[1:]).replace("PR", "Pr")


def _client() -> httpx.Client:
    return httpx.Client(timeout=40.0, follow_redirects=True,
                        headers={"User-Agent": UA, "Accept": "application/json",
                                 "Referer": f"{BASE}/rankings"})


def _leaderboard_rows(client: httpx.Client, lb: str, params: dict) -> list[dict]:
    r = client.get(f"{BASE}/api/proxy/v1/leaderboards/{lb}", params=params)
    r.raise_for_status()
    data = r.json().get("Data") or {}
    return data.get("Leaderboard") or []


# ---------- legacy typed 欄位 ↔ metrics key（向後相容；分析走 advanced_flat view）----------
_LEGACY = (
    ("pa", "pa"), ("woba", "woba"), ("woba_pr", "wobaPr"), ("ba", "ba"), ("ba_pr", "baPr"),
    ("slg", "slg"), ("slg_pr", "slgPr"), ("iso", "iso"), ("iso_pr", "isoPr"),
    ("obp", "obp"), ("obp_pr", "obpPr"), ("brl", "brl"), ("brl_pr", "brlPr"),
    ("brlp", "brlp"), ("brlp_pr", "prlpPr"), ("ev", "ev"), ("ev_pr", "evPr"),
    ("max_ev", "maxEv"), ("max_ev_pr", "maxEvPr"), ("hardhitp", "hardHitp"), ("hardhitp_pr", "hardHitpPr"),
    ("kp", "kp"), ("kp_pr", "kpPr"), ("bbp", "bbp"), ("bbp_pr", "bbpPr"),
    ("whiffp", "whiffp"), ("whiffp_pr", "whiffpPr"), ("chasep", "chasep"), ("chasep_pr", "chasepPr"),
)
_STAT_PK = ("year", "kind_code", "acnt", "role")
_STAT_BASE_COLS = ["year", "kind_code", "acnt", "role", "metrics"] + [c for c, _ in _LEGACY]
_STAT_SRC_COLS = ["source_run_id", "source_fetched_at", "last_seen_at"]
_STAT_COLS = _STAT_BASE_COLS + _STAT_SRC_COLS


def _stat_upsert_sql() -> str:
    ph = ",".join("%s::jsonb" if c == "metrics" else "%s" for c in _STAT_COLS)
    non_pk = [c for c in _STAT_COLS if c not in _STAT_PK]
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in non_pk) + ", updated_at=now()"
    return (f"INSERT INTO cpbl.advanced_stats ({','.join(_STAT_COLS)}) VALUES ({ph}) "
            f"ON CONFLICT (year, kind_code, acnt, role) DO UPDATE SET {updates}")


def _record(merged: dict, year: int, acnt: str, role: str, kind_code: str = "A") -> tuple:
    """DB-free：組 advanced_stats base 欄位（不含 source_* provenance）。"""
    return (year, kind_code, acnt, role, json.dumps(merged, ensure_ascii=False)) + tuple(
        merged.get(jk) for _, jk in _LEGACY)


# ============================================================================
# Fetch（分 dataset）
# ============================================================================

@dataclass
class ScalarFetch:
    data: dict[str, dict]  # {acnt: 合併指標}
    report: ValidationReport


def _merge_scalar(client: httpx.Client, search_type: str, game_kind: str, year: int,
                  delay: float = 0.5) -> ScalarFetch:
    """scalar 三表依 acnt 合併並附驗證計數（空 acnt skip、重複 key）。"""
    out: dict[str, dict] = {}
    rep = ValidationReport()
    for lb in _SCALAR_LEADERBOARDS:
        rows = _leaderboard_rows(client, lb, {"searchType": search_type, "gameKind": game_kind,
                                              "year": str(year)})
        seen_in_lb: set[str] = set()
        for row in rows:
            rep.observed_rows += 1
            acnt = (row.get("Player") or {}).get("Acnt")
            if not acnt:
                rep.empty_id_rows += 1
                continue
            if acnt in seen_in_lb:
                rep.duplicate_key_rows += 1
            seen_in_lb.add(acnt)
            m = out.setdefault(acnt, {})
            for k, v in row.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    m[_norm_key(k)] = v
        time.sleep(delay)
    rep.accepted_rows = len(out)
    return ScalarFetch(out, rep)


def _fetch_leaderboards(client: httpx.Client, search_type: str, game_kind: str, year: int,
                        delay: float = 0.5) -> dict[str, dict]:
    """相容既有 partial 路徑與測試：回 {acnt: 合併 scalar 指標}（不含 pitch-tracking）。"""
    return _merge_scalar(client, search_type, game_kind, year, delay=delay).data


@dataclass
class PitchTypeFetch:
    rows: list[tuple]  # (acnt, pitch_type, pitches, kph, kph_max, spin_rate, spin_rate_max, throws, payload)
    report: ValidationReport


def _to_num(v) -> float | int | None:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _fetch_pitch_type(client: httpx.Client, search_type: str, game_kind: str, year: int,
                      delay: float = 0.5) -> PitchTypeFetch:
    """pitch-tracking leaderboard：每 (acnt, pitch_type) 一列，保存球數/球速/轉速/慣用手。"""
    rows_raw = _leaderboard_rows(client, _PITCH_TRACKING,
                                 {"searchType": search_type, "gameKind": game_kind, "year": str(year)})
    rep = ValidationReport(observed_rows=len(rows_raw))
    seen: set[tuple[str, str]] = set()
    out: list[tuple] = []
    for row in rows_raw:
        acnt = (row.get("Player") or {}).get("Acnt")
        pt = row.get("PitchType")
        if not acnt or not pt:
            rep.empty_id_rows += 1
            continue
        key = (acnt, pt)
        if key in seen:
            rep.duplicate_key_rows += 1
            continue
        seen.add(key)
        out.append((acnt, pt, _to_num(row.get("Pitches")), _to_num(row.get("Kph")),
                    _to_num(row.get("KphMax")), _to_num(row.get("SpinRate")),
                    _to_num(row.get("SpinRateMax")), row.get("Throws"),
                    json.dumps(row, ensure_ascii=False)))
    rep.accepted_rows = len(out)
    time.sleep(delay)
    return PitchTypeFetch(out, rep)


@dataclass
class SummaryFetch:
    rows: list[tuple]  # (category, pitch_type, metrics_json, payload_json)
    report: ValidationReport


def _summary_dict(client: httpx.Client, game_kind: str, year: int) -> dict:
    """summary 端點：回 Data.Leaderboard（dict of category → rows）。"""
    r = client.get(f"{BASE}/api/proxy/v1/leaderboards/{_SUMMARY}",
                   params={"gameKind": game_kind, "year": str(year)})
    r.raise_for_status()
    return (r.json().get("Data") or {}).get("Leaderboard") or {}


def _fetch_league_summary(client: httpx.Client, game_kind: str, year: int,
                          delay: float = 0.5) -> SummaryFetch:
    """summary：Data.Leaderboard 為 {BattedBall,ExitVelocity,PrTable,PitchTracking}，
    各 category 一或多列（PitchTracking 依球種）。Player=null，不塞進 advanced_stats。"""
    lb = _summary_dict(client, game_kind, year)
    rep = ValidationReport()
    seen: set[tuple[str, str]] = set()
    out: list[tuple] = []
    for category, arr in lb.items():
        for row in (arr or []):
            rep.observed_rows += 1
            if not category:
                rep.empty_id_rows += 1
                continue
            pt = row.get("PitchType") or ""
            key = (category, pt)
            if key in seen:
                rep.duplicate_key_rows += 1
                continue
            seen.add(key)
            metrics = {_norm_key(k): v for k, v in row.items()
                       if isinstance(v, (int, float)) and not isinstance(v, bool)}
            out.append((category, pt, json.dumps(metrics, ensure_ascii=False),
                        json.dumps(row, ensure_ascii=False)))
    rep.accepted_rows = len(out)
    time.sleep(delay)
    return SummaryFetch(out, rep)


# ============================================================================
# Full snapshot（run manifest + 原子晉升）
# ============================================================================

def _now() -> datetime:
    return datetime.now(UTC)


def _stage_player_stats(cur, run_id: int, data: dict[str, dict], year: int, kind_code: str,
                        role: str, fetched_at: datetime) -> None:
    now = _now()
    sql = _stat_upsert_sql()
    params = [_record(m, year, acnt, role, kind_code) + (run_id, fetched_at, now)
              for acnt, m in data.items()]
    if params:
        cur.executemany(sql, params)


def _stage_pitch_type(cur, run_id: int, rows: list[tuple], year: int, kind_code: str,
                      role: str, fetched_at: datetime) -> None:
    now = _now()
    params = [(year, kind_code, role, acnt, pt, pit, kph, kmax, sr, srmax, throws,
               run_id, fetched_at, now, payload)
              for (acnt, pt, pit, kph, kmax, sr, srmax, throws, payload) in rows]
    if params:
        cur.executemany(
            """
            INSERT INTO cpbl.advanced_pitch_type_stats
                (year, kind_code, role, acnt, pitch_type, pitches, kph, kph_max,
                 spin_rate, spin_rate_max, throws, source_run_id, source_fetched_at,
                 last_seen_at, source_payload)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT (year, kind_code, role, acnt, pitch_type) DO UPDATE SET
                pitches=EXCLUDED.pitches, kph=EXCLUDED.kph, kph_max=EXCLUDED.kph_max,
                spin_rate=EXCLUDED.spin_rate, spin_rate_max=EXCLUDED.spin_rate_max,
                throws=EXCLUDED.throws, source_run_id=EXCLUDED.source_run_id,
                source_fetched_at=EXCLUDED.source_fetched_at, last_seen_at=EXCLUDED.last_seen_at,
                source_payload=EXCLUDED.source_payload, updated_at=now()
            """,
            params,
        )


def _stage_league_summary(cur, run_id: int, rows: list[tuple], year: int, kind_code: str,
                          fetched_at: datetime) -> None:
    now = _now()
    params = [(year, kind_code, category, pt, metrics, run_id, fetched_at, now, payload)
              for (category, pt, metrics, payload) in rows]
    if params:
        cur.executemany(
            """
            INSERT INTO cpbl.advanced_league_summary
                (year, kind_code, category, pitch_type, metrics, source_run_id,
                 source_fetched_at, last_seen_at, source_payload)
            VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb)
            ON CONFLICT (year, kind_code, category, pitch_type) DO UPDATE SET
                metrics=EXCLUDED.metrics, source_run_id=EXCLUDED.source_run_id,
                source_fetched_at=EXCLUDED.source_fetched_at, last_seen_at=EXCLUDED.last_seen_at,
                source_payload=EXCLUDED.source_payload, updated_at=now()
            """,
            params,
        )


@dataclass
class DatasetOutcome:
    spec: RunSpec
    run_id: int | None
    promoted: bool
    report: ValidationReport
    error: str | None = None


def _run_dataset(spec: RunSpec, scope: str, source_endpoint: str, fetched_at: datetime,
                 report: ValidationReport, stage_fn, dry_run: bool) -> DatasetOutcome:
    """共用晉升流程：驗證 → open_run → promote / reject。dry_run 不寫任何資料。"""
    snap.validate(spec, report)
    if dry_run:
        return DatasetOutcome(spec, None, False, report,
                              error=None if report.ok else "validation_failed(dry-run)")
    run_id = snap.open_run(spec, scope, source_endpoint, fetched_at,
                           observed_rows=report.observed_rows)
    if not report.ok:
        snap.reject_run(run_id, report)
        return DatasetOutcome(spec, run_id, False, report, error="validation_failed")
    try:
        snap.promote_full(spec, run_id, stage_fn, report)
    except Exception as e:  # noqa: BLE001 — 晉升失敗整筆 rollback，run 標 failed 留審計
        snap.reject_run(run_id, report, status="failed")
        log.error("promote %s 失敗：%s", spec, e)
        return DatasetOutcome(spec, run_id, False, report, error=str(e))
    return DatasetOutcome(spec, run_id, True, report)


def run_full_snapshot(year: int, kind_code: str = "A",
                      roles: tuple[str, ...] = ("batting", "pitching"),
                      delay: float = 0.5, dry_run: bool = False,
                      client: httpx.Client | None = None) -> list[DatasetOutcome]:
    """對 (year, kind_code) 全量抓 player_stats / pitch_type_stats（依 role）+ league_summary，
    各自建立 full run 並原子晉升。回傳每個 dataset run 的 outcome。"""
    own = client is None
    http = client or _client()
    outcomes: list[DatasetOutcome] = []
    search = {"batting": "batter", "pitching": "pitcher"}
    try:
        for role in roles:
            st = search[role]
            fetched_at = _now()
            sf = _merge_scalar(http, st, kind_code, year, delay=delay)
            spec = RunSpec(year, kind_code, "player_stats", role)
            outcomes.append(_run_dataset(
                spec, "full", "leaderboards/pr-table+exit-velocity+batted-ball", fetched_at, sf.report,
                lambda cur, rid, d=sf.data, y=year, k=kind_code, r=role, f=fetched_at:
                    _stage_player_stats(cur, rid, d, y, k, r, f), dry_run))

            fetched_at = _now()
            pf = _fetch_pitch_type(http, st, kind_code, year, delay=delay)
            spec = RunSpec(year, kind_code, "pitch_type_stats", role)
            outcomes.append(_run_dataset(
                spec, "full", "leaderboards/pitch-tracking", fetched_at, pf.report,
                lambda cur, rid, rows=pf.rows, y=year, k=kind_code, r=role, f=fetched_at:
                    _stage_pitch_type(cur, rid, rows, y, k, r, f), dry_run))

        fetched_at = _now()
        lf = _fetch_league_summary(http, kind_code, year, delay=delay)
        spec = RunSpec(year, kind_code, "league_summary", "")
        outcomes.append(_run_dataset(
            spec, "full", "leaderboards/summary", fetched_at, lf.report,
            lambda cur, rid, rows=lf.rows, y=year, k=kind_code, f=fetched_at:
                _stage_league_summary(cur, rid, rows, y, k, f), dry_run))
    finally:
        if own:
            http.close()
    return outcomes


# ============================================================================
# Partial refresh（daily；refresh_recent 用）
# ============================================================================

def _upsert(records: list[tuple]) -> int:
    """partial：把 scalar 記錄掛到現行 promoted pointer 底下 UPSERT（無 pointer 時 source_run_id NULL）。"""
    if not records:
        return 0
    now = _now()
    specs = {(r[0], r[1], r[3]) for r in records}  # (year, kind_code, role)
    runmap = {s: snap.current_run_id(RunSpec(s[0], s[1], "player_stats", s[2])) for s in specs}
    sql = _stat_upsert_sql()
    params = [r + (runmap[(r[0], r[1], r[3])], now, now) for r in records]
    with conn() as c:
        c.cursor().executemany(sql, params)
    return len(records)


@dataclass(frozen=True)
class AdvancedScrapeResult:
    rows: int
    outcome: str
    error_codes: tuple[str, ...]


def scrape_advanced_result(year: int, players: list[tuple[str, str]], delay: float = 1.0,
                           kind_code: str = "A") -> AdvancedScrapeResult:
    """daily partial refresh：只更新已觀測 acnt 的 scalar 值。保留可觀測 outcome；
    個別 role 抓取失敗不中斷、記 error code。不晉升快照、不宣稱完整。"""
    client = _client()
    records: list[tuple] = []
    errors: list[str] = []
    want_b = {a for a, r in players if r == "batting"}
    want_p = {a for a, r in players if r == "pitching"}
    try:
        for role, search_type, want in (("batting", "batter", want_b), ("pitching", "pitcher", want_p)):
            if not want:
                continue
            try:
                lb = _fetch_leaderboards(client, search_type, kind_code, year, delay=min(delay, 0.5))
            except httpx.HTTPError as e:
                log.warning("leaderboard %s/%s 抓取失敗：%s", search_type, kind_code, e)
                errors.append(f"{role}_http_error")
                continue
            records += [_record(m, year, a, role, kind_code) for a, m in lb.items() if a in want and m]
            log.info("進階 %s kind=%s：leaderboard %d 人，命中 %d",
                     role, kind_code, len(lb), sum(1 for a in lb if a in want))
    finally:
        client.close()
    rows = _upsert(records)
    outcome = "error" if errors else ("available" if rows > 0 else "missing")
    return AdvancedScrapeResult(rows=rows, outcome=outcome, error_codes=tuple(errors))


def scrape_advanced(year: int, players: list[tuple[str, str]], delay: float = 1.0,
                    kind_code: str = "A") -> int:
    """相容既有 CLI 的整數介面。"""
    return scrape_advanced_result(year, players, delay=delay, kind_code=kind_code).rows


def current_players() -> list[tuple[str, str]]:
    """本季登錄選手 [(acnt, role)]；同時是打者與投手者取打者（進攻數值較常看）。"""
    with conn() as c:
        bats = {r[0] for r in c.execute("SELECT DISTINCT player_id FROM cpbl.batting_current").fetchall()}
        pits = {r[0] for r in c.execute("SELECT DISTINCT player_id FROM cpbl.pitching_current").fetchall()}
    players = [(a, "batting") for a in sorted(bats)]
    players += [(a, "pitching") for a in sorted(pits - bats)]
    return players
