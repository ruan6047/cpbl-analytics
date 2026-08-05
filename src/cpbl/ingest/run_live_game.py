"""CLI【實驗】：賽況即時 TrackMan 單次探測（不寫 DB、不掛排程；等使用者下令實測）。

    uv run cpbl-live-game 2026 A 186                 # 單次探測並印觀測報告
    uv run cpbl-live-game 2026 A 186 /tmp/g186.json  # 另存完整 payload 供分析

可行性驗證法：比賽進行中對當日場次跑 2-3 次（間隔 1-2 分鐘），
比對 trackman_nodes / 比分是否隨局勢更新。
"""

from __future__ import annotations

import argparse
import json
import logging

from cpbl.ingest._cli import KIND_CODES, cli_parser
from cpbl.ingest.cpbl_live_game import probe


def _parser() -> argparse.ArgumentParser:
    p = cli_parser("cpbl-live-game", __doc__)
    p.add_argument("year", type=int, help="年份")
    p.add_argument("kind", choices=KIND_CODES, help="賽別碼")
    p.add_argument("sno", type=int, help="game_sno")
    p.add_argument("dump", nargs="?", help="另存完整 payload 的路徑（省略＝不存）")
    return p


def main() -> None:
    args = _parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    payload = probe(args.year, args.kind, args.sno, dump_path=args.dump)
    print(json.dumps(payload, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
