"""#353 規劃 r4：PA 五表全量（及 >1 批的增量）改為逐批小交易＋批間限速。

研究 3：10/28 全量是 4,513 場、1,445,834,586 bytes 的單一交易，期間 1 vCPU 被吃滿（sar %user 93.78、
%idle 0），哨兵量到 recap-wp 6.21s。改法：場次鍵切成每批 ``PA_BATCH_GAMES`` 場，每批＝現行增量
payload（閉包守衛＋列數自檢、單交易），批後暫停＝該批送出耗時 × 比例（不少於下限），最後一批後不停；
全部批次成功才由 shell 做一次全族對帳；任一批失敗即停、不送後續批。

本檔零 DB：假 Psql／假送出端驗切批、鍵集合、暫停與失敗即停；增量 ≤ 一批時以 34aa6dd4 產生的
payload sha256 當黃金值（PLAN-r4 §6 第 5 項）。可拋棄 DB 上的實跑證據在
``~/.wf-evidence/cpbl-analytics/353/exec-2/``。
"""

from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path

import pytest

from cpbl.ingest import boxpa_sync as bs
from cpbl.ingest import pa_incremental as pi

K = bs.GameKey


class GoldenPsql:
    """簽章由 ``sigs`` 給；``copy_out_to`` 回可辨識、含 NULL 與跳脫字元的假 COPY 列。

    與 34aa6dd4 黃金值產生器（exec-2 證據 ``golden_old.py``）逐字同一組回應；改了這裡黃金值就失效。"""

    def __init__(self, sigs: dict[K, str] | None = None, keys_rows: list[list[str]] | None = None):
        self.sigs = sigs or {}
        self.keys_rows = keys_rows or []
        self.reads: list[str] = []
        self.copies: list[str] = []

    def read(self, sql: str) -> list[list[str]]:
        self.reads.append(sql)
        if "string_agg(b::text" in sql:
            return [[str(k.year), k.kind_code, str(k.game_sno), v] for k, v in self.sigs.items()]
        if sql == pi.FULL_KEYS_SQL:
            return self.keys_rows
        raise AssertionError(f"unexpected read: {sql[:80]}")

    def copy_out_to(self, sql: str, out) -> None:
        self.copies.append(sql)
        table = re.search(r"FROM cpbl\.(\w+)", sql).group(1)
        out.write(f"{table}\t1\t\\N\t2026-10-28 00:00:00+00\n{table}\t2\tx\\ty\t\n")


