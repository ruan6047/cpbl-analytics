"""CLI：用已存的 www 原文重放，只補 livelog 被吃掉的同號列（#357 WP2-e）。**預設 dry-run。**

    uv run cpbl-replay-livelog-extra --raw-dir DIR [--ledger L.jsonl ...]           # dry-run，只出報告
    uv run cpbl-replay-livelog-extra --raw-dir DIR --ledger L.jsonl --apply \\
        --restore-out restore.jsonl --report report.json                            # 寫入

輸入：原文目錄（`YEAR-KIND-SNO.json.gz`＝`getlive` 回應，附 `SHA256SUMS`；#357 研究 2／WP1 產物）
＋ #361 交付的 ledger（格式契約 `~/.wf-evidence/cpbl-analytics/361/exec-1/FORMAT.md`）。

逐場判前態（PLAN-v2 §2.3②「逐場三態可接受」），任一條不成立 ⇒ **該場不寫**、列進報告：

* 原文檔 sha256 必須在 SHA256SUMS 內且相符。
* DB 主表事件號集合＝原文事件號集合。
* 同號多筆只准出現在**最後事件號**（2026 全 608 場皆此形狀）；其他位置有同號組＝新型態，
  交 C1 回看，不寫。
* 最後事件號以外，每一列主表＝現行寫入端對原文的轉換（逐欄）。
* 最後事件號那一列：content／is_special_event 以外的欄位＝主列轉換；content／is_special_event
  為下列三態之一——
  - `old`：content＝結束標記（現行寫入端修正前的後到者勝）；
  - `new`：content＝原文第一筆非標記列（今日切片後重爬過）；
  - `361`：該 PK 在 #361 ledger，且 DB＝ledger `new_content`／`new_is_special_event`，且 ledger
    的新值＝原文主列（content 依 ledger 的 `crlf_to_lf` 正規化比對）、`raw_sha256`＝原文檔。
  is_special_event 允許 true 或主列轉換值（#361 方案甲已把它改成原文值）。
* 附加表現況：空，或已等於本次要寫的列（冪等重跑）。

寫入（`--apply`）：`old` 改最後一列為主列轉換值＋寫附加列；`new`／`361` 只寫附加列。
寫前先把該場被改的主表列與附加表現況寫進 `--restore-out`（JSONL、fsync），再在同一交易內
`SELECT ... FOR UPDATE` 重驗前態後寫入；重驗不過就 rollback 並列為不符。

⛔ 不重放 PA（PA 由 `cpbl-build-pa` 依 `pa_build.end_marker_restoration` 受控接受）；
⛔ 不寫正式站（正式站經每日鏈同步）。
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cpbl.db import conn
from cpbl.ingest._cli import cli_parser
from cpbl.ingest.cpbl_gamelog import (
    _LL_COLS,
    _LL_EXTRA_COLS,
    _is_end_marker,
    _livelog_extra_rows,
    _livelog_rows,
)

log = logging.getLogger("cpbl.livelog_replay")

_RAW_NAME = re.compile(r"^(\d{4})-([ACDE])-(\d+)\.json\.gz$")
_COLS = _LL_COLS.split(",")
_I_EVENT, _I_CONTENT, _I_SPECIAL = (_COLS.index(c) for c in ("main_event_no", "content",
                                                              "is_special_event"))
_LEDGER_KEYS = frozenset({
    "tool", "tool_sha256", "run_id", "db", "year", "kind_code", "game_sno", "main_event_no",
    "old_content", "old_sha256", "new_content", "new_sha256", "normalization",
    "old_is_special_event", "new_is_special_event", "raw_file", "raw_sha256", "applied",
})

GameKey = tuple[int, str, int]

# 判定結果（報告與測試共用的字面）
STATE_OLD, STATE_NEW, STATE_361 = "old", "new", "361"
ACTION_UPDATE_AND_EXTRA = "update_last_and_write_extra"
ACTION_EXTRA_ONLY = "write_extra_only"
ACTION_ALREADY = "already_done"
ACTION_NO_DUP = "no_duplicate"


@dataclass
class RawGame:
    key: GameKey
    path: Path
    sha256: str
    livelog: list[dict]


@dataclass
class Decision:
    key: GameKey
    action: str | None = None           # None＝不符、不寫
    state: str | None = None
    reasons: list[str] = field(default_factory=list)
    update_row: tuple | None = None     # 主表最後一列的新值（_LL_COLS 順序）
    extra_rows: list[tuple] = field(default_factory=list)


def crlf_to_lf(text: str | None) -> str | None:
    """#361 ledger 的 `normalization=crlf_to_lf`。"""
    return None if text is None else text.replace("\r\n", "\n")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_sha256sums(raw_dir: Path) -> dict[str, str]:
    sums: dict[str, str] = {}
    for line in (raw_dir / "SHA256SUMS").read_text().splitlines():
        if line.strip():
            digest, name = line.split(None, 1)
            sums[name.strip().lstrip("*")] = digest
    return sums


