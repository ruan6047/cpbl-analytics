"""#353 WP1：canonical PA 五表的每日同步——逐場增量替換＋事後全族對帳（取代 TRUNCATE＋全量重灌）。

用法（由 ``scripts/refresh-cpbl-prod.sh`` 的 ``sync_pa_build`` 呼叫；一般不需手動跑）::

    python -m cpbl.ingest.pa_incremental --help
    python -m cpbl.ingest.pa_incremental payload   --local-psql CMD --target-psql CMD --out FILE [--full]
    python -m cpbl.ingest.pa_incremental reconcile --local-psql CMD --target-psql CMD

為什麼（研究 2 直接量到）：舊做法在單一交易內 ``TRUNCATE`` 五表再重灌，ACCESS EXCLUSIVE 一路持有到
commit（正式站約 7 分 20 秒）；期間讀 PA 表的請求全部排隊，API 連線池 8 條被占滿，連 info 端點
都等不到連線。改成 DELETE 只取 ROW EXCLUSIVE，讀者走 MVCC 看到交易前的快照，不被擋。

設計（核定規劃 r2 §3 WP1）：

1. **簽章**：每場 ``game_recap_builds`` 全列文字（含 ``state``——``pa_build.py`` 會把 published 改成
   superseded 而 build_id 不變）＋該場 ``game_recap_source_revisions`` 的 id 集合，各取 md5；本機與
   production 各查一次。列文字依 session 的 TimeZone／DateStyle 等而變，所以查詢內先 ``SET LOCAL`` 固定。
2. **差異場**＝簽章不同 ∪ production 有本機無 ∪ 本機有 production 無。0 場＝不送任何 payload。
3. **payload**：與晚間鏈 ``boxpa_sync.build_pa_payload`` **同一個產生器**（:func:`boxpa_sync.write_pa_payload`）
   ——交易內 lock／statement timeout、production 端 FK 閉包守衛、子→父 DELETE 目標鍵、父→子
   ``OVERRIDING SYSTEM VALUE`` 插入、寫入後列數自檢；送出前以同一支守衛逐行斷言。鍵來自簽章比對
   （含 D、不設 7 場上限），⛔ 不經、也不放寬晚間鏈的 ``parse_games``（A|E|C、≤7 場）。
4. **全族對帳**（fail-closed）：五表總列數＋各表 max(identity)＋published build 集合，本機與 production
   必須相等；不等 ⇒ 非零結束，交需求方決定是否授權全量模式（D5：現在不授權、個案裁定）。
5. **全量模式**（``--full``；shell 端 ``PA_FULL_RESYNC=1``）：scope＝全部場（``WHERE TRUE``），同一產生器，
   不 TRUNCATE，讀者不被擋；代價重（P1 容器：耗時約 TRUNCATE 的 4.7 倍、WAL 1.5 倍、表暫時 2 倍），
   只能人工指定，⛔ 每日鏈不得自動觸發（shell 端在 ``DAILY_DAY_TYPE`` 存在時拒絕）。

FIX1／#88 不變量照舊成立：production 不是這五表的 writer，id 一律鏡像本機。刪除範圍是「該場的
全部列」而不是用 id 對齊，所以 2026-08-03 那種「內容相同、id 不同」的殘留列，只要所在的場被替換
就會一併清掉；簽章沒變卻帶著漂移的場，由第 4 步的全族對帳抓出來，再用全量模式修。

離開碼：0 成功 · 64 參數錯 · 67 本機自檢／簽章鍵異常／payload 守衛不過（未送）· 68 全族對帳不等
· 72 ssh 連線失敗 · 74 production psql 報錯。
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from cpbl.ingest._cli import cli_parser
from cpbl.ingest.boxpa_sync import (
    EXIT_MISMATCH,
    EXIT_SELF_CHECK,
    PA_TABLES,
    GameKey,
    Psql,
    SyncError,
    assert_pa_lines,
    closure_violations_sql,
    keys_sql,
    write_pa_payload,
)

# 列文字（b::text）與 timestamptz 顯示依 session 設定而變；兩端各自的預設不保證相同，故查詢內固定。
_PIN_SESSION = (
    "SET LOCAL TimeZone = 'UTC'; SET LOCAL DateStyle = 'ISO, YMD'; "
    "SET LOCAL IntervalStyle = 'postgres'; SET LOCAL extra_float_digits = 1;\n"
)

SIGNATURE_SQL = _PIN_SESSION + """\
SELECT k.year, k.kind_code, k.game_sno, COALESCE(b.sig, '-') || '/' || COALESCE(r.sig, '-')
FROM (SELECT year, kind_code, game_sno FROM cpbl.game_recap_builds
      UNION SELECT year, kind_code, game_sno FROM cpbl.game_recap_source_revisions) k