def _golden_case(n: int) -> tuple[list[K], GoldenPsql, GoldenPsql]:
    keys = ([K(2026, "D" if i % 3 == 0 else "A", 100 + i) for i in range(n)] + [K(2025, "C", 1)])[:n]
    local = {k: "new" for k in keys} | {K(2026, "A", 1): "same"}
    prod = {k: "old" for k in keys[: n // 2]} | {K(2026, "A", 1): "same"}
    return keys, GoldenPsql(local), GoldenPsql(prod)


# 34aa6dd4 的 ``pa_incremental.write_payload(local, target, out)`` 對 :func:`_golden_case` 的輸出
# （exec-2 證據 golden-34aa6dd4.txt；以 ``git archive 34aa6dd4 src`` 的舊碼跑出）。
GOLDEN_34AA6DD4 = {
    1: ("e7226a079eb038dfb415cf9de517b18555b8f1b3992dfaf11ca7dba6d4fb888b", 8598),
    22: ("c163d02ddb272a31566ff14526249f6833bb190ac8e3691a71ee6f9385cb670f", 17733),
    50: ("bc311f75cbfbc0bb3d3bc7e379d441bc8c89fd07b267c81e3cc1340998959c0b", 29913),
}


class FakeSender:
    """替代 ``ssh … psql --single-transaction``：記下每份送出的檔；第 ``fail_at`` 次（1 起算）以 ``code`` 失敗。"""

    def __init__(self, fail_at: int | None = None, code: int = bs.EXIT_TARGET_SQL):
        self.sent: list[bytes] = []
        self.fail_at, self.code = fail_at, code

    def send_file(self, path: Path) -> None:
        self.sent.append(path.read_bytes())
        if self.fail_at is not None and len(self.sent) == self.fail_at:
            raise bs.SyncError(self.code, "target psql 失敗 rc=3：BOXPA_CLOSURE")


class Clock:
    """每次送出推進 ``step`` 秒；``sleep`` 只記錄、不真的睡。"""

    def __init__(self, step: float = 3.0):
        self.now, self.step = 1000.0, step
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.now += s


def _apply(local, target, tmp_path: Path, *, full=False, sender=None, clock=None, **kw):
    sender = sender or FakeSender()
    clock = clock or Clock()
    orig = sender.send_file

    def send(path: Path) -> None:
        clock.now += clock.step
        orig(path)

    sender.send_file = send
    lines: list[str] = []
    result = pi.apply(local, target, sender, tmp_path, full=full, sleep=clock.sleep, clock=clock,
                      log=lines.append, **kw)
    return result, sender, clock, lines


# --------------------------------------------------------------------------- 黃金值（增量 ≤ 一批）


@pytest.mark.parametrize("n", sorted(GOLDEN_34AA6DD4))
def test_single_batch_incremental_payload_is_byte_identical_to_34aa6dd4(n: int, tmp_path: Path) -> None:
    keys, local, prod = _golden_case(n)
    assert pi.select_keys(local, prod, full=False) == sorted(keys)
    out = io.StringIO()
    pi.write_batch_payload(local, sorted(keys), out)
    data = out.getvalue().encode()
    assert (hashlib.sha256(data).hexdigest(), len(out.getvalue())) == GOLDEN_34AA6DD4[n]


@pytest.mark.parametrize("n", sorted(GOLDEN_34AA6DD4))
def test_single_batch_apply_sends_the_golden_payload_once_without_pausing(n: int, tmp_path: Path) -> None:
    _, local, prod = _golden_case(n)
    result, sender, clock, lines = _apply(local, prod, tmp_path, pause_min=30.0)
    assert len(sender.sent) == 1
    assert hashlib.sha256(sender.sent[0]).hexdigest() == GOLDEN_34AA6DD4[n][0]
    assert clock.sleeps == [], "增量 ≤ 一批：零暫停（不可調）"
    assert result == {"games": n, "batches": 1, "committed": 1}
    assert not list(tmp_path.iterdir()), "成功後不留 payload"


def test_golden_case_mutation_is_detected() -> None:
    """變異自證：產生器多一個位元組，黃金值就不等（防止黃金值測試構造上恆綠）。"""
    keys, local, _ = _golden_case(22)
    out = io.StringIO()
    pi.write_batch_payload(local, sorted(keys), out)
    mutated = out.getvalue().replace("lock_timeout = '10s'", "lock_timeout = '11s'", 1).encode()
    assert hashlib.sha256(mutated).hexdigest() != GOLDEN_34AA6DD4[22][0]


# --------------------------------------------------------------------------- 切批


@pytest.mark.parametrize(("n", "size"), [(1, 50), (50, 50), (51, 50), (200, 50), (4513, 50), (7, 3)])
def test_batches_partition_keys_without_overlap(n: int, size: int) -> None:
    keys = sorted(K(2000 + i // 400, "A", i % 400 + 1) for i in range(n))
    bs_ = pi.batches(keys, size)
    flat = [k for b in bs_ for k in b]
    assert flat == keys, "聯集＝輸入、順序不變、彼此不重疊"
    assert all(1 <= len(b) <= size for b in bs_)
    assert len(bs_) == -(-n // size)


def test_batch_size_must_be_positive() -> None:
    with pytest.raises(bs.SyncError) as e:
        pi.batches([K(2026, "A", 1)], 0)
    assert e.value.code == bs.EXIT_USAGE


def test_every_batch_payload_passes_the_guard_with_its_own_scope_and_has_closure(tmp_path: Path) -> None:
    keys = [K(2026, "A", n) for n in range(1, 121)]
    local = GoldenPsql({k: "new" for k in keys})
    _, sender, _, _ = _apply(local, GoldenPsql({}), tmp_path, batch_games=50)
    assert len(sender.sent) == 3
    for batch, raw in zip(pi.batches(keys, 50), sender.sent, strict=True):
        text = raw.decode()
        bs.assert_pa_lines(text.splitlines(), bs.keys_sql(batch))
        assert "BOXPA_CLOSURE" in text and bs.closure_violations_sql(batch) in text
        assert "WHERE TRUE" not in text
        assert "statement_timeout = '300s'" in text


# --------------------------------------------------------------------------- 全量鍵集合


def _rows(*keys: K) -> list[list[str]]:
    return [[str(k.year), k.kind_code, str(k.game_sno)] for k in keys]


def test_full_keys_are_the_union_of_both_sides_across_all_five_tables() -> None:
    for t in bs.PA_TABLES:
        assert f"FROM cpbl.{t}" in pi.FULL_KEYS_SQL, t
    assert pi.FULL_KEYS_SQL.count(" UNION ") == len(bs.PA_TABLES) - 1
    local = GoldenPsql(keys_rows=_rows(K(2026, "A", 1), K(2026, "A", 2)))
    prod = GoldenPsql(keys_rows=_rows(K(2026, "A", 2), K(1990, "A", 9)))
    assert pi.select_keys(local, prod, full=True) == [K(1990, "A", 9), K(2026, "A", 1), K(2026, "A", 2)]
    assert all("string_agg" not in s for s in local.reads + prod.reads), "全量不比簽章"


def test_orphan_child_rows_are_covered_where_signature_keys_would_miss_them() -> None:
    """變異樣本：孤兒場（只出現在子表、不在 builds／source_revisions）。舊的 WHERE TRUE 會刪到它；
    只取簽章鍵（builds ∪ source_revisions）的做法會漏——新鍵集合必須含它。"""
    orphan = K(2019, "A", 77)
    signed = {K(2026, "A", 1): "s"}
    prod = GoldenPsql(sigs=signed, keys_rows=_rows(K(2026, "A", 1), orphan))
    local = GoldenPsql(sigs=signed, keys_rows=_rows(K(2026, "A", 1)))
    signature_only = sorted(pi.signatures(local).keys() | pi.signatures(prod).keys())
    assert orphan not in signature_only, "前提：簽章鍵確實漏掉孤兒場"
    assert orphan in pi.select_keys(local, prod, full=True)


def test_full_keys_reject_malformed_rows() -> None:
    bad = GoldenPsql(keys_rows=[["2026", "A", "1;DROP"]])
    with pytest.raises(bs.SyncError) as e:
        pi.select_keys(bad, GoldenPsql(), full=True)
    assert e.value.code == bs.EXIT_SELF_CHECK


def test_full_mode_is_batched_and_never_one_transaction_over_all_games(tmp_path: Path) -> None:
    keys = [K(2026, "A", n) for n in range(1, 131)]
    local = GoldenPsql(keys_rows=_rows(*keys))
    result, sender, _, lines = _apply(local, GoldenPsql(), tmp_path, full=True, batch_games=50)
    assert result == {"games": 130, "batches": 3, "committed": 3}
    assert [len(re.findall(r"^DELETE FROM cpbl.game_recap_builds ", s.decode(), re.M)) for s in sender.sent] == [1, 1, 1]
    assert any(ln.startswith("PA_FULL_RESYNC_GAMES=130") for ln in lines)


def test_full_mode_statement_timeout_constant_is_removed() -> None:
    src = Path(pi.__file__).read_text(encoding="utf-8")
    assert not hasattr(pi, "FULL_STATEMENT_TIMEOUT") and "3600s" not in src
    assert not hasattr(pi, "FULL_SCOPE") and "scope=FULL_SCOPE" not in src


def test_incremental_limit_and_refusal_are_unchanged(tmp_path: Path) -> None:
    assert pi.MAX_INCREMENTAL_GAMES == 200
    local = GoldenPsql({K(2026, "A", n): "x" for n in range(pi.MAX_INCREMENTAL_GAMES + 1)})
    with pytest.raises(bs.SyncError) as e:
        _apply(local, GoldenPsql(), tmp_path)
    assert e.value.code == bs.EXIT_SELF_CHECK
    assert local.copies == [] and not list(tmp_path.iterdir())


# --------------------------------------------------------------------------- 暫停


def test_pause_is_only_between_batches_and_scales_with_the_previous_batch(tmp_path: Path) -> None:
    keys = [K(2026, "A", n) for n in range(1, 151)]
    clock = Clock(step=7.5)
    _, sender, clock, lines = _apply(GoldenPsql({k: "n" for k in keys}), GoldenPsql(), tmp_path,
                                     clock=clock, batch_games=50, pause_ratio=1.0, pause_min=2.0)
    assert len(sender.sent) == 3
    assert clock.sleeps == [7.5, 7.5], "批間暫停＝前一批送出耗時；最後一批後不停"
    batch_lines = [ln for ln in lines if ln.startswith("PA_BATCH ")]
    assert len(batch_lines) == 3
    for i, ln in enumerate(batch_lines, 1):
        assert re.fullmatch(rf"PA_BATCH {i}/3 games=50 bytes=\d+ first=\S+ last=\S+ started=\d+\.\d{{3}} "
                            rf"finished=\d+\.\d{{3}} send_s=7\.500 pause_s={'7.500' if i < 3 else '0.000'}", ln), ln


def test_pause_floor_and_ratio(tmp_path: Path) -> None:
    keys = [K(2026, "A", n) for n in range(1, 101)]
    _, _, clock, _ = _apply(GoldenPsql({k: "n" for k in keys}), GoldenPsql(), tmp_path,
                            clock=Clock(step=0.5), batch_games=50, pause_ratio=1.0, pause_min=2.0)
    assert clock.sleeps == [2.0], "耗時短於下限 ⇒ 用下限"
    _, _, clock, _ = _apply(GoldenPsql({k: "n" for k in keys}), GoldenPsql(), tmp_path,
                            clock=Clock(step=4.0), batch_games=50, pause_ratio=1.5, pause_min=2.0)
    assert clock.sleeps == [6.0]


def test_no_difference_sends_nothing_and_does_not_pause(tmp_path: Path) -> None:
    same = {K(2026, "A", 1): "s"}
    result, sender, clock, lines = _apply(GoldenPsql(same), GoldenPsql(same), tmp_path)
    assert result == {"games": 0, "batches": 0, "committed": 0}
    assert sender.sent == [] and clock.sleeps == []
    assert "PA_INCREMENTAL_GAMES=0" in lines


@pytest.mark.parametrize(("args", "ok"), [
    ({"batch_games": 50, "pause_ratio": 1.0, "pause_min": 2.0}, True),
    ({"batch_games": 0}, False), ({"pause_ratio": -0.1}, False), ({"pause_min": -1}, False),
])
def test_batch_settings_are_validated(args, ok, tmp_path: Path) -> None:
    same = {K(2026, "A", 1): "s"}
    if ok:
        _apply(GoldenPsql(same), GoldenPsql(same), tmp_path, **args)
        return
    with pytest.raises(bs.SyncError) as e:
        _apply(GoldenPsql(same), GoldenPsql(same), tmp_path, **args)
    assert e.value.code == bs.EXIT_USAGE


def test_settings_come_from_the_environment_with_defaults(monkeypatch) -> None:
    for name in ("PA_BATCH_GAMES", "PA_BATCH_PAUSE_RATIO", "PA_BATCH_PAUSE_MIN_S"):
        monkeypatch.delenv(name, raising=False)
    args = pi._parser().parse_args(["apply", "--local-psql", "a", "--target-psql", "b",
                                    "--apply-psql", "c", "--workdir", "d"])
    assert (args.batch_games, args.pause_ratio, args.pause_min) == (50, 1.0, 2.0)
    monkeypatch.setenv("PA_BATCH_GAMES", "20")
    monkeypatch.setenv("PA_BATCH_PAUSE_RATIO", "2")
    monkeypatch.setenv("PA_BATCH_PAUSE_MIN_S", "5")
    args = pi._parser().parse_args(["apply", "--local-psql", "a", "--target-psql", "b",
                                    "--apply-psql", "c", "--workdir", "d"])
    assert (args.batch_games, args.pause_ratio, args.pause_min) == (20, 2.0, 5.0)


# --------------------------------------------------------------------------- 中途失敗


@pytest.mark.parametrize("code", [bs.EXIT_TARGET_SQL, bs.EXIT_TARGET])
def test_failure_at_batch_k_stops_without_sending_later_batches(code: int, tmp_path: Path) -> None:
    keys = [K(2026, "A", n) for n in range(1, 201)]
    sender = FakeSender(fail_at=2, code=code)
    lines: list[str] = []
    clock = Clock()
    with pytest.raises(bs.SyncError) as e:
        pi.apply(GoldenPsql({k: "n" for k in keys}), GoldenPsql(), sender, tmp_path, full=False,
                 batch_games=50, sleep=clock.sleep, clock=clock, log=lines.append)
    assert e.value.code == code
    assert len(sender.sent) == 2, "第 2 批失敗 ⇒ 不送第 3、4 批"
    assert len(clock.sleeps) == 1, "失敗後不再暫停"
    msg = str(e.value)
    assert "PA_BATCH_FAILED 2/4" in msg and "committed=1/4" in msg
    assert "committed_range=2026-A-1..2026-A-50" in msg
    assert "failed_keys=" + ",".join(k.text for k in keys[50:100]) + " " in msg, "失敗批逐場列出（供恢復）"
    kept = list(tmp_path.iterdir())
    assert len(kept) == 1 and kept[0].read_bytes() == sender.sent[1], "失敗批的 payload 保留供查"


def test_failure_at_first_batch_reports_nothing_committed(tmp_path: Path) -> None:
    keys = [K(2026, "A", n) for n in range(1, 61)]
    with pytest.raises(bs.SyncError) as e:
        _apply(GoldenPsql({k: "n" for k in keys}), GoldenPsql(), tmp_path, sender=FakeSender(fail_at=1))
    assert "committed=0/2" in str(e.value) and "committed_range=-" in str(e.value)


def test_guard_failure_on_a_batch_payload_sends_nothing_of_that_batch(tmp_path: Path, monkeypatch) -> None:
    keys = [K(2026, "A", n) for n in range(1, 61)]
    real = pi.write_batch_payload
    calls = []

    def bad_second(local, batch, out):
        calls.append(batch)
        real(local, batch, out)
        if len(calls) == 2:
            out.write("TRUNCATE cpbl.game_pa_events;\n")

    monkeypatch.setattr(pi, "write_batch_payload", bad_second)
    sender = FakeSender()
    with pytest.raises(bs.SyncError) as e:
        _apply(GoldenPsql({k: "n" for k in keys}), GoldenPsql(), tmp_path, sender=sender)
    assert e.value.code == bs.EXIT_SELF_CHECK
    assert len(sender.sent) == 1, "守衛不過的那批不送"
    assert "committed=1/2" in str(e.value)


# --------------------------------------------------------------------------- 送出端


def test_send_file_maps_ssh_and_psql_failures(tmp_path: Path) -> None:
    f = tmp_path / "p.sql"
    f.write_text("SELECT 1;\n", encoding="utf-8")
    bs.Psql(["sh", "-c", "cat >/dev/null"], label="target").send_file(f)
    for rc, code in ((255, bs.EXIT_TARGET), (3, bs.EXIT_TARGET_SQL)):
        with pytest.raises(bs.SyncError) as e:
            bs.Psql(["sh", "-c", f"cat >/dev/null; exit {rc}"], label="target").send_file(f)
        assert e.value.code == code


def test_send_file_streams_the_file_as_stdin(tmp_path: Path) -> None:
    f, got = tmp_path / "p.sql", tmp_path / "got"
    f.write_bytes(b"line1\n\\.\nline3\n")
    bs.Psql(["sh", "-c", f"cat > {got}"], label="target").send_file(f)
    assert got.read_bytes() == f.read_bytes()