def load_raw_games(raw_dir: Path, *, only: set[GameKey] | None = None
                   ) -> tuple[dict[GameKey, RawGame], dict[str, str]]:
    """讀原文目錄。回傳 (可用場次, 不可用檔名→原因)。sha256 不符或不在 SHA256SUMS 的檔不收。"""
    sums = load_sha256sums(raw_dir)
    games: dict[GameKey, RawGame] = {}
    rejected: dict[str, str] = {}
    for path in sorted(raw_dir.glob("*.json.gz")):
        m = _RAW_NAME.match(path.name)
        if not m:
            rejected[path.name] = "unrecognised_name"
            continue
        key = (int(m.group(1)), m.group(2), int(m.group(3)))
        if only is not None and key not in only:
            continue
        digest = _sha256(path)
        if sums.get(path.name) != digest:
            rejected[path.name] = "sha256_missing_or_mismatch"
            continue
        payload = json.loads(gzip.decompress(path.read_bytes()))
        livelog = json.loads(payload.get("LiveLogJson") or "[]")
        if not isinstance(livelog, list):
            rejected[path.name] = "livelog_not_array"
            continue
        games[key] = RawGame(key, path, digest, livelog)
    return games, rejected


def load_ledgers(paths: list[Path]) -> dict[tuple[int, str, int, str], dict]:
    """讀 #361 ledger（最終檔，applied=true）。欄位不齊／PK 重複／未 applied ⇒ 整批拒絕。"""
    out: dict[tuple[int, str, int, str], dict] = {}
    for path in paths:
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            row = json.loads(line)
            missing = _LEDGER_KEYS - row.keys()
            if missing:
                raise ValueError(f"{path}:{n} ledger 欄位不齊：{sorted(missing)}")
            if row["applied"] is not True or row["normalization"] != "crlf_to_lf":
                raise ValueError(f"{path}:{n} ledger 非已套用的 crlf_to_lf 列")
            pk = (int(row["year"]), row["kind_code"], int(row["game_sno"]), row["main_event_no"])
            if pk in out:
                raise ValueError(f"{path}:{n} ledger PK 重複：{pk}")
            for side in ("old", "new"):
                digest = hashlib.sha256(row[f"{side}_content"].encode()).hexdigest()
                if digest != row[f"{side}_sha256"]:
                    raise ValueError(f"{path}:{n} ledger {side}_sha256 與內容不符")
            out[pk] = row
    return out


def _final_event_no(livelog: list[dict]) -> str | None:
    nos = [str(r["MainEventNo"]) for r in livelog if r.get("MainEventNo")]
    if not nos:
        return None
    return max(nos, key=lambda no: (0, int(no)) if no.isdigit() else (1, no))  # type: ignore[return-value]


