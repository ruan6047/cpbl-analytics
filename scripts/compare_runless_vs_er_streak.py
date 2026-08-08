#!/usr/bin/env python
"""ML-PITCHER-RUNLESS1：失分口徑 vs 自責分口徑的**逐人對照**與**媒體數字檢查點**。

交付文件（`docs/research/ML-PITCHER-RUNLESS1/RESULTS.md`）的兩張表由本腳本產生——
「並列 vs 取代」的建議要附證據，而證據不能是人工敲出來的數字。窮舉對帳在
`scripts/reconcile_scoreless_streak.py`（R1–R10 ＋ X1–X3），本腳本**不做對帳**，
只做對照；兩者刻意分開，避免「產生數字的人順便宣布數字沒問題」。

輸出兩張表：

1. **逐人對照**：指定球季／層級下，兩個口徑的排行榜取**聯集**（不是只比前 N 名的交集
   ——那會把「在 A 榜上、掉出 B 榜」的人整個藏起來），逐人列出兩邊的局數、名次與差額。
2. **媒體檢查點**：把資料截到報導當下的日期重跑，與公開報導的數字對照。截日以
   `Appearance.game_date <= as_of` 過濾，**不改動任何演算法**。

`--as-of` 是資料截點，不是「今天」；本腳本不輸出 wall-clock 時戳，artifact 可逐次比對。

## 母體會長大：數字逐日變動是常態

聯集人數、母體人數都會隨新比賽增加而變動——canonical `templates/statistical-redline.md`
第 9 條：**標注 as-of、不設法凍結數字**。`--compare-to` 與對帳腳本用同一套判定
（`identical` / `input_drift` / `mismatch_same_input`，見
`cpbl.api.scoreless.classify_artifact_drift`），只有「指紋相同卻算出不同結果」才 exit 1。

用法：

    uv run python scripts/compare_runless_vs_er_streak.py
    uv run python scripts/compare_runless_vs_er_streak.py --json-out artifacts/runless-compare.json
    uv run python scripts/compare_runless_vs_er_streak.py \
        --compare-to docs/research/ML-PITCHER-RUNLESS1/COMPARE_A.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from cpbl.api.helpers import kinds_of
from cpbl.api.scoreless import (
    DRIFT_INPUT,
    DRIFT_MISMATCH,
    build_item,
    classify_artifact_drift,
    compute_all,
    load_appearances,
    population_fingerprint,
)
from cpbl.models.scoreless_streak import EARNED_RUN_BASIS, RUN_BASIS, Basis

# 檢查點。`expected_innings` 是**外部／既有的數字**，不是本次算出來的；對不上時照實
# 列出差額，不調參數去湊。
#
# **`source_kind` 必須照實標**，不可把三筆都說成「媒體對照」：
#   - `media`：公開報導的數字（來源見 ML-PITCHER-SCORELESS1_RESULTS.md §3.4）。
#     2018+ 且有媒體報導的連續紀錄只有坎南與黃子鵬兩筆，前五名其餘三位皆早於資料邊界。
#   - `prior_internal`：**本專案先前以另一條路算出**的數字。SCORELESS1_RESULTS.md §3.3
#     自己就寫明「這一節是內部資料算出的口徑差異，**不是第三筆公開紀錄對照**」。
#     它有交叉驗證價值（另一次計算、同一個答案），但**不能充當第三筆外部證據**。
CHECKPOINTS = [
    {
        "player_id": "0000007570", "player_name": "坎南", "as_of": date(2026, 6, 20),
        "season": 2026, "kind_code": "A", "expected_innings": 30.0,
        "source_kind": "media",
        "wording": "先發連續 35 局無失分（6/26 第 6 局中斷）→ 開賽前累積 30 局",
        "note": "媒體用詞是「無失分」；其中 3.0 局來自 04-23 那場的零得分後綴（尾段機制）",
    },
    {
        "player_id": "0000002274", "player_name": "黃子鵬", "as_of": date(2026, 7, 15),
        "season": 2026, "kind_code": "A", "expected_innings": 33.2,
        "source_kind": "media",
        "wording": "自 6/7 起連 5 場、33.2 局無失分",
        "note": "媒體用詞是「無失分」；這段連續紀錄正好起於一次出賽的開頭",
    },
    {
        "player_id": "0000003639", "player_name": "呂彥青", "as_of": date(2026, 7, 26),
        "season": 2026, "kind_code": "A", "expected_innings": 9.0,
        "source_kind": "prior_internal",
        "wording": "SCORELESS1_RESULTS.md §3.3 表格內「連續無失分局數」欄：9.0 局 / 9 場",
        "note": "同時點自責分口徑為 28.1 局；差異來自 06-11 那場 runs=1, earned_runs=0。"
                "§3.3 明文這不是公開紀錄對照，故此列是**內部交叉驗證**不是外部證據",
    },
]


def _streaks(kind_code: str, basis: Basis, as_of: date | None = None,
             player_id: str | None = None):
    """→ (player_id → item dict, player_id → 姓名)。`as_of` 只過濾出賽，不改演算法。"""
    kinds = kinds_of(kind_code)
    by_player, names = load_appearances(kinds, player_id)
    if as_of is not None:
        by_player = {pid: [a for a in apps if a.game_date and a.game_date <= as_of]
                     for pid, apps in by_player.items()}
        by_player = {pid: apps for pid, apps in by_player.items() if apps}
    results = compute_all(by_player, (kind_code,), basis=basis)
    items = {pid: build_item(pid, names.get(pid), by_player[pid], res, basis)
             for pid, res in results.items()}
    return items, names, by_player


def _ranked(items: dict[str, dict], season: int, by_player) -> list[dict]:
    """端點的母體與排序規則：該季有出賽、outs>0，依 outs → strict_outs → player_id。"""
    pool = [i for pid, i in items.items()
            if i["outs"] > 0 and any(a.year == season for a in by_player[pid])]
    pool.sort(key=lambda i: (-i["outs"], -i["strict_outs"], i["player_id"]))
    return pool


def leaderboard_diff(season: int, kind_code: str, top: int) -> dict:
    er_items, names, by_player = _streaks(kind_code, EARNED_RUN_BASIS)
    rn_items, _, _ = _streaks(kind_code, RUN_BASIS)
    er_rank = _ranked(er_items, season, by_player)
    rn_rank = _ranked(rn_items, season, by_player)
    er_pos = {i["player_id"]: n for n, i in enumerate(er_rank, 1)}
    rn_pos = {i["player_id"]: n for n, i in enumerate(rn_rank, 1)}

    # 聯集：只比前 N 的交集會藏起「掉出榜外」的人，而那正是最該看的一類。
    keys = [i["player_id"] for i in er_rank[:top]]
    keys += [i["player_id"] for i in rn_rank[:top] if i["player_id"] not in keys]

    # 差異的**成因**要能逐筆看見，不能只給兩個數字：把失分口徑的中斷場連同該場官方
    # runs／earned_runs 一起列出。差額幾乎全部落在 `runs>0 且 earned_runs=0` 的場次上，
    # 但那是要被檢驗的宣稱，不是預設——所以逐筆輸出，讓讀的人自己判斷。
    by_key = {pid: {a.key: a for a in apps} for pid, apps in by_player.items()}

    rows = []
    for pid in keys:
        e, r = er_items[pid], rn_items[pid]
        brk = None
        if r["break_game"]:
            g = r["break_game"]
            a = by_key[pid].get((g["year"], g["kind_code"], g["game_sno"]))
            if a is not None:
                brk = {"game_date": g["game_date"], "opponent": g["opponent"],
                       "runs": a.runs, "earned_runs": a.earned_runs,
                       "unearned_only": a.runs is not None and a.earned_runs is not None
                       and a.runs > 0 and a.earned_runs == 0}
        rows.append({
            "run_break_game": brk,
            "player_id": pid, "player_name": names.get(pid),
            "er_rank": er_pos.get(pid), "er_innings": e["innings"],
            "er_strict_innings": e["strict_innings"], "er_tail_outs": e["tail_outs"],
            "er_appearances": e["appearances_counted"], "er_break": e["break_reason"],
            "run_rank": rn_pos.get(pid), "run_innings": r["innings"],
            "run_strict_innings": r["strict_innings"], "run_tail_outs": r["tail_outs"],
            "run_appearances": r["appearances_counted"], "run_break": r["break_reason"],
            "outs_delta": r["outs"] - e["outs"],
            "same_value": r["outs"] == e["outs"],
        })
    differing = [x for x in rows if not x["same_value"]]
    return {
        "season": season, "kind_code": kind_code, "top": top,
        "er_pool": len(er_rank), "run_pool": len(rn_rank),
        "identical_in_union": sum(1 for x in rows if x["same_value"]),
        "differing_in_union": len(differing),
        # 差異場次中「只掉非自責分」的比例——這是「兩個口徑的差額來自哪裡」的直接證據。
        "differing_broken_by_unearned_only": sum(
            1 for x in differing
            if x["run_break_game"] and x["run_break_game"]["unearned_only"]),
        "rows": rows,
    }


def media_checks() -> list[dict]:
    out = []
    for cp in CHECKPOINTS:
        row = {k: cp[k] for k in
               ("player_name", "player_id", "season", "kind_code",
                "source_kind", "wording", "expected_innings", "note")}
        row["as_of"] = str(cp["as_of"])
        for label, basis in (("er", EARNED_RUN_BASIS), ("run", RUN_BASIS)):
            items, _, _ = _streaks(cp["kind_code"], basis, cp["as_of"], cp["player_id"])
            item = items.get(cp["player_id"])
            row[f"{label}_innings"] = item["innings"] if item else None
            row[f"{label}_strict_innings"] = item["strict_innings"] if item else None
            row[f"{label}_tail_outs"] = item["tail_outs"] if item else None
            row[f"{label}_appearances"] = item["appearances_counted"] if item else None
            row[f"{label}_match"] = bool(item and item["innings"] == cp["expected_innings"])
        out.append(row)
    return out


# `--compare-to` 追蹤的輸出面統計量（輸入面走 fingerprint，兩者刻意分開）。
TRACKED = ("er_pool", "run_pool", "union_size", "identical_in_union",
           "differing_in_union", "differing_broken_by_unearned_only",
           "checkpoints_matched_er", "checkpoints_matched_run")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--kind", default="A")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--json-out")
    ap.add_argument("--compare-to", metavar="ARTIFACT.json",
                    help="與既有 artifact 比對，把差異歸因到 input drift 或算錯")
    args = ap.parse_args()

    diff = leaderboard_diff(args.season, args.kind, args.top)
    checks = media_checks()
    by_player, _names = load_appearances(kinds_of(args.kind))
    diff["fingerprint"] = population_fingerprint(by_player, kinds_of(args.kind))
    diff["union_size"] = len(diff["rows"])
    diff["checkpoints_matched_er"] = sum(1 for c in checks if c["er_match"])
    diff["checkpoints_matched_run"] = sum(1 for c in checks if c["run_match"])

    print(f"逐人對照：{args.season} {args.kind}"
          f"（資料 as-of {diff['fingerprint']['data_asof']}；"
          f"兩口徑前 {args.top} 名的**聯集**；"
          f"母體 自責分 {diff['er_pool']} 人／失分 {diff['run_pool']} 人）\n")
    hdr = ("投手", "自責分 名次", "自責分 局數", "自責分 場次",
           "失分 名次", "失分 局數", "失分 場次", "差額(outs)",
           "失分口徑中斷場", "該場 R/ER")
    print(" | ".join(hdr))
    print(" | ".join("---" for _ in hdr))
    for x in diff["rows"]:
        b = x["run_break_game"]
        print(" | ".join(str(v) for v in (
            x["player_name"], x["er_rank"] or "-", x["er_innings"], x["er_appearances"],
            x["run_rank"] or "-", x["run_innings"], x["run_appearances"],
            x["outs_delta"],
            f"{b['game_date']} vs {b['opponent']}" if b else x["run_break"],
            f"{b['runs']}/{b['earned_runs']}" if b else "-")))
    print(f"\n聯集 {len(diff['rows'])} 人中：兩口徑數值相同 {diff['identical_in_union']}、"
          f"不同 {diff['differing_in_union']}；不同者中由「只掉非自責分」的場次中斷的有 "
          f"{diff['differing_broken_by_unearned_only']} 人")

    n_media = sum(1 for c in checks if c["source_kind"] == "media")
    print(f"\n檢查點（`as_of` 為資料截點；expected 是外部／既有數字，不是本次算出來的）\n"
          f"來源分類：media {n_media} 筆＝公開報導；prior_internal "
          f"{len(checks) - n_media} 筆＝本專案先前計算，**不算外部證據**\n")
    mhdr = ("投手", "來源", "資料截至", "對照值", "自責分口徑", "自責分符合",
            "失分口徑", "失分符合")
    print(" | ".join(mhdr))
    print(" | ".join("---" for _ in mhdr))
    for c in checks:
        print(" | ".join(str(v) for v in (
            c["player_name"], c["source_kind"], c["as_of"], c["expected_innings"],
            c["er_innings"], "✓" if c["er_match"] else "✗",
            c["run_innings"], "✓" if c["run_match"] else "✗")))

    current = {"leaderboard_diff": diff, "media_checkpoints": checks}

    mismatches = 0
    if args.compare_to:
        with open(args.compare_to, encoding="utf-8") as fh:
            previous = json.load(fh)
        row = classify_artifact_drift(previous.get("leaderboard_diff"), diff, TRACKED)
        print(f"\n輸入漂移偵測（對照 artifact：{args.compare_to}）")
        print("**母體長大造成的數字變動不是缺陷**（statistical-redline 第 9 條："
              "標注 as-of、不凍結數字）。\n")
        if row["verdict"] is None:
            print(f"  無從分類：{row['reason']}")
        else:
            d = row["input_delta"]
            print(f"  as-of {row['data_asof_before']} → {row['data_asof_after']}；"
                  f"出賽數 {d['appearances']['before']}→{d['appearances']['after']}"
                  f"（{d['appearances']['delta']:+d}）、"
                  f"投手數 {d['pitchers']['delta']:+d}、"
                  f"逐局比分列 {d['scoreboard_rows']['delta']:+d}")
            for f in row["changed_fields"]:
                print(f"    輸出 {f['field']}：{f['before']} → {f['after']}")
            print(f"  判定：{row['verdict']}")
            if row["verdict"] == DRIFT_INPUT:
                print("  → 差異歸因於輸入變動；處置是更新 artifact 並標注 as-of，"
                      "不是把數字凍住。")
        mismatches = 1 if row["verdict"] == DRIFT_MISMATCH else 0
        current["drift_vs"] = {"artifact": args.compare_to, "row": row}

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(current, fh, ensure_ascii=False, indent=2)
        print(f"\nJSON → {args.json_out}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
