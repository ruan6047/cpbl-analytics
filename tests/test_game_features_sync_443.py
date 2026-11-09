"""#443 (c)：`refresh-cpbl-prod.sh` 同步 `game_features` 時，正式站讀者任何時點都不會讀到空表。

缺陷形狀（base `bef5ac60`）：先以**獨立 ssh** 對正式站 `TRUNCATE cpbl.game_features`（自己就 commit），
再由下一個交易 `sync_table` 灌回。兩者之間正式站是空表，`/api/daily` 的賽前機率讀它
（`src/cpbl/api/routers/daily.py`）。

修法：`SYNC_TABLE_EXACT=1 sync_table game_features …` 走 `_sync_table_exact`——**單一交易**內
「暫存表 → COPY → 刪本機沒有的鍵 → 只更新有變的列」，只取 ROW EXCLUSIVE；讀者走 MVCC 看到交易前快照。

兩層證據：

* **CI 形狀測試**（零 DB、零網路）：沿用 `test_prod_sync_revision_seq` 的假樁 harness 跑真腳本，
  斷言沒有獨立的 TRUNCATE ssh、資料包恰一 COPY／一個限定本表的 DELETE／一個 INSERT、無
  TRUNCATE／CASCADE／DROP／ALTER／setval、以 `--single-transaction` 送出；本機 0 列（或取不到列數）
  rc=67 且不送出。
* **真 PostgreSQL 併發測試**（預設 skip）：需一顆拋棄式 PG 容器與 database，名稱都須含 ``443``、
  database ⛔ 不得是 ``cpbl``：

      docker run -d --name cpbl-443-gf -e POSTGRES_PASSWORD=x -e POSTGRES_DB=gf443 postgres:17-alpine
      GF_SYNC_443_CONTAINER=cpbl-443-gf GF_SYNC_443_DATABASE=gf443 \\
        uv run pytest tests/test_game_features_sync_443.py
      docker rm -f cpbl-443-gf

  以真腳本的函式本體產生資料包（本機讀取由假 docker 供應合成列、假 ssh 只收資料包），在交易尾端
  加 `pg_sleep` 撐開窗口，讀者迴圈同時 `count(*)`：新資料包最小列數 > 0（正控）；舊兩段式
  （獨立 TRUNCATE 後送去掉 DELETE 的同一份資料包＝base 的 sync_table 形狀）最小列數 = 0（負控）。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from tests.test_prod_sync_revision_seq import _run_refresh

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "refresh-cpbl-prod.sh"
TABLE = "game_features"
PK = "year,kind_code,game_season_code,game_sno"


def _gf_payloads(calls: list[dict]) -> list[dict]:
    return [c for c in calls if f"INSERT INTO cpbl.{TABLE} " in c["stdin"]]


def _statements(payload: str) -> list[str]:
    """COPY 資料段以外的行（資料內容可能含任意文字，不參與形狀判斷）。"""
    out, in_copy = [], False
    for line in payload.splitlines():
        if in_copy:
            in_copy = line != "\\."
            continue
        if line.startswith("COPY ") and line.endswith(" FROM stdin;"):
            in_copy = True
        out.append(line)
    return out


@pytest.fixture(scope="module")
def full_run(tmp_path_factory: pytest.TempPathFactory):
    result, calls = _run_refresh(tmp_path_factory.mktemp("gf443"))
    assert result.returncode == 0, result.stderr[-2000:]
    return result, calls


def test_no_separate_truncate_is_sent(full_run) -> None:
    _result, calls = full_run
    hits = [c["argv"][-1] for c in calls if re.search(rf"TRUNCATE\s+cpbl\.{TABLE}\b", c["argv"][-1] if c["argv"] else "")]
    assert hits == [], f"仍有獨立 ssh 清空 {TABLE}：{hits}"
    for c in calls:
        assert not re.search(rf"(?i)TRUNCATE\s+(TABLE\s+)?cpbl\.{TABLE}\b", c["stdin"]), "資料包內不得 TRUNCATE"


def test_payload_is_one_transaction_with_exact_shape(full_run) -> None:
    _result, calls = full_run
    payloads = _gf_payloads(calls)
    assert len(payloads) == 1, f"{TABLE} 資料包應恰 1 份，實得 {len(payloads)}"
    call = payloads[0]
    assert "--single-transaction" in call["argv"][-1] and "ON_ERROR_STOP=1" in call["argv"][-1]

    stmts = _statements(call["stdin"])
    copies = [s for s in stmts if s.startswith("COPY ")]
    deletes = [s for s in stmts if s.upper().startswith("DELETE")]
    inserts = [s for s in stmts if s.startswith("INSERT INTO ")]
    assert len(copies) == 1 and copies[0].startswith(f"COPY _stg ({PK},"), copies
    assert len(deletes) == 1, deletes
    assert deletes[0].startswith(f"DELETE FROM cpbl.{TABLE} AS tgt WHERE NOT EXISTS (SELECT 1 FROM _stg s WHERE "), \
        deletes[0]
    for k in PK.split(","):
        assert f"s.{k}=tgt.{k}" in deletes[0], (k, deletes[0])
    assert len(inserts) == 1 and inserts[0].startswith(f"INSERT INTO cpbl.{TABLE} AS tgt SELECT * FROM _stg "), inserts
    # DELETE 在 INSERT 之前、兩者都在 COPY 之後（同一交易內）。
    assert stmts.index(copies[0]) < stmts.index(deletes[0]) < stmts.index(inserts[0])
    for s in stmts:
        # 暫存表的 `ON COMMIT DROP` 是交易結束時丟暫存表，不是 DDL 語句；DROP／ALTER 只禁語句開頭。
        assert not re.search(r"(?i)\b(TRUNCATE|CASCADE|SETVAL)\b", s), s
        assert not re.match(r"(?i)\s*(DROP|ALTER)\b", s), s


@pytest.mark.parametrize("count", ["0", ""])
def test_local_zero_or_unknown_rows_refuses_with_67_and_sends_nothing(tmp_path: Path, count: str) -> None:
    result, calls = _run_refresh(tmp_path, **{f"STUB_COUNT_{TABLE}": count})
    assert result.returncode == 67, (result.returncode, result.stderr[-1500:])
    assert _gf_payloads(calls) == []
    assert not [c for c in calls if TABLE in (c["argv"][-1] if c["argv"] else "") and "TRUNCATE" in c["argv"][-1]]


# ============================================================== 真 PostgreSQL 併發（預設 skip）

CONTAINER = os.getenv("GF_SYNC_443_CONTAINER", "")
DB = os.getenv("GF_SYNC_443_DATABASE", "")
DB_USER = os.getenv("GF_SYNC_443_USER", "postgres")
N_LOCAL = 300
HOLD_SECONDS = 1.5

_real_pg = pytest.mark.skipif(not (CONTAINER and DB),
                              reason="requires GF_SYNC_443_CONTAINER + GF_SYNC_443_DATABASE (throwaway, names contain 443)")

# 欄位型別比照本機 `cpbl.game_features`（pg_dump --schema-only，2026-11-09）。
_DDL = """
DROP SCHEMA IF EXISTS cpbl CASCADE;
CREATE SCHEMA cpbl;
CREATE TABLE cpbl.game_features (
    year integer NOT NULL, kind_code text NOT NULL, game_season_code text NOT NULL, game_sno integer NOT NULL,
    game_date date, season integer, home_team_code text, away_team_code text, home_team_name text,
    away_team_name text, home_win integer, completed boolean DEFAULT false NOT NULL,
    winrate_diff double precision, h2h_home double precision, starter_era_diff double precision,
    home_field double precision, recent_form_diff double precision, run_diff_diff double precision,
    runs_scored_diff double precision, runs_allowed_diff double precision, starter_whip_diff double precision,
    starter_k9_diff double precision, rest_days_diff double precision, prior_winpct_diff double precision,
    prior_team_ops_diff double precision, prior_team_slg_diff double precision,
    prior_team_era_diff double precision, prior_team_whip_diff double precision,
    team_ops_now_diff double precision, team_avg_now_diff double precision, team_sb_now_diff double precision,
    team_wp_now_diff double precision, team_err_now_diff double precision,
    PRIMARY KEY (year, kind_code, game_season_code, game_sno)
);
"""

_FAKE_DOCKER = """\
import os, sys
argv = sys.argv[1:]
joined = " ".join(argv)
stdin = sys.stdin.read() if "-i" in argv else ""
if "information_schema.columns" in joined:
    print("\\n".join(os.environ["STUB_COLUMNS"].split(",")))
