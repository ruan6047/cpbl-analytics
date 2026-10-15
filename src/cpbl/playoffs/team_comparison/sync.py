"""隊伍比較摘要三表本機 → 目標庫（生產）的 insert-only 同步（#287 WP4a；比照 #284 名單同步）。

⛔ 不進 refresh-cpbl-prod.sh 的 sync_table UPSERT 清單（三表有不可變觸發器，UPSERT 會直接失敗）。
shell（``TEAM_COMPARISON_ONLY=1`` 早退模式，或完整鏈 gamelog 同步之後）只負責備份與 psql 管道；
比對、payload、對帳都在本模組：

1. **欄位漂移守衛**：本機三表的欄位清單必須逐欄等於本模組常數（本機多／少任何欄 ⇒ exit 67、不寫）。
2. **本機自檢**：build_id 必須等於 uuid5(year|builder_version|source_hash)；``rows_digest`` 必須等於
   以列重算的值；current 必須指向同年既有 build（exit 67）。
3. **目標唯讀比對**：目標沒有三表＝exit 69（schema 只隨部署窗口套用，本模組不 migrate）。
   目標無此 build＝待插入；同 build_id 但 build 欄或列雜湊不同＝拒絕（exit 70，整批不寫、不重試）；
   目標有本機沒有的 build 或指標年份＝拒絕（生產不應有獨立 writer）。指標不同＝待更新。
4. 無待寫＝``TEAM_COMPARISON_SYNC_PLAN=no-change``（shell 不備份、不寫）。
5. 有待寫＝``insert-pending``；``apply`` 以單一 psql 交易：payload 以 COPY 進 temp 表 → 交易內再查一次
   衝突 → ``INSERT … WHERE NOT EXISTS``（build、列）→ 指標明確欄位 ``ON CONFLICT DO UPDATE``（列先、指標後）。
6. **事後對帳**：重讀目標，逐 build 以列重算 ``rows_digest`` 與本機比對、逐年比對指標（exit 71；已寫列保留）。

用法（兩端都是「讀 stdin 腳本的 psql 指令」，shlex 切分、不經 shell；本機端只做唯讀查詢）：
  python -m cpbl.playoffs.team_comparison.sync plan \\
      --local-psql  "docker exec -i cpbl287-pg psql -U cpbl287 -d cpbl_test_287" \\
      --target-psql "docker exec -i cpbl287-pg psql -U cpbl287 -d cpbl_test_287_prod"
  python -m cpbl.playoffs.team_comparison.sync apply     --local-psql "…" --target-psql "…"
  python -m cpbl.playoffs.team_comparison.sync reconcile --local-psql "…" --target-psql "…"

退出碼：0 成功 · 2 參數錯 · 67 本機自檢／欄位漂移 · 69 目標尚無三表（待部署窗口）
        70 內容衝突拒絕（不寫） · 71 事後對帳不等 · 72 目標指令失敗（psql／ssh）
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime

from cpbl.playoffs.team_comparison import core
from cpbl.playoffs.team_comparison.builder import build_id_for
from cpbl.rosters.sync import PsqlTarget, SyncError, _copy_escape

EXIT_SELF_CHECK = 67
EXIT_NO_TABLE = 69
EXIT_REJECT = 70
EXIT_RECONCILE = 71
EXIT_TARGET = 72

BUILD_COLUMNS = ("build_id", "year", "kind_code", "builder_version", "source_hash", "games_fingerprint",
                 "completed_games", "rows_digest", "coverage", "built_at")
ROW_COLUMNS = ("build_id", *core.ROW_COLUMNS)
CURRENT_COLUMNS = ("year", "kind_code", "build_id", "promoted_at", "pending_source_hash", "pending_since")
TABLE_COLUMNS = {
    "team_comparison_build": BUILD_COLUMNS,
    "team_comparison_row": ROW_COLUMNS,
    "team_comparison_current": CURRENT_COLUMNS,
}
_TS = ("built_at", "promoted_at", "pending_since")

TABLES_EXIST_SQL = (
    "SELECT (to_regclass('cpbl.team_comparison_build') IS NOT NULL"
    " AND to_regclass('cpbl.team_comparison_row') IS NOT NULL"
    " AND to_regclass('cpbl.team_comparison_current') IS NOT NULL)::text;"
)
COLUMNS_SQL = (
    "SELECT COALESCE(json_object_agg(table_name, cols), '{}'::json)::text FROM ("
    " SELECT table_name, json_agg(column_name::text ORDER BY ordinal_position) AS cols"
    " FROM information_schema.columns WHERE table_schema = 'cpbl' AND table_name IN ("
    + ", ".join(f"'{t}'" for t in TABLE_COLUMNS) + ") GROUP BY table_name) x;"
)


def _agg(table: str, cols: tuple[str, ...], order: str) -> str:
    return (f"COALESCE((SELECT json_agg(json_build_object({', '.join(f'{c!r}, {c}' for c in cols)})"
            f" ORDER BY {order}) FROM cpbl.{table}), '[]'::json)")


# 三表全量唯讀傾印（單行 JSON）。欄名為本模組常數，無外部輸入。
DUMP_SQL = (
    "SELECT json_build_object("
    f"'builds', {_agg('team_comparison_build', BUILD_COLUMNS, 'build_id')}, "
    f"'rows', {_agg('team_comparison_row', ROW_COLUMNS, 'build_id, scope, team_code, opponent_code')}, "
    f"'current', {_agg('team_comparison_current', CURRENT_COLUMNS, 'year, kind_code')}"
    ")::text;"
)


# ---------------------------------------------------------------- 正規化與自檢


def _ts(v: str | None) -> str | None:
    return None if v is None else datetime.fromisoformat(v).astimezone(UTC).isoformat()


@dataclass
class Bundle:
    builds: dict[str, dict]                 # build_id → build 列
    rows: dict[str, list[dict]]             # build_id → 列
    current: dict[tuple[int, str], dict]    # (year, kind) → 指標列


def normalize(dump: dict) -> Bundle:
    builds = {}
    for b in dump["builds"]:
        rec = {k: b[k] for k in BUILD_COLUMNS}
        rec["build_id"] = str(rec["build_id"])
        rec["built_at"] = _ts(rec["built_at"])
        builds[rec["build_id"]] = rec
    rows: dict[str, list[dict]] = {}
    for r in dump["rows"]:
        rec = {k: r[k] for k in ROW_COLUMNS}
        rec["build_id"] = str(rec["build_id"])
        rows.setdefault(rec["build_id"], []).append(rec)
    current = {}
    for c in dump["current"]:
        rec = {k: c[k] for k in CURRENT_COLUMNS}
        rec["build_id"] = str(rec["build_id"])
        for k in ("promoted_at", "pending_since"):
            rec[k] = _ts(rec[k])
        current[(int(rec["year"]), rec["kind_code"])] = rec
    return Bundle(builds, rows, current)


def column_drift(columns: dict[str, list[str]]) -> list[str]:
    problems = []
    for table, expected in TABLE_COLUMNS.items():
        got = tuple(columns.get(table) or ())
        if got != expected:
            extra = [c for c in got if c not in expected]
            missing = [c for c in expected if c not in got]
            problems.append(f"{table} 欄位與同步清單不符（本機多：{extra}；本機少：{missing}；"
                            "漏列欄會在生產只插不更，補清單後再跑）")
    return problems


def self_check(b: Bundle) -> list[str]:
    problems = []
    for bid, build in sorted(b.builds.items()):
        expect = str(build_id_for(int(build["year"]), build["builder_version"], build["source_hash"]))
        if expect != bid:
            problems.append(f"build {bid} 身分 ≠ uuid5(year|version|source_hash)={expect}")
        rows = b.rows.get(bid, [])
        if not rows:
            problems.append(f"build {bid} 沒有列")
        elif core.rows_digest(rows) != build["rows_digest"]:
            problems.append(f"build {bid} rows_digest 存值 {build['rows_digest']} ≠ 重算 {core.rows_digest(rows)}")
    for bid in sorted(set(b.rows) - set(b.builds)):
        problems.append(f"列指向不存在的 build {bid}")
    for (year, kind), cur in sorted(b.current.items()):
        build = b.builds.get(cur["build_id"])
        if not build or int(build["year"]) != year:
            problems.append(f"current {year}/{kind} 指向不存在或他年的 build {cur['build_id']}")
    return problems


# ---------------------------------------------------------------- 比對計畫


@dataclass
class Plan:
    insert_builds: list[str] = field(default_factory=list)
    update_current: list[tuple[int, str]] = field(default_factory=list)
    skipped_builds: list[str] = field(default_factory=list)
    rejects: list[dict] = field(default_factory=list)

    @property
    def state(self) -> str:
        if self.rejects:
            return "reject"
        return "insert-pending" if (self.insert_builds or self.update_current) else "no-change"


def plan(local: Bundle, target: Bundle) -> Plan:
    p = Plan()
    for bid in sorted(set(local.builds) | set(target.builds)):
        if bid not in local.builds:
            p.rejects.append({"build_id": bid, "reason": "目標有本機沒有的 build（生產不應有獨立 writer，拒絕）"})
            continue
        if bid not in target.builds:
            p.insert_builds.append(bid)
            continue
        lb, tb = local.builds[bid], target.builds[bid]
        diff = {k: {"local": lb[k], "target": tb[k]} for k in BUILD_COLUMNS if lb[k] != tb[k]}
        t_digest = core.rows_digest(target.rows.get(bid, []))
        if t_digest != lb["rows_digest"]:
            diff["rows_digest_recomputed"] = {"local": lb["rows_digest"], "target": t_digest}
        if diff:
            p.rejects.append({"build_id": bid, "reason": "同 build_id 內容不同（拒絕，不覆寫）", "diff": diff})
        else:
            p.skipped_builds.append(bid)
    for key in sorted(set(local.current) | set(target.current)):
        if key not in local.current:
            p.rejects.append({"current": f"{key[0]}/{key[1]}", "reason": "目標有本機沒有的指標年份（拒絕）"})
        elif local.current[key] != target.current.get(key):
            p.update_current.append(key)
    return p


# ---------------------------------------------------------------- payload


def payload(local: Bundle, p: Plan) -> dict:
    builds = [local.builds[b] for b in p.insert_builds]
    rows = [r for b in p.insert_builds for r in local.rows[b]]
    current = [local.current[k] for k in p.update_current]
    return {"builds": builds, "rows": rows, "current": current}


def apply_script(doc: dict) -> str:
    """單一交易的 psql 腳本：build／列 insert-only，指標明確欄位 UPSERT（列先、指標後）。"""
    line = _copy_escape(json.dumps(doc, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    bcols = ", ".join(BUILD_COLUMNS)
    rcols = ", ".join(ROW_COLUMNS)
    ccols = ", ".join(CURRENT_COLUMNS)
    return f"""\\set QUIET on
