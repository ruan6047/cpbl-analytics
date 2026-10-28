"""`refresh-cpbl-prod.sh` 的 #344 同步補洞：`mirror_table` 整表鏡像＋三張新 sync_table。

沿用 `tests/test_prod_sync_revision_seq.py` 的真腳本 harness（假 ssh／docker，零 DB、零網路），
以生產路徑 `SKIP_SCRAPE=1 WITH_DETAIL=1` 執行，逐份檢查送往 ssh 的 payload。

斷言對應規劃（#344 plan-1 §7）的風險：TRUNCATE 只作用於目標表、identity 表帶 OVERRIDING、
本機 0 列拒寫、新 sync_table 欄位清單與 migration schema 一致。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_prod_sync_revision_seq import SCRIPT, _payload_containing, _run_refresh

ROOT = Path(__file__).parents[1]

MIRROR_TABLES = {"championship_members": False, "box_pitching_revisions": True,
                 "game_livelog_extra": False}

# 新增 sync_table 的表 → 定義該表的 migration（CI 無 DB，欄位一致性以 migration DDL 對照）。
NEW_SYNC_TABLES = {
    "player_transactions": "035_player_transactions.sql",
    "game_completion_evidence": "070_game_completion_evidence.sql",
    "fielding_seasons": "001_init.sql",
}


@pytest.fixture(scope="module")
def baseline_run(tmp_path_factory: pytest.TempPathFactory) -> tuple:
    result, calls = _run_refresh(tmp_path_factory.mktemp("mirror-baseline"))
    assert result.returncode == 0, f"harness 未跑完：rc={result.returncode}\n{result.stderr}"
    return result, calls


def _statements(payload: str) -> list[str]:
    """COPY 資料段以外的行。"""
    out, in_copy = [], False
    for line in payload.splitlines():
        if in_copy:
            in_copy = line != "\\."
            continue
        if line.startswith("COPY "):
            in_copy = True
        out.append(line)
    return out


@pytest.mark.parametrize(("table", "identity"), MIRROR_TABLES.items())
def test_mirror_truncates_only_its_own_table_then_inserts(baseline_run, table, identity) -> None:
    _, calls = baseline_run
    payload = _payload_containing(calls, f"TRUNCATE cpbl.{table};")
    stmts = _statements(payload)

    assert [s for s in stmts if s.startswith("TRUNCATE")] == [f"TRUNCATE cpbl.{table};"]
    assert "CASCADE" not in payload.upper()
    inserts = [s for s in stmts if s.startswith("INSERT INTO")]
    assert inserts == [
        f"INSERT INTO cpbl.{table} "
        f"{'OVERRIDING SYSTEM VALUE ' if identity else ''}SELECT * FROM _mirror_stg;"
    ], inserts
    # 順序：TRUNCATE → 暫存 COPY → INSERT（同一份 payload＝同一個 --single-transaction）。
    i_trunc = stmts.index(f"TRUNCATE cpbl.{table};")
    i_copy = next(i for i, s in enumerate(stmts) if s.startswith("COPY _mirror_stg "))
    i_ins = stmts.index(inserts[0])
    assert i_trunc < i_copy < i_ins
    if identity:
        # 鏡像 id：沿用 `_stage`，dump 的 setval 保留（與 OVERRIDING 帶入的本機 id 一致）。
        assert "pg_catalog.setval" in payload


def test_mirror_payloads_are_separate_ssh_calls_with_single_transaction(baseline_run) -> None:
    _, calls = baseline_run
    for table in MIRROR_TABLES:
        hits = [c for c in calls if f"TRUNCATE cpbl.{table};" in c["stdin"]]
        assert len(hits) == 1, table
        assert "--single-transaction" in hits[0]["argv"][-1]
        assert "ON_ERROR_STOP=1" in hits[0]["argv"][-1]


def test_box_mirror_runs_only_in_detail_chain(tmp_path: Path) -> None:
    result, calls = _run_refresh(tmp_path, with_detail=False)
    assert result.returncode == 0, result.stderr
    assert not [c for c in calls if "TRUNCATE cpbl.box_pitching_revisions;" in c["stdin"]]
    assert _payload_containing(calls, "TRUNCATE cpbl.championship_members;")


def test_mirror_refuses_when_local_table_is_empty(tmp_path: Path) -> None:
    """本機 0 列 → exit 67，且任何 TRUNCATE 都沒有送出。"""
    result, calls = _run_refresh(tmp_path, STUB_MIRROR_COUNT="0")

    assert result.returncode == 67
    assert "mirror_table championship_members" in result.stderr
    assert "生產未被觸碰" in result.stderr
    assert not [c for c in calls if "TRUNCATE" in c["stdin"].upper()
                and "_mirror_stg" in c["stdin"]]


def test_mirror_refuses_when_local_count_is_unreadable(tmp_path: Path) -> None:
    result, calls = _run_refresh(tmp_path, STUB_MIRROR_COUNT="")

    assert result.returncode == 67
    assert not [c for c in calls if "_mirror_stg" in c["stdin"]]


# ── #357 game_livelog_extra：完整鏈、緊接 game_livelog；本機 0 列略過不清空 ──────────
def test_livelog_extra_mirror_follows_livelog_in_detail_chain(baseline_run) -> None:
    _, calls = baseline_run
    i_ll = next(i for i, c in enumerate(calls)
                if "INSERT INTO cpbl.game_livelog AS tgt SELECT * FROM _stg " in c["stdin"])
    i_x = next(i for i, c in enumerate(calls) if "TRUNCATE cpbl.game_livelog_extra;" in c["stdin"])
    assert i_ll < i_x


def test_livelog_extra_not_mirrored_without_detail(tmp_path: Path) -> None:
    result, calls = _run_refresh(tmp_path, with_detail=False)
    assert result.returncode == 0, result.stderr
    assert not [c for c in calls if "game_livelog_extra" in c["stdin"]]


def test_livelog_extra_empty_local_is_skipped_not_truncated(tmp_path: Path) -> None:
    """本機 0 列（回補前／當日無同號組）：略過、不 TRUNCATE prod，整條鏈照常跑完。"""
    result, calls = _run_refresh(tmp_path, STUB_COUNT_game_livelog_extra="0")
    assert result.returncode == 0, result.stderr
    assert "game_livelog_extra：本機 0 列，略過（不清空 prod）" in result.stdout
    assert not [c for c in calls if "game_livelog_extra" in c["stdin"]]
    assert _payload_containing(calls, "TRUNCATE cpbl.championship_members;")


def test_livelog_extra_unreadable_count_still_fails_closed(tmp_path: Path) -> None:
    """列數讀不到≠0 列：交給 mirror_table 的 exit 67，不略過。"""
    result, calls = _run_refresh(tmp_path, STUB_COUNT_game_livelog_extra="")
    assert result.returncode == 67
    assert "mirror_table game_livelog_extra" in result.stderr
    assert not [c for c in calls if "TRUNCATE cpbl.game_livelog_extra;" in c["stdin"]]


def _sync_table_calls() -> dict[str, tuple[list[str], list[str]]]:
    joined = re.sub(r"\\\n\s*", " ", SCRIPT.read_text(encoding="utf-8"))
    out = {}
    for table, pk, rest in re.findall(r'^\s*sync_table\s+(\w+)\s+"([^"]+)"\s*(.*)$', joined, re.M):
        out[table] = (pk.split(","), [x for x in rest.split() if re.fullmatch(r"\w+", x)])
    return out


def _migration_columns(table: str, migration: str) -> tuple[list[str], list[str]]:
    sql = (ROOT / "migrations" / migration).read_text(encoding="utf-8")
    m = re.search(rf"CREATE TABLE IF NOT EXISTS cpbl\.{table} \((.*?)\n\);", sql, re.S)
    assert m, f"{migration} 找不到 cpbl.{table} 的 CREATE TABLE"
    body = re.sub(r"--[^\n]*", "", m.group(1))
    pk_m = re.search(r"PRIMARY KEY \(([^)]*)\)", body)
    assert pk_m, table
    cols = []
    for part in body.replace(pk_m.group(0), "").split(","):
        part = part.strip()
        if not part or part.upper().startswith("PRIMARY KEY") or not re.match(r"\w", part):
            continue
        cols.append(part.split()[0])
    return [c.strip() for c in pk_m.group(1).split(",")], cols


@pytest.mark.parametrize(("table", "migration"), NEW_SYNC_TABLES.items())
def test_new_sync_table_lists_match_migration_schema(table, migration) -> None:
    """CI 無 DB：以建表 migration 對照（之後無 ALTER ADD COLUMN；執行時另有 sync_table 欄位守衛）。"""
    pk, cols = _sync_table_calls()[table]
    mig_pk, mig_cols = _migration_columns(table, migration)

    assert pk == mig_pk
    assert set(pk) | set(cols) == set(mig_cols), (sorted(set(mig_cols) - set(pk) - set(cols)),
                                                  sorted(set(pk) | set(cols) - set(mig_cols)))
    for path in sorted((ROOT / "migrations").glob("*.sql")):
        assert not re.search(rf"ALTER TABLE (IF EXISTS )?cpbl\.{table}\b[^;]*ADD COLUMN",
                             path.read_text(encoding="utf-8"), re.I), path.name


@pytest.mark.parametrize("table", NEW_SYNC_TABLES)
def test_new_sync_tables_are_sent_in_production_chain(baseline_run, table) -> None:
    _, calls = baseline_run
    payload = _payload_containing(calls, f"INSERT INTO cpbl.{table} AS tgt SELECT * FROM _stg ")
    assert "COPY _stg " in payload
    assert "TRUNCATE" not in payload.upper()


def test_tables_judged_unneeded_stay_unsynced() -> None:
    """#344 裁定 team_roster／person_history 不需要：不得出現在任何同步呼叫。"""
    text = SCRIPT.read_text(encoding="utf-8")
    for table in ("team_roster", "person_history"):
        assert not re.search(rf"^\s*(sync_table|mirror_table|sync_revision_table)\s+{table}\b",
                             text, re.M), table
