"""第 3 區 32 人資格名單背景讀取面（#286 S05）：名單、本站角色、出賽 G、官方 PR≥90、A／D 背景。

分兩層（沿 :mod:`cpbl.playoffs.watch_reader` 慣例）：

- :func:`read_roster_inputs`：薄 I/O，呼叫端已開好單一 ``REPEATABLE READ READ ONLY`` 交易；只 SELECT。
  查詢次數與名單人數無關（``ANY`` 批次）：一隊 32 人與兩隊 64 人是同一組查詢。
- :func:`compute_roster`：純組裝，同輸入同輸出。

紅線：

1. GET ⛔ 寫入、⛔ 觸發爬取或重建；⛔ 讀／import ``reports/background``、``reports/assembler``（#272 共享區）。
2. 名單與本站角色只讀 S03 三表（``series_roster``／``series_roster_member``／``roster_annotation_revision``）；
   ⛔ 以出賽紀錄反推名單。名單未提交 ⇒ 該隊 ``missing``、不列球員。
3. 當場 28 人登錄：S11 交付前恆 unknown，⛔ 由 32 人名單或先發推算；說明只走頁尾（需求方 Q4）。
4. 出賽 G＝本季逐場 box（gamelog）去重 ``game_sno``：代跑、守備出場（PA=0）也有列，保留續賽同一場只算一次。
   投手讀投球 box、其餘守位讀打擊 box。與官方季累計 ``*_current.g`` 對帳（規劃 §1：本機 0 不符）。
5. 背景層級：本季一軍 A 有出賽 ⇒ ``A``；沒有但二軍 D 有 ⇒ ``D``（只給傳統計數，⛔ PR／OPS+）；都沒有 ⇒ ``none``。
6. PR≥90 標籤只採官方進階 ``advanced_stats`` 的一軍 A 列，與球員頁同閘門（``ability._ADV_GATE``）、同一組欄；
   官方沒有就不標，⛔ 自行排名。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from cpbl.api.helpers import _dicts
from cpbl.coverage import taipei_date

CONTRACT = "playoffs-roster/v1"
READ_ONLY_TXN = "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"

POSITION_ORDER = {p: i for i, p in enumerate(("投手", "捕手", "內野手", "外野手"))}
#: S03 「未分類」不是角色：呈現為 null（格內「—」）。
UNCLASSIFIED = "unclassified"

#: 球員頁「官方進階・百分位 PR」同一組欄（``web/src/app/players/[id]/lib.ts`` ``ADV``，同順序）；
#: ``brl_pr`` 是 ``brlp_pr`` 的計數重複，球員頁去重不列（season.tsx ``fused``），這裡同樣不列。
PR_COLUMNS = ("ev_pr", "max_ev_pr", "brlp_pr", "hardhitp_pr", "woba_pr", "ba_pr", "iso_pr", "slg_pr",
              "obp_pr", "chasep_pr", "whiffp_pr", "kp_pr", "bbp_pr")
PR_TAG_MIN = 90


def role_of(position: str) -> str:
    """官方守位 → 讀哪一種 box：投手讀投球，其餘讀打擊。"""
    return "pitching" if position == "投手" else "batting"


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


@dataclass
class RosterInputs:
    """一次唯讀交易讀到的全部事實（測試可直接構造）。"""

    year: int
    series: str
    context: dict                                         # S02 compute_series_context 輸出
    rosters: dict[str, dict | None] | None = None         # team → 名單；None ⇒ 來源不可用
    team_names: dict[str, str] = field(default_factory=dict)
    # (player_id, role, kind) → 原始計數（kind ∈ A／D；g＝去重 game_sno）
    counts: dict[tuple[str, str, str], dict] = field(default_factory=dict)
    # (player_id, role) → {pr 欄: 值}（一軍 A、已過閘門）
    advanced: dict[tuple[str, str], dict] = field(default_factory=dict)
    background_cutoff: str | None = None                  # 本季一軍最後一個有 box 的比賽日


# —— 純計算 ——————————————————————————————————————————————————————————


def _r(v: float | None, n: int) -> float | None:
    return None if v is None else round(v, n)


def batting_line(c: dict) -> dict:
    """打擊原始計數 → 率（先加總計數再算；分母 0 ⇒ None）。"""
    ab, h, bb, hbp, sf, tb = (c.get(k) or 0 for k in ("ab", "h", "bb", "hbp", "sf", "tb"))
    den = ab + bb + hbp + sf
    obp = (h + bb + hbp) / den if den else None
    slg = tb / ab if ab else None
    return {
        "pa": c.get("pa") or 0, "ab": ab, "h": h, "hr": c.get("hr") or 0, "bb": bb,
        "avg": _r(h / ab if ab else None, 3), "obp": _r(obp, 3), "slg": _r(slg, 3),
        "ops": _r(obp + slg, 3) if obp is not None and slg is not None else None,
    }


def pitching_line(c: dict) -> dict:
    """投球原始計數（outs）→ 局數字串與 ERA（outs=0 ⇒ ERA None）。"""
    outs, er = c.get("outs") or 0, c.get("er") or 0
    return {
        "outs": outs, "ip": f"{outs // 3}.{outs % 3}", "er": er, "so": c.get("so") or 0, "bb": c.get("bb") or 0,
        "era": _r(er * 27 / outs, 2) if outs else None,
    }


def pr_tags(adv: dict | None) -> list[dict]:
    """官方 PR≥90 的欄（高到低；同值依球員頁欄序）。無官方列 ⇒ 空。"""
    if not adv:
        return []
    tags = [{"key": k, "value": int(adv[k])} for k in PR_COLUMNS
            if adv.get(k) is not None and int(adv[k]) >= PR_TAG_MIN]
    order = {k: i for i, k in enumerate(PR_COLUMNS)}
    return sorted(tags, key=lambda t: (-t["value"], order[t["key"]]))


def background_of(pid: str, role: str, inputs: RosterInputs) -> dict:
    """一名球員的例行賽背景：A 優先；無 A 改 D（只給傳統計數）；都沒有 ⇒ none。"""
    line = batting_line if role == "batting" else pitching_line
    a = inputs.counts.get((pid, role, "A"))
    if a and a.get("g"):
        return {"level": "A", "g": a["g"], "line": line(a), "pr_tags": pr_tags(inputs.advanced.get((pid, role)))}
    d = inputs.counts.get((pid, role, "D"))
    if d and d.get("g"):
        return {"level": "D", "g": d["g"], "line": line(d), "pr_tags": []}
    return {"level": "none", "g": None, "line": None, "pr_tags": []}


def _role(v: str | None) -> str | None:
    return None if v in (None, UNCLASSIFIED) else v


def compute_roster(inputs: RosterInputs, *, now: datetime) -> dict:
    """``playoffs-roster/v1``（JSON-able）。``now`` 只用於 ``as_of``。"""
    ctx = inputs.context
    s = (ctx.get("series") or {}).get(inputs.series)
    sid = s.get("series_id") if s else None
    teams = [t for t in ((sid or {}).get("teams") or []) if t]
    out = {
        "contract": CONTRACT,
        "context_version": ctx.get("context_version"),
        "series_id": sid,
        "series": inputs.series,
        "year": inputs.year,
        "as_of": {
            "now": now.isoformat(),
            "taipei_date": taipei_date(now).isoformat(),
            "last_refresh_at": (ctx.get("as_of") or {}).get("last_refresh_at"),
            "last_completed_game_date": (ctx.get("as_of") or {}).get("last_completed_game_date"),
            "background_cutoff": inputs.background_cutoff,
        },
        "default_scope": "background",
        "scopes": {"background": {"status": "ok"}, "series": {"status": "not_provided"}},
        "registration": {"status": "unknown", "reason": "registration_source_not_delivered"},
        "roster_version": _hash(inputs.rosters),
    }
    missing: list[str] = ["registration_source_not_delivered"]
    if not teams:
        return {**out, "status": "series_unknown", "teams": [], "missing_reason": [*missing, "series_teams_unknown"]}

    team_out = []
    for code in teams:
        roster = None if inputs.rosters is None else inputs.rosters.get(code)
        status = "unavailable" if inputs.rosters is None else "submitted" if roster else "missing"
        if status != "submitted":
            missing.append(f"roster_{status}:{code}")
        members = []
        for m in (roster or {}).get("members", []):
            role = role_of(m["official_position"])
            members.append({
                "player_id": m["player_id"],
                "name": m["announced_name"],
                "official_position": m["official_position"],
                "tactical_role": _role(m.get("tactical_role")),
                "role": role,
                "background": background_of(m["player_id"], role, inputs),
            })
        members.sort(key=lambda x: (POSITION_ORDER.get(x["official_position"], 99), x["player_id"]))
        team_out.append({
            "team_code": code,
            "team_name": inputs.team_names.get(code),
            "roster_status": status,
            "roster": None if not roster else {
                "roster_id": roster["roster_id"], "published_date": roster.get("published_date"),
                "source_url": roster.get("source_url"), "annotation_version": roster.get("annotation_version"),
            },
            "members": members,
        })
    statuses = {t["roster_status"] for t in team_out}
    status = ("unavailable" if "unavailable" in statuses else "ok" if statuses == {"submitted"}
              else "roster_missing" if "submitted" not in statuses else "partial")
    if any(m["background"]["level"] == "none" for t in team_out for m in t["members"]):
        missing.append("background_none")
    return {**out, "status": status, "teams": team_out, "missing_reason": list(dict.fromkeys(missing))}


# —— 讀取（薄 I/O） ————————————————————————————————————————————————————

ROSTER_SQL = """
    SELECT r.team_code, r.roster_id::text AS roster_id, r.published_date, r.source_url,
           lv.rev AS annotation_version, m.player_id, m.announced_name, m.official_position, a.tactical_role
      FROM cpbl.series_roster r
      JOIN cpbl.series_roster_member m ON m.roster_id = r.roster_id
      LEFT JOIN LATERAL (SELECT max(x.revision) AS rev FROM cpbl.roster_annotation_revision x
                          WHERE x.roster_id = r.roster_id) lv ON TRUE
      LEFT JOIN cpbl.roster_annotation_revision a
             ON a.roster_id = r.roster_id AND a.player_id = m.player_id AND a.revision = lv.rev
     WHERE r.year = %(year)s AND r.kind_code = %(kind)s AND r.team_code = ANY(%(teams)s)
     ORDER BY r.team_code, m.player_id
