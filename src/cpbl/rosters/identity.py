"""身分解析、外籍三態判定與提交前規則檢查（PRD「身分解析與缺資料」）。

佐證只讀官方姓名來源（players 主檔、同年同隊 team_roster）與同年同隊佐證
（team_roster、一軍 A／E／C 出賽經 games 判隊、已提交的同年同隊名單）。

- 有 `@id`：主檔查無＝未命中；主檔姓名與同年同隊 team_roster 姓名皆不等於公告姓名＝ID/name 衝突；
  無同年同隊佐證＝身份證據不足。三者皆停草稿。
- 無 `@id`：同年同隊佐證範圍內精確姓名唯一才自動解析；多重命中／未命中停草稿並列候選。
- ⛔ 不做模糊比對、⛔ 不建別名表、⛔ 不創假 ID；不讀成績——沒有本季 A 成績不影響解析與提交。

外籍判定三態：`players.country` 非空才算已核，再套 `cpbl.imports` 的永田／羅力 override。
⛔ 刻意不呼叫 `imports.classify()`：它對 NULL 保守回 'local'，在名單資格檢查裡等於把未知猜成本土。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cpbl.imports import LOREE_PIDS, NAGATA_PIDS
from cpbl.rosters.canonical import IMPORT_LIMIT, ROSTER_SIZE, UNCLASSIFIED, norm
from cpbl.rosters.parser import Entry, ParsedRoster

VERIFIED_IMPORT = "verified_import"
VERIFIED_NON_IMPORT = "verified_non_import"
UNKNOWN = "unknown"

STATUS_LABEL = {VERIFIED_IMPORT: "已核洋將", VERIFIED_NON_IMPORT: "已核非洋將", UNKNOWN: "身分未知"}

# 同年同隊佐證所採計的一軍賽別（例行 A＋季後 E／C）。
EVIDENCE_KINDS = ("A", "E", "C")
PARTICIPANT_NOTE = "需人工確認（S02 系列參賽隊契約未核定；本卡只驗 team_dim 存在）"


def import_status(player_id: str, country: str | None) -> str:
    # 核定判準（PLAN §2.4）：country 非空才算已核，再套 override；NULL 一律 unknown——
    # 條款球員也不例外（#284 R1 F2），否則主檔缺國籍時仍會宣稱檢查完整。
    if country is None or not country.strip():
        return UNKNOWN
    if player_id in NAGATA_PIDS or player_id in LOREE_PIDS:
        return VERIFIED_NON_IMPORT  # 申請制條款的手動 override，皆不占洋將名額
    return VERIFIED_NON_IMPORT if country.strip() == "中華民國" else VERIFIED_IMPORT


@dataclass(frozen=True)
class PlayerRecord:
    player_id: str
    name: str
    country: str | None


@dataclass
class TeamYearContext:
    """解析一份名單所需的全部佐證快照（DB 或 fixture 皆可產生）。"""

    year: int
    team_code: str
    team_known: bool
    players: dict[str, PlayerRecord]
    evidence: dict[str, set[str]]          # player_id → 佐證種類（同年同隊）
    roster_names: dict[str, str] = field(default_factory=dict)  # 同年同隊 team_roster 姓名


@dataclass(frozen=True)
class Resolved:
    entry: Entry
    player_id: str | None
    master_name: str | None
    evidence: tuple[str, ...]
    import_status: str | None
    problem: str | None = None
    candidates: tuple[dict, ...] = ()

    @property
    def role(self) -> str:
        return self.entry.role or UNCLASSIFIED


def load_context(cur, year: int, team_code: str, explicit_ids: list[str],
                 names: list[str]) -> TeamYearContext:
    """以唯讀查詢建立佐證快照（psycopg cursor；參數化）。"""
    team_known = cur.execute(
        "SELECT EXISTS (SELECT 1 FROM cpbl.team_dim WHERE team_code = %s)", (team_code,)
    ).fetchone()[0]
    evidence: dict[str, set[str]] = {}
    roster_names: dict[str, str] = {}
    for pid, name in cur.execute(
        "SELECT player_id, name FROM cpbl.team_roster WHERE year = %s AND team_code = %s",
        (year, team_code),
    ).fetchall():
        evidence.setdefault(pid, set()).add("team_roster")
        roster_names[pid] = name
    for pid, kind in cur.execute(
        """
        SELECT DISTINCT x.acnt, x.kind_code FROM (
            SELECT hitter_acnt AS acnt, year, kind_code, game_sno, visiting_home_type
              FROM cpbl.batting_gamelog WHERE year = %(y)s AND kind_code = ANY(%(k)s)
            UNION ALL
            SELECT pitcher_acnt, year, kind_code, game_sno, visiting_home_type
              FROM cpbl.pitching_gamelog WHERE year = %(y)s AND kind_code = ANY(%(k)s)
        ) x
        JOIN cpbl.games g ON g.year = x.year AND g.kind_code = x.kind_code AND g.game_sno = x.game_sno
        WHERE (x.visiting_home_type = '2' AND g.home_team_code = %(t)s)
           OR (x.visiting_home_type = '1' AND g.away_team_code = %(t)s)
        """,
        {"y": year, "k": list(EVIDENCE_KINDS), "t": team_code},
    ).fetchall():
        evidence.setdefault(pid, set()).add(f"gamelog_{kind}")
    if cur.execute("SELECT to_regclass('cpbl.series_roster') IS NOT NULL").fetchone()[0]:
        for pid, kind in cur.execute(
            """
            SELECT m.player_id, r.kind_code FROM cpbl.series_roster r
              JOIN cpbl.series_roster_member m USING (roster_id)
             WHERE r.year = %s AND r.team_code = %s
            """,
            (year, team_code),
        ).fetchall():
            evidence.setdefault(pid, set()).add(f"series_roster_{kind}")
    wanted = sorted(set(explicit_ids) | set(evidence))
    players: dict[str, PlayerRecord] = {}
    for pid, name, country in cur.execute(
        "SELECT id, name, country FROM cpbl.players WHERE id = ANY(%s) OR name = ANY(%s)",
        (wanted, list(names)),
    ).fetchall():
        players[pid] = PlayerRecord(pid, name, country)
    return TeamYearContext(year=year, team_code=team_code, team_known=bool(team_known),
                           players=players, evidence=evidence, roster_names=roster_names)


def _official_names(ctx: TeamYearContext, pid: str) -> set[str]:
    names = set()
    if pid in ctx.players:
        names.add(norm(ctx.players[pid].name))
    if pid in ctx.roster_names:
        names.add(norm(ctx.roster_names[pid]))
    return names


def _candidate(ctx: TeamYearContext, pid: str) -> dict:
    p = ctx.players.get(pid)
    return {
        "player_id": pid,
        "master_name": p.name if p else None,
        "team_year_evidence": sorted(ctx.evidence.get(pid, ())) or ["無同年同隊佐證"],
    }


def resolve_entry(ctx: TeamYearContext, entry: Entry) -> Resolved:
    if entry.explicit_id is not None:
        pid = entry.explicit_id
        rec = ctx.players.get(pid)
        if rec is None:
            return Resolved(entry, None, None, (), None, problem=f"主檔查無 @id={pid}（不創假 ID）")
        ev = tuple(sorted(ctx.evidence.get(pid, ())))
        status = import_status(pid, rec.country)
        if entry.name not in _official_names(ctx, pid):
            return Resolved(entry, None, rec.name, ev, status,
                            problem=f"ID/name 不符：@id={pid} 的官方姓名是「{rec.name}」",
                            candidates=(_candidate(ctx, pid),))
        if not ev:
            return Resolved(entry, None, rec.name, ev, status,
                            problem=f"身份證據不足：{pid} 無 {ctx.year}/{ctx.team_code} 同年同隊佐證",
                            candidates=(_candidate(ctx, pid),))
        return Resolved(entry, pid, rec.name, ev, status)

    in_scope = sorted(pid for pid in ctx.evidence if entry.name in _official_names(ctx, pid))
    if len(in_scope) == 1:
        pid = in_scope[0]
        rec = ctx.players.get(pid)
        if rec is None:
            return Resolved(entry, None, None, (), None,
                            problem=f"同年同隊佐證 {pid} 在主檔查無（先補身份，不創假 ID）")
        return Resolved(entry, pid, rec.name, tuple(sorted(ctx.evidence[pid])),
                        import_status(pid, rec.country))
    elsewhere = sorted(pid for pid, rec in ctx.players.items()
                       if norm(rec.name) == entry.name and pid not in in_scope)
    if len(in_scope) > 1:
        return Resolved(entry, None, None, (), None,
                        problem=f"同年同隊同名多重命中 {len(in_scope)} 人；請以 @id= 指定",
                        candidates=tuple(_candidate(ctx, p) for p in in_scope + elsewhere))
    return Resolved(entry, None, None, (), None,
                    problem=f"{ctx.year}/{ctx.team_code} 範圍內查無姓名「{entry.name}」",
                    candidates=tuple(_candidate(ctx, p) for p in elsewhere))


@dataclass
class Prepared:
    """預覽結果：解析＋身分＋規則檢查。status ∈ ready／draft／violation。"""

    parsed: ParsedRoster
    rows: list[Resolved]
    violations: list[str]
    import_check: dict
    team_known: bool

    @property
    def unresolved(self) -> list[Resolved]:
        return [r for r in self.rows if r.player_id is None]

    @property
    def status(self) -> str:
        if self.unresolved:
            return "draft"
        if self.violations:
            return "violation"
        return "ready"


def check(parsed: ParsedRoster, ctx: TeamYearContext) -> Prepared:
    rows = [resolve_entry(ctx, e) for e in parsed.entries]
    violations: list[str] = []
    if not ctx.team_known:
        violations.append(f"隊伍代碼 {parsed.team_code} 不在 team_dim")
    if len(rows) != ROSTER_SIZE:
        violations.append(f"人數 {len(rows)} ≠ {ROSTER_SIZE}：未滿或超過 32 人不能提交")
    seen: dict[str, Resolved] = {}
    for r in rows:
        if r.player_id is None:
            continue
        if r.player_id in seen:
            first = seen[r.player_id]
            kind = "官方守位衝突" if first.entry.position != r.entry.position else "重複 ID"
            violations.append(
                f"{kind}：{r.player_id} 出現在第 {first.entry.line} 行（{first.entry.position}）"
                f"與第 {r.entry.line} 行（{r.entry.position}）"
            )
        else:
            seen[r.player_id] = r
    verified = [r for r in seen.values() if r.import_status == VERIFIED_IMPORT]
    unknown = [r for r in seen.values() if r.import_status == UNKNOWN]
    import_check = {
        "basis": "players.country+cpbl.imports overrides",
        "limit": IMPORT_LIMIT,
        "verified_imports": [
            {"player_id": r.player_id, "name": r.master_name,
             "country": ctx.players[r.player_id].country}
            for r in sorted(verified, key=lambda r: r.player_id)
        ],
        "unknown": [{"player_id": r.player_id, "name": r.master_name}
                    for r in sorted(unknown, key=lambda r: r.player_id)],
        "complete": not unknown,
    }
    if len(verified) > IMPORT_LIMIT:
        names = "、".join(f"{v['name']}({v['player_id']})" for v in import_check["verified_imports"])
        violations.append(f"已核洋將 {len(verified)} 人 > 上限 {IMPORT_LIMIT}：{names}")
    return Prepared(parsed=parsed, rows=rows, violations=violations,
                    import_check=import_check, team_known=ctx.team_known)
