"""#355 WP-S E2：目標場來源觀測紀錄 scoped payload 在**真 PostgreSQL** 上成立（預設 skip）。

需一個拋棄式 database（名稱須含 ``355``、⛔ 不得是 ``cpbl``），在本機 PG 容器內：

    docker exec cpbl-analytics-db-1 createdb -U cpbl cpbl_355_e2_<時間戳>
    BOXPA_REV_355_DATABASE=cpbl_355_e2_<時間戳> uv run pytest tests/test_boxpa_source_revisions_scratch_db_355.py

做法（PLAN-1 §5 E2）：在該 database 先擺「本機」狀態 → 以**真** refresh-cpbl-prod.sh（POSTSEASON_BOXPA_ONLY、
假 ssh 只收 payload）產生 scoped payload，本機讀取由假 docker 轉給這顆真 PG → 把同一 database 換成「production」
狀態（prod max(id) 200 ＞ 序列 last_value 150，即 2026-08-14 地雷區形狀；目標場缺 livelog／scoreboard 列＝G4
窗口形狀）→ 以與腳本相同的 psql 旗標套用 payload。斷言：

* 套用前 `/status` 判定（``_build_game_status``，與 games.py 同一份 SQL 選列）＝``pending_refresh``；
  套用後＝``available``；
* 無 id 碰撞、新列 id 全部 ＞ prod 原 max(id)；去掉矯正 setval 的同一份 payload 必撞 id（負控）；
* 只帶目標場 × livelog／scoreboard（本機的 schedule／advanced 列與非目標場列不出現在 production）；
  非目標場列前後逐位元相同；
* ``boxpa_sync.current_source_revisions``（reconcile 用的 SQL）套用前不等、套用後兩邊相同；
* 第二次套用成功且結果不變（冪等）。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

DB = os.getenv("BOXPA_REV_355_DATABASE", "")
CONTAINER = os.getenv("BOXPA_REV_355_CONTAINER", "cpbl-analytics-db-1")
ROOT = Path(__file__).resolve().parents[1]
KEY = "2026-C-4"
KEY_SQL = "(year, kind_code, game_sno) IN ((2026,'C',4))"
NOT_TARGET = "NOT (year = 2026 AND kind_code = 'C' AND game_sno = 4)"

pytestmark = pytest.mark.skipif(not DB, reason="requires BOXPA_REV_355_DATABASE (throwaway database)")


def _psql_argv() -> list[str]:
    assert "355" in DB and DB != "cpbl", "只在名稱含 355 的拋棄式 database 上跑"
    docker = shutil.which("docker")
    assert docker
    return [docker, "exec", "-i", CONTAINER, "psql", "-X", "-U", "cpbl", "-d", DB]


def _sql(script: str, *, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run([*_psql_argv(), "-q", "-At", "-v", "ON_ERROR_STOP=1"], input=script,
                          capture_output=True, text=True)
    if check:
        assert proc.returncode == 0, proc.stderr
    return proc


def _apply(payload: str) -> subprocess.CompletedProcess:
    """與腳本送 production 時同一組旗標（-v ON_ERROR_STOP=1 -q --single-transaction）。"""
    return subprocess.run([*_psql_argv(), "-v", "ON_ERROR_STOP=1", "-q", "--single-transaction"],
                          input=payload, capture_output=True, text=True)


def _rows(query: str) -> list[dict]:
    out = _sql(f"SELECT COALESCE(json_agg(t), '[]'::json) FROM ({query}) t;").stdout.strip()
    return json.loads(out)


def _status() -> str:
    from cpbl.api.helpers import OFFICIAL_SCHEDULE_ORDER_BY, SOURCE_REVISION_ORDER_BY
    from cpbl.api.routers.games import _build_game_status

    schedule = _rows(
        "SELECT raw_present_status, raw_game_result, raw_game_date, raw_pre_exe_date, payload_hash, "
        "fetched_at, last_seen_at FROM cpbl.game_schedule_status_revisions "
        f"WHERE year=2026 AND kind_code='C' AND game_sno=4 ORDER BY {OFFICIAL_SCHEDULE_ORDER_BY}")
    sources = _rows(
        "SELECT DISTINCT ON (source) source, outcome, row_count, error_code, detail, fetched_at, last_seen_at "
        "FROM cpbl.game_source_revisions WHERE year=2026 AND kind_code='C' AND game_sno=4 "
        f"ORDER BY source, {SOURCE_REVISION_ORDER_BY}")
    return _build_game_status(schedule, {r["source"]: r for r in sources})["play_by_play_availability"]["status"]


def _current():
    from cpbl.ingest import boxpa_sync as bs
    db = bs.Psql(_psql_argv(), label="local")
    return bs.current_source_revisions(db, bs.parse_games(KEY))[KEY]


def _fingerprint(where: str) -> str:
    return _sql("SELECT count(*)||':'||COALESCE(md5(string_agg(x::text, '|' ORDER BY x.id)), '') "
                f"FROM cpbl.game_source_revisions x WHERE {where};").stdout.strip()


_LOCAL = """
INSERT INTO cpbl.game_source_revisions (id, year, kind_code, game_sno, source, source_version, outcome, row_count,
  detail, fetched_at, last_seen_at, seen_count) OVERRIDING SYSTEM VALUE VALUES
 (141, 2026,'C',4,'livelog','live-v1','available',300,'{"n":1}','2026-10-21 22:20:00+08','2026-10-21 22:20:00+08',1),
 (142, 2026,'C',4,'livelog','live-v2','available',349,'{"n":2}','2026-10-21 22:42:20+08','2026-10-21 22:42:20+08',2),
 (143, 2026,'C',4,'scoreboard','sb-v1','available',20,'{}','2026-10-21 22:42:20+08','2026-10-21 22:42:20+08',1),
 (144, 2026,'C',4,'schedule','sched-local','available',1,'{}','2026-10-21 22:40:00+08','2026-10-21 22:40:00+08',1),
 (145, 2026,'C',4,'advanced','adv-local','missing',0,'{}','2026-10-21 22:41:00+08','2026-10-21 22:41:00+08',1),
 (146, 2026,'C',3,'livelog','c3-local-only','available',300,'{}','2026-10-20 22:00:00+08','2026-10-20 22:00:00+08',1);
