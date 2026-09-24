"""生涯對戰的對手隊別判定（#201）：只陳述逐打席證據能支持的交手隊別。

官方對戰表的隊號是**爬取當時**對手的所屬隊（現任／末任），不是歷次交手時的隊別；
生涯列（year=9999）直接拿來標示或篩選，會把轉隊前的交手算到新東家名下。

本模組改以 published build 中 ``state='ready'`` 的逐打席紀錄（2018 起才有）重建
「對手交手時所屬隊」，再對照官方生涯打席數判定可信度：

- 證據打席數＝官方打席數 → ``confirmed``（可為一隊或多隊）
- 0 < 證據 < 官方 → ``partial``（已證實的隊＋其餘未知；2017 前交手、缺 build 等）
- 證據＝0、官方＝0、或證據 > 官方 → ``unknown``（對不上官方就不宣稱任何隊）

⛔ 只用於 career scope：本季／區間仍沿用官方隊號（#201 明列的限制，不在本卡修正）。
⛔ 不回推 2017 前的季表隊別：那是推論，不是交手證據。
統計欄一律不動，仍取官方對戰表。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from cpbl.franchises import franchise_of, franchise_prefixes

CONFIRMED, PARTIAL, UNKNOWN = "confirmed", "partial", "unknown"

# role → (主角 gamelog 表, gamelog 主角欄, PA 主角欄, PA 對手欄, 上半局時對手所屬隊欄)
# pre_state.half='1'＝上半局客隊進攻：打者視角的對手（投手）屬守備方＝主隊；
# 投手視角的對手（打者）屬進攻方＝客隊。先發與終結投手必屬同隊，故取終結投手不影響隊別。
_ROLE_SQL = {
    "batting": ("batting_gamelog", "hitter_acnt", "hitter_acnt", "end_pitcher_acnt",
                "home_team_code", "away_team_code"),
    "pitching": ("pitching_gamelog", "pitcher_acnt", "end_pitcher_acnt", "hitter_acnt",
                 "away_team_code", "home_team_code"),
}


def _evidence_sql(role: str, with_opponent: bool) -> str:
    gamelog, gl_col, self_col, opp_col, top_team, bottom_team = _ROLE_SQL[role]
    opp_filter = f" AND pa.{opp_col}=%(opp)s" if with_opponent else ""
    # 表名／欄名皆取自上方 role 白名單；值一律參數化。
    # 先以主角 gamelog 縮小場次再走 idx_game_pa_start_event；只比對官方生涯列
    # 爬取日（台北時區）之前的比賽，避免把官方尚未計入的場次算成證據。
    return f"""
        WITH g AS (
            SELECT DISTINCT year, game_sno FROM cpbl.{gamelog}
            WHERE {gl_col}=%(pid)s AND kind_code=%(kind)s
        ), pa AS (
            SELECT pa.{opp_col} AS opp_id, gm.game_date,
                   CASE WHEN pa.pre_state->>'half'='1' THEN gm.{top_team}
                        ELSE gm.{bottom_team} END AS team_code
            FROM g
            JOIN cpbl.game_plate_appearances pa
              ON pa.year=g.year AND pa.kind_code=%(kind)s AND pa.game_sno=g.game_sno
            JOIN cpbl.game_recap_builds b
              ON b.build_id=pa.build_id AND b.state='published'
            JOIN cpbl.games gm
              ON gm.year=pa.year AND gm.kind_code=pa.kind_code AND gm.game_sno=pa.game_sno
            WHERE pa.state='ready' AND pa.{self_col}=%(pid)s{opp_filter}
        )
        SELECT pa.opp_id, pa.team_code, count(*)
        FROM pa
        JOIN cpbl.batter_pitcher_matchups m
          ON m.kind_code=%(kind)s AND m.year=9999
         AND m.{"hitter_acnt" if role == "batting" else "pitcher_acnt"}=%(pid)s
         AND m.{"pitcher_acnt" if role == "batting" else "hitter_acnt"}=pa.opp_id
        WHERE pa.game_date < (m.updated_at AT TIME ZONE 'Asia/Taipei')::date
          AND pa.team_code IS NOT NULL
        GROUP BY pa.opp_id, pa.team_code
    """  # noqa: S608


def load_team_evidence(
    cur: Any,
    player_id: str,
    role: str,
    kind_code: str,
    opponent_id: str | None = None,
) -> dict[str, dict[str, int]]:
    """主角對每位對手的逐打席隊別證據：``{opp_id: {交手時隊號: 打席數}}``。"""
    if role not in _ROLE_SQL:
        raise ValueError(f"不支援的 role：{role}")
    params = {"pid": player_id, "kind": kind_code, "opp": opponent_id}
    cur.execute(_evidence_sql(role, opponent_id is not None), params)
    evidence: dict[str, dict[str, int]] = {}
    for opp_id, team_code, count in cur.fetchall():
        teams = evidence.setdefault(opp_id, {})
        teams[team_code] = teams.get(team_code, 0) + int(count)
    return evidence


def classify_team_evidence(
    official_pa: int | None,
    evidence: Mapping[str, int] | None,
) -> tuple[list[str], str]:
    """依官方打席數與證據判定 ``(已證實 franchise 清單, 狀態)``。"""
    official = official_pa or 0
    teams = {code: n for code, n in (evidence or {}).items() if n > 0}
    recorded = sum(teams.values())
    if official <= 0 or recorded <= 0 or recorded > official:
        return [], UNKNOWN
    franchises = sorted({franchise_of(code) for code in teams})
    return franchises, CONFIRMED if recorded == official else PARTIAL


def annotate_career_opponent_teams(
    items: Iterable[dict[str, Any]],
    evidence: Mapping[str, Mapping[str, int]],
    team_names: Mapping[str, str],
) -> None:
    """就地為生涯對手列加上 ``opp_franchises``／``opp_team_status``。

    舊欄位 ``opp_team_code``／``opp_franchise``／``opp_team`` 只在「已確認且恰一隊」時
    帶值（改為該交手隊），其餘清成 null——任何只讀舊欄位的畫面都不會再顯示錯隊。
    """
    for item in items:
        franchises, status = classify_team_evidence(
            item.get("plate_appearances"), evidence.get(item["opp_id"]),
        )
        item["opp_franchises"] = franchises
        item["opp_team_status"] = status
        single = franchises[0] if status == CONFIRMED and len(franchises) == 1 else None
        item["opp_team_code"] = single
        item["opp_franchise"] = single
        item["opp_team"] = team_names.get(single[:3]) if single else None


def matches_team(franchises: Iterable[str], team_code: str) -> bool:
    """已證實隊別中是否含篩選隊（接受歷史隊碼，依 franchise 展開）。"""
    allowed = franchise_prefixes(team_code)
    return any(code[:3] in allowed for code in franchises)


def load_team_names(cur: Any) -> dict[str, str]:
    """三碼隊碼 → 隊名（與清單既有 ``opp_team`` 同來源 ``cpbl.teams``）。"""
    cur.execute("SELECT team_id, name FROM cpbl.teams")
    return {team_id: name for team_id, name in cur.fetchall()}
