# LIFECYCLE: ci_guard · CI 繫結守衛——不必手動跑，CI 會跑；刪了 CI 會紅
"""TEAM-STYLE2 換教練混雜效應檢定（唯讀；描述性）。

依 docs/research/TEAM-STYLE2_RESULTS.md §0 預註冊規格：
把 TEAM-STYLE1 的 33 組跨季配對按「t 與 t+1 主教練是否同一人」二分，
逐軸比較兩組延續性（Pearson r）＋配對層 bootstrap CI。

主教練逐季判定：維基逐年列場數唯一最大者（快照 docs/research/team_style2_wiki_snapshot.json；
平手＝不可判定）。z 值直接讀 team_style1_metrics.json，不重算軸。

用法：
    uv run python scripts/team_style2_manager_pairs.py --fetch   # 重建維基快照（需網路）
    uv run python scripts/team_style2_manager_pairs.py           # 分析（讀快照；DB 唯讀 QA）
    uv run python scripts/team_style2_manager_pairs.py --skip-db # 無 DB 環境重跑統計本體
"""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = ROOT / "docs" / "research" / "team_style2_wiki_snapshot.json"
STYLE1_PATH = ROOT / "docs" / "research" / "team_style1_metrics.json"
OUT_PATH = ROOT / "docs" / "research" / "team_style2_metrics.json"

AXES = ("speed", "smallball", "power", "discipline", "starter_ip", "pitch_k", "defense")
AXIS_LABELS = {
    "speed": "速度戰",
    "smallball": "短打戰術",
    "power": "長打火力",
    "discipline": "選球紀律",
    "starter_ip": "先發吃局",
    "pitch_k": "三振型投手",
    "defense": "守備效率",
}
TEAM_LABELS = {
    "AAA011": "味全龍",
    "ACN011": "中信兄弟",
    "ADD011": "統一7-ELEVEn獅",
    "AEO011": "富邦悍將",
    "AJL011": "樂天桃猿（含 Lamigo）",
    "AKP011": "台鋼雄鷹",
}

# bootstrap 參數（預註冊凍結）
B = 10_000
SEED = 20260727

_EXCLUDE_NAMES = {"--", "—", "-", "合計", "總計", "小計", "累計"}


# ---------------------------------------------------------------------------
# 維基快照（--fetch）
# ---------------------------------------------------------------------------

def _expand_rows(table_html: str, ncols: int) -> list[list[str]]:
    """展開 rowspan 還原完整網格（沿用 cpbl_managers._parse_managers 同款邏輯：
    單格列＝時期分隔列，重置 rowspan carry 並跳過）。"""
    from cpbl.ingest.cpbl_managers import _cells

    rows: list[list[str]] = []
    carry: dict[int, list] = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.S):
        cs = _cells(tr)
        if len(cs) == 1:  # 時期分隔列（如「俊國熊時期」）
            carry = {}
            continue
        row: list[str] = []
        ci = si = 0
        while ci < ncols:
            if ci in carry and carry[ci][1] > 0:
                row.append(carry[ci][0]); carry[ci][1] -= 1; ci += 1
            elif si < len(cs):
                txt, rs = cs[si]; si += 1; row.append(txt)
                if rs > 1:
                    carry[ci] = [txt, rs - 1]
                ci += 1
            else:
                break
        if row:
            rows.append(row)
    return rows


def fetch_snapshot() -> dict:
    """抓六隊維基條目 → 選定總教練表 → 展開列 → 寫快照（含 revid provenance）。"""
    import httpx

    from cpbl.ingest.cpbl_managers import UA, WIKI_TITLE, _best_table, _get

    snap: dict = {"fetched_at": datetime.now(UTC).isoformat(), "source": "zh.wikipedia.org", "teams": {}}
    with httpx.Client(headers={"User-Agent": UA}) as client:
        for code, title in WIKI_TITLE.items():
            d = _get(client, action="parse", page=title, prop="text|revid")
            parse = d["parse"]
            found = _best_table(parse["text"]["*"])
            if not found:
                raise RuntimeError(f"{code}（{title}）解析不到總教練表")
            table, header = found
            snap["teams"][code] = {
                "title": title,
                "revid": parse.get("revid"),
                "header": header,
                "rows": _expand_rows(table, len(header)),
            }
    SNAPSHOT_PATH.write_text(json.dumps(snap, ensure_ascii=False, indent=1) + "\n")
    print(f"snapshot written: {SNAPSHOT_PATH}")
    return snap


