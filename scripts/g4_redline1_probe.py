"""INGEST-GAME-TM-REFACTOR1-G4 Phase A：紅線 1／3 的歸因探針（唯讀，產 artifact）。

dry-run 若出現物理欄位不一致（紅線 1）或 `only_prod_pk`（紅線 3），本腳本回答
**歸因**問題——不由執行者主觀判定，一律以可重跑的量測回答：

紅線 1（物理欄位）三選一：
- `prod_stale`：正式表是舊資料，logs 端點**現值**已與單場 API 一致 → 重跑即收斂。
- `endpoints_disagree`：兩支官方端點**當下**對同一球給出不同 TrackMan → 切換會用
  單場 API 的值覆蓋既有 logs 值，屬資料正確性事件，**須交需求方裁定**。
- `precision_only`：float4 round-trip 後即相等（不應出現，`_cell_equal` 已處理）。

紅線 3（`only_prod_pk`）三選一，依單場 API payload 內該事件的存在形態判定：
- `present_but_trackman_null`：單場 API **有該事件但 Trackman=null**（兩端點的 TrackMan
  掛載範圍不同）→ 新路徑不會寫入這些球＝覆蓋淨損，非官方刪球。
- `absent_from_livelog`：單場 API 根本沒有該事件（官方刪球／事件重編）。
- `present_with_trackman`：不該出現（若有，代表對帳邏輯有誤）。

    uv run python scripts/g4_redline1_probe.py --outdir docs/research/INGEST-GAME-TM-REFACTOR1-G4
"""

from __future__ import annotations

import argparse
import datetime as _dt
import gzip
import json
import statistics
from collections import Counter
from pathlib import Path

from cpbl.db import conn
from cpbl.ingest.cpbl_pitch_tracking import _COLS, _client, _fetch_logs, parse_pitches
from cpbl.ingest.game_tm_shadow import _cell_equal

_COL = [c.strip() for c in _COLS.split(",")]
_PK = ("pitcher_acnt", "pitch_cnt")


def _by_pk(records: list[tuple]) -> dict[tuple, dict]:
    out: dict[tuple, dict] = {}
    for r in records:
        d = dict(zip(_COL, r, strict=True))
        out.setdefault((d["pitcher_acnt"], d["pitch_cnt"]), d)
    return out


def _prod(year: int, kind: str, sno: int) -> dict[tuple, dict]:
    with conn() as c:
        rows = c.execute(
            f"SELECT {_COLS} FROM cpbl.pitch_tracking "
            "WHERE year=%s AND kind_code=%s AND game_sno=%s", (year, kind, sno)).fetchall()
    return _by_pk([tuple(r) for r in rows])


def _game_meta(year: int, kind: str, sno: int) -> dict:
    with conn() as c:
        r = c.execute("SELECT game_date, venue, home_team_code, away_team_code FROM cpbl.games "
                      "WHERE year=%s AND kind_code=%s AND game_sno=%s",
                      (year, kind, sno)).fetchall()
    return ({"game_date": str(r[0][0]), "venue": r[0][1],
             "home": r[0][2], "away": r[0][3]} if r else {})