SELECT setval(pg_get_serial_sequence('cpbl.game_source_revisions','id'), 150, true);
"""

_PROD = """
TRUNCATE cpbl.game_source_revisions;
INSERT INTO cpbl.game_source_revisions (id, year, kind_code, game_sno, source, source_version, outcome, row_count,
  fetched_at, last_seen_at) OVERRIDING SYSTEM VALUE
 SELECT g, 2026, 'C', 1 + (g % 3), 'schedule', 'p' || g, 'available', 1,
        '2026-10-19 21:00:00+08', '2026-10-19 21:00:00+08' FROM generate_series(100, 198) g;
INSERT INTO cpbl.game_source_revisions (id, year, kind_code, game_sno, source, source_version, outcome, row_count,
  fetched_at, last_seen_at) OVERRIDING SYSTEM VALUE VALUES
 (199, 2026,'C',3,'livelog','c3-prod','available',301,'2026-10-20 22:30:00+08','2026-10-20 22:30:00+08'),
 (200, 2026,'C',4,'schedule','sched-prod','available',1,'2026-10-21 22:40:00+08','2026-10-21 22:40:00+08');
-- prod 序列落後 max(id)（2026-08-14 地雷區形狀：151..200 皆已被佔）
SELECT setval(pg_get_serial_sequence('cpbl.game_source_revisions','id'), 150, true);
TRUNCATE cpbl.game_schedule_status_revisions;
INSERT INTO cpbl.game_schedule_status_revisions (year, kind_code, game_season_code, game_sno, raw_present_status,
  raw_game_result, raw_game_date, payload_hash, raw_payload, fetched_at, last_seen_at)
 VALUES (2026,'C','',4,1,'0','2026-10-21','final-hash','{}','2026-10-21 22:40:00+08','2026-10-21 22:40:00+08');
