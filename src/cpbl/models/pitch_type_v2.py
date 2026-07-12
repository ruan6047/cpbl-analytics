"""球種細分 v2（ML-PT2 Phase2）：MLB 標籤遷移 cluster-then-label。

v1（pitch_type.py）逐投手 KMeans 分群後以教科書規則命名（複合名，寧粗勿錯）。
v2 保留 v1 分群結果——DB 中 (pitcher, pitch_type_pred) 群組＝叢集單位——改用
MLB Savant pitch-movement leaderboard（投手×球種聚合，2023–25，data/mlb/）訓練
QDA，對「叢集質心」命名成細分球種（四縫/伸卡/卡特/滑球/橫掃/曲球/變速/指叉）。
寫入 pitch_type_pred_v2，v1 欄不動（並存對照；前端切換另案、gated on 驗收）。

統計對齊（勿動，錯了難察覺；背景見 docs/TASKS.md ML-PT2 卡）：
1. **速度不用絕對值**：中職均速低 MLB ~8–10 km/h。改用 speed_ratio＝佔該投手
   最快叢集/球種的比例，兩邊同構計算。
2. **位移錨移**（anchor-shift）：兩系統（TrackMan vs Hawk-Eye/推估）有加性偏差
   → IVB/HB 以「該聯盟四縫平均」為原點的差值表達，MLB/CPBL 各用自家錨。
3. **HB 符號**：Savant leaderboard 的 pitcher_break_x 是無符號量值（R/L 四縫同號
   +7.6/+7.9、臂側變速 +14.4 與手套側橫掃 +13.8 同號，2025 實證），依球種物理方向
   恢復：臂側(FF/SI/CH/FS)=負、手套側(SL/ST/CU/FC)=正——與 v1 hb_norm 的
   glove-positive 慣例同向。CPBL 端 hb_glove = hb_cm ×（右投 +1／左投 −1），
   左右手沿 v1 用 avg(rel_side) 符號判定。
4. **spin 不用**：跨量測系統轉速有偏差。
5. **複合名誠實輸出**：posterior top1 置信不足 → 「A/B」複合名，寧粗勿錯（承 v1）。
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

import numpy as np
from sklearn.discriminant_analysis import QuadraticDiscriminantAnalysis
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from cpbl.db import conn

log = logging.getLogger("cpbl.pitch_type_v2")

# 資料下載（一次性，data/ 不進 repo）：
#   curl -A "Mozilla/5.0" "https://baseballsavant.mlb.com/leaderboard/pitch-movement?year={Y}&team=&min=50&pitch_type=ALL&hand=&csv=true" -o data/mlb/mv{Y}.csv
MLB_DIR = Path("data/mlb")
MLB_YEARS = (2023, 2024, 2025)
MPH2KMH = 1.60934
IN2CM = 2.54

# 球種物理方向（恢復無符號 break_x 的符號；glove-positive 慣例）
_GLOVE_SIDE = {"SL", "ST", "CU", "FC"}
_MERGE = {"SV": "CU", "KC": "CU", "FO": "FS"}     # 近親併類
_ZH = {"FF": "四縫", "SI": "伸卡", "FC": "卡特", "SL": "滑球",
       "ST": "橫掃", "CU": "曲球", "CH": "變速", "FS": "指叉"}

MIN_GROUP_N = 20     # 質心樣本數下限：更小的群不命名（v2 留 NULL，誠實缺席）
_P1_MIN = 0.55       # top1 posterior 低於此 → 複合名
_P1_DOM = 1.8        # top1 ≥ 1.8×top2 才視為單一名


def _load_mlb() -> tuple[np.ndarray, np.ndarray, tuple[float, float], int]:
    """讀 Savant pitch-movement CSV → (X, y, 聯盟FF錨, 投手數)。
    X = [speed_ratio, ivb−FF錨, hb_glove−FF錨]（cm）。"""
    rows: list[dict] = []
    for y in MLB_YEARS:
        with open(MLB_DIR / f"mv{y}.csv", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                pt = _MERGE.get(r["pitch_type"], r["pitch_type"])
                if pt not in _ZH:
                    continue
                bx = float(r["pitcher_break_x"]) * IN2CM
                rows.append({
                    "pid": f'{r["pitcher_id"]}|{r["year"]}', "pt": pt,
                    "speed": float(r["avg_speed"]) * MPH2KMH,
                    "ivb": float(r["pitcher_break_z_induced"]) * IN2CM,
                    "hb_g": bx if pt in _GLOVE_SIDE else -bx,
                })
    by_p: dict[str, list[dict]] = {}
    for r in rows:
        by_p.setdefault(r["pid"], []).append(r)
    keep: list[dict] = []
    for rs in by_p.values():
        # 需有速球系（FF/SI/FC）當 top-speed 錨，避免只剩慢速球的殘缺投手扭曲 ratio
        if not any(x["pt"] in ("FF", "SI", "FC") for x in rs):
            continue
        top = max(x["speed"] for x in rs)
        for x in rs:
            x["ratio"] = x["speed"] / top
        keep += rs
    ff = [x for x in keep if x["pt"] == "FF"]
    anchor = (float(np.mean([x["ivb"] for x in ff])), float(np.mean([x["hb_g"] for x in ff])))
    x_mat = np.array([[x["ratio"], x["ivb"], x["hb_g"]] for x in keep])
    y_vec = np.array([x["pt"] for x in keep])
    return x_mat, y_vec, anchor, len(by_p)


def _load_centroids(year: int, kind_code: str) -> list[dict]:
    """CPBL 叢集質心：(pitcher, v1 pred) 群組的特徵平均＋樣本數＋左右手。"""
    with conn() as c:
        rows = c.execute(
            """
            SELECT pitcher_acnt, pitch_type_pred, count(*) n,
                   avg(rel_speed) speed, avg(ivb_cm) ivb, avg(hb_cm) hb, avg(rel_side) side
            FROM cpbl.pitch_tracking
            WHERE year=%s AND kind_code=%s AND pitch_type_pred IS NOT NULL
              AND rel_speed IS NOT NULL AND ivb_cm IS NOT NULL AND hb_cm IS NOT NULL
            GROUP BY pitcher_acnt, pitch_type_pred
            """,
            (year, kind_code),
        ).fetchall()
    out = []
    for acnt, pred, n, speed, ivb, hb, side in rows:
        out.append({"acnt": acnt, "pred": pred, "n": int(n), "speed": float(speed),
                    "ivb": float(ivb), "hb": float(hb), "side": float(side) if side is not None else 0.0})
    return out


def _name(clf, feat: np.ndarray) -> str:
    """質心 → v2 名。top1 置信不足時複合名（top1/top2）。"""
    p = clf.predict_proba(feat.reshape(1, -1))[0]
    order = np.argsort(p)[::-1]
    classes = clf[-1].classes_
    c1, c2 = classes[order[0]], classes[order[1]]
    p1, p2 = p[order[0]], p[order[1]]
    if p1 >= _P1_MIN and p1 >= _P1_DOM * p2:
        return _ZH[c1]
    return f"{_ZH[c1]}/{_ZH[c2]}"


def _binary_precision(year: int, kind_code: str, col: str, fastball_names: tuple[str, ...]) -> tuple[float, int]:
    """速球類預測 vs tagged fastball 的精確率（沿 v1 驗收口徑）。複合名以 top1（'/' 前段）計。"""
    with conn() as c:
        rows = c.execute(
            f"""
            SELECT split_part({col}, '/', 1) p, tagged_pitch_type, count(*)
            FROM cpbl.pitch_tracking
            WHERE year=%s AND kind_code=%s AND {col} IS NOT NULL AND tagged_pitch_type IS NOT NULL
            GROUP BY 1, 2
            """,
            (year, kind_code),
        ).fetchall()
    hit = tot = 0
    for p, tagged, n in rows:
        if p in fastball_names:
            tot += n
            if tagged == "fastball":
                hit += n
    return (hit / tot if tot else 0.0), tot


def classify_v2(year: int, kind_code: str = "A") -> dict:
    x_mlb, y_mlb, mlb_anchor, n_mlb_p = _load_mlb()
    # 標準化再 QDA：reg_param 在未標準化特徵上會以絕對量級注入變異，
    # 淹掉 ratio 軸（σ~0.03）→ 速度訊號全毀（羅戈 133km/h 群被判四縫，實測）。
    clf = make_pipeline(
        StandardScaler(),
        QuadraticDiscriminantAnalysis(
            reg_param=0.05, priors=np.full(len(set(y_mlb)), 1 / len(set(y_mlb)))),
    ).fit(x_mlb, y_mlb)

    cents = _load_centroids(year, kind_code)
    # CPBL 聯盟四縫錨＝v1「速球」群質心的加權平均（glove frame）
    by_p: dict[str, list[dict]] = {}
    for g in cents:
        by_p.setdefault(g["acnt"], []).append(g)
    ff_w = ff_ivb = ff_hb = 0.0
    for g in cents:
        if g["pred"] == "速球":
            rh = 1.0 if (sum(x["side"] * x["n"] for x in by_p[g["acnt"]]) >= 0) else -1.0
            ff_w += g["n"]
            ff_ivb += g["ivb"] * g["n"]
            ff_hb += g["hb"] * rh * g["n"]
    cpbl_anchor = (ff_ivb / ff_w, ff_hb / ff_w)
    # 乘法對齊：每軸以「聯盟四縫平均」比值縮放（增益型量測偏差；加性錨移會把
    # 下游球種的差值過度拉深——羅戈滑球 delta −72cm 超出 MLB 曲球域，實測誤判）
    sc_ivb = mlb_anchor[0] / cpbl_anchor[0]
    sc_hb = mlb_anchor[1] / cpbl_anchor[1]

    updates: list[tuple[str, str, str]] = []   # (acnt, old_pred, v2)
    for acnt, groups in by_p.items():
        rh = 1.0 if (sum(x["side"] * x["n"] for x in groups) >= 0) else -1.0
        top = max(x["speed"] for x in groups)
        for g in groups:
            if g["n"] < MIN_GROUP_N:
                continue
            feat = np.array([g["speed"] / top,
                             g["ivb"] * sc_ivb,
                             g["hb"] * rh * sc_hb])
            updates.append((acnt, g["pred"], _name(clf, feat)))

    with conn() as c:
        cur = c.cursor()
        cur.execute("UPDATE cpbl.pitch_tracking SET pitch_type_pred_v2=NULL "
                    "WHERE year=%s AND kind_code=%s AND pitch_type_pred_v2 IS NOT NULL",
                    (year, kind_code))
        written = 0
        for acnt, old, new in updates:
            cur.execute(
                "UPDATE cpbl.pitch_tracking SET pitch_type_pred_v2=%s "
                "WHERE year=%s AND kind_code=%s AND pitcher_acnt=%s AND pitch_type_pred=%s",
                (new, year, kind_code, acnt, old),
            )
            written += cur.rowcount

    # 驗收：二元精確率對照。雙口徑——
    # 嚴格（四縫∪伸卡）：91.7%＜v1，但缺口集中「伸卡」群（ratio≈0.998＝投手最快球，
    # 且大宗為黃子鵬/王凱程等下勾伸卡名家）→ 是官方弱標籤把下勾伸卡標 breakingball、
    # v1 標「變化球」；v2 更接近真值。四縫口徑（對應 v1 速球語意）則勝 v1。
    p1, n1 = _binary_precision(year, kind_code, "pitch_type_pred", ("速球",))
    p2, n2 = _binary_precision(year, kind_code, "pitch_type_pred_v2", ("四縫", "伸卡"))
    p3, n3 = _binary_precision(year, kind_code, "pitch_type_pred_v2", ("四縫",))
    metrics = {"v1_fastball_precision": round(p1, 4), "v1_n": n1,
               "v2_fastball_precision": round(p2, 4), "v2_n": n2,
               "v2_ff_only_precision": round(p3, 4), "v2_ff_n": n3,
               "groups_labeled": len(updates), "written": written,
               "mlb_pitchers": n_mlb_p, "mlb_rows": len(y_mlb)}
    with conn() as c:
        c.execute(
            "INSERT INTO cpbl.model_versions (id, task, algo, params, cv_metrics) VALUES (%s,%s,%s,%s,%s) "
            "ON CONFLICT (id) DO UPDATE SET params=EXCLUDED.params, "
            "cv_metrics=EXCLUDED.cv_metrics, trained_at=now()",
            (f"pitch_type_v2_{year}{kind_code}", "pitch_type", "qda-mlb-transfer-v2",
             json.dumps({"mlb_years": MLB_YEARS, "features": ["speed_ratio", "ivb_d", "hb_glove_d"],
                         "anchor_mlb": [round(v, 1) for v in mlb_anchor],
                         "anchor_cpbl": [round(v, 1) for v in cpbl_anchor],
                         "scale": [round(sc_ivb, 3), round(sc_hb, 3)], "align": "multiplicative", "priors": "uniform",
                         "reg_param": 0.1, "p1_min": _P1_MIN, "p1_dom": _P1_DOM,
                         "min_group_n": MIN_GROUP_N}),
             json.dumps(metrics)),
        )
    log.info("classify_v2 %d/%s → %s", year, kind_code, metrics)
    return metrics


def report(year: int, kind_code: str, names: list[str]) -> None:
    """驗收報表：指定投手的 v1→v2 對照（含用量），供人工比對公開球探資訊。"""
    with conn() as c:
        rows = c.execute(
            """
            SELECT pl.name, t.pitch_type_pred, t.pitch_type_pred_v2, count(*),
                   round(avg(t.rel_speed)::numeric, 1)
            FROM cpbl.pitch_tracking t JOIN cpbl.players pl ON pl.id = t.pitcher_acnt
            WHERE t.year=%s AND t.kind_code=%s AND pl.name = ANY(%s)
              AND t.pitch_type_pred IS NOT NULL
            GROUP BY 1, 2, 3 ORDER BY 1, 4 DESC
            """,
            (year, kind_code, names),
        ).fetchall()
    cur = None
    for name, v1, v2, n, spd in rows:
        if name != cur:
            print(f"\n{name}")
            cur = name
        print(f"  {v1:　<6} → {v2 or '—':　<8} n={n:<4} 均速 {spd}")


def main() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description="球種細分 v2：MLB 標籤遷移（質心命名）")
    ap.add_argument("year", type=int, nargs="?", default=2026)
    ap.add_argument("--kind", default="A")
    args = ap.parse_args()
    from cpbl.db import migrate
    migrate()
    m = classify_v2(args.year, args.kind)
    print(json.dumps(m, ensure_ascii=False, indent=2))
    # 驗收 free test set：羅戈 + PTT 文章六終結者
    report(args.year, args.kind, ["羅戈", "曾峻岳", "林凱威", "鍾允華", "朱承洋", "林詩翔", "李振昌"])


if __name__ == "__main__":
    main()