def _diff_cols(a: dict, b: dict) -> list[str]:
    return [c for c in _COL if not _cell_equal(c, a.get(c), b.get(c))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="docs/research/INGEST-GAME-TM-REFACTOR1-G4")
    ap.add_argument("--delay", type=float, default=0.4)
    args = ap.parse_args()
    outdir = Path(args.outdir)
    summary = json.loads((outdir / "dryrun_summary.json").read_text())

    # 受影響場次：有 physical 逐格不一致者（紅線 1）
    affected = [g["game"] for g in summary["per_game"] if g["cells"].get("physical")]
    report: dict = {"card": "INGEST-GAME-TM-REFACTOR1-G4", "probe": "redline1_redline3_attribution",
                    "generated_at": _dt.datetime.now().astimezone().isoformat(),
                    "source_dryrun": str(outdir / "dryrun_summary.json"),
                    "redline1_games": [], "redline3_attribution": {}}

    client = _client()
    try:
        for gid in affected:
            year, kind, sno = gid.split("-")
            year, sno = int(year), int(sno)
            payload = json.loads(gzip.open(outdir / f"payloads/{gid}.json.gz").read())
            livelog = (payload.get("Data") or {}).get("Game", {}).get("LiveLog") or []
            api = _by_pk(parse_pitches(livelog, kind))
            prod = _prod(year, kind, sno)
            # logs 端點現值（該場出現過的投手）
            logs: dict[tuple, dict] = {}
            for acnt in sorted({pk[0] for pk in prod} | {pk[0] for pk in api}):
                entries = [p for p in _fetch_logs(client, acnt, year, kind)
                           if str(p.get("GameSno")) == str(sno)]
                logs.update(_by_pk(parse_pitches(entries, kind)))

            lp = sorted(set(logs) & set(prod))
            la = sorted(set(logs) & set(api))
            lp_diff = [pk for pk in lp if _diff_cols(logs[pk], prod[pk])]
            la_diff = [pk for pk in la if _diff_cols(logs[pk], api[pk])]
            if lp_diff and not la_diff:
                verdict = "prod_stale"
            elif la_diff and not lp_diff:
                verdict = "endpoints_disagree"
            elif not la_diff and not lp_diff:
                verdict = "precision_only"
            else:
                verdict = "mixed_needs_human"

            # 量化：rel_speed 差值分布（僅共同 PK、兩邊皆非 None）
            deltas = [abs(api[pk]["rel_speed"] - prod[pk]["rel_speed"])
                      for pk in sorted(set(api) & set(prod))
                      if api[pk].get("rel_speed") is not None and prod[pk].get("rel_speed") is not None]
            big = [d for d in deltas if d > 1.0]
            report["redline1_games"].append({
                "game": gid, **_game_meta(year, kind, sno),
                "rows": {"api": len(api), "prod": len(prod), "logs_now": len(logs),
                         "common_api_prod": len(set(api) & set(prod))},
                "logs_now_vs_prod_rows_differing": f"{len(lp_diff)}/{len(lp)}",
                "logs_now_vs_game_api_rows_differing": f"{len(la_diff)}/{len(la)}",
                "verdict": verdict,
                "rel_speed_abs_delta": {
                    "n": len(deltas), "gt_1_kmh": len(big),
                    "max": round(max(deltas), 4) if deltas else None,
                    "median": round(statistics.median(deltas), 6) if deltas else None},
                "api_pitch_call_null_rows": sum(1 for pk in api if api[pk].get("pitch_call") is None),
                "prod_pitch_call_null_rows": sum(1 for pk in prod if prod[pk].get("pitch_call") is None),
            })
            print(f"[redline1] {gid} verdict={verdict} "
                  f"logs~prod={len(lp_diff)}/{len(lp)} logs~api={len(la_diff)}/{len(la)} "
                  f"relΔ>1km/h={len(big)}/{len(deltas)}")
    finally:
        client.close()

    # 紅線 3 歸因：以已保存的單場 payload 判定每一筆 only_prod_pk 的存在形態
    op = json.loads((outdir / "dryrun_only_prod_pk.json").read_text())
    cat: Counter[str] = Counter()
    rows_out = []
    cache: dict[str, dict] = {}
    for r in op:
        gid = f"{r['year']}-{r['kind_code']}-{r['game_sno']}"
        if gid not in cache:
            payload = json.loads(gzip.open(outdir / f"payloads/{gid}.json.gz").read())
            ll = (payload.get("Data") or {}).get("Game", {}).get("LiveLog") or []
            idx: dict[tuple, list[dict]] = {}
            for e in ll:
                idx.setdefault((e.get("PitcherAcnt"), e.get("PitchCnt")), []).append(e)
            cache[gid] = idx
        ev = cache[gid].get((r["pitcher_acnt"], r["pitch_cnt"]))
        if not ev:
            c = "absent_from_livelog"
        elif all(e.get("Trackman") is None for e in ev):
            c = "present_but_trackman_null"
        else:
            c = "present_with_trackman"
        cat[c] += 1
        rows_out.append({**r, "attribution": c,
                         "content": (ev[0].get("Content") if ev else None),
                         "inning_seq": (ev[0].get("InningSeq") if ev else None)})
    report["redline3_attribution"] = {
        "total": len(op), "by_category": dict(cat),
        "affected_games": sorted({f"{r['year']}-{r['kind_code']}-{r['game_sno']}" for r in op}),
        "rows": rows_out,
    }
    print(f"[redline3] only_prod_pk={len(op)} 歸因分布={dict(cat)}")

    p = outdir / "redline_attribution.json"
    p.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str) + "\n")
    print(f"  → {p}")


if __name__ == "__main__":
    main()
