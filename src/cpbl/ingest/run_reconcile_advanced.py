"""CLI：一次性修復污染的 advanced_stats + 建立完整快照（INGEST-ADV-RECONCILE1）。

    uv run cpbl-reconcile-advanced --dry-run            # 只 fetch+驗證+印差異，不寫
    uv run cpbl-reconcile-advanced                      # 備份 → 全量晉升 → 印 before/after 差異
    uv run cpbl-reconcile-advanced --years 2026 --kinds A,D
    uv run cpbl-reconcile-advanced --resume             # 跳過今天已 promoted 的 scope
    uv run cpbl-reconcile-advanced --rollback 42        # 把 run 42 的 scope 回捲到 run 42

replay-safe：正式模式可重跑（每次建新 run、原子晉升、刪殘列，冪等收斂到官方當刻集合）。
本 CLI 只動本機 DB；production 修復為 review 通過 + 需求方 sign-off 後的獨立 rollout。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path

from cpbl.db import conn, migrate
from cpbl.ingest import advanced_snapshot as snap
from cpbl.ingest.advanced_snapshot import RunSpec
from cpbl.ingest.cpbl_advanced import run_full_snapshot

log = logging.getLogger("cpbl.reconcile")

ROLES = ("batting", "pitching")
MOIERMAN = "0000007790"  # 抽樣對帳：2026 A pitching 應同時有 fastball / breakingball 兩列


def _visible_acnts(cur, year: int, kind: str, role: str) -> set[str]:
    gate = snap.gating_predicate("a", "player_stats")
    rows = cur.execute(
        f"SELECT acnt FROM cpbl.advanced_stats a "
        f"WHERE year=%s AND kind_code=%s AND role=%s AND {gate}",
        (year, kind, role),
    ).fetchall()
    return {r[0] for r in rows}


def _counts(cur, year: int, kind: str) -> dict:
    def one(sql: str, *p) -> int:
        return int(cur.execute(sql, p).fetchone()[0])

    out: dict = {"advanced_stats": {}, "pitch_type": {}, "league_summary": 0}
    for role in ROLES:
        out["advanced_stats"][role] = {
            "raw": one("SELECT count(*) FROM cpbl.advanced_stats WHERE year=%s AND kind_code=%s AND role=%s",
                       year, kind, role),
            "visible": len(_visible_acnts(cur, year, kind, role)),
        }
        out["pitch_type"][role] = one(
            "SELECT count(*) FROM cpbl.advanced_pitch_type_stats WHERE year=%s AND kind_code=%s AND role=%s",
            year, kind, role)
    out["league_summary"] = one(
        "SELECT count(*) FROM cpbl.advanced_league_summary WHERE year=%s AND kind_code=%s", year, kind)
    return out


def backup(year: int, out_dir: Path) -> tuple[Path, str]:
    """把該年 advanced_stats 全列（含 provenance）落 JSON 檔並回 (path, sha256)。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"advanced_stats-{year}-{ts}.json"
    with conn() as c:
        cur = c.cursor()
        cols = [d.name for d in cur.execute(
            "SELECT * FROM cpbl.advanced_stats WHERE false").description]
        rows = cur.execute(
            "SELECT * FROM cpbl.advanced_stats WHERE year=%s ORDER BY kind_code, role, acnt",
            (year,)).fetchall()
    payload = [dict(zip(cols, r, strict=True)) for r in rows]
    text = json.dumps(payload, ensure_ascii=False, default=str, indent=0)
    path.write_text(text, encoding="utf-8")
    sha = hashlib.sha256(text.encode()).hexdigest()
    log.info("備份 %d 列 → %s（sha256=%s）", len(rows), path, sha)
    return path, sha


def _promoted_today(spec: RunSpec) -> bool:
    with conn() as c:
        row = c.execute(
            """SELECT source_fetched_at::date FROM cpbl.advanced_snapshot_state
                WHERE year=%s AND kind_code=%s AND dataset=%s AND role=%s""",
            (spec.year, spec.kind_code, spec.dataset, spec.role)).fetchone()
    return bool(row and row[0] == date.today())