# ---------------------------------------------------------------------------
# 主教練逐季判定（預註冊 §0.2；純函式，測試封閉解）
# ---------------------------------------------------------------------------

def clean_name(name: str) -> str:
    """去掉維基姓名後的括號註記（同 cpbl_managers._clean_name 口徑）。"""
    return re.sub(r"[（(].*$", "", name or "").strip()


def _first_year(cell: str) -> int | None:
    m = re.search(r"\d{4}", cell or "")
    return int(m.group()) if m else None


def _games(cell: str) -> int:
    m = re.search(r"\d+", cell or "")
    return int(m.group()) if m else 0


def season_manager_games(header: list[str], rows: list[list[str]], year: int) -> tuple[dict[str, int], list[list[str]]]:
    """回傳 (該季各主教練場數加總, 判定所依據的原始列)。規則見 spec §0.2。"""
    from cpbl.ingest.cpbl_managers import _NAME_KEYS, _YEAR_KEYS, _col_idx

    name_i = _col_idx(header, *_NAME_KEYS)
    year_i = _col_idx(header, *_YEAR_KEYS)
    g_i = _col_idx(header, "出賽", "執教場次", "場次")
    if name_i is None or year_i is None or g_i is None:
        return {}, []
    games: dict[str, int] = {}
    used: list[list[str]] = []
    for row in rows:
        y = _first_year(row[year_i] if year_i < len(row) else "")
        if y != year:
            continue
        g = _games(row[g_i] if g_i < len(row) else "")
        if g <= 0:
            continue
        name = clean_name(row[name_i] if name_i < len(row) else "")
        if not name or name in _EXCLUDE_NAMES or name in _NAME_KEYS:
            continue
        games[name] = games.get(name, 0) + g
        used.append(row)
    return games, used


def main_manager(games: dict[str, int]) -> tuple[str | None, str]:
    """(主教練, 判定說明)；不可判定回 (None, 原因)。規則：場數唯一最大者；平手＝不可判定。"""
    if not games:
        return None, "無含場數之逐年列（不可判定）"
    # 防禦性：單列多名（頓號/斜線）——姓名含分隔符即整季不可判定
    for n in games:
        if re.search(r"[、/／]", n):
            return None, f"姓名欄含多名（{n}）（不可判定）"
    top = max(games.values())
    winners = [n for n, g in games.items() if g == top]
    detail = "；".join(f"{n} {g}場" for n, g in sorted(games.items(), key=lambda kv: -kv[1]))
    if len(winners) > 1:
        return None, f"場數平手（{detail}）（不可判定）"
    return winners[0], detail


def classify_pair(m_t: str | None, m_t1: str | None) -> str:
    """'same' / 'changed' / 'excluded'（任一季不可判定即排除）。"""
    if m_t is None or m_t1 is None:
        return "excluded"
    return "same" if m_t == m_t1 else "changed"


# ---------------------------------------------------------------------------
# 統計（預註冊 §0.4；純函式）
# ---------------------------------------------------------------------------

