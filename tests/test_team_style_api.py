"""UX-TEAM-STYLE1 API view 塑形單元測試（不碰 DB）。

軸計算數學性質在 tests/test_team_style.py；本檔測 view 層：
軸級語意標注、教練時間標記資源（TEAM-STYLE2 判定的機械抽取）、
build_team_style 的排名／franchise 折疊／退化保護。
"""

from __future__ import annotations

import json
from pathlib import Path

from cpbl.api.team_style import (
    AXIS_SEMANTICS,
    SEMANTICS_VALUES,
    axis_counts,
    build_team_style,
    managers_of,
    season_managers,
)
from cpbl.models.team_style import AXES, BAT_KEYS, PIT_KEYS

REPO = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# 軸級語意標注（設計約束 3：判定在後端做一次）
# ---------------------------------------------------------------------------


def test_semantics_covers_all_axes_with_valid_values():
    assert set(AXIS_SEMANTICS) == set(AXES)
    assert set(AXIS_SEMANTICS.values()) <= SEMANTICS_VALUES


def test_semantics_frozen_assignments():
    """研究定案（TEAM-STYLE1_RESULTS §2）：逐軸語意不得改判。"""
    assert AXIS_SEMANTICS["discipline"] == "cross_season_stable"  # 唯一可標跨季延續
    assert AXIS_SEMANTICS["starter_ip"] == "current_season_only"  # 必標「本季」
    assert AXIS_SEMANTICS["pitch_k"] == "current_season_only"
    assert AXIS_SEMANTICS["defense"] == "numbers_only"            # 零形容詞
    for axis in ("speed", "smallball", "power"):
        assert AXIS_SEMANTICS[axis] == "usable"


def test_defense_counts_empty():
    """守備效率列只有數字與排名：不提供額外計數欄。"""
    agg = dict.fromkeys(BAT_KEYS + PIT_KEYS, 1)
    assert axis_counts("defense", agg) == {}


# ---------------------------------------------------------------------------
# 教練時間標記資源（直接取 TEAM-STYLE2 artifact 判定，不重新發明規則）
# ---------------------------------------------------------------------------


def test_managers_resource_matches_style2_artifact():
    """打包資源必須是 TEAM-STYLE2 artifact season_managers 的機械抽取。"""
    artifact = json.loads(
        (REPO / "docs/research/team_style2_metrics.json").read_text(encoding="utf-8"))
    expected = [
        {"franchise": r["franchise"], "year": r["year"],
         "main_manager": r["main_manager"], "detail": r["detail"]}
        for r in artifact["season_managers"]
    ]
    assert list(season_managers()) == expected
    assert len(expected) == 39


def test_managers_of_excludes_undetermined_and_out_of_coverage():
    add = managers_of("ADD011")
    assert 2019 not in add                    # 場數平手 → 不可判定 → 不標
    assert add[2018] == "黃甘霖"
    assert add[2020] == "林岳平"
    assert managers_of("ACN011")[2023] == "彭政閔"  # 季中換帥：場數最多者
    assert 2026 not in managers_of("AAA011")  # 覆蓋外年份不標
    assert managers_of("AJL011")[2018] == "洪一中"  # Lamigo 年併入樂天 franchise


# ---------------------------------------------------------------------------
# build_team_style：排名／franchise 折疊／退化保護（合成資料）
# ---------------------------------------------------------------------------


def _game(**kw) -> dict:
    """一場合成隊場計數（預設值使所有軸分母非 0）。"""
    base = {
        "pa": 40, "ab": 34, "h": 9, "singles": 6, "tb": 14, "sh": 1, "sf": 1,
        "bb": 4, "hbp": 1, "so": 8, "sb": 1, "cs": 1,
        "outs": 27, "starter_outs": 18, "pa_against": 38, "h_a": 8, "hr_a": 1,
        "bb_a": 3, "hbp_a": 1, "so_a": 7,
        "game_date": "2024-04-01", "game_sno": 1,
    }
    base.update(kw)
    return base


def _fixture() -> dict[tuple[int, str], list[dict]]:
    return {
        # 2019：AJK011（Lamigo 舊碼）盜壘企圖遠多於對手 → speed 排第 1
        (2019, "AJK011"): [_game(sb=9, cs=3)],
        (2019, "ACN011"): [_game(sb=0, cs=0)],
        # 2024：三隊，AJL011 居中
        (2024, "AJL011"): [_game(sb=4, cs=2)],
        (2024, "ACN011"): [_game(sb=9, cs=3)],
        (2024, "AAA011"): [_game(sb=0, cs=0)],
        # 2025：ACN011 打擊 pa=0 → 退化 → 整季不出
        (2025, "AJL011"): [_game()],
        (2025, "ACN011"): [_game(pa=0, ab=0, singles=0, bb=0, hbp=0)],
    }


def test_build_ranks_and_franchise_folding():
    names = {(2019, "AJK011"): "Lamigo", (2024, "AJL011"): "樂天桃猿"}
    out = build_team_style(
        "AJL011", _fixture(), names,
        in_progress_years={2024}, managers={2019: "洪一中"})
    assert out["franchise"] == "AJL011"
    assert out["scope"] == "full_season"
    assert [a["key"] for a in out["axes"]] == list(AXES)
    years = [s["year"] for s in out["seasons"]]
    assert years == [2019, 2024]              # 2025 退化整季不出；折疊含 AJK011
    s19, s24 = out["seasons"]
    assert s19["team_code"] == "AJK011" and s19["team_name"] == "Lamigo"
    assert s19["axes"]["speed"]["rank"] == 1 and s19["n_teams"] == 2
    assert s19["manager"] == "洪一中" and s24["manager"] is None
    assert s24["axes"]["speed"]["rank"] == 2 and s24["n_teams"] == 3
    assert s24["in_progress"] is True and s19["in_progress"] is False
    # z 為季內聯盟標準化：兩隊時互為相反數
    assert abs(s19["axes"]["speed"]["z"] - 1.0) < 1e-9
    # counts 與 raw 同源（speed 明細＝盜壘企圖組成）
    assert s19["axes"]["speed"]["counts"] == {"sb": 9, "cs": 3}
    # defense 無額外計數（設計約束 3）
    assert s24["axes"]["defense"]["counts"] == {}
    # discipline 是複合軸，無單一 raw；其餘軸 raw 皆給
    assert s24["axes"]["discipline"]["raw"] is None
    assert s24["axes"]["power"]["raw"] is not None