\\set ON_ERROR_STOP on
\\pset tuples_only on
\\pset format unaligned
BEGIN;
CREATE TEMP TABLE _tc_sync_payload (doc jsonb NOT NULL) ON COMMIT DROP;
COPY _tc_sync_payload (doc) FROM STDIN;
{line}
\\.
CREATE TEMP TABLE _tc_build ON COMMIT DROP AS
  SELECT * FROM jsonb_populate_recordset(NULL::cpbl.team_comparison_build,
                                         (SELECT doc->'builds' FROM _tc_sync_payload));
CREATE TEMP TABLE _tc_row ON COMMIT DROP AS
  SELECT * FROM jsonb_populate_recordset(NULL::cpbl.team_comparison_row,
                                         (SELECT doc->'rows' FROM _tc_sync_payload));
CREATE TEMP TABLE _tc_current ON COMMIT DROP AS
  SELECT * FROM jsonb_populate_recordset(NULL::cpbl.team_comparison_current,
                                         (SELECT doc->'current' FROM _tc_sync_payload));
DO $tc_sync$
DECLARE bad text;
BEGIN
  SELECT string_agg(t.build_id::text, ', ') INTO bad
    FROM _tc_build s JOIN cpbl.team_comparison_build t USING (build_id)
   WHERE ROW(t.year, t.builder_version, t.source_hash, t.games_fingerprint, t.rows_digest)
         IS DISTINCT FROM ROW(s.year, s.builder_version, s.source_hash, s.games_fingerprint, s.rows_digest);
  IF bad IS NOT NULL THEN
    RAISE EXCEPTION 'TEAM_COMPARISON_SYNC_CONFLICT 比對後目標出現同 build_id 不同內容：%', bad;
  END IF;
