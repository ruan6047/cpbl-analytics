"""#353 WP1：PA 五表每日同步改為逐場增量替換（取代 TRUNCATE＋全量重灌）。

研究 2：舊的 ``TRUNCATE`` 在單一交易內持 ACCESS EXCLUSIVE 約 7 分 20 秒，讀 PA 表的請求整段被擋、
連線池 8 條被占滿。新做法：比對每場簽章，只對有差異的場在單交易內「子→父 DELETE 目標鍵 →
父→子 INSERT」（與晚間鏈 ``boxpa_sync.build_pa_payload`` 同一個產生器），事後全族對帳 fail-closed。

本檔零 DB：以假 Psql 驗判定、形狀與守衛。可拋棄 DB 上的「同步交易進行中讀者 1s 內返回」證據
在 ``~/.wf-evidence/cpbl-analytics/353/exec-1/``（規劃 §6 E0）。
"""

from __future__ import annotations

import io
import re

import pytest

from cpbl.ingest import boxpa_sync as bs
from cpbl.ingest import pa_incremental as pi

K = bs.GameKey


class FakePsql:
    """``read`` 依 SQL 形狀回傳簽章或全族摘要；``copy_out*`` 回傳可辨識的假 COPY 列。"""

    def __init__(self, sigs: dict[K, str] | None = None, family: list[list[str]] | None = None):
        self.sigs = sigs or {}
        self.family = family or []
        self.reads: list[str] = []
        self.copies: list[str] = []

    def read(self, sql: str) -> list[list[str]]:
        self.reads.append(sql)
        if "string_agg(b::text" in sql:
            return [[str(k.year), k.kind_code, str(k.game_sno), v] for k, v in self.sigs.items()]
        if "'published'" in sql:
            return self.family
        raise AssertionError(f"unexpected read: {sql[:80]}")

    def _rows(self, sql: str) -> str:
        table = re.search(r"FROM cpbl\.(\w+)", sql).group(1)
        return f"{table}-row-1\t1\n{table}-row-2\t2\n"

    def copy_out(self, sql: str) -> str:
        self.copies.append(sql)
        return self._rows(sql)

    def copy_out_to(self, sql: str, out) -> None:
        self.copies.append(sql)
        out.write(self._rows(sql))


# --------------------------------------------------------------------------- 差異判定


def test_diff_covers_changed_prod_only_and_local_only_games() -> None:
    local = {K(2026, "A", 1): "same", K(2026, "A", 2): "new-build", K(2026, "D", 9): "only-local"}
    prod = {K(2026, "A", 1): "same", K(2026, "A", 2): "old-build", K(2025, "C", 3): "only-prod"}
    assert pi.diff_games(local, prod) == [K(2025, "C", 3), K(2026, "A", 2), K(2026, "D", 9)]


def test_state_flip_changes_the_signature_sql_input() -> None:
    """``pa_build.py`` 把 published 改成 superseded 時 build_id 不變——簽章必須含整列（含 state）。"""
    sql = pi.SIGNATURE_SQL
    assert "string_agg(b::text" in sql, "builds 簽章取整列文字（含 state）"
    assert "string_agg(id::text" in sql, "source_revisions 取 id 集合"
    for gu in ("TimeZone = 'UTC'", "DateStyle = 'ISO, YMD'", "extra_float_digits = 1",
               "IntervalStyle = 'postgres'"):
        assert gu in sql, f"列文字依 session 設定而變，兩端必須固定：{gu}"


def test_signatures_parse_and_validate_keys() -> None:
    db = FakePsql({K(2026, "D", 229): "x"})
    assert pi.signatures(db) == {K(2026, "D", 229): "x"}


@pytest.mark.parametrize("row", [
    ["2026", "AA", "1", "x"], ["2026", "a", "1", "x"], ["20x6", "A", "1", "x"],
    ["2026", "A", "1;DROP", "x"], ["2026", "A", "1"],
])
def test_signature_rows_with_unexpected_keys_fail_closed(row) -> None:
    class Db(FakePsql):
        def read(self, sql):
            return [row]

    with pytest.raises(bs.SyncError) as e:
        pi.signatures(Db())
    assert e.value.code == bs.EXIT_SELF_CHECK


# --------------------------------------------------------------------------- payload


