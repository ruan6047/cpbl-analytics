"""#391 聯盟收官 [league closure]：總冠軍確定後，該軍球季切成「球季結束」的**唯一**判定來源。

官方資料沒有「取消／不需舉行／冠軍確定」欄位（#391 需求研究兩輪），所以收官一律由正式資料推導：

* **一軍（major）**：沿用 :mod:`cpbl.postseason_contract` 的 §63／§60 推導（``compute_series``，⛔ 不重寫計數）；
  台灣大賽 C ``series_status == "decided"`` 才算收官。``unknown``（規則衝突、戰績缺、公告不符…）一律**不收官**。
* **二軍（farm）**：二軍總冠軍賽 F 的完賽列「先達 3 勝」（需求方裁定 #11；無官方條文，2014–2025 歷年資料推論）。
  出現和局 ⇒ ``undecided_tie``、不收官，等人判斷（裁定 #12）。2026 起決勝場須官方排程 final
  （與 ``requires_official_completion`` 同一年界 ``DAILY_CHAIN_FINAL_FROM_YEAR``；更早年份沒有官方狀態軌跡）。
* ``not_needed_keys``＝決勝後仍未完賽的列（§63「剩餘比賽取消」，如 2026/C/7），顯示端與排程端據此排除。

fail-open 的方向固定是「繼續爬」：主風險是誤判提早停爬（#391 風險），所以判不出來就是 ``closed=False``。

**球季的選法**：省略 ``season`` 時取該軍「已有完賽例行賽」的最大年份（major 看 A、farm 看 D），⛔ 不用今天的年份——
否則 1/1 一過就自動「未收官」而恢復每日爬 www；開季切回屬 #392（熱身賽開始）。在 #392 上線前，人工指示更新走
既有 ``DAILY_FORCE_FULL=1``，或本模組的 ``CPBL_SEASON_CLOSE=open``（讀到即回 ``closed=False``，status 照實保留）。

唯讀：只 ``SELECT``（單一 READ ONLY 交易），不寫 DB、不連網、沒有旗標檔。

CLI（唯讀；週跑腳本與人工核對用）::

    python -m cpbl.season_close                 # JSON：兩軍收官狀態
    python -m cpbl.season_close closed-leagues  # 一行：已收官的軍（major,farm；無則空行）
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime

from cpbl.completion import (
    DAILY_CHAIN_FINAL_FROM_YEAR,
    completed_games_sql_with_evidence,
    official_final_sql,
)
from cpbl.coverage import taipei_date

MAJOR, FARM = "major", "farm"
LEAGUES = (MAJOR, FARM)
# 每軍的賽別（一軍：例行 A＋季後挑戰賽 E＋台灣大賽 C；二軍：例行 D＋二軍總冠軍賽 F）。
LEAGUE_KINDS: dict[str, tuple[str, ...]] = {MAJOR: ("A", "E", "C"), FARM: ("D", "F")}
KIND_LEAGUE = {k: lg for lg, kinds in LEAGUE_KINDS.items() for k in kinds}
FARM_FINAL_KIND = "F"
#: 二軍總冠軍賽「先達 3 勝」（裁定 #11）。⚠️ 賽制若改回七戰四勝會提早切（卡面已接受的風險），改這一個常數。
FARM_WINS_NEEDED = 3
OVERRIDE_ENV = "CPBL_SEASON_CLOSE"
OVERRIDE_OPEN = "open"

GameKey = tuple[int, str, int]


@dataclass(frozen=True)
class LeagueClosure:
    league: str
    season: int | None
    closed: bool
    status: str                      # decided／undecided／undecided_tie／unknown／no_data
    champion_team_code: str | None = None
    decided_by: GameKey | None = None
    decided_game_date: date | None = None
    not_needed_keys: frozenset[GameKey] = field(default_factory=frozenset)
    basis: str = ""
    reason: str | None = None
    override: str | None = None

    def to_json(self) -> dict:
        return {
            "league": self.league, "season": self.season, "closed": self.closed, "status": self.status,
            "champion_team_code": self.champion_team_code,
            "decided_by": ({"year": self.decided_by[0], "kind_code": self.decided_by[1],
                            "game_sno": self.decided_by[2]} if self.decided_by else None),
            "decided_game_date": self.decided_game_date.isoformat() if self.decided_game_date else None,
            "not_needed": [{"year": y, "kind_code": k, "game_sno": s} for y, k, s in sorted(self.not_needed_keys)],
            "basis": self.basis, "reason": self.reason, "override": self.override,
        }


def kinds_of(leagues: Iterable[str]) -> tuple[str, ...]:
    """軍 → 賽別（依 A、E、C、D、F 順序）。"""
    wanted = {k for lg in leagues for k in LEAGUE_KINDS.get(lg, ())}
    return tuple(k for k in ("A", "E", "C", "D", "F") if k in wanted)


def parse_leagues(raw: str | None) -> frozenset[str]:
    """``"major,farm"`` → frozenset；空值＝無。未知值 ⇒ ``ValueError``（fail loud：打錯不得被讀成「沒有收官」以外的東西）。"""
    parts = {p.strip() for p in (raw or "").split(",") if p.strip()}
    bad = parts - set(LEAGUES)
    if bad:
        raise ValueError(f"收官清單只接受 major、farm：{raw!r}")
    return frozenset(parts)


def format_leagues(leagues: Iterable[str]) -> str:
    leagues = set(leagues)
    return ",".join(lg for lg in LEAGUES if lg in leagues)


# =========================================================================== 判定（純函式）

def major_closure(season: int, series: Mapping[str, dict], games: Iterable, *, rule_version: str | None) -> LeagueClosure:
    """一軍：``compute_series`` 的 C 系列 decided ⇒ 收官。``games``＝``postseason_contract.GameFact``。"""
    from cpbl.postseason_contract import is_not_needed

    c = series.get("C") or {}
    status = c.get("series_status")
    key = c.get("decided_by_game_key")
    basis = f"§63/§60 rule_version={rule_version}"
    games = list(games)
    not_needed = frozenset(g.key for g in games if is_not_needed(series, g))
    if status != "decided" or not key:
        mapped = {"active": "undecided", "pending": "undecided"}.get(status or "", "unknown")
        return LeagueClosure(MAJOR, season, False, mapped, basis=basis,
                             reason=c.get("conflict_reason") or (status or "no_c_series"),
                             not_needed_keys=frozenset(k for k in not_needed if k[1] == "E"))
    decided = (int(key["year"]), key["kind_code"], int(key["game_sno"]))
    day = next((g.game_date for g in games if g.key == decided), None)
    return LeagueClosure(MAJOR, season, True, "decided", champion_team_code=c.get("winner"),
                         decided_by=decided, decided_game_date=day, not_needed_keys=not_needed, basis=basis)


@dataclass(frozen=True)
class FarmGame:
    """一列二軍總冠軍賽 F（只來自 ``cpbl.games``）。"""
    year: int
    game_sno: int
    game_date: date | None
    away_team_code: str
    home_team_code: str
    away_score: int | None
    home_score: int | None
    completed: bool
    official_final: bool = False

    @property
    def key(self) -> GameKey:
        return (self.year, FARM_FINAL_KIND, self.game_sno)


def tally_farm_series(season: int, games: Iterable[FarmGame], *,
                      wins_needed: int = FARM_WINS_NEEDED) -> LeagueClosure:
    """二軍：F 完賽列依日期序計勝，先達 ``wins_needed`` 勝 ⇒ 收官。

    * 任一完賽列為和局 ⇒ ``undecided_tie``（裁定 #12，等人判斷；⛔ 不推 §66 的和局語意到二軍）。
    * 參賽隊不只兩隊、或決勝後還有完賽列 ⇒ ``unknown``（判準與事實矛盾：可能賽制不是先達 3 勝）。
    * 2026 起決勝場須官方 final（23:00 夜抓可能讀到賽中部分比分）；否則 ``undecided``。"""
    basis = f"farm_first_to_{wins_needed}"
    rows = sorted(games, key=lambda g: (g.game_date or date.max, g.game_sno))
    if not rows:
        return LeagueClosure(FARM, season, False, "no_data", basis=basis, reason="no_f_rows")
    done = [g for g in rows if g.completed and g.home_score is not None and g.away_score is not None]
    teams = {t for g in rows for t in (g.away_team_code, g.home_team_code)}
    if len(teams) != 2:
        return LeagueClosure(FARM, season, False, "unknown", basis=basis, reason="participants_not_two")
    if any(g.home_score == g.away_score for g in done):
        return LeagueClosure(FARM, season, False, "undecided_tie", basis=basis, reason="tie_in_series")
    wins = dict.fromkeys(teams, 0)
    decided: FarmGame | None = None
    champion: str | None = None
    for g in done:
        if decided is not None:
            return LeagueClosure(FARM, season, False, "unknown", basis=basis, reason="game_after_decided")
        winner = g.home_team_code if g.home_score > g.away_score else g.away_team_code
        wins[winner] += 1
        if wins[winner] >= wins_needed:
            decided, champion = g, winner
    if decided is None:
        return LeagueClosure(FARM, season, False, "undecided", basis=basis, reason="no_team_reached")
    if season >= DAILY_CHAIN_FINAL_FROM_YEAR and not decided.official_final:
        return LeagueClosure(FARM, season, False, "undecided", basis=basis,
                             reason="decisive_game_not_official_final")
    not_needed = frozenset(g.key for g in rows if not g.completed)
    return LeagueClosure(FARM, season, True, "decided", champion_team_code=champion, decided_by=decided.key,
                         decided_game_date=decided.game_date, not_needed_keys=not_needed, basis=basis)


def apply_override(closure: LeagueClosure, env: Mapping[str, str] | None = None) -> LeagueClosure:
    """``CPBL_SEASON_CLOSE=open``：人工指示更新期間一律回「未收官」（status 照實保留，override 標明）。"""
    value = (os.environ if env is None else env).get(OVERRIDE_ENV, "").strip()
    if value != OVERRIDE_OPEN:
        return closure
    return replace(closure, closed=False, override=OVERRIDE_OPEN)


# =========================================================================== 讀取（唯讀）

# 球季＝該軍例行賽（A／D）已有 canonical 完賽列的最大年份（判準同讀端 ``completed_games_sql_with_evidence``）。
LATEST_SEASON_SQL = f"""
    SELECT g.year FROM cpbl.games g
    WHERE g.kind_code = %(kind)s AND {completed_games_sql_with_evidence("g", "%(as_of)s")}
    ORDER BY g.year DESC LIMIT 1
