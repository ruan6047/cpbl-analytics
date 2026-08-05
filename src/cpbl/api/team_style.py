"""球隊頁「球風」區塊的 view 組裝（UX-TEAM-STYLE1；唯讀）。

軸計算全部來自共用模組 ``cpbl.models.team_style``（TEAM-STYLE1 凍結 spec
50c23be，設計約束 6「計算單一來源」）；本模組只做 request-time 聚合與
回應塑形，不建表、不寫 DB（derived-stats-computed-live 慣例）。

軸級語意標注（設計約束 3；判定在後端做一次，前端只映射文案）：

- ``cross_season_stable``：唯一可標「具跨季延續性」的軸（選球紀律）。
- ``current_season_only``：必標「本季」——季內成立、跨季不延續（先發吃局／三振型投手）。
- ``numbers_only``：只放數字與排名、零形容詞（守備效率）。
- ``usable``：可用，附季內噪音／跨季延續偏弱等穩定性語意（速度戰／短打戰術／長打火力）。

教練時間標記（設計約束 2；STYLE2 No-Go → 分段維持逐季，教練名僅時間標記）：
逐季主教練**直接取 TEAM-STYLE2 artifact 的 39 筆逐季判定結果**（機械抽取打包於
``resources/team_style2_season_managers.json``，不重新發明判定規則）；不可判定
或覆蓋外的季（含 2026）一律不標。``managers.to_year`` 是維基最後戰績列年份而非
卸任年（STYLE2 紅線 3），故任何以任期年份範圍推逐季歸屬的做法都被禁止。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from cpbl.db import conn
from cpbl.franchises import franchise_of
from cpbl.models import team_style as ts

# 軸級語意 discriminator（機器可讀；文案由前端 copy 表映射）。
AXIS_SEMANTICS: dict[str, str] = {
    "speed": "usable",
    "smallball": "usable",
    "power": "usable",
    "discipline": "cross_season_stable",
    "starter_ip": "current_season_only",
    "pitch_k": "current_season_only",
    "defense": "numbers_only",
}

SEMANTICS_VALUES = frozenset(
    {"cross_season_stable", "current_season_only", "numbers_only", "usable"}
)

_MANAGERS_RESOURCE = Path(__file__).resolve().parent.parent / "resources" / \
    "team_style2_season_managers.json"


@lru_cache(maxsize=1)
def season_managers() -> tuple[dict, ...]:
    """TEAM-STYLE2 逐季主教練判定（含不可判定列，main_manager=None）。"""
    data = json.loads(_MANAGERS_RESOURCE.read_text(encoding="utf-8"))
    return tuple(data["season_managers"])


def managers_of(franchise: str) -> dict[int, str]:
    """該 franchise 已判定的逐季主教練（不可判定季不入 dict＝不標）。"""
    return {
        r["year"]: r["main_manager"]
        for r in season_managers()
        if r["franchise"] == franchise and r["main_manager"] is not None
    }


def fill_current_managers(
    managers: dict[int, str],
    in_progress_years: set[int],
    lookup,
) -> dict[int, str]:
    """教練標記的兩個來源分工（需求方 2026-07-27 第四批裁定）：

    - **歷史季**＝TEAM-STYLE2 逐季判定 resource（研究凍結，不動）。
    - **當季（進行中賽季）**＝官網 ``cpbl.coaches``（/team/index 爬蟲、
      current 系列語意每季重爬覆蓋）——STYLE2 覆蓋不到的進行中賽季由此補標。

    只補「STYLE2 無判定且進行中」的年；歷史不可判定季（如統一 2019）不在
    in_progress 故維持不標。``lookup(year)`` 查無（防禦性）→ 該年維持不標。
    嚴禁以「延伸前任」推當季（活證據：富邦 2025 陳金鋒 → 2026 後藤光尊、
    樂天 2025 古久保健二 → 2026 曾豪駒）。
    """
    out = dict(managers)
    for year in in_progress_years:
        if year in out:
            continue  # STYLE2 已判定的季不覆蓋
        name = lookup(year)
        if name:
            out[year] = name
    return out


def axis_counts(axis: str, agg: dict[str, int]) -> dict[str, int]:
    """各軸明細用的原始計數（給一般球迷看「次數」；rate 仍是凍結軸值）。

    defense 依設計約束 3 只回空 dict——該列只呈現 DER 數字與排名。
    """
    if axis == "speed":
        return {"sb": agg["sb"], "cs": agg["cs"]}
    if axis == "smallball":
        return {"sh": agg["sh"], "pa": agg["pa"]}
    if axis == "power":
        return {"extra_bases": agg["tb"] - agg["h"], "ab": agg["ab"]}
    if axis == "discipline":
        return {"bb": agg["bb"], "so": agg["so"], "pa": agg["pa"]}
    if axis == "starter_ip":
        return {"starter_outs": agg["starter_outs"], "outs": agg["outs"]}
    if axis == "pitch_k":
        return {"so_a": agg["so_a"], "pa_against": agg["pa_against"]}
    return {}


_RAW_KEY = {  # 軸 → raw 成分鍵（凍結 spec §0.2；discipline 為複合軸無單一 raw）
    "speed": "sba_rate", "smallball": "sh_rate", "power": "iso",
    "starter_ip": "starter_share", "pitch_k": "kpct", "defense": "der",
}


def build_team_style(
    code: str,
    by_team: dict[tuple[int, str], list[dict]],
    names: dict[tuple[int, str], str],
    in_progress_years: set[int],
    managers: dict[int, str],
) -> dict:
    """純塑形（單元測試對象）：逐季 z／raw／排名／計數＋教練時間標記。

    z 與排名對全季全部球隊算（rank_desc 對 z 由高至低），再抽出該 franchise
    的列；franchise 折疊沿 ``cpbl.franchises``（在 2018+ 資料域與 STYLE1
    凍結 FRANCHISE_MAP 一致：AJK011→AJL011）。
    """
    fc = franchise_of(code)
    seasons: list[dict] = []
    for year in sorted({y for y, _ in by_team}):
        teams = {t: recs for (y, t), recs in by_team.items() if y == year}
        aggs = {t: ts.aggregate_games(recs) for t, recs in teams.items()}
        raw = {t: ts.raw_axes(a) for t, a in aggs.items()}
        # 退化保護：任一隊任一成分分母為 0（極早季）→ 該季無法季內標準化，整季不出。
        if any(v is None for r in raw.values() for v in r.values()):
            continue
        z = ts.season_axis_z(raw)
        mine = next((t for t in z if franchise_of(t) == fc), None)
        if mine is None:
            continue
        axes = {}
        for axis in ts.AXES:
            z_by_team = {t: z[t][axis] for t in z}
            rk = _RAW_KEY.get(axis)
            # 聯盟平均 raw＝z-score 計算裡的同一個均值（同季全部球隊、算術平均），
            # 供歷史圖的「聯盟環境」參考線；不另算一套口徑。discipline 複合軸無單一 raw。
            league_mean = (round(sum(raw[t][rk] for t in z) / len(z), 6)
                           if rk else None)
            axes[axis] = {
                "z": round(z[mine][axis], 4),
                "raw": round(raw[mine][rk], 6) if rk else None,
                "league_raw_mean": league_mean,
                "rank": ts.rank_desc(z_by_team, mine),
                "counts": axis_counts(axis, aggs[mine]),
            }
        seasons.append({
            "year": year,
            "team_code": mine,
            "team_name": names.get((year, mine), mine),
            "n_teams": len(z),
            "in_progress": year in in_progress_years,
            "manager": managers.get(year),  # 僅時間標記；不可判定季為 None
            "axes": axes,
        })
    return {
        "team": code,
        "franchise": fc,
        # 口徑：全季（設計約束 7）；不接半季 ContextSwitcher。
        "scope": "full_season",
        "axes": [
            {"key": a, "label": ts.AXIS_LABELS[a], "semantics": AXIS_SEMANTICS[a]}
            for a in ts.AXES
        ],
        "seasons": seasons,
    }


def _in_progress_years(c) -> set[int]:
    """該年仍有「排在今天（含）之後、未完成」的一軍例行賽 → 「賽季進行中」（設計約束 8）。

    完成判定沿 ``cpbl.completion``；必須加「今天（含）之後」的未來界線：
    歷史年份的 0-0 列**不是**取消未補——2018/2025 各一場其實是真實的 0:0 和局
    （DATA-TIE-REMEDY1 已取官方 box 證據）。改用證據感知判準後它們算完成場，
    不再被誤計為 pending。球季打完（無未來場次）標注自動消失，不寫死年份。

    界線用**台北日**而非 ``CURRENT_DATE``（DATA-TZ-BOUNDARY1／AUDIT1 C12）：DB
    timezone 是 UTC，台北 00:00–07:59 期間 ``CURRENT_DATE`` 仍是前一日。這裡是
    **下界**（``>=``），UTC 落後的方向與上界相反——會把**昨天**未完成的場次也算成
    「今天之後待打」，使已打完的球季在晨間 8 小時被誤標為「進行中」。
    """
    from cpbl.completion import TAIPEI_TODAY_SQL, completed_games_sql_with_evidence

    rows = c.execute(
        "SELECT year, count(*) FILTER (WHERE NOT ("
        + completed_games_sql_with_evidence("games")
        + f") AND game_date >= {TAIPEI_TODAY_SQL}) "
        "FROM cpbl.games WHERE kind_code = 'A' AND year BETWEEN %s AND %s "
        "GROUP BY year",
        (ts.YEAR_FROM, ts.YEAR_TO),
    ).fetchall()
    return {int(y) for y, pending in rows if int(pending or 0) > 0}


def team_style_payload(code: str) -> dict:
    """IO 入口：載入 gamelog 聚合（request-time，唯讀）＋塑形。"""
    fc = franchise_of(code)
    with conn() as c:
        by_team = ts.load_team_games(c)
        names = ts.load_team_names(c)
        in_progress = _in_progress_years(c)

        def _coach_lookup(year: int) -> str | None:
            """當季一軍總教練（官網 coaches；pos 精確比對）。查無 → None。"""
            row = c.execute(
                "SELECT name FROM cpbl.coaches "
                "WHERE year = %s AND pos = '一軍總教練' AND team_code = %s",
                (year, fc),
            ).fetchone()
            return row[0].strip() if row and row[0] else None

        managers = fill_current_managers(managers_of(fc), in_progress, _coach_lookup)
    return build_team_style(code, by_team, names, in_progress, managers)