"""

TEAM_NAMES_SQL = "SELECT team_code, short FROM cpbl.team_dim WHERE team_code = ANY(%(teams)s)"

# 出賽 G＝去重 game_sno（保留續賽同一場只算一次）；PA=0 的代跑／守備出場也有列。
BAT_COUNTS_SQL = """
    SELECT b.hitter_acnt AS pid, b.kind_code, count(DISTINCT b.game_sno) AS g,
           sum(b.plate_appearances) AS pa, sum(b.at_bats) AS ab, sum(b.hits) AS h, sum(b.bb) AS bb,
           sum(b.hbp) AS hbp, sum(b.sac_fly) AS sf, sum(b.total_bases) AS tb, sum(b.home_runs) AS hr
      FROM cpbl.batting_gamelog b
     WHERE b.year = %(year)s AND b.kind_code IN ('A', 'D') AND b.hitter_acnt = ANY(%(ids)s)
     GROUP BY 1, 2
"""

PIT_COUNTS_SQL = """
    SELECT p.pitcher_acnt AS pid, p.kind_code, count(DISTINCT p.game_sno) AS g,
           sum(COALESCE(p.inning_pitched_cnt, 0) * 3 + COALESCE(p.inning_pitched_div3, 0)) AS outs,
           sum(p.earned_runs) AS er, sum(p.so) AS so, sum(p.bb) AS bb
      FROM cpbl.pitching_gamelog p
     WHERE p.year = %(year)s AND p.kind_code IN ('A', 'D') AND p.pitcher_acnt = ANY(%(ids)s)
     GROUP BY 1, 2
