"""INGEST-GAME-TM-REFACTOR1-G4 Phase A：全季唯讀 dry-run 對帳（單場 API vs 正式表存量）。

**唯讀紅線**：本腳本對 `cpbl.pitch_tracking` 只下 SELECT，全檔無 INSERT／UPDATE／DELETE。
Phase A 不寫入存量；寫入是 Phase B、且由需求方親手執行。

母體：指定年份 kind A 與 D 的**全部完成場**（`completed_game_snos`，含
`game_date <= CURRENT_DATE` 界線以排除掛未來日期的保留賽）。逐場打單場 API、經共用
pure parser `parse_pitches` 解析，與正式表該場既有列逐格比對。

比對邏輯沿用 Gate 3 `game_tm_shadow.diff_rows` 的同一套（直接 import `_cell_equal`／
`_REAL_F4_COLS`，不複寫）——含 float4 round-trip：migration 018 那批欄位以 `real` 存入，
用 `==` 比 float64 原值必然逐格不等，那是儲存精度假陽性而非真差異（Gate 3 踩過）。
**本腳本不修改 shadow harness，只唯讀 import 其純函式常數。**

去重語意與 `_upsert` 對齊：同一 PK 在單場 payload 內重複出現時**保留第一筆**
（`_upsert` 的 `seen` 集合即此語意）。若用後者覆蓋前者，dry-run 的「將寫入什麼」就與
實際寫入不同。逐場記錄被丟棄的重複筆數（`dup_pk_dropped`）。

欄位分三桶（依卡面紅線字面，不自行歸併）：
- `physical`（紅線 1，零容忍）：`rel_speed`／`spin_rate`／`plate_loc_*`／`traj_*`／`hit_*`
  與其餘釋放點/進壘點物理量。
- `text`（紅線 2，允許非 0 但須逐筆歸因）：`content` 等敘述欄位與雙方姓名。
- `other`：兩份清單都沒點名的欄位（球種標籤、局數/球數狀態）。**刻意不併入任一紅線**，
  單獨列出交查核者／需求方判讀，避免執行者替紅線範圍作擴張或縮減解釋。

**凍結例外**（需求方 2026-08-05 裁定）：`FROZEN_GAMES` 內的場次其 physical mismatch
不計入紅線 1 母體。三個數字全留（合計／凍結／母體內），「排除」必須看得見而非消失。

產出（`--outdir`，預設 docs/research/INGEST-GAME-TM-REFACTOR1-G4/）：
- `dryrun_summary.json`     全域與逐 kind 統計、逐場明細
- `dryrun_text_diffs.json`  紅線 2 逐筆歸因（含 endpoint_url／fetched_at／payload_sha256）
- `dryrun_only_prod_pk.json` 紅線 3 母體逐筆清單
- `dryrun_fetch_log.jsonl`  每場一列：endpoint_url／fetched_at／payload_sha256／bytes
- `payloads/<gid>.json.gz`  有任何差異之場次的官方回應全文（gzip；raw sha256 見 fetch log）

    uv run python scripts/dryrun_game_tm_fullseason.py --year 2026 --kinds A D --delay 0.4
"""

from __future__ import annotations

import argparse
import datetime as _dt
import gzip
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

import httpx

from cpbl.db import conn
from cpbl.ingest.cpbl_pitch_tracking import (
    _COLS,
    FROZEN_GAMES,
    GAMES_EP,
    _client,
    completed_game_snos,
    is_frozen,
    parse_pitches,
)
from cpbl.ingest.game_tm_shadow import _cell_equal

_COL_NAMES = [c.strip() for c in _COLS.split(",")]
_PK_COLS = ("year", "kind_code", "game_sno", "pitcher_acnt", "pitch_cnt")