"""


def test_e2_scoped_source_revision_payload_on_real_postgres(tmp_path):
    _sql("DROP SCHEMA IF EXISTS cpbl CASCADE; CREATE SCHEMA cpbl;")
    _sql((ROOT / "migrations" / "061_game_source_revisions.sql").read_text(encoding="utf-8"))
    _sql(_LOCAL)
    local_current = _current()
    assert local_current["livelog"][0] == "live-v2" and local_current["scoreboard"][0] == "sb-v1"

    # 1) 真腳本產生 payload（本機讀取轉給這顆真 PG；假 ssh 只收下 payload、不套用）。
    from tests.test_boxpa_sync_mode import _run
    result, calls, _ = _run(tmp_path / "gen", POSTSEASON_BOXPA_GAMES=KEY, POSTSEASON_BOXPA_PARTS="box",
                            STUB_KEYS_SQL=KEY_SQL, STUB_PA_GAMES=KEY,
                            STUB_REV_REAL_PSQL=json.dumps(_psql_argv()))
    assert result.returncode == 0, result.stdout + result.stderr
    (payload,) = [c["stdin"] for c in calls("ssh") if "INSERT INTO cpbl.game_source_revisions " in c["stdin"]]
    (tmp_path / "payload.sql").write_text(payload, encoding="utf-8")

    # 2) 換成 production 狀態（G4 窗口：目標場只有 schedule 列，沒有 livelog／scoreboard）。
    _sql(_PROD)
    assert _status() == "pending_refresh"
    assert _current() != local_current
    before_other = _fingerprint(NOT_TARGET)

    # 3) 負控：去掉矯正 setval 的同一份 payload → 必撞 id（地雷區 151..200）。
    no_fix = "\n".join(line for line in payload.splitlines() if "setval" not in line) + "\n"
    bad = _apply(no_fix)
    assert bad.returncode != 0 and "duplicate key" in bad.stderr, bad.stderr

    # 4) 套用真 payload：成功、無碰撞，/status 轉 available，reconcile 判兩邊相同。
    ok = _apply(payload)
    assert ok.returncode == 0, ok.stderr
    assert _status() == "available"
    assert _current() == local_current
    target = _rows("SELECT id, source, source_version FROM cpbl.game_source_revisions "
                   f"WHERE {KEY_SQL} ORDER BY source, source_version")
    assert [(r["source"], r["source_version"]) for r in target] == [
        ("livelog", "live-v1"), ("livelog", "live-v2"), ("schedule", "sched-prod"), ("scoreboard", "sb-v1")]
    assert all(r["id"] > 200 for r in target if r["source"] != "schedule"), target
    assert _fingerprint(NOT_TARGET) == before_other, "非目標場列逐位元不變（本機 C3 列不得送上）"
    assert not _rows("SELECT 1 FROM cpbl.game_source_revisions WHERE source_version IN "
                     "('sched-local','adv-local','c3-local-only')")
    full = _rows("SELECT source_version, outcome, row_count, detail, fetched_at, last_seen_at, seen_count "
                 f"FROM cpbl.game_source_revisions WHERE {KEY_SQL} AND source <> 'schedule' ORDER BY source_version")
    assert [(r["source_version"], r["row_count"], r["seen_count"], r["detail"]) for r in full] == [
        ("live-v1", 300, 1, {"n": 1}), ("live-v2", 349, 2, {"n": 2}), ("sb-v1", 20, 1, {})], "整欄鏡像本機"

    # 5) 冪等：第二次套用成功、結果不變。
    after_first = _fingerprint("TRUE")
    again = _apply(payload)
    assert again.returncode == 0, again.stderr
    assert _fingerprint("TRUE") == after_first
    assert _status() == "available"

    _sql("DROP SCHEMA cpbl CASCADE;")
