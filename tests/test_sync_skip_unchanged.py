"""`sync_table` 只改真的變了的列（2026-09-24）。

為什麼：原本每次同步把送過去的每一列都 UPDATE 一次（約 2,177,577 列，game_livelog 全史
1,392,649 列），生產端 game_livelog 累計 n_tup_upd 86,791,479 對 n_tup_ins 68,228——幾乎全是
值沒變的重寫，在 1 vCPU／950MB 的 VPS 上變成大量換頁。見 `scripts/refresh-cpbl-prod.sh`。

本測試驗**接線**：真腳本送出的每一句 upsert 都帶 `WHERE ROW(tgt.…) IS DISTINCT FROM
ROW(EXCLUDED.…)`，且比較欄位與 SET 欄位是同一份清單（漏比一欄＝那欄改了也不會同步）。
SQL 行為本身 2026-09-24 已對本機 DB 實測（交易內執行後 ROLLBACK）：45 張同步表以自身資料
為 staging（2,179,532 列）全部 `INSERT 0 0`；games 改 4 處（文字改值、NULL→值、值→NULL、
新增一列）得 `INSERT 0 4`。
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.test_prod_sync_revision_seq import _run_refresh

_UPSERT = re.compile(
    r"^INSERT INTO cpbl\.(?P<table>\w+) AS tgt SELECT \* FROM _stg "
    r"ON CONFLICT \((?P<pk>[^)]*)\) DO UPDATE SET (?P<set>.+) "
    r"WHERE ROW\((?P<old>[^)]*)\) IS DISTINCT FROM ROW\((?P<new>[^)]*)\);$"
)


def _sync_table_upserts(tmp_path: Path) -> list[str]:
    result, calls = _run_refresh(tmp_path)
    assert result.returncode == 0, f"harness 未跑完：rc={result.returncode}\n{result.stderr}"
    lines = [line for c in calls for line in c["stdin"].splitlines()
             if line.startswith("INSERT INTO cpbl.") and "FROM _stg ON CONFLICT" in line]
    assert lines, "一句 sync_table upsert 都沒抓到——不接受「沒找到所以沒問題」"
    return lines


def test_every_sync_table_upsert_skips_unchanged_rows(tmp_path: Path) -> None:
    for line in _sync_table_upserts(tmp_path):
        m = _UPSERT.match(line)
        assert m, f"upsert 缺少只改變動列的 WHERE（或形狀變了）：{line[:200]}"
        set_cols = [a.split("=EXCLUDED.")[0] for a in m["set"].split(",")]
        assert all(f"{c}=EXCLUDED.{c}" in m["set"].split(",") for c in set_cols), line[:200]
        assert m["old"].split(",") == [f"tgt.{c}" for c in set_cols], (m["table"], m["old"])
        assert m["new"].split(",") == [f"EXCLUDED.{c}" for c in set_cols], (m["table"], m["new"])
