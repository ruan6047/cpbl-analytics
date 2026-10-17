"""名單三表本機 → 目標庫（生產）的獨立 insert-only 同步（#284 Q3 裁定 A）。

⛔ 不進 refresh-cpbl-prod.sh 的 sync_table UPSERT 清單、⛔ 不掛每日鏈、⛔ 無 UPDATE／DELETE。
shell（`ROSTER_ONLY=1`）只負責備份與把 psql 管道接到目標；比對、payload、對帳都在本模組：

1. 本機自檢：讀本機三表，以 canonical 重算 membership／source／revision 雜湊，必須等於存值（exit 67）。
2. 目標唯讀比對：目標沒有三表＝exit 69（schema 只隨部署窗口套用，本模組不 migrate）。
   逐 scope（year, kind_code, team_code）：目標無＝待插入；名單頭、會員、角色版全同＝略過；
   任一不同＝拒絕並報差異（exit 70，⛔ 整批不寫、⛔ 不重試）；目標有本機無的名單或角色版＝拒絕。
3. 全部略過＝`ROSTER_SYNC_PLAN=no-change`（shell 不備份、不寫）。
4. 有待插入＝`ROSTER_SYNC_PLAN=insert-pending`；`apply` 以單一 psql 交易寫入：payload 以 COPY 進
   temp 表 → 交易內再查一次衝突（防比對與寫入之間的競寫）→ `INSERT … SELECT … WHERE NOT EXISTS`。
   目標端的唯一鍵、不可變觸發器與 32 人延遲約束同樣生效。
5. 事後對帳：再唯讀取回目標列，重算雜湊並逐 scope 對照本機（exit 71；已寫入列保留，不刪）。

用法（兩端都是「讀 stdin 腳本的 psql 指令」，shlex 切分、不經本機 shell；本機端只做唯讀查詢）：
  python -m cpbl.rosters.sync plan \
      --local-psql  "docker exec -i cpbl284-pg psql -U cpbl -d cpbl_test_284" \
      --target-psql "docker exec -i cpbl284-pg psql -U cpbl -d cpbl_test_284_prod"
  python -m cpbl.rosters.sync apply     --local-psql "…" --target-psql "…"
  python -m cpbl.rosters.sync reconcile --local-psql "…" --target-psql "…"
生產接線只在 scripts/refresh-cpbl-prod.sh 的 ROSTER_ONLY=1 模式（先 plan、有待插入才備份、再 apply）。

退出碼：0 成功 · 2 參數錯 · 67 本機自檢失敗 · 69 目標尚無名單表（待部署窗口）
        70 內容不同拒絕（不寫） · 71 事後對帳不等 · 72 目標指令失敗（psql／ssh）
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime

from cpbl.rosters.canonical import (
    ROSTER_SIZE,
    membership_hash,
    revision_hash,
    revision_hash_v2,
    source_hash,
    validate_roles_v2,
)

EXIT_SELF_CHECK = 67
EXIT_NO_TABLE = 69
EXIT_REJECT = 70
EXIT_RECONCILE = 71
EXIT_TARGET = 72

HEAD_COLUMNS = (
    "roster_id", "year", "kind_code", "team_code", "source_url", "published_date",
    "published_precision", "observed_at", "observation_basis", "identity_verified_at",
    "input_origin", "raw_text", "hash_version", "membership_hash", "source_hash",
    "import_check", "submitted_at",
)
MEMBER_COLUMNS = ("roster_id", "player_id", "official_position", "announced_name")
REVISION_COLUMNS = ("roster_id", "revision", "player_id", "tactical_role", "revision_hash",
                    "changed_at", "role_format_version", "tactical_roles", "role_provenance")
_TIMESTAMPS = ("observed_at", "identity_verified_at", "submitted_at", "changed_at")

TABLES_EXIST_SQL = (
    "SELECT (to_regclass('cpbl.series_roster') IS NOT NULL"
    " AND to_regclass('cpbl.series_roster_member') IS NOT NULL"
    " AND to_regclass('cpbl.roster_annotation_revision') IS NOT NULL)::text;"
)
ROLE_SCHEMA_SQL = (
    "SELECT (count(*)=3)::text FROM information_schema.columns WHERE table_schema='cpbl' "
    "AND table_name='roster_annotation_revision' AND column_name IN "
    "('role_format_version','tactical_roles','role_provenance');"
)


def _agg(table: str, cols: tuple[str, ...], order: str) -> str:
    return (f"COALESCE((SELECT json_agg(json_build_object({', '.join(f'{c!r}, {c}' for c in cols)})"
            f" ORDER BY {order}) FROM cpbl.{table}), '[]'::json)")


# 三表全量唯讀傾印（單行 JSON）。欄名為本模組常數，無外部輸入。
DUMP_SQL = (
    "SELECT json_build_object("
    f"'rosters', {_agg('series_roster', HEAD_COLUMNS, 'roster_id')}, "
    f"'members', {_agg('series_roster_member', MEMBER_COLUMNS, 'roster_id, player_id')}, "
    f"'revisions', {_agg('roster_annotation_revision', REVISION_COLUMNS, 'roster_id, revision, player_id')}"
    ")::text;"
)


class SyncError(RuntimeError):
    def __init__(self, code: int, message: str, detail: object = None):
        self.code = code
        self.detail = detail
        super().__init__(message)


# ---------------------------------------------------------------- 正規化與自檢


def _ts(v: str | None) -> str | None:
    return None if v is None else datetime.fromisoformat(v).astimezone(UTC).isoformat()


def normalize(dump: dict) -> dict[tuple, dict]:
    """傾印 → {scope: {"head", "members": {pid: row}, "revisions": {rev: {"hash", "changed_at", "roles"}}}}。"""
    by_id: dict[str, dict] = {}
    for h in dump["rosters"]:
        head = {k: h[k] for k in HEAD_COLUMNS}
        for k in _TIMESTAMPS:
            if k in head:
                head[k] = _ts(head[k])
        head["roster_id"] = str(head["roster_id"])
        head["published_date"] = str(head["published_date"])
        by_id[head["roster_id"]] = {"head": head, "members": {}, "revisions": {}}
    for m in dump["members"]:
        by_id[str(m["roster_id"])]["members"][m["player_id"]] = {
            "official_position": m["official_position"], "announced_name": m["announced_name"]}
    for r in dump["revisions"]:
        rev = by_id[str(r["roster_id"])]["revisions"].setdefault(
            int(r["revision"]), {"hash": set(), "changed_at": set(), "roles": {},
                                 "formats": set(), "details": {}})
        rev["hash"].add(r["revision_hash"])
        rev["changed_at"].add(_ts(r["changed_at"]))
        rev["roles"][r["player_id"]] = r["tactical_role"]
        if any(k not in r for k in REVISION_COLUMNS[-3:]):
            raise SyncError(EXIT_SELF_CHECK, "角色傾印缺format／roles／provenance欄")
        rev["formats"].add(r["role_format_version"])
        rev["details"][r["player_id"]] = {k: r[k] for k in REVISION_COLUMNS[-3:]}
    out = {}
    for rec in by_id.values():
        for rev in rec["revisions"].values():
            rev["hash"] = sorted(rev["hash"])
            rev["changed_at"] = sorted(rev["changed_at"])
            rev["formats"] = sorted(rev["formats"])
        h = rec["head"]
        out[(h["year"], h["kind_code"], h["team_code"])] = rec
    return out


def _revision_hash(rec: dict, rev: dict) -> str:
    formats = rev.get("formats", [1])
    if len(formats) != 1 or any(d["role_format_version"] != formats[0]
                                for d in rev.get("details", {}).values()):
        raise ValueError("逐列格式與同版格式不一致")
    if formats == [1]:
        if any(d["tactical_roles"] is not None or d["role_provenance"] is not None
               for d in rev.get("details", {}).values()):
            raise ValueError("v1不可包含v2角色欄")
        return revision_hash(rev["roles"].items())
    if formats != [2] or set(rev.get("details", {})) != set(rev["roles"]):
        raise ValueError("未知或混合角色格式")
    rows = []
    for pid, d in rev["details"].items():
        if rev["roles"][pid] != "unclassified":
            raise ValueError("v2 scalar必須為unclassified相容占位")
        validate_roles_v2(rec["members"][pid]["official_position"],
                          d["tactical_roles"], d["role_provenance"])
        rows.append((pid, d["tactical_roles"], d["role_provenance"]))
    return revision_hash_v2(rows)


def recomputed(rec: dict) -> dict:
    h = rec["head"]
    return {
        "membership_hash": membership_hash(
            h["year"], h["kind_code"], h["team_code"],
            [(m["official_position"], pid) for pid, m in rec["members"].items()]),
        "source_hash": source_hash(
            h["source_url"], h["published_date"], h["published_precision"],
            [(pid, m["announced_name"]) for pid, m in rec["members"].items()]),
        "revisions": {n: _revision_hash(rec, r) for n, r in rec["revisions"].items()},
    }


def self_check(bundle: dict[tuple, dict]) -> list[str]:
    """存值必須等於重算值；每份 32 人、每版 32 列且同一雜湊、版本號連續。"""
    problems = []
    for scope, rec in sorted(bundle.items()):
        label = "/".join(map(str, scope))
        try:
            h, calc = rec["head"], recomputed(rec)
        except (ValueError, KeyError, TypeError) as exc:
            problems.append(f"{label} 角色格式／來源不合法：{exc}")
            continue
        if len(rec["members"]) != ROSTER_SIZE:
            problems.append(f"{label} 會員 {len(rec['members'])} ≠ 32")
        for k in ("membership_hash", "source_hash"):
            if h[k] != calc[k]:
                problems.append(f"{label} {k} 存值 {h[k]} ≠ 重算 {calc[k]}")
        if sorted(rec["revisions"]) != list(range(1, len(rec["revisions"]) + 1)):
            problems.append(f"{label} 角色版本不連續：{sorted(rec['revisions'])}")
        for n, rev in sorted(rec["revisions"].items()):
            if len(rev["roles"]) != ROSTER_SIZE or rev["hash"] != [calc["revisions"][n]]:
                problems.append(f"{label} 角色版本 {n} 列數 {len(rev['roles'])}／存值 {rev['hash']}"
                                f" ≠ 重算 {calc['revisions'][n]}")
    return problems


# ---------------------------------------------------------------- 比對計畫


@dataclass
class Plan:
    insert_rosters: list[tuple] = field(default_factory=list)
    insert_revisions: list[tuple[tuple, int]] = field(default_factory=list)
    skipped: list[tuple] = field(default_factory=list)
    rejects: list[dict] = field(default_factory=list)

    @property
    def state(self) -> str:
        if self.rejects:
            return "reject"
        return "insert-pending" if (self.insert_rosters or self.insert_revisions) else "no-change"


def _rec_diff(local: dict, target: dict) -> dict:
    d: dict = {}
    head = {k: (local["head"][k], target["head"][k]) for k in HEAD_COLUMNS
            if local["head"][k] != target["head"][k]}
    if head:
        d["head"] = {k: {"local": v[0], "target": v[1]} for k, v in head.items()}
    lm, tm = local["members"], target["members"]
    if lm != tm:
        d["members"] = {
            "only_local": sorted(set(lm) - set(tm)), "only_target": sorted(set(tm) - set(lm)),
            "changed": sorted(p for p in set(lm) & set(tm) if lm[p] != tm[p]),
        }
    return d


def plan(local: dict[tuple, dict], target: dict[tuple, dict], *, scopes=None) -> Plan:
    p = Plan()
    for scope in sorted(scopes if scopes is not None else set(local) | set(target)):
        label = "/".join(map(str, scope))
        if scopes is not None and (scope not in local or scope not in target):
            p.rejects.append({"scope": label, "reason": "scoped角色同步只允許兩端既有名單，不新增會員"})
            continue
        if scope not in local:
            p.rejects.append({"scope": label, "reason": "目標有本機沒有的名單（異常，拒絕）",
                              "target_roster_id": target[scope]["head"]["roster_id"]})
            continue
        if scope not in target:
            p.insert_rosters.append(scope)
            continue
        lrec, trec = local[scope], target[scope]
        diff = _rec_diff(lrec, trec)
        if diff:
            p.rejects.append({"scope": label, "reason": "同 scope 內容不同（拒絕，不覆寫）", "diff": diff})
            continue
        bad = False
        for n in sorted(set(lrec["revisions"]) | set(trec["revisions"])):
            if n not in lrec["revisions"]:
                p.rejects.append({"scope": label, "reason": f"目標有本機沒有的角色版本 {n}"})
                bad = True
            elif n not in trec["revisions"]:
                p.insert_revisions.append((scope, n))
            elif lrec["revisions"][n] != trec["revisions"][n]:
                p.rejects.append({"scope": label, "reason": f"角色版本 {n} 內容不同（拒絕）",
                                  "local": lrec["revisions"][n]["hash"],
                                  "target": trec["revisions"][n]["hash"]})
                bad = True
        if not bad and not any(s == scope for s, _ in p.insert_revisions):
            p.skipped.append(scope)
    return p


# ---------------------------------------------------------------- payload


def _copy_escape(s: str) -> str:
    return (s.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r")
            .replace("\t", "\\t"))


def payload(local: dict[tuple, dict], p: Plan, *, scopes=None) -> dict:
    rosters, members, revisions = [], [], []
    for scope in p.insert_rosters:
        rec = local[scope]
        rid = rec["head"]["roster_id"]
        rosters.append(rec["head"])
        members += [{"roster_id": rid, "player_id": pid, **m} for pid, m in sorted(rec["members"].items())]
        for n in sorted(rec["revisions"]):
            revisions += _revision_rows(rid, n, rec["revisions"][n])
    for scope, n in p.insert_revisions:
        rec = local[scope]
        revisions += _revision_rows(rec["head"]["roster_id"], n, rec["revisions"][n])
    doc = {"rosters": rosters, "members": members, "revisions": revisions}
    if scopes is not None:
        doc["scopes"] = [{"year": y, "kind_code": k, "team_code": t} for y, k, t in sorted(scopes)]
    return doc


def _revision_rows(rid: str, n: int, rev: dict) -> list[dict]:
    (h,) = rev["hash"]
    (changed,) = rev["changed_at"] if len(rev["changed_at"]) == 1 else (None,)
    if changed is None:
        raise SyncError(EXIT_SELF_CHECK, f"{rid} 角色版本 {n} 的 changed_at 不一致")
    return [{"roster_id": rid, "revision": n, "player_id": pid, "tactical_role": role,
             "revision_hash": h, "changed_at": changed,
             **rev.get("details", {}).get(pid, {"role_format_version": 1, "tactical_roles": None,
                                               "role_provenance": None})}
            for pid, role in sorted(rev["roles"].items())]


def apply_script(doc: dict) -> str:
    """單一交易的 psql 腳本（⛔ 無 UPDATE／DELETE／ON CONFLICT DO UPDATE）。

    資料以 COPY 文字格式送進 temp 表（單行 JSON），不拼進 SQL 文字。
    """
    line = _copy_escape(json.dumps(doc, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    heads = ", ".join(HEAD_COLUMNS)
    mems = ", ".join(MEMBER_COLUMNS)
    revs = ", ".join(REVISION_COLUMNS)
    return f"""\\set QUIET on