"""

CUTOFF_SQL = """
    SELECT max(g.game_date) FROM cpbl.games g
     WHERE g.year = %(year)s AND g.kind_code = 'A'
       AND EXISTS (SELECT 1 FROM cpbl.batting_gamelog b
                    WHERE b.year = g.year AND b.kind_code = g.kind_code AND b.game_sno = g.game_sno)
"""


def _adv_sql() -> str:
    from cpbl.api.routers.ability import _ADV_GATE  # 與球員頁／能力卡同一閘門（只 import，不改）

    return (f"SELECT a.acnt, a.role, {', '.join('a.' + c for c in PR_COLUMNS)} FROM cpbl.advanced_stats a "
            f"WHERE a.acnt = ANY(%(ids)s) AND a.year = %(year)s AND a.kind_code = 'A' AND {_ADV_GATE}")


def _optional(cur, fn):
    """名單來源失敗只降級（回 None），以 SAVEPOINT 隔離，不讓交易進入 aborted（同 watch_reader）。"""
    connection = getattr(cur, "connection", None)
    try:
        if connection is not None and hasattr(connection, "transaction"):
            with connection.transaction():
                return fn()
        return fn()
    except Exception:  # noqa: BLE001 — 缺表／權限：該來源 unavailable＋missing_reason
        return None


def read_context(cur, year: int, *, now: datetime, live_reader=None) -> dict:
    """S02 context（與 overview／watch 同一呼叫 ⇒ ``context_version`` 同源可比）。"""
    from cpbl import postseason_contract as contract

    return contract.compute_series_context(
        contract.read_series_inputs(cur, year, now=now, live_reader=live_reader), now=now)


def read_rosters(cur, year: int, series: str, teams: list[str]) -> dict[str, dict | None]:
    cur.execute(ROSTER_SQL, {"year": year, "kind": series, "teams": teams})
    out: dict[str, dict | None] = {t: None for t in teams}
    for r in _dicts(cur):
        ros = out.get(r["team_code"]) or {
            "roster_id": r["roster_id"], "published_date": str(r["published_date"]),
            "source_url": r["source_url"], "annotation_version": r["annotation_version"], "members": []}
        ros["members"].append({"player_id": r["player_id"], "announced_name": r["announced_name"],
                               "official_position": r["official_position"], "tactical_role": r["tactical_role"]})
        out[r["team_code"]] = ros
    return out


def read_background(cur, inputs: RosterInputs) -> None:
    """A／D 計數、官方 PR、背景截止日：每項一次 ``ANY`` 批次（與人數無關）。"""
    members = [m for r in (inputs.rosters or {}).values() if r for m in r["members"]]
    bat = sorted({m["player_id"] for m in members if role_of(m["official_position"]) == "batting"})
    pit = sorted({m["player_id"] for m in members if role_of(m["official_position"]) == "pitching"})
    ids = sorted({*bat, *pit})
    cur.execute(CUTOFF_SQL, {"year": inputs.year})
    row = cur.fetchone()
    inputs.background_cutoff = row[0].isoformat() if row and row[0] else None
    if not ids:
        return
    for role, sql, pids in (("batting", BAT_COUNTS_SQL, bat), ("pitching", PIT_COUNTS_SQL, pit)):
        cur.execute(sql, {"year": inputs.year, "ids": pids})
        for r in _dicts(cur):
            key = (r.pop("pid"), role, r.pop("kind_code"))
            inputs.counts[key] = {k: (int(v) if v is not None else None) for k, v in r.items()}
    cur.execute(_adv_sql(), {"ids": ids, "year": inputs.year})
    for r in _dicts(cur):
        inputs.advanced[(r.pop("acnt"), r.pop("role"))] = r


def read_roster_inputs(cur, year: int, series: str, *, now: datetime, live_reader=None) -> RosterInputs:
    """讀 S02 context＋兩隊名單＋背景；查詢次數與名單人數無關。"""
    ctx = read_context(cur, year, now=now, live_reader=live_reader)
    inputs = RosterInputs(year=year, series=series, context=ctx)
    s = (ctx.get("series") or {}).get(series)
    teams = [t for t in (((s or {}).get("series_id") or {}).get("teams") or []) if t]
    if not teams:
        return inputs
    inputs.rosters = _optional(cur, lambda: read_rosters(cur, year, series, teams))
    cur.execute(TEAM_NAMES_SQL, {"teams": teams})
    inputs.team_names = {r[0]: r[1] for r in cur.fetchall()}
    read_background(cur, inputs)
    return inputs


def playoffs_roster(year: int, series: str, *, now: datetime | None = None, connect: Callable | None = None,
                    live_reader=None) -> dict:
    """``playoffs-roster/v1``：單一 REPEATABLE READ READ ONLY 交易讀完全部來源。"""
    if connect is None:
        from cpbl.db import conn as connect
    now = now or datetime.now(UTC)
    with connect() as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute(READ_ONLY_TXN)
            inputs = read_roster_inputs(cur, year, series, now=now, live_reader=live_reader)
    return compute_roster(inputs, now=now)
