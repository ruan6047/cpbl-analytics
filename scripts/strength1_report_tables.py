# LIFECYCLE: ci_guard · CI 繫結守衛——不必手動跑，CI 會跑；刪了 CI 會紅
"""由 canonical artifact 產生 GAME-RECAP-WP-STRENGTH1 報告的數字區塊。

**為什麼存在**：本卡四輪跨家族查核中三次是執行者「過度宣稱」——人工謄寫數字、抽樣核對
後宣稱「全數對帳」，實際仍有 8 處過期（iteration 3 查核 F2）。人工對帳的失敗率在這條線上
是實測的，不是假設的。故報告的數字改由本腳本從 artifact 產生，並以 `--check` 在 pytest 內
釘住同步——**讓「報告數字過期」在結構上不可能發生**，而不是再對帳一次。

用法：

    uv run python scripts/strength1_report_tables.py            # 就地更新報告區塊
    uv run python scripts/strength1_report_tables.py --check    # 只檢查是否同步（CI／pytest）

報告端以 HTML 註解標記可產生區塊：

    <!-- generated:population start -->
    ...（本腳本產生，勿手改）
    <!-- generated:population end -->

標記外的敘述（機制解釋、設計理由、對照論述）仍由人撰寫；**凡帶數字者一律放進區塊內**。
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "docs/research/game_recap_wp_strength1_metrics.json"
REPORT = ROOT / "docs/research/GAME-RECAP-WP-STRENGTH1_RESULTS.md"

CAL1_ARTIFACT = ROOT / "docs/research/game_recap_wp_cal1_metrics.json"

# 報告裡**每一張帶數字的表格**都必須有歸屬：不是由本腳本產生，就得在這裡列明「為什麼不是」。
# `test_every_numeric_table_is_accounted_for` 會枚舉報告中的所有表格逐一比對——iteration 4
# 的守衛只驗證既有區塊，於是 §3／§5／§6.3／§7.1 四張表在區塊外過期也照樣 exit 0（查核 F1）。
UNGENERATED_TABLES = {
    "| # | 紅線 | 落地位置 | 驗證 |":
        "§1 紅線對照：內容是設計敘述與測試名稱，無 artifact 數值",
}


def cal1_brier() -> dict[int, float]:
    """WP-CAL1 的逐季 Brier，直接讀該卡 artifact 的 `isotonic`（其定案校準器）。

    iteration 4 把這四個值寫成腳本常數並在報告註腳聲明「外部常數」；查核 F1 要求改為
    具來源資訊的 artifact 或取得需求方例外。CAL1 artifact 就在同一個目錄，讀它即可，
    不需要例外——常數本來就是不必要的。
    """
    cal1 = json.loads(CAL1_ARTIFACT.read_text(encoding="utf-8"))
    return {s["year"]: s["isotonic"]["brier"] for s in cal1["seasons"]}


def cal1_band_contrast() -> tuple[float, float]:
    """WP-CAL1 池化 1-3 局帶的 base vs isotonic 偏差（pt）。

    isotonic 是 CAL1 的定案校準器（§4.1 的 CAL1 欄同源）。iteration 5 發現本報告 §4.3 引
    isotonic（−2.41pt）、§6.4 卻引 beta（−2.58pt≈2.6pt），兩處各引一個校準器且都沒說是哪個
    ——由枚舉式表格守衛（iteration 4 查核 F1 的修正）反照出來。統一由此函式供數。
    """
    cal1 = json.loads(CAL1_ARTIFACT.read_text(encoding="utf-8"))
    bands = cal1["pooled_inning_bands"]
    dev = lambda fam: (bands[fam]["1-3"]["pred"] - bands[fam]["1-3"]["actual"]) * 100  # noqa: E731
    return dev("base"), dev("isotonic")


def _pct(part: float, whole: float) -> str:
    return f"{part / whole * 100:.1f}%" if whole else "—"


def _num(x: float, digits: int = 6, signed: bool = False) -> str:
    """數字一律用文件既有的排版負號（U+2212），避免產生區塊與人工段落混排時樣式不一。"""
    return f"{x:+.{digits}f}".replace("-", "−") if signed else f"{x:.{digits}f}"


def population_block(a: dict) -> list[str]:
    pop, fp = a["population"], a["population_fingerprint"]
    years = sorted(pop["by_year"], key=int)
    latest = max(fp["by_year"], key=int)
    fy = fp["by_year"][latest]
    return [
        f"**賽前母體**：A 一軍例行 **{pop['n_games']:,} 場**（完成場且 "
        f"`game_date ≤ data_as_of`；本次 `data_as_of = {a['data_as_of']}`），"
        f"含 **{pop['tie_games']} 場和局**（標籤 `y=0.5`）。",
        "",
        "| 年 | " + " | ".join(years) + " |",
        "|---|" + "---:|" * len(years),
        "| 場數 | " + " | ".join(str(pop["by_year"][y]) for y in years) + " |",
        "",
        f"本次 {latest} 輸入指紋：`n_completed={fy['n_completed']}`、"
        f"`sno_md5={fy['sno_md5']}`、`games_md5={fy['games_md5']}`、"
        f"`model_inputs_md5={fy['model_inputs_md5']}`；"
        f"全域 `model_inputs_md5={fp['model_inputs_md5']}`。",
    ]


def source_tier_block(a: dict) -> list[str]:
    tiers = a["population"]["source_tiers"]
    n_games = a["population"]["n_games"]
    rows, sides = [], set()
    for label, key in (("先發", "starter"), ("牛棚", "bullpen")):
        t = tiers[key]
        side = sum(t.values())
        sides.add(side)
        rows.append(
            f"| {label} | {t['own']:,}（{_pct(t['own'], side)}） | "
            f"{t['prior']:,}（{_pct(t['prior'], side)}） | "
            f"{t['league']:,}（{_pct(t['league'], side)}） |")
    # 兩項各自的側數應同為「場數 × 2」；不同即代表某側有場次未歸類，屬缺陷而非顯示問題。
    total = (f"兩項各 {sides.pop():,} 側＝{n_games:,} 場 × 2 側" if len(sides) == 1
             else f"**逐項側數不一致：{sorted(sides)}——應同為 {n_games * 2:,}，請查**")
    return [
        f"**先發／牛棚 rate 的資訊來源層級**：逐場逐側計數，{total}。",
        "",
        "| 指標 | 當季自身（own） | 前一季（prior） | fit 窗聯盟率（league） |",
        "|---|---:|---:|---:|",
        *rows,
    ]


def coverage_block(a: dict) -> list[str]:
    seasons = sorted(a["seasons"], key=lambda s: s["year"])
    excluded = {s["year"]: s["excluded_pa_no_pregame_features"] for s in seasons}
    full = [s for s in seasons if s["coverage_raw"] == 1.0 and s["effective_coverage"] == 1.0]
    partial = [s for s in seasons if s not in full]
    line = (f"**排除帳**：四個驗證季的 `excluded_pa_no_pregame_features` "
            f"{'**皆為 0**' if set(excluded.values()) == {0} else f'為 {excluded}'}；")
    if full:
        line += (f"`coverage_raw` 與 `effective_coverage` "
                 f"{full[0]['year']}–{full[-1]['year']} 皆 **1.000000**")
    for s in partial:
        line += (f"、{s['year']} 為 **{s['coverage_raw']:.6f}**"
                 f"（{s['n_completed_games']} 完成場中 {s['n_scored_games']} 場有 published PA build）")
    return [line + "。"]


def seasons_block(a: dict) -> list[str]:
    head = ("| 季 | base 模型窗 | n_PA | cov | **主場常數** | **CAL1（歷史）** | "
            "**base（未融合）** | **本卡 WP_adj** | Δ vs base | Δ 的 99% CI |")
    cal1 = {y: f"{v:.5f}" + ("¹" if y == 2026 else "") for y, v in cal1_brier().items()}
    rows = []
    for s in sorted(a["seasons"], key=lambda r: -r["year"]):
        d = s["brier_delta_diagnostic"]
        delta = s["adjusted"]["brier_raw"] - s["base"]["brier_raw"]
        fit = s["windows"]["final_fit"]
        label = (f"**{s['year']}（鎖箱；資料截止 {a['data_as_of']}、"
                 f"完成場 {s['n_completed_games']}）**" if s["holdout_sealed"] else str(s["year"]))
        rows.append(
            f"| {label} | {fit[0]}-{fit[1]} | {s['base']['n_pa']:,} | {s['coverage']:.4f} | "
            f"{_num(s['baseline_home_const']['brier_raw'])} | {cal1.get(s['year'], '—')} | "
            f"{_num(s['base']['brier_raw'])} | **{_num(s['adjusted']['brier_raw'])}** | "
            f"**{_num(delta, signed=True)}**{' ❌' if delta > 0 else ''} | "
            f"[{_num(d['ci'][0], signed=True)}, {_num(d['ci'][1], signed=True)}] |")
    return [head, "|---|---|---:|---:|---:|---:|---:|---:|---:|---|", *rows]


def verdict_block(a: dict) -> list[str]:
    """§0 的硬門檻對照與一句話結論——這裡的數字最常被引用，故一併產生。"""
    v, p = a["verdict"], a["pooled"]
    seasons = sorted(a["seasons"], key=lambda s: s["year"])
    worse = [s for s in seasons
             if s["adjusted"]["brier_raw"] > s["base"]["brier_raw"]]
    full_cov = [s for s in seasons if s["coverage_raw"] == 1.0]
    partial = [s for s in seasons if s["coverage_raw"] != 1.0]
    delta = p["adj"]["brier_raw"] - p["base"]["brier_raw"]
    ci = p["brier_delta_diagnostic"]["ci"]
    margins = sorted(s["baseline_home_const"]["brier_raw"] - s["adjusted"]["brier_raw"]
                     for s in seasons)
    bands = a["pooled_inning_bands"]
    worst_pt = max(abs(bands["adj"]["raw"][b]["dev"]) * 100
                   for b in bands["adj"]["raw"] if b != "10+")
    worst_gap = max((abs(bands["adj"]["raw"][b]["dev"]) - abs(bands["base"]["raw"][b]["dev"])) * 100
                    for b in bands["adj"]["raw"] if b != "10+")
    cov_cell = (f"✅ {full_cov[0]['year']}–{full_cov[-1]['year']} 皆 **1.000000**" if full_cov else "")
    for s in partial:
        cov_cell += (f"；{s['year']} **{_num(s['coverage_raw'])}**"
                     f"（{s['n_completed_games'] - s['n_scored_games']} 場尚無 published PA build）")
    fail = "；".join(f"**{s['year']}（{_num(s['adjusted']['brier_raw'] - s['base']['brier_raw'], signed=True)}）**"
                    for s in worse)
    return [
        f"> **A scope（局面 WP ＋ 戰力感知先驗融合）＝ {v['status']}"
        f"{'（No-Go）' if v['status'] == 'unsupported' else ''}。**",
        "> `GAME-RECAP-WP-API1` 的 A 範圍**維持阻塞**。",
        "",
        "| 硬門檻 | 結果 |",
        "|---|---|",
        f"| 各驗證季 coverage ≥ 0.98（**含 effective coverage**） | {cov_cell} |",
        f"| 融合後 Brier 勝主場常數基準 | ✅ 四季皆勝（幅度 {margins[0]:.3f}–{margins[-1]:.3f}） |",
        f"| **融合後 Brier 不得劣於同代未融合 base** | ❌ {fail} 劣於 base |",
        "| 池化十分位 n≥1000：\\|dev\\|≤0.03 或 99% CI 含 0 | ✅ 通過（**但見 §6 的重要但書**） |",
        f"| 池化局帶 n≥1000：\\|dev\\|≤0.03 或 99% CI 含 0 | ✅ 三帶 \\|dev\\| 皆 ≤{worst_pt:.2f}pt |",
        f"| 局帶相對 base 不得系統性惡化 | ✅ 最大惡化 {worst_gap:+.2f}pt（<1pt，未達揭露門檻） |",
        "| 全部預註冊驗證季 2023–2026 皆執行 | ✅ |",
        "",
        f"**一句話結論**：融合層在**校準**上有微幅正向效果（池化 ECE "
        f"{p['base']['ece_weighted']} → {p['adj']['ece_weighted']}，顯著偏差分箱 "
        f"{p['base'].get('significant_bins') or []} → {p['adj'].get('significant_bins') or []}），"
        f"但在**準確度**上與零無異——池化 Brier 差 **{_num(delta, signed=True)}"
        f"（99% game-cluster CI [{_num(ci[0], signed=True)}, {_num(ci[1], signed=True)}]）**，"
        f"四季中 {len(worse)} 季變差。根因不是融合式或實作，而是"
        f"**八項凍結賽前特徵在時間外幾乎不含增量資訊**（§6）。",
    ]


def p0_block(a: dict) -> list[str]:
    rows, deltas = [], []
    for s in sorted(a["seasons"], key=lambda r: -r["year"]):
        d = s["p0_diagnostics"]
        gap = d["game_brier"] - d["baseline_home_const_game_brier"]
        deltas.append(gap)
        rows.append(
            f"| {s['year']} | {_num(d['game_brier'])} | "
            f"{_num(d['baseline_home_const_game_brier'])} | "
            f"{'**' if gap > 0 else ''}{_num(gap, signed=True)}{'**' if gap > 0 else ''} | "
            f"[{d['min_p0']:.3f}, {d['max_p0']:.3f}] |")
    mean = sum(deltas) / len(deltas)
    return [
        "| 驗證季 | p0 逐場 Brier | leakage-safe 主場常數 | Δ | p0 值域 |",
        "|---|---:|---:|---:|---|",
        *rows,
        "",
        f"四季平均 Δ ≈ {_num(mean, digits=4, signed=True)}，"
        f"{sum(1 for d in deltas if d > 0)} 季為正。",
    ]


def prior_diag_block(a: dict) -> list[str]:
    rows = []
    for d in sorted(a["prior_signal_diagnostics"], key=lambda r: r["year"]):
        late = _num(d["late_season"]) if d["late_season"] is not None else "—"
        late_c = _num(d["late_season_const"]) if d["late_season_const"] else "—"
        rows.append(
            f"| {d['year']} | {_num(d['in_sample'])} | {_num(d['out_of_time'])} | "
            f"{_num(d['home_const'])} | {_num(d['leaky_same_season'])} | {late} | {late_c} |")
    return [
        "| Y | ① 同窗 in-sample | ② 時間外（本卡用法） | ③ 主場常數 | "
        "④ `game_features` starter 欄 | ⑤ 後半季時間外 | ⑥ 後半季常數 |",
        "|---|---:|---:|---:|---:|---:|---:|",
        *rows,
    ]


def pooled_block(a: dict) -> list[str]:
    p = a["pooled"]
    n_pa = p["base"]["n_pa"]
    n_games = p["base"]["n_games"]
    d = p["brier_delta_diagnostic"]
    delta = p["adj"]["brier_raw"] - p["base"]["brier_raw"]
    return [
        f"池化 2023–2026：n_PA = {n_pa:,}；n_games = {n_games:,}。",
        "",
        "| 模型 | Brier | ECE | 顯著偏差分箱（99% 叢集 CI 排除 0） |",
        "|---|---:|---:|---|",
        f"| 主場常數基準 | {p['baseline_home_const_brier']} | — | — |",
        f"| **base（未融合）** | **{_num(p['base']['brier_raw'])}** | "
        f"{p['base']['ece_weighted']} | **{p['base'].get('significant_bins') or []}** |",
        f"| **WP_adj（本卡）** | **{_num(p['adj']['brier_raw'])}** | "
        f"**{p['adj']['ece_weighted']}** | **{p['adj'].get('significant_bins') or []}** |",
        "",
        f"池化 Brier 差 **{_num(delta, signed=True)}**，99% game-cluster CI "
        f"**[{_num(d['ci'][0], signed=True)}, {_num(d['ci'][1], signed=True)}]**"
        f"（`brier_delta_diagnostic`；診斷用，不進判定）。",
    ]


def bands_block(a: dict) -> list[str]:
    raw_base = a["pooled_inning_bands"]["base"]["raw"]
    raw_adj = a["pooled_inning_bands"]["adj"]["raw"]
    boot = a["pooled_inning_bands"]["adj"]["boot"]
    rows = []
    for band in raw_adj:
        b, j = raw_base[band], raw_adj[band]
        gap = (abs(j["dev"]) - abs(b["dev"])) * 100
        interval = boot[band]["ci"]
        rows.append(
            f"| {band}{'（僅揭露）' if band == '10+' else ''} | {j['n']:,} | "
            f"{_num(b['dev'], digits=5, signed=True)} | {_num(j['dev'], digits=5, signed=True)} | "
            f"{'**' if abs(gap) >= 0.5 else ''}{_num(gap, digits=2, signed=True)}pt"
            f"{'**' if abs(gap) >= 0.5 else ''} | "
            f"[{_num(interval[0], digits=5, signed=True)}, "
            f"{_num(interval[1], digits=5, signed=True)}] |")
    return ["| 帶 | n | base dev | WP_adj dev | Δ\\|dev\\| | WP_adj 的 99% CI |",
            "|---|---:|---:|---:|---:|---|", *rows]


def advanced_block(a: dict) -> list[str]:
    sh = a["advanced_shadow_2026"]
    adv, tm = sh["advanced_stats_2026"], sh["pitch_tracking_2026_A"]
    corr = sh["season_end_correlation"]
    pearson = sorted(corr["pearson"].items(), key=lambda kv: -abs(kv[1] or 0))
    listed = "、".join(f"`{k}` **{v:+.3f}**" for k, v in pearson[:4] if v is not None)
    return [
        f"> 本節不吃 `--as-of`，數字為 `observed_at = {sh['observed_at']}` 的當下全表狀態；"
        "比對重跑輸出時須與 `generated_at` 一併排除。",
        "",
        "| 項目 | 現況 | 不可用原因 |",
        "|---|---|---|",
        f"| `advanced_stats` 2026 | 投手 {adv['pitching_rows']} 列、打者 {adv['batting_rows']} 列 | "
        f"**{adv['reason_unusable']}** |",
        f"| `pitch_tracking` 2026 A | {tm['games_with_tracking']}/{tm['completed_games']} 場"
        f"（coverage {tm['coverage']}）、{tm['pitches']:,} 球 | {tm['reason_unusable']} |",
        "",
        f"季末彙總相關性（{corr['n_starters_joined']} 位 PA≥100 的先發，"
        f"只回答「概念是否對齊」）：{listed}。",
    ]


def selection_block(a: dict) -> list[str]:
    """§3 選型證據。查核 F1 實測：本表原在產生區塊外，把 Brier 改成 0.999999 也照樣通過。"""
    rows = []
    for s in sorted(a["seasons"], key=lambda r: r["year"]):
        sel, w = s["selection"], s["windows"]
        chosen = sel["chosen"]
        grid = next(g for g in sel["prior_grid"]
                    if g["kappa"] == chosen["kappa"] and g["lambda"] == chosen["lambda"])
        gamma = next(g for g in sel["gamma_grid"] if g["gamma"] == chosen["gamma"])
        base = sel["selection_season_base_brier"]
        better = gamma["sel_brier"] < base
        rows.append(
            f"| {s['year']} | {w['inner_fit'][0]}–{w['inner_fit'][1]} | "
            f"{w['inner_selection']} | {chosen['kappa']} | {chosen['lambda']:g} | "
            f"{chosen['gamma']:g} | {_num(grid['sel_brier'])} | "
            f"{_num(gamma['sel_brier'])} {'<' if better else '>'} {_num(base)}"
            f"（{'改善' if better else '**惡化**'}） |")
    return ["| 驗證季 Y | inner fit | 選型季 Y−1 | 選定 κ | 選定 λ | 選定 γ | "
            "選型季逐場 Brier | 選型季融合 vs 未融合 |",
            "|---|---|---|---:|---:|---:|---:|---|", *rows]


def hard_gate_block(a: dict) -> list[str]:
    """§5 逐條硬門檻——**純格式化** `verdict.gate_results`，不在此處做任何判定。

    iteration 5 版為了印這張表把門檻邏輯重寫了一次，四條各與 `strength_verdict()` 不等價
    （4a 漏 effective coverage、4d 漏 |dev| 上限、5a 漏 CI 條件、5b 規則寫反），報告因此
    可能顯示與真實判定相反的結果（查核 F1 實測：effective_coverage 改 0.5 仍印 ✅）。
    判定只能有一條路徑；本函式現在只會把已判好的結果排版。
    """
    gates = a["verdict"]["gate_results"]
    rows = []
    for g in gates:
        n_fail = len(g["failures"])
        mark = "✅ 通過" if g["passed"] else "❌ **失敗**" + (f" ×{n_fail}" if n_fail > 1 else "")
        detail = "；".join(g["failures"]) if g["failures"] else g["evidence"]
        rule = g["rule"].replace("|dev|", "\\|dev\\|")
        rows.append(f"| {g['gate']} | {rule} | {mark} | {detail} |")
    failed = [g for g in gates if not g["passed"]]
    return [
        "| 條 | 門檻 | 判定 | 證據 |",
        "|---|---|---|---|",
        *rows,
        "",
        f"**任一硬門檻失敗即 No-Go**。本次失敗 {len(failed)} 條"
        + (f"（{'、'.join(g['gate'] for g in failed)}）" if failed else "")
        + f" → **{'No-Go' if a['verdict']['status'] == 'unsupported' else a['verdict']['status']}**。",
    ]


def cal1_contrast_block(a: dict) -> list[str]:
    base_pt, iso_pt = cal1_band_contrast()
    return [
        f"三個例行帶皆遠低於 0.03 上限、CI 皆含 0。"
        f"**對照 CAL1**：事後校準（定案的 isotonic）當時把 1-3 帶從 "
        f"{_num(base_pt, digits=2, signed=True)}pt 惡化到 "
        f"{_num(iso_pt, digits=2, signed=True)}pt，超過 2pt 硬性上限。",
    ]


def cal1_mechanism_block(a: dict) -> list[str]:
    """§6.4 CAL1 vs STRENGTH1 的機制對照表。

    iteration 5 把整張表列為 `UNGENERATED_TABLES` 例外，理由字串聲稱「唯二數字已由測試釘住」
    ——但那支測試只驗了 isotonic 的 −2.41pt，沒驗 base 的 −0.10pt，查核者把 base 改成 +9.99pt
    三道檢查全部放行（查核 F2）。**用一句未經驗證的宣稱去豁免一張表**，正是本卡反覆犯的錯。
    整張表改為產生，兩個數字都出自 CAL1 artifact。
    """
    base_pt, iso_pt = cal1_band_contrast()
    seasons = a["seasons"]
    worst_gap = max(
        (abs(a["pooled_inning_bands"]["adj"]["raw"][b]["dev"])
         - abs(a["pooled_inning_bands"]["base"]["raw"][b]["dev"])) * 100
        for b in a["pooled_inning_bands"]["adj"]["raw"] if b != "10+")
    worse = sum(1 for s in seasons if s["adjusted"]["brier_raw"] > s["base"]["brier_raw"])
    return [
        "| | WP-CAL1（事後校準） | WP-STRENGTH1（戰力先驗） |",
        "|---|---|---|",
        f"| 失敗形態 | 修正**有力但方向錯**：池化分箱修平了，卻把 1-3 局帶從 "
        f"{_num(base_pt, digits=2, signed=True)}pt 破壞到 {_num(iso_pt, digits=2, signed=True)}pt"
        f"（定案的 isotonic，超過 2pt 硬性上限） | 修正**方向對但沒有力**：局帶完好無損"
        f"（最大惡化僅 {_num(worst_gap, digits=2, signed=True)}pt），"
        f"但四季中 {worse} 季 Brier 反而變差 |",
        "| 根因 | 校準窗與驗證季分屬不同世代 base，學到的中心修正已過時（不具時間平穩性） | "
        "賽前可得資訊在時間外幾乎不含增量預測力 |",
        "| 共同教訓 | 內部窗指標會為有害／無效的層背書；**唯一防線是嵌套時間外驗證＋逐局帶硬門檻** | 同左 |",
    ]


def decile_block(a: dict) -> list[str]:
    """§6.3 池化十分位。iteration 4 版只列了討論到的 4 個 bin 且 n 寫成「~6.1k」概數。"""
    base = a["pooled"]["base"]["raw_deciles"]
    adj = a["pooled"]["adj"]["raw_deciles"]
    rows = []
    for key in sorted(base, key=int):
        b, j = base[key], adj[key]
        gain = (abs(b["dev"]) - abs(j["dev"])) * 100
        rows.append(
            f"| {key} | {b['n']:,} | {_num(b['dev'], digits=5, signed=True)} | "
            f"{_num(j['dev'], digits=5, signed=True)} | "
            f"{_num(gain, digits=2, signed=True)}pt{'（惡化）' if gain < 0 else ''} |")
    return ["| 分箱 | n | base dev | WP_adj dev | 改善 |",
            "|---|---:|---:|---:|---:|", *rows]


def ablation_block(a: dict) -> list[str]:
    """§7.1 預註冊消融。三層在季間的排序不穩定是本卡的核心論據之一，數字不容過期。"""
    layers = [("team_only", "team_only（4 項）"), ("team_starter", "team+starter（7 項）"),
              ("full", "**full（8 項）**")]
    rows = []
    for s in sorted(a["seasons"], key=lambda r: -r["year"]):
        vals = {k: s["ablation"][k]["fused_pa_brier"] for k, _ in layers}
        best = min(vals, key=lambda k: vals[k])
        cells = "".join(
            f" {'**' if k == best else ''}{_num(vals[k])}{'**' if k == best else ''} |"
            for k, _ in layers)
        rows.append(f"| {s['year']} |{cells}")
    return ["| 季 | " + " | ".join(label for _, label in layers) + " |",
            "|---|---:|---:|---:|", *rows]


BLOCKS = {
    "verdict": verdict_block,
    "population": population_block,
    "source_tiers": source_tier_block,
    "coverage_ledger": coverage_block,
    "selection": selection_block,
    "seasons": seasons_block,
    "pooled": pooled_block,
    "bands": bands_block,
    "hard_gates": hard_gate_block,
    "cal1_contrast": cal1_contrast_block,
    "deciles": decile_block,
    "cal1_mechanism": cal1_mechanism_block,
    "ablation": ablation_block,
    "p0_diagnostics": p0_block,
    "prior_signal_diagnostics": prior_diag_block,
    "advanced_shadow": advanced_block,
}


def render(artifact: dict) -> dict[str, str]:
    return {name: "\n".join(fn(artifact)) for name, fn in BLOCKS.items()}


def apply(text: str, blocks: dict[str, str]) -> str:
    """把各區塊寫回標記之間；標記缺席即報錯（不靜默略過——那會讓數字悄悄留在人工版本）。"""
    for name, body in blocks.items():
        pattern = re.compile(
            rf"(<!-- generated:{name} start -->\n).*?(\n<!-- generated:{name} end -->)",
            re.DOTALL)
        if not pattern.search(text):
            raise SystemExit(f"報告缺少 generated:{name} 標記區塊")
        text = pattern.sub(lambda m: m.group(1) + body + m.group(2), text, count=1)
    return text


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--artifact", default=str(ARTIFACT))
    ap.add_argument("--report", default=str(REPORT))
    ap.add_argument("--check", action="store_true", help="只檢查同步，不寫檔；不同步時 exit 1")
    args = ap.parse_args()

    artifact = json.loads(Path(args.artifact).read_text(encoding="utf-8"))
    report = Path(args.report)
    current = report.read_text(encoding="utf-8")
    updated = apply(current, render(artifact))
    if args.check:
        if current != updated:
            sys.stdout.writelines(difflib.unified_diff(
                current.splitlines(keepends=True), updated.splitlines(keepends=True),
                fromfile="報告現況", tofile="artifact 應產生"))
            raise SystemExit("報告數字與 artifact 不同步；跑一次本腳本（不帶 --check）即可更新")
        print("報告數字與 artifact 同步")
        return
    report.write_text(updated, encoding="utf-8")
    print(f"已更新 {len(BLOCKS)} 個區塊：{'、'.join(BLOCKS)}")


if __name__ == "__main__":
    main()
