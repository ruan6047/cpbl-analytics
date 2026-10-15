"""#287 隊伍比較隔離 DB 演練共用（opt-in）。

卡號隔離資源（本卡 Resource 欄）：容器 cpbl287-pg 127.0.0.1:55287 的 cpbl_test_287（本機角色）與
cpbl_test_287_prod（生產角色）。cpbl_test_287 預先以本機共享 cpbl 2025/2026 真實資料唯讀匯入
（games／batting_gamelog／pitching_gamelog／完賽證據／官方排程狀態／team_standings／異動訊號），
⛔ 不自造樣本；變異一律是對真實列的單點改動，並在測試結束還原。

環境變數：CPBL287_TEST_DSN／CPBL287_PROD_TEST_DSN（psycopg），
         CPBL287_LOCAL_PSQL／CPBL287_PROD_PSQL（例 "docker exec -i cpbl287-pg psql -U cpbl287 -d cpbl_test_287"）。
"""

from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

LOCAL_DB = ("127.0.0.1", "55287", "cpbl_test_287")
PROD_DB = ("127.0.0.1", "55287", "cpbl_test_287_prod")
TABLES = ("team_comparison_current", "team_comparison_row", "team_comparison_build")


def isolated_dsn(env: str, expected: tuple[str, str, str]) -> str:
    """opt-in DSN；未設＝skip（⛔ skip 不算通過），設了但不是本卡資源＝fail。"""
    dsn = os.environ.get(env)
    if not dsn:
        pytest.skip(f"{env} 未設（#287 隔離 DB 演練為 opt-in）")
    d = conninfo_to_dict(dsn)
    if (d.get("host"), str(d.get("port")), d.get("dbname")) != expected:
        pytest.fail(f"{env} 不在 #287 隔離資源 {expected}", pytrace=False)
    return dsn


def psql_cmd(env: str, dbname: str) -> str:
    cmd = os.environ.get(env)
    if not cmd:
        pytest.skip(f"{env} 未設（#287 同步演練為 opt-in）")
    if "cpbl287-pg" not in cmd or f"-d {dbname}" not in cmd:
        pytest.fail(f"{env} 不在 #287 隔離資源（需 cpbl287-pg 與 -d {dbname}）", pytrace=False)
    return cmd


def connector(dsn: str):
    def _connect():
        return psycopg.connect(dsn)
    return _connect


def reset_summary(dsn: str) -> None:
    """清空本卡三表（只限隔離庫）：暫停不可變觸發器 → TRUNCATE → 恢復。"""
    with psycopg.connect(dsn, autocommit=True) as c:
        db = c.execute("SELECT current_database()").fetchone()[0]
        assert db in (LOCAL_DB[2], PROD_DB[2]), db
        with c.transaction():
            c.execute("ALTER TABLE cpbl.team_comparison_build DISABLE TRIGGER USER")
            c.execute("ALTER TABLE cpbl.team_comparison_row DISABLE TRIGGER USER")
            c.execute("TRUNCATE " + ", ".join(f"cpbl.{t}" for t in TABLES))
            c.execute("ALTER TABLE cpbl.team_comparison_build ENABLE TRIGGER USER")
            c.execute("ALTER TABLE cpbl.team_comparison_row ENABLE TRIGGER USER")


def require_real_samples(dsn: str) -> None:
    """匯入的真實樣本必須在（2025／2026 A 各 360 場、gamelog 非空）；不在就 fail 不 skip。"""
    with psycopg.connect(dsn) as c:
        n = dict(c.execute("SELECT year, count(*) FROM cpbl.games WHERE kind_code='A' AND year IN (2025, 2026) "
                           "GROUP BY year").fetchall())
        bat = c.execute("SELECT count(*) FROM cpbl.batting_gamelog WHERE year IN (2025, 2026)").fetchone()[0]
    if n != {2025: 360, 2026: 360} or bat == 0:
        pytest.fail(f"cpbl_test_287 尚未匯入真實樣本（games={n} batting={bat}）；先跑 evidence/scripts/import_samples.sh",
                    pytrace=False)


@contextmanager
def mutated(dsn: str, sql: str, params: tuple, restore_sql: str, restore_params: tuple):
    """對真實列做單點變異並在離開時還原（只限隔離庫）。"""
    with psycopg.connect(dsn) as c:
        assert c.execute("SELECT current_database()").fetchone()[0] == LOCAL_DB[2]
        c.execute(sql, params)
    try:
        yield
    finally:
        with psycopg.connect(dsn) as c:
            c.execute(restore_sql, restore_params)
