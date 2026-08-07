"""ML-WP-VERDICT-ROBUST1 §C — 同一份資料、同一份指標，只換判定規則的逐 scope 對照。

**為什麼是這種對照法**：`ML-WP-VAL-RESAMPLE1` 的教訓是，母體每天在長，若不把
「資料變了」與「規則變了」切開，前者會被誤記成後者的效果（那張卡的 D scope 翻面
就是靠三路控制組才辨認出來的）。本腳本因此**完全不碰 DB**：v2 與 v3 兩套判定
都跑在同一份 `verdict_metrics.json` 上，兩者唯一的差異只能是規則。

三條腿：

1. `canonical`  ── `ML-WP-VAL-RESAMPLE1/val1_metrics_events.json` 內**已存**的 verdict
   （2026-08-07 上午資料 × v2 規則）。只讀不算，供母體漂移參照。
2. `today_v2`   ── 今日資料 × **v2 規則**。由 `legacy_verdict_for()` 重放，
   它讀的是 artifact 裡逐分箱保留的 `dev_ci_legacy_seed`（seed 20260725 的單一 seed
   百分位 CI），與基準 `876ce9f` 的 `verdict_for()` 逐行等價。
3. `today_v3`   ── 今日資料 × **v3 規則**。artifact 內 `scopes.*.verdict` 直接取用。

輸出 `verdict_comparison.json` 與 `verdict_comparison.md`（VERDICT.md 引用的表格
一律由此產生，不人工謄寫）。artifact 內**不放 wall-clock 時戳**，故乾淨 worktree
重跑必須逐位重現——`--check` 就是驗這件事。

用法::

    uv run python docs/research/ML-WP-VERDICT-ROBUST1/compare_verdicts.py
    uv run python docs/research/ML-WP-VERDICT-ROBUST1/compare_verdicts.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
RESEARCH = REPO_ROOT / "docs" / "research"

# `audit_io` 是 RESEARCH-VERDICT-AUDIT1 為「artifact 不放時戳 + 每支腳本要有 --check」
# 定下的共用出口。複製一份會讓同一條紀律有兩份實作（本專案反覆踩過的坑），
# 故直接沿用該檔——本卡對它是唯讀。
sys.path.insert(0, str(RESEARCH / "RESEARCH-VERDICT-AUDIT1"))
import audit_io  # noqa: E402

from cpbl.models.winprob_val import THRESHOLDS  # noqa: E402

METRICS = HERE / "verdict_metrics.json"
# 兩份歷史 artifact，皆唯讀：
#  * PUBLISHED：`docs/research/game_recap_wp_val1_metrics.json`，即 main 上仍在被引用的
#    那份。**E scope 是 pre-FIX1 缺陷版**（借 D 分布、cap15；ML-WP-VAL-RESAMPLE1 §6-F1），
#    故 E 那一格只作歷史記錄，不得當事實來源；重生成歸 #100。
#  * RESAMPLE1：取樣修正後、判定規則仍是 v2 的最新一份（08-07 上午資料）。
PUBLISHED = RESEARCH / "game_recap_wp_val1_metrics.json"
CANONICAL = RESEARCH / "ML-WP-VAL-RESAMPLE1" / "val1_metrics_events.json"
OUT_JSON = HERE / "verdict_comparison.json"
OUT_MD = HERE / "verdict_comparison.md"

SCOPE_LABEL = {"A": "一軍例行", "C": "一軍總冠軍賽", "D": "二軍例行",
               "E": "一軍季後挑戰賽"}


# ───────────────────── v2 判定規則（基準 876ce9f 的凍結副本）─────────────────────
def legacy_verdict_for(kind: str, seasons: list[dict], pooled: dict) -> dict:
    """基準 `876ce9f` `winprob_val.verdict_for()` 的**凍結副本**（v2 規則）。

    刻意複製而非 import：被比較的那個版本已經不存在於 HEAD 上，A/B 需要一份不會
    隨本卡改動而漂移的歷史規則。兩處與原文的差異都只是取值路徑，語意相同：

    * 分箱顯著性讀 `dev_ci_legacy_seed`——v2 的 `dev_ci` 就是 seed 20260725 的單一
      seed 百分位 CI，v3 把該欄改成跨 seed 池化後，單一 seed 的值保留在這個欄位。
    * 逐季 `significant_bins` 由同一份單一 seed CI 依 v2 判準（n≥300 且 CI 排除 0）
      現場重算，而非讀 artifact 內 v3 算出的那份。
    """
    if not seasons or not pooled.get("n_pa"):
        return {"status": "unsupported", "reasons": ["無可評樣本"], "v1_flags": []}
    hard, disclosure, v1_flags = [], [], []
    for s in seasons:
        wf = s["walk_forward"]
        tag = f"{kind}{s['year']}"
        if s["coverage"] < THRESHOLDS["min_coverage"]:
            hard.append(f"{tag} coverage {s['coverage']} < {THRESHOLDS['min_coverage']}")
        if wf["brier"] >= s["baseline_home_const"]["brier"]:
            hard.append(f"{tag} Brier {wf['brier']} 未勝過主場常數基準 "
                        f"{s['baseline_home_const']['brier']}")
        if wf["ece_weighted"] > THRESHOLDS["ece_weighted_max"]:
            v1_flags.append(f"{tag} ECE {wf['ece_weighted']}（v1 點估計參考）")
        if wf["decile_max_dev"] is not None and \
                wf["decile_max_dev"] > THRESHOLDS["decile_max_dev"]:
            v1_flags.append(f"{tag} maxdev {wf['decile_max_dev']}（v1 點估計參考）")
        sig = _legacy_significant_bins(wf)
        if sig:
            disclosure.append(f"{tag} 逐季顯著偏差分箱 {sig}（99% 叢集 CI 排除 0）")
    for d in pooled.get("deciles", []):
        ci = d.get("dev_ci_legacy_seed")
        if ci is None or d["n"] < 1000:
            continue
        dev = d["pred"] - d["actual"]
        if ci[0] > 0 or ci[1] < 0:
            if abs(dev) > THRESHOLDS["pooled_bin_dev_max"]:
                hard.append(f"池化十分位 {d['bin']} 偏差 {dev:+.4f} 顯著且超過 "
                            f"±{THRESHOLDS['pooled_bin_dev_max']}（n={d['n']}）")
            else:
                disclosure.append(f"池化十分位 {d['bin']} 偏差 {dev:+.4f} 顯著但幅度受控"
                                  f"（n={d['n']}）")
    small = all(s["walk_forward"]["n_pa"] < THRESHOLDS["min_season_pa"] for s in seasons)
    proxy = kind in ("C", "E")
    if proxy and pooled["ece_weighted"] > THRESHOLDS["proxy_pooled_ece_max"]:
        hard.append(f"proxy 池化 ECE {pooled['ece_weighted']} > "
                    f"{THRESHOLDS['proxy_pooled_ece_max']}，代理證據不足以掛警示上線")
    if hard:
        status = "unsupported"
    elif proxy or small:
        status = "proxy_with_warning"
        if proxy:
            disclosure.append("模型分布借自他 scope（C←A、E←D），規則邊界已換用該 scope 配置")
        if small:
            disclosure.append(f"單季樣本皆 < {THRESHOLDS['min_season_pa']}，統計檢定力不足")
    else:
        status = "supported"
    return {"status": status, "reasons": hard, "disclosure": disclosure,
            "v1_flags": v1_flags}


def _legacy_significant_bins(wf: dict) -> list[int]:
    out = []
    for d in wf.get("deciles") or []:
        ci = d.get("dev_ci_legacy_seed")
        if ci and d["n"] >= 300 and (ci[0] > 0 or ci[1] < 0):
            out.append(d["bin"])
    return out


# ───────────────────────── 對照 ─────────────────────────
def _decisive_bins(pooled: dict) -> list[dict]:
    """兩套規則都會看的那些分箱（n≥1000），逐一列出兩邊怎麼判。"""
    rows = []
    for d in pooled.get("deciles", []):
        if d["n"] < 1000 or d.get("sig_state") is None:
            continue
        dev = round(d["pred"] - d["actual"], 4)
        legacy_ci = d["dev_ci_legacy_seed"]
        rows.append({
            "bin": d["bin"], "n": d["n"], "dev": dev,
            "over_threshold": abs(dev) > THRESHOLDS["pooled_bin_dev_max"],
            "v2_single_seed_ci": legacy_ci,
            "v2_significant": bool(legacy_ci[0] > 0 or legacy_ci[1] < 0),
            "v2_seed_votes": f"{d['n_seeds_significant']}/{d['n_seeds']}",
            "v3_pooled_ci": d["dev_ci"],
            "v3_p_one": d["p_one"],
            "v3_p_one_mc_ci": d["p_one_mc_ci"],
            "v3_reps_total": d.get("reps_total"),
            "v3_state": d["sig_state"],
            "v3_hit_reps_cap": d.get("hit_reps_cap"),
        })
    return rows


def build(metrics: dict[str, Any], canonical: dict[str, Any] | None,
          published: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "note": ("v2 與 v3 兩套判定跑在同一份 verdict_metrics.json 上，"
                 "故兩者差異只能來自規則，不可能來自母體漂移。"),
        "thresholds": metrics["thresholds"],
        "pre_score_source": metrics["pre_score_source"],
        "scopes": {},
    }
    for kind, sc in metrics["scopes"].items():
        seasons, pooled = sc["seasons"], sc["pooled_walk_forward"]
        v2 = legacy_verdict_for(kind, seasons, pooled)
        v3 = sc["verdict"]
        canon = None
        if canonical and kind in canonical.get("scopes", {}):
            canon = canonical["scopes"][kind]["verdict"]
        pub = None
        if published and kind in published.get("scopes", {}):
            pub = published["scopes"][kind]["verdict"]
        out["scopes"][kind] = {
            "label": SCOPE_LABEL.get(kind, kind),
            "n_games_pooled": pooled.get("n_games"),
            "n_pa_pooled": pooled.get("n_pa"),
            "pooled_brier": pooled.get("brier"),
            "baseline_home_const_brier": pooled.get("baseline_home_const_brier"),
            "pooled_ece": pooled.get("ece_weighted"),
            "null_ece": pooled.get("null_ece"),
            "published_status": (pub or {}).get("status"),
            "published_caveat": ("E scope 為 pre-FIX1 缺陷版，只作歷史記錄"
                                 if kind == "E" else None),
            "canonical_status": (canon or {}).get("status"),
            "canonical_reasons": (canon or {}).get("reasons"),
            "today_v2_status": v2["status"],
            "today_v2_reasons": v2["reasons"],
            "today_v3_status": v3["status"],
            "today_v3_reasons": v3["reasons"],
            "today_v3_insufficient": v3.get("insufficient", []),
            "changed_by_rule": v2["status"] != v3["status"],
            "decisive_bins": _decisive_bins(pooled),
            "season_baseline_gate": [
                {
                    "season": s["year"],
                    "n_games": s.get("n_completed_games"),
                    "brier": s["walk_forward"]["brier"],
                    "baseline": s["baseline_home_const"]["brier"],
                    "delta": (s["baseline_home_const"].get("delta_boot") or {}).get("delta"),
                    "delta_ci": (s["baseline_home_const"].get("delta_boot") or {}).get("ci"),
                    "v2_fails": s["walk_forward"]["brier"] >= s["baseline_home_const"]["brier"],
                    "v3_state": (s["baseline_home_const"].get("delta_boot") or {}).get("sig_state"),
                }
                for s in seasons
            ],
        }
    # 上線資格：v2 與 v3 各自有哪些 scope 到得了「可掛上線」的等級。
    shippable = {"supported", "proxy_with_warning"}
    out["shippable_scopes"] = {
        "v2": sorted(k for k, v in out["scopes"].items()
                     if v["today_v2_status"] in shippable),
        "v3": sorted(k for k, v in out["scopes"].items()
                     if v["today_v3_status"] in shippable),
    }
    out["no_scope_gained_shipping_eligibility"] = set(
        out["shippable_scopes"]["v3"]) <= set(out["shippable_scopes"]["v2"])
    return out


def _md(out: dict[str, Any]) -> str:
    L = ["<!-- 由 compare_verdicts.py 產生，勿手改。 -->", ""]
    L += ["### 表 1｜逐 scope 判定：已發布 → RESAMPLE1 → 今日×v2 → 今日×v3", "",
          "| scope | 場數 | 已發布 artifact（v2） | RESAMPLE1（v2・上午資料） | "
          "今日×v2 | 今日×v3 | 規則造成的變化 |",
          "|---|---:|---|---|---|---|---|"]
    for k, v in out["scopes"].items():
        pub = v["published_status"] + ("（pre-FIX1）" if v["published_caveat"] else "")
        L.append(f"| {k}（{v['label']}） | {v['n_games_pooled']:,} | {pub} | "
                 f"{v['canonical_status']} | {v['today_v2_status']} | "
                 f"**{v['today_v3_status']}** | "
                 f"{'**是**' if v['changed_by_rule'] else '否'} |")
    L += ["", "### 表 2｜決定性分箱（n≥1000）：v2 單一 seed vs v3 池化尾機率", "",
          "| scope-分箱 | n | dev | 超 ±0.03？ | v2 單 seed CI | v2 判 | 12-seed 投票 | "
          "v3 池化 CI | v3 p_one（MC 區間） | 重抽次數 | v3 判 |",
          "|---|---:|---:|---|---|---|---|---|---|---:|---|"]
    for k, v in out["scopes"].items():
        for b in v["decisive_bins"]:
            L.append(
                f"| {k}-{b['bin']} | {b['n']:,} | {b['dev']:+.4f} | "
                f"{'**是**' if b['over_threshold'] else '否'} | {b['v2_single_seed_ci']} | "
                f"{'顯著' if b['v2_significant'] else '不顯著'} | {b['v2_seed_votes']} | "
                f"{b['v3_pooled_ci']} | {b['v3_p_one']} {b['v3_p_one_mc_ci']} | "
                f"{b['v3_reps_total']:,} | {b['v3_state']} |")
    L += ["", "### 表 3｜逐季「Brier 須勝過全押主場」閘門", "",
          "| scope-季 | 完成場數 | 季 Brier | 主場常數基準 | Δ | Δ 的 99% CI | "
          "v2 判 | v3 判 |", "|---|---:|---:|---:|---:|---|---|---|"]
    for k, v in out["scopes"].items():
        for s in v["season_baseline_gate"]:
            L.append(
                f"| {k}{s['season']} | {s['n_games']} | {s['brier']} | {s['baseline']} | "
                f"{s['delta']:+.5f} | {s['delta_ci']} | "
                f"{'**硬性失敗**' if s['v2_fails'] else '通過'} | {s['v3_state']} |")
    L += ["", "### 表 4｜proxy 池化 ECE 門檻的可達性（完美校準零假設）", "",
          "| scope | 場數 | 觀測 ECE | H0 期望 ECE | H0 p95 | 門檻 | 門檻可達？ |",
          "|---|---:|---:|---:|---:|---:|---|"]
    gate = out["thresholds"]["proxy_pooled_ece_max"]
    for k, v in out["scopes"].items():
        ne = v["null_ece"]
        if not ne:
            continue
        L.append(f"| {k} | {v['n_games_pooled']:,} | {v['pooled_ece']:.5f} | "
                 f"{ne['analytic_mean']:.5f} | {ne['mc_p95']:.5f} | {gate} | "
                 f"{'否（門檻低於雜訊底線）' if ne['analytic_mean'] > gate else '是'} |")
    L += ["", "### 表 5｜上線資格（只有 supported／proxy_with_warning 可掛上線）", "",
          f"- v2：`{out['shippable_scopes']['v2']}`",
          f"- v3：`{out['shippable_scopes']['v3']}`",
          f"- **v3 沒有讓任何 scope 取得 v2 下沒有的上線資格**："
          f"{out['no_scope_gained_shipping_eligibility']}", ""]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="不寫檔；驗證交付的兩份產物是否與本次重生成逐位相同")
    args = ap.parse_args()
    metrics = json.loads(METRICS.read_text(encoding="utf-8"))
    canonical = (json.loads(CANONICAL.read_text(encoding="utf-8"))
                 if CANONICAL.exists() else None)
    published = (json.loads(PUBLISHED.read_text(encoding="utf-8"))
                 if PUBLISHED.exists() else None)
    out = build(metrics, canonical, published)
    ok = audit_io.emit(OUT_JSON, json.dumps(out, ensure_ascii=False, indent=2),
                       check=args.check)
    ok = audit_io.emit(OUT_MD, _md(out), check=args.check) and ok

    print("=== 逐 scope 判定 ===")
    for k, v in out["scopes"].items():
        print(f"  {k}: 已發布={v['published_status']} → "
              f"RESAMPLE1={v['canonical_status']} → 今日×v2={v['today_v2_status']}"
              f" → 今日×v3={v['today_v3_status']}"
              f"{'   ← 規則造成變化' if v['changed_by_rule'] else ''}")
    print()
    print(f"上線資格 v2={out['shippable_scopes']['v2']} → "
          f"v3={out['shippable_scopes']['v3']}；"
          f"未新增任何上線資格：{out['no_scope_gained_shipping_eligibility']}")
    return audit_io.finish(ok, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
