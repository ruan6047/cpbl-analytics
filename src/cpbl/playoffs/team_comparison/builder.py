"""全年 A／兩隊 A 對戰背景摘要的本機離線 builder（#287 WP2；CLI 入口 ``cpbl-build-team-comparison`` 在
:mod:`cpbl.ingest.run_build_team_comparison`）。

流程（PLAN r2 §2.1–§2.3、§3）：

1. **讀**（單一 REPEATABLE READ READ ONLY 交易）：該年已完成 A 場（``cpbl.completion`` 證據感知判準）、
   完賽證據鍵、該等場的 batting／pitching gamelog 本卡所用欄位、current 指標。
2. 算 ``source_hash``（內容雜湊；gamelog 無 revision 欄，只有內容雜湊能涵蓋 box 更正）與
   ``games_fingerprint``；與 current 同源同版 ⇒ **no-op exit 0**（冪等）。
3. 逐場兩側 box 覆蓋檢查（停止條件 §12.1-1）：不全 ⇒ **不寫 build、不切 current**，只在指標列
   標 ``pending_source_hash``／``pending_since``（舊版標待更新），列出缺漏場次，exit 3。
4. **寫**（單一交易）：不可變 build＋列（``ON CONFLICT DO NOTHING``）→ 指標 CAS（只有 current
   仍是讀到的那一版才切換）。中途失敗／被殺 ⇒ 交易回滾，指標不動；可攔的失敗再標待更新。
   兩個 builder 競爭時至多一次切換；輸家若發現 current 已是同一 build 視為成功。

⛔ 只寫 ``team_comparison_*`` 三表（與 ``--record-failure`` 的本機 ``refresh_log`` 一列）；
⛔ 不 migrate（schema 只隨 migration 部署）；⛔ GET 不呼叫本模組。

退出碼：0 成功／無變更 · 2 參數錯 · 3 覆蓋不全（未切換，標待更新） · 4 指標已被他人切到別版
        · 5 建置失敗（已回滾，標待更新） · 6 摘要表不存在（尚未套 migration）
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from psycopg.types.json import Jsonb

from cpbl.completion import completed_games_sql_with_evidence
from cpbl.playoffs.team_comparison import core

BUILDER_VERSION = "team-comparison-1.0.0"
#: build_id 命名空間（固定值；改了就等於換掉全部既有 build 身分，⛔ 不得改）
BUILD_NAMESPACE = uuid.UUID("6f6a2c1e-3f0b-5d7a-9c87-2870287028a1")

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_COVERAGE = 3
EXIT_CAS_LOST = 4
EXIT_FAILED = 5
EXIT_NO_TABLES = 6

TABLES_EXIST_SQL = (
    "SELECT to_regclass('cpbl.team_comparison_build') IS NOT NULL"
    " AND to_regclass('cpbl.team_comparison_row') IS NOT NULL"
    " AND to_regclass('cpbl.team_comparison_current') IS NOT NULL"
)

COMPLETED_A_GAMES_SQL = (
    "SELECT g.year, g.kind_code, g.game_sno, g.game_date, g.home_team_code, g.away_team_code, "
    "g.home_score, g.away_score FROM cpbl.games g "
    f"WHERE g.year = %s AND g.kind_code = 'A' AND {completed_games_sql_with_evidence('g')} "
    "ORDER BY g.game_sno"
)
EVIDENCE_SQL = ("SELECT game_sno FROM cpbl.game_completion_evidence "
                "WHERE year = %s AND kind_code = 'A' ORDER BY game_sno")
BAT_SQL = (
    "SELECT year, kind_code, game_sno, hitter_acnt, "
    + ", ".join(core.BAT_SOURCE_COLUMNS)
    + " FROM cpbl.batting_gamelog WHERE year = %s AND kind_code = 'A' AND game_sno = ANY(%s)"
    " ORDER BY game_sno, hitter_acnt"
)
PIT_SQL = (
    "SELECT year, kind_code, game_sno, pitcher_acnt, "
    + ", ".join(core.PIT_SOURCE_COLUMNS)
    + " FROM cpbl.pitching_gamelog WHERE year = %s AND kind_code = 'A' AND game_sno = ANY(%s)"
    " ORDER BY game_sno, pitcher_acnt"
)
CURRENT_SQL = (
    "SELECT c.build_id, c.pending_source_hash, b.source_hash, b.builder_version "
    "FROM cpbl.team_comparison_current c JOIN cpbl.team_comparison_build b USING (build_id) "
    "WHERE c.year = %s AND c.kind_code = 'A'"
)


def build_id_for(year: int, builder_version: str, source_hash: str) -> uuid.UUID:
    return uuid.uuid5(BUILD_NAMESPACE, f"{year}|{builder_version}|{source_hash}")


@dataclass
class Source:
    year: int
    games: list[core.GameRow]
    evidence: list[int]
    bat_rows: list[dict]
    pit_rows: list[dict]

    def source_hash(self) -> str:
        bat = [[r["game_sno"], r["hitter_acnt"], *(r[c] for c in core.BAT_SOURCE_COLUMNS)]
               for r in self.bat_rows]
        pit = [[r["game_sno"], r["pitcher_acnt"], *(r[c] for c in core.PIT_SOURCE_COLUMNS)]
               for r in self.pit_rows]
        return core.sha256_hex({
            "label": "team-comparison-source/v1", "year": self.year,
            "games": core.games_payload(self.games), "evidence": self.evidence,
            "batting_columns": core.BAT_SOURCE_COLUMNS, "batting": sorted(bat, key=lambda r: (r[0], r[1])),
            "pitching_columns": core.PIT_SOURCE_COLUMNS, "pitching": sorted(pit, key=lambda r: (r[0], r[1])),
        })


@dataclass
class Plan:
    year: int
    source_hash: str
    games_fingerprint: str
    build_id: uuid.UUID
    rows: list[dict]
    rows_digest: str
    coverage: dict
    current_build_id: uuid.UUID | None
    current_pending: str | None
    current_same: bool

    @property
    def complete(self) -> bool:
        return not self.coverage["missing"] and self.coverage["expected_games"] > 0


def _dict_rows(cur, sql: str, params) -> list[dict]:
    cur.execute(sql, params)
    names = [d.name for d in cur.description]
    return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]


def read_source(cur, year: int) -> Source:
    """一次唯讀讀完來源（呼叫端負責 REPEATABLE READ READ ONLY 交易）。"""
    games_raw = _dict_rows(cur, COMPLETED_A_GAMES_SQL, (year,))
    snos = [r["game_sno"] for r in games_raw]
    if len(snos) != len(set(snos)):
        raise RuntimeError(f"{year} A 已完成場次的 game_sno 重複（games 同場多 season_code 列）")
    games = [core.GameRow((int(r["year"]), r["kind_code"], int(r["game_sno"])), r["game_date"],
                          r["home_team_code"], r["away_team_code"], r["home_score"], r["away_score"])
             for r in games_raw]
    cur.execute(EVIDENCE_SQL, (year,))
    evidence = [int(r[0]) for r in cur.fetchall()]
    bat = _dict_rows(cur, BAT_SQL, (year, snos)) if snos else []
    pit = _dict_rows(cur, PIT_SQL, (year, snos)) if snos else []
    return Source(year, games, evidence, bat, pit)


def compute_rows(src: Source) -> tuple[list[dict], dict]:
    """全年 A（每隊一列）＋兩隊 A 對戰（有交手的有序隊對各一列）＋逐場覆蓋。"""
    index = core.box_index(src.games, src.bat_rows, src.pit_rows)
    teams = sorted({t for g in src.games for t in (g.home, g.away)})
    rows: list[dict] = []
    for team in teams:
        mine = [g for g in src.games if team in (g.home, g.away)]
        rows.append(core.row_from_totals("season", team, "", core.aggregate(team, mine, index)))
        for opp in teams:
            if opp == team:
                continue
            h2h = [g for g in mine if g.opponent(team) == opp]
            if h2h:
                rows.append(core.row_from_totals("head_to_head", team, opp,
                                                 core.aggregate(team, h2h, index)))
    return rows, core.coverage(src.games, index)


def plan_build(src: Source, current: tuple | None) -> Plan:
    sh = src.source_hash()
    rows, cov = compute_rows(src)
    bid = build_id_for(src.year, BUILDER_VERSION, sh)
    cur_bid, cur_pending, cur_hash, cur_ver = current if current else (None, None, None, None)
    return Plan(
        year=src.year, source_hash=sh, games_fingerprint=core.games_fingerprint(src.year, src.games),
        build_id=bid, rows=rows, rows_digest=core.rows_digest(rows), coverage=cov,
        current_build_id=cur_bid, current_pending=cur_pending,
        current_same=(cur_hash == sh and cur_ver == BUILDER_VERSION),
    )


# ---------------------------------------------------------------- 寫入


class BuildError(RuntimeError):
    def __init__(self, code: int, message: str):
        self.code = code
        super().__init__(message)


INSERT_BUILD_SQL = (
    "INSERT INTO cpbl.team_comparison_build (build_id, year, kind_code, builder_version, source_hash, "
    "games_fingerprint, completed_games, rows_digest, coverage) VALUES (%s, %s, 'A', %s, %s, %s, %s, %s, %s) "
    "ON CONFLICT (build_id) DO NOTHING"
)
INSERT_ROW_SQL = (
    "INSERT INTO cpbl.team_comparison_row (build_id, " + ", ".join(core.ROW_COLUMNS) + ") VALUES ("
    + ", ".join(["%s"] * (len(core.ROW_COLUMNS) + 1)) + ") ON CONFLICT DO NOTHING"
)
MARK_PENDING_SQL = (
    "UPDATE cpbl.team_comparison_current SET pending_source_hash = %s, "
    "pending_since = COALESCE(pending_since, now()) WHERE year = %s AND kind_code = 'A'"
)
CLEAR_PENDING_SQL = (
    "UPDATE cpbl.team_comparison_current SET pending_source_hash = NULL, pending_since = NULL "
    "WHERE year = %s AND kind_code = 'A' AND build_id = %s AND pending_source_hash IS NOT NULL"
)


def _row_params(build_id: uuid.UUID, r: dict) -> list:
    return [build_id, *(Jsonb(r[c]) if c == "null_reasons" else r[c] for c in core.ROW_COLUMNS)]


def write_build(c, p: Plan) -> None:
    """不可變 build＋列（同交易）；已存在同 build_id 時核對列雜湊一致。"""
    with c.cursor() as cur:
        cur.execute(INSERT_BUILD_SQL, (p.build_id, p.year, BUILDER_VERSION, p.source_hash,
                                       p.games_fingerprint, p.coverage["expected_games"],
                                       p.rows_digest, Jsonb(p.coverage)))
        cur.execute("SELECT rows_digest FROM cpbl.team_comparison_build WHERE build_id = %s",
                    (p.build_id,))
        existing = cur.fetchone()[0]
        if existing != p.rows_digest:
            raise BuildError(EXIT_FAILED, f"build {p.build_id} 已存在但列雜湊不同（{existing} ≠ {p.rows_digest}）")
        cur.executemany(INSERT_ROW_SQL, [_row_params(p.build_id, r) for r in p.rows])
        cur.execute("SELECT count(*) FROM cpbl.team_comparison_row WHERE build_id = %s", (p.build_id,))
        n = cur.fetchone()[0]
        if n != len(p.rows):
            raise BuildError(EXIT_FAILED, f"build {p.build_id} 列數 {n} ≠ {len(p.rows)}")


def promote(c, year: int, build_id: uuid.UUID, expected: uuid.UUID | None) -> bool:
    """指標 CAS：只有 current 仍是 ``expected``（None＝尚無指標）時才切到 ``build_id``。"""
    with c.cursor() as cur:
        if expected is None:
            cur.execute(
                "INSERT INTO cpbl.team_comparison_current (year, kind_code, build_id) VALUES (%s, 'A', %s) "
                "ON CONFLICT (year, kind_code) DO NOTHING", (year, build_id))
        else:
            cur.execute(
                "UPDATE cpbl.team_comparison_current SET build_id = %s, promoted_at = now(), "
                "pending_source_hash = NULL, pending_since = NULL "
                "WHERE year = %s AND kind_code = 'A' AND build_id = %s", (build_id, year, expected))
        return cur.rowcount == 1


def mark_pending(connect: Callable, year: int, source_hash: str) -> bool:
    """舊版標待更新（只動指標列的 pending 兩欄；無指標或標記本身失敗回 False，不遮蓋原失敗）。"""
    try:
        with connect() as c, c.cursor() as cur:
            cur.execute(MARK_PENDING_SQL, (source_hash, year))
            return cur.rowcount == 1
    except Exception:  # noqa: BLE001 — 標記失敗只影響「待更新」提示，原退出碼照實回報
        return False


def current_build_id(connect: Callable, year: int) -> uuid.UUID | None:
    with connect() as c:
        row = c.execute("SELECT build_id FROM cpbl.team_comparison_current "
                        "WHERE year = %s AND kind_code = 'A'", (year,)).fetchone()
    return row[0] if row else None


@dataclass
class Outcome:
    code: int
    status: str
    message: str
    plan: Plan | None = None


def _read_plan(connect: Callable, year: int) -> Plan | None:
    with connect() as c:
        with c.transaction():
            cur = c.cursor()
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cur.execute(TABLES_EXIST_SQL)
            if not cur.fetchone()[0]:
                raise BuildError(EXIT_NO_TABLES, "team_comparison_* 摘要表不存在（尚未套 migration 077；本 builder 不 migrate）")
            src = read_source(cur, year)
            cur.execute(CURRENT_SQL, (year,))
            current = cur.fetchone()
    if not src.games:
        return None
    return plan_build(src, current)


def run_build(connect: Callable, year: int, *, dry_run: bool = False) -> Outcome:
    try:
        p = _read_plan(connect, year)
    except BuildError as exc:
        return Outcome(exc.code, "no_tables" if exc.code == EXIT_NO_TABLES else "failed", str(exc))
    except Exception as exc:  # noqa: BLE001 — 讀取失敗（連線、資料不變量）如實回報，不寫任何東西
        return Outcome(EXIT_FAILED, "failed", f"{year} 讀取來源失敗（未寫入）：{type(exc).__name__}: {exc}")
    if p is None:
        return Outcome(EXIT_OK, "no_games", f"{year} 尚無已完成 A 場，無可建置內容（未寫入）")
    if p.current_same:
        if p.current_pending and not dry_run:
            with connect() as c:
                c.execute(CLEAR_PENDING_SQL, (year, p.current_build_id))
        return Outcome(EXIT_OK, "no_change",
                       f"{year} 來源未變（source_hash {p.source_hash[:12]}，build {p.current_build_id}）", p)
    if not p.complete:
        missing = sorted({m["game_key"] for m in p.coverage["missing"]})
        msg = (f"{year} A 母體覆蓋不全：{len(missing)} 場缺 box 或欄位未知（{', '.join(missing[:10])}"
               f"{' …' if len(missing) > 10 else ''}）；不切 current")
        if not dry_run:
            marked = mark_pending(connect, year, p.source_hash)
            msg += "，舊版已標待更新" if marked else "，尚無舊版可標"
        return Outcome(EXIT_COVERAGE, "coverage_incomplete", msg, p)
    if dry_run:
        return Outcome(EXIT_OK, "dry_run", f"{year} 將建 build {p.build_id}（{len(p.rows)} 列）", p)
    try:
        with connect() as c:
            with c.transaction():
                write_build(c, p)
                if not promote(c, year, p.build_id, p.current_build_id):
                    raise BuildError(EXIT_CAS_LOST, "current 已被其他程序切換")
    except BuildError as exc:
        if exc.code == EXIT_CAS_LOST:
            now_id = current_build_id(connect, year)
            if now_id == p.build_id:
                return Outcome(EXIT_OK, "already_current",
                               f"{year} current 已由其他程序切到同一 build {p.build_id}", p)
            return Outcome(EXIT_CAS_LOST, "cas_lost",
                           f"{year} current 在建置期間被切到 {now_id}（未覆寫；請重跑）", p)
        mark_pending(connect, year, p.source_hash)
        return Outcome(exc.code, "failed", f"{year} 建置失敗（已回滾、舊版標待更新）：{exc}", p)
    except Exception as exc:  # noqa: BLE001 — 任何寫入失敗都回滾並標待更新，再如實回報
        mark_pending(connect, year, p.source_hash)
        return Outcome(EXIT_FAILED, "failed",
                       f"{year} 建置失敗（已回滾、舊版標待更新）：{type(exc).__name__}: {exc}", p)
    return Outcome(EXIT_OK, "promoted",
                   f"{year} 已建 build {p.build_id}（{len(p.rows)} 列）並切換 current"
                   f"（前一版 {p.current_build_id}）", p)


def run_promote_existing(connect: Callable, year: int, build_id: uuid.UUID) -> Outcome:
    """回指既有 build（回復用；PLAN §12.4／§13）。"""
    with connect() as c:
        row = c.execute("SELECT year FROM cpbl.team_comparison_build WHERE build_id = %s",
                        (build_id,)).fetchone()
    if not row or int(row[0]) != year:
        return Outcome(EXIT_FAILED, "failed", f"build {build_id} 不存在或不屬於 {year}")
    cur_id = current_build_id(connect, year)
    with connect() as c:
        with c.transaction():
            ok = promote(c, year, build_id, cur_id)
    if not ok:
        return Outcome(EXIT_CAS_LOST, "cas_lost", f"{year} current 在回指期間被切換")
    return Outcome(EXIT_OK, "promoted", f"{year} current 回指 build {build_id}（前一版 {cur_id}）")


def record_failure(connect: Callable, year: int, out: Outcome) -> None:
    """每日鏈用：失敗時在**本機** refresh_log 記一列（scope team-comparison-build；不擋其他步驟）。"""
    detail = {"year": year, "exit_code": out.code, "status": out.status,
              "source_hash": out.plan.source_hash if out.plan else None}
    with connect() as c:
        c.execute("INSERT INTO cpbl.refresh_log (scope, from_date, to_date, detail, ok, note) "
                  "VALUES ('team-comparison-build', %s, %s, %s, false, %s)",
                  (date(year, 1, 1), date(year, 12, 31), Jsonb(detail), out.message[:1000]))
