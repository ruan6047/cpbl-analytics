"""CLI 入口的 `--help` 護欄（DEV-CLI-HELP-GUARD1／GUARD2）。

模組雖然放在 `cpbl.ingest` 底下（GUARD1 只授權改 ingest/），使用者已擴及
`cpbl.models` 與 `cpbl.features` 的入口（GUARD2）。搬到 `cpbl/_cli.py` 會更符合分層，
但那要動 30 個 ingest 入口的 import，不在 GUARD2 範圍——留給後續整理。


2026-08-05 跨家族查核期間，查核者為了看用法打了 `cpbl-scrape-pitches --help`，
結果 `--help` 被當成位置參數吞掉，直接對官方 stats 站開了真實爬蟲並寫入 DB（+46 列）。
**用 `--help` 探索一支 CLI 竟然有副作用**——這是工程安全缺陷，不只是使用體驗問題：
查核者、新進維運者、任何人第一次碰這些指令時的自然動作就是先打 `--help`。

本模組提供所有 CLI 入口共用的 argparse 殼，保證三件事：

1. `-h/--help` 由 argparse 原生處理 → 印 usage 後 `SystemExit(0)`，主流程一行都沒跑。
2. 未知旗標／無法辨識的位置參數 → `SystemExit(2)`，主流程不執行。
3. 既有合法呼叫形式完全不變——launchd 排程（`scripts/scrape-daily.sh`、
   `scripts/weekly-game-pitches.sh`）與 docs／docstring 裡的指令一個都不能壞。

為同時滿足 (2) 與 (3)，位置參數的語意刻意保持原樣，依既有解析風格分兩類處理：

* **順序無關嗅探型**（如 `cpbl-scrape-pitches 2026 A 1.5`，年/賽別/秒數可任意排列）
  沿用既有嗅探函式，只把「無法辨識的 token 靜默略過」改成 `parser.error()`。
  靜默略過正是事故的放大器：`--help` 被吞掉後沒有留下任何跡象。
* **固定位序型**（原本讀 `sys.argv[1]`、`sys.argv[2]`…）直接宣告成 argparse 位置參數，
  型別與預設值逐一對齊原本的 `int()` / `float()` 與 `or` 預設，語意零改變。

`allow_abbrev=False`：不接受旗標縮寫。排程腳本只用完整旗標，關掉可避免未來新增旗標時
既有縮寫突然變歧義而在 cron 裡靜默失敗。
"""

from __future__ import annotations

import argparse

KIND_CODES = ("A", "C", "D", "E")
"""賽別碼：A 一軍例行 / C 一軍季後 / D 二軍 / E 二軍季後。"""


def cli_parser(prog: str, doc: str | None = None) -> argparse.ArgumentParser:
    """建立統一格式的 parser：模組 docstring 原樣當說明（裡面就有用法範例）。"""
    return argparse.ArgumentParser(
        prog=prog,
        description=doc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
