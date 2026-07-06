"""CLI：驗證「重算分項」對照「官方爬取分項」——Phase 0 harness。

    uv run cpbl-verify-splits [year] [kind]     # 預設 2026 A

逐 (家族, 欄位) 比對重算值與官方值，輸出吻合率與 mismatch 樣本。
驗收紅線：T1 全欄 100%；T2 每個系統性差異都須有已解釋的規則，否則不得進 Phase 1。
只讀不寫、不爬網。對照基準以每位選手官方快照日（updated_at::date）為 cutoff，
排除快照後的場次，避免把時差誤判成重建錯誤。
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from datetime import date
from zoneinfo import ZoneInfo

from cpbl.db import conn
from cpbl.ingest.splits_calc import (
    Table,
    calc_batting_t1,
    calc_pitching_t1,
    calc_t2,
)

_TPE = ZoneInfo("Asia/Taipei")

# 非計數欄（鍵/衍生率/時間戳）不比對
_SKIP_COLS = {
    "year", "kind_code", "acnt", "item_group_code", "item_index", "item_name",
    "item_note", "updated_at", "fight_team_code", "fight_team_name", "team_no",
    "avg", "obp", "slg", "ops", "ta", "goao", "sb_pct", "inning_pitched_cnt",
}

GROUP_LABELS_BAT = {"1": "主客", "3": "vs投手", "4": "壘上", "5": "出局", "6": "局數",
                    "7": "比分", "8": "月份", "9": "球場", "10": "棒次", "VT": "vs各隊"}
GROUP_LABELS_PIT = {"1": "主客", "3": "vs打者", "4": "角色", "5": "壘上", "6": "出局",
                    "7": "局數", "8": "比分", "9": "月份", "10": "球場", "VT": "vs各隊"}


def _official(table: str, year: int, kind: str) -> tuple[dict, dict[str, date]]:
    """讀官方表 → ({key: {col: val}}, {acnt: cutoff_date})。"""
    is_vs = table.endswith("_vs_team")
    with conn() as c:
        cur = c.execute(
            f"SELECT * FROM cpbl.{table} WHERE year = %s AND kind_code = %s",  # noqa: S608 — table 為內部常數
            (year, kind))
        cols = [d.name for d in cur.description]
        rows = cur.fetchall()
    out: dict = {}
    cutoff: dict[str, date] = {}
    i_acnt = cols.index("acnt")
    i_upd = cols.index("updated_at")
    for r in rows:
        d = dict(zip(cols, r, strict=True))
        acnt = d["acnt"]
        key = ((acnt, "VT", d["fight_team_name"]) if is_vs
               else (acnt, d["item_group_code"], d["item_name"]))
        out[key] = {k: int(v) for k, v in d.items()
                    if k not in _SKIP_COLS and isinstance(v, int)}
        upd = r[i_upd]
        if upd is not None:
            prev = cutoff.get(r[i_acnt])
            # 快照日必須取台北時區：01:46 台北 = 前一日 UTC，用 UTC 日期會把
            # 快照已含的最後一天比賽錯誤排除（harness 實證：高捷 6/17 案例）
            u = upd.astimezone(_TPE).date()
            if prev is None or u > prev:
                cutoff[r[i_acnt]] = u
    return out, cutoff


def _names() -> dict[str, str]:
    with conn() as c:
        return dict(c.execute("SELECT id, name FROM cpbl.players").fetchall())


def _merge(dst: Table, src: Table) -> None:
    for key, cnt in src.items():
        dst.setdefault(key, Counter()).update(cnt)


def _compare(label: str, computed: Table, official: dict, groups: dict[str, str],
             names: dict[str, str], samples: list) -> None:
    """逐家族逐欄比對，印吻合率；mismatch 收進 samples。"""
    by_grp_cols: dict[str, set] = defaultdict(set)
    for (_, grp, _), cnt in computed.items():
        by_grp_cols[grp].update(cnt.keys())
    all_grps = sorted({k[1] for k in computed} | {k[1] for k in official},
                      key=lambda g: (len(g), g))
    print(f"\n═══ {label} ═══")
    for grp in all_grps:
        keys = {k for k in computed if k[1] == grp} | {k for k in official if k[1] == grp}
        cols = sorted(by_grp_cols.get(grp, set()))
        gname = groups.get(grp, grp)
        if not cols:
            print(f"[{grp} {gname}] 未重算（{sum(1 for k in official if k[1] == grp)} 官方列）")
            continue
        stats = {c: [0, 0, 0] for c in cols}  # [total, equal, sum|Δ|]
        # 官方有填但我們沒算的欄
        off_cols = Counter()
        for k in keys:
            ours = computed.get(k, {})
            offs = official.get(k, {})
            for c in cols:
                o, f = ours.get(c, 0), offs.get(c, 0)
                stats[c][0] += 1
                if o == f:
                    stats[c][1] += 1
                else:
                    stats[c][2] += abs(o - f)
                    samples.append((label, grp, gname, k[0], names.get(k[0], "?"),
                                    k[2], c, o, f))
            for c, v in offs.items():
                if v and c not in by_grp_cols[grp]:
                    off_cols[c] += 1
        bad = {c: s for c, s in stats.items() if s[1] < s[0]}
        n_keys = len(keys)
        if not bad:
            print(f"[{grp} {gname}] ✅ {n_keys} 列 × {len(cols)} 欄全數吻合")
        else:
            print(f"[{grp} {gname}] {n_keys} 列：")
            for c, (tot, eq, sd) in sorted(bad.items(), key=lambda x: x[1][1] - x[1][0]):
                print(f"    {c}: {eq}/{tot} 吻合（mismatch {tot - eq}, Σ|Δ|={sd}）")
        if off_cols:
            print(f"    ⚠️ 官方有值未重算欄: {dict(off_cols)}")


def main() -> None:
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    kind = sys.argv[2] if len(sys.argv) > 2 else "A"
    names = _names()

    off_bat, bat_cut = _official("batting_splits", year, kind)
    off_pit, pit_cut = _official("pitching_splits", year, kind)
    off_bvt, bvt_cut = _official("batting_vs_team", year, kind)
    off_pvt, pvt_cut = _official("pitching_vs_team", year, kind)

    bat_t1, bat_vt = calc_batting_t1(year, kind, bat_cut)
    pit_t1, pit_vt = calc_pitching_t1(year, kind, pit_cut)
    # vs各隊有獨立 cutoff，另算一份（成本低：同 SQL 再跑一次）
    _, bat_vt = calc_batting_t1(year, kind, bvt_cut)
    _, pit_vt = calc_pitching_t1(year, kind, pvt_cut)
    bat_t2, pit_t2, bat_gofo, diag = calc_t2(year, kind, bat_cut, pit_cut)
    _merge(bat_t1, bat_gofo)          # 家族 1/8/9 的 go/fo 由 livelog 補
    _merge(bat_t1, bat_t2)            # 打者家族合併為單表比對
    _merge(pit_t1, pit_t2)

    samples: list = []
    _compare(f"打者分項 {year} {kind}", bat_t1, off_bat, GROUP_LABELS_BAT, names, samples)
    _compare(f"投手分項 {year} {kind}", pit_t1, off_pit, GROUP_LABELS_PIT, names, samples)
    _compare(f"打者vs各隊 {year} {kind}", bat_vt, off_bvt, GROUP_LABELS_BAT, names, samples)
    _compare(f"投手vs各隊 {year} {kind}", pit_vt, off_pvt, GROUP_LABELS_PIT, names, samples)

    print("\n═══ diagnostics ═══")
    print(f"PA islands={diag['islands']} 有效PA={diag['pa']} "
          f"無結果island(非PA)={diag['skipped_no_outcome']} "
          f"幽靈島(換人公告)={sum(diag['skipped_no_pitch'].values())}")
    if diag["skipped_no_pitch"]:
        print(f"  幽靈島結果分布(審計用): {dict(diag['skipped_no_pitch'])}")
    if diag["unknown_action"]:
        print(f"🔴 未知打席結果詞彙（紅線，必修）: {dict(diag['unknown_action'])}")
    if diag["missing_batter_bio"]:
        top = diag["missing_batter_bio"].most_common(5)
        print(f"⚠️ 打者缺 bats（vs左右打略過）: {len(diag['missing_batter_bio'])} 人, top={top}")
    if diag["missing_pitcher_bio"]:
        print(f"⚠️ 投手缺 throws: {len(diag['missing_pitcher_bio'])} 人")
    if diag["missing_role"]:
        print(f"⚠️ 投手該場無 role（VS.先發/中繼/救援略過）: {len(diag['missing_role'])} 場次")

    if samples:
        print(f"\n═══ mismatch 樣本（共 {len(samples)}，前 40）═══")
        for label, grp, gname, acnt, nm, item, col, o, f in samples[:40]:
            print(f"  {label} [{grp} {gname}] {nm}({acnt}) {item} {col}: 算={o} 官={f}")

    sys.exit(1 if diag["unknown_action"] else 0)


if __name__ == "__main__":
    main()