def _sample_reconcile(cur, year: int) -> None:
    rows = cur.execute(
        """SELECT pitch_type, pitches, round(kph::numeric,2), round(spin_rate::numeric,1)
             FROM cpbl.advanced_pitch_type_stats
            WHERE year=%s AND kind_code='A' AND role='pitching' AND acnt=%s
            ORDER BY pitch_type""",
        (year, MOIERMAN)).fetchall()
    log.info("抽樣對帳 魔爾曼(%s) 2026 A pitching：%d 列", MOIERMAN, len(rows))
    for pt, pit, kph, spin in rows:
        log.info("  %-12s pitches=%s kph=%s spin=%s", pt, pit, kph, spin)


def _rollback(run_id: int) -> None:
    with conn() as c:
        row = c.execute(
            "SELECT year, kind_code, dataset, role FROM cpbl.advanced_ingest_runs WHERE id=%s",
            (run_id,)).fetchone()
    if not row:
        raise SystemExit(f"run {run_id} 不存在")
    spec = RunSpec(int(row[0]), row[1], row[2], row[3])
    n = snap.rollback_to(spec, run_id)
    log.info("rollback %s → run %d：刪 %d 列", spec, run_id, n)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default=str(date.today().year), help="逗號分隔，如 2026")
    ap.add_argument("--kinds", default="A,D", help="逗號分隔，如 A,D")
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resume", action="store_true", help="跳過今天已 promoted 的 scope")
    ap.add_argument("--rollback", type=int, metavar="RUN_ID")
    ap.add_argument("--backup-dir", default="artifacts/reconcile")
    args = ap.parse_args()

    migrate()
    if args.rollback is not None:
        _rollback(args.rollback)
        return

    years = [int(y) for y in args.years.split(",")]
    kinds = args.kinds.split(",")

    for year in years:
        if not args.dry_run:
            backup(year, Path(args.backup_dir))
        for kind in kinds:
            with conn() as c:
                before = _counts(c.cursor(), year, kind)
                before_vis = {r: _visible_acnts(c.cursor(), year, kind, r) for r in ROLES}
            roles = tuple(
                r for r in ROLES
                if not (args.resume and _promoted_today(RunSpec(year, kind, "player_stats", r)))
            )
            if not roles and args.resume:
                log.info("resume：%d kind=%s 全 role 今日已 promoted，跳過", year, kind)
                continue
            outcomes = run_full_snapshot(year, kind_code=kind, roles=roles or ROLES,
                                         delay=args.delay, dry_run=args.dry_run)
            for o in outcomes:
                log.info("%d kind=%s %s/%s run=%s promoted=%s observed=%d accepted=%d empty=%d dup=%d%s",
                         year, kind, o.spec.dataset, o.spec.role or "-", o.run_id, o.promoted,
                         o.report.observed_rows, o.report.accepted_rows, o.report.empty_id_rows,
                         o.report.duplicate_key_rows, f" ERROR={o.error}" if o.error else "")
            if args.dry_run:
                continue
            with conn() as c:
                cur = c.cursor()
                after = _counts(cur, year, kind)
                for role in ROLES:
                    now_vis = _visible_acnts(cur, year, kind, role)
                    removed = sorted(before_vis[role] - now_vis)
                    added = sorted(now_vis - before_vis[role])
                    log.info("%d kind=%s role=%s advanced_stats raw %d→%d visible %d→%d 移除污染 acnt=%d 新增=%d",
                             year, kind, role, before["advanced_stats"][role]["raw"],
                             after["advanced_stats"][role]["raw"],
                             before["advanced_stats"][role]["visible"],
                             after["advanced_stats"][role]["visible"], len(removed), len(added))
                    if removed:
                        log.info("  移除 acnt 樣本：%s%s", removed[:10],
                                 " …" if len(removed) > 10 else "")
                    log.info("%d kind=%s role=%s pitch_type %d→%d",
                             year, kind, role, before["pitch_type"][role], after["pitch_type"][role])
                log.info("%d kind=%s league_summary %d→%d",
                         year, kind, before["league_summary"], after["league_summary"])
                _sample_reconcile(cur, year)

    audit = snap.pointer_audit()
    if audit:
        log.error("pointer audit 違規 %d 列：%s", len(audit), audit)
        raise SystemExit(1)
    log.info("pointer audit=0（所有 pointer 皆 promoted/full/scope 一致）")


if __name__ == "__main__":
    main()