\\set ON_ERROR_STOP on
\\pset tuples_only on
\\pset format unaligned
BEGIN;
CREATE TEMP TABLE _roster_sync_payload (doc jsonb NOT NULL) ON COMMIT DROP;
COPY _roster_sync_payload (doc) FROM STDIN;
{line}
\\.
CREATE TEMP TABLE _rs_head ON COMMIT DROP AS
  SELECT * FROM jsonb_populate_recordset(NULL::cpbl.series_roster,
                                         (SELECT doc->'rosters' FROM _roster_sync_payload));
CREATE TEMP TABLE _rs_member ON COMMIT DROP AS
  SELECT * FROM jsonb_populate_recordset(NULL::cpbl.series_roster_member,
                                         (SELECT doc->'members' FROM _roster_sync_payload));
CREATE TEMP TABLE _rs_revision ON COMMIT DROP AS
  SELECT * FROM jsonb_populate_recordset(NULL::cpbl.roster_annotation_revision,
                                         (SELECT doc->'revisions' FROM _roster_sync_payload));
DO $roster_sync$
DECLARE bad text;
BEGIN
  IF (SELECT doc ? 'scopes' FROM _roster_sync_payload) THEN
    IF (SELECT jsonb_array_length(doc->'scopes') FROM _roster_sync_payload) <> 2
       OR EXISTS (SELECT 1 FROM _rs_head) OR EXISTS (SELECT 1 FROM _rs_member) THEN
      RAISE EXCEPTION 'ROSTER_SYNC_SCOPE scoped模式須兩隊既有名單且只能新增角色版本';
    END IF;
    IF (SELECT count(DISTINCT s) FROM _roster_sync_payload p,
        jsonb_to_recordset(p.doc->'scopes') AS s(year integer,kind_code text,team_code text)) <> 2
       OR (SELECT count(*) FROM cpbl.series_roster r WHERE EXISTS (
         SELECT 1 FROM _roster_sync_payload p, jsonb_to_recordset(p.doc->'scopes')
           AS s(year integer,kind_code text,team_code text)
          WHERE (s.year,s.kind_code,s.team_code)=(r.year,r.kind_code,r.team_code))) <> 2 THEN
      RAISE EXCEPTION 'ROSTER_SYNC_SCOPE allowlist須為兩份不同的既有名單';
    END IF;
    IF EXISTS (
      SELECT 1 FROM _rs_revision v LEFT JOIN cpbl.series_roster r USING (roster_id)
       WHERE r.roster_id IS NULL OR NOT EXISTS (
         SELECT 1 FROM _roster_sync_payload p, jsonb_to_recordset(p.doc->'scopes')
           AS s(year integer, kind_code text, team_code text)
          WHERE (s.year,s.kind_code,s.team_code)=(r.year,r.kind_code,r.team_code))
    ) THEN RAISE EXCEPTION 'ROSTER_SYNC_SCOPE payload包含allowlist外名單'; END IF;
  END IF;
  SELECT string_agg(format('%s/%s/%s', s.year, s.kind_code, s.team_code), ', ') INTO bad
    FROM _rs_head h JOIN cpbl.series_roster s
      ON s.year = h.year AND s.kind_code = h.kind_code AND s.team_code = h.team_code;
  IF bad IS NOT NULL THEN
    RAISE EXCEPTION 'ROSTER_SYNC_CONFLICT 比對後目標已出現同 scope 名單：%', bad;
  END IF;
  SELECT string_agg(format('%s#%s', v.roster_id, v.revision), ', ') INTO bad
    FROM (SELECT DISTINCT roster_id, revision FROM _rs_revision) v
    JOIN (SELECT DISTINCT roster_id, revision FROM cpbl.roster_annotation_revision) t
      USING (roster_id, revision);
  IF bad IS NOT NULL THEN
    RAISE EXCEPTION 'ROSTER_SYNC_CONFLICT 比對後目標已出現同角色版本：%', bad;
  END IF;