# 紅線 1 零容忍欄位集：卡面字面列舉 rel_speed／spin_rate／plate_loc_*／traj_*／hit_*，
# 「等物理與軌跡欄位」故一併納入同層級的釋放點與進壘點物理量（rel_side/rel_height/
# extension/zone_speed/zone_time/ivb_cm/hb_cm）。hit_landing_confidence 雖為文字值，
# 但字面屬 hit_*，依卡面從嚴歸此桶（若真出現不一致會另行標註其文字性質，不自行放寬）。
_PHYSICAL_COLS = frozenset({
    "rel_speed", "spin_rate", "rel_side", "rel_height", "extension",
    "zone_speed", "plate_loc_side", "plate_loc_height", "zone_time",
    "hit_exit_speed", "hit_launch_angle", "hit_direction", "hit_distance", "hit_hang_time",
    "hit_landing_bearing", "hit_landing_confidence", "hit_spin_rate",
    "traj_accel_y", "traj_accel_z", "ivb_cm", "hb_cm",
    "traj_x0", "traj_x1", "traj_x2", "traj_y0", "traj_y1", "traj_y2",
    "traj_z0", "traj_z1", "traj_z2",
})
# 紅線 2：`content` 等敘述欄位（官方賽後可修文字）。
_TEXT_COLS = frozenset({"content", "pitcher_name", "hitter_name"})


def bucket_of(col: str) -> str:
    if col in _PHYSICAL_COLS:
        return "physical"
    if col in _TEXT_COLS:
        return "text"
    return "other"


def _pk_of_row(d: dict) -> tuple:
    return tuple(d[c] for c in _PK_COLS)


def rows_by_pk_first_wins(records: list[tuple]) -> tuple[dict[tuple, dict], int]:
    """把 parser 產出的 tuple 轉 {PK: dict}，**同 PK 保留第一筆**（與 `_upsert` 去重語意一致）。

    回傳 (by_pk, dup_dropped)。pure，供離線測試。
    """
    by_pk: dict[tuple, dict] = {}
    dup = 0
    for rec in records:
        d = dict(zip(_COL_NAMES, rec, strict=True))
        pk = _pk_of_row(d)
        if pk in by_pk:
            dup += 1
            continue
        by_pk[pk] = d
    return by_pk, dup


def diff_game(api_by_pk: dict[tuple, dict], prod_by_pk: dict[tuple, dict]) -> dict:
    """單場對帳（pure）：PK 集合差異 + 共同 PK 逐格比對（float4 round-trip 後）。

    `only_prod_pk` ＝ 正式表有、單場 API 沒有的列（紅線 3 母體）。
    `only_api_pk` ＝ 單場 API 有、正式表沒有的列（存量缺漏，Phase B 寫入即補上）。
    """
    only_api = sorted(set(api_by_pk) - set(prod_by_pk))
    only_prod = sorted(set(prod_by_pk) - set(api_by_pk))
    cells: list[dict] = []
    for pk in sorted(set(api_by_pk) & set(prod_by_pk)):
        a, p = api_by_pk[pk], prod_by_pk[pk]
        for col in _COL_NAMES:
            if not _cell_equal(col, a.get(col), p.get(col)):
                cells.append({"pk": list(pk), "column": col, "bucket": bucket_of(col),
                              "api_value": a.get(col), "prod_value": p.get(col)})
    return {"only_api_pk": [list(pk) for pk in only_api],
            "only_prod_pk": [list(pk) for pk in only_prod],
            "cell_mismatches": cells}


def _prod_rows(year: int, kind_code: str, snos: list[int]) -> dict[int, dict[tuple, dict]]:
    """正式表該 kind 全場次列（唯讀 SELECT）。回傳 {game_sno: {PK: row_dict}}。"""
    out: dict[int, dict[tuple, dict]] = {s: {} for s in snos}
    if not snos:
        return out
    with conn() as c:
        rows = c.execute(
            f"SELECT {_COLS} FROM cpbl.pitch_tracking "
            "WHERE year=%s AND kind_code=%s AND game_sno = ANY(%s)",
            (year, kind_code, snos),
        ).fetchall()
    for r in rows:
        d = dict(zip(_COL_NAMES, tuple(r), strict=True))
        out.setdefault(d["game_sno"], {})[_pk_of_row(d)] = d
    return out


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _json_default(o):
    if isinstance(o, _dt.date | _dt.datetime):
        return o.isoformat()
    raise TypeError(f"not JSON serialisable: {type(o)}")


