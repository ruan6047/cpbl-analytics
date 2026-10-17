"""兩隊多重角色預覽／原子追加／完整版本還原；呼叫端用db.conn管理交易。"""

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from cpbl.rosters.canonical import membership_hash, revision_hash, revision_hash_v2, source_hash
from cpbl.rosters.role_package import parse_package
from cpbl.rosters.store import EXIT_ANNOTATE, EXIT_RACE, RosterError


def _check_team(cur, package, team):
    head = cur.execute(
        "SELECT roster_id,year,kind_code,team_code,membership_hash,source_hash,source_url,"
        "published_date,published_precision FROM cpbl.series_roster WHERE roster_id=%s",
        (team["roster_id"],)).fetchone()
    if head is None or (head["year"], head["kind_code"], head["team_code"]) != (
            package["year"], package["kind_code"], team["team_code"]):
        raise RosterError(EXIT_ANNOTATE, "package scope與已提交名單不符")
    members = cur.execute(
        "SELECT player_id,official_position,announced_name FROM cpbl.series_roster_member "
        "WHERE roster_id=%s ORDER BY player_id", (team["roster_id"],)).fetchall()
    wanted = sorted([{k: m[k] for k in ("player_id", "official_position", "announced_name")}
                     for m in team["members"]], key=lambda m: m["player_id"])
    if members != wanted:
        raise RosterError(EXIT_ANNOTATE, "package會員ID／公告姓名／官方守位與已提交會員不同")
    mh = membership_hash(package["year"], package["kind_code"], team["team_code"],
                         [(m["official_position"], m["player_id"]) for m in members])
    sh = source_hash(head["source_url"], str(head["published_date"]), head["published_precision"],
                     [(m["player_id"], m["announced_name"]) for m in members])
    if any(head[k] != team[k] or head[k] != value for k, value in (
            ("membership_hash", mh), ("source_hash", sh))):
        raise RosterError(EXIT_ANNOTATE, "會員／來源hash與package或實際會員不符")
    latest = cur.execute(
        "SELECT revision,revision_hash FROM cpbl.roster_annotation_revision "
        "WHERE roster_id=%s ORDER BY revision DESC LIMIT 1", (team["roster_id"],)).fetchone()
    return latest


def _expected(team, latest, desired_hash):
    if latest["revision_hash"] == desired_hash:
        return "unchanged"
    if (latest["revision"], latest["revision_hash"]) != (
            team["expected_latest_revision"], team["expected_latest_hash"]):
        raise RosterError(EXIT_RACE, "角色基準已變更；拒絕套用，請核對預覽")
    return "revised"


def preview_package(c, doc):
    package = parse_package(doc)
    results = []
    with c.cursor(row_factory=dict_row) as cur:
        for team in package["teams"]:
            latest = _check_team(cur, package, team)
            results.append({"roster_id": team["roster_id"], "team_code": team["team_code"],
                            "status": _expected(team, latest, team["revision_hash"]),
                            "latest_revision": latest["revision"],
                            "latest_hash": latest["revision_hash"],
                            "revision_hash": team["revision_hash"], "member_count": 32})
    return {"format": package["format"], "approval": package["approval"], "teams": results}


def _append(cur, rid, revision, rows, h):
    cur.executemany(
        "INSERT INTO cpbl.roster_annotation_revision "
        "(roster_id,revision,player_id,tactical_role,revision_hash,role_format_version,"
        "tactical_roles,role_provenance) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        [(rid, revision, r["player_id"], r["tactical_role"], h, r["role_format_version"],
          r["tactical_roles"], Jsonb(r["role_provenance"]) if r["role_provenance"] is not None else None)
         for r in rows])


def annotate_package(c, doc, confirm_approval_hash, restore_versions=None):
    """一次鎖兩隊並在同一交易追加；restore只複製既有完整版本，不刪歷史。"""
    package = parse_package(doc)
    if confirm_approval_hash != package["approval"]["approval_table_sha256"]:
        raise RosterError(EXIT_ANNOTATE, "核准表hash確認不符")
    if restore_versions is not None and (set(restore_versions) != {
            t["roster_id"] for t in package["teams"]} or any(
                type(v) is not int or v < 1 for v in restore_versions.values())):
        raise RosterError(EXIT_ANNOTATE, "restore須明確指定兩隊既有完整版本")
    results = []
    with c.transaction(), c.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT roster_id FROM cpbl.series_roster WHERE roster_id=ANY(%s::uuid[]) "
                    "ORDER BY roster_id FOR UPDATE", ([t["roster_id"] for t in package["teams"]],))
        for team in package["teams"]:
            latest = _check_team(cur, package, team)
            rows = [{**m, "tactical_role": "unclassified", "role_format_version": 2}
                    for m in team["members"]]
            h = team["revision_hash"]
            if restore_versions is not None:
                rows = cur.execute(
                    "SELECT player_id,tactical_role,role_format_version,tactical_roles,role_provenance,"
                    "revision_hash FROM cpbl.roster_annotation_revision WHERE roster_id=%s AND revision=%s "
                    "ORDER BY player_id", (team["roster_id"], restore_versions[team["roster_id"]])).fetchall()
                if len(rows) != 32 or len({r["role_format_version"] for r in rows}) != 1:
                    raise RosterError(EXIT_ANNOTATE, "restore版本不存在或不完整")
                fmt = rows[0]["role_format_version"]
                if fmt == 1:
                    h = revision_hash([(r["player_id"], r["tactical_role"]) for r in rows])
                elif fmt == 2:
                    h = revision_hash_v2([(r["player_id"], r["tactical_roles"], r["role_provenance"])
                                          for r in rows])
                else:
                    raise RosterError(EXIT_ANNOTATE, "restore遇到未知角色格式")
                if {r["revision_hash"] for r in rows} != {h}:
                    raise RosterError(EXIT_ANNOTATE, "restore來源hash驗證失敗")
            status = _expected(team, latest, h)
            revision = latest["revision"] if status == "unchanged" else latest["revision"] + 1
            if status == "revised":
                _append(cur, team["roster_id"], revision, rows, h)
            results.append({"roster_id": team["roster_id"], "team_code": team["team_code"],
                            "status": status, "annotation_version": revision, "revision_hash": h})
    return {"teams": results}
