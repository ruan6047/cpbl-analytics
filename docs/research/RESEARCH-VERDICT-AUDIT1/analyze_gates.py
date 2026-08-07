"""RESEARCH-VERDICT-AUDIT1 §2 — 對否定判定的決定性閘門做「雜訊底線」重算。

問題：三準則裡最難機械化的是準則 3——「樣本不足以判定」與「測了，不準」的分界。
本腳本把這條線量化：**在模型完全校準的零假設下，該閘門的統計量會落在哪裡？**
若零假設下的期望值已經超過門檻，那個門檻就不是判準，是雜訊產生器
（此判讀方法不是本卡發明的，`ML-OUTCOME-SIMPLE-LEAK2_RESULTS.md` §3.2 已在本專案內
用過同一招把固定校準斜率區間打掉，本卡只是把它套到 WP 家族尚未受檢的閘門上）。

三件事，全部只讀已交付 artifact，不讀 DB、不重跑任何模型：

1. **ECE 雜訊底線**（VAL1 A/C/D/E、CAL1 池化）。ECE 是**加權絕對**偏差，
   在有限樣本下**恆為正偏**——完美校準的模型也量不到 0。用 artifact 自帶的
   逐分箱 game-cluster bootstrap SE（`dev_se`），在 H0: dev_b ~ N(0, se_b) 下
   算 E[ECE] = Σ w_b·E|dev_b| = Σ w_b·se_b·√(2/π)，另以 Monte Carlo 取 95 百分位。
   `proxy_pooled_ece_max = 0.05` 這道門檻若低於該底線，季後 scope 永遠過不了。

2. **CAL1 逐局帶閘門的不確定性**。CAL1 的 `pooled_inning_bands` 是唯一**沒有**
   任何 SE／CI 的閘門，而它是 CAL1 剔除其他三條後僅存的決定性證據。
   後續卡 `GAME-RECAP-WP-STRENGTH1` 對**同一 scope、同期間、幾乎同母體**
   （A 2023–2026，1,233 場 vs CAL1 1,227 場）的同一組局帶算了 cluster bootstrap SE，
   本腳本直接借該 SE 給 CAL1 的 dev 配上 99% CI。這是跨 artifact 的移植，
   不是重跑，故一併輸出兩者母體差以供判斷可比性。

3. **逐季小樣本 scope 的解析度**。列出 C／E 各季的完成場數與逐分箱 dev_se 值域，
   用來回答「這一季的 Brier 比較有沒有解析度」。

輸出 `gate_analysis.json`；stdout 為摘要。

用法：
    uv run python docs/research/RESEARCH-VERDICT-AUDIT1/analyze_gates.py
    uv run python docs/research/RESEARCH-VERDICT-AUDIT1/analyze_gates.py --check
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import audit_io
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
RESEARCH = REPO_ROOT / "docs" / "research"
OUT_PATH = RESEARCH / "RESEARCH-VERDICT-AUDIT1" / "gate_analysis.json"
OUT_MD = RESEARCH / "RESEARCH-VERDICT-AUDIT1" / "gate_tables.md"

VAL1 = RESEARCH / "game_recap_wp_val1_metrics.json"
VAL1_FIX1 = RESEARCH / "game_recap_wp_val1_fix1_metrics.json"
CAL1 = RESEARCH / "game_recap_wp_cal1_metrics.json"
STRENGTH1 = RESEARCH / "game_recap_wp_strength1_metrics.json"

HALF_NORMAL_MEAN = math.sqrt(2.0 / math.pi)  # E|X| for X ~ N(0, 1)
MC_REPS = 20000
MC_SEED = 20260807
Z99 = 2.5758293035489004  # 雙尾 99% 常態分位


def _load(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def null_ece(deciles: list[dict[str, Any]], rng: np.random.Generator) -> dict[str, Any]:
    """完美校準零假設下的 ECE 分布。

    ECE = Σ_b w_b·|dev_b|。H0 取 dev_b ~ N(0, se_b)，se_b 直接用 artifact 自己的
    game-cluster bootstrap SE（同一把尺，故不引入新的變異假設）。

    近似的兩處，方向已標明：
    - **分箱間獨立**：實際上同一場的打席橫跨多個分箱，dev_b 之間有相關。忽略相關
      對 ECE（絕對值之和）的影響方向不定，故本值只作**量級**判讀，不作檢定。
    - **常態**：分箱 n 皆 ≥ 數十場叢集時尚可；n_games 極小的 scope（C/E）本來就是
      「解析度不足」的直接證據，不倚賴此近似的精度。
    """
    se = np.array([float(d["dev_se"]) for d in deciles], dtype=float)
    n = np.array([float(d["n"]) for d in deciles], dtype=float)
    w = n / n.sum()
    analytic = float((w * se * HALF_NORMAL_MEAN).sum())
    draws = rng.normal(0.0, 1.0, size=(MC_REPS, se.size)) * se
    sim = np.abs(draws) @ w
    return {
        "n_bins": int(se.size),
        "analytic_mean": analytic,
        "mc_mean": float(sim.mean()),
        "mc_p95": float(np.quantile(sim, 0.95)),
        "mc_p99": float(np.quantile(sim, 0.99)),
        "dev_se_min": float(se.min()),
        "dev_se_max": float(se.max()),
    }


def _write_markdown(out: dict[str, Any], *, check: bool) -> bool:
    """VERDICTS.md 引用的表格一律由此產生，杜絕人工謄寫（STRENGTH1 曾因謄寫連三輪查核失敗）。"""
    L: list[str] = ["<!-- 由 analyze_gates.py 產生，勿手改。 -->", ""]
    L += [
        "### 表 1｜VAL1 池化：ECE 觀測值 vs 完美校準零假設下的雜訊底線",
        "",
        "| scope | 場數 | 觀測 ECE | H0 期望 ECE | H0 p95 | proxy 門檻 | 門檻低於底線？ | 觀測值落在 H0 p95 內？ | 顯著分箱 |",
        "|---|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for k, v in out["val1_scopes"].items():
        ne = v["null_ece"]
        L.append(
            f"| {k} | {v['n_games']:,} | {v['observed_ece']:.5f} | {ne['analytic_mean']:.5f} | "
            f"{ne['mc_p95']:.5f} | {v['proxy_ece_gate']} | "
            f"{'**是**' if v['gate_below_noise_floor'] else '否'} | "
            f"{'**是**' if v['observed_ece_within_null_p95'] else '否'} | {v['significant_bins']} |"
        )
    L += [
        "",
        "### 表 2｜VAL1 池化 Brier vs 全押主場基準",
        "",
        "| scope | 場數 | 池化 Brier | 全押主場基準 | 模型勝基準？ |",
        "|---|---:|---:|---:|---|",
    ]
    for k, v in out["val1_scopes"].items():
        L.append(
            f"| {k} | {v['n_games']:,} | {v['brier']:.5f} | {v['baseline_home_const_brier']:.5f} | "
            f"{'是' if v['beats_home_constant_baseline'] else '否'} |"
        )
    L += [
        "",
        "### 表 3｜C／E 逐季解析度（決定性理由引用的那幾季）",
        "",
        "| scope-季 | 完成場數 | n_PA | 該季 Brier | 逐分箱 dev_se 值域 |",
        "|---|---:|---:|---:|---|",
    ]
    for k in ("C", "E"):
        for s in out["val1_scopes"][k]["seasons"]:
            lo, hi = s["dev_se_min"], s["dev_se_max"]
            L.append(
                f"| {k}{s['year']} | {s['n_completed_games']} | {s['n_pa']} | {s['brier']} | "
                f"[{lo}, {hi}] |"
            )
    L += [
        "",
        "### 表 4｜CAL1 逐局帶 dev 配上 99% CI（SE 借自 STRENGTH1 同 scope 同期間 adj 局帶 bootstrap）",
        "",
        "| 帶 | 族 | n_PA | dev (pt) | 99% CI (pt) | CI 含 0 |",
        "|---|---|---:|---:|---|---|",
    ]
    for b in out["cal1_band_gate"]["bands"]:
        for fam, r in b["families"].items():
            lo, hi = r["ci99_borrowed"]
            L.append(
                f"| {b['band']} | {fam} | {r['n_pa']:,} | {r['dev']*100:+.2f} | "
                f"[{lo*100:+.2f}, {hi*100:+.2f}] | {'**是**' if r['ci99_contains_zero'] else '否'} |"
            )
    L += [
        "",
        f"> CAL1 自身 artifact 的局帶欄是否帶不確定性量化："
        f"**{'有' if out['cal1_band_gate']['cal1_has_native_band_uncertainty'] else '無'}**"
        f"（CAL1 池化 {out['cal1_band_gate']['cal1_n_games_pooled']:,} 場；"
        f"借用 SE 的 STRENGTH1 池化 {out['cal1_band_gate']['strength1_n_games_pooled']:,} 場）。",
        "",
    ]
    return audit_io.emit(OUT_MD, "\n".join(L) + "\n", check=check)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check",
        action="store_true",
        help="不寫檔；驗證交付的 gate_analysis.json／gate_tables.md 是否與本次重生成逐位相同",
    )
    args = ap.parse_args()

    rng = np.random.default_rng(MC_SEED)
    val1 = _load(VAL1)
    fix1 = _load(VAL1_FIX1)
    cal1 = _load(CAL1)
    strength1 = _load(STRENGTH1)

    out: dict[str, Any] = {
        "note": "全部輸入為已交付 artifact，全程唯讀；本腳本不重跑任何模型、不讀 DB。",
        "inputs": {
            str(p.relative_to(REPO_ROOT)): None for p in (VAL1, VAL1_FIX1, CAL1, STRENGTH1)
        },
        "mc": {"reps": MC_REPS, "seed": MC_SEED},
    }

    # ---- 1. VAL1 各 scope 的 ECE 雜訊底線（E 用 FIX1 版，其餘用 canonical）----
    ece_gate = float(val1["thresholds"]["proxy_pooled_ece_max"])
    scopes: dict[str, Any] = {}
    for scope in ("A", "C", "D", "E"):
        src = fix1 if scope == "E" else val1
        src_name = "game_recap_wp_val1_fix1_metrics.json" if scope == "E" else "game_recap_wp_val1_metrics.json"
        sc = src["scopes"][scope]
        pw = sc["pooled_walk_forward"]
        rec = {
            "source_artifact": src_name,
            "n_games": pw["n_games"],
            "n_pa": pw["n_pa"],
            "observed_ece": pw["ece_weighted"],
            "brier": pw["brier"],
            "baseline_home_const_brier": pw.get("baseline_home_const_brier"),
            "beats_home_constant_baseline": (
                pw["brier"] < pw["baseline_home_const_brier"]
                if pw.get("baseline_home_const_brier") is not None
                else None
            ),
            "significant_bins": pw["significant_bins"],
            "verdict_status": sc["verdict"]["status"],
            "verdict_reasons": sc["verdict"]["reasons"],
            "null_ece": null_ece(pw["deciles"], rng),
        }
        rec["proxy_ece_gate"] = ece_gate
        rec["gate_below_noise_floor"] = rec["null_ece"]["analytic_mean"] > ece_gate
        rec["observed_ece_within_null_p95"] = pw["ece_weighted"] <= rec["null_ece"]["mc_p95"]
        # 逐季解析度
        seasons = []
        for s in sc["seasons"]:
            wf = s.get("walk_forward") or {}
            devses = [d["dev_se"] for d in (wf.get("deciles") or []) if d.get("dev_se") is not None]
            seasons.append(
                {
                    "year": s["year"],
                    "n_completed_games": s.get("n_completed_games"),
                    "n_pa": wf.get("n_pa"),
                    "brier": wf.get("brier"),
                    "baseline_home_const_brier": wf.get("baseline_home_const_brier"),
                    "dev_se_min": min(devses) if devses else None,
                    "dev_se_max": max(devses) if devses else None,
                }
            )
        rec["seasons"] = seasons
        scopes[scope] = rec
    out["val1_scopes"] = scopes

    # ---- 2. CAL1 逐局帶閘門：借 STRENGTH1 的 cluster bootstrap SE 配 CI ----
    cal_pooled = cal1["pooled"]
    cal_bands = cal1["pooled_inning_bands"]
    st_bands = strength1["pooled_inning_bands"]
    band_rows = []
    for band in ("1-3", "4-6", "7-9", "10+"):
        base = cal_bands["base"][band]
        beta = cal_bands["beta"][band]
        iso = cal_bands["isotonic"][band]
        se = st_bands["adj"]["boot"][band]["se"]
        rows = {}
        for fam, d in (("base", base), ("isotonic", iso), ("beta", beta)):
            dev = d["pred"] - d["actual"]
            rows[fam] = {
                "n_pa": d["n"],
                "pred": d["pred"],
                "actual": d["actual"],
                "dev": dev,
                "ci99_borrowed": [dev - Z99 * se, dev + Z99 * se],
                "ci99_contains_zero": abs(dev) <= Z99 * se,
            }
        band_rows.append(
            {
                "band": band,
                "borrowed_se_from_strength1_adj": se,
                "families": rows,
                "worsening_pt_beta_vs_base": abs(beta["pred"] - beta["actual"]) * 100
                - abs(base["pred"] - base["actual"]) * 100,
            }
        )
    out["cal1_band_gate"] = {
        "cal1_has_native_band_uncertainty": any(
            k in cal_bands.get("base", {}).get("1-3", {}) for k in ("se", "ci", "dev_se")
        ),
        "cal1_n_games_pooled": cal_pooled["base"]["n_games"],
        "strength1_n_games_pooled": strength1["pooled"]["base"]["n_games"],
        "population_comparable_note": (
            "CAL1 池化 2023–2026 A 共 1,227 場；STRENGTH1 同 scope 同期間 1,233 場"
            "（差 6 場＝CAL1 當時的 published PA build 缺口）。借用 SE 的前提是"
            "叢集數與分箱 n 幾乎相同，故 SE 量級可移植；此為量級判讀，不作為正式檢定。"
        ),
        "thresholds": {
            "band_dev_worsen_hard_pt": cal1["thresholds"]["band_dev_worsen_hard_pt"],
            "strength1_band_dev_max": strength1["thresholds"]["band_dev_max"],
        },
        "bands": band_rows,
        "cal1_verdict_reasons": cal1["verdict"]["reasons"],
    }

    # ---- 3. STRENGTH1 的決定性閘門 4c 與其自報 CI ----
    st_seasons = []
    for s in strength1["seasons"]:
        st_seasons.append(
            {
                "year": s.get("year"),
                "base_brier": (s.get("base") or {}).get("raw_brier") or (s.get("base") or {}).get("brier"),
                "adj_brier": (s.get("adj") or {}).get("raw_brier") or (s.get("adj") or {}).get("brier"),
            }
        )
    out["strength1"] = {
        "verdict_reasons": strength1["verdict"]["reasons"],
        "pooled_brier_delta_diagnostic": strength1["pooled"].get("brier_delta_diagnostic"),
        "seasons": st_seasons,
    }

    ok = audit_io.emit(
        OUT_PATH, json.dumps(out, ensure_ascii=False, indent=2), check=args.check
    )
    ok = _write_markdown(out, check=args.check) and ok

    # ---- stdout 摘要 ----
    print("=== VAL1 池化：ECE 雜訊底線 vs 0.05 proxy 門檻 ===")
    print(f"{'scope':>5} {'games':>6} {'obs ECE':>9} {'H0 mean':>9} {'H0 p95':>9} {'sig bins':>9}  gate<floor")
    for k, v in out["val1_scopes"].items():
        ne = v["null_ece"]
        print(
            f"{k:>5} {v['n_games']:>6} {v['observed_ece']:>9.5f} {ne['analytic_mean']:>9.5f} "
            f"{ne['mc_p95']:>9.5f} {str(v['significant_bins']):>9}  {v['gate_below_noise_floor']}"
        )
    print()
    print("=== VAL1：池化 Brier vs 全押主場基準（模型是否贏基準）===")
    for k, v in out["val1_scopes"].items():
        print(
            f"  {k}: brier {v['brier']:.5f} vs baseline {v['baseline_home_const_brier']:.5f} "
            f"→ beats={v['beats_home_constant_baseline']}"
        )
    print()
    print("=== C／E 逐季解析度（完成場數與逐分箱 dev_se 值域）===")
    for k in ("C", "E"):
        for s in out["val1_scopes"][k]["seasons"]:
            print(
                f"  {k}{s['year']}: games={s['n_completed_games']} pa={s['n_pa']} "
                f"brier={s['brier']} baseline={s['baseline_home_const_brier']} "
                f"dev_se∈[{s['dev_se_min']}, {s['dev_se_max']}]"
            )
    print()
    print("=== CAL1 逐局帶（借 STRENGTH1 同期間 cluster SE 配 99% CI）===")
    print(f"{'band':>5} {'family':>9} {'dev(pt)':>9} {'99% CI (pt)':>24}  含 0")
    for b in out["cal1_band_gate"]["bands"]:
        for fam, r in b["families"].items():
            lo, hi = r["ci99_borrowed"]
            print(
                f"{b['band']:>5} {fam:>9} {r['dev']*100:>9.2f} "
                f"{f'[{lo*100:+.2f}, {hi*100:+.2f}]':>24}  {r['ci99_contains_zero']}"
            )
    print()
    print(f"artifact: {OUT_PATH.relative_to(REPO_ROOT)}")
    return audit_io.finish(ok, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