def decide(raw: RawGame, db_rows: list[tuple], db_extra: list[tuple],
           ledger: dict[tuple[int, str, int, str], dict]) -> Decision:
    """純函式：一場的前態判定與要寫的列。`db_rows`／`db_extra` 依 `_LL_COLS`／`_LL_EXTRA_COLS` 順序。"""
    year, kind, sno = raw.key
    d = Decision(raw.key)
    want_main = {r[_I_EVENT]: r for r in _livelog_rows(year, kind, sno, raw.livelog)}
    want_extra = _livelog_extra_rows(year, kind, sno, raw.livelog)
    have = {r[_I_EVENT]: tuple(r) for r in db_rows}
    if set(have) != set(want_main):
        d.reasons.append(f"event_set_mismatch: db_only={sorted(set(have) - set(want_main))[:5]} "
                         f"raw_only={sorted(set(want_main) - set(have))[:5]}")
        return d
    final_no = _final_event_no(raw.livelog)
    dup_nos = sorted({r[3] for r in want_extra})
    if dup_nos and dup_nos != [final_no]:
        d.reasons.append(f"unexpected_dup_groups: {dup_nos}（只准最後事件號；交 C1 回看）")
        return d
    for no, want in want_main.items():
        if no != final_no and have[no] != want:
            d.reasons.append(f"row_mismatch: {no}")
    if d.reasons:
        return d
    if not dup_nos:
        if db_extra:
            d.reasons.append("extra_rows_present_but_raw_has_no_duplicates")
            return d
        d.action = ACTION_NO_DUP
        return d

    want_last, got = want_main[final_no], have[final_no]
    same_others = all(got[i] == want_last[i] for i in range(len(_COLS))
                      if i not in (_I_CONTENT, _I_SPECIAL))
    if not same_others:
        d.reasons.append(f"last_row_structured_mismatch: {final_no}")
        return d
    content, special = got[_I_CONTENT], got[_I_SPECIAL]
    special_ok = special is True or special == want_last[_I_SPECIAL]
    ledger_row = ledger.get((year, kind, sno, final_no))
    if ledger_row is not None:
        # #361 交叉核對：ledger 的新值必須＝原文主列；不等＝停該場（不論 DB 現況）。
        if (ledger_row["new_content"] != crlf_to_lf(want_last[_I_CONTENT])
                or ledger_row["new_is_special_event"] != want_last[_I_SPECIAL]
                or ledger_row["raw_sha256"] != raw.sha256):
            d.reasons.append("ledger_disagrees_with_raw")
            return d
    if content == want_last[_I_CONTENT] and special_ok:
        d.state = STATE_NEW
    elif (ledger_row is not None and content == ledger_row["new_content"]
          and special == ledger_row["new_is_special_event"]):
        d.state = STATE_361
    elif _is_end_marker(content) and special_ok:
        d.state = STATE_OLD
    else:
        d.reasons.append(f"last_row_content_unexpected: {final_no}")
        return d

    have_extra = sorted(tuple(r) for r in db_extra)
    if have_extra and have_extra != sorted(want_extra):
        d.reasons.append("extra_rows_present_and_differ")
        return d
    d.extra_rows = want_extra
    if d.state == STATE_OLD:
        d.action = ACTION_UPDATE_AND_EXTRA
        d.update_row = want_last
    elif have_extra:
        d.action = ACTION_ALREADY
    else:
        d.action = ACTION_EXTRA_ONLY
    return d


# ── DB 層 ──────────────────────────────────────────────────────────────────────────
def _fetch(cur: Any, key: GameKey, *, lock: bool = False) -> tuple[list[tuple], list[tuple]]:
    suffix = " FOR UPDATE" if lock else ""
    cur.execute(f"SELECT {_LL_COLS} FROM cpbl.game_livelog "  # noqa: S608 — 固定欄位常數
                f"WHERE year=%s AND kind_code=%s AND game_sno=%s{suffix}", key)
    main = [tuple(r) for r in cur.fetchall()]
    cur.execute(f"SELECT {_LL_EXTRA_COLS} FROM cpbl.game_livelog_extra "  # noqa: S608
                f"WHERE year=%s AND kind_code=%s AND game_sno=%s{suffix}", key)
    return main, [tuple(r) for r in cur.fetchall()]


def _write_restore(fh: Any, d: Decision, main: list[tuple], extra: list[tuple]) -> None:
    old_last = next((r for r in main if d.update_row and r[_I_EVENT] == d.update_row[_I_EVENT]), None)
    fh.write(json.dumps({
        "year": d.key[0], "kind_code": d.key[1], "game_sno": d.key[2], "action": d.action,
        "state": d.state, "columns": _COLS, "old_main_row": old_last,
        "extra_columns": _LL_EXTRA_COLS.split(","), "old_extra_rows": extra,
    }, ensure_ascii=False, default=str) + "\n")
    fh.flush()
    os.fsync(fh.fileno())