def _write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=_json_default) + "\n")


def build_manifest(outdir: Path, fetched_at_by_path: dict[str, str]) -> dict:
    """逐檔 path／sha256／bytes／fetched_at（紅線 2 的信任錨點鏈中間環）。

    **宣稱範圍**：manifest 自身的 sha256 寫入 handoff event 後，可證明「handoff 之後」
    artifact 未被修改。它**不是**來源真實性錨點——執行者若在寫 handoff 前同時改
    payload、manifest 與 event evidence，整條鏈仍會自洽（卡面紅線 2 已明載）。
    """
    entries = []
    for p in sorted(outdir.rglob("*")):
        if not p.is_file() or p.name == "manifest.json":
            continue
        rel = str(p.relative_to(outdir))
        data = p.read_bytes()
        entries.append({"path": rel, "sha256": _sha256(data), "bytes": len(data),
                        "fetched_at": fetched_at_by_path.get(rel)})
    return {"card": "INGEST-GAME-TM-REFACTOR1-G4", "phase": "A",
            "generated_at": _dt.datetime.now().astimezone().isoformat(),
            "files": entries}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--kinds", nargs="+", default=["A", "D"])
    ap.add_argument("--delay", type=float, default=0.4)
    ap.add_argument("--outdir", default="docs/research/INGEST-GAME-TM-REFACTOR1-G4")
    ap.add_argument("--limit", type=int, default=None, help="每 kind 只跑前 N 場（煙霧測試用）")
    ap.add_argument("--rebuild-manifest", action="store_true",
                    help="不抓網、只依現有檔案重建 manifest.json（後續 artifact 補齊後收尾用）")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    if args.rebuild_manifest:
        # payload 的 fetched_at 由 fetch log 還原，不因重建而遺失取得時間。
        fa: dict[str, str] = {}
        fl = outdir / "dryrun_fetch_log.jsonl"
        if fl.exists():
            for line in fl.read_text().splitlines():
                if line.strip():
                    rec = json.loads(line)
                    fa[f"payloads/{rec['game']}.json.gz"] = rec["fetched_at"]
        _write_json(outdir / "manifest.json", build_manifest(outdir, fa))
        print(f"manifest.json sha256 = {_sha256((outdir / 'manifest.json').read_bytes())}")
        return

    (outdir / "payloads").mkdir(parents=True, exist_ok=True)
    fetch_log_path = outdir / "dryrun_fetch_log.jsonl"
    fetch_log = fetch_log_path.open("w")
    fetched_at_by_path: dict[str, str] = {}

    client = _client()
    per_game: list[dict] = []
    text_diffs: list[dict] = []
    only_prod_all: list[dict] = []
    bucket_counter: Counter[str] = Counter()
    col_counter: Counter[str] = Counter()
    by_kind: dict[str, dict] = {}
    fetch_errors: list[dict] = []
    requests_made = 0
    frozen_physical = 0   # 凍結例外場貢獻的物理欄位不一致（不計入紅線 1 母體）

    try:
        for kind in args.kinds:
            snos = completed_game_snos(args.year, kind)
            if args.limit:
                snos = snos[: args.limit]
            prod = _prod_rows(args.year, kind, snos)
            k_stat = {"completed_games": len(snos), "api_rows": 0, "prod_rows": 0,
                      "common_pk": 0, "only_api_pk": 0, "only_prod_pk": 0,
                      "dup_pk_dropped": 0, "cells": Counter()}
            for sno in snos:
                gid = f"{args.year}-{kind}-{sno}"
                time.sleep(args.delay)
                url = f"{GAMES_EP}/{gid}"
                fetched_at = _dt.datetime.now().astimezone().isoformat()
                try:
                    r = client.get(url)
                    r.raise_for_status()
                    raw = r.content
                    payload = r.json()
                except (httpx.HTTPError, ValueError) as e:
                    fetch_errors.append({"game": gid, "error": str(e), "fetched_at": fetched_at})
                    print(f"  ✗ {gid} 抓取失敗：{e}")
                    continue
                requests_made += 1
                raw_sha = _sha256(raw)
                fetch_log.write(json.dumps({"game": gid, "endpoint_url": url,
                                            "fetched_at": fetched_at, "payload_sha256": raw_sha,
                                            "bytes": len(raw)}, ensure_ascii=False) + "\n")
                livelog = ((payload.get("Data") or {}).get("Game") or {}).get("LiveLog") or []
                api_by_pk, dup = rows_by_pk_first_wins(parse_pitches(livelog, kind))
                prod_by_pk = prod.get(sno, {})
                d = diff_game(api_by_pk, prod_by_pk)

                k_stat["api_rows"] += len(api_by_pk)
                k_stat["prod_rows"] += len(prod_by_pk)
                k_stat["common_pk"] += len(set(api_by_pk) & set(prod_by_pk))
                k_stat["only_api_pk"] += len(d["only_api_pk"])
                k_stat["only_prod_pk"] += len(d["only_prod_pk"])
                k_stat["dup_pk_dropped"] += dup
                for cell in d["cell_mismatches"]:
                    if cell["bucket"] == "physical" and is_frozen(args.year, kind, sno):
                        frozen_physical += 1
                    k_stat["cells"][cell["bucket"]] += 1
                    bucket_counter[cell["bucket"]] += 1
                    col_counter[cell["column"]] += 1
                    if cell["bucket"] == "text":
                        text_diffs.append({
                            "year": cell["pk"][0], "kind_code": cell["pk"][1],
                            "game_sno": cell["pk"][2], "pitcher_acnt": cell["pk"][3],
                            "pitch_cnt": cell["pk"][4], "column": cell["column"],
                            "prod_value": cell["prod_value"], "api_value": cell["api_value"],
                            "endpoint_url": url, "fetched_at": fetched_at,
                            "payload_sha256": raw_sha,
                        })
                for pk in d["only_prod_pk"]:
                    only_prod_all.append({"year": pk[0], "kind_code": pk[1], "game_sno": pk[2],
                                          "pitcher_acnt": pk[3], "pitch_cnt": pk[4],
                                          "endpoint_url": url, "fetched_at": fetched_at,
                                          "payload_sha256": raw_sha})

                has_diff = bool(d["only_api_pk"] or d["only_prod_pk"] or d["cell_mismatches"])
                if has_diff:  # 只為有差異的場保存官方回應全文（gzip；raw sha256 見 fetch log）
                    rel = f"payloads/{gid}.json.gz"
                    with gzip.open(outdir / rel, "wb") as f:
                        f.write(raw)
                    fetched_at_by_path[rel] = fetched_at
                per_game.append({
                    "game": gid, "api_rows": len(api_by_pk), "prod_rows": len(prod_by_pk),
                    "only_api_pk": len(d["only_api_pk"]), "only_prod_pk": len(d["only_prod_pk"]),
                    "dup_pk_dropped": dup,
                    "cells": {k: v for k, v in Counter(
                        c["bucket"] for c in d["cell_mismatches"]).items()},
                    "payload_saved": has_diff,
                })
                mark = "·" if not has_diff else "!"
                print(f"  {mark} {gid} api={len(api_by_pk)} prod={len(prod_by_pk)} "
                      f"only_api={len(d['only_api_pk'])} only_prod={len(d['only_prod_pk'])} "
                      f"cells={len(d['cell_mismatches'])}")
            k_stat["cells"] = dict(k_stat["cells"])
            by_kind[kind] = k_stat
            print(f"== kind {kind} 完成：{k_stat}")
    finally:
        client.close()
        fetch_log.close()

    summary = {
        "card": "INGEST-GAME-TM-REFACTOR1-G4", "phase": "A", "mode": "dry-run (read-only)",
        "generated_at": _dt.datetime.now().astimezone().isoformat(),
        "params": {"year": args.year, "kinds": args.kinds, "delay": args.delay,
                   "limit": args.limit},
        "requests_made": requests_made,
        "fetch_errors": fetch_errors,
        "by_kind": by_kind,
        "totals": {
            "completed_games": sum(v["completed_games"] for v in by_kind.values()),
            "api_rows": sum(v["api_rows"] for v in by_kind.values()),
            "prod_rows": sum(v["prod_rows"] for v in by_kind.values()),
            "only_api_pk": sum(v["only_api_pk"] for v in by_kind.values()),
            "only_prod_pk": sum(v["only_prod_pk"] for v in by_kind.values()),
            "dup_pk_dropped": sum(v["dup_pk_dropped"] for v in by_kind.values()),
            "cell_mismatch_by_bucket": dict(bucket_counter),
            "cell_mismatch_by_column": dict(col_counter),
        },
        "redlines": {
            # 紅線 1 母體排除凍結例外場（需求方 2026-08-05 裁定；清單見
            # cpbl_pitch_tracking.FROZEN_GAMES）。兩個數字都留，避免「排除後就看不見」。
            "frozen_games": sorted(f"{y}-{k}-{s}" for y, k, s in FROZEN_GAMES),
            "redline1_physical_cell_mismatches_all": bucket_counter.get("physical", 0),
            "redline1_physical_cell_mismatches_frozen": frozen_physical,
            "redline1_physical_cell_mismatches": bucket_counter.get("physical", 0) - frozen_physical,
            "redline1_pass": (bucket_counter.get("physical", 0) - frozen_physical) == 0,
            "redline2_text_cell_mismatches": bucket_counter.get("text", 0),
            "redline3_only_prod_pk": sum(v["only_prod_pk"] for v in by_kind.values()),
            "redline3_pass": sum(v["only_prod_pk"] for v in by_kind.values()) == 0,
            "other_bucket_cell_mismatches": bucket_counter.get("other", 0),
        },
        "per_game": per_game,
    }
    _write_json(outdir / "dryrun_summary.json", summary)
    _write_json(outdir / "dryrun_text_diffs.json", text_diffs)
    _write_json(outdir / "dryrun_only_prod_pk.json", only_prod_all)

    manifest = build_manifest(outdir, fetched_at_by_path)
    _write_json(outdir / "manifest.json", manifest)
    manifest_sha = _sha256((outdir / "manifest.json").read_bytes())

    print("\n================ dry-run 對帳（唯讀） ================")
    print(f"請求數={requests_made}  抓取失敗={len(fetch_errors)}")
    for k, v in by_kind.items():
        print(f"kind {k}: 完成場={v['completed_games']} api列={v['api_rows']} 表列={v['prod_rows']} "
              f"only_api={v['only_api_pk']} only_prod={v['only_prod_pk']} "
              f"dup丟棄={v['dup_pk_dropped']} 逐格={v['cells']}")
    in_scope = bucket_counter.get("physical", 0) - frozen_physical
    print(f"紅線1 物理欄位不一致：合計={bucket_counter.get('physical', 0)} "
          f"凍結場除外={frozen_physical} 母體內={in_scope}"
          f"（{'PASS' if in_scope == 0 else 'FAIL'}）")
    print(f"紅線2 文字欄位不一致={bucket_counter.get('text', 0)} 筆 → dryrun_text_diffs.json")
    print(f"紅線3 only_prod_pk={summary['redlines']['redline3_only_prod_pk']}"
          f"（{'PASS' if summary['redlines']['redline3_pass'] else '阻擋 Phase B，須交需求方裁定'}）")
    print(f"其他桶（非紅線點名欄位）={bucket_counter.get('other', 0)} 筆 → 交查核者判讀")
    print(f"\nmanifest.json sha256 = {manifest_sha}")


if __name__ == "__main__":
    main()
