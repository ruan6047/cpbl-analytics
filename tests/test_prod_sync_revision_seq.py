"""`sync_revision_table()` 的序列碰撞守衛（OPS-PROD-SYNC-SEQ-COLLISION1）。

**為什麼要用「跑真腳本」而不是抽 helper 做函式單測**：本次缺陷的性質是**呼叫點的語句
順序**——`pg_dump` 產生的 `setval` 落在函式自己 echo 的 `INSERT` 之前，於是 prod 從
本機序列的 `last_value` 開始配號、撞上 prod 既有 id。函式單測看不到語句順序，也證明
不了「另外兩個共用 `_stage` 的函式沒被誤傷」。故沿用 `tests/test_backup_prod_db.py`
的既有手法：把假 `ssh`／`docker`／`uv`／`curl`／`python3` 放進 `PATH`，直接跑真腳本，
捕獲每一份送往 ssh 的 payload 再逐份斷言。零 DB、零網路。

**安全設計為 fail-safe**：`VPS` 指向 `.invalid` 保留網域、`LOCAL_DB` 指向不存在的容器、
`DEPLOY_PATH` 指向不存在的路徑。假樁沒攔到也連不上任何真實主機。

**兩個 fail-closed 要求（皆為本卡自身教訓的回歸）**：

1. 生產路徑一律以 `SKIP_SCRAPE=1 WITH_DETAIL=1` 執行——`scripts/scrape-daily.sh:106`
   即此組合。不帶 `WITH_DETAIL` 時 `sync_pa_build`／`sync_advanced_snapshot`
   **根本不執行**，作用域回歸斷言會「無輸出卻看起來像通過」。
2. 找不到目標 payload 一律判紅（`_payload_containing` 直接 `assert`），不接受
   vacuous truth——原始缺陷逃逸的成因，正是自測只驗了唯一不可能失敗的情境（首灌）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "refresh-cpbl-prod.sh"

REVISION_TABLES = ("game_schedule_status_revisions", "game_source_revisions")

# 假本機序列 last_value／假 prod max(id)：沿用 2026-08-14 的實測值，
# 使 harness 重現當日的地雷區形狀（prod_max > local last_value）。
FAKE_LOCAL_SEQ = {"game_schedule_status_revisions": 17489, "game_source_revisions": 18056}
FAKE_PROD_MAX = {"game_schedule_status_revisions": 18138, "game_source_revisions": 18590}

# 作用域回歸：這兩個函式各自 `_stage` 五張表，其 dump `setval` 是**對的**
# （以 OVERRIDING SYSTEM VALUE 明確鏡像 id），修法不得誤傷。
SCOPE_REGRESSION = (
    ("sync_advanced_snapshot", "COPY _adv_run (", 5),
    ("sync_pa_build", "COPY _pa_rev (", 5),
)

# --- 假 pg_dump 的輸出：複刻 pg_dump 17.9 `--data-only -t` 的真實形狀 -----------------
# 佔位符用 __TABLE__／__I__／__N__ 而非 str.format，避免與內容中的大括號打架；
# 嵌進假樁原始碼時一律走 json.dumps（內容含反斜線，直接內插會被當跳脫序列）。
_DUMP_HEADER = (
    "--\n-- PostgreSQL database dump\n--\n\n"
    "\\restrict 2kBl9fDtycedWZ4IFharf9nr97EpepblkqXxR8wD6l8FCR3nioW3WG7CxhOlkrq\n\n"
    "-- Dumped from database version 17.9\n"
    "-- Dumped by pg_dump version 17.9\n\n"
    "SET statement_timeout = 0;\n"
    "SET client_encoding = 'UTF8';\n"
    "SET row_security = off;\n\n"
    "--\n-- Data for Name: __TABLE__; Type: TABLE DATA; Schema: cpbl; Owner: cpbl\n--\n\n"
)
_DUMP_COPY = "COPY cpbl.__TABLE__ (id, year, kind_code, payload_hash) FROM stdin;\n"
_DUMP_ROW = "__I__\t2026\tA\thash__I__\n"
_DUMP_COPY_END = "\\.\n\n"
_DUMP_SEQ = (
    "\n--\n"
    "-- Name: __TABLE___id_seq; Type: SEQUENCE SET; Schema: cpbl; Owner: cpbl\n"
    "--\n\n"
    "SELECT pg_catalog.setval('cpbl.__TABLE___id_seq', __N__, true);\n\n"
)
_DUMP_TAIL = (
    "\n--\n-- PostgreSQL database dump complete\n--\n\n"
    "\\unrestrict ddqM9rEBJA5FrFjIqvzhev03XIpVqlWFVyFxmWjkWq5Me6DmnssJXP50sI383VB\n"
)


# --------------------------------------------------------------------------- 假樁

_STUB_HELPERS = """\
import json, os
from pathlib import Path