END
$roster_sync$;
INSERT INTO cpbl.series_roster ({heads})
  SELECT {heads} FROM _rs_head h
   WHERE NOT EXISTS (SELECT 1 FROM cpbl.series_roster s WHERE s.roster_id = h.roster_id);
INSERT INTO cpbl.series_roster_member ({mems})
  SELECT {mems} FROM _rs_member m
   WHERE NOT EXISTS (SELECT 1 FROM cpbl.series_roster_member t
                      WHERE t.roster_id = m.roster_id AND t.player_id = m.player_id);
INSERT INTO cpbl.roster_annotation_revision ({revs})
  SELECT {revs} FROM _rs_revision v
   WHERE NOT EXISTS (SELECT 1 FROM cpbl.roster_annotation_revision t
                      WHERE t.roster_id = v.roster_id AND t.revision = v.revision
                        AND t.player_id = v.player_id);
SELECT 'ROSTER_SYNC_STAGED ' || (SELECT count(*) FROM _rs_head) || ' ' || (SELECT count(*) FROM _rs_member)
       || ' ' || (SELECT count(*) FROM _rs_revision);
COMMIT;
"""


# ---------------------------------------------------------------- 傳輸


class PsqlTarget:
    """以 psql 讀 stdin 腳本的目標（docker exec／ssh 皆可）；不經 shell 解讀。"""

    def __init__(self, command: str | list[str]):
        self.argv = shlex.split(command) if isinstance(command, str) else list(command)

    def run(self, script: str) -> str:
        proc = subprocess.run(self.argv, input=script, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise SyncError(EXIT_TARGET, f"目標指令失敗 rc={proc.returncode}：{proc.stderr.strip()}")
        return proc.stdout

    def read(self, sql: str) -> str:
        script = ("\\set QUIET on\n\\set ON_ERROR_STOP on\n\\pset tuples_only on\n"
                  "\\pset format unaligned\nBEGIN TRANSACTION READ ONLY;\n" + sql + "\nCOMMIT;\n")
        out = self.run(script).strip()  # QUIET＋tuples_only：stdout 只有查詢結果本身
        if not out:
            raise SyncError(EXIT_TARGET, "目標沒有回傳任何列")
        return out


def read_target(target) -> dict[tuple, dict]:
    if target.read(TABLES_EXIST_SQL).strip() != "true":
        raise SyncError(EXIT_NO_TABLE, "目標尚無名單表（待部署窗口套用 schema；本同步不 migrate）")
    if target.read(ROLE_SCHEMA_SQL).strip() != "true":
        raise SyncError(EXIT_NO_TABLE, "目標尚無角色v2欄（待部署窗口；本同步不migrate）")
    return normalize(json.loads(target.read(DUMP_SQL)))


def read_local(source) -> dict[tuple, dict]:
    if source.read(TABLES_EXIST_SQL).strip() != "true":
        raise SyncError(EXIT_SELF_CHECK, "本機尚無名單表")
    if source.read(ROLE_SCHEMA_SQL).strip() != "true":
        raise SyncError(EXIT_SELF_CHECK, "本機尚無角色v2欄")
    return normalize(json.loads(source.read(DUMP_SQL)))


# ---------------------------------------------------------------- 對帳


def reconcile(local: dict[tuple, dict], target: dict[tuple, dict]) -> tuple[bool, list[dict]]:
    ok = True
    rows = []
    for scope in sorted(set(local) | set(target)):
        lrec, trec = local.get(scope), target.get(scope)
        lcalc = recomputed(lrec) if lrec else None
        tcalc = recomputed(trec) if trec else None
        row = {
            "scope": "/".join(map(str, scope)),
            "roster_id_local": lrec and lrec["head"]["roster_id"],
            "roster_id_target": trec and trec["head"]["roster_id"],
            "membership_local": lrec and lrec["head"]["membership_hash"],
            "membership_target": trec and trec["head"]["membership_hash"],
            "membership_target_recomputed": tcalc and tcalc["membership_hash"],
            "source_local": lrec and lrec["head"]["source_hash"],
            "source_target": trec and trec["head"]["source_hash"],
            "source_target_recomputed": tcalc and tcalc["source_hash"],
            "revisions_local": lrec and len(lrec["revisions"]),
            "revisions_target": trec and len(trec["revisions"]),
        }
        row["equal"] = bool(
            lrec and trec and not _rec_diff(lrec, trec) and lrec["revisions"] == trec["revisions"]
            and tcalc["membership_hash"] == trec["head"]["membership_hash"]
            and tcalc["source_hash"] == trec["head"]["source_hash"]
            and lcalc["revisions"] == tcalc["revisions"]
        )
        ok &= row["equal"]
        rows.append(row)
    return ok, rows


def _print_table(rows: list[dict]) -> None:
    print("scope｜roster_id｜membership 本機/目標(重算)｜source 本機/目標(重算)｜角色版數 本機/目標｜一致")
    for r in rows:
        def s(v):
            return (v or "—")[:12]
        print(f"{r['scope']}｜{r['roster_id_local'] or '—'}｜{s(r['membership_local'])}/"
              f"{s(r['membership_target'])}({s(r['membership_target_recomputed'])})｜"
              f"{s(r['source_local'])}/{s(r['source_target'])}({s(r['source_target_recomputed'])})｜"
              f"{r['revisions_local']}/{r['revisions_target']}｜{'✓' if r['equal'] else '✗'}")


# ---------------------------------------------------------------- 入口


def _local_checked(source) -> dict[tuple, dict]:
    local = read_local(source)
    problems = self_check(local)
    if problems:
        raise SyncError(EXIT_SELF_CHECK, "本機自檢失敗：" + "；".join(problems))
    return local


def run_plan(source, target, *, scopes=None) -> tuple[dict, dict, Plan]:
    local = _local_checked(source)
    _require_v2_scopes(local, scopes)
    remote = read_target(target)
    return local, remote, plan(local, remote, scopes=scopes)


def run_apply(source, target, *, scopes=None) -> tuple[Plan, bool, list[dict]]:
    local, _, p = run_plan(source, target, scopes=scopes)
    if p.state == "reject":
        raise SyncError(EXIT_REJECT, "內容不同，拒絕同步（不寫入、不重試）", p.rejects)
    if p.state == "insert-pending":
        out = target.run(apply_script(payload(local, p, scopes=scopes)))
        if "ROSTER_SYNC_STAGED" not in out:
            raise SyncError(EXIT_TARGET, f"目標未回報寫入結果：{out!r}")
    remote = read_target(target)
    ok, rows = reconcile(_scoped(local, scopes), _scoped(remote, scopes))
    return p, ok, rows


def _scoped(bundle, scopes):
    if scopes is not None and any(s not in bundle for s in scopes):
        raise SyncError(EXIT_RECONCILE, "對帳缺少allowlist指定的既有名單，不能把空集合當一致")
    return bundle if scopes is None else {s: r for s, r in bundle.items() if s in scopes}


def _require_v2_scopes(bundle, scopes):
    if scopes is None and any(2 in r.get("formats", [])
                              for rec in bundle.values() for r in rec["revisions"].values()):
        raise SyncError(EXIT_SELF_CHECK, "含v2歷史時必須明確提供兩隊--scope，禁止未限範圍同步")


def parse_scopes(values):
    if not values:
        return None
    scopes = []
    for value in values:
        if not re.fullmatch(r"(?:19|20)[0-9]{2}:[EC]:[A-Z0-9]{6}", value):
            raise ValueError("scope須為YYYY:E或C:TEAM_CODE")
        y, k, team = value.split(":")
        scopes.append((int(y), k, team))
    if len(scopes) != 2 or len(set(scopes)) != 2:
        raise ValueError("scoped同步須明確指定兩個不同scope")
    return tuple(sorted(scopes))


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m cpbl.rosters.sync", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 allow_abbrev=False)
    ap.add_argument("action", choices=("plan", "apply", "reconcile"))
    ap.add_argument("--local-psql", required=True,
                    help="本機來源庫的 psql 指令（唯讀；shlex 切分，不經 shell）")
    ap.add_argument("--target-psql", required=True,
                    help="讀 stdin 腳本的 psql 指令（shlex 切分，不經 shell）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--scope", action="append", default=[], metavar="YEAR:KIND:TEAM",
                    help="只追加兩個既有名單scope的角色版本；每隊各給一次")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    source = PsqlTarget(args.local_psql)
    target = PsqlTarget(args.target_psql)
    try:
        scopes = parse_scopes(args.scope)
        if args.action == "plan":
            _, _, p = run_plan(source, target, scopes=scopes)
            if p.state == "reject":
                raise SyncError(EXIT_REJECT, "內容不同，拒絕同步（不寫入、不重試）", p.rejects)
            print(f"insert_rosters={['/'.join(map(str, s)) for s in p.insert_rosters]}")
            print(f"insert_revisions={[('/'.join(map(str, s)), n) for s, n in p.insert_revisions]}")
            print(f"skipped={['/'.join(map(str, s)) for s in p.skipped]}")
            print(f"ROSTER_SYNC_PLAN={p.state}")
            return 0
        if args.action == "apply":
            p, ok, rows = run_apply(source, target, scopes=scopes)
            print(f"ROSTER_SYNC_PLAN={p.state}" + ("（無變更，未寫入）" if p.state == "no-change" else ""))
        else:
            local = _local_checked(source)
            _require_v2_scopes(local, scopes)
            ok, rows = reconcile(_scoped(local, scopes), _scoped(read_target(target), scopes))
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            _print_table(rows)
        if not ok:
            raise SyncError(EXIT_RECONCILE, "事後對帳不等（已寫入列保留，不刪）")
        print("ROSTER_SYNC_RECONCILE=ok")
        return 0
    except SyncError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        if exc.detail:
            print(json.dumps(exc.detail, ensure_ascii=False, indent=2, default=str), file=sys.stderr)
        return exc.code
    except (ValueError, KeyError, TypeError) as exc:
        print(f"✗ 角色格式／scope錯誤：{exc}", file=sys.stderr)
        return EXIT_SELF_CHECK


if __name__ == "__main__":
    sys.exit(main())
