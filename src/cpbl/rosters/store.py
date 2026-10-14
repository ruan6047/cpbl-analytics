"""名單的預覽、提交、角色修訂與唯讀摘要（DB 讀寫，皆參數化、皆走 cpbl.db.conn()）。

- submit：單交易 `INSERT … ON CONFLICT (year, kind_code, team_code) DO NOTHING RETURNING`。
  有回傳＝寫 32 會員＋角色版本 1；無回傳＝改讀既有列比雙雜湊：相同回原 roster_id（冪等，
  不重寫、不重算提交時間），不同拒絕並列差異。競爭提交由 DB 唯一約束保證至多一個成功。
- annotate：會員與來源須與已提交名單完全相同；角色與最新版相同＝冪等，不同＝寫 revision n+1。
  ⛔ 不觸碰 series_roster／series_roster_member（membership_hash、submitted_at 不變）。
- show：唯讀交易；成績以 LEFT JOIN 取得，無列＝None（呈現「無」），⛔ 不當 0。
  ⛔ 本模組的讀取函式只供 CLI，不是 S05/S08 的讀取契約（#284 T3）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from cpbl.rosters.canonical import (
    HASH_VERSION,
    POSITION_ORDER,
    membership_hash,
    revision_hash,
    source_hash,
)
from cpbl.rosters.identity import Prepared, check, load_context
from cpbl.rosters.parser import ParsedRoster

ELIGIBILITY_NOTE = "資格名單：不代表先發、當場 28 人登錄或可用"


class RosterError(RuntimeError):
    """可預期的拒絕（附 CLI 退出碼與差異）。"""

    def __init__(self, code: int, message: str, detail: dict | None = None):
        self.code = code
        self.detail = detail or {}
        super().__init__(message)


# CLI 退出碼（寫進 --help）
EXIT_SYNTAX = 10
EXIT_DRAFT = 11
EXIT_VIOLATION = 12
EXIT_CONFLICT = 13
EXIT_CONFIRM = 14
EXIT_ANNOTATE = 15
EXIT_RACE = 16


@dataclass(frozen=True)
class Origin:
    """名單來源 metadata（pasted_text＝CLI 實收；official_population_v1＝已核記錄遷入）。"""

    input_origin: str
    observed_at: datetime
    observation_basis: str
    identity_verified_at: datetime | None  # None＝提交當下（人工以 --confirm-hash 確認的時刻）


def pasted_origin(observed_at: datetime | None = None) -> Origin:
    return Origin("pasted_text", observed_at or datetime.now(UTC), "cli_input", None)


# ---------------------------------------------------------------- 雜湊與差異


def hashes(prep: Prepared) -> dict[str, str] | None:
    """全部身分已解析才有雜湊（未解析的列沒有 ID 可算）。"""
    if prep.unresolved:
        return None
    p = prep.parsed
    return {
        "membership_hash": membership_hash(
            p.year, p.kind_code, p.team_code, [(r.entry.position, r.player_id) for r in prep.rows]
        ),
        "source_hash": source_hash(
            p.source_url, p.published_date.isoformat(), "date",
            [(r.player_id, r.entry.name) for r in prep.rows],
        ),
        "revision_hash": revision_hash([(r.player_id, r.role) for r in prep.rows]),
    }


def _diff(existing: dict, prep: Prepared) -> dict:
    p = prep.parsed
    old = {m["player_id"]: m for m in existing["members"]}
    new = {r.player_id: r for r in prep.rows if r.player_id}
    d: dict = {
        "added_ids": sorted(set(new) - set(old)),
        "removed_ids": sorted(set(old) - set(new)),
        "position_changes": [
            {"player_id": pid, "submitted": old[pid]["official_position"], "input": new[pid].entry.position}
            for pid in sorted(set(old) & set(new))
            if old[pid]["official_position"] != new[pid].entry.position
        ],
        "announced_name_changes": [
            {"player_id": pid, "submitted": old[pid]["announced_name"], "input": new[pid].entry.name}
            for pid in sorted(set(old) & set(new))
            if old[pid]["announced_name"] != new[pid].entry.name
        ],
        "source_changes": {},
    }
    for key, value in (("source_url", p.source_url),
                       ("published_date", p.published_date.isoformat())):
        if str(existing[key]) != value:
            d["source_changes"][key] = {"submitted": str(existing[key]), "input": value}
    return d


# ---------------------------------------------------------------- 讀取


def read_roster(cur, year: int, kind_code: str, team_code: str,
                annotation_version: int | None = None) -> dict | None:
    """讀一份名單（頭＋32 會員＋指定或最新角色版＋本季 A 出賽數 LEFT JOIN）。"""
    cur.row_factory = dict_row
    head = cur.execute(
        "SELECT * FROM cpbl.series_roster WHERE year = %s AND kind_code = %s AND team_code = %s",
        (year, kind_code, team_code),
    ).fetchone()
    if head is None:
        return None
    versions = [r["revision"] for r in cur.execute(
        "SELECT DISTINCT revision FROM cpbl.roster_annotation_revision WHERE roster_id = %s "
        "ORDER BY revision", (head["roster_id"],)).fetchall()]
    version = versions[-1] if annotation_version is None else annotation_version
    if version not in versions:
        raise RosterError(EXIT_ANNOTATE, f"角色版本 {version} 不存在（現有 {versions}）")
    members = cur.execute(
        """
        SELECT m.player_id, m.official_position, m.announced_name, p.name AS master_name,
               a.tactical_role, a.revision_hash, a.changed_at, g.a_games
          FROM cpbl.series_roster_member m
          LEFT JOIN cpbl.players p ON p.id = m.player_id
          LEFT JOIN cpbl.roster_annotation_revision a
                 ON a.roster_id = m.roster_id AND a.player_id = m.player_id AND a.revision = %(v)s
          LEFT JOIN (
                SELECT acnt, count(DISTINCT game_sno) AS a_games FROM (
                    SELECT hitter_acnt AS acnt, game_sno FROM cpbl.batting_gamelog
                     WHERE year = %(y)s AND kind_code = 'A'
                    UNION ALL
                    SELECT pitcher_acnt, game_sno FROM cpbl.pitching_gamelog
                     WHERE year = %(y)s AND kind_code = 'A'
                ) u GROUP BY acnt
          ) g ON g.acnt = m.player_id
         WHERE m.roster_id = %(r)s
        """,
        {"v": version, "y": year, "r": head["roster_id"]},
    ).fetchall()
    members.sort(key=lambda m: (POSITION_ORDER[m["official_position"]], m["player_id"]))
    return {"head": head, "members": members, "annotation_version": version,
            "annotation_versions": versions, "note": ELIGIBILITY_NOTE}


def _existing_core(cur, year: int, kind_code: str, team_code: str) -> dict | None:
    cur.row_factory = dict_row
    head = cur.execute(
        "SELECT roster_id, membership_hash, source_hash, submitted_at, source_url, published_date "
        "FROM cpbl.series_roster WHERE year = %s AND kind_code = %s AND team_code = %s",
        (year, kind_code, team_code),
    ).fetchone()
    if head is None:
        return None
    head["members"] = cur.execute(
        "SELECT player_id, official_position, announced_name FROM cpbl.series_roster_member "
        "WHERE roster_id = %s", (head["roster_id"],)).fetchall()
    latest = cur.execute(
        "SELECT revision, revision_hash FROM cpbl.roster_annotation_revision WHERE roster_id = %s "
        "ORDER BY revision DESC LIMIT 1", (head["roster_id"],)).fetchone()
    head["latest_revision"] = latest
    return head


# ---------------------------------------------------------------- 預覽


def prepare(c, parsed: ParsedRoster) -> tuple[Prepared, dict | None, dict | None]:
    """預覽：身分解析＋規則檢查＋與已提交名單比對。回傳 (prepared, hashes, existing_verdict)。"""
    with c.cursor() as cur:
        ctx = load_context(
            cur, parsed.year, parsed.team_code,
            [e.explicit_id for e in parsed.entries if e.explicit_id],
            [e.name for e in parsed.entries],
        )
        prep = check(parsed, ctx)
        h = hashes(prep)
        verdict = None
        if h is not None:
            existing = _existing_core(cur, parsed.year, parsed.kind_code, parsed.team_code)
            if existing is not None:
                same = (existing["membership_hash"] == h["membership_hash"]
                        and existing["source_hash"] == h["source_hash"])
                verdict = {
                    "roster_id": str(existing["roster_id"]),
                    "submitted_at": existing["submitted_at"].isoformat(),
                    "status": "idempotent" if same else "conflict",
                    "diff": None if same else _diff(existing, prep),
                    "roles_differ_from_latest": (
                        existing["latest_revision"]["revision_hash"] != h["revision_hash"]),
                }
    return prep, h, verdict


# ---------------------------------------------------------------- 提交


def submit(c, parsed: ParsedRoster, confirm_hash: str, origin: Origin) -> dict:
    """單交易原子提交；呼叫端負責 commit／rollback（cpbl.db.conn() 自動處理）。"""
    prep, h, _ = prepare(c, parsed)
    if prep.status == "draft":
        raise RosterError(EXIT_DRAFT, "身分未解析，停在草稿，不能提交")
    if prep.status == "violation":
        raise RosterError(EXIT_VIOLATION, "規則違反，不能提交：" + "；".join(prep.violations))
    if confirm_hash != h["membership_hash"]:
        raise RosterError(EXIT_CONFIRM, "--confirm-hash 與本次預覽的 membership_hash 不符；"
                                        "請重跑 preview 人工核對後帶入")
    p = prep.parsed
    roster_id = uuid.uuid4()
    with c.cursor() as cur:
        created = cur.execute(
            """
            INSERT INTO cpbl.series_roster (
                roster_id, year, kind_code, team_code, source_url, published_date,
                published_precision, observed_at, observation_basis, identity_verified_at,
                input_origin, raw_text, hash_version, membership_hash, source_hash, import_check)
            VALUES (%s, %s, %s, %s, %s, %s, 'date', %s, %s, COALESCE(%s, now()), %s, %s, %s, %s, %s, %s)
            ON CONFLICT (year, kind_code, team_code) DO NOTHING
            RETURNING roster_id, submitted_at
            """,
            (roster_id, p.year, p.kind_code, p.team_code, p.source_url, p.published_date,
             origin.observed_at, origin.observation_basis, origin.identity_verified_at,
             origin.input_origin, p.raw_text, HASH_VERSION, h["membership_hash"],
             h["source_hash"], Jsonb(prep.import_check)),
        ).fetchone()
        if created is not None:
            cur.executemany(
                "INSERT INTO cpbl.series_roster_member (roster_id, player_id, official_position, "
                "announced_name) VALUES (%s, %s, %s, %s)",
                [(roster_id, r.player_id, r.entry.position, r.entry.name) for r in prep.rows],
            )
            cur.executemany(
                "INSERT INTO cpbl.roster_annotation_revision (roster_id, revision, player_id, "
                "tactical_role, revision_hash) VALUES (%s, 1, %s, %s, %s)",
                [(roster_id, r.player_id, r.role, h["revision_hash"]) for r in prep.rows],
            )
            return {"status": "created", "roster_id": str(created[0]),
                    "submitted_at": created[1].isoformat(), **_public(h)}
        # 衝突：唯一鍵已被（可能是剛剛競爭的）另一個提交占用 → 新敘述讀已提交列比對。
        existing = _existing_core(cur, p.year, p.kind_code, p.team_code)
    if (existing["membership_hash"] == h["membership_hash"]
            and existing["source_hash"] == h["source_hash"]):
        out = {"status": "idempotent", "roster_id": str(existing["roster_id"]),
               "submitted_at": existing["submitted_at"].isoformat(), **_public(h)}
        if existing["latest_revision"]["revision_hash"] != h["revision_hash"]:
            out["notice"] = "角色未套用（提交只建立會員；改角色請用 annotate）"
        return out
    raise RosterError(EXIT_CONFLICT, "同一隊同一系列已有不同內容的名單；拒絕，不覆寫",
                      {"roster_id": str(existing["roster_id"]), "diff": _diff(existing, prep)})


def _public(h: dict) -> dict:
    return {"membership_hash": h["membership_hash"], "source_hash": h["source_hash"]}


def annotate(c, parsed: ParsedRoster) -> dict:
    """角色修訂：會員與來源須與已提交名單相同；不同角色寫新版（32 列）。"""
    prep, h, verdict = prepare(c, parsed)
    if prep.status != "ready":
        raise RosterError(EXIT_DRAFT if prep.status == "draft" else EXIT_VIOLATION,
                          "輸入未通過預覽檢查：" + "；".join(prep.violations or ["身分未解析"]))
    if verdict is None:
        raise RosterError(EXIT_ANNOTATE, "尚無已提交名單；先 submit")
    if verdict["status"] != "idempotent":
        raise RosterError(EXIT_ANNOTATE, "會員或來源與已提交名單不同；annotate 只改角色",
                          {"diff": verdict["diff"]})
    with c.cursor() as cur:
        cur.row_factory = dict_row
        latest = cur.execute(
            "SELECT revision, revision_hash FROM cpbl.roster_annotation_revision "
            "WHERE roster_id = %s ORDER BY revision DESC LIMIT 1", (verdict["roster_id"],)
        ).fetchone()
        if latest["revision_hash"] == h["revision_hash"]:
            return {"status": "unchanged", "roster_id": verdict["roster_id"],
                    "annotation_version": latest["revision"]}
        nxt = latest["revision"] + 1
        try:
            with c.transaction():
                cur.executemany(
                    "INSERT INTO cpbl.roster_annotation_revision (roster_id, revision, player_id, "
                    "tactical_role, revision_hash) VALUES (%s, %s, %s, %s, %s)",
                    [(verdict["roster_id"], nxt, r.player_id, r.role, h["revision_hash"])
                     for r in prep.rows],
                )
        except Exception as exc:  # noqa: BLE001 — 只把 PK 衝突轉成可重跑提示
            if getattr(exc, "sqlstate", None) == "23505":
                raise RosterError(EXIT_RACE, f"角色版本 {nxt} 已被同時進行的修訂寫入；請重跑") from exc
            raise
    return {"status": "revised", "roster_id": verdict["roster_id"], "annotation_version": nxt,
            "revision_hash": h["revision_hash"]}