HEADER, COPY, ROW, COPY_END, SEQ, TAIL = {header}, {copy}, {row}, {copy_end}, {seq}, {tail}


def fake_dump(table, seq_last_value, with_setval):
    body = HEADER.replace("__TABLE__", table) + COPY.replace("__TABLE__", table)
    for i in range(1, 4):
        body += ROW.replace("__I__", str(i))
    body += COPY_END
    if with_setval:
        body += SEQ.replace("__TABLE__", table).replace("__N__", str(seq_last_value))
    return body + TAIL


def log_call(kind, argv, stdin_text):
    out = Path(os.environ["STUB_LOG_DIR"]) / kind
    out.mkdir(parents=True, exist_ok=True)
    index = len(list(out.glob("*.json")))
    (out / ("%03d.json" % index)).write_text(
        json.dumps({{"argv": argv, "stdin": stdin_text}}), encoding="utf-8"
    )
"""

_DOCKER_STUB = '''\
import json, os, re, sys
sys.path.insert(0, os.environ["STUB_HELPER_DIR"])
from stub_helpers import fake_dump, log_call

argv = sys.argv[1:]
log_call("docker", argv, "")
joined = " ".join(argv)
local_seq = json.loads(os.environ["STUB_LOCAL_SEQ"])

if "pg_dump" in argv:
    table = argv[argv.index("-t") + 1].split(".", 1)[1]
    # STUB_INJECT_SETVAL 模擬「有人改回 pg_dump 原生行為／序列名對不上」：即使呼叫端
    # 要求排除，dump 仍吐出原生 setval。守衛必須在送出前當場擋下（T6）。
    inject = os.environ.get("STUB_INJECT_SETVAL") == "1"
    with_setval = ("--exclude-table-data" not in argv) or inject
    sys.stdout.write(fake_dump(table, local_seq.get(table, 100), with_setval))
elif "pg_get_serial_sequence" in joined:
    table = re.search(r"pg_get_serial_sequence\\('cpbl\\.(\\w+)'", joined).group(1)
    print("" if os.environ.get("STUB_SEQUENCE_MISSING") == "1" else "cpbl.%s_id_seq" % table)
elif "last_value" in joined:
    print(local_seq.get(re.search(r"FROM cpbl\\.(\\w+)_id_seq", joined).group(1), 100))
elif "max(game_date)" in joined:
    print("2026-08-14|300")
else:
    print("")
'''

_SSH_STUB = '''\
import json, os, re, sys
sys.path.insert(0, os.environ["STUB_HELPER_DIR"])
from stub_helpers import log_call

argv = sys.argv[1:]
log_call("ssh", argv, sys.stdin.read())

match = re.search(r"max\\(id\\), 0\\) FROM cpbl\\.(\\w+)", argv[-1] if argv else "")
if match:
    print(json.loads(os.environ["STUB_PROD_MAX"]).get(match.group(1), 0))
'''


def _write_exec(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _build_harness(tmp_path: Path) -> dict:
    """假 bin ＋ 假 repo（腳本以 symlink 指回真檔，確保跑的是 repo 現行版本）。"""
    fake_bin, helper_dir = tmp_path / "bin", tmp_path / "helpers"
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True, exist_ok=True)

    _write_exec(
        helper_dir / "stub_helpers.py",
        _STUB_HELPERS.format(
            header=json.dumps(_DUMP_HEADER),
            copy=json.dumps(_DUMP_COPY),
            row=json.dumps(_DUMP_ROW),
            copy_end=json.dumps(_DUMP_COPY_END),
            seq=json.dumps(_DUMP_SEQ),
            tail=json.dumps(_DUMP_TAIL),
        ),
    )
    # 假樁自己用絕對路徑的解譯器，才不會被 PATH 上的 python3 樁吃掉。
    _write_exec(fake_bin / "docker", f"#!{sys.executable}\n{_DOCKER_STUB}")
    _write_exec(fake_bin / "ssh", f"#!{sys.executable}\n{_SSH_STUB}")
    _write_exec(
        fake_bin / "uv",
        '#!/bin/sh\ncase "$*" in\n'
        "  *cpbl.completion*) echo 'home_score + away_score > 0' ;;\n"
        '  *) echo "stub uv $*" ;;\nesac\n',
    )
    _write_exec(fake_bin / "curl", "#!/bin/sh\necho '{}'\n")
    _write_exec(fake_bin / "python3", "#!/bin/sh\ncat > /dev/null\nexit 0\n")

    # 腳本以絕對路徑（$REPO_DIR/scripts/…）呼叫的兩支，樁在假 repo 內。
    _write_exec(repo / "scripts" / "backup-prod-db.sh", "#!/bin/sh\necho /dev/null\n")
    _write_exec(repo / "scripts" / "verify_refresh_info.py", "# stub\n")
    os.symlink(SCRIPT, repo / "scripts" / SCRIPT.name)

    return {"bin": fake_bin, "helpers": helper_dir, "log": tmp_path / "calls", "repo": repo}


def _run_refresh(
    tmp_path: Path, *, with_detail: bool = True, **stub_env: str
) -> tuple[subprocess.CompletedProcess, list[dict]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    harness = _build_harness(tmp_path)
    (tmp_path / "tmp").mkdir(exist_ok=True)
    env = {
        "PATH": f"{harness['bin']}:/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        "TMPDIR": str(tmp_path / "tmp"),
        "STUB_LOG_DIR": str(harness["log"]),
        "STUB_HELPER_DIR": str(harness["helpers"]),
        "STUB_LOCAL_SEQ": json.dumps(FAKE_LOCAL_SEQ),
        "STUB_PROD_MAX": json.dumps(FAKE_PROD_MAX),
        # fail-safe：三者皆不可達，假樁沒攔到也碰不到任何真實主機／容器。
        "VPS": "stub@harness.invalid",
        "LOCAL_DB": "stub-nonexistent-container",
        "DEPLOY_PATH": "/nonexistent/stub-deploy",
        "API_INFO_URL": "http://127.0.0.1:1/api/info",
        "SKIP_SCRAPE": "1",
        **stub_env,
    }
    if with_detail:
        env["WITH_DETAIL"] = "1"

    result = subprocess.run(
        ["/bin/bash", str(harness["repo"] / "scripts" / SCRIPT.name)],
        env=env,
        text=True,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    ssh_dir = harness["log"] / "ssh"
    calls = (
        [json.loads(p.read_text(encoding="utf-8")) for p in sorted(ssh_dir.glob("*.json"))]
        if ssh_dir.is_dir()
        else []
    )
    return result, calls


def _payload_containing(calls: list[dict], needle: str) -> str:
    """找出含 `needle` 的 ssh payload。**找不到即判紅**（fail-closed，不得靜默通過）。"""
    hits = [c["stdin"] for c in calls if needle in c["stdin"]]
    assert hits, (
        f"找不到含 {needle!r} 的 ssh payload——不接受「沒找到所以沒問題」。"
        f"實際捕獲 {len(calls)} 份 payload。"
    )
    assert len(hits) == 1, f"{needle!r} 出現在 {len(hits)} 份 payload，預期恰好 1 份"
    return hits[0]


@pytest.fixture(scope="module")
def baseline_run(tmp_path_factory: pytest.TempPathFactory) -> tuple:
    """生產路徑的一次完整執行：`SKIP_SCRAPE=1 WITH_DETAIL=1`（同 scrape-daily.sh:106）。"""
    result, calls = _run_refresh(tmp_path_factory.mktemp("baseline"))
    assert result.returncode == 0, f"harness 未跑完：rc={result.returncode}\n{result.stderr}"
    return result, calls


# --------------------------------------------------------------- 文字層 T1–T7（無 DB）


@pytest.mark.parametrize("table", REVISION_TABLES)
def test_t1_revision_payload_carries_exactly_one_corrective_setval(baseline_run, table) -> None:
    """T1：payload 內 setval 恰好 1 個，且為矯正形式（指向該表自己的序列）。"""
    _, calls = baseline_run
    payload = _payload_containing(calls, f"INSERT INTO cpbl.{table} (")

    setvals = [line for line in payload.splitlines() if "setval" in line]
    assert len(setvals) == 1, setvals
    assert "pg_get_serial_sequence" in setvals[0]
    assert f"'cpbl.{table}', 'id'" in setvals[0]
    # 空目標邊界：0 列時 max(id) 為 NULL。setval 是 STRICT，NULL 參數不報錯而是**靜默
    # no-op**（序列原封不動）；改成 COALESCE(...,0) 又會撞 MINVALUE 而報錯。GREATEST
    # 與第三參數 is_called 同時處理這兩種形態，缺一不可（見 D2）。
    assert "GREATEST(COALESCE((SELECT max(id)" in setvals[0]
    assert "> 0);" in setvals[0], "第三參數 is_called 必須是 count(*) > 0"


@pytest.mark.parametrize("table", REVISION_TABLES)
def test_t2_corrective_setval_sits_after_copy_and_before_insert(baseline_run, table) -> None:
    """T2：矯正 setval 的位置。放在 INSERT 之後無效——交易在 INSERT 當場中止，永遠執行不到。

    定位的是**矯正**那一行而非「任何一行 setval」：只驗位置的話，未修版本的 dump 原生
    setval 也剛好落在 `\\.` 與 `INSERT` 之間，這條斷言就會在壞碼上一樣是綠的。
    """
    _, calls = baseline_run
    lines = _payload_containing(calls, f"INSERT INTO cpbl.{table} (").splitlines()

    copy_end = max(i for i, line in enumerate(lines) if line == "\\.")
    setval = next(i for i, line in enumerate(lines) if "pg_get_serial_sequence" in line)
    insert = next(
        i for i, line in enumerate(lines) if line.startswith(f"INSERT INTO cpbl.{table} ")
    )

    assert copy_end < setval < insert, (copy_end, setval, insert)
    assert "setval" in lines[setval]


@pytest.mark.parametrize("table", REVISION_TABLES)
def test_t3_revision_payload_has_no_native_dump_setval(baseline_run, table) -> None:
    """T3：dump 原生 setval 必須消失——那一行就是把 prod 序列拉回本機 last_value 的元凶。"""
    _, calls = baseline_run
    payload = _payload_containing(calls, f"INSERT INTO cpbl.{table} (")

    assert "pg_catalog.setval" not in payload
    # COPY 區塊本身一字未動（`--exclude-table-data` 只拿掉序列資料），既有 sed 仍生效。
    assert "COPY _rev_stg (" in payload
    assert "\\restrict" not in payload and "\\unrestrict" not in payload


@pytest.mark.parametrize(("owner", "marker", "expected"), SCOPE_REGRESSION)
def test_t4_t5_scope_regression_other_syncs_keep_their_dump_setval(
    baseline_run, owner, marker, expected
) -> None:
    """T4／T5：`sync_pa_build`／`sync_advanced_snapshot` 的 dump setval **仍在**。

    它們以 `OVERRIDING SYSTEM VALUE` 明確鏡像 id，setval 在那裡是對的；修法若落在共用的
    `_stage` 上就會誤傷那 10 個呼叫點。這條斷言是抽 helper 做函式單測辦不到的——它證明
    的是「另外兩個函式沒被改到」，而那要在同一次執行內才看得到。
    """
    _, calls = baseline_run
    payload = _payload_containing(calls, marker)

    assert payload.count("pg_catalog.setval") == expected, f"{owner}: {payload.count('setval')}"


def test_t6_guard_blocks_bad_payload_before_it_reaches_ssh(tmp_path: Path) -> None:
    """T6（本組最重要）：注入 dump 原生 setval → 腳本非 0 結束，且**壞 payload 從未抵達 ssh**。

    只驗 `exit 1` 不夠——守衛的全部價值在於資料沒有離開本機。

    註：無法斷言「假 ssh 從未被呼叫」——`ssh` 在本函式之前已被 `migrate` 與
    `sync_table games` 合法呼叫過。此處斷言的是更精確的等價物：**帶著壞 payload 的那次
    ssh 從未發生**（逐份檢查所有捕獲的 payload）。
    """
    result, calls = _run_refresh(tmp_path, STUB_INJECT_SETVAL="1")
    first = REVISION_TABLES[0]

    assert result.returncode == 67
    assert "未通過送出前守衛" in result.stderr
    assert "生產未被觸碰" in result.stderr

    for call in calls:
        assert f"INSERT INTO cpbl.{first} (" not in call["stdin"]
        assert "COPY _rev_stg (" not in call["stdin"]

    # 壞 payload 刻意保留供人檢視，且留在本機。
    retained = list((tmp_path / "tmp").glob(f"cpbl-rev-{first}.*"))
    assert retained, "守衛擋下時應保留 payload 供檢視"
    assert "pg_catalog.setval" in retained[0].read_text(encoding="utf-8")


def test_t6b_guard_refuses_when_sequence_name_cannot_be_resolved(tmp_path: Path) -> None:
    """T6b：查不到序列名時 fail-closed，不得靜默退回會產生 setval 的舊行為。"""
    result, calls = _run_refresh(tmp_path, STUB_SEQUENCE_MISSING="1")

    assert result.returncode == 66
    assert "取不到 cpbl." in result.stderr
    for call in calls:
        assert f"INSERT INTO cpbl.{REVISION_TABLES[0]} (" not in call["stdin"]


def test_t7_missing_payload_fails_closed_instead_of_passing_vacuously(tmp_path: Path) -> None:
    """T7：本卡自身教訓的回歸——找不到目標 payload 時**必須判紅**。

    規劃期的實驗第一次跑沒帶 `WITH_DETAIL`，兩條作用域斷言因此根本沒執行，卻被印成空白
    看起來像通過——與原始缺陷「自測只驗了唯一不可能失敗的情境」形狀完全相同。此測試
    直接證明 `_payload_containing` 在該情境下會拋錯，而不是靜默放行。
    """
    result, calls = _run_refresh(tmp_path / "no-detail", with_detail=False)
    assert result.returncode == 0

    markers = [marker for _, marker, _ in SCOPE_REGRESSION]

    # 不帶 WITH_DETAIL → sync_pa_build／sync_advanced_snapshot 根本不執行。
    for marker in markers:
        with pytest.raises(AssertionError, match="不接受「沒找到所以沒問題」"):
            _payload_containing(calls, marker)

    # 而生產路徑（WITH_DETAIL=1）確實會執行它們——證明 T4／T5 不是 vacuous truth。
    detail_result, detail_calls = _run_refresh(tmp_path / "with-detail")
    assert detail_result.returncode == 0
    for marker in markers:
        assert _payload_containing(detail_calls, marker)


@pytest.mark.parametrize("table", REVISION_TABLES)
def test_invariant_telemetry_reports_the_zone_the_old_code_would_have_hit(
    baseline_run, table
) -> None:
    """遙測是結案證據的載體：`zone_before` 就是舊碼當天會踩到的地雷區大小。"""
    result, _ = baseline_run
    expected_zone = FAKE_PROD_MAX[table] - FAKE_LOCAL_SEQ[table]
    line = next(
        line for line in result.stdout.splitlines() if line.strip().startswith(f"ⓘ {table} ")
    )

    assert f"old_seq={FAKE_LOCAL_SEQ[table]}" in line
    assert f"prod_max={FAKE_PROD_MAX[table]}" in line
    assert f"zone_before={expected_zone}" in line
    assert f"corrected={FAKE_PROD_MAX[table]}" in line
    assert "zone_after=0" in line


# ----------------------------------------------------------- 碼面守衛（作用域與註解）


def test_guard_is_not_a_pipeline_filter() -> None:
    """守衛必須「先落地再斷言」：管線過濾器雖會讓整條回非 0，但資料早已流進 ssh。"""
    source = SCRIPT.read_text(encoding="utf-8")
    body = source.split("sync_revision_table() {", 1)[1].split("\n}\n", 1)[0]

    assert 'mktemp "${TMPDIR:-/tmp}/cpbl-rev-' in body
    assert '} > "$payload"' in body
    assert '_assert_revision_payload "$payload" "$t" || exit 67' in body
    assert '< "$payload"' in body
    assert "} | ssh" not in body, "payload 不得以管線直送 ssh"


def test_shared_stage_helper_is_untouched_by_this_card() -> None:
    """作用域紅線：`_stage` 是三方共用（11 個呼叫點），改動落在它身上等於誤傷 10 處。"""
    source = SCRIPT.read_text(encoding="utf-8")
    stage = source.split("_stage() {  # $1=來源表  $2=暫存表名\n", 1)[1].split("\n}\n", 1)[0]

    assert "--exclude-table-data" not in stage
    assert "--exclude-table-data" in source.split("_stage_noseq() {", 1)[1]
    for fn in ("sync_advanced_snapshot", "sync_pa_build"):
        body = source.split(f"{fn}() {{\n", 1)[1].split("\n}\n", 1)[0]
        assert "_stage_noseq" not in body, f"{fn} 不得改用 _stage_noseq"


def test_escaped_defect_rationale_is_rewritten_not_merely_deleted() -> None:
    """註解 `:156-160` 本身是缺陷逃逸的機制；只刪不重寫等於把陷阱留給下一個人。"""
    source = SCRIPT.read_text(encoding="utf-8")

    assert "已知且刻意接受的副作用" not in source, "舊的錯誤敘述必須移除"
    assert "第二次執行，且期間有新列" in source, "須明載舊自測的盲區"
    assert "box_pitching_revisions" in source, "須點名第三張同型表"
    assert "non sequitur" in source, "須說明「前提為真、推論無效」"


# --------------------------------------------- DB 層 D1–D3（需拋棄式資料庫，預設 skip）
#
# 只驗兩件「由 Postgres 語意決定、文字層看不到」的事：序列名解析、空目標邊界；
# 外加一條對 2026-08-14 的定點回歸（fault injection）。需一個專用拋棄式資料庫：
#   createdb -h localhost -p 5433 -U cpbl cpbl_prod_sync_seq1
#   PROD_SYNC_SEQ_TEST_DATABASE_URL=postgresql://cpbl:...@localhost:5433/cpbl_prod_sync_seq1

_DB_URL_ENV = "PROD_SYNC_SEQ_TEST_DATABASE_URL"
_EXPECTED_DB_NAME = "cpbl_prod_sync_seq1"

requires_scratch_db = pytest.mark.skipif(
    not os.getenv(_DB_URL_ENV),
    reason=f"requires a throwaway PostgreSQL via {_DB_URL_ENV}",
)


def _scratch_connection():
    import psycopg

    url = os.environ[_DB_URL_ENV]
    assert url.rsplit("/", 1)[-1] == _EXPECTED_DB_NAME, "只在專用拋棄式資料庫上跑"
    connection = psycopg.connect(url)
    connection.execute("DROP SCHEMA IF EXISTS seqtest CASCADE")
    connection.execute("CREATE SCHEMA seqtest")
    connection.commit()
    return connection


@requires_scratch_db
def test_d1_serial_sequence_resolves_for_identity_columns() -> None:
    """D1：`pg_get_serial_sequence()` 對 GENERATED ALWAYS AS IDENTITY 欄解析得到序列。

    修法完全靠這個函式取得序列名（不寫死 pattern）——它若對 identity 欄回 NULL，
    `--exclude-table-data` 就會收到空字串、dump 的 setval 復活。腳本對此 fail-closed
    （見 T6b），但前提是這裡真的解析得到。
    """
    with _scratch_connection() as connection:
        connection.execute(
            "CREATE TABLE seqtest.rev ("
            "  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,"
            "  content_key text NOT NULL UNIQUE)"
        )
        resolved = connection.execute(
            "SELECT pg_get_serial_sequence('seqtest.rev', 'id')"
        ).fetchone()[0]

        assert resolved == "seqtest.rev_id_seq"
        connection.execute("DROP SCHEMA seqtest CASCADE")
        connection.commit()


@requires_scratch_db
def test_d2_corrective_setval_survives_an_empty_target() -> None:
    """D2：空目標邊界（`box_pitching_revisions` 正是此狀態，prod 0 列）。

    兩種直覺寫法各有一種失效形態，而且**兩種都不是「報錯就好」**：

    - `setval(seq, (SELECT max(id) …), true)`：`setval` 是 STRICT，NULL 參數**不報錯**，
      而是靜默回 NULL、序列原封不動。這比報錯更危險——修法會看起來生效卻什麼也沒做。
      （規劃期把它記成「當場報錯」，實測為誤。）
    - `setval(seq, COALESCE(max(id), 0), true)`：0 低於序列 MINVALUE，**這個才報錯**。

    `GREATEST(COALESCE(…, 0), 1)` ＋ 第三參數 `is_called = count(*) > 0` 同時處理兩者，
    且首列 id 必須是 1（不是 2）。
    """
    import psycopg

    with _scratch_connection() as connection:
        connection.execute(
            "CREATE TABLE seqtest.rev ("
            "  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,"
            "  content_key text NOT NULL UNIQUE)"
        )
        connection.commit()
        before = connection.execute("SELECT last_value, is_called FROM seqtest.rev_id_seq").fetchone()

        # 形態一：靜默 no-op（不拋例外，序列未變）。
        naive = connection.execute(
            "SELECT setval(pg_get_serial_sequence('seqtest.rev','id'),"
            " (SELECT max(id) FROM seqtest.rev), true)"
        ).fetchone()[0]
        assert naive is None, "STRICT 函式對 NULL 參數應回 NULL"
        assert (
            connection.execute("SELECT last_value, is_called FROM seqtest.rev_id_seq").fetchone()
            == before
        ), "靜默 no-op：序列必須原封不動"

        # 形態二：COALESCE(...,0) 撞 MINVALUE，這個才報錯。
        with pytest.raises(psycopg.errors.NumericValueOutOfRange, match="out of bounds"):
            with connection.transaction():
                connection.execute(
                    "SELECT setval(pg_get_serial_sequence('seqtest.rev','id'),"
                    " COALESCE((SELECT max(id) FROM seqtest.rev), 0), true)"
                )

        # 矯正形式：兩種形態都不發生，且首列 id = 1。
        connection.execute(
            "SELECT setval(pg_get_serial_sequence('seqtest.rev','id'),"
            " GREATEST(COALESCE((SELECT max(id) FROM seqtest.rev), 0), 1),"
            " (SELECT count(*) FROM seqtest.rev) > 0)"
        )
        connection.execute("INSERT INTO seqtest.rev (content_key) VALUES ('first')")

        assert connection.execute("SELECT id FROM seqtest.rev").fetchone()[0] == 1
        connection.execute("DROP SCHEMA seqtest CASCADE")
        connection.commit()


@requires_scratch_db
def test_d3_fixed_point_regression_of_the_2026_08_14_collision() -> None:
    """D3：定點回歸（fault injection）——`prod_max > local last_value` ＋期間有新列。

    這正是原自測漏掉的那一格：首灌（目標為空）是唯一構造上不可能觸發的情境。

    **落點也一起驗**。舊行為是否炸，取決於真插入的列落在批次的哪個位置（`pg_dump` 的
    heap 順序，每日重排）：落在地雷區才撞，落在其後就僥倖存活。2026-08-14 兩張表同時
    暴露、只有一張炸，差別就在這裡。故本測試跑兩種落點：

    - 新列在批次**前段** → 舊行為**必炸**（定點重現 08-14 的 gsr）
    - 新列在批次**尾端** → 舊行為**僥倖存活**（重現同日 gssr 的存活；證明「這次沒炸」
      從來不是修好了）

    而矯正行為在**兩種落點下都綠**——地雷區恆為 0 是構造保證，與落點無關。
    """
    import psycopg

    local_last_value, prod_max, existing_from = 150, 200, 100  # 地雷區 = 50
    upsert = (
        "INSERT INTO seqtest.dst (content_key) SELECT content_key FROM seqtest.src ORDER BY seq"
        " ON CONFLICT (content_key) DO UPDATE SET seen_count = seqtest.dst.seen_count + 1"
    )

    def _build(connection, *, new_rows_first: bool) -> None:
        connection.execute("DROP TABLE IF EXISTS seqtest.dst, seqtest.src")
        connection.execute(
            "CREATE TABLE seqtest.dst ("
            "  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,"
            "  content_key text NOT NULL UNIQUE, seen_count int NOT NULL DEFAULT 1)"
        )
        # 目標端既有列 id 100..200：模擬 prod 首灌後自行配號留下的連續區塊。
        connection.execute(
            "INSERT INTO seqtest.dst (id, content_key) OVERRIDING SYSTEM VALUE"
            " SELECT g, 'k' || g FROM generate_series(%s::int, %s::int) g",
            (existing_from, prod_max),
        )
        # 來源端（本機）：共有列 ＋ 3 列新列（真插入）。`seq` 明確固定批次內的列序，
        # 取代 heap 順序——真實情境靠運氣，測試要能指定。
        connection.execute("CREATE TABLE seqtest.src (seq int PRIMARY KEY, content_key text)")
        offset = 0 if new_rows_first else prod_max
        connection.execute(
            "INSERT INTO seqtest.src VALUES (%s,'new-a'), (%s,'new-b'), (%s,'new-c')",
            (offset + 1, offset + 2, offset + 3),
        )
        shift = 3 if new_rows_first else 0
        connection.execute(
            "INSERT INTO seqtest.src SELECT g + %s::int, 'k' || g"
            " FROM generate_series(%s::int, %s::int) g",
            (shift, existing_from, prod_max),
        )
        connection.commit()

    with _scratch_connection() as connection:
        # (a) 新列在前段：舊行為必炸——定點重現 2026-08-14 的 game_source_revisions。
        _build(connection, new_rows_first=True)
        with pytest.raises(psycopg.errors.UniqueViolation):
            with connection.transaction():
                connection.execute(
                    "SELECT setval(pg_get_serial_sequence('seqtest.dst','id'), %s, true)",
                    (local_last_value,),
                )
                connection.execute(upsert)

        # 矯正行為：setval 到目標自己的 max(id) → 配出的 id 構造上高於所有既有 id。
        with connection.transaction():
            connection.execute(
                "SELECT setval(pg_get_serial_sequence('seqtest.dst','id'),"
                " GREATEST(COALESCE((SELECT max(id) FROM seqtest.dst), 0), 1),"
                " (SELECT count(*) FROM seqtest.dst) > 0)"
            )
            connection.execute(upsert)
        total, highest = connection.execute("SELECT count(*), max(id) FROM seqtest.dst").fetchone()
        assert total == (prod_max - existing_from + 1) + 3
        assert highest > prod_max, "新列的 id 必須全部高於目標端原有的 max(id)"

        # (b) 新列在尾端：舊行為**僥倖存活**——「這次沒炸」不構成任何證據。
        _build(connection, new_rows_first=False)
        with connection.transaction():
            connection.execute(
                "SELECT setval(pg_get_serial_sequence('seqtest.dst','id'), %s, true)",
                (local_last_value,),
            )
            connection.execute(upsert)
        assert connection.execute("SELECT count(*) FROM seqtest.dst").fetchone()[0] == (
            prod_max - existing_from + 1
        ) + 3, "舊行為在此落點下存活——差別只在落點，不在修法"

        # 而矯正行為在這個落點下同樣綠（地雷區恆為 0 與落點無關）。
        _build(connection, new_rows_first=False)
        with connection.transaction():
            connection.execute(
                "SELECT setval(pg_get_serial_sequence('seqtest.dst','id'),"
                " GREATEST(COALESCE((SELECT max(id) FROM seqtest.dst), 0), 1),"
                " (SELECT count(*) FROM seqtest.dst) > 0)"
            )
            connection.execute(upsert)
        assert connection.execute("SELECT max(id) FROM seqtest.dst").fetchone()[0] > prod_max

        connection.execute("DROP SCHEMA seqtest CASCADE")
        connection.commit()