elif "SELECT count(*) FROM cpbl.game_features" in joined:
    print(os.environ["STUB_N"])
elif "TO STDOUT" in stdin:
    sys.stdout.write(open(os.environ["STUB_ROWS"], encoding="utf-8").read())
else:
    raise SystemExit("unexpected docker call: " + joined)
"""
_FAKE_SSH = """\
import os, sys
open(os.environ["STUB_PAYLOAD"], "w", encoding="utf-8").write(sys.stdin.read())
"""


def _psql_argv() -> list[str]:
    assert "443" in CONTAINER and "443" in DB and DB != "cpbl", "只在名稱含 443 的拋棄式容器／database 上跑"
    docker = shutil.which("docker")
    assert docker
    return [docker, "exec", "-i", CONTAINER, "psql", "-X", "-U", DB_USER, "-d", DB]


def _sql(script: str) -> str:
    p = subprocess.run([*_psql_argv(), "-q", "-At", "-v", "ON_ERROR_STOP=1"], input=script,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def _function(name: str) -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    m = re.search(rf"^{name}\(\) \{{[^\n]*\n.*?^\}}\n", text, re.S | re.M)
    assert m, f"找不到 {name} 函式本體"
    return m.group(0)


def _gf_columns() -> list[str]:
    """腳本裡 game_features 那一行 sync_table 的 PK＋欄位清單（與腳本同一份，不另抄）。"""
    text = SCRIPT.read_text(encoding="utf-8")
    m = re.search(r'sync_table game_features "([^"]+)" \\\n(.*?)\n(?:else|fi)\b', text, re.S)
    assert m, "找不到 game_features 的 sync_table 呼叫"
    rest = m.group(2).replace("\\\n", " ").split()
    return [*m.group(1).split(","), *rest]


def _local_rows(cols: list[str], n: int) -> str:
    """合成「本機」列（tab 分隔 COPY 文字格式）：kind A、1..n 場。"""
    lines = []
    for i in range(1, n + 1):
        row = []
        for c in cols:
            if c == "year":
                row.append("2026")
            elif c == "kind_code":
                row.append("A")
            elif c == "game_season_code":
                row.append("0")
            elif c == "game_sno":
                row.append(str(i))
            elif c == "game_date":
                row.append("2026-04-01")
            elif c == "season":
                row.append("2026")
            elif c in ("home_win",):
                row.append(str(i % 2))
            elif c == "completed":
                row.append("t")
            elif c.endswith("_code") or c.endswith("_name"):
                row.append("T")
            else:
                row.append(str(i / 1000))
        lines.append("\t".join(row))
    return "\n".join(lines) + "\n"


def _new_payload(tmp_path: Path) -> str:
    cols = _gf_columns()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("docker", _FAKE_DOCKER), ("ssh", _FAKE_SSH)):
        (bin_dir / name).write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
        (bin_dir / name).chmod(0o755)
    rows = tmp_path / "rows.tsv"
    rows.write_text(_local_rows(cols, N_LOCAL), encoding="utf-8")
    payload = tmp_path / "payload.sql"
    (tmp_path / "tmp").mkdir()
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "TMPDIR": str(tmp_path / "tmp"),
           "STUB_COLUMNS": ",".join(cols), "STUB_N": str(N_LOCAL), "STUB_ROWS": str(rows),
           "STUB_PAYLOAD": str(payload),
           # fail-safe：不可達的主機／容器
           "LOCAL_DB": "stub-nonexistent-container", "VPS": "stub@harness.invalid",
           "DEPLOY_PATH": "/nonexistent/stub-deploy"}
    pk, rest = PK, [c for c in cols if c not in PK.split(",")]
    script = ("set -euo pipefail\n" + _function("sync_table") + _function("_sync_table_exact")
              + 'SYNC_TABLE_EXACT=1 sync_table "$@"\n')
    r = subprocess.run(["/bin/bash", "-c", script, "harness", TABLE, pk, *rest], env=env, text=True,
                       capture_output=True, check=False)
    assert r.returncode == 0, r.stderr
    return payload.read_text(encoding="utf-8")


def _seed_prod() -> None:
    """「正式站」初始狀態：本機 1..N 的舊版（值不同）＋本機沒有的殘留列（D 列與 N+1..N+20）。"""
    _sql(_DDL + f"""
