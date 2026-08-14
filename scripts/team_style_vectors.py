# LIFECYCLE: oneshot · 卡片一次性產物——不要跑；刪除須需求方裁定（TEAM-STYLE1）
"""TEAM-STYLE1 球隊球風向量計算（唯讀；描述性）。

依 docs/research/TEAM-STYLE1_RESULTS.md §0 預註冊規格計算 7 個描述性風格軸：
季內聯盟 z-score、分半／跨季自相關穩定性、face validity 抽查、母體對帳與 QA。
所有查詢僅 SELECT；產出 JSON artifact 與 stdout markdown 表格（貼入報告用）。

軸計算與 z-score 邏輯抽至共用模組 ``cpbl.models.team_style``（UX-TEAM-STYLE1
設計約束 6：研究腳本與 API 同源）；本腳本保留研究專屬流程（穩定性檢定、
face validity、母體對帳、QA、artifact/markdown 產出）。

用法：
    uv run python scripts/team_style_vectors.py \
        --out docs/research/team_style1_metrics.json
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from cpbl.models.team_style import (
    AXES,
    AXIS_LABELS,
    FRANCHISE_MAP,
    STABILITY_YEARS,
    YEAR_FROM,
    YEAR_TO,
    batting_axes_raw,
    load_team_games,
    load_team_names,
    pearson,
    pitching_axes_raw,
    rank_desc,
    season_axis_z,
    split_half,
    zscores,
)
from cpbl.models.team_style import (
    aggregate_games as _agg,
)
from cpbl.models.team_style import (
    completed_a_filter as _completed_a_filter,
)
from cpbl.models.team_style import (
    raw_axes as _raw_axes,
)

__all__ = [  # 供 tests/test_team_style.py 與後續研究腳本 re-export
    "batting_axes_raw", "pearson", "pitching_axes_raw", "rank_desc",
    "season_axis_z", "split_half", "zscores",
]

# face validity 抽查（預註冊於 spec §0.4；先選定才看結果）
FACE_VALIDITY_CASES = (
    {"year": 2023, "team_code": "AAA011", "axes": ["smallball"], "rank_max": 2,
     "rationale": "葉君璋時期味全龍以短打小球戰術聞名"},
    {"year": 2019, "team_code": "AJK011", "axes": ["power"], "rank_max": 2,
     "rationale": "Lamigo 隊史著名重砲打線時期"},
    {"year": 2021, "team_code": "ACN011", "axes": ["starter_ip", "pitch_k"], "rank_max": 2,
     "rationale": "中信兄弟洋投先發輪值宰制、奪總冠軍（至少一軸達標）"},
)


# ---------------------------------------------------------------------------
# 資料載入（唯讀 SELECT；研究專屬——母體對帳與 QA baseline）
# ---------------------------------------------------------------------------

def load_reconciliation(c) -> list[dict]:
    """逐年母體對帳：games 完成場 vs gamelog 覆蓋場、隊數（spec §0.1／§0.5）。"""
    sql = f"""
        SELECT g.year,
               count(*) AS games_completed,
               count(DISTINCT bg.game_sno) AS games_with_batting,
               count(DISTINCT pg.game_sno) AS games_with_pitching
        FROM cpbl.games g
        LEFT JOIN (SELECT DISTINCT year, kind_code, game_sno FROM cpbl.batting_gamelog) bg
               ON bg.year = g.year AND bg.kind_code = g.kind_code AND bg.game_sno = g.game_sno
        LEFT JOIN (SELECT DISTINCT year, kind_code, game_sno FROM cpbl.pitching_gamelog) pg
               ON pg.year = g.year AND pg.kind_code = g.kind_code AND pg.game_sno = g.game_sno
        WHERE {_completed_a_filter()}
        GROUP BY g.year ORDER BY g.year
    """
    teams_sql = f"""
        SELECT year, count(DISTINCT code) FROM (
            SELECT g.year, g.home_team_code AS code FROM cpbl.games g WHERE {_completed_a_filter()}
            UNION
            SELECT g.year, g.away_team_code FROM cpbl.games g WHERE {_completed_a_filter()}
        ) t GROUP BY year ORDER BY year
    """
    params = (YEAR_FROM, YEAR_TO)
    rows = c.execute(sql, params).fetchall()
    teams = dict(c.execute(teams_sql, params + params).fetchall())
    return [
        {"year": y, "games_completed": gc, "games_with_batting": gb,
         "games_with_pitching": gp, "teams": teams[y],
         "coverage_ok": gc == gb == gp}
        for y, gc, gb, gp in rows
    ]


def load_qa_baseline(c) -> list[dict]:
    """QA：本管線 2026 隊打擊三圍 vs 官方 team_current（spec §0.5，容差 0.002）。"""
    return [
        {"team_code": tc, "avg": float(a), "obp": float(o), "slg": float(s)}
        for _, tc, a, o, s in c.execute(
            "SELECT year, team_code, bat_avg, bat_obp, bat_slg FROM cpbl.team_current "
            "WHERE year = %s ORDER BY team_code", (2026,)).fetchall()
    ]


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def compute(by_team: dict[tuple[int, str], list[dict]]) -> dict:
    years = sorted({y for y, _ in by_team})
    raw_full: dict[int, dict[str, dict]] = {}
    raw_half: dict[tuple[int, int], dict[str, dict]] = {}
    for year in years:
        teams = {t: recs for (y, t), recs in by_team.items() if y == year}
        raw_full[year] = {t: _raw_axes(_agg(recs)) for t, recs in teams.items()}
        for half in (1, 2):
            half_raw = {}
            for t, recs in teams.items():
                n1, _ = split_half(len(recs))
                part = recs[:n1] if half == 1 else recs[n1:]
                half_raw[t] = _raw_axes(_agg(part))
            raw_half[(year, half)] = half_raw

    z_full = {year: season_axis_z(raw_full[year]) for year in years}
    z_half = {key: season_axis_z(raw) for key, raw in raw_half.items()}

    # 分半穩定性（2018–2025 pooled）
    split_stats = {}
    for axis in AXES:
        h1, h2 = [], []
        for year in years:
            if year not in STABILITY_YEARS:
                continue
            for t in sorted(z_full[year]):
                h1.append(z_half[(year, 1)][t][axis])
                h2.append(z_half[(year, 2)][t][axis])
        split_stats[axis] = {"pearson_r": pearson(h1, h2), "n": len(h1)}

    # 跨季自相關（franchise 對映；t, t+1 皆須在 2018–2025）
    autocorr_stats = {}
    pairs_list = []
    for axis in AXES:
        xs, ys, pairs = [], [], []
        for year in STABILITY_YEARS[:-1]:
            if year + 1 not in STABILITY_YEARS:
                continue
            cur = {FRANCHISE_MAP.get(t, t): z for t, z in z_full.get(year, {}).items()}
            nxt = {FRANCHISE_MAP.get(t, t): z for t, z in z_full.get(year + 1, {}).items()}
            for fr in sorted(set(cur) & set(nxt)):
                xs.append(cur[fr][axis])
                ys.append(nxt[fr][axis])
                pairs.append({"franchise": fr, "t": year, "t1": year + 1})
        autocorr_stats[axis] = {"pearson_r": pearson(xs, ys), "n_pairs": len(xs)}
        if not pairs_list:
            pairs_list = pairs  # 各軸配對集合相同，記一次即可

    # face validity（預註冊隊季；rank 1 = 該季該軸最高）
    face = []
    for case in FACE_VALIDITY_CASES:
        year, team = case["year"], case["team_code"]
        ranks = {axis: rank_desc({t: z_full[year][t][axis] for t in z_full[year]}, team)
                 for axis in case["axes"]}
        face.append({**case, "ranks": ranks,
                     "n_teams": len(z_full[year]),
                     "pass": any(r <= case["rank_max"] for r in ranks.values())})

    return {"raw_full": raw_full, "z_full": z_full,
            "split_half": split_stats,
            "autocorr": autocorr_stats, "autocorr_pairs": pairs_list,
            "face_validity": face}


def _slash_line(recs: list[dict]) -> dict[str, float] | None:
    a = _agg(recs)
    obp_den = a["ab"] + a["bb"] + a["hbp"] + a["sf"]
    if not a["ab"] or not obp_den:
        return None
    return {"avg": a["h"] / a["ab"],
            "obp": (a["h"] + a["bb"] + a["hbp"]) / obp_den,
            "slg": a["tb"] / a["ab"]}


def _qa_rows(per_team: dict[str, list[dict]], baseline: list[dict]) -> list[dict]:
    out = []
    for row in baseline:
        line = _slash_line(per_team.get(row["team_code"], []) or [])
        if line is None:
            out.append({"team_code": row["team_code"], "ok": False,
                        "reason": "no gamelog aggregate"})
            continue
        deltas = {k: line[k] - row[k] for k in ("avg", "obp", "slg")}
        out.append({"team_code": row["team_code"],
                    "computed": {k: round(v, 4) for k, v in line.items()},
                    "official": {k: row[k] for k in ("avg", "obp", "slg")},
                    "max_abs_delta": round(max(abs(d) for d in deltas.values()), 4),
                    "ok": all(abs(d) <= 0.002 for d in deltas.values())})
    return out


def qa_check(by_team: dict[tuple[int, str], list[dict]], baseline: list[dict]) -> dict:
    """QA 兩份對照：

    1. ``pre_registered``：spec §0.5 凍結版——2026 全季 vs team_current。
    2. ``post_hoc_scope_corrected``：診斷後補（**非預註冊**）——實查發現 team_current
       為「當前半季」口徑（官網隊伍成績頁預設範圍），改以最新 game_season_code
       範圍對比，用以驗證聚合路徑本身無誤。
    """
    full = {t: recs for (y, t), recs in by_team.items() if y == 2026}
    season_codes = {g.get("season_code") for recs in full.values() for g in recs} - {None}
    latest = max(season_codes) if season_codes else None
    half = {t: [g for g in recs if g.get("season_code") == latest]
            for t, recs in full.items()}
    return {
        "pre_registered": _qa_rows(full, baseline),
        "post_hoc_scope_corrected": {
            "scope": f"game_season_code = '{latest}'（2026 當前半季）",
            "rows": _qa_rows(half, baseline),
        },
    }


# ---------------------------------------------------------------------------
# 輸出
# ---------------------------------------------------------------------------

def _fmt_r(r: float | None) -> str:
    return "—" if r is None else f"{r:+.3f}"


def render_markdown(res: dict, recon: list[dict], names: dict, qa: dict) -> str:
    lines: list[str] = []
    lines.append("### 逐年母體對帳（games 完成場 vs gamelog 覆蓋）\n")
    lines.append("| 年 | 隊數 | 完成場 | 打擊 gamelog | 投手 gamelog | 覆蓋 |")
    lines.append("|---|---|---|---|---|---|")
    total_ts = 0
    for r in recon:
        total_ts += r["teams"]
        ok = "✅" if r["coverage_ok"] else "❌"
        lines.append(f"| {r['year']} | {r['teams']} | {r['games_completed']} "
                     f"| {r['games_with_batting']} | {r['games_with_pitching']} | {ok} |")
    lines.append(f"\n隊季母體合計：**{total_ts}**；已計算向量列數：**{len_vectors(res)}**"
                 f"（{'一致' if total_ts == len_vectors(res) else '不一致'}）\n")

    lines.append("### 分半穩定性（2018–2025，季內前後半 z 值 Pearson r）\n")
    lines.append("| 軸 | r | n | 判讀（spec §0.4 帶） |")
    lines.append("|---|---|---|---|")
    for axis in AXES:
        st = res["split_half"][axis]
        r = st["pearson_r"]
        band = ("高穩定" if r is not None and r >= 0.5 else
                "中度" if r is not None and r >= 0.3 else "**不穩定**")
        lines.append(f"| {AXIS_LABELS[axis]}（{axis}） | {_fmt_r(r)} | {st['n']} | {band} |")

    lines.append("\n### 跨季自相關（franchise t vs t+1，2018–2025）\n")
    lines.append("| 軸 | r | 配對數 | 判讀 |")
    lines.append("|---|---|---|---|")
    for axis in AXES:
        st = res["autocorr"][axis]
        r = st["pearson_r"]
        band = ("中度延續" if r is not None and r >= 0.3 else
                "弱" if r is not None and r >= 0.1 else "**無延續訊號**")
        lines.append(f"| {AXIS_LABELS[axis]}（{axis}） | {_fmt_r(r)} | {st['n_pairs']} | {band} |")

    lines.append("\n### Face validity 抽查（預註冊隊季）\n")
    lines.append("| 隊季 | 軸 | 名次/隊數 | 判準 | 結果 |")
    lines.append("|---|---|---|---|---|")
    for case in res["face_validity"]:
        name = names.get((case["year"], case["team_code"]), case["team_code"])
        ranks = "、".join(f"{AXIS_LABELS[a]} 第{r}" for a, r in case["ranks"].items())
        verdict = "PASS" if case["pass"] else "**FAIL**"
        lines.append(f"| {case['year']} {name} | {ranks} | /{case['n_teams']} 隊 "
                     f"| 任一軸 ≤ {case['rank_max']} | {verdict} |")

    def _qa_table(rows: list[dict]) -> None:
        lines.append("| 隊 | 計算 AVG/OBP/SLG | 官方 AVG/OBP/SLG | max|Δ| | 結果 |")
        lines.append("|---|---|---|---|---|")
        for row in rows:
            c, o = row["computed"], row["official"]
            ok = "✅" if row["ok"] else "❌"
            lines.append(f"| {row['team_code']} | {c['avg']:.3f}/{c['obp']:.3f}/{c['slg']:.3f} "
                         f"| {o['avg']:.3f}/{o['obp']:.3f}/{o['slg']:.3f} "
                         f"| {row['max_abs_delta']:.4f} | {ok} |")

    lines.append("\n### QA（預註冊版）：2026 全季三圍 vs 官方 team_current（容差 0.002）\n")
    _qa_table(qa["pre_registered"])
    scoped = qa["post_hoc_scope_corrected"]
    lines.append(f"\n### QA（事後診斷版，非預註冊）：{scoped['scope']} vs team_current\n")
    _qa_table(scoped["rows"])

    lines.append("\n### 隊季風格向量（季內 z；正值＝該風格強於當季聯盟平均）\n")
    header = " | ".join(AXIS_LABELS[a] for a in AXES)
    lines.append(f"| 年 | 隊 | {header} |")
    lines.append("|---|---|" + "---|" * len(AXES))
    for year in sorted(res["z_full"]):
        for t in sorted(res["z_full"][year]):
            zs = res["z_full"][year][t]
            name = names.get((year, t), t)
            cells = " | ".join(f"{zs[a]:+.2f}" for a in AXES)
            lines.append(f"| {year} | {name} | {cells} |")
    return "\n".join(lines)


def len_vectors(res: dict) -> int:
    return sum(len(teams) for teams in res["z_full"].values())


def build_artifact(res: dict, recon: list[dict], names: dict, qa: dict) -> dict:
    team_seasons = []
    for year in sorted(res["z_full"]):
        for t in sorted(res["z_full"][year]):
            team_seasons.append({
                "year": year, "team_code": t,
                "team_name": names.get((year, t), t),
                "raw": {k: (round(v, 6) if v is not None else None)
                        for k, v in res["raw_full"][year][t].items()},
                "z": {a: round(res["z_full"][year][t][a], 4) for a in AXES},
            })
    return {
        "card": "TEAM-STYLE1",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "spec": {
            "sample": {"kind_code": "A", "years": [YEAR_FROM, YEAR_TO],
                       "completed_rule": "home_score+away_score>0 AND game_date<=CURRENT_DATE",
                       "stability_years": list(STABILITY_YEARS),
                       "franchise_map": FRANCHISE_MAP},
            "axes": {a: AXIS_LABELS[a] for a in AXES},
            "normalization": "season-league z-score (population std); "
                             "composite discipline re-standardized",
        },
        "reconciliation": {
            "per_year": recon,
            "team_seasons_expected": sum(r["teams"] for r in recon),
            "team_seasons_computed": len(team_seasons),
            "match": sum(r["teams"] for r in recon) == len(team_seasons),
        },
        "team_seasons": team_seasons,
        "stability": {
            "split_half": {a: {"pearson_r": (round(v["pearson_r"], 4)
                                             if v["pearson_r"] is not None else None),
                               "n": v["n"]}
                           for a, v in res["split_half"].items()},
            "cross_season_autocorr": {a: {"pearson_r": (round(v["pearson_r"], 4)
                                                        if v["pearson_r"] is not None else None),
                                          "n_pairs": v["n_pairs"]}
                                      for a, v in res["autocorr"].items()},
            "autocorr_pairs": res["autocorr_pairs"],
        },
        "face_validity": res["face_validity"],
        "qa_team_current_2026": qa,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="docs/research/team_style1_metrics.json")
    args = parser.parse_args()

    from cpbl.db import conn

    with conn() as c:
        by_team = load_team_games(c)
        recon = load_reconciliation(c)
        names = load_team_names(c)
        baseline = load_qa_baseline(c)

    res = compute(by_team)
    qa = qa_check(by_team, baseline)
    artifact = build_artifact(res, recon, names, qa)

    out_path = Path(args.out)
    out_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(render_markdown(res, recon, names, qa))
    print(f"\nartifact → {out_path}")


if __name__ == "__main__":
    main()