def apply_decision(d: Decision, ledger: dict, raw: RawGame, restore_fh: Any) -> bool:
    """同一交易：鎖住該場 → 重驗前態 → 寫復原檔 → 改主列＋重寫附加列。重驗不過回 False（未寫）。"""
    with conn() as c:
        cur = c.cursor()
        main, extra = _fetch(cur, d.key, lock=True)
        again = decide(raw, main, extra, ledger)
        if again.action != d.action or again.update_row != d.update_row:
            return False
        _write_restore(restore_fh, d, main, extra)
        if d.update_row is not None:
            cur.execute(
                "UPDATE cpbl.game_livelog SET content=%s, is_special_event=%s "
                "WHERE year=%s AND kind_code=%s AND game_sno=%s AND main_event_no=%s",
                (d.update_row[_I_CONTENT], d.update_row[_I_SPECIAL], *d.key, d.update_row[_I_EVENT]),
            )
        cur.execute("DELETE FROM cpbl.game_livelog_extra WHERE year=%s AND kind_code=%s "
                    "AND game_sno=%s", d.key)
        if d.extra_rows:
            cur.executemany(
                f"INSERT INTO cpbl.game_livelog_extra ({_LL_EXTRA_COLS}) "
                f"VALUES ({','.join(['%s'] * len(_LL_EXTRA_COLS.split(',')))})",
                d.extra_rows,
            )
    return True


def run(raw_dir: Path, ledger_paths: list[Path], *, apply: bool, restore_out: Path | None,
        only: set[GameKey] | None = None) -> dict[str, Any]:
    games, rejected_files = load_raw_games(raw_dir, only=only)
    ledger = load_ledgers(ledger_paths)
    report: dict[str, Any] = {
        "raw_dir": str(raw_dir), "apply": apply, "raw_games": len(games),
        "rejected_files": rejected_files, "ledger_rows": len(ledger),
        "actions": {}, "states": {}, "refused": [], "applied": 0, "recheck_failed": [],
    }
    restore_fh = open(restore_out, "a", encoding="utf-8") if (apply and restore_out) else None  # noqa: SIM115
    try:
        for key in sorted(games):
            with conn() as c:
                main, extra = _fetch(c.cursor(), key)
            d = decide(games[key], main, extra, ledger)
            if d.action is None:
                report["refused"].append({"game": "-".join(map(str, key)), "reasons": d.reasons})
                continue
            report["actions"][d.action] = report["actions"].get(d.action, 0) + 1
            if d.state:
                report["states"][d.state] = report["states"].get(d.state, 0) + 1
            if apply and d.action in (ACTION_UPDATE_AND_EXTRA, ACTION_EXTRA_ONLY):
                if apply_decision(d, ledger, games[key], restore_fh):
                    report["applied"] += 1
                else:
                    report["recheck_failed"].append("-".join(map(str, key)))
    finally:
        if restore_fh:
            restore_fh.close()
    return report


def main(argv: list[str] | None = None) -> None:
    p = cli_parser("cpbl-replay-livelog-extra", __doc__)
    p.add_argument("--raw-dir", type=Path, required=True)
    p.add_argument("--ledger", type=Path, action="append", default=[],
                   help="#361 ledger（最終檔），可重複")
    p.add_argument("--game", action="append", default=[], metavar="YEAR:KIND:SNO",
                   help="只處理這幾場（可重複）")
    p.add_argument("--apply", action="store_true", help="真的寫入（預設 dry-run）")
    p.add_argument("--restore-out", type=Path, help="--apply 時必填：復原檔（JSONL，附加寫）")
    p.add_argument("--report", type=Path, help="報告 JSON 輸出位置")
    args = p.parse_args(argv)
    if args.apply and not args.restore_out:
        p.error("--apply 必須同時給 --restore-out")
    only = None
    if args.game:
        only = set()
        for g in args.game:
            y, k, s = g.split(":")
            only.add((int(y), k, int(s)))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    report = run(args.raw_dir, args.ledger, apply=args.apply, restore_out=args.restore_out, only=only)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.write_text(text + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("raw_games", "actions", "states", "applied")}
                     | {"refused": len(report["refused"]), "recheck_failed": len(report["recheck_failed"]),
                        "rejected_files": len(report["rejected_files"])}, ensure_ascii=False))
    sys.exit(1 if (report["recheck_failed"] or (args.apply and report["refused"])) else 0)


if __name__ == "__main__":
    main()
