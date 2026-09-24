"""`refresh-cpbl-prod.sh` 的 `sync_table` 欄位清單漂移守衛（2026-09-23）。

缺陷形狀：`sync_table` 是 `INSERT … ON CONFLICT DO UPDATE SET <清單>`，清單外的欄在生產端
「只插不更」，而同步照樣 exit 0。pitch_tracking 曾因此漏 19 欄。守衛在寫入前比對本機
schema，漏欄即非零結束、不送出任何 payload。

做法：從**真腳本**抽出 `sync_table` 函式本體，以假 `docker`／`ssh` 執行（零 DB、零網路）。
假 docker 對欄位查詢回傳 `STUB_COLUMNS`，對 pg_dump 回一段最小 COPY；假 ssh 把 stdin 寫檔，
所以「有沒有送出 payload」可直接斷言。
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "refresh-cpbl-prod.sh"

_DOCKER = """#!/bin/sh
case "$*" in
  *information_schema.columns*) printf '%s\\n' $STUB_COLUMNS ;;
  *pg_dump*) printf 'COPY cpbl.t (id) FROM stdin;\\n1\\n\\\\.\\n' ;;
  *) : ;;
esac
"""
_SSH = """#!/bin/sh
cat > "$STUB_SSH_OUT"
"""


def _function_body() -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    m = re.search(r"^sync_table\(\) \{\n.*?^\}\n", text, re.S | re.M)
    assert m, "找不到 sync_table 函式本體——函式被改名或搬走了，本測試要跟著改"
    return m.group(0)


def _run(tmp_path: Path, columns: list[str], table: str, pk: str, cols: list[str]):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (("docker", _DOCKER), ("ssh", _SSH)):
        (bin_dir / name).write_text(body, encoding="utf-8")
        (bin_dir / name).chmod(0o755)
    out = tmp_path / "ssh_payload.sql"
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "STUB_COLUMNS": " ".join(columns),
        "STUB_SSH_OUT": str(out),
        # fail-safe：不可達的主機／容器，假樁沒攔到也碰不到真實環境
        "LOCAL_DB": "stub-nonexistent-container", "VPS": "stub@harness.invalid",
        "DEPLOY_PATH": "/nonexistent/stub-deploy",
    }
    script = "set -euo pipefail\n" + _function_body() + 'sync_table "$@"\n'
    result = subprocess.run(["/bin/bash", "-c", script, "harness", table, pk, *cols],
                            env=env, text=True, capture_output=True, check=False)
    payload = out.read_text(encoding="utf-8") if out.exists() else None
    return result, payload


def test_complete_list_is_synced(tmp_path: Path) -> None:
    result, payload = _run(tmp_path, ["id", "a", "b"], "t", "id", ["a", "b"])

    assert result.returncode == 0, result.stderr
    assert payload is not None
    assert ("INSERT INTO cpbl.t AS tgt SELECT * FROM _stg ON CONFLICT (id) DO UPDATE SET "
            "a=EXCLUDED.a,b=EXCLUDED.b WHERE ROW(tgt.a,tgt.b) IS DISTINCT FROM "
            "ROW(EXCLUDED.a,EXCLUDED.b);") in payload


def test_missing_column_fails_before_any_payload_is_sent(tmp_path: Path) -> None:
    """核心回歸：本機有 c、清單沒有 → 非零結束，且**一份 payload 都沒送出**。"""
    result, payload = _run(tmp_path, ["id", "a", "b", "c"], "t", "id", ["a", "b"])

    assert result.returncode != 0
    assert "sync_table t" in result.stderr and "c" in result.stderr.split("：")[-1]
    assert payload is None


def test_composite_primary_key_columns_are_not_reported_missing(tmp_path: Path) -> None:
    columns = ["year", "kind_code", "game_sno", "pitcher_acnt", "pitch_cnt", "rel_speed"]
    result, payload = _run(tmp_path, columns, "pitch_tracking",
                           "year,kind_code,game_sno,pitcher_acnt,pitch_cnt", ["rel_speed"])

    assert result.returncode == 0, result.stderr
    assert payload is not None


def test_every_sync_table_call_in_the_script_parses() -> None:
    """清單格式本身的健全性：每個呼叫都有表名、PK 與至少一個更新欄，且更新欄不重複、不含 PK。

    ⚠️ 這裡驗不了「清單是否涵蓋本機 schema」——CI 沒有 DB。那一半由守衛在每次同步時
    對真實 schema 執行（本卡交付時以真本機 DB 跑過 44 個呼叫全數放行）。
    """
    joined = re.sub(r"\\\n\s*", " ", SCRIPT.read_text(encoding="utf-8"))
    calls = re.findall(r'^\s*sync_table\s+(\w+)\s+"([^"]+)"\s*(.*)$', joined, re.M)
    assert len(calls) >= 44
    for table, pk, rest in calls:
        cols = [x for x in rest.split() if re.fullmatch(r"\w+", x)]
        assert cols, table
        assert len(cols) == len(set(cols)), f"{table} 更新欄重複"
        assert not set(cols) & set(pk.split(",")), f"{table} 更新欄含 PK"


@pytest.mark.skipif(os.name != "posix", reason="需要 /bin/bash")
def test_guard_runs_before_the_payload_pipeline() -> None:
    """守衛必須在 `{ …pg_dump… } | ssh` 管線之前——放在後面等於寫完才檢查。"""
    body = _function_body()
    assert body.index("return 1") < body.index("| ssh")
