"""#293 S12 WP2：季後目標場 box／PA 的 scoped 同步（``refresh-cpbl-prod.sh`` 的 ``POSTSEASON_BOXPA_ONLY``）。

用法（由 ``scripts/refresh-cpbl-prod.sh`` 依序呼叫；一般不需手動跑）::

    python -m cpbl.ingest.boxpa_sync --help
    python -m cpbl.ingest.boxpa_sync precheck   --games 2026-C-2 --local-psql CMD --target-psql CMD
    python -m cpbl.ingest.boxpa_sync pa-payload --games 2026-C-2 --local-psql CMD --out FILE
    python -m cpbl.ingest.boxpa_sync reconcile  --games 2026-C-2 --local-psql CMD --target-psql CMD --out FILE
    python -m cpbl.ingest.boxpa_sync fingerprint --games 2026-C-2 --psql CMD

設計（核定規劃 PLAN r2 §5 WP2、§9.1）：

* **只動目標場鍵**：box 七表由 shell 的 ``sync_table``（與完整鏈**同一份**欄位清單）只對目標鍵
  upsert、不 DELETE；PA 五表在單一交易內「子→父只 DELETE 目標鍵 → 父→子 ``OVERRIDING SYSTEM
  VALUE`` 插入本機同鍵列」。⛔ 不 TRUNCATE、⛔ 不 CASCADE（payload 送出前以 :func:`assert_pa_payload`
  斷言；FK 的 ``ON DELETE CASCADE`` 因子表先刪而無列可波及，且 :func:`closure_violations_sql`
  在交易內先擋下任何跨場參照）。
* **FK 閉包**：目標場列參照的 revision／build／PA 都必須屬同一場；非目標場列也不得參照目標場的列。
  本機在送出前驗（不成立就不送，exit 67）；同一段 SQL 也嵌進 payload，在 production 交易內再驗一次
  （成立才 DELETE，否則 RAISE → 整個交易回滾）。
* **新碼只在本機跑**（§9.1）：本模組在本機 host 執行，遠端只收到 SQL 文字（``--target-psql`` 是
  ``ssh … docker exec -i prod_pg psql``）。⛔ 不呼叫 ``prod_cpbl_api``、不 migrate、不訓練、不寫 refresh 標記。
* **對帳**：逐表、逐場列數（本機 vs production）＋ PA published build_id；不用
  ``game_source_revisions.row_count``（livelog 該值比實表多 1 的語意未查，PLAN §14）。

離開碼（shell 端照原碼結束，晚間鏈據此判斷）：
  0 成功 · 64 參數錯 · 67 本機自檢／FK 閉包不成立（不送）· 68 對帳不等
  72 ssh 連線失敗（暫時性，可重送一次）· 73 production 尚未完賽（等下一次；不是錯誤）
  74 production psql 報錯（不重送）
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cpbl.ingest._cli import cli_parser

EXIT_USAGE = 64
EXIT_SELF_CHECK = 67
EXIT_MISMATCH = 68
EXIT_TARGET = 72          # ssh 連線失敗（rc 255）：暫時性
EXIT_NOT_FINAL = 73
EXIT_TARGET_SQL = 74      # production psql 本身報錯：不重送

# 晚間鏈目標場只收 A／E／C（#365 起含一軍 A；⛔ 不收 D）；一次最多 7 場（台灣大賽上限；A 每晚 ≤3 場），
# 防呆避免誤傳整季清單。
GAME_KEY_RE = re.compile(r"^(\d{4})-([AEC])-(\d{1,3})$")
MAX_GAMES = 7

# box 七表：欄位清單**不在這裡**——住在 refresh-cpbl-prod.sh 的 sync_box_* 函式（與完整鏈共用）。
# 這裡只列名稱供對帳與指紋使用；tests/test_boxpa_sync_mode.py 釘住兩邊同一組。
BOX_TABLES: tuple[str, ...] = (
    "game_detail", "game_scoreboard", "game_livelog", "pitch_tracking",
    "pitching_game_flags", "batting_gamelog", "pitching_gamelog",
)
# PA 五表，父→子（INSERT 順序）；DELETE 用反序。
PA_TABLES: tuple[str, ...] = (
    "game_recap_source_revisions", "game_recap_builds", "game_plate_appearances",
    "game_pa_events", "game_pa_pitch_mappings",
)
# 有 GENERATED ALWAYS identity 的四表需 OVERRIDING SYSTEM VALUE；builds 的 build_id 是 uuid。
_PA_IDENTITY = {"game_recap_source_revisions", "game_plate_appearances", "game_pa_events",
                "game_pa_pitch_mappings"}
_PA_STAGE = {"game_recap_source_revisions": "_bp_rev", "game_recap_builds": "_bp_build",
             "game_plate_appearances": "_bp_pa", "game_pa_events": "_bp_ev",
             "game_pa_pitch_mappings": "_bp_map"}


class SyncError(RuntimeError):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, order=True)
class GameKey:
    year: int
    kind_code: str
    game_sno: int

    @property
    def text(self) -> str:
        return f"{self.year}-{self.kind_code}-{self.game_sno}"


def parse_games(raw: str) -> list[GameKey]:
    """``2026-C-2,2026-C-3`` → 去重排序的鍵。格式不符、空、超過上限一律 :class:`SyncError` 64。

    值已逐一以正規式驗成數字／A|E|C，才會被內插進 SQL（:func:`keys_sql`）——不接受任何其他字元。"""
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()]
    if not parts:
        raise SyncError(EXIT_USAGE, "目標場清單為空")
    keys = set()
    for p in parts:
        m = GAME_KEY_RE.fullmatch(p)
        if not m:
            raise SyncError(EXIT_USAGE, f"目標場鍵格式不符（需 YYYY-A|E|C-SNO）：{p!r}")
        keys.add(GameKey(int(m.group(1)), m.group(2), int(m.group(3))))
    if len(keys) > MAX_GAMES:
        raise SyncError(EXIT_USAGE, f"目標場最多 {MAX_GAMES} 場：{len(keys)}")
    return sorted(keys)


def keys_sql(keys: Sequence[GameKey], alias: str | None = None) -> str:
    """``(year, kind_code, game_sno) IN ((2026,'C',2), …)``（值已由 :func:`parse_games` 驗過）。"""
    p = f"{alias}." if alias else ""
    tuples = ",".join(f"({k.year},'{k.kind_code}',{k.game_sno})" for k in keys)
    return f"({p}year, {p}kind_code, {p}game_sno) IN ({tuples})"


# =========================================================================== FK 閉包

def closure_violations_sql(keys: Sequence[GameKey]) -> str:
    """回傳一段 SELECT，列出違反「目標場自成閉包」的參照（0 列＝成立）。

    兩個方向都驗：(a) 目標場的列參照了別場的 revision／build／PA；(b) 別場的列參照了目標場的
    revision／build／PA（此時 DELETE 目標場會讓別場列失去參照，或經 ``ON DELETE CASCADE`` 被連帶刪除）。
    ``game_pa_pitch_mappings.build_id`` 沒有 FK，但語意上同場，一併驗。
    """
    same = "{c}.year = {p}.year AND {c}.kind_code = {p}.kind_code AND {c}.game_sno = {p}.game_sno"
    edges = (
        # (子表, 子別名, 參照欄, 父表, 父別名, 父鍵欄)
        ("game_recap_builds", "c", "livelog_revision_id", "game_recap_source_revisions", "p", "id"),
        ("game_recap_builds", "c", "tracking_revision_id", "game_recap_source_revisions", "p", "id"),
        ("game_plate_appearances", "c", "build_id", "game_recap_builds", "p", "build_id"),
        ("game_pa_events", "c", "pa_row_id", "game_plate_appearances", "p", "pa_row_id"),
        ("game_pa_pitch_mappings", "c", "pa_row_id", "game_plate_appearances", "p", "pa_row_id"),
        ("game_pa_pitch_mappings", "c", "source_revision_id", "game_recap_source_revisions", "p", "id"),
        ("game_pa_pitch_mappings", "c", "build_id", "game_recap_builds", "p", "build_id"),
    )
    child_in, parent_in = keys_sql(keys, "c"), keys_sql(keys, "p")
    parts = []
    for child, ca, col, parent, pa, pcol in edges:
        cond = same.format(c=ca, p=pa)
        join = f"FROM cpbl.{child} {ca} JOIN cpbl.{parent} {pa} ON {pa}.{pcol} = {ca}.{col}"
        # 兩個方向分開寫（各自只用一側的場次鍵過濾），讓 production 端走 (year,kind_code,game_sno)
        # 索引而不是對 OR 條件全表掃描。
        for side, scope in (("out", child_in), ("in", parent_in)):
            parts.append(f"SELECT '{child}.{col}:{side}' AS edge, {ca}.year, {ca}.kind_code, "
                         f"{ca}.game_sno {join} WHERE {scope} AND NOT ({cond})")
    return "\n UNION ALL ".join(parts)


# =========================================================================== 傳輸

class Psql:
    """以 psql 讀 stdin 腳本（``docker exec -i …`` 或 ``ssh … psql``）；argv 不經 shell 解讀。"""

    def __init__(self, command: str | Sequence[str], *, label: str):
        self.argv = shlex.split(command) if isinstance(command, str) else list(command)
        self.label = label

    def run(self, script: str) -> str:
        proc = subprocess.run(self.argv, input=script, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            if self.label != "target":
                code = EXIT_SELF_CHECK
            else:
                code = EXIT_TARGET if proc.returncode == 255 else EXIT_TARGET_SQL
            raise SyncError(code,
                            f"{self.label} psql 失敗 rc={proc.returncode}：{proc.stderr.strip()[-400:]}")
        return proc.stdout

    def read(self, sql: str) -> list[list[str]]:
        script = ("\\set QUIET on\n\\set ON_ERROR_STOP on\n\\pset tuples_only on\n"
                  "\\pset format unaligned\n\\pset fieldsep '\\t'\nBEGIN TRANSACTION READ ONLY;\n"
                  + sql + ";\nCOMMIT;\n")
        out = self.run(script)
        return [line.split("\t") for line in out.splitlines() if line.strip()]

    def copy_out(self, sql: str) -> str:
        """``COPY (sql) TO STDOUT``（text 格式）的原文；與 pg_dump 的 COPY 資料段同一格式。"""
        return self.run("\\set QUIET on\n\\set ON_ERROR_STOP on\nBEGIN TRANSACTION READ ONLY;\n"
                        f"COPY ({sql}) TO STDOUT;\nCOMMIT;\n")


# =========================================================================== 讀取

def published_builds(db: Psql, keys: Sequence[GameKey]) -> dict[str, str]:
    rows = db.read(
        "SELECT year||'-'||kind_code||'-'||game_sno, build_id::text FROM cpbl.game_recap_builds "
        f"WHERE state = 'published' AND {keys_sql(keys)}")
    return {k: b for k, b in rows}


def counts(db: Psql, keys: Sequence[GameKey], tables: Iterable[str]) -> dict[str, dict[str, int]]:
    """逐表、逐場列數。沒有列的場記 0（不省略）。"""
    tables = list(tables)
    union = "\n UNION ALL ".join(
        f"SELECT '{t}', year||'-'||kind_code||'-'||game_sno, count(*) FROM cpbl.{t} "
        f"WHERE {keys_sql(keys)} GROUP BY 1, 2" for t in tables)
    out = {t: {k.text: 0 for k in keys} for t in tables}
    for t, key, n in db.read(union):
        out[t][key] = int(n)
    return out


def prod_completed(db: Psql, keys: Sequence[GameKey]) -> set[str]:
    """production 的 games 是否已依 ``cpbl.completion``（新判準＝API 用的那支）判為完賽。"""
    from cpbl.completion import completed_games_sql_with_evidence

    rows = db.read(
        "SELECT g.year||'-'||g.kind_code||'-'||g.game_sno FROM cpbl.games g "
        f"WHERE {keys_sql(keys, 'g')} AND {completed_games_sql_with_evidence('g')}")
    return {r[0] for r in rows}


# =========================================================================== precheck

def precheck(local: Psql, target: Psql, keys: Sequence[GameKey]) -> dict:
    """送出前自檢（全部唯讀）。回傳 ``{"pa_keys": [...], "pa_skipped": {...}}``。

    * production games 必須已完賽（否則 73：box／PA 不得先於 final 送達）。
    * 本機 FK 閉包必須成立（否則 67）。
    * PA 只對「本機有 published build」的場送；沒有的場 PA 一列都不動（不 DELETE production），
      記在 ``pa_skipped``。box 照送（本機有多少送多少，到齊與否由分類器判定）。
    """
    done = prod_completed(target, keys)
    missing = [k.text for k in keys if k.text not in done]
    if missing:
        raise SyncError(EXIT_NOT_FINAL, f"production 尚未完賽：{','.join(missing)}（等下一次）")
    bad = local.read(closure_violations_sql(keys))
    if bad:
        raise SyncError(EXIT_SELF_CHECK, f"本機 FK 閉包不成立（不送）：{bad[:5]}")
    pub = published_builds(local, keys)
    return {"pa_keys": [k.text for k in keys if k.text in pub],
            "pa_skipped": {k.text: "no_local_published_build" for k in keys if k.text not in pub}}


# =========================================================================== PA payload

def build_pa_payload(local: Psql, keys: Sequence[GameKey]) -> str:
    """目標鍵 PA 五表替換的單交易 payload（由 shell 以 ``psql --single-transaction`` 送出）。

    形狀：交易內守衛（timeout、production 端閉包）→ 子→父 DELETE 目標鍵 → 父→子 暫存＋INSERT →
    事後列數自檢。⛔ 不含 TRUNCATE／CASCADE／setval（:func:`assert_pa_payload`）。"""
    scope = keys_sql(keys)
    lines = [
        "SET LOCAL statement_timeout = '300s';",
        "SET LOCAL lock_timeout = '10s';",
        "DO $boxpa$ BEGIN",
        f"  IF EXISTS ({closure_violations_sql(keys)}) THEN",
        "    RAISE EXCEPTION 'BOXPA_CLOSURE production 端目標場閉包不成立（不刪不寫）';",
        "  END IF;",
        "END $boxpa$;",
    ]
    for t in reversed(PA_TABLES):
        lines.append(f"DELETE FROM cpbl.{t} WHERE {scope};")
    checks = []
    for t in PA_TABLES:
        stg = _PA_STAGE[t]
        data = local.copy_out(f"SELECT * FROM cpbl.{t} WHERE {scope}")
        lines.append(f"CREATE TEMP TABLE {stg} (LIKE cpbl.{t} INCLUDING DEFAULTS) ON COMMIT DROP;")
        lines.append(f"COPY {stg} FROM stdin;")
        if data.strip():
            lines.append(data.rstrip("\n"))
        lines.append("\\.")
        lines.append(f"DO $boxpa$ BEGIN IF EXISTS (SELECT 1 FROM {stg} WHERE NOT {scope}) THEN "
                     f"RAISE EXCEPTION 'BOXPA_SCOPE {t} 暫存含目標外的列'; END IF; END $boxpa$;")
        override = " OVERRIDING SYSTEM VALUE" if t in _PA_IDENTITY else ""
        lines.append(f"INSERT INTO cpbl.{t}{override} SELECT * FROM {stg};")
        checks.append(f"(SELECT count(*) FROM cpbl.{t} WHERE {scope}) <> (SELECT count(*) FROM {stg})")
    lines.append("DO $boxpa$ BEGIN IF " + " OR ".join(checks) + " THEN "
                 "RAISE EXCEPTION 'BOXPA_COUNT 寫入後列數與暫存不符'; END IF; END $boxpa$;")
    return "\n".join(lines) + "\n"


_FORBIDDEN = re.compile(r"\b(TRUNCATE|CASCADE|setval|DROP\s+TABLE|ALTER\s+TABLE|refresh_log)\b", re.I)


def assert_pa_payload(payload: str, keys: Sequence[GameKey]) -> None:
    """送出前守衛（fail closed）：不在 COPY 資料段的每一行，都必須是本模組產生的形狀。"""
    scope = keys_sql(keys)
    in_copy = False
    deletes, inserts = [], []
    for line in payload.splitlines():
        if in_copy:
            if line == "\\.":
                in_copy = False
            continue
        if line.startswith("COPY ") and line.endswith(" FROM stdin;"):
            in_copy = True
            continue
        if _FORBIDDEN.search(line):
            raise SyncError(EXIT_SELF_CHECK, f"PA payload 含禁止語句：{line[:120]}")
        if line.startswith("DELETE "):
            if not line.endswith(f" WHERE {scope};"):
                raise SyncError(EXIT_SELF_CHECK, f"DELETE 不是只限目標鍵：{line[:160]}")
            deletes.append(line.split()[2])
        if line.startswith("INSERT "):
            inserts.append(line.split()[2])
    if in_copy:
        raise SyncError(EXIT_SELF_CHECK, "PA payload COPY 不完整")
    want_del = [f"cpbl.{t}" for t in reversed(PA_TABLES)]
    want_ins = [f"cpbl.{t}" for t in PA_TABLES]
    if deletes != want_del or inserts != want_ins:
        raise SyncError(EXIT_SELF_CHECK, f"PA payload 形狀不符：DELETE {deletes}／INSERT {inserts}")


# =========================================================================== 對帳

def reconcile(local: Psql, target: Psql, keys: Sequence[GameKey], pa_keys: Iterable[str],
              parts: Iterable[str] = ("box", "pa")) -> dict:
    """逐表逐場對帳。回傳 manifest；``ok`` 為 False 時 shell 以 68 結束。

    * box：七表逐場列數相等（本次沒送 box 時 ``box_ok=None``，不參與 ``ok``）。
    * PA：``pa_keys``（本機有 published 的場）五表逐場列數相等，且 published build_id 相同。
    """
    pa_keys = set(pa_keys)
    tables = (*BOX_TABLES, *PA_TABLES)
    lc, tc = counts(local, keys, tables), counts(target, keys, tables)
    lpub, tpub = published_builds(local, keys), published_builds(target, keys)
    games = {}
    ok = True
    for k in keys:
        box = {t: {"local": lc[t][k.text], "prod": tc[t][k.text]} for t in BOX_TABLES}
        box_ok = all(v["local"] == v["prod"] for v in box.values()) if "box" in set(parts) else None
        pa = {t: {"local": lc[t][k.text], "prod": tc[t][k.text]} for t in PA_TABLES}
        if k.text in pa_keys:
            pa_ok = (all(v["local"] == v["prod"] for v in pa.values())
                     and lpub.get(k.text) is not None and lpub.get(k.text) == tpub.get(k.text))
        else:
            pa_ok = None   # 本次未送 PA
        ok = ok and box_ok is not False and pa_ok is not False
        games[k.text] = {"box": box, "box_ok": box_ok, "pa": pa, "pa_sent": k.text in pa_keys,
                         "pa_ok": pa_ok, "published_build_local": lpub.get(k.text),
                         "published_build_prod": tpub.get(k.text)}
    return {"at": datetime.now(UTC).isoformat(), "ok": ok, "games": games}


# =========================================================================== 非目標場指紋

FINGERPRINT_SCOPE = "year = 2026 AND kind_code IN ('E', 'C')"


def fingerprint(db: Psql, keys: Sequence[GameKey], *, whole_table: bool = False) -> dict[str, dict]:
    """非目標場的逐表指紋（列數＋同一 session 內的列文字 md5），供前後比對「沒有碰到別場」。

    範圍預設只取 2026 E／C 的非目標場（production 1 vCPU 上不掃全史 PA 五表）；
    ``whole_table=True``（隔離 DB 預演用）掃整表非目標列。指紋只在同一顆 DB 前後比較，跨 DB 不可比。"""
    scope = "TRUE" if whole_table else FINGERPRINT_SCOPE
    out = {}
    for t in (*BOX_TABLES, *PA_TABLES):
        (row,) = db.read(
            f"SELECT count(*), COALESCE(md5(string_agg(x::text, '|' ORDER BY x::text)), '') "
            f"FROM cpbl.{t} x WHERE ({scope}) AND NOT {keys_sql(keys, 'x')}")
        out[t] = {"rows": int(row[0]), "md5": row[1]}
    return out


# =========================================================================== CLI

def _parser():
    p = cli_parser("python -m cpbl.ingest.boxpa_sync", __doc__)
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("precheck", "pa-payload", "reconcile"):
        s = sub.add_parser(name)
        s.add_argument("--games", required=True)
        s.add_argument("--local-psql", required=True)
        if name != "pa-payload":
            s.add_argument("--target-psql", required=True)
        if name != "precheck":
            s.add_argument("--out", required=True)
        if name in ("pa-payload", "reconcile"):
            s.add_argument("--pa-games", default="", help="precheck 判定可送 PA 的場（逗號分隔；可空）")
        if name == "reconcile":
            s.add_argument("--parts", default="box,pa", help="這次送出的來源（box,pa／box／pa）")
    f = sub.add_parser("fingerprint")
    f.add_argument("--games", required=True)
    f.add_argument("--psql", required=True)
    f.add_argument("--whole-table", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        keys = parse_games(args.games)
        if args.command == "fingerprint":
            print(json.dumps(fingerprint(Psql(args.psql, label="db"), keys,
                                         whole_table=args.whole_table), sort_keys=True))
            return 0
        local = Psql(args.local_psql, label="local")
        if args.command == "precheck":
            result = precheck(local, Psql(args.target_psql, label="target"), keys)
            print(f"BOXPA_KEYS_SQL={keys_sql(keys)}")
            print(f"BOXPA_PA_GAMES={','.join(result['pa_keys'])}")
            for key, why in sorted(result["pa_skipped"].items()):
                print(f"BOXPA_PA_SKIPPED={key}:{why}")
            return 0
        pa_keys = [k for k in (args.pa_games or "").split(",") if k]
        pa_scope = [k for k in keys if k.text in set(pa_keys)]
        if args.command == "pa-payload":
            payload = build_pa_payload(local, pa_scope) if pa_scope else ""
            if payload:
                assert_pa_payload(payload, pa_scope)
            Path(args.out).write_text(payload, encoding="utf-8")
            print(f"BOXPA_PA_PAYLOAD={'empty' if not payload else len(payload)}")
            return 0
        manifest = reconcile(local, Psql(args.target_psql, label="target"), keys, pa_keys,
                             [p for p in args.parts.split(",") if p])
        Path(args.out).write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
                                  encoding="utf-8")
        print(f"BOXPA_RECONCILE={'ok' if manifest['ok'] else 'mismatch'}")
        return 0 if manifest["ok"] else EXIT_MISMATCH
    except SyncError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
