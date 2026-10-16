"""cpbl-import-series-awards：官方系列獎項的本機離線匯入（#288 S07 WP-AWARDS；series_award_* 唯一 writer）。

流程：維護者把官方公布頁的 URL 與得主清單寫成 JSON → 本 CLI 驗證 → 寫入 DATABASE_URL 指向的庫（預設本機
共享 cpbl）→ 生產只經 `scripts/refresh-cpbl-prod.sh` 的 sync_table 同步。⛔ 爬蟲、⛔ 公開寫入 API、
⛔ 從單場 MVP 次數推獎項。寫本機共享庫前須取得資源租用；真實獎項匯入須另取需求方授權。

用法：
  cpbl-import-series-awards awards.json --dry-run     # 只驗證並列出將寫入的內容（交易回滾，不留任何列）
  cpbl-import-series-awards awards.json               # 驗證後寫入
  cpbl-import-series-awards - --dry-run < awards.json # 也可讀 stdin

輸入（官方已公布）：
  {"year": 2026, "kind_code": "C", "status": "published",
   "source_url": "https://www.cpbl.com.tw/...", "checked_at": "2026-10-26T21:00:00+08:00",
   "awards": [{"award_name": "<官方完整獎項名稱>", "award_type": "series_mvp",
               "winners": [{"winner_name": "<官方公布姓名>", "player_id": "0000000000", "team_code": "ACN011"}]}]}
輸入（本站查核時官方尚未公布）：status 改 "not_published"，且不得有 awards。
  · awards 依官方公布順序；共同得主依官方順序列在同一獎項的 winners（⛔ 壓成一人）。
  · player_id、team_code 可省略（官方名單對不到本站 ID 時不猜）；revision 可省略（自動取下一號）。

不變量：同內容重送＝冪等（不新增 revision）；指定已存在的 revision 號＝拒收；revision 只追加、不可改
        （migration 078 觸發器）；status=published 必有得主、not_published 不得有得主。

退出碼：
  0 成功（created／unchanged／dry-run 通過） · 2 參數錯 · 10 輸入不合格（逐條列原因）
  13 revision 號已存在或不大於最新（只追加） · 20 寫入失敗（DB 錯誤，交易已回滾）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from cpbl.ingest._cli import cli_parser
from cpbl.playoffs.series_awards import (
    AwardInputError,
    DuplicateRevisionError,
    parse_input,
    write_revision,
)

PROG = "cpbl-import-series-awards"
EXIT_INVALID = 10
EXIT_DUPLICATE = 13
EXIT_DB = 20


def _parser():
    p = cli_parser(PROG, __doc__)
    p.add_argument("input", help="輸入 JSON 檔路徑；- 表示 stdin")
    p.add_argument("--dry-run", action="store_true", help="只驗證並列出內容，交易回滾不留列")
    return p


def _load(path: str) -> dict:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return json.loads(text)


def _describe(item) -> list[str]:
    lines = [f"{item.year}/{item.kind_code} status={item.status} checked_at={item.checked_at.isoformat()}",
             f"  source_url={item.source_url}", f"  content_sha256={item.content_sha256()}"]
    for seq, a in enumerate(item.awards, 1):
        names = "、".join(f"{w.winner_name}({w.player_id or '—'}/{w.team_code or '—'})" for w in a.winners)
        lines.append(f"  {seq}. {a.award_name} [{a.award_type}]：{names}")
    return lines


def run(argv: list[str] | None = None, *, connect=None) -> int:
    args = _parser().parse_args(argv)
    try:
        raw = _load(args.input)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"⛔ 讀不到輸入或不是合法 JSON：{exc}", file=sys.stderr)
        return EXIT_INVALID
    if connect is None:
        from cpbl.db import conn as connect
    try:
        with connect() as c:
            with c.transaction():
                cur = c.cursor()
                cur.execute("SELECT team_code FROM cpbl.team_dim")
                team_codes = {r[0] for r in cur.fetchall()}
                try:
                    item = parse_input(raw, team_codes=team_codes)
                except AwardInputError as exc:
                    print("⛔ 輸入不合格，拒收：", file=sys.stderr)
                    for e in exc.errors:
                        print(f"  - {e}", file=sys.stderr)
                    raise _Rollback(EXIT_INVALID) from None
                try:
                    result = write_revision(cur, item)
                except DuplicateRevisionError as exc:
                    print(f"⛔ {exc}", file=sys.stderr)
                    raise _Rollback(EXIT_DUPLICATE) from None
                print("\n".join(_describe(item)))
                if args.dry_run:
                    print(f"dry-run：將 {result.action} revision {result.revision}（已回滾，未寫入）")
                    raise _Rollback(0)
                print(f"{result.action} revision {result.revision}")
                return 0
    except _Rollback as rb:
        return rb.code
    except Exception as exc:  # noqa: BLE001 — DB 錯誤（含觸發器拒絕）：交易已由 context manager 回滾
        print(f"⛔ 寫入失敗（已回滾）：{type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_DB


class _Rollback(Exception):  # noqa: N818 — 控制流：離開交易區塊即回滾
    def __init__(self, code: int):
        super().__init__(code)
        self.code = code


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
