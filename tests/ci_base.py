"""CI 最小資料基底（#413）：產生器、載入器與 pytest 端的偵測。

為什麼有這支：CI 的主 DSN 原本刻意指向沒人聽的埠，凡是要真實資料的測試在 CI 一律 skip，
只在需求方 Mac 的正式庫上才有覆蓋。這裡把「固定幾場完成場＋對應切片」從本機庫**唯讀**擷取成
逐表 CSV（``tests/fixtures/ci_base/``），CI 先 migrate 到產出時的 migration 最大號、載入、
再把之後的新 migration 疊上去，讓那批測試在 CI 空庫上也實跑。

三個入口（都從 repo 根執行）::

    uv run python tests/ci_base.py generate --source-dsn <本機庫> --reference-dsn <已 migrate 的拋棄式庫>
    uv run python tests/ci_base.py load --target-dsn <拋棄式空庫>
    （pytest 端）conftest 讀 ``marker_of()``／測試讀 ``active()``

⛔ 產生器只開唯讀交易（``default_transaction_read_only=on`` 加 ``READ ONLY``），不寫任何 DB；
⛔ 載入器拒絕三種目標：設定預設值（本機主庫）、``.env`` 的主庫、``cpbl.games`` 已有資料的庫。
⛔ 不收哨兵年份（1900、2099）與 2018/D/110：好幾個測試會自己寫這些鍵，收進來會撞。

跨年衰退（需求方裁定 #413 待裁 2）：凡以「本季」（``date.today().year``）為準的測試，在跨年後
會因基底只有舊季而退回 skip——**每季重產一次基底**，不加每年 1/1 必紅的守衛。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "ci_base"
MANIFEST = "manifest.json"
FORMAT = "cpbl-ci-base/1"
# 載入完成後寫在 COMMENT ON DATABASE 的前綴；conftest 只認這個前綴。
MARKER_PREFIX = "cpbl-ci-base "
# 新增 fixtures 總量上限（需求方 #413：5 MB 未壓縮）。超過就讓產生器失敗，不硬塞。
SIZE_LIMIT_BYTES = 5 * 1024 * 1024
TAIPEI = timezone(timedelta(hours=8))

# --------------------------------------------------------------------------- 選取內容
#
# 場次（每一場都帶「為了哪些測試」——改動前先查那些測試還在不在）。
GAMES: tuple[tuple[int, str, int, str], ...] = (
    (2026, "E", 1, "季後 E：test_postseason_sources 本機 loader 對帳"),
    (2026, "E", 2, "季後 E：test_postseason_sources 本機 loader 對帳"),
    (2026, "E", 3, "季後 E：test_postseason_sources 本機 loader 對帳"),
    (2026, "E", 4, "季後 E：test_postseason_sources 本機 loader 對帳"),
    (2026, "A", 81, "test_er_rebuild_score_deferral；延長賽含突破僵局列＋published PA build＋"
                    "起始事件自帶得分的打席（test_pa_facts／test_recap_wp_pre_scores／test_sabr_re24）"),
    (2018, "A", 124, "test_er_rebuild_error_gate_narrowing（12 局下 E=1、該半局 0 分）"),
    (2018, "A", 213, "test_er_rebuild_error_gate_narrowing（1 局下 E=1、該半局 1 分）"),
    (2026, "D", 234, "官方 final 的 0:0（test_completion_evidence）"),
)

_GAME_VALUES = ", ".join(f"({y}, '{k}', {s})" for y, k, s, _ in GAMES)
_IN_GAMES = f"(year, kind_code, game_sno) IN (VALUES {_GAME_VALUES})"
_PUBLISHED_BUILDS = (f"SELECT build_id FROM cpbl.game_recap_builds "
                     f"WHERE state = 'published' AND {_IN_GAMES}")

# 0000000797 與 丘昌榮：test_coaches_history 的兩個端點。
_COACH_PERSON_ID = "0000000797"
_COACH_NAME = "丘昌榮"
_COACH_NAMES = (f"(SELECT name FROM cpbl.players WHERE id = '{_COACH_PERSON_ID}' "
                f"UNION SELECT '{_COACH_NAME}')")
# test_records_api：生涯榜要有人、且「現役」要與冠軍榜有交集 → 取同時在 2026 登錄名單與
# 冠軍成員裡、生涯全壘打最多的三人（並列以 player_id 決定，確定性）。
_RECORD_PLAYERS = """(SELECT player_id FROM (
    SELECT b.player_id, sum(b.hr) AS hr FROM cpbl.batting_seasons b
    WHERE b.player_id IN (SELECT player_id FROM cpbl.team_roster WHERE year = 2026)
      AND b.player_id IN (SELECT player_id FROM cpbl.championship_members)
    GROUP BY b.player_id ORDER BY hr DESC, b.player_id LIMIT 3) t)"""


@dataclass(frozen=True)
class Table:
    name: str
    where: str          # 純常數 SQL 條件；"TRUE"＝全表
    why: str


# 依 FK 順序（父在前）；載入器照這個順序 COPY。
# ⛔ migration 自己播種的表（team_dim、venue_dim、championships、championship_managers）不收：
# 載入順序是先 migrate 到 N，那些列已在庫裡，再 COPY 會撞主鍵；產生器會檢查並拒絕。
TABLES: tuple[Table, ...] = (
    Table("games", "year NOT IN (1900, 2099)",
          "全量（需求方裁定 #413 待裁 1）：completion_evidence／daily_summary 全庫對帳、streak、standings"),
    Table("standings", "TRUE", "全量（待裁 1）：test_completion_evidence R2 2018–2024 和局對帳"),
    Table("game_completion_evidence", "TRUE", "全量（待裁 1）：有證據的 0:0"),
    Table("game_schedule_status_revisions",
          f"{_IN_GAMES} OR (year, kind_code, game_sno) IN ("
          "SELECT year, kind_code, game_sno FROM cpbl.games "
          "WHERE home_score + away_score = 0 OR (year >= 2026 AND kind_code IN ('E', 'C')))",
          "官方 final 判準：入選場次＋全部 0:0＋2026 起季後 E／C（completion 的官方分支）"),
    Table("championship_members", "TRUE", "test_records_api 冠軍榜"),
    Table("batting_seasons", f"player_id IN {_RECORD_PLAYERS}", "test_records_api 生涯榜（三人）"),
    Table("team_roster", f"year = 2026 AND player_id IN {_RECORD_PLAYERS}",
          "test_records_api 現役判定（同三人）"),
    Table("player_awards", "award = '年度最佳總教練'", "test_championship_managers 第三來源"),
    Table("coaches", f"name IN {_COACH_NAMES}", "test_coaches_history"),
    Table("managers", f"name IN {_COACH_NAMES}", "test_coaches_history"),
    Table("run_expectancy", "TRUE", "RE24 矩陣（test_pa_facts／test_sabr_re24）"),
    # --- 逐場切片
    Table("game_detail", _IN_GAMES, "box 核心"),
    Table("game_scoreboard", _IN_GAMES, "box 核心；ER 重建的官方失誤"),
    Table("game_livelog", _IN_GAMES, "box 核心；逐打席"),
    Table("game_livelog_extra", _IN_GAMES, "livelog 附加列"),
    Table("batting_gamelog", _IN_GAMES, "box 核心"),
    Table("pitching_gamelog", _IN_GAMES, "box 核心"),
    Table("pitching_game_flags", _IN_GAMES, "box 核心"),
    Table("pitch_tracking", _IN_GAMES, "逐球（postseason box 計數）"),
    Table("game_source_revisions", _IN_GAMES, "box 來源觀測時刻"),
    Table("game_recap_source_revisions",
          f"id IN (SELECT livelog_revision_id FROM cpbl.game_recap_builds WHERE build_id IN ({_PUBLISHED_BUILDS})"
          f" UNION SELECT tracking_revision_id FROM cpbl.game_recap_builds WHERE build_id IN ({_PUBLISHED_BUILDS})"
          f" UNION SELECT source_revision_id FROM cpbl.game_pa_pitch_mappings WHERE build_id IN ({_PUBLISHED_BUILDS}))",
          "published build 引用的來源版本"),
    Table("game_recap_builds", f"build_id IN ({_PUBLISHED_BUILDS})", "只取 published"),
    Table("game_plate_appearances", f"build_id IN ({_PUBLISHED_BUILDS})", "只取 published"),
    Table("game_pa_events",
          f"pa_row_id IN (SELECT pa_row_id FROM cpbl.game_plate_appearances "
          f"WHERE build_id IN ({_PUBLISHED_BUILDS}))", "只取 published"),
    Table("game_pa_pitch_mappings", f"build_id IN ({_PUBLISHED_BUILDS})", "只取 published"),
)

# players 是閉包：上面各表引用到的人＋兩位教練。最後才算（要等其他表的條件），但載入時排第一。
_PLAYER_REFS = (
    ("championship_members", "player_id"), ("batting_seasons", "player_id"),
    ("team_roster", "player_id"), ("player_awards", "player_id"),
    ("batting_gamelog", "hitter_acnt"), ("pitching_gamelog", "pitcher_acnt"),
)
PERSON_HISTORY = Table(
    "person_history", f"name IN {_COACH_NAMES}", "test_coaches_history（FK → players）")


def _players_where() -> str:
    by_name = f"name IN {_COACH_NAMES}"
    refs = " UNION ".join(
        f"SELECT {col} FROM cpbl.{t} WHERE {next(x.where for x in TABLES if x.name == t)}"
        for t, col in _PLAYER_REFS)
    return (f"{by_name} OR id = '{_COACH_PERSON_ID}' OR id IN ({refs}) "
            f"OR id IN (SELECT player_id FROM cpbl.person_history WHERE {PERSON_HISTORY.where})")


def load_order() -> tuple[Table, ...]:
    players = Table("players", _players_where(), "被引用到的人（FK／JOIN）")
    return (players, *TABLES, PERSON_HISTORY)


# --------------------------------------------------------------------------- 共用

def _migrations() -> list[Path]:
    return sorted((ROOT / "migrations").glob("*.sql"))


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _local_key(dsn: str) -> tuple[str, int, str]:
    """把 DSN 正規化成 (主機類別, 埠, 庫名)：localhost／127.0.0.1／::1 一律當同一台。"""
    from psycopg import conninfo
    d = conninfo.conninfo_to_dict(dsn)
    host = (d.get("host") or "localhost").lower()
    if host in ("localhost", "127.0.0.1", "::1", "") or host.startswith("/"):
        host = "local"
    return host, int(d.get("port") or 5432), d.get("dbname") or d.get("user") or ""


def _dotenv_database_url() -> str | None:
    env = ROOT / ".env"
    if not env.is_file():
        return None
    for line in env.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key.strip() == "DATABASE_URL":
            return value.strip().strip("'\"")
    return None


def protected_targets() -> list[str]:
    """載入器⛔ 寫入的主庫：設定預設值（本機 5433 主庫）與 .env 的 DATABASE_URL。"""
    from cpbl.config import Settings
    out = [Settings.model_fields["database_url"].default]
    if (env := _dotenv_database_url()):
        out.append(env)
    return out


class Refused(RuntimeError):
    """載入目標不合格（主庫或已有資料）。"""


def refuse_target(dsn: str, *, games_rows: int | None) -> None:
    """三種拒絕：等於設定預設值、等於 .env 主庫、``cpbl.games`` 已非空。"""
    key = _local_key(dsn)
    for protected in protected_targets():
        if _local_key(protected) == key:
            raise Refused(f"目標是主庫（{key[0]}:{key[1]}/{key[2]}），拒絕寫入")
    if games_rows:
        raise Refused(f"目標 cpbl.games 已有 {games_rows} 列，拒絕載入（只載入空的拋棄式庫）")


# --------------------------------------------------------------------------- 產生器

_SESSION = ("SET TimeZone = 'UTC'", "SET DateStyle = 'ISO, YMD'", "SET IntervalStyle = 'postgres'",
            "SET extra_float_digits = 1", "SET bytea_output = 'hex'")


def _columns(cur, table: str) -> list[tuple[str, str]]:
    rows = cur.execute(
        "SELECT a.attname, format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
        "WHERE a.attrelid = %s::regclass AND a.attnum > 0 AND NOT a.attisdropped "
        "AND a.attgenerated = '' ORDER BY a.attnum", (f"cpbl.{table}",)).fetchall()
    return [(r[0], r[1]) for r in rows]


def _order_by(cur, table: str, cols: list[str]) -> list[str]:
    pk = cur.execute(
        "SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid "
        "AND a.attnum = ANY (i.indkey) WHERE i.indrelid = %s::regclass AND i.indisprimary "
        "ORDER BY array_position(i.indkey, a.attnum)", (f"cpbl.{table}",)).fetchall()
    return [r[0] for r in pk] or cols


def _fingerprint(cur, tables: list[str]) -> str:
    """來源指紋：入選各表的寫入計數（插入／更新／刪除）。兩次產生之間有人寫過這些表就會變。"""
    rows = cur.execute(
        "SELECT relname, n_tup_ins, n_tup_upd, n_tup_del FROM pg_stat_all_tables "
        "WHERE schemaname = 'cpbl' AND relname = ANY (%s) ORDER BY relname", (tables,)).fetchall()
    return _sha256(json.dumps([list(r) for r in rows]).encode())


def _ro_connect(dsn: str):
    """唯讀連線，之後的第一個交易是 ``REPEATABLE READ READ ONLY``（整次擷取共用一個快照）。

    ⛔ 不能在非 autocommit 下直接 ``SET SESSION CHARACTERISTICS``：psycopg 執行它時已隱式開了
    交易，這句只影響**之後**的交易，當次交易仍是預設的 READ COMMITTED（#413 審核 F1）。所以先在
    autocommit 下設好 session 特性，再切回交易模式；第一個 ``execute()`` 開的交易才吃得到。
    """
    import psycopg
    c = psycopg.connect(dsn, options="-c default_transaction_read_only=on", autocommit=True)
    c.execute("SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    c.autocommit = False
    return c


def require_snapshot_txn(cur) -> None:
    """當次交易必須是 ``REPEATABLE READ`` 且唯讀；不是就停（規劃 §2「單一 REPEATABLE READ READ ONLY 交易」）。"""
    isolation = cur.execute("SHOW transaction_isolation").fetchone()[0]
    read_only = cur.execute("SHOW transaction_read_only").fetchone()[0]
    if (isolation, read_only) != ("repeatable read", "on"):
        raise SystemExit(f"擷取交易不是 REPEATABLE READ READ ONLY（isolation={isolation!r}, "
                         f"read_only={read_only!r}）——停止，不產出不一致的快照")


def generate(source_dsn: str, reference_dsn: str, out_dir: Path, extracted_on: str) -> dict:
    """唯讀擷取基底。``reference_dsn``＝以本 repo migration 建好的拋棄式庫（只讀其 catalog）。"""
    migrations = _migrations()
    tables = load_order()
    names = [t.name for t in tables]
    with _ro_connect(reference_dsn) as ref:
        ref_rec = ref.execute("SELECT to_regclass('cpbl.schema_migrations')").fetchone()[0]
        ref_files = ([r[0] for r in ref.execute(
            "SELECT filename FROM cpbl.schema_migrations ORDER BY filename").fetchall()]
            if ref_rec else [])
        if ref_files != [m.name for m in migrations]:
            raise SystemExit("reference 庫的 migration 記錄與 repo migrations/ 不一致——先在 reference 上 migrate()")
        ref_cols = {t: _columns(ref.cursor(), t) for t in names}
        seeded = [t for t in names if ref.execute(
            f"SELECT EXISTS (SELECT 1 FROM cpbl.{t})").fetchone()[0]]  # noqa: S608 — 表名來自模組常數
        if seeded:
            raise SystemExit(f"這些表由 migration 播種，不得收進基底（載入會撞主鍵）：{seeded}")
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.csv"):
        old.unlink()
    entries = []
    with _ro_connect(source_dsn) as c:
        cur = c.cursor()
        require_snapshot_txn(cur)
        for s in _SESSION:
            cur.execute(s)
        src_rec = cur.execute("SELECT to_regclass('cpbl.schema_migrations')").fetchone()[0]
        if src_rec:
            recorded = [r[0] for r in cur.execute(
                "SELECT filename FROM cpbl.schema_migrations ORDER BY filename").fetchall()]
            if recorded != [m.name for m in migrations]:
                raise SystemExit("來源庫的 migration 記錄與 repo migrations/ 不一致——停止（#413 規劃 §9）")
            schema_check = {"method": "schema_migrations", "detail": "來源記錄與 repo 逐檔相同"}
        else:
            schema_check = {"method": "columns-vs-reference",
                            "detail": "來源庫沒有 cpbl.schema_migrations；改以入選各表的欄位（名稱＋型別）"
                                      "與 migrate 到最大號的拋棄式庫逐表比對，全數相同"}
        fingerprint = _fingerprint(cur, names)
        for t in tables:
            cols = _columns(cur, t.name)
            if sorted(cols) != sorted(ref_cols[t.name]):
                raise SystemExit(f"{t.name} 欄位與 repo migration 結果不同——停止（#413 規劃 §9）："
                                 f"{sorted(set(cols) ^ set(ref_cols[t.name]))}")
            col_names = [n for n, _ in cols]
            order = _order_by(cur, t.name, col_names)
            select = (f"SELECT {', '.join(col_names)} FROM cpbl.{t.name} WHERE {t.where} "
                      f"ORDER BY {', '.join(order)}")
            buf = io.BytesIO()
            with cur.copy(f"COPY ({select}) TO STDOUT (FORMAT csv, HEADER)") as cp:
                for chunk in cp:
                    buf.write(chunk)
            data = buf.getvalue()
            rows = _csv_rows(data)
            path = out_dir / f"{t.name}.csv"
            path.write_bytes(data)
            entries.append({"table": t.name, "file": path.name, "rows": rows, "bytes": len(data),
                            "sha256": _sha256(data), "columns": col_names, "why": t.why,
                            "selection": t.where})
        if _fingerprint(cur, names) != fingerprint:
            raise SystemExit("擷取期間來源被寫入（指紋改變）——重跑")
        c.rollback()
    manifest = {
        "format": FORMAT,
        "extracted_on": extracted_on,
        "source": "需求方 Mac 本機主庫（docker compose db，埠 5433）唯讀擷取；非 VPS 生產",
        "source_fingerprint": fingerprint,
        "migration_max": migrations[-1].name,
        "schema_check": schema_check,
        "regenerate": "每季重產（需求方裁定 #413 待裁 2）：跨年後以「本季」為準的測試會退回 skip",
        "games": [{"year": y, "kind_code": k, "game_sno": s, "why": w} for y, k, s, w in GAMES],
        "excluded": "哨兵年份 1900／2099、2018/D/110（測試自行寫入）；營運表（refresh_log、ingest runs、alert、shadow）",
        "tables": entries,
    }
    text = json.dumps(manifest, ensure_ascii=False, indent=1) + "\n"
    (out_dir / MANIFEST).write_text(text, encoding="utf-8")
    total = sum(p.stat().st_size for p in out_dir.iterdir() if p.is_file())
    if total > SIZE_LIMIT_BYTES:
        raise SystemExit(f"基底 {total} bytes 超過上限 {SIZE_LIMIT_BYTES}——回報需求方，不硬塞（#413）")
    return manifest


def _csv_rows(data: bytes) -> int:
    return sum(1 for _ in csv.reader(io.StringIO(data.decode("utf-8")))) - 1


# --------------------------------------------------------------------------- 載入器

def read_manifest(fixture_dir: Path = FIXTURE_DIR) -> dict:
    manifest = json.loads((fixture_dir / MANIFEST).read_text(encoding="utf-8"))
    if manifest.get("format") != FORMAT:
        raise SystemExit(f"manifest 格式 {manifest.get('format')!r} 不是 {FORMAT}")
    return manifest


def _manifest_digest(fixture_dir: Path) -> str:
    return _sha256((fixture_dir / MANIFEST).read_bytes())


def _migrate(dsn: str, migrations_dir: Path | None) -> list[str]:
    """以本 repo 的 ``cpbl.db.migrate()`` 套 migration；``migrations_dir`` 只在第一段（≤N）用。"""
    from cpbl import db
    from cpbl.config import settings
    previous = os.environ.get("CPBL_MIGRATIONS_DIR")
    settings.database_url = dsn
    if db._pool is not None:
        db._pool.close()
        db._pool = None
    try:
        if migrations_dir is None:
            os.environ.pop("CPBL_MIGRATIONS_DIR", None)
        else:
            os.environ["CPBL_MIGRATIONS_DIR"] = str(migrations_dir)
        return db.migrate()
    finally:
        if previous is None:
            os.environ.pop("CPBL_MIGRATIONS_DIR", None)
        else:
            os.environ["CPBL_MIGRATIONS_DIR"] = previous
        if db._pool is not None:
            db._pool.close()
            db._pool = None


def load(target_dsn: str, fixture_dir: Path = FIXTURE_DIR) -> dict:
    """把基底載入一個**空的**拋棄式庫：migrate 到 N → COPY → setval → migrate 其餘 → 寫標記。

    任何不相容（欄名、型別、NOT NULL、FK、列數、migration 最大號）都讓這裡失敗並回非零——
    ⛔ 不靜默 skip（#413 驗收 3）。
    """
    import psycopg
    from psycopg import sql

    manifest = read_manifest(fixture_dir)
    refuse_target(target_dsn, games_rows=None)
    with psycopg.connect(target_dsn) as c:
        games = c.execute("SELECT to_regclass('cpbl.games')").fetchone()[0]
        n = c.execute("SELECT count(*) FROM cpbl.games").fetchone()[0] if games else 0
    refuse_target(target_dsn, games_rows=n)

    migrations = _migrations()
    names = [m.name for m in migrations]
    top = manifest["migration_max"]
    if top not in names:
        raise SystemExit(f"manifest 的 migration 最大號 {top} 不在 repo migrations/——基底與 migration 不相容")
    with tempfile.TemporaryDirectory(prefix="cpbl-ci-base-") as tmp:
        for m in migrations[: names.index(top) + 1]:
            shutil.copy2(m, Path(tmp) / m.name)
        first = _migrate(target_dsn, Path(tmp))

    loaded = []
    with psycopg.connect(target_dsn) as c:
        c.execute("SET TimeZone = 'UTC'")
        c.execute("SET DateStyle = 'ISO, YMD'")
        for entry in manifest["tables"]:
            path = fixture_dir / entry["file"]
            data = path.read_bytes()
            if _sha256(data) != entry["sha256"]:
                raise SystemExit(f"{entry['file']} 的 sha256 與 manifest 不符")
            header = next(csv.reader(io.StringIO(data.split(b"\n", 1)[0].decode("utf-8"))))
            stmt = sql.SQL("COPY {} ({}) FROM STDIN (FORMAT csv, HEADER MATCH)").format(
                sql.Identifier("cpbl", entry["table"]), sql.SQL(", ").join(map(sql.Identifier, header)))
            with c.cursor().copy(stmt) as cp:
                cp.write(data)
            got = c.execute(sql.SQL("SELECT count(*) FROM {}").format(
                sql.Identifier("cpbl", entry["table"]))).fetchone()[0]
            if got != entry["rows"]:
                raise SystemExit(f"{entry['table']} 載入 {got} 列，manifest 記 {entry['rows']} 列")
            loaded.append((entry["table"], got))
        # 序列：只對有資料的表、用 max+1（setval 是 STRICT，NULL 會靜默 no-op，故先 COALESCE）。
        seqs = c.execute("""
            SELECT c.relname, a.attname, pg_get_serial_sequence(format('cpbl.%%I', c.relname), a.attname)
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
            WHERE n.nspname = 'cpbl' AND c.relname = ANY (%s)
              AND pg_get_serial_sequence(format('cpbl.%%I', c.relname), a.attname) IS NOT NULL
            ORDER BY 1, 2""", ([e["table"] for e in manifest["tables"]],)).fetchall()
        for table, col, seq in seqs:
            c.execute(sql.SQL("SELECT setval(%s, COALESCE((SELECT max({}) FROM {}) + 1, 1), false)").format(
                sql.Identifier(col), sql.Identifier("cpbl", table)), (seq,))
    rest = _migrate(target_dsn, None)
    marker = f"{MARKER_PREFIX}{FORMAT} manifest-sha256={_manifest_digest(fixture_dir)}"
    with psycopg.connect(target_dsn, autocommit=True) as c:
        dbname = c.execute("SELECT current_database()").fetchone()[0]
        c.execute(sql.SQL("COMMENT ON DATABASE {} IS {}").format(sql.Identifier(dbname), sql.Literal(marker)))
    return {"migrated_to_n": len(first), "loaded": loaded, "migrated_after": rest, "marker": marker}


# --------------------------------------------------------------------------- pytest 端

# conftest 偵測到標記時設成標記字串；測試以 active() 判斷「這是基底，不是正式庫」。
_ACTIVE: str | None = None


def marker_of(dsn: str, *, connect_timeout: int = 2) -> str | None:
    """讀 ``dsn`` 那個庫的 COMMENT（經維護庫 ``postgres``，不連模板庫本身——連著模板就無法複製）。"""
    import psycopg
    from psycopg import conninfo
    dbname = conninfo.conninfo_to_dict(dsn).get("dbname")
    if not dbname:
        return None
    try:
        with psycopg.connect(conninfo.make_conninfo(dsn, dbname="postgres"),
                             connect_timeout=connect_timeout) as c:
            row = c.execute("SELECT shobj_description(oid, 'pg_database') FROM pg_database "
                            "WHERE datname = %s", (dbname,)).fetchone()
    except Exception:  # noqa: BLE001 — 連不上＝沒有基底，交回 conftest 既有的探測流程
        return None
    text = row[0] if row else None
    return text if text and text.startswith(MARKER_PREFIX) else None


def set_active(marker: str | None) -> None:
    global _ACTIVE
    _ACTIVE = marker


def active() -> bool:
    """本次 pytest 的主 DSN 是否為已載入的 CI 基底（不是正式庫）。"""
    return _ACTIVE is not None


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tests/ci_base.py", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="唯讀擷取基底到 tests/fixtures/ci_base/")
    g.add_argument("--source-dsn", required=True)
    g.add_argument("--reference-dsn", required=True, help="已 migrate 到 repo 最大號的拋棄式庫（只讀 catalog）")
    g.add_argument("--out", type=Path, default=FIXTURE_DIR)
    g.add_argument("--extracted-on", default=datetime.now(TAIPEI).date().isoformat())
    ld = sub.add_parser("load", help="把基底載入空的拋棄式庫並寫上標記")
    ld.add_argument("--target-dsn", required=True)
    ld.add_argument("--fixtures", type=Path, default=FIXTURE_DIR)
    args = p.parse_args(argv)
    try:
        if args.cmd == "generate":
            m = generate(args.source_dsn, args.reference_dsn, args.out, args.extracted_on)
            total = sum(e["bytes"] for e in m["tables"])
            print(f"generated {len(m['tables'])} tables, {total} CSV bytes, migration_max={m['migration_max']}")
            for e in m["tables"]:
                print(f"  {e['table']:<34} {e['rows']:>7} rows {e['bytes']:>9} B  {e['sha256']}")
        else:
            r = load(args.target_dsn, args.fixtures)
            print(f"migrated to N: {r['migrated_to_n']} files; after N: {r['migrated_after']}")
            for t, n in r["loaded"]:
                print(f"  {t:<34} {n:>7} rows")
            print(f"marker: {r['marker']}")
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "src"))
    raise SystemExit(main())
