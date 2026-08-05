"""INGEST-GAME-TM-REFACTOR1-G4 Phase A：gate 判定與凍結例外後的紅線 1 複判（唯讀）。

回應第 1 輪跨家族查核（GPT-5.6@Codex）三 finding 的需求方 2026-08-05 裁定：

- **紅線 1（F1）**：凍結例外場次的 mismatch **不計入母體**。本腳本自
  `dryrun_summary.json`（Codex 已獨立重跑複驗、逐檔 sha256 不變）**重新推導**判定，
  **不重抓網路**——base artifact 保持位元不變，查核者對它的既有驗證繼續成立。
- **紅線 3（F3）**：gate 語意改「**未歸因** `only_prod_pk` ＝ 0」。原始 43 筆與逐筆分類
  **完整保留不得刪減**，本腳本原樣搬運 `redline_attribution.json` 的每一列並附分類統計，
  未歸因＝未落入任何已知結構性類別者。
- **pa_build 交接**：附「除外列 PK 穩定、reconciliation 不受影響」的機器產生證據。

    uv run python scripts/g4_gate_report.py --outdir docs/research/INGEST-GAME-TM-REFACTOR1-G4
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
from collections import Counter
from pathlib import Path

from cpbl.db import conn
from cpbl.ingest.cpbl_pitch_tracking import FROZEN_GAMES, is_frozen

# 已知的**結構性**歸因類別：官方端點之間的掛載範圍差異，非我方缺陷、亦非官方刪球。
# 落在這兩類之外者即「未歸因」，計入 gate 母體。
_STRUCTURAL = {
    "present_but_trackman_null": "單場 API 有該事件但 Trackman=null（兩端點 TrackMan 掛載範圍不同）",
    "absent_from_livelog": "單場 API LiveLog 無該事件（官方事件集合差異）",
}


def _game_tuple(gid: str) -> tuple[int, str, int]:
    y, k, s = gid.split("-")
    return int(y), k, int(s)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="docs/research/INGEST-GAME-TM-REFACTOR1-G4")
    args = ap.parse_args()
    outdir = Path(args.outdir)
    summary = json.loads((outdir / "dryrun_summary.json").read_text())
    attrib = json.loads((outdir / "redline_attribution.json").read_text())

    # ── 紅線 1：凍結例外後複判 ───────────────────────────────────────────────
    frozen_games, kept_games = [], []
    for g in summary["per_game"]:
        phys = g["cells"].get("physical", 0)
        (frozen_games if is_frozen(*_game_tuple(g["game"])) else kept_games).append(
            {"game": g["game"], "physical_cells": phys,
             "other_cells": g["cells"].get("other", 0), "text_cells": g["cells"].get("text", 0)})
    phys_in_scope = sum(g["physical_cells"] for g in kept_games)
    phys_frozen = sum(g["physical_cells"] for g in frozen_games)

    # ── 紅線 3：未歸因 = 0 判定（原始 43 筆完整保留）─────────────────────────
    rows = attrib["redline3_attribution"]["rows"]
    cat = Counter(r["attribution"] for r in rows)
    unattributed = [r for r in rows if r["attribution"] not in _STRUCTURAL]

    # 除外列現況：這些 PK 現在存在於正式表嗎？（純 UPSERT 永久保留的前提）
    present = 0
    with conn() as c:
        for r in rows:
            n = c.execute(
                "SELECT count(*) FROM cpbl.pitch_tracking WHERE year=%s AND kind_code=%s "
                "AND game_sno=%s AND pitcher_acnt=%s AND pitch_cnt=%s",
                (r["year"], r["kind_code"], r["game_sno"], r["pitcher_acnt"], r["pitch_cnt"]),
            ).fetchall()[0][0]
            present += 1 if n == 1 else 0

    # ── pa_build 交接證據 ───────────────────────────────────────────────────
    affected = sorted({f"{r['year']}-{r['kind_code']}-{r['game_sno']}" for r in rows})
    per_game = {g["game"]: g for g in summary["per_game"]}
    build_states = {}
    with conn() as c:
        for gid in affected:
            y, k, s = _game_tuple(gid)
            got = c.execute(
                "SELECT state, builder_version, taxonomy_version FROM cpbl.game_recap_builds "
                "WHERE year=%s AND kind_code=%s AND game_sno=%s ORDER BY built_at DESC LIMIT 1",
                (y, k, s)).fetchall()
            build_states[gid] = ({"state": got[0][0], "builder_version": got[0][1],
                                  "taxonomy_version": got[0][2]} if got else None)
    pa_rows = []
    for gid in affected:
        g = per_game[gid]
        frozen = is_frozen(*_game_tuple(gid))
        pa_rows.append({
            "game": gid, "frozen": frozen,
            "only_api_pk": g["only_api_pk"], "only_prod_pk": g["only_prod_pk"],
            "cell_mismatch_total": sum(g["cells"].values()),
            "build_state": build_states[gid],
            # 切換後這一場的 pitch_tracking 會發生什麼事
            "write_effect_after_cutover": (
                "凍結：任何路徑都不寫入 → 逐球列集合與值完全不變"
                if frozen else
                ("UPSERT 共同 PK 但逐格全等（cell_mismatch=0）且無新增列（only_api_pk=0）"
                 " → 值不變、PK 集合不變，等同 no-op"
                 if g["cells"] == {} and g["only_api_pk"] == 0 else
                 "⚠️ 有值變動或新增列，需人工判讀")),
        })
    no_op = all(r["write_effect_after_cutover"].startswith(("凍結", "UPSERT")) for r in pa_rows)

    report = {
        "card": "INGEST-GAME-TM-REFACTOR1-G4", "phase": "A",
        "purpose": "第 1 輪查核 F1/F3 的需求方裁定落地判定（自既有 dry-run artifact 推導，未重抓）",
        "generated_at": _dt.datetime.now().astimezone().isoformat(),
        "derived_from": {
            "dryrun_summary.json": "未修改（逐檔 sha256 見 manifest.json）",
            "redline_attribution.json": "未修改",
            "note": "本判定不重跑 dry-run，故查核者對 base artifact 的既有複驗繼續成立。",
        },
        "frozen_games": {
            "list": sorted(f"{y}-{k}-{s}" for y, k, s in FROZEN_GAMES),
            "source": "需求方 2026-08-05 逐場核入（卡面紅線 1）；執行者不得自行擴充",
            "enforcement": "cpbl_pitch_tracking._upsert 於唯一寫入口過濾 + scrape_game_pitches 跳過請求",
        },
        "redline1": {
            "physical_cell_mismatches_total": phys_in_scope + phys_frozen,
            "physical_cell_mismatches_frozen_excluded": phys_frozen,
            "physical_cell_mismatches_in_scope": phys_in_scope,
            "verdict": "PASS" if phys_in_scope == 0 else "FAIL",
            "games_with_physical_mismatch_in_scope":
                [g["game"] for g in kept_games if g["physical_cells"]],
            "frozen_games_detail": frozen_games,
        },
        "redline3_gate": {
            "gate_definition": "未歸因 only_prod_pk = 0（需求方 2026-08-05 語意修訂）",
            "total_rows": len(rows),
            "by_attribution": dict(cat),
            "structural_categories": _STRUCTURAL,
            "unattributed_count": len(unattributed),
            "unattributed_rows": unattributed,
            "verdict": "PASS" if not unattributed else "BLOCK",
            "rows_present_in_pitch_tracking": f"{present}/{len(rows)}",
            "retention": "純 UPSERT 永久保留（本卡不授權任何 DELETE；較完整資料非缺陷）",
            "rows": rows,   # 原始逐筆完整保留，不得刪減
        },
        "pa_build_handoff": {
            "why_it_matters": ("pa_build 以 (pitcher_acnt, pitch_cnt) 把 pitch_tracking 逐球"
                               "映射到 PA，orphan（無 PA 擁有的逐球）為 fail-closed 訊號；"
                               "故 PK 集合變動會影響 reconciliation。"),
            "pk_stability_argument": [
                "1. 寫入路徑無任何 DELETE（tests/test_refresh_pitch_ingest.py 有原始碼層斷言）"
                "，故 PK 集合只增不減——除外的 43 列不會消失。",
                "2. 除外列現況全數存在於正式表（見 rows_present_in_pitch_tracking）。",
                "3. 受影響場次切換後的寫入效果逐場列出：凍結場完全不寫；其餘場 cell_mismatch=0"
                " 且 only_api_pk=0，UPSERT 為值相同的 no-op → pa_build 輸入位元不變。",
                "4. 因此 reconciliation 不會被本次切換觸發（其比對對象 pa_id × PA fingerprint"
                " 的輸入未變）。",
            ],
            "all_games_no_op_or_frozen": no_op,
            "per_game": pa_rows,
        },
    }
    p = outdir / "gate_only_prod_pk.json"
    p.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str) + "\n")

    print("=== 紅線 1（凍結例外後複判）===")
    print(f"  物理不一致合計 {phys_in_scope + phys_frozen}；凍結場除外 {phys_frozen}；"
          f"母體內 {phys_in_scope} → {report['redline1']['verdict']}")
    print(f"  凍結清單：{report['frozen_games']['list']}")
    print("=== 紅線 3 gate（未歸因 = 0）===")
    print(f"  總計 {len(rows)} 筆，分類 {dict(cat)}，未歸因 {len(unattributed)} "
          f"→ {report['redline3_gate']['verdict']}")
    print(f"  除外列現存於正式表：{present}/{len(rows)}")
    print("=== pa_build 交接 ===")
    print(f"  受影響 {len(affected)} 場，全部為凍結或值相同 no-op：{no_op}")
    for r in pa_rows:
        print(f"   · {r['game']} frozen={r['frozen']} build={(r['build_state'] or {}).get('state')}"
              f" → {r['write_effect_after_cutover']}")
    print(f"  → {p}")


if __name__ == "__main__":
    main()
