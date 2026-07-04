"""CLI【實驗】：賽況即時 TrackMan 單次探測（不寫 DB、不掛排程；等使用者下令實測）。

    uv run cpbl-live-game 2026 A 186                 # 單次探測並印觀測報告
    uv run cpbl-live-game 2026 A 186 /tmp/g186.json  # 另存完整 payload 供分析

可行性驗證法：比賽進行中對當日場次跑 2-3 次（間隔 1-2 分鐘），
比對 trackman_nodes / 比分是否隨局勢更新。
"""

from __future__ import annotations

import json
import logging
import sys

from cpbl.ingest.cpbl_live_game import probe


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    year, kind, sno = int(sys.argv[1]), sys.argv[2], int(sys.argv[3])
    dump = sys.argv[4] if len(sys.argv) > 4 else None
    print(json.dumps(probe(year, kind, sno, dump_path=dump), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
