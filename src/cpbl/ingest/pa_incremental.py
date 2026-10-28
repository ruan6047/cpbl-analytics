"""#353：canonical PA 五表的每日同步——逐場增量替換＋事後全族對帳（取代 TRUNCATE＋全量重灌）；
r4 起全量與超過一批的增量都改成逐批小交易＋批間限速。

用法（由 ``scripts/refresh-cpbl-prod.sh`` 的 ``sync_pa_build`` 呼叫；一般不需手動跑）::

    python -m cpbl.ingest.pa_incremental --help
    python -m cpbl.ingest.pa_incremental apply     --local-psql CMD --target-psql CMD --apply-psql CMD
                                                   --workdir DIR [--full] [--batch-games N]
                                                   [--pause-ratio R] [--pause-min S]
    python -m cpbl.ingest.pa_incremental reconcile --local-psql CMD --target-psql CMD

為什麼（研究 2 直接量到）：舊做法在單一交易內 ``TRUNCATE`` 五表再重灌，ACCESS EXCLUSIVE 一路持有到
commit（正式站約 7 分 20 秒）；期間讀 PA 表的請求全部排隊，API 連線池 8 條被占滿，連 info 端點
都等不到連線。改成 DELETE 只取 ROW EXCLUSIVE，讀者走 MVCC 看到交易前的快照，不被擋。

為什麼要分批（研究 3，規劃 r4）：不擋讀者還不夠。10/28 全量是 4,513 場、1,445,834,586 bytes 的
**單一**交易，套用期間 1 vCPU 被吃滿（sar %user 93.78、%idle 0），哨兵量到 recap-wp 6.21s。所以把
場次切成每批 ``PA_BATCH_GAMES`` 場的小交易，批與批之間停下來把 CPU 讓給 API。

設計（核定規劃 r2 §3 WP1＋r4 §3、§4、§6）：

1. **簽章**：每場 ``game_recap_builds`` 全列文字（含 ``state``——``pa_build.py`` 會把 published 改成
   superseded 而 build_id 不變）＋該場 ``game_recap_source_revisions`` 的 id 集合，各取 md5；本機與
   production 各查一次。列文字依 session 的 TimeZone／DateStyle 等而變，所以查詢內先 ``SET LOCAL`` 固定。
2. **要替換的場**：增量＝簽章不同 ∪ production 有本機無 ∪ 本機有 production 無（0 場＝不送）；
   全量＝兩端五張表各自 DISTINCT 場次鍵的聯集（:data:`FULL_KEYS_SQL`）。全量不能只用簽章鍵：舊的
   ``WHERE TRUE`` 會刪掉場次不在 builds／source_revisions 上的孤兒列，聯集才保住同一個覆蓋範圍。
3. **每批 payload**：與晚間鏈 ``boxpa_sync.build_pa_payload`` **同一個產生器**
   （:func:`boxpa_sync.write_pa_payload`）——交易內 lock／statement timeout（300s）、production 端 FK
   閉包守衛（全量的每一批也帶）、子→父 DELETE 該批鍵、父→子 ``OVERRIDING SYSTEM VALUE`` 插入、寫入後
   列數自檢；送出前以同一支守衛逐行斷言。鍵來自簽章比對或全量聯集（含 D、不設 7 場上限），
   ⛔ 不經、也不放寬晚間鏈的 ``parse_games``（A|E|C、≤7 場）。增量 ≤ 一批時就是一批、一個交易、
   不暫停，payload 與 34aa6dd4 逐位元相同（tests/test_pa_batched_353.py 黃金值）。
4. **限速**：每批送出後暫停 ``max(PA_BATCH_PAUSE_MIN_S, 該批送出耗時 × PA_BATCH_PAUSE_RATIO)`` 秒，
   最後一批後不停。批間不送任何資料，ssh／docker exec／psql 管線與 backend 同時閒置。
5. **原子性單位是「批」（每場一致），不是全族**：第 k 批失敗 ⇒ 立即停止，不送後續批、不做對帳，
   以該批的離開碼結束；production 會是「第 1…k−1 批已換成本機版本、其餘仍是舊版本」，每場內部一致
   （批次原子＋閉包守衛）。stderr 印出已提交範圍與失敗批的場次鍵。恢復＝重跑同一指令（冪等），
   或剩餘差異 ≤ 上限時由下一次每日增量收斂；⛔ 不自動重跑。
6. **全族對帳**（fail-closed，shell 端在全部批次成功後呼叫一次 ``reconcile``）：五表總列數＋各表
   max(identity)＋published build 集合，本機與 production 必須相等；不等 ⇒ 非零結束。
7. **全量模式**（``--full``；shell 端 ``PA_FULL_RESYNC=1``）只能人工指定，⛔ 每日鏈不得自動觸發
   （shell 端在 ``DAILY_DAY_TYPE`` 存在時拒絕）。套用期間本機 PA builder 不得執行（每批 payload 在送出前
   才從本機產生）；這由共同主 PM 排窗口互斥，不是本模組的機制。

FIX1／#88 不變量照舊成立：production 不是這五表的 writer，id 一律鏡像本機。刪除範圍是「該場的
全部列」而不是用 id 對齊，所以 2026-08-03 那種「內容相同、id 不同」的殘留列，只要所在的場被替換
就會一併清掉；簽章沒變卻帶著漂移的場，由全族對帳抓出來，再用全量模式修。

離開碼：0 成功 · 64 參數錯（含批次設定越界）· 67 本機自檢／鍵異常／payload 守衛不過（該批未送）
· 68 全族對帳不等 · 72 ssh 連線失敗 · 74 production psql 報錯。72／74／67 發生在第 k 批時，
第 1…k−1 批已提交。
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, TextIO

from cpbl.ingest._cli import cli_parser
from cpbl.ingest.boxpa_sync import (
    EXIT_MISMATCH,
    EXIT_SELF_CHECK,
    EXIT_USAGE,
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

# 全量的場次集合：兩端五張表各自的 DISTINCT 場次鍵（含只出現在子表的孤兒場）。各表都有以
# (year, kind_code, game_sno) 開頭的索引，game_pa_pitch_mappings 除外（規劃 r4 §1）。
FULL_KEYS_SQL = "\n UNION ".join(f"SELECT year, kind_code, game_sno FROM cpbl.{t}" for t in PA_TABLES)

# 分批與限速（規劃 r4 §6 第 2 項；預設值是推論值，E0 證據見 exec-2 報告）。環境變數可調，
# 但增量 ≤ 一批時不暫停這一點不可調（只有一批＝沒有「批間」）。
PA_BATCH_GAMES = 50
PA_BATCH_PAUSE_RATIO = 1.0
PA_BATCH_PAUSE_MIN_S = 2.0

_KIND_RE = re.compile(r"^[A-Z]$")
_INT_RE = re.compile(r"^\d{1,4}$")


def _key(row: list[str]) -> GameKey:
    """簽章列 → 鍵。值會被內插進 SQL（:func:`keys_sql`），故逐欄以正規式驗過；不符 ⇒ 67。"""
    if (len(row) != 4 or not _INT_RE.fullmatch(row[0]) or not _KIND_RE.fullmatch(row[1])
            or not _INT_RE.fullmatch(row[2])):
        raise SyncError(EXIT_SELF_CHECK, f"簽章列的場次鍵不符預期形狀（不送）：{row[:3]!r}")
    return GameKey(int(row[0]), row[1], int(row[2]))


def _game_key(row: list[str]) -> GameKey:
    """全量鍵列（三欄）→ 鍵；同 :func:`_key` 逐欄驗過。"""
    if len(row) != 3:
        raise SyncError(EXIT_SELF_CHECK, f"全量鍵列的欄數不符預期（不送）：{row!r}")
    return _key([*row, ""])


def signatures(db: Psql) -> dict[GameKey, str]:
    return {_key(row): row[3] for row in db.read(SIGNATURE_SQL)}


def diff_games(local: Mapping[GameKey, str], target: Mapping[GameKey, str]) -> list[GameKey]:
    return sorted(k for k in local.keys() | target.keys() if local.get(k) != target.get(k))


def select_keys(local: Psql, target: Psql, *, full: bool) -> list[GameKey]:
    """本次要替換的場（排序）。增量超過 :data:`MAX_INCREMENTAL_GAMES` ⇒ 67（⛔ 不自動改跑全量）。"""
    if full:
        return sorted({_game_key(r) for r in local.read(FULL_KEYS_SQL)}
                      | {_game_key(r) for r in target.read(FULL_KEYS_SQL)})
    keys = diff_games(signatures(local), signatures(target))
    if len(keys) > MAX_INCREMENTAL_GAMES:
        raise SyncError(EXIT_SELF_CHECK,
                        f"差異場 {len(keys)} 場超過每日上限 {MAX_INCREMENTAL_GAMES}（疑似簽章失準；未送）。"
                        "⛔ 不自動改跑全量；交需求方判斷是否授權 PA_FULL_RESYNC=1")
    return keys


def batches(keys: Sequence[GameKey], size: int) -> list[list[GameKey]]:
    if size < 1:
        raise SyncError(EXIT_USAGE, f"PA_BATCH_GAMES 必須 ≥1：{size}")
    return [list(keys[i:i + size]) for i in range(0, len(keys), size)]


def write_batch_payload(local: Psql, keys: Sequence[GameKey], out: TextIO) -> None:
    """一批的 payload＝34aa6dd4 增量模式的同一個呼叫（同 scope、同閉包守衛、同 300s）。"""
    write_pa_payload(local, out, scope=keys_sql(keys), closure_sql=closure_violations_sql(keys))


def assert_payload_file(path: Path, keys: Sequence[GameKey]) -> None:
    with path.open(encoding="utf-8") as fh:
        assert_pa_lines((line.rstrip("\n") for line in fh), keys_sql(keys))


class Sender(Protocol):
    def send_file(self, path: Path) -> None: ...


def _span(keys: Sequence[GameKey]) -> str:
    return f"{keys[0].text}..{keys[-1].text}" if keys else "-"


def apply(local: Psql, target: Psql, sender: Sender, workdir: Path, *, full: bool,
          batch_games: int = PA_BATCH_GAMES, pause_ratio: float = PA_BATCH_PAUSE_RATIO,
          pause_min: float = PA_BATCH_PAUSE_MIN_S, sleep: Callable[[float], None] = time.sleep,
          clock: Callable[[], float] = time.time, log: Callable[[str], None] = print) -> dict:
    """逐批「產生 → 斷言 → 單交易送出 → 暫停」。任一批失敗 ⇒ :class:`SyncError`（訊息含已提交範圍）。"""
    if pause_ratio < 0 or pause_min < 0:
        raise SyncError(EXIT_USAGE, f"暫停設定不得為負：ratio={pause_ratio} min={pause_min}")
    batches([], batch_games)  # 先驗批次大小，再碰任何 DB
    keys = select_keys(local, target, full=full)
    if full:
        log(f"PA_FULL_RESYNC_GAMES={len(keys)}")
    elif not keys:
        log("PA_INCREMENTAL_GAMES=0")
        log("    · PA：本機與 production 每場簽章相同，沒有要替換的場（未送）")
        return {"games": 0, "batches": 0, "committed": 0}
    else:
        log(f"PA_INCREMENTAL_GAMES={len(keys)} {','.join(k.text for k in keys)}")
    groups = batches(keys, batch_games)
    n = len(groups)
    for i, batch in enumerate(groups, 1):
        path = workdir / f"pa-batch-{i:04d}-of-{n:04d}.sql"
        sent = False
        try:
            with path.open("w", encoding="utf-8") as fh:
                write_batch_payload(local, batch, fh)
            assert_payload_file(path, batch)
            started = clock()
            sent = True
            sender.send_file(path)
            finished = clock()
        except SyncError as exc:
            if not sent:
                path.write_text("", encoding="utf-8")  # 守衛不過：不留下半份可被誤送的檔
            done = [k for b in groups[:i - 1] for k in b]
            raise SyncError(exc.code, (
                f"PA_BATCH_FAILED {i}/{n} rc={exc.code} committed={i - 1}/{n} "
                f"committed_range={_span(done)} failed_keys={','.join(k.text for k in batch)} "
                f"payload={path}：{exc}")) from exc
        size = path.stat().st_size
        path.unlink()
        send_s = finished - started
        pause = max(pause_min, send_s * pause_ratio) if i < n else 0.0
        log(f"PA_BATCH {i}/{n} games={len(batch)} bytes={size} first={batch[0].text} last={batch[-1].text} "
            f"started={started:.3f} finished={finished:.3f} send_s={send_s:.3f} pause_s={pause:.3f}")
        if pause:
            sleep(pause)
    log(f"PA_BATCHES_COMMITTED={n}/{n}")
    return {"games": len(keys), "batches": n, "committed": n}


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
    for name in ("apply", "reconcile"):
        s = sub.add_parser(name)
        s.add_argument("--local-psql", required=True)
        s.add_argument("--target-psql", required=True, help="唯讀查詢用（簽章、全量鍵、對帳）")
        if name == "apply":
            s.add_argument("--apply-psql", required=True,
                           help="送出每批 payload 用（-v ON_ERROR_STOP=1 --single-transaction）")
            s.add_argument("--workdir", required=True, help="每批 payload 的落地目錄（失敗批保留於此）")
            s.add_argument("--full", action="store_true", help="全量模式（只能人工指定）")
            s.add_argument("--batch-games", type=int,
                           default=os.environ.get("PA_BATCH_GAMES", str(PA_BATCH_GAMES)))
            s.add_argument("--pause-ratio", type=float,
                           default=os.environ.get("PA_BATCH_PAUSE_RATIO", str(PA_BATCH_PAUSE_RATIO)))
            s.add_argument("--pause-min", type=float,
                           default=os.environ.get("PA_BATCH_PAUSE_MIN_S", str(PA_BATCH_PAUSE_MIN_S)))
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    local = Psql(args.local_psql, label="local")
    target = Psql(args.target_psql, label="target")
    try:
        if args.command == "apply":
            apply(local, target, Psql(args.apply_psql, label="target"), Path(args.workdir), full=args.full,
                  batch_games=args.batch_games, pause_ratio=args.pause_ratio, pause_min=args.pause_min,
                  log=lambda line: print(line, flush=True))
            return 0
        manifest = reconcile_family(local, target)
        print("PA_RECONCILE=" + json.dumps(manifest, ensure_ascii=False, sort_keys=True))
        return 0 if manifest["ok"] else EXIT_MISMATCH
    except SyncError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
