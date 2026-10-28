"""#383 段 2 P-B：11 張衍生表的受守衛整表替換（PLAN-v4 §3.2 P-B、§4 S2-3a／S2-3、§6）。

⛔ 本檔不是每日同步的一部分，也不取代 `refresh-cpbl-prod.sh` 的 `sync_table`／`mirror_table`；
它是 #383 段 2 一次性的整表替換工具。形狀沿用 `mirror_table`（payload 先落地、形狀守衛通過才送出、
單一交易）與 #357 `prod_clear_livelog_extra.sh`（預設唯讀、`--apply` 才寫、庫名雙重守衛）。

兩個子命令。forward（灌入新值）與 rollback（灌回備份）用**同一個** `replace`、同一套斷言，
差別只在拿哪一份 export 當輸入：

    # 1) 取值：單一 REPEATABLE READ READ ONLY 快照內，對 11 表 COPY 出資料並算出列數與有序 md5
    uv run python docs/research/ISSUE-383/replace_derived_tables.py export --target local:cpbl_383s2 \
        --expect-db cpbl_383s2 --out <目錄>
    # 2) 唯讀檢查（預設）：核對 payload 形狀與 manifest，列出目標庫現值與預期值的逐表差異
    uv run python docs/research/ISSUE-383/replace_derived_tables.py replace --target local:cpbl_383s2 \
        --expect-db cpbl_383s2 --payload <export 目錄>
    # 3) 寫入：同上加 --apply。單一交易：庫名守衛 → 鎖表 → DELETE 全表 → COPY → 交易內逐表斷言列數＋md5，
    #    任一不符 RAISE、整筆回滾
    uv run python docs/research/ISSUE-383/replace_derived_tables.py replace ... --apply

rollback：寫入前先對目標庫跑一次 `export`（那份就是回滾 payload），出事時把它當 `--payload` 再跑
`replace --apply`。

md5 定義（export 端與交易內斷言共用 `table_digest_sql` 這一個產生器）：
`md5(coalesce(string_agg(ROW(<manifest 欄序>)::text, E'\\n' ORDER BY <主鍵>), ''))`，
於 `SET LOCAL TimeZone='UTC'、DateStyle='ISO, YMD'、IntervalStyle='postgres'、extra_float_digits=1`
之下計算。欄序取 manifest（不取目標表的實體欄序），兩端實體欄序不同也算得一致。

目標（`--target`）：
- `local:<庫名>` → `docker exec -i cpbl-analytics-db-1 psql -U cpbl -d <庫名>`
- `prod` → 經 ssh 進 `prod_pg`，庫名取正式站 `.env` 的 `DB_NAME`，且必須等於 `--expect-db`。
  ⛔ 依 DATABASE_CONTRACT §5，正式站 `--apply` 由需求方執行（PLAN-v4 §3.2、R3）。

庫名守衛兩層：連線後先 `SELECT current_database()` 比對 `--expect-db`（不符直接退出、不送任何寫入）；
寫入交易 BEGIN 後的第一個語句再以 `DO` 區塊驗一次，不符 RAISE、整筆回滾。

退出碼：0＝檢查完成且目標已等於預期（或寫入成功）；10＝唯讀檢查完成、目標與預期有差異；
2＝參數或 payload 形狀錯誤（未送出）；3＝lock 或每日鏈程序存在（未送出）；4＝庫名守衛拒絕（未送出）；
5＝psql 執行失敗（寫入交易已回滾）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

# PLAN-v4 §1.1／S2-0 REPORT 的 11 張表；順序＝寫入順序（表間無 FK／trigger，順序只影響輸出可讀性）。
TABLES: tuple[str, ...] = (
    "fielding_innings",
    "catcher_runs",
    "batter_traits",
    "pitcher_traits",
    "run_expectancy",
    "sabr_run_values",
    "batter_wsb",
    "batter_re24",
    "pitcher_re24",
    "run_dist",
    "win_expectancy",
)

LOCK_FILE = Path("/private/tmp/cpbl-analytics-refresh.lock")
CHAIN_PATTERN = "refresh-cpbl-prod|scrape-daily|cpbl-refresh-recent|postseason-evening"
LOCAL_CONTAINER = "cpbl-analytics-db-1"
VPS = os.environ.get("VPS", "root@45.76.100.29")
DEPLOY_PATH = os.environ.get("DEPLOY_PATH", "/opt/personal-website")

SESSION_SETTINGS = (
    "SET LOCAL TimeZone = 'UTC';",
    "SET LOCAL DateStyle = 'ISO, YMD';",
    "SET LOCAL IntervalStyle = 'postgres';",
    "SET LOCAL extra_float_digits = 1;",
)
PSET = ("\\pset format unaligned", "\\pset tuples_only on")

# 表分段標記：COPY text 格式裡資料內的反斜線一律轉義成 `\\`，故以單一 `\.` 起頭的行只可能是
# 終止符或本標記，不可能是資料。
_MARK_TABLE = "\\.PB-TABLE "
_MARK_DIGEST = "PB-DIGEST|"
_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


class PayloadError(Exception):
    """payload／manifest／參數形狀不符；尚未送出任何寫入。"""


def _ident(name: str) -> str:
    if not _IDENT_RE.match(name):
        raise PayloadError(f"識別字不合法：{name!r}")
    return name


def _lit(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def table_digest_sql(table: str, cols: list[str], pk: list[str]) -> str:
    """回傳 `(count, md5)` 的 SELECT；export 端與交易內斷言共用這一個產生器。"""
    t = _ident(table)
    c = ", ".join(_ident(x) for x in cols)
    o = ", ".join(_ident(x) for x in pk)
    return (
        f"SELECT count(*)::bigint, "
        f"md5(coalesce(string_agg(ROW({c})::text, E'\\n' ORDER BY {o}), '')) "
        f"FROM cpbl.{t}"
    )


def _digest_line_sql(tag: str, table: str, m: dict) -> str:
    return f"SELECT '{tag}{table}|' || n || '|' || h FROM ({table_digest_sql(table, m['cols'], m['pk'])}) AS x(n, h);"


def guard_sql(expect_db: str) -> str:
    """寫入交易 BEGIN 後第一個語句：current_database() 必須等於 expect_db，否則 RAISE。"""
    return (
        "DO $pbguard$ BEGIN\n"
        f"  IF current_database() <> {_lit(expect_db)} THEN\n"
        f"    RAISE EXCEPTION 'PB-GUARD: current_database()=% 不是 %', current_database(), {_lit(expect_db)};\n"
        "  END IF;\n"
        "END $pbguard$;"
    )


def assert_sql(manifest: dict) -> str:
    """交易內逐表斷言：列數與 md5 任一不符即 RAISE（整筆回滾）。"""
    lines = ["DO $pbassert$ DECLARE n bigint; h text; BEGIN"]
    for t in TABLES:
        m = manifest["tables"][t]
        lines.append(f"  {table_digest_sql(t, m['cols'], m['pk'])} INTO n, h;")
        lines.append(f"  IF n <> {int(m['rows'])} OR h <> {_lit(m['md5'])} THEN")
        lines.append(
            f"    RAISE EXCEPTION 'PB-ASSERT {t}: rows=% md5=% 預期 rows={int(m['rows'])} md5={m['md5']}', n, h;"
        )
        lines.append("  END IF;")
    lines.append(f"  RAISE NOTICE 'PB-ASSERT-OK {len(TABLES)} 表';")
    lines.append("END $pbassert$;")
    return "\n".join(lines)


def validate_manifest(manifest: dict, copies: dict[str, bytes]) -> None:
    """manifest 必須恰為 11 表、欄位／主鍵為合法識別字、每份 COPY 檔 sha256 與行數相符。"""
    tabs = manifest.get("tables")
    if not isinstance(tabs, dict) or set(tabs) != set(TABLES):
        got = sorted(tabs) if isinstance(tabs, dict) else tabs
        raise PayloadError(f"manifest 表集合不符：{got}")
    if set(copies) != set(TABLES):
        raise PayloadError(f"payload COPY 檔集合不符：{sorted(copies)}")
    for t in TABLES:
        m = tabs[t]
        for k in ("cols", "pk", "rows", "md5", "sha256"):
            if k not in m:
                raise PayloadError(f"{t} manifest 缺 {k}")
        for x in [*m["cols"], *m["pk"]]:
            _ident(x)
        if not m["pk"] or not set(m["pk"]) <= set(m["cols"]):
            raise PayloadError(f"{t} 主鍵為空或不在欄位內")
        if not re.fullmatch(r"[0-9a-f]{32}", str(m["md5"])):
            raise PayloadError(f"{t} md5 形狀不符：{m['md5']!r}")
        body = copies[t]
        if hashlib.sha256(body).hexdigest() != m["sha256"]:
            raise PayloadError(f"{t} COPY 檔 sha256 與 manifest 不符")
        if body and not body.endswith(b"\n"):
            raise PayloadError(f"{t} COPY 檔未以換行結束")
        n = body.count(b"\n")
        if n != int(m["rows"]):
            raise PayloadError(f"{t} COPY 檔行數 {n} 與 manifest rows {m['rows']} 不符")
        if any(line.startswith(b"\\.") for line in body.split(b"\n")):
            raise PayloadError(f"{t} COPY 檔含終止符形狀的行")


def build_apply_sql(manifest: dict, copies: dict[str, bytes], expect_db: str) -> bytes:
    """單一交易：BEGIN → 庫名守衛 → 鎖表 → 寫前現值 → 逐表 DELETE＋COPY → 斷言 → COMMIT。"""
    validate_manifest(manifest, copies)
    out: list[bytes] = []

    def w(s: str) -> None:
        out.append((s + "\n").encode())

    w("\\set ON_ERROR_STOP 1")
    for s in PSET:
        w(s)
    w("BEGIN;")
    w(guard_sql(expect_db))
    for s in SESSION_SETTINGS:
        w(s)
    w("LOCK TABLE " + ", ".join(f"cpbl.{_ident(t)}" for t in TABLES) + " IN EXCLUSIVE MODE;")
    for t in TABLES:
        w(_digest_line_sql("PB-BEFORE|", t, manifest["tables"][t]))
    for t in TABLES:
        m = manifest["tables"][t]
        w(f"DELETE FROM cpbl.{_ident(t)};")
        w(f"COPY cpbl.{_ident(t)} ({', '.join(_ident(c) for c in m['cols'])}) FROM stdin;")
        out.append(copies[t])
        w("\\.")
    w(assert_sql(manifest))
    for t in TABLES:
        w(_digest_line_sql("PB-AFTER|", t, manifest["tables"][t]))
    w("COMMIT;")
    return b"".join(out)


_FORBIDDEN = re.compile(r"(?i)\b(DROP|TRUNCATE|ALTER|CASCADE|INSERT|UPDATE|GRANT|REVOKE)\b")


def check_payload_shape(sql: bytes) -> list[str]:
    """送出前形狀守衛（同 mirror_table awk 守衛的精神）：只允許本工具產生的語句種類與順序。"""
    why: list[str] = []
    in_copy = False
    deletes: list[str] = []
    copies: list[str] = []
    stmts: list[str] = []
    for raw in sql.decode().split("\n"):
        if in_copy:
            if raw == "\\.":
                in_copy = False
            continue
        if not raw or raw == "\\set ON_ERROR_STOP 1" or raw in PSET:
            continue
        if raw.startswith("COPY "):
            copies.append(raw)
            in_copy = True
            continue
        stmts.append(raw)
        if raw.startswith("DELETE "):
            deletes.append(raw)
        if _FORBIDDEN.search(raw):
            why.append(f"禁止語句：{raw[:80]}")
    if in_copy:
        why.append("COPY 未結束")
    if stmts[:2] != ["BEGIN;", "DO $pbguard$ BEGIN"]:
        why.append("BEGIN 後第一個語句不是庫名守衛")
    if not any(s.startswith("  IF current_database() <> ") for s in stmts):
        why.append("缺庫名比對")
    if "DO $pbassert$ DECLARE n bigint; h text; BEGIN" not in stmts:
        why.append("缺交易內斷言")
    n_md5_checks = sum(1 for s in stmts if re.match(r"^  IF n <> \d+ OR h <> '[0-9a-f]{32}' THEN$", s))
    if n_md5_checks != len(TABLES):
        why.append(f"列數＋md5 斷言數 {n_md5_checks}，應為 {len(TABLES)}")
    if deletes != [f"DELETE FROM cpbl.{t};" for t in TABLES]:
        why.append(f"DELETE 形狀不符：{deletes}")
    if [c.split(" (")[0] for c in copies] != [f"COPY cpbl.{t}" for t in TABLES]:
        why.append("COPY 形狀不符")
    if not stmts or stmts[-1] != "COMMIT;":
        why.append("最後一個語句不是 COMMIT")
    return why


def _echo_mark(table: str) -> str:
    # psql 單引號內的反斜線要成對，才會印出單一 `\`
    return "\\echo '" + (_MARK_TABLE + table).replace("\\", "\\\\") + "'"


def build_export_sql(meta: dict[str, dict]) -> str:
    """單一 REPEATABLE READ READ ONLY 快照：先印 11 表 digest 行，再逐表以標記行起頭 COPY 出資料。"""
    out = ["\\set ON_ERROR_STOP 1", *PSET, "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;", *SESSION_SETTINGS]
    out.append("SELECT 'PB-DB|' || current_database() || '|' || now()::text;")
    # digest 行全部先印、COPY 段在後：COPY 段之內只會出現資料與下一個標記行，digest 行不會被誤收成資料
    out += [_digest_line_sql(_MARK_DIGEST, t, meta[t]) for t in TABLES]
    for t in TABLES:
        m = meta[t]
        out.append(_echo_mark(t))
        cols = ", ".join(_ident(c) for c in m["cols"])
        order = ", ".join(_ident(c) for c in m["pk"])
        out.append(f"COPY (SELECT {cols} FROM cpbl.{_ident(t)} ORDER BY {order}) TO STDOUT;")
    out.append(_echo_mark("__END__"))
    out.append("COMMIT;")
    return "\n".join(out) + "\n"


def parse_export_stream(stream: bytes) -> tuple[str, dict[str, tuple[int, str]], dict[str, bytes]]:
    """把 export 的單一 psql 輸出切成 (庫名, 每表 digest, 每表 COPY 原文)。"""
    db = ""
    digests: dict[str, tuple[int, str]] = {}
    copies: dict[str, bytes] = {}
    cur: str | None = None
    buf: list[bytes] = []
    lines = stream.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    for line in lines:
        s = line.decode()
        if s.startswith(_MARK_TABLE):
            if cur is not None:
                copies[cur] = b"".join(x + b"\n" for x in buf)
            name = s[len(_MARK_TABLE):]
            cur = None if name == "__END__" else name
            buf = []
            continue
        if cur is not None:
            buf.append(line)
            continue
        if s.startswith("PB-DB|"):
            db = s.split("|")[1]
        elif s.startswith(_MARK_DIGEST):
            _, t, n, h = s.split("|")
            digests[t] = (int(n), h)
    if cur is not None:
        raise PayloadError(f"export 輸出在 {cur} 中途結束（缺結束標記）")
    return db, digests, copies


def target_argv(target: str, *, write: bool) -> list[str]:
    """回傳 psql argv（SQL 一律走 stdin）。唯讀連線多一個 session 級 default_transaction_read_only。"""
    flags = ["-X", "-q", "-v", "ON_ERROR_STOP=1"]
    if not write:
        flags += ["-c", "SET default_transaction_read_only = on", "-f", "-"]
    if target.startswith("local:"):
        db = _ident(target.split(":", 1)[1])
        return ["docker", "exec", "-i", LOCAL_CONTAINER, "psql", *flags, "-U", "cpbl", "-d", db]
    if target == "prod":
        inner = (
            f"cd {shlex.quote(DEPLOY_PATH)} && set -a && . ./.env && docker exec -i prod_pg psql "
            + " ".join(shlex.quote(f) for f in flags)
            + ' -U "$DB_USER" -d "$DB_NAME"'
        )
        return ["ssh", "-o", "BatchMode=yes", VPS, inner]
    raise PayloadError(f"--target 只接受 local:<庫名> 或 prod：{target!r}")


def _run(target: str, sql: bytes, *, write: bool) -> subprocess.CompletedProcess:
    return subprocess.run(target_argv(target, write=write), input=sql, capture_output=True, check=False)


def _ro(target: str, sql_lines: list[str], what: str) -> str:
    r = _run(target, ("\n".join([*PSET, *sql_lines]) + "\n").encode(), write=False)
    if r.returncode != 0:
        print(f"FATAL: {what}失敗：{r.stderr.decode()[-600:]}", file=sys.stderr)
        raise SystemExit(5)
    return r.stdout.decode()


def _guard_db(target: str, expect_db: str) -> None:
    out = _ro(target, ["SELECT current_database();"], "連線")
    db = out.strip().splitlines()[-1].strip() if out.strip() else ""
    if db != expect_db:
        print(f"FATAL: PB-GUARD 連線庫 {db!r} 不是 --expect-db {expect_db!r}（未送出任何寫入）", file=sys.stderr)
        raise SystemExit(4)
    print(f"[guard] current_database()={db}")


def _table_meta(target: str) -> dict[str, dict]:
    names = ", ".join(_lit(t) for t in TABLES)
    sql = (
        "SELECT c.relname, string_agg(a.attname, ',' ORDER BY a.attnum), "
        "(SELECT string_agg(pa.attname, ',' ORDER BY array_position(i.indkey, pa.attnum)) "
        "   FROM pg_index i JOIN pg_attribute pa ON pa.attrelid = i.indrelid AND pa.attnum = ANY(i.indkey) "
        "  WHERE i.indrelid = c.oid AND i.indisprimary) "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped "
        f"WHERE n.nspname = 'cpbl' AND c.relkind = 'r' AND c.relname IN ({names}) GROUP BY c.relname, c.oid;"
    )
    meta: dict[str, dict] = {}
    for line in _ro(target, [sql], "讀表結構").splitlines():
        if line.count("|") != 2:
            continue
        t, cols, pk = line.split("|")
        meta[t] = {"cols": cols.split(","), "pk": pk.split(",") if pk else []}
    missing = [t for t in TABLES if t not in meta or not meta[t]["pk"]]
    if missing:
        print(f"FATAL: 目標庫缺表或缺主鍵：{missing}", file=sys.stderr)
        raise SystemExit(2)
    return meta


def _current_digests(target: str, manifest: dict) -> dict[str, tuple[int, str]]:
    sql = ["BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;", *SESSION_SETTINGS]
    sql += [_digest_line_sql(_MARK_DIGEST, t, manifest["tables"][t]) for t in TABLES]
    sql.append("COMMIT;")
    return parse_export_stream(_ro(target, sql, "讀現值").encode())[1]


def _chain_running() -> str | None:
    if LOCK_FILE.exists():
        return f"lock 存在：{LOCK_FILE}"
    r = subprocess.run(["pgrep", "-fl", CHAIN_PATTERN], capture_output=True, text=True, check=False)
    hits = [x for x in r.stdout.splitlines() if "pytest-of-" not in x]
    return f"每日鏈程序存在：{hits}" if hits else None


def load_payload(d: Path) -> tuple[dict, dict[str, bytes]]:
    manifest = json.loads((d / "manifest.json").read_text())
    copies = {t: (d / f"{t}.copy").read_bytes() for t in TABLES if (d / f"{t}.copy").exists()}
    validate_manifest(manifest, copies)
    return manifest, copies


def cmd_export(a: argparse.Namespace) -> int:
    _guard_db(a.target, a.expect_db)
    meta = _table_meta(a.target)
    r = _run(a.target, build_export_sql(meta).encode(), write=False)
    if r.returncode != 0:
        print(f"FATAL: export 失敗：{r.stderr.decode()[-800:]}", file=sys.stderr)
        return 5
    db, digests, copies = parse_export_stream(r.stdout)
    if db != a.expect_db or set(digests) != set(TABLES) or set(copies) != set(TABLES):
        print(f"FATAL: export 輸出不完整：db={db} digests={sorted(digests)} copies={sorted(copies)}", file=sys.stderr)
        return 5
    tables = {
        t: {
            "cols": meta[t]["cols"],
            "pk": meta[t]["pk"],
            "rows": digests[t][0],
            "md5": digests[t][1],
            "sha256": hashlib.sha256(copies[t]).hexdigest(),
        }
        for t in TABLES
    }
    manifest = {
        "source_db": db,
        "source_target": a.target,
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "md5_definition": "md5(coalesce(string_agg(ROW(cols)::text, E'\\n' ORDER BY pk), '')) "
        "with TimeZone=UTC, DateStyle=ISO,YMD, IntervalStyle=postgres, extra_float_digits=1",
        "tables": tables,
    }
    validate_manifest(manifest, copies)  # 自己產生的也過同一道驗證
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for t in TABLES:
        (out / f"{t}.copy").write_bytes(copies[t])
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")
    for t in TABLES:
        print(f"  {t}: rows={tables[t]['rows']} md5={tables[t]['md5']}")
    print(f"✓ export {db} → {out}")
    return 0


def cmd_replace(a: argparse.Namespace) -> int:
    manifest, copies = load_payload(Path(a.payload))
    sql = build_apply_sql(manifest, copies, a.expect_db)
    why = check_payload_shape(sql)
    if why:
        print("FATAL: payload 未通過送出前守衛（未送出）：" + "；".join(why), file=sys.stderr)
        return 2
    _guard_db(a.target, a.expect_db)
    meta = _table_meta(a.target)
    for t in TABLES:
        m = manifest["tables"][t]
        if meta[t]["pk"] != m["pk"] or set(meta[t]["cols"]) != set(m["cols"]):
            print(f"FATAL: {t} 目標表欄位／主鍵與 manifest 不符（未送出）", file=sys.stderr)
            return 2
    cur = _current_digests(a.target, manifest)
    ndiff = 0
    for t in TABLES:
        m = manifest["tables"][t]
        now = cur.get(t, (-1, "?"))
        same = now == (int(m["rows"]), m["md5"])
        ndiff += not same
        print(f"  {'＝' if same else '≠'} {t}: 現值 rows={now[0]} md5={now[1]}｜預期 rows={m['rows']} md5={m['md5']}")
    print(f"[check] 差異表數={ndiff}／{len(TABLES)}" + ("（已是目標）" if ndiff == 0 else ""))
    if not a.apply:
        print("（唯讀檢查完成；要寫入請加 --apply）")
        return 0 if ndiff == 0 else 10
    busy = _chain_running()
    if busy:
        print(f"FATAL: {busy}；先等它結束（未送出）", file=sys.stderr)
        return 3
    r = _run(a.target, sql, write=True)
    sys.stdout.write(r.stdout.decode())
    sys.stderr.write(r.stderr.decode())
    if r.returncode != 0:
        print(f"FATAL: 寫入交易失敗（rc={r.returncode}），整筆已回滾", file=sys.stderr)
        return 5
    print("✓ 整表替換完成（交易內 11 表斷言通過）")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="單一唯讀快照取 11 表 COPY＋manifest")
    e.add_argument("--target", required=True)
    e.add_argument("--expect-db", required=True)
    e.add_argument("--out", required=True)
    r = sub.add_parser("replace", help="預設唯讀檢查；--apply 才以單一交易整表替換")
    r.add_argument("--target", required=True)
    r.add_argument("--expect-db", required=True)
    r.add_argument("--payload", required=True)
    r.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)
    try:
        return cmd_export(a) if a.cmd == "export" else cmd_replace(a)
    except PayloadError as ex:
        print(f"FATAL: {ex}（未送出）", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