"""

_FARM_DONE = completed_games_sql_with_evidence("g", "%(as_of)s")
FARM_GAMES_SQL = f"""
    SELECT g.year, g.game_sno, g.game_date, g.away_team_code, g.home_team_code, g.away_score, g.home_score,
           COALESCE({_FARM_DONE}, FALSE) AS completed, COALESCE({official_final_sql("g")}, FALSE) AS official_final
    FROM cpbl.games g
    WHERE g.year = %(year)s AND g.kind_code = 'F'
    ORDER BY g.game_date, g.game_sno
"""


def _latest_season(cur, kind: str, as_of: date) -> int | None:
    cur.execute(LATEST_SEASON_SQL, {"kind": kind, "as_of": as_of})
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else None


def read_major(cur, season: int, *, as_of: date) -> LeagueClosure:
    from cpbl import postseason_contract as pc

    cur.execute(pc.GAMES_V2_SQL, {"year": season, "as_of": as_of})
    cols = [d[0] for d in cur.description]
    games = []
    for row in cur.fetchall():
        r = dict(zip(cols, row, strict=False))
        games.append(pc.GameFact(
            year=int(r["year"]), kind_code=r["kind_code"], game_sno=int(r["game_sno"]), game_date=r["game_date"],
            away_team_code=r["away_team_code"], home_team_code=r["home_team_code"],
            away_score=r["away_score"], home_score=r["home_score"], completed=bool(r["completed"])))
    standings = pc.standings_facts(pc.standings_rows(cur, season, as_of))
    rule = pc.season_rule(season)
    series, _plan = pc.compute_series(rule, standings, games, year=season)
    return major_closure(season, series, games, rule_version=rule.rule_version if rule else None)


def read_farm(cur, season: int, *, as_of: date) -> LeagueClosure:
    cur.execute(FARM_GAMES_SQL, {"year": season, "as_of": as_of})
    games = [FarmGame(int(y), int(sno), d, away, home, a, h, bool(done), bool(final))
             for y, sno, d, away, home, a, h, done, final in cur.fetchall()]
    return tally_farm_series(season, games)


def league_closure(season: int | None = None, *, now: datetime | None = None, connect: Callable | None = None,
                   leagues: Iterable[str] = LEAGUES, env: Mapping[str, str] | None = None) -> dict[str, LeagueClosure]:
    """兩軍（或指定軍）的收官判定。單一 ``READ ONLY`` 交易；DB 錯誤上浮（呼叫端自行決定 fail-open）。"""
    if connect is None:
        from cpbl.db import conn as connect
    now = now or datetime.now(UTC)
    as_of = taipei_date(now)
    out: dict[str, LeagueClosure] = {}
    with connect() as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute("SET TRANSACTION READ ONLY")
            for league in leagues:
                year = season if season is not None else _latest_season(
                    cur, "A" if league == MAJOR else "D", as_of)
                if year is None:
                    out[league] = LeagueClosure(league, None, False, "no_data", reason="no_season")
                    continue
                result = read_major(cur, year, as_of=as_of) if league == MAJOR else read_farm(cur, year, as_of=as_of)
                out[league] = apply_override(result, env)
    return out


def closed_leagues(closures: Mapping[str, LeagueClosure]) -> frozenset[str]:
    return frozenset(lg for lg, c in closures.items() if c.closed)


def not_needed_keys(closures: Mapping[str, LeagueClosure]) -> frozenset[GameKey]:
    return frozenset(k for c in closures.values() for k in c.not_needed_keys)


def main(argv: list[str] | None = None) -> int:
    from cpbl.ingest._cli import cli_parser

    parser = cli_parser("python -m cpbl.season_close", __doc__)
    parser.add_argument("command", nargs="?", choices=("show", "closed-leagues"), default="show")
    parser.add_argument("--year", type=int, help="指定球季（預設：各軍已有完賽例行賽的最大年份）")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    closures = league_closure(args.year)
    if args.command == "closed-leagues":
        print(format_leagues(closed_leagues(closures)))
    else:
        print(json.dumps({lg: c.to_json() for lg, c in closures.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