END
$tc_sync$;
INSERT INTO cpbl.team_comparison_build ({bcols})
  SELECT {bcols} FROM _tc_build s
   WHERE NOT EXISTS (SELECT 1 FROM cpbl.team_comparison_build t WHERE t.build_id = s.build_id);
INSERT INTO cpbl.team_comparison_row ({rcols})
  SELECT {rcols} FROM _tc_row s
   WHERE NOT EXISTS (SELECT 1 FROM cpbl.team_comparison_row t
                      WHERE t.build_id = s.build_id AND t.scope = s.scope
                        AND t.team_code = s.team_code AND t.opponent_code = s.opponent_code);
INSERT INTO cpbl.team_comparison_current ({ccols})
  SELECT {ccols} FROM _tc_current
  ON CONFLICT (year, kind_code) DO UPDATE SET build_id = EXCLUDED.build_id,
    promoted_at = EXCLUDED.promoted_at, pending_source_hash = EXCLUDED.pending_source_hash,
    pending_since = EXCLUDED.pending_since;
SELECT 'TEAM_COMPARISON_SYNC_STAGED ' || (SELECT count(*) FROM _tc_build) || ' '
       || (SELECT count(*) FROM _tc_row) || ' ' || (SELECT count(*) FROM _tc_current);
COMMIT;
"""


# ---------------------------------------------------------------- 讀取


def read_target(target) -> Bundle:
    if target.read(TABLES_EXIST_SQL).strip() != "true":
        raise SyncError(EXIT_NO_TABLE, "目標尚無隊伍比較摘要表（待部署窗口套用 migration；本同步不 migrate）")
    return normalize(json.loads(target.read(DUMP_SQL)))


def read_local(source) -> Bundle:
    if source.read(TABLES_EXIST_SQL).strip() != "true":
        raise SyncError(EXIT_SELF_CHECK, "本機尚無隊伍比較摘要表")
    drift = column_drift(json.loads(source.read(COLUMNS_SQL)))
    if drift:
        raise SyncError(EXIT_SELF_CHECK, "欄位漂移：" + "；".join(drift))
    local = normalize(json.loads(source.read(DUMP_SQL)))
    problems = self_check(local)
    if problems:
        raise SyncError(EXIT_SELF_CHECK, "本機自檢失敗：" + "；".join(problems))
    return local


# ---------------------------------------------------------------- 對帳


def reconcile(local: Bundle, target: Bundle) -> tuple[bool, list[dict]]:
    ok = True
    out = []
    for bid in sorted(set(local.builds) | set(target.builds)):
        lb, tb = local.builds.get(bid), target.builds.get(bid)
        t_digest = core.rows_digest(target.rows.get(bid, [])) if tb else None
        row = {"build_id": bid, "year": (lb or tb)["year"],
               "source_hash": (lb or tb)["source_hash"], "builder_version": (lb or tb)["builder_version"],
               "digest_local": lb and lb["rows_digest"], "digest_target": tb and tb["rows_digest"],
               "digest_target_recomputed": t_digest,
               "rows_local": len(local.rows.get(bid, [])), "rows_target": len(target.rows.get(bid, []))}
        row["equal"] = bool(lb and tb and lb == tb and t_digest == lb["rows_digest"])
        ok &= row["equal"]
        out.append(row)
    for key in sorted(set(local.current) | set(target.current)):
        lc, tc = local.current.get(key), target.current.get(key)
        row = {"current": f"{key[0]}/{key[1]}", "build_local": lc and lc["build_id"],
               "build_target": tc and tc["build_id"], "pending_local": lc and lc["pending_since"],
               "pending_target": tc and tc["pending_since"], "equal": lc == tc}
        ok &= row["equal"]
        out.append(row)
    return ok, out


def _print_table(rows: list[dict]) -> None:
    print("build／指標｜年｜source_hash｜rows_digest 本機/目標(重算)｜列數 本機/目標｜一致")
    for r in rows:
        if "build_id" in r:
            def s(v):
                return (v or "—")[:12]
            print(f"{r['build_id']}｜{r['year']}｜{s(r['source_hash'])}｜{s(r['digest_local'])}/"
                  f"{s(r['digest_target'])}({s(r['digest_target_recomputed'])})｜"
                  f"{r['rows_local']}/{r['rows_target']}｜{'✓' if r['equal'] else '✗'}")
        else:
            print(f"current {r['current']}｜{r['build_local'] or '—'} → {r['build_target'] or '—'}｜"
                  f"pending {r['pending_local'] or '—'}/{r['pending_target'] or '—'}｜{'✓' if r['equal'] else '✗'}")


# ---------------------------------------------------------------- 入口


def run_plan(source, target) -> tuple[Bundle, Bundle, Plan]:
    local = read_local(source)
    remote = read_target(target)
    return local, remote, plan(local, remote)


def run_apply(source, target) -> tuple[Plan, bool, list[dict]]:
    local, _, p = run_plan(source, target)
    if p.state == "reject":
        raise SyncError(EXIT_REJECT, "內容衝突，拒絕同步（不寫入、不重試）", p.rejects)
    if p.state == "insert-pending":
        out = target.run(apply_script(payload(local, p)))
        if "TEAM_COMPARISON_SYNC_STAGED" not in out:
            raise SyncError(EXIT_TARGET, f"目標未回報寫入結果：{out!r}")
    ok, rows = reconcile(local, read_target(target))
    return p, ok, rows


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m cpbl.playoffs.team_comparison.sync", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    ap.add_argument("action", choices=("plan", "apply", "reconcile"))
    ap.add_argument("--local-psql", required=True, help="本機來源庫的 psql 指令（唯讀；shlex 切分，不經 shell）")
    ap.add_argument("--target-psql", required=True, help="讀 stdin 腳本的 psql 指令（shlex 切分，不經 shell）")
    ap.add_argument("--json", action="store_true")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    source = PsqlTarget(args.local_psql)
    target = PsqlTarget(args.target_psql)
    try:
        if args.action == "plan":
            _, _, p = run_plan(source, target)
            if p.state == "reject":
                raise SyncError(EXIT_REJECT, "內容衝突，拒絕同步（不寫入、不重試）", p.rejects)
            print(f"insert_builds={p.insert_builds}")
            print(f"update_current={[f'{y}/{k}' for y, k in p.update_current]}")
            print(f"skipped_builds={p.skipped_builds}")
            print(f"TEAM_COMPARISON_SYNC_PLAN={p.state}")
            return 0
        if args.action == "apply":
            p, ok, rows = run_apply(source, target)
            print(f"TEAM_COMPARISON_SYNC_PLAN={p.state}" + ("（無變更，未寫入）" if p.state == "no-change" else ""))
        else:
            ok, rows = reconcile(read_local(source), read_target(target))
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            _print_table(rows)
        if not ok:
            raise SyncError(EXIT_RECONCILE, "事後對帳不等（已寫入列保留，不刪）")
        print("TEAM_COMPARISON_SYNC_RECONCILE=ok")
        return 0
    except SyncError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        if exc.detail:
            print(json.dumps(exc.detail, ensure_ascii=False, indent=2, default=str), file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())

