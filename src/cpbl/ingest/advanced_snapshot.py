"""進階排行榜 run-manifest 快照晉升機制（INGEST-ADV-RECONCILE1）。

模型
----
full run：全量 fetch（在記憶體）→ 單一 transaction 內 stage（寫入目標表並標 source_run_id）
→ 鎖 run 驗 scope/identity → status='promoted' → UPSERT advanced_snapshot_state pointer
→ 刪該 scope 中 source_run_id 非本 run 的殘列。任一步失敗整筆 rollback，run 另記 rejected。

partial run：只 UPSERT 已觀測 acnt 的數值 + last_seen_at，掛在「現行 promoted pointer」的
run_id 底下（維持可見性），不建立新 pointer、不刪列、不宣稱完整快照。無 pointer 時退回 legacy
UPSERT（source_run_id NULL）以保留 reconcile 前既有行為。

gating：public 讀取只回「source_run_id = 該 scope 現行 pointer」的列；scope 尚無 pointer 時
只回 source_run_id IS NULL 的 legacy 列（見 GATING_PREDICATE 與 migration 063 的 advanced_flat）。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime

from cpbl.db import conn

log = logging.getLogger("cpbl.advanced.snapshot")

DATASETS = ("player_stats", "pitch_type_stats", "league_summary")
DATASET_TABLE = {
    "player_stats": "cpbl.advanced_stats",
    "pitch_type_stats": "cpbl.advanced_pitch_type_stats",
    "league_summary": "cpbl.advanced_league_summary",
}
# 晉升合理筆數下限（低於此視為 fetch 異常，拒絕晉升，不覆寫現行快照）。
MIN_ACCEPTED = {"player_stats": 30, "pitch_type_stats": 20, "league_summary": 1}
# 相對前一 promoted 快照的最低保留比例（避免半殘快照取代完整快照）。
MIN_RETAIN_RATIO = 0.5


def gating_predicate(alias: str, dataset: str = "player_stats") -> str:
    """回傳一段 SQL 片段：`alias` 那列是否屬於現行 promoted 快照（或 legacy 未管理列）。

    含 role 維度的 dataset（player_stats / pitch_type_stats）以 alias.role 對齊 pointer.role；
    無 role 維度的 league_summary（表無 role 欄，pointer role 恆 ''）改比對 pointer role=''。
    供 API 讀路徑內嵌（無參數）。
    """
    role_pred = "s.role = ''" if dataset == "league_summary" else f"s.role = {alias}.role"
    return (
        f"((NOT EXISTS (SELECT 1 FROM cpbl.advanced_snapshot_state s "
        f"  WHERE s.year = {alias}.year AND s.kind_code = {alias}.kind_code "
        f"    AND s.dataset = '{dataset}' AND {role_pred}) "
        f"  AND {alias}.source_run_id IS NULL) "
        f" OR EXISTS (SELECT 1 FROM cpbl.advanced_snapshot_state s "
        f"  WHERE s.year = {alias}.year AND s.kind_code = {alias}.kind_code "
        f"    AND s.dataset = '{dataset}' AND {role_pred} "
        f"    AND s.current_run_id = {alias}.source_run_id))"
    )


@dataclass(frozen=True)
class RunSpec:
    year: int
    kind_code: str
    dataset: str
    role: str = ""

    def __post_init__(self) -> None:
        if self.dataset not in DATASETS:
            raise ValueError(f"未知 dataset：{self.dataset}")


@dataclass
class ValidationReport:
    observed_rows: int = 0
    accepted_rows: int = 0
    empty_id_rows: int = 0
    duplicate_key_rows: int = 0
    errors: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_json(self) -> str:
        return json.dumps(self.errors, ensure_ascii=False)


def open_run(spec: RunSpec, scope: str, source_endpoint: str, source_fetched_at: datetime,
             observed_rows: int = 0, source_version: str | None = None,
             provenance: dict | None = None) -> int:
    """建立 run 列（status='running'），回 run_id。獨立 commit，確保失敗仍留審計。"""
    if scope not in ("full", "partial"):
        raise ValueError(f"未知 snapshot_scope：{scope}")
    with conn() as c:
        row = c.execute(
            """
            INSERT INTO cpbl.advanced_ingest_runs
                (year, kind_code, dataset, role, snapshot_scope, status,
                 source_endpoint, source_version, source_fetched_at, observed_rows, provenance)
            VALUES (%s,%s,%s,%s,%s,'running',%s,%s,%s,%s,%s::jsonb)
            RETURNING id
            """,
            (spec.year, spec.kind_code, spec.dataset, spec.role, scope,
             source_endpoint, source_version, source_fetched_at, observed_rows,
             json.dumps(provenance or {}, ensure_ascii=False)),
        ).fetchone()
    return int(row[0])


def reject_run(run_id: int, report: ValidationReport, status: str = "rejected") -> None:
    """標記 run 為 rejected/failed 並寫入計數與 error_report（不動任何資料列）。"""
    with conn() as c:
        c.execute(
            """
            UPDATE cpbl.advanced_ingest_runs
               SET status=%s, observed_rows=%s, accepted_rows=%s, empty_id_rows=%s,
                   duplicate_key_rows=%s, error_report=%s::jsonb, completed_at=now()
             WHERE id=%s
            """,
            (status, report.observed_rows, report.accepted_rows, report.empty_id_rows,
             report.duplicate_key_rows, report.as_json(), run_id),
        )


def _prior_row_count(cur, spec: RunSpec) -> int | None:
    row = cur.execute(
        """SELECT row_count FROM cpbl.advanced_snapshot_state
            WHERE year=%s AND kind_code=%s AND dataset=%s AND role=%s""",
        (spec.year, spec.kind_code, spec.dataset, spec.role),
    ).fetchone()
    return int(row[0]) if row else None


def validate(spec: RunSpec, report: ValidationReport, prior: int | None = -1) -> ValidationReport:
    """晉升前驗證：筆數下限 + 相對前快照保留比例 + 重複 key。附加錯誤寫入 report.errors。

    prior=-1（預設）時自 DB 讀前一 promoted 快照列數；單元測試可直接注入 prior（含 None）。
    """
    floor = MIN_ACCEPTED.get(spec.dataset, 1)
    if report.accepted_rows < floor:
        report.errors["row_count_below_floor"] = {"accepted": report.accepted_rows, "floor": floor}
    if report.duplicate_key_rows > 0:
        report.errors["duplicate_natural_key"] = report.duplicate_key_rows
    if prior == -1:
        with conn() as c:
            prior = _prior_row_count(c.cursor(), spec)
    if prior and report.accepted_rows < prior * MIN_RETAIN_RATIO:
        report.errors["retain_ratio_regression"] = {"accepted": report.accepted_rows, "prior": prior}
    return report


def promote_full(spec: RunSpec, run_id: int, stage_fn, report: ValidationReport) -> None:
    """單一 transaction 原子晉升：stage → 鎖 run 驗 scope/identity → promoted → pointer → 刪殘列。

    `stage_fn(cur, run_id)` 負責把已 fetch 的列以 source_run_id=run_id UPSERT 進目標表。
    任一步 raise 即整筆 rollback（含 stage 寫入的列）。
    """
    table = DATASET_TABLE[spec.dataset]
    role_clause = "" if spec.dataset == "league_summary" else "AND role = %(role)s "
    with conn() as c:
        cur = c.cursor()
        stage_fn(cur, run_id)
        locked = cur.execute(
            """SELECT snapshot_scope, year, kind_code, dataset, role, status
                 FROM cpbl.advanced_ingest_runs WHERE id=%s FOR UPDATE""",
            (run_id,),
        ).fetchone()
        if locked is None:
            raise RuntimeError(f"run {run_id} 不存在")
        scope, y, k, d, r, status = locked
        if scope != "full":
            raise RuntimeError(f"run {run_id} snapshot_scope={scope}，非 full 不可晉升")
        if (y, k, d, r) != (spec.year, spec.kind_code, spec.dataset, spec.role):
            raise RuntimeError(f"run {run_id} identity {(y, k, d, r)} 與 spec {spec} 不符")
        if status == "promoted":
            raise RuntimeError(f"run {run_id} 已 promoted，不可重複晉升")
        cur.execute(
            """
            UPDATE cpbl.advanced_ingest_runs
               SET status='promoted', observed_rows=%s, accepted_rows=%s, empty_id_rows=%s,
                   duplicate_key_rows=%s, error_report=%s::jsonb, completed_at=now()
             WHERE id=%s
            """,
            (report.observed_rows, report.accepted_rows, report.empty_id_rows,
             report.duplicate_key_rows, report.as_json(), run_id),
        )
        cur.execute(
            """
            INSERT INTO cpbl.advanced_snapshot_state
                (year, kind_code, dataset, role, current_run_id, row_count, source_fetched_at)
            SELECT year, kind_code, dataset, role, id, %s, source_fetched_at
              FROM cpbl.advanced_ingest_runs WHERE id=%s
            ON CONFLICT (year, kind_code, dataset, role) DO UPDATE
               SET current_run_id=EXCLUDED.current_run_id, row_count=EXCLUDED.row_count,
                   source_fetched_at=EXCLUDED.source_fetched_at, promoted_at=now()
            """,
            (report.accepted_rows, run_id),
        )
        deleted = cur.execute(
            f"""DELETE FROM {table}
                 WHERE year=%(year)s AND kind_code=%(kind)s {role_clause}
                   AND source_run_id IS DISTINCT FROM %(run)s""",
            {"year": spec.year, "kind": spec.kind_code, "role": spec.role, "run": run_id},
        ).rowcount
    log.info("promote %s：run=%d accepted=%d 刪殘列=%d", spec, run_id, report.accepted_rows, deleted)


def rollback_to(spec: RunSpec, run_id: int) -> int:
    """把某 scope 的現行快照回捲到指定（早前 promoted）run。刪除非該 run 的列並改回 pointer。

    只用於本機修復演練；run 必須是該 scope 曾 promoted 的 full run。回傳刪除列數。
    """
    table = DATASET_TABLE[spec.dataset]
    role_clause = "" if spec.dataset == "league_summary" else "AND role = %(role)s "
    with conn() as c:
        cur = c.cursor()
        run = cur.execute(
            """SELECT snapshot_scope, year, kind_code, dataset, role, status
                 FROM cpbl.advanced_ingest_runs WHERE id=%s FOR UPDATE""",
            (run_id,),
        ).fetchone()
        if run is None:
            raise RuntimeError(f"run {run_id} 不存在")
        if run[0] != "full" or (run[1], run[2], run[3], run[4]) != (
                spec.year, spec.kind_code, spec.dataset, spec.role):
            raise RuntimeError(f"run {run_id} 非本 scope 的 full run，不可回捲")
        n = cur.execute(
            f"""DELETE FROM {table}
                 WHERE year=%(year)s AND kind_code=%(kind)s {role_clause}
                   AND source_run_id IS DISTINCT FROM %(run)s""",
            {"year": spec.year, "kind": spec.kind_code, "role": spec.role, "run": run_id},
        ).rowcount
        cur.execute(
            """UPDATE cpbl.advanced_snapshot_state
                  SET current_run_id=%s, promoted_at=now(),
                      row_count=(SELECT accepted_rows FROM cpbl.advanced_ingest_runs WHERE id=%s)
                WHERE year=%s AND kind_code=%s AND dataset=%s AND role=%s""",
            (run_id, run_id, spec.year, spec.kind_code, spec.dataset, spec.role),
        )
    return n


def current_run_id(spec: RunSpec) -> int | None:
    with conn() as c:
        row = c.execute(
            """SELECT current_run_id FROM cpbl.advanced_snapshot_state
                WHERE year=%s AND kind_code=%s AND dataset=%s AND role=%s""",
            (spec.year, spec.kind_code, spec.dataset, spec.role),
        ).fetchone()
    return int(row[0]) if row else None


def pointer_audit() -> list[tuple]:
    """回傳所有違反 pointer 不變量的列（應為空）：pointer 對應的 run 非 promoted、
    非 full，或 scope identity 不一致。供晉升後留證。"""
    with conn() as c:
        return c.execute(
            """
            SELECT s.year, s.kind_code, s.dataset, s.role, s.current_run_id,
                   r.status, r.snapshot_scope
              FROM cpbl.advanced_snapshot_state s
              JOIN cpbl.advanced_ingest_runs r ON r.id = s.current_run_id
             WHERE r.status <> 'promoted'
                OR r.snapshot_scope <> 'full'
                OR (r.year, r.kind_code, r.dataset, r.role)
                   <> (s.year, s.kind_code, s.dataset, s.role)
            """
        ).fetchall()
