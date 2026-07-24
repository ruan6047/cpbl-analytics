"""GAME-RECAP-PA1-EXPAND1 migration guard.

純文字結構斷言（不需 DB）：守住 066 為 additive／idempotent，且承載契約與
TAXONOMY1 v1.0.0 state machine 輸出所需的關鍵 constraint／index。行為（FK、
unique、CHECK、cascade）由 fresh-DB rehearsal 驗證，見 handoff 報告。
"""

from __future__ import annotations

from pathlib import Path

_MIGRATION = Path(__file__).parents[1] / "migrations" / "066_game_recap_pa_expand.sql"


def _sql() -> str:
    return _MIGRATION.read_text(encoding="utf-8")


def test_all_five_contract_objects_are_created_idempotently() -> None:
    sql = _sql()
    for table in (
        "game_recap_source_revisions",
        "game_recap_builds",
        "game_plate_appearances",
        "game_pa_events",
        "game_pa_pitch_mappings",
    ):
        assert f"CREATE TABLE IF NOT EXISTS cpbl.{table}" in sql


def test_every_index_is_guarded_if_not_exists() -> None:
    sql = _sql()
    # 每個 CREATE INDEX 都必須帶 IF NOT EXISTS（migrate() 每次全跑須冪等）
    for line in sql.splitlines():
        stripped = line.strip().upper()
        if stripped.startswith("CREATE") and "INDEX" in stripped:
            assert "IF NOT EXISTS" in stripped, line


def test_migration_is_purely_additive() -> None:
    sql = _sql().upper()
    # additive expand：不得刪表/欄、不得改動既有 migration 的表
    assert "DROP TABLE" not in sql
    assert "DROP COLUMN" not in sql
    assert "ALTER TABLE CPBL.GAME_LIVELOG" not in sql
    assert "ALTER TABLE CPBL.PITCH_TRACKING" not in sql
    assert "ALTER TABLE CPBL.GAME_SOURCE_REVISIONS" not in sql  # 061 物件不得改寫


def test_source_revision_manifest_carries_provenance() -> None:
    sql = _sql()
    assert "source_sha256" in sql
    assert "parser_version" in sql
    assert "max_source_key" in sql
    assert "CHECK (source_kind IN ('livelog', 'tracking'))" in sql
    # 唯一鍵：game key + source kind + 內容 hash（同內容重抓 → 同一 manifest）
    assert "UNIQUE (year, kind_code, game_sno, source_kind, source_sha256)" in sql


def test_build_pins_versions_and_enforces_single_published_per_game() -> None:
    sql = _sql()
    assert "builder_version" in sql
    assert "taxonomy_version" in sql  # builder 必須 pin taxonomy（TAXONOMY §9）
    # current canonical：每場至多一個 published build
    assert "uq_game_recap_builds_one_published" in sql
    assert "WHERE state = 'published'" in sql


def test_pa_carries_state_machine_and_stable_id() -> None:
    sql = _sql()
    # 穩定 pa_id 索引（非唯一：跨 build 相同）
    assert "idx_game_pa_pa_id" in sql
    # 唯一鍵 game key + build + pa_index
    assert "UNIQUE (year, kind_code, game_sno, build_id, pa_index)" in sql
    # TAXONOMY island_classes → PA state 值域
    for state in ("ready", "unreliable", "truncated", "non_pa", "reconciliation_required"):
        assert f"'{state}'" in sql
    # 契約固定的 public tracking_availability 值域
    for avail in (
        "available",
        "advanced_pending",
        "no_equipment",
        "source_missing",
        "mapping_failed",
        "source_error",
    ):
        assert f"'{avail}'" in sql


def test_pitch_mapping_prevents_double_binding_per_revision() -> None:
    sql = _sql()
    # 同一版本每顆球至多綁定一個 PA（契約紅燈）；pitch local key 對齊 pitch_tracking PK
    assert (
        "UNIQUE (source_revision_id, year, kind_code, game_sno, pitcher_acnt, pitch_cnt)"
        in sql
    )
    assert "CHECK (mapping_state IN ('mapped', 'failed'))" in sql
