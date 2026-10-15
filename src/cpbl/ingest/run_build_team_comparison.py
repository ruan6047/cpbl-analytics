"""cpbl-build-team-comparison：全年 A／兩隊 A 對戰背景摘要的本機離線 builder（#287 S06 WP2）。

建置邏輯住 :mod:`cpbl.playoffs.team_comparison.builder`；CLI 放在 ``cpbl.ingest`` 底下，讓
``tests/test_cli_help_guard.py`` 的 ``--help`` 零副作用密封探針自動涵蓋（比照 #284 ``cpbl-roster``）。

用法：
  cpbl-build-team-comparison --year 2026                     # 來源未變＝no-op；更正⇒新 build 並切 current
  cpbl-build-team-comparison --year 2026 --dry-run           # 只讀來源、算雜湊與覆蓋，不寫
  cpbl-build-team-comparison --year 2026 --promote-existing <build_id>   # 回指既有 build（回復用）
  cpbl-build-team-comparison --year 2026 --record-failure    # 每日鏈用：失敗時在本機 refresh_log 記一列

DB：寫入 DATABASE_URL 指向的庫（預設本機共享 cpbl；寫共享庫前須取得資源租用）。只寫
    ``team_comparison_*`` 三表（與 --record-failure 的本機 refresh_log 一列）；⛔ 不 migrate；
    ⛔ 生產只經 ``refresh-cpbl-prod.sh`` 的 TEAM_COMPARISON_ONLY／完整鏈 insert-only 同步。

退出碼：0 成功／無變更 · 2 參數錯 · 3 A 母體覆蓋不全（未切換，舊版標待更新）
        4 指標在建置期間被他人切到別版 · 5 建置失敗（已回滾，舊版標待更新）
        6 摘要表不存在（尚未套 migration 077）
"""

from __future__ import annotations

import argparse
import sys
import uuid

from cpbl.playoffs.team_comparison.builder import (
    BUILDER_VERSION,
    EXIT_NO_TABLES,
    EXIT_OK,
    record_failure,
    run_build,
    run_promote_existing,
)


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="cpbl-build-team-comparison", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 allow_abbrev=False)
    ap.add_argument("--year", type=int, required=True, help="建置年份（該年全年 A 與兩隊 A 對戰）")
    ap.add_argument("--promote-existing", type=uuid.UUID, metavar="BUILD_ID",
                    help="不重建，把 current 回指到該年既有 build（回復用）")
    ap.add_argument("--dry-run", action="store_true", help="只讀來源、算雜湊與覆蓋，不寫任何表")
    ap.add_argument("--record-failure", action="store_true",
                    help="非零退出時在本機 refresh_log 記一列（每日鏈用）")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    from cpbl.db import conn

    if args.promote_existing:
        out = run_promote_existing(conn, args.year, args.promote_existing)
    else:
        out = run_build(conn, args.year, dry_run=args.dry_run)
    stream = sys.stdout if out.code == EXIT_OK else sys.stderr
    print(f"TEAM_COMPARISON_BUILD={out.status} {out.message}", file=stream)
    if out.plan:
        print(f"  source_hash={out.plan.source_hash} builder_version={BUILDER_VERSION} "
              f"build_id={out.plan.build_id} rows_digest={out.plan.rows_digest} "
              f"games={out.plan.coverage['expected_games']}", file=stream)
    if out.code != EXIT_OK and args.record_failure and out.code != EXIT_NO_TABLES:
        try:
            record_failure(conn, args.year, out)
        except Exception as exc:  # noqa: BLE001 — 記錄失敗不改變原退出碼
            print(f"  ⚠ refresh_log 記錄失敗：{type(exc).__name__}: {exc}", file=sys.stderr)
    return out.code


if __name__ == "__main__":
    sys.exit(main())
