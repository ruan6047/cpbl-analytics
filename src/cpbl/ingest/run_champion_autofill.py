"""CLI：新球季冠軍自動補列（#469；不 migrate、不爬蟲）。

    cpbl-champion-autofill

一軍收官判定 decided 且 ``cpbl.championships`` 缺該年 ⇒ 補冠軍與奪冠總教練列（只新增不覆蓋），
只有實際補了列才重建 ``championship_members``。結果以一行 JSON 印到 stdout；失敗以退出碼 1 結束。
``CPBL_CHAMPION_AUTOFILL=off`` 停用（不讀不寫）。

正式站由 VPS timer ``cpbl469-champion-autofill`` 每日執行
``docker exec prod_cpbl_api cpbl-champion-autofill``（unit 檔：``ops/vps/``）。
⛔ 刻意不呼叫 ``migrate()``——正式庫用 ``cpbl-build-championships``（會 migrate）是禁止的。
"""

from __future__ import annotations

import argparse
import json
import logging

from cpbl.ingest._cli import cli_parser
from cpbl.ingest.championships import run_champion_autofill


def _parser() -> argparse.ArgumentParser:
    return cli_parser("cpbl-champion-autofill", __doc__)


def main() -> None:
    _parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    code, out = run_champion_autofill()
    print(json.dumps(out, ensure_ascii=False, sort_keys=True, default=str), flush=True)
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