INSERT INTO cpbl.game_features (year, kind_code, game_season_code, game_sno, completed, winrate_diff)
  SELECT 2026, 'A', '0', g, false, -1 FROM generate_series(1, {N_LOCAL}) g;
INSERT INTO cpbl.game_features (year, kind_code, game_season_code, game_sno, completed)
  SELECT 2026, 'A', '0', g, false FROM generate_series({N_LOCAL + 1}, {N_LOCAL + 20}) g;
INSERT INTO cpbl.game_features (year, kind_code, game_season_code, game_sno, completed)
  SELECT 2025, 'D', '0', g, false FROM generate_series(1, 10) g;
""")


def _sample_counts(stop: threading.Event, out: list[int]) -> None:
    loop = f"while true; do psql -X -At -U {DB_USER} -d {DB} -c 'SELECT count(*) FROM cpbl.game_features'; done"
    docker = shutil.which("docker")
    p = subprocess.Popen([docker, "exec", CONTAINER, "sh", "-c", loop], stdout=subprocess.PIPE, text=True)
    try:
        while not stop.is_set():
            line = p.stdout.readline()
            if line.strip().isdigit():
                out.append(int(line))
    finally:
        p.kill()
        p.wait()
        subprocess.run([docker, "exec", CONTAINER, "pkill", "-f", "SELECT count"], capture_output=True)


def _apply_with_reader(steps: list[tuple[str, str]]) -> list[int]:
    """steps：("command", sql)＝獨立 psql（自己 commit）；("payload", sql)＝--single-transaction 送出。"""
    counts: list[int] = []
    stop = threading.Event()
    reader = threading.Thread(target=_sample_counts, args=(stop, counts))
    reader.start()
    try:
        deadline = time.monotonic() + 10
        while len(counts) < 5 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert len(counts) >= 5, "讀者迴圈沒有取到樣本"
        start = len(counts)
        for kind, sql in steps:
            extra = ["-q", "-c", sql] if kind == "command" else ["-v", "ON_ERROR_STOP=1", "-q", "--single-transaction"]
            p = subprocess.run([*_psql_argv(), *extra], input=None if kind == "command" else sql,
                               capture_output=True, text=True)
            assert p.returncode == 0, p.stderr
        end = len(counts)
    finally:
        stop.set()
        reader.join()
    window = counts[start:end]
    assert len(window) >= 5, f"窗口內樣本太少（{len(window)}），無法判斷"
    return window


def _hold(payload: str) -> str:
    """在交易尾端（commit 前）撐開窗口。"""
    return payload + f"SELECT pg_sleep({HOLD_SECONDS});\n"


@_real_pg
def test_real_pg_new_payload_never_exposes_empty_table(tmp_path: Path) -> None:
    payload = _new_payload(tmp_path)
    _seed_prod()
    window = _apply_with_reader([("payload", _hold(payload))])

    assert min(window) > 0, f"新資料包期間讀者讀到空表：min={min(window)}"
    # 結果與本機一致：本機 1..N 全在、殘留列被刪、值已更新。
    assert _sql("SELECT count(*), count(*) FILTER (WHERE completed AND winrate_diff > 0) "
                "FROM cpbl.game_features") == f"{N_LOCAL}|{N_LOCAL}"


@_real_pg
def test_real_pg_old_two_step_shape_exposes_empty_table_negative_control(tmp_path: Path) -> None:
    """負控：base 的兩段式（獨立 TRUNCATE commit 後，再送不含 DELETE 的 sync_table 形狀）。"""
    payload = _new_payload(tmp_path)
    old = "\n".join(line for line in payload.splitlines()
                    if not line.startswith("DELETE FROM cpbl.game_features ")) + "\n"
    assert old != payload
    _seed_prod()
    window = _apply_with_reader([("command", "TRUNCATE cpbl.game_features"), ("payload", _hold(old))])

    assert min(window) == 0, f"負控失效：舊兩段式期間讀者沒有讀到空表（min={min(window)}），檢查不出缺陷"


def test_real_pg_case_is_wired_to_the_same_column_list() -> None:
    """CI 也跑：真 PG 測試取的欄位清單就是腳本那一行（避免抄錯而讓真 PG 測試測到別的形狀）。"""
    cols = _gf_columns()
    assert cols[:4] == PK.split(",")
    assert len(cols) == len(set(cols)) == 33