LEFT JOIN (SELECT year, kind_code, game_sno, md5(string_agg(b::text, '|' ORDER BY b.build_id)) AS sig
           FROM cpbl.game_recap_builds b GROUP BY year, kind_code, game_sno) b
       USING (year, kind_code, game_sno)
LEFT JOIN (SELECT year, kind_code, game_sno, md5(string_agg(id::text, ',' ORDER BY id)) AS sig
           FROM cpbl.game_recap_source_revisions GROUP BY year, kind_code, game_sno) r
       USING (year, kind_code, game_sno)"""

# 各表的 identity／代理鍵欄（builds 是 uuid、無序數，不比 max）。
IDENTITY_COLUMN: dict[str, str] = {
    "game_recap_source_revisions": "id",
    "game_plate_appearances": "pa_row_id",
    "game_pa_events": "id",
    "game_pa_pitch_mappings": "id",
}

FAMILY_SQL = _PIN_SESSION + "\n UNION ALL ".join(
    [f"SELECT '{t}', count(*)::text, "
     + (f"COALESCE(max({IDENTITY_COLUMN[t]}), 0)::text" if t in IDENTITY_COLUMN else "''")
     + f" FROM cpbl.{t}" for t in PA_TABLES]
    + ["SELECT 'published', count(*)::text, COALESCE(md5(string_agg("
       "year || '-' || kind_code || '-' || game_sno || ':' || build_id::text, ',' "
       "ORDER BY year, kind_code, game_sno)), '') FROM cpbl.game_recap_builds WHERE state = 'published'"]
)

# 每日差異場的上限。P2（2026-09-24 起 21 個有變動的日子）單日最多 22 場；全史約 4,511 場。
# 超過＝簽章失準（例如兩端列文字不一致）的訊號：照跑等於每日鏈自動做一次近乎全量的 DELETE＋INSERT，
# 而全量模式只能人工指定（D5）。故拒絕並交人判斷，不自動降級成全量。
MAX_INCREMENTAL_GAMES = 200
FULL_SCOPE = "TRUE"
# 全量模式單一語句（全表 DELETE／INSERT）在 1 vCPU 上可能遠超增量的 300s（P1 容器全量 DELETE
# 整段 318.9s；VPS 未量）。只在人工指定時用。
FULL_STATEMENT_TIMEOUT = "3600s"

_KIND_RE = re.compile(r"^[A-Z]$")
_INT_RE = re.compile(r"^\d{1,4}$")


def _key(row: list[str]) -> GameKey:
    """簽章列 → 鍵。值會被內插進 SQL（:func:`keys_sql`），故逐欄以正規式驗過；不符 ⇒ 67。"""
    if (len(row) != 4 or not _INT_RE.fullmatch(row[0]) or not _KIND_RE.fullmatch(row[1])
            or not _INT_RE.fullmatch(row[2])):
        raise SyncError(EXIT_SELF_CHECK, f"簽章列的場次鍵不符預期形狀（不送）：{row[:3]!r}")
    return GameKey(int(row[0]), row[1], int(row[2]))


def signatures(db: Psql) -> dict[GameKey, str]:
    return {_key(row): row[3] for row in db.read(SIGNATURE_SQL)}


def diff_games(local: Mapping[GameKey, str], target: Mapping[GameKey, str]) -> list[GameKey]:
    return sorted(k for k in local.keys() | target.keys() if local.get(k) != target.get(k))


def write_payload(local: Psql, target: Psql, out: TextIO, *, full: bool = False) -> list[GameKey] | None:
    """寫出 payload（差異 0 場時什麼都不寫）。回傳本次替換的場；全量模式回 None。"""
    if full:
        write_pa_payload(local, out, scope=FULL_SCOPE, closure_sql=None,
                         statement_timeout=FULL_STATEMENT_TIMEOUT)
        return None
    keys = diff_games(signatures(local), signatures(target))
    if len(keys) > MAX_INCREMENTAL_GAMES:
        raise SyncError(EXIT_SELF_CHECK,
                        f"差異場 {len(keys)} 場超過每日上限 {MAX_INCREMENTAL_GAMES}（疑似簽章失準；未送）。"
                        "⛔ 不自動改跑全量；交需求方判斷是否授權 PA_FULL_RESYNC=1")
    if keys:
        write_pa_payload(local, out, scope=keys_sql(keys), closure_sql=closure_violations_sql(keys))
    return keys


def assert_payload_file(path: Path, keys: list[GameKey] | None) -> None:
    scope = FULL_SCOPE if keys is None else keys_sql(keys)
    with path.open(encoding="utf-8") as fh:
        assert_pa_lines((line.rstrip("\n") for line in fh), scope)


def family(db: Psql) -> dict[str, list[str]]:
    return {row[0]: row[1:] for row in db.read(FAMILY_SQL)}


def reconcile_family(local: Psql, target: Psql) -> dict:
    lf, tf = family(local), family(target)
    names = [*PA_TABLES, "published"]
    tables = {n: {"local": lf.get(n), "prod": tf.get(n)} for n in names}
    ok = all(v["local"] is not None and v["local"] == v["prod"] for v in tables.values())
    return {"at": datetime.now(UTC).isoformat(), "ok": ok, "tables": tables}


def _parser():
    p = cli_parser("python -m cpbl.ingest.pa_incremental", __doc__)
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("payload", "reconcile"):
        s = sub.add_parser(name)
        s.add_argument("--local-psql", required=True)
        s.add_argument("--target-psql", required=True)
        if name == "payload":
            s.add_argument("--out", required=True)
            s.add_argument("--full", action="store_true", help="全量模式（只能人工指定）")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    local = Psql(args.local_psql, label="local")
    target = Psql(args.target_psql, label="target")
    try:
        if args.command == "payload":
            out = Path(args.out)
            with out.open("w", encoding="utf-8") as fh:
                keys = write_payload(local, target, fh, full=args.full)
            if keys == []:
                print("PA_INCREMENTAL_GAMES=0")
                return 0
            assert_payload_file(out, keys)
            if keys is None:
                print(f"PA_FULL_RESYNC_PAYLOAD_BYTES={out.stat().st_size}")
            else:
                print(f"PA_INCREMENTAL_GAMES={len(keys)} {','.join(k.text for k in keys)}")
                print(f"PA_INCREMENTAL_PAYLOAD_BYTES={out.stat().st_size}")
            return 0
        manifest = reconcile_family(local, target)
        print("PA_RECONCILE=" + json.dumps(manifest, ensure_ascii=False, sort_keys=True))
        return 0 if manifest["ok"] else EXIT_MISMATCH
    except SyncError as exc:
        if args.command == "payload":
            Path(args.out).write_text("", encoding="utf-8")  # 守衛不過：不留下半份可被誤送的檔
        print(f"✗ {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
