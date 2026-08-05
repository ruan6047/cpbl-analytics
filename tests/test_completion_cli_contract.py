"""`python -m cpbl.completion` 的 shell 契約回歸。

scripts/refresh-cpbl-prod.sh 以 `$(uv run python -m cpbl.completion)` 把 stdout
直接內插進 SQL（reconciliation gate）。契約：**恰一行**、無別名前綴、內容＝
`completed_games_sql()`。2026-08-05 曾因 __main__ 多印一行 evidence 版判準，
使內插後 SQL 語法錯誤（釋出阻斷缺陷，PM 熱修）——本檔釘住該契約。
"""

from __future__ import annotations

import subprocess
import sys

from cpbl.completion import completed_games_sql, completed_games_sql_with_evidence


def _run_module(*args: str) -> list[str]:
    out = subprocess.run(
        [sys.executable, "-m", "cpbl.completion", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.splitlines()


def test_default_stdout_is_exactly_one_line_of_legacy_predicate():
    lines = _run_module()
    assert lines == [completed_games_sql()]


def test_default_stdout_has_no_alias_prefix():
    (line,) = _run_module()
    assert "g." not in line


def test_with_evidence_flag_is_exactly_one_line_of_evidence_predicate():
    lines = _run_module("--with-evidence")
    assert lines == [completed_games_sql_with_evidence("g")]
