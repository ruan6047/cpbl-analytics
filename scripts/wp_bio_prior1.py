"""ML-WP-BIO-PRIOR1：WP 賽前先驗 bio 方向研究 spike（唯讀；協定見預註冊 spec）。

協定唯一來源：`docs/research/ML-WP-BIO-PRIOR1_SPEC.md`（先於本檔 commit 凍結）。
fit 2018..Y−1 → 只評 Y（Y=2023–2026）；L2 logistic λ=100 一組；七項特徵凍結
（隊伍四項沿 STRENGTH1 loader＋bio 三項：年紀差／身分差／年資差）。
判準三項（池化 Brier 勝主場常數／99% 逐場 bootstrap CI 排除 0／2026 不得顯著反向）
同時成立才過關。DB 全程唯讀（本檔僅 SELECT）。

執行（host 即可，無 LightGBM 相依）::

    uv run python scripts/wp_bio_prior1.py --out /path/to/scratch.json   # scratch
    uv run python scripts/wp_bio_prior1.py                               # 定稿 artifact
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

# ───────────────────────── 凍結常數（spec §1/§6；不得執行期改動） ─────────────────────────
CARD = "ML-WP-BIO-PRIOR1"
SPEC = "docs/research/ML-WP-BIO-PRIOR1_SPEC.md"
AS_OF = date(2026, 7, 27)          # 與 STRENGTH1 artifact data_as_of 相同（母體可對帳）
FIT_FIRST = 2018
VAL_YEARS = (2023, 2024, 2025, 2026)
LAMBDA = 100.0                     # 一組，不掃網格（spec §1）
BOOT_REPS = 10000
BOOT_CI = 0.99
SEED = 20260727                    # 池化；逐年診斷 = SEED + Y（spec §6）
KIND = "A"

FEATURE_KEYS: tuple[str, ...] = (
    "prior_winpct_diff",       # 隊伍四項：沿 STRENGTH1 GameRow.team_feats
    "winrate_diff",
    "run_margin_diff",
    "rest_days_diff",
    "starter_age_diff",        # bio 三項（spec §2–§5）
    "starter_import_diff",
    "starter_seniority_diff",
)

# 身分二值化（spec §3；canonical classify 分類碼 → 外籍職業補強池旗標）
IMPORT_FLAG = {"import": 1, "loree": 1, "local": 0, "nagata": 0}


# ───────────────────────── 純函式（單元測試對象） ─────────────────────────
def age_years(game_date: date, birthday: date | None) -> float | None:
    """年齡（年）＝ (game_date − birthday).days / 365.25；缺生日 → None（交由填補）。"""
    if birthday is None:
        return None
    return (game_date - birthday).days / 365.25


def import_flag(cls: str) -> int:
    """spec §3 凍結二值化：{import, loree} → 1；{local, nagata} → 0。"""
    return IMPORT_FLAG[cls]


def seniority(game_year: int, ps_years: Sequence[int]) -> int:
    """年資＝ game_year − min(嚴格早於比賽年的 pitching_seasons 年份)；無 → 0（spec §4）。"""
    prior = [y for y in ps_years if y < game_year]
    return game_year - min(prior) if prior else 0


def neutral_fill_mean(ages: Sequence[float]) -> float:
    """fit 窗非缺值先發席次年齡均值（per-slot 逐場計；spec §5）。"""
    if not ages:
        raise ValueError("fit 窗無非缺值先發席次，無法定義中性填補值")
    return sum(ages) / len(ages)


def bio_diffs(home: tuple[float | None, str, int], away: tuple[float | None, str, int],
              fill_age: float) -> dict[str, float]:
    """bio 三項（主 − 客）；缺生日側年齡以 fill_age 中性填補（spec §5）。"""
    (h_age, h_cls, h_sen), (a_age, a_cls, a_sen) = home, away
    return {
        "starter_age_diff": (h_age if h_age is not None else fill_age)
                            - (a_age if a_age is not None else fill_age),
        "starter_import_diff": float(import_flag(h_cls) - import_flag(a_cls)),
        "starter_seniority_diff": float(h_sen - a_sen),
    }


def percentile_ci(draws: list[float], ci: float) -> list[float]:
    """倉內慣例 percentile 索引法：sorted[int(q*(n−1))]（spec §6）。"""
    ds = sorted(draws)
    n = len(ds)
    lo_q, hi_q = (1 - ci) / 2, 1 - (1 - ci) / 2
    return [ds[int(lo_q * (n - 1))], ds[int(hi_q * (n - 1))]]


def paired_bootstrap(deltas: Sequence[float], *, reps: int = BOOT_REPS,
                     ci: float = BOOT_CI, seed: int = SEED) -> dict:
    """逐場配對 Δ 的 game-level bootstrap：重抽場、取平均（spec §6）。

    回傳未捨入 point / ci / se —— 判準直接讀未捨入值，顯示層才捨入。
    """
    point = sum(deltas) / len(deltas)
    rng = random.Random(seed)
    draws = []
    for _ in range(reps):
        pick = rng.choices(deltas, k=len(deltas))
        draws.append(sum(pick) / len(pick))
    mean = sum(draws) / len(draws)
    se = (sum((d - mean) ** 2 for d in draws) / max(len(draws) - 1, 1)) ** 0.5
    return {"point": point, "ci": percentile_ci(draws, ci), "se": se,
            "reps": reps, "seed": seed}


def brier(preds: Sequence[float], ys: Sequence[float]) -> float:
    return sum((p - y) ** 2 for p, y in zip(preds, ys, strict=True)) / len(preds)


# ───────────────────────── 資料載入（唯讀 SELECT） ─────────────────────────
def load_bio_maps(cur, pids: Sequence[str]) -> tuple[dict[str, tuple[date | None, str]], dict[str, list[int]]]:
    """先發 pid → (birthday, canonical 身分碼)；pid → pitching_seasons 年份表。"""
    from cpbl.imports import classify

    cur.execute("SELECT id, birthday, country FROM cpbl.players WHERE id = ANY(%s)",
                (list(pids),))
    bio = {pid: (bday, classify(pid, country)) for pid, bday, country in cur.fetchall()}
    missing = [p for p in pids if p not in bio]
    if missing:
        raise ValueError(f"players 缺 {len(missing)} 位先發列（母體對帳前提破裂）: {missing[:5]}")
    cur.execute("SELECT player_id, array_agg(DISTINCT year) FROM cpbl.pitching_seasons "
                "WHERE player_id = ANY(%s) GROUP BY player_id", (list(pids),))
    ps_years = {pid: sorted(ys) for pid, ys in cur.fetchall()}
    return bio, ps_years


def load_starters(cur) -> dict[tuple[int, int], tuple[str, str]]:
    """(year, game_sno) → (home_starter_id, away_starter_id)；與 loader 同母體條件。"""
    cur.execute(
        "SELECT year, game_sno, home_starter_id, away_starter_id FROM cpbl.games "
        "WHERE kind_code=%s AND year BETWEEN %s AND %s "
        "  AND home_score + away_score > 0 AND game_date <= %s",
        (KIND, FIT_FIRST, VAL_YEARS[-1], AS_OF))
    return {(y, sno): (h, a) for y, sno, h, a in cur.fetchall()}


def completed_counts(cur) -> dict[int, int]:
    """母體對帳：逐年完成場數（獨立 SQL，與 loader 條件同文）。"""
    cur.execute(
        "SELECT year, count(*) FROM cpbl.games "
        "WHERE kind_code=%s AND year BETWEEN %s AND %s "
        "  AND home_score + away_score > 0 AND game_date <= %s GROUP BY year",
        (KIND, FIT_FIRST, VAL_YEARS[-1], AS_OF))
    return dict(cur.fetchall())


# ───────────────────────── 主流程 ─────────────────────────
def run(out_path: Path) -> dict:
    from cpbl.db import conn
    from cpbl.models.winprob_strength import fit_logistic_l2, home_rate_exact, load_game_rows

    with conn() as c:
        cur = c.cursor()
        rows = load_game_rows(cur, FIT_FIRST, VAL_YEARS[-1], as_of=AS_OF)
        starters = load_starters(cur)
        pids = sorted({p for pair in starters.values() for p in pair})
        bio, ps_years = load_bio_maps(cur, pids)
        sql_counts = completed_counts(cur)
        home_consts = {y: home_rate_exact(cur, KIND, FIT_FIRST, y - 1, AS_OF)
                       for y in VAL_YEARS}

    # 母體對帳（spec §7）：loader 場數 vs 獨立 SQL 場數逐年相等，先發鍵完備
    loaded = defaultdict(int)
    for r in rows:
        loaded[r.year] += 1
        assert (r.year, r.game_sno) in starters, f"缺先發鍵 {(r.year, r.game_sno)}"
    assert dict(loaded) == sql_counts, f"母體對帳失敗: {dict(loaded)} != {sql_counts}"

    def side(pid: str, game_year: int) -> tuple[date | None, str, int]:
        bday, cls = bio[pid]
        return bday, cls, seniority(game_year, ps_years.get(pid, ()))

    # 逐年缺值／身分分布揭露（spec §5/§7）
    disclosure: dict[int, dict] = {}
    for r in rows:
        d = disclosure.setdefault(r.year, {"games": 0, "missing_birthday_games": 0,
                                           "missing_birthday_slots": 0,
                                           "identity_slots": defaultdict(int)})
        d["games"] += 1
        h_pid, a_pid = starters[(r.year, r.game_sno)]
        n_missing = sum(1 for p in (h_pid, a_pid) if bio[p][0] is None)
        d["missing_birthday_slots"] += n_missing
        d["missing_birthday_games"] += 1 if n_missing else 0
        for p in (h_pid, a_pid):
            d["identity_slots"][bio[p][1]] += 1

    def features(r, fill_age: float) -> dict[str, float]:
        h_pid, a_pid = starters[(r.year, r.game_sno)]
        h_bday, h_cls, h_sen = side(h_pid, r.year)
        a_bday, a_cls, a_sen = side(a_pid, r.year)
        return {**r.team_feats,
                **bio_diffs((age_years(r.game_date, h_bday), h_cls, h_sen),
                            (age_years(r.game_date, a_bday), a_cls, a_sen), fill_age)}

    seasons = []
    pooled_deltas: list[float] = []
    pooled_pm: list[float] = []
    pooled_pc: list[float] = []
    pooled_y: list[float] = []
    for year in VAL_YEARS:
        fit_rows = [r for r in rows if FIT_FIRST <= r.year <= year - 1]
        val_rows = [r for r in rows if r.year == year]
        fill_ages = []
        for r in fit_rows:
            for pid in starters[(r.year, r.game_sno)]:
                a = age_years(r.game_date, bio[pid][0])
                if a is not None:
                    fill_ages.append(a)
        fill = neutral_fill_mean(fill_ages)
        model = fit_logistic_l2([features(r, fill) for r in fit_rows],
                                [r.y for r in fit_rows], keys=FEATURE_KEYS,
                                lam=LAMBDA, kappa=0,
                                fit_years=range(FIT_FIRST, year))
        preds = [model.predict(features(r, fill)) for r in val_rows]
        ys = [r.y for r in val_rows]
        pc = home_consts[year]
        deltas = [(p - y) ** 2 - (pc - y) ** 2 for p, y in zip(preds, ys, strict=True)]
        boot = paired_bootstrap(deltas, seed=SEED + year)
        seasons.append({
            "year": year, "fit_window": [FIT_FIRST, year - 1],
            "n_fit_games": len(fit_rows), "n_val_games": len(val_rows),
            "home_const_p": round(pc, 6), "age_fill": round(fill, 4),
            "brier_model": round(brier(preds, ys), 6),
            "brier_home_const": round(brier([pc] * len(ys), ys), 6),
            "delta_brier": round(boot["point"], 6),
            "delta_ci99": [round(v, 6) for v in boot["ci"]],
            "delta_se": round(boot["se"], 6), "boot_seed": boot["seed"],
            "model": model.params(),
        })
        pooled_deltas.extend(deltas)
        pooled_pm.extend(preds)
        pooled_pc.extend([pc] * len(ys))
        pooled_y.extend(ys)

    pooled_boot = paired_bootstrap(pooled_deltas, seed=SEED)
    pooled = {
        "n_games": len(pooled_deltas),
        "brier_model": brier(pooled_pm, pooled_y),
        "brier_home_const": brier(pooled_pc, pooled_y),
        "delta_brier": pooled_boot["point"],
        "delta_ci99": pooled_boot["ci"],
        "delta_se": pooled_boot["se"],
        "boot_seed": pooled_boot["seed"], "boot_reps": pooled_boot["reps"],
    }

    # 判準（spec §6；未捨入值）
    c1 = pooled["brier_model"] < pooled["brier_home_const"]
    c2 = pooled["delta_ci99"][1] < 0.0
    s2026 = next(s for s in seasons if s["year"] == 2026)
    val_2026_deltas = pooled_deltas[-s2026["n_val_games"]:]  # VAL_YEARS 升冪 → 尾端即 2026
    boot_2026 = paired_bootstrap(val_2026_deltas, seed=SEED + 2026)
    d2026_point, ci_2026 = boot_2026["point"], boot_2026["ci"]
    sig_adverse_2026 = d2026_point > 0.0 and ci_2026[0] > 0.0
    c3 = not sig_adverse_2026
    verdict = "Go" if (c1 and c2 and c3) else "No-Go"

    # STRENGTH1 八項 p0 對照（spec §7；直接引 artifact，不重跑）
    ref_path = Path(__file__).parents[1] / "docs/research/game_recap_wp_strength1_metrics.json"
    ref = json.loads(ref_path.read_text())
    eight = [{"year": d["year"], "n_val_games": d["n_val_games"],
              "brier_p0_out_of_time": d["out_of_time"],
              "brier_home_const": d["home_const"],
              "delta_brier": round(d["out_of_time"] - d["home_const"], 6)}
             for d in ref["prior_signal_diagnostics"]]
    eight_pooled = (sum(d["n_val_games"] * (d["brier_p0_out_of_time"] - d["brier_home_const"])
                        for d in eight) / sum(d["n_val_games"] for d in eight))

    result = {
        "card": CARD, "spec": SPEC, "kind": KIND,
        "data_as_of": AS_OF.isoformat(),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "protocol": {"fit_first": FIT_FIRST, "val_years": list(VAL_YEARS),
                     "lambda": LAMBDA, "boot_reps": BOOT_REPS, "boot_ci": BOOT_CI,
                     "seed_pooled": SEED, "seed_per_year": "seed + year",
                     "feature_keys": list(FEATURE_KEYS),
                     "import_flag_map": IMPORT_FLAG},
        "population": {
            str(y): {"completed_sql": sql_counts[y], "scored_loader": loaded[y],
                     "missing_birthday_games": disclosure[y]["missing_birthday_games"],
                     "missing_birthday_slots": disclosure[y]["missing_birthday_slots"],
                     "identity_slots": dict(disclosure[y]["identity_slots"])}
            for y in sorted(sql_counts)},
        "seasons": seasons,
        "pooled": {k: (round(v, 6) if isinstance(v, float) else
                       [round(x, 6) for x in v] if isinstance(v, list) else v)
                   for k, v in pooled.items()},
        "criteria": {
            "C1_pooled_brier_beats_home_const": {
                "pass": c1, "brier_model": round(pooled["brier_model"], 6),
                "brier_home_const": round(pooled["brier_home_const"], 6)},
            "C2_pooled_ci99_excludes_zero_improving": {
                "pass": c2, "delta": round(pooled["delta_brier"], 6),
                "ci99": [round(v, 6) for v in pooled["delta_ci99"]]},
            "C3_2026_not_significantly_adverse": {
                "pass": c3, "delta_2026": round(d2026_point, 6),
                "ci99_2026": [round(v, 6) for v in ci_2026],
                "significantly_adverse": sig_adverse_2026,
                "directional_warning": d2026_point > 0.0},
        },
        "verdict": verdict,
        "strength1_eight_feature_reference": {
            "seasons": eight, "pooled_delta_brier": round(eight_pooled, 6),
            "source": "docs/research/game_recap_wp_strength1_metrics.json prior_signal_diagnostics"},
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")

    print(f"=== {CARD}（λ={LAMBDA}、七項凍結特徵；判準見 {SPEC}） ===")
    print(f"{'Y':>5} {'n_fit':>6} {'n_val':>6} {'Brier(bio7)':>12} {'Brier(常數)':>12} "
          f"{'Δ':>9} {'99% CI':>22}")
    for s in seasons:
        print(f"{s['year']:>5} {s['n_fit_games']:>6} {s['n_val_games']:>6} "
              f"{s['brier_model']:>12.6f} {s['brier_home_const']:>12.6f} "
              f"{s['delta_brier']:>9.6f} [{s['delta_ci99'][0]:.6f}, {s['delta_ci99'][1]:.6f}]")
    print(f"{'池化':>5} {'':>6} {pooled['n_games']:>6} {pooled['brier_model']:>12.6f} "
          f"{pooled['brier_home_const']:>12.6f} {pooled['delta_brier']:>9.6f} "
          f"[{pooled['delta_ci99'][0]:.6f}, {pooled['delta_ci99'][1]:.6f}]")
    for name, cinfo in result["criteria"].items():
        print(f"  {name}: {'PASS' if cinfo['pass'] else 'FAIL'}")
    print(f"verdict: {verdict}")
    print(f"artifact: {out_path}")
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).parents[1] / "docs/research/ml_wp_bio_prior1_metrics.json")
    run(ap.parse_args().out)


if __name__ == "__main__":
    main()