def _incremental(local_sigs, prod_sigs) -> tuple[str, FakePsql]:
    local, prod, out = FakePsql(local_sigs), FakePsql(prod_sigs), io.StringIO()
    pi.write_payload(local, prod, out)
    return out.getvalue(), local


def test_no_difference_sends_nothing() -> None:
    payload, local = _incremental({K(2026, "A", 1): "s"}, {K(2026, "A", 1): "s"})
    assert payload == ""
    assert local.copies == []


def test_incremental_payload_is_the_boxpa_shape_scoped_to_diff_games() -> None:
    keys = [K(2026, "A", 2), K(2026, "D", 9)]
    payload, _ = _incremental({keys[0]: "n", keys[1]: "x", K(2026, "A", 1): "s"},
                              {keys[0]: "o", K(2026, "A", 1): "s"})
    bs.assert_pa_payload(payload, keys)  # 晚間鏈同一支守衛，D 與超過 7 場都不經 parse_games
    scope = bs.keys_sql(keys)
    assert f"WHERE {scope};" in payload
    assert "(2026,'A',1)" not in payload, "簽章相同的場不得被刪"
    assert "BOXPA_CLOSURE" in payload, "production 端 FK 閉包守衛"
    assert "SET LOCAL lock_timeout" in payload and "SET LOCAL statement_timeout" in payload
    assert "BOXPA_COUNT" in payload, "寫入後列數自檢"


def test_incremental_payload_has_no_truncate_cascade_or_setval() -> None:
    payload, _ = _incremental({K(2026, "A", 2): "n"}, {})
    for forbidden in ("TRUNCATE", "CASCADE", "setval"):
        assert forbidden not in payload
    assert "OVERRIDING SYSTEM VALUE" in payload, "id 一律鏡像本機（FIX1 不變量）"
    assert "ON CONFLICT" not in payload, "⛔ 不得改用 id 當衝突鍵"


def test_more_than_seven_games_and_d_games_are_allowed_without_touching_parse_games() -> None:
    local = {K(2026, "D", n): "x" for n in range(1, 23)}
    payload, _ = _incremental(local, {})
    bs.assert_pa_payload(payload, sorted(local))
    assert bs.MAX_GAMES == 7 and bs.GAME_KEY_RE.pattern == r"^(\d{4})-([AEC])-(\d{1,3})$", \
        "⛔ 不得為每日增量放寬晚間鏈的 parse_games 防呆"


def test_runaway_difference_refuses_instead_of_becoming_an_implicit_full_resync() -> None:
    """差異場異常多＝簽章失準的訊號；⛔ 不得在每日鏈自動變成等同全量模式的大量 DELETE。"""
    local = {K(2026, "A", n): "x" for n in range(pi.MAX_INCREMENTAL_GAMES + 1)}
    local_db, prod_db, out = FakePsql(local), FakePsql({}), io.StringIO()
    with pytest.raises(bs.SyncError) as e:
        pi.write_payload(local_db, prod_db, out)
    assert e.value.code == bs.EXIT_SELF_CHECK
    assert out.getvalue() == "" and local_db.copies == []


def test_full_mode_uses_the_same_generator_without_truncate() -> None:
    local, prod, out = FakePsql({K(2026, "A", 1): "s"}), FakePsql({K(2026, "A", 1): "s"}), io.StringIO()
    pi.write_payload(local, prod, out, full=True)
    payload = out.getvalue()
    bs.assert_pa_lines(payload.splitlines(), pi.FULL_SCOPE)
    assert "TRUNCATE" not in payload and "CASCADE" not in payload
    assert [f"DELETE FROM cpbl.{t} WHERE TRUE;" for t in reversed(bs.PA_TABLES)] == \
        [ln for ln in payload.splitlines() if ln.startswith("DELETE ")]
    assert f"SET LOCAL statement_timeout = '{pi.FULL_STATEMENT_TIMEOUT}';" in payload
    assert prod.reads == [], "全量模式不需比對簽章"


def test_assert_rejects_unscoped_delete_and_truncate() -> None:
    keys = [K(2026, "A", 2)]
    payload, _ = _incremental({keys[0]: "n"}, {})
    bad = payload.replace(f"DELETE FROM cpbl.game_pa_events WHERE {bs.keys_sql(keys)};",
                          "DELETE FROM cpbl.game_pa_events WHERE TRUE;")
    with pytest.raises(bs.SyncError):
        bs.assert_pa_payload(bad, keys)
    with pytest.raises(bs.SyncError):
        bs.assert_pa_payload("TRUNCATE cpbl.game_pa_events;\n" + payload, keys)