def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson r；退化（std=0 或 n<2）回 None。"""
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    return sxy / math.sqrt(sxx * syy)


def group_axis_r(pairs_z: list[dict]) -> dict[str, float | None]:
    """一組配對（每對含 z_t / z_t1 dict）→ 逐軸 Pearson r。"""
    out: dict[str, float | None] = {}
    for ax in AXES:
        out[ax] = pearson([p["z_t"][ax] for p in pairs_z], [p["z_t1"][ax] for p in pairs_z])
    return out


def bootstrap_deltas(same: list[dict], changed: list[dict], b: int = B, seed: int = SEED) -> dict:
    """配對層分層 bootstrap（spec §0.4.4）：兩組各自重抽（含放回、n 不變、7 軸整包），
    每 replicate 重算 Δr_axis 與 Δ̄；退化 replicate 剔除計數。回傳 percentile 95% CI。"""
    import numpy as np

    rng = np.random.default_rng(seed)
    n_s, n_c = len(same), len(changed)
    per_axis: dict[str, list[float]] = {ax: [] for ax in AXES}
    means: list[float] = []
    dropped = 0
    for _ in range(b):
        idx_s = rng.integers(0, n_s, n_s)
        idx_c = rng.integers(0, n_c, n_c)
        rs = group_axis_r([same[i] for i in idx_s])
        rc = group_axis_r([changed[i] for i in idx_c])
        if any(rs[ax] is None or rc[ax] is None for ax in AXES):
            dropped += 1
            continue
        deltas = [rs[ax] - rc[ax] for ax in AXES]
        for ax, dv in zip(AXES, deltas, strict=True):
            per_axis[ax].append(dv)
        means.append(sum(deltas) / len(AXES))

    def ci(vals: list[float]) -> list[float] | None:
        if not vals:  # 全部 replicate 退化剔除（真實資料不預期發生；照實回 None）
            return None
        lo, hi = np.percentile(np.asarray(vals), [2.5, 97.5])
        return [round(float(lo), 6), round(float(hi), 6)]

    return {
        "b": b,
        "seed": seed,
        "replicates_used": len(means),
        "replicates_dropped_degenerate": dropped,
        "per_axis_ci": {ax: ci(per_axis[ax]) for ax in AXES},
        "mean_delta_ci": ci(means),
    }


# ---------------------------------------------------------------------------
# 分析主流程
# ---------------------------------------------------------------------------

def _season_team_code(franchise: str, year: int) -> str:
    """AJL011 配對中 2019 以前的隊季 z 存為 AJK011（TEAM-STYLE1 凍結對映）。"""
    if franchise == "AJL011" and year <= 2019:
        return "AJK011"
    return franchise


def _db_qa(assignments: list[dict]) -> list[dict]:
    """QA 交叉檢核（非判定依據）：判定結果應可對上 cpbl.managers 原始列。唯讀 SELECT。"""
    from cpbl.db import conn

    out = []
    with conn() as c:
        for a in assignments:
            if a["main_manager"] is None:
                continue
            row = c.execute(
                "SELECT era_name, from_year, to_year FROM cpbl.managers "
                "WHERE team_code=%s AND name=%s AND from_year<=%s AND (to_year IS NULL OR to_year>=%s)",
                (a["franchise"], a["main_manager"], a["year"], a["year"]),
            ).fetchone()
            out.append({
                "franchise": a["franchise"],
                "year": a["year"],
                "main_manager": a["main_manager"],
                "db_match": row is not None,
                "db_row": {"era_name": row[0], "from_year": row[1], "to_year": row[2]} if row else None,
            })
    return out


def run_analysis(skip_db: bool = False) -> dict:
    snap = json.loads(SNAPSHOT_PATH.read_text())
    style1 = json.loads(STYLE1_PATH.read_text())
    pairs_spec = style1["stability"]["autocorr_pairs"]
    z_by = {(t["year"], t["team_code"]): t["z"] for t in style1["team_seasons"]}

    # 逐季主教練判定（僅配對涉及的 franchise×季）
    seasons_needed = sorted({(p["franchise"], y) for p in pairs_spec for y in (p["t"], p["t1"])})
    assignments = []
    assign_by: dict[tuple[str, int], dict] = {}
    for fr, y in seasons_needed:
        team = snap["teams"][fr]
        games, used_rows = season_manager_games(team["header"], team["rows"], y)
        mm, detail = main_manager(games)
        rec = {
            "franchise": fr, "year": y, "main_manager": mm, "detail": detail,
            "games_by_manager": dict(sorted(games.items(), key=lambda kv: -kv[1])),
            "source_rows": used_rows, "wiki_title": team["title"], "wiki_revid": team["revid"],
        }
        assignments.append(rec)
        assign_by[(fr, y)] = rec

    # 33 組配對二分（窮舉）
    pair_rows = []
    grouped: dict[str, list[dict]] = {"same": [], "changed": [], "excluded": []}
    for p in pairs_spec:
        fr, t, t1 = p["franchise"], p["t"], p["t1"]
        a_t, a_t1 = assign_by[(fr, t)], assign_by[(fr, t1)]
        cls = classify_pair(a_t["main_manager"], a_t1["main_manager"])
        z_t = z_by[(t, _season_team_code(fr, t))]
        z_t1 = z_by[(t1, _season_team_code(fr, t1))]
        row = {
            "franchise": fr, "t": t, "t1": t1,
            "manager_t": a_t["main_manager"], "manager_t1": a_t1["main_manager"],
            "basis_t": a_t["detail"], "basis_t1": a_t1["detail"],
            "group": cls, "z_t": z_t, "z_t1": z_t1,
        }
        pair_rows.append(row)
        grouped[cls].append(row)

    same, changed = grouped["same"], grouped["changed"]
    r_same = group_axis_r(same)
    r_changed = group_axis_r(changed)
    deltas = {ax: (None if r_same[ax] is None or r_changed[ax] is None
                   else round(r_same[ax] - r_changed[ax], 6)) for ax in AXES}
    boot = bootstrap_deltas(same, changed)

    # 判準（spec §0.4.5，凍結）：Go ⇔ ≥4/7 軸 Δr>0 且 Δ̄ CI 下界 > 0
    n_pos = sum(1 for ax in AXES if deltas[ax] is not None and deltas[ax] > 0)
    mean_delta = round(sum(deltas[ax] for ax in AXES) / len(AXES), 6)
    mean_ci = boot["mean_delta_ci"]
    go = (n_pos >= 4) and (mean_ci is not None) and (mean_ci[0] > 0)

    artifact = {
        "card": "TEAM-STYLE2",
        "generated_at": datetime.now(UTC).isoformat(),
        "spec": {
            "preregistered_in": "docs/research/TEAM-STYLE2_RESULTS.md §0（先行 commit）",
            "upstream": "docs/research/team_style1_metrics.json（TEAM-STYLE1 凍結 spec 50c23be；軸/z/配對沿用不重算）",
            "manager_rule": "維基逐年列場數唯一最大者；平手/缺列＝不可判定；to_year 與 managers.g 不用於判定",
            "binary_rule": "t 與 t+1 主教練同名＝同教練組；任一季不可判定＝配對排除",
            "decision_rule": "Go ⇔ ≥4/7 軸 Δr>0 且七軸平均 Δ̄ 之 95% bootstrap CI 下界 > 0",
            "bootstrap": {"b": B, "seed": SEED, "resample": "配對層 cluster、兩組分層、percentile 95% CI"},
        },
        "wiki_snapshot": {
            "path": "docs/research/team_style2_wiki_snapshot.json",
            "fetched_at": snap["fetched_at"],
            "revids": {code: t["revid"] for code, t in snap["teams"].items()},
        },
        "season_managers": [
            {k: v for k, v in a.items()} for a in assignments
        ],
        "pairs": [
            {k: v for k, v in p.items() if k not in ("z_t", "z_t1")} for p in pair_rows
        ],
        "group_sizes": {"same": len(same), "changed": len(changed), "excluded": len(grouped["excluded"])},
        "excluded_pairs": [
            {"franchise": p["franchise"], "t": p["t"], "t1": p["t1"],
             "reason_t": p["basis_t"] if p["manager_t"] is None else None,
             "reason_t1": p["basis_t1"] if p["manager_t1"] is None else None}
            for p in grouped["excluded"]
        ],
        "per_axis": {
            ax: {
                "r_same": None if r_same[ax] is None else round(r_same[ax], 6),
                "n_same": len(same),
                "r_changed": None if r_changed[ax] is None else round(r_changed[ax], 6),
                "n_changed": len(changed),
                "delta_r": deltas[ax],
                "delta_ci95": boot["per_axis_ci"][ax],
            } for ax in AXES
        },
        "pooled": {
            "mean_delta_r": mean_delta,
            "ci95": boot["mean_delta_ci"],
            "axes_delta_positive": n_pos,
            "axes_total": len(AXES),
        },
        "bootstrap_diagnostics": {
            "replicates_used": boot["replicates_used"],
            "replicates_dropped_degenerate": boot["replicates_dropped_degenerate"],
        },
        "conclusion": {
            "go": go,
            "label": "Go：任期分段成立" if go else "No-Go：維持逐季呈現；教練分段僅作呈現選項（事實分組）",
        },
    }
    if not skip_db:
        artifact["db_qa_managers_crosscheck"] = _db_qa(assignments)

    OUT_PATH.write_text(json.dumps(artifact, ensure_ascii=False, indent=1) + "\n")
    _print_markdown(artifact)
    return artifact


# ---------------------------------------------------------------------------
# stdout markdown（貼報告用）
# ---------------------------------------------------------------------------

def _print_markdown(a: dict) -> None:
    print(f"\nartifact: {OUT_PATH}\n")

    print("### 逐季主教練判定（維基逐年列場數；判定依據窮舉）\n")
    print("| Franchise | 季 | 主教練 | 判定依據（該季各任場數） |")
    print("|---|---|---|---|")
    for s in a["season_managers"]:
        mm = s["main_manager"] or "**不可判定**"
        print(f"| {TEAM_LABELS[s['franchise']]} | {s['year']} | {mm} | {s['detail']} |")

    print("\n### 33 組配對二分歸屬（窮舉）\n")
    print("| Franchise | t → t+1 | 主教練 t | 主教練 t+1 | 組別 |")
    print("|---|---|---|---|---|")
    lab = {"same": "同教練", "changed": "換教練", "excluded": "**排除（不可判定）**"}
    for p in a["pairs"]:
        print(f"| {TEAM_LABELS[p['franchise']]} | {p['t']}→{p['t1']} | "
              f"{p['manager_t'] or '不可判定'} | {p['manager_t1'] or '不可判定'} | {lab[p['group']]} |")
    g = a["group_sizes"]
    print(f"\n合計：同教練 {g['same']} 對／換教練 {g['changed']} 對／排除 {g['excluded']} 對"
          f"（共 {g['same'] + g['changed'] + g['excluded']} 對）")

    print("\n### 逐軸兩組跨季自相關（Pearson r）與差異\n")
    print("| 軸 | r（同教練） | r（換教練） | Δr | Δr 95% CI |")
    print("|---|---|---|---|---|")
    for ax in AXES:
        p = a["per_axis"][ax]
        ci = p["delta_ci95"]
        print(f"| {AXIS_LABELS[ax]}（{ax}） | {p['r_same']:+.3f} (n={p['n_same']}) | "
              f"{p['r_changed']:+.3f} (n={p['n_changed']}) | {p['delta_r']:+.3f} | "
              f"[{ci[0]:+.3f}, {ci[1]:+.3f}] |")

    pl = a["pooled"]
    print(f"\n池化差異 Δ̄（七軸平均）= {pl['mean_delta_r']:+.3f}，"
          f"95% bootstrap CI [{pl['ci95'][0]:+.3f}, {pl['ci95'][1]:+.3f}]；"
          f"Δr>0 軸數 = {pl['axes_delta_positive']}/{pl['axes_total']}")
    bd = a["bootstrap_diagnostics"]
    print(f"bootstrap：B={a['spec']['bootstrap']['b']}、seed={a['spec']['bootstrap']['seed']}、"
          f"有效 replicates={bd['replicates_used']}、退化剔除={bd['replicates_dropped_degenerate']}")
    print(f"\n**結論（預凍結判準）**：{a['conclusion']['label']}")

    if "db_qa_managers_crosscheck" in a:
        bad = [q for q in a["db_qa_managers_crosscheck"] if not q["db_match"]]
        print(f"\nDB QA（cpbl.managers 交叉檢核）：{len(a['db_qa_managers_crosscheck'])} 筆判定，"
              f"mismatch {len(bad)} 筆" + (f"：{bad}" if bad else ""))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fetch", action="store_true", help="重建維基快照（需網路）")
    ap.add_argument("--skip-db", action="store_true", help="跳過 cpbl.managers QA 交叉檢核")
    args = ap.parse_args()
    if args.fetch:
        fetch_snapshot()
        return
    run_analysis(skip_db=args.skip_db)


if __name__ == "__main__":
    main()