def test_build_pa_payload_output_is_unchanged_by_the_streaming_refactor() -> None:
    """晚間鏈的 payload 逐位元不變：以重構前的演算法（逐字搬進測試）當黃金值比對。"""
    keys = bs.parse_games("2026-C-2,2026-A-355")

    def legacy(local, keys):
        scope = bs.keys_sql(keys)
        lines = ["SET LOCAL statement_timeout = '300s';", "SET LOCAL lock_timeout = '10s';",
                 "DO $boxpa$ BEGIN", f"  IF EXISTS ({bs.closure_violations_sql(keys)}) THEN",
                 "    RAISE EXCEPTION 'BOXPA_CLOSURE production 端目標場閉包不成立（不刪不寫）';",
                 "  END IF;", "END $boxpa$;"]
        for t in reversed(bs.PA_TABLES):
            lines.append(f"DELETE FROM cpbl.{t} WHERE {scope};")
        checks = []
        for t in bs.PA_TABLES:
            stg = bs._PA_STAGE[t]
            data = local.copy_out(f"SELECT * FROM cpbl.{t} WHERE {scope}")
            lines.append(f"CREATE TEMP TABLE {stg} (LIKE cpbl.{t} INCLUDING DEFAULTS) ON COMMIT DROP;")
            lines.append(f"COPY {stg} FROM stdin;")
            if data.strip():
                lines.append(data.rstrip("\n"))
            lines.append("\\.")
            lines.append(f"DO $boxpa$ BEGIN IF EXISTS (SELECT 1 FROM {stg} WHERE NOT {scope}) THEN "
                         f"RAISE EXCEPTION 'BOXPA_SCOPE {t} 暫存含目標外的列'; END IF; END $boxpa$;")
            override = " OVERRIDING SYSTEM VALUE" if t in bs._PA_IDENTITY else ""
            lines.append(f"INSERT INTO cpbl.{t}{override} SELECT * FROM {stg};")
            checks.append(f"(SELECT count(*) FROM cpbl.{t} WHERE {scope}) <> (SELECT count(*) FROM {stg})")
        lines.append("DO $boxpa$ BEGIN IF " + " OR ".join(checks) + " THEN "
                     "RAISE EXCEPTION 'BOXPA_COUNT 寫入後列數與暫存不符'; END IF; END $boxpa$;")
        return "\n".join(lines) + "\n"

    assert bs.build_pa_payload(FakePsql(), keys) == legacy(FakePsql(), keys)


# --------------------------------------------------------------------------- 全族對帳


def _family(revisions="5000", rev_max="9001", published_md5="abc") -> list[list[str]]:
    return [["game_recap_source_revisions", revisions, rev_max],
            ["game_recap_builds", "13170", ""],
            ["game_plate_appearances", "1019705", "2000000"],
            ["game_pa_events", "4108278", "5000000"],
            ["game_pa_pitch_mappings", "292319", "400000"],
            ["published", "4510", published_md5]]


def test_family_reconcile_equal() -> None:
    m = pi.reconcile_family(FakePsql(family=_family()), FakePsql(family=_family()))
    assert m["ok"] is True
    assert set(m["tables"]) == {*bs.PA_TABLES, "published"}


@pytest.mark.parametrize("prod", [
    _family(revisions="5001"), _family(rev_max="9002"), _family(published_md5="zzz"),
])
def test_family_reconcile_detects_count_max_id_and_published_set_drift(prod) -> None:
    m = pi.reconcile_family(FakePsql(family=_family()), FakePsql(family=prod))
    assert m["ok"] is False


def test_family_reconcile_fails_closed_when_a_table_is_missing() -> None:
    m = pi.reconcile_family(FakePsql(family=_family()), FakePsql(family=_family()[:-1]))
    assert m["ok"] is False


def test_family_sql_covers_counts_max_ids_and_published_builds() -> None:
    sql = pi.FAMILY_SQL
    for t, idcol in pi.IDENTITY_COLUMN.items():
        assert f"max({idcol})" in sql and f"FROM cpbl.{t}" in sql
    assert "state = 'published'" in sql
