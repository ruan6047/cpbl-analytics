"""#391 WP1：聯盟收官判定（``cpbl.season_close``）。

黃金樣本一律是真實列（驗收 6、⛔ 不自造）：
- ``tests/fixtures/season_close_391_real.json``：本機 DB 唯讀抽取的 2026 E／C、2026 官方戰績、2011／2025 F
  （抽取 SQL、時點見 ``_provenance``）。
- ``tests/fixtures/getgamedatas_F_2026_raw.json``：2026 F 官網 getgamedatas 原始回應（#391 第二輪需求研究）。

「系列未分勝負」只截斷真實列的完賽狀態（例：2026 C 只算到 G5＝3:2），不改比分、不造隊碼。
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from cpbl import postseason_contract as pc
from cpbl import season_close as sc

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REAL = json.loads((FIXTURES / "season_close_391_real.json").read_text(encoding="utf-8"))
RAW_F_2026 = json.loads((FIXTURES / "getgamedatas_F_2026_raw.json").read_text(encoding="utf-8"))
DRAGON, BRO = "AAA011", "ACN011"
NOW = datetime(2026, 10, 29, 4, 0, tzinfo=UTC)   # 台北 10/29 12:00


def major_games() -> list[pc.GameFact]:
    return [pc.GameFact(year=2026, kind_code=k, game_sno=s, game_date=date.fromisoformat(d),
                        away_team_code=away, home_team_code=home, away_score=a, home_score=h, completed=done,
                        official_status="final" if done else "scheduled")
            for k, s, d, away, home, a, h, done in REAL["major_2026"]]


def standings() -> pc.StandingsFacts:
    return pc.standings_facts((REAL["standings_source_2026"], REAL["standings_2026"]))


def major(games: list[pc.GameFact]) -> sc.LeagueClosure:
    rule = pc.season_rule(2026)
    series, _ = pc.compute_series(rule, standings(), games, year=2026)
    return sc.major_closure(2026, series, games, rule_version=rule.rule_version)


def farm_rows(year: int) -> list[sc.FarmGame]:
    return [sc.FarmGame(year, sno, date.fromisoformat(d), away, home, a, h, done, final)
            for sno, d, away, home, a, h, done, final in REAL["farm"][str(year)]]


def farm_2026_from_raw() -> list[sc.FarmGame]:
    """官網原文 → FarmGame。完賽與官方 final 用與 ``season_close.FARM_GAMES_SQL`` 相同的語意：
    F 不在官方完賽範圍（比分 > 0 且日期不晚於今天即完賽）；官方 final＝PresentStatus=1 且 GameResult='0'
    （``completion.official_final_sql`` 的 raw 組合）。"""
    entries = json.loads(json.loads(RAW_F_2026["body"])["GameDatas"])
    out = []
    for e in entries:
        day = date.fromisoformat(e["GameDate"][:10])
        a, h = int(e["VisitingScore"]), int(e["HomeScore"])
        out.append(sc.FarmGame(int(e["Year"]), int(e["GameSno"]), day, e["VisitingTeamCode"], e["HomeTeamCode"],
                               a, h, a + h > 0 and day <= NOW.date(),
                               int(e["PresentStatus"]) == 1 and str(e["GameResult"]) == "0"))
    return out


# —— 驗收 6：2026 實際資料會觸發 ——

def test_2026_major_closes_after_c6_and_marks_c7_not_needed():
    got = major(major_games())
    assert (got.closed, got.status, got.champion_team_code) == (True, "decided", DRAGON)
    assert got.decided_by == (2026, "C", 6) and got.decided_game_date == date(2026, 10, 26)
    assert got.not_needed_keys == frozenset({(2026, "C", 7)})


def test_2026_farm_closes_on_first_to_three_from_official_raw():
    games = farm_2026_from_raw()
    assert len(games) == 3
    got = sc.tally_farm_series(2026, games)
    assert (got.closed, got.status, got.champion_team_code) == (True, "decided", "AEO022")
    assert got.decided_by == (2026, "F", 3) and got.not_needed_keys == frozenset()


def test_2025_farm_real_series_closes_at_g5():
    got = sc.tally_farm_series(2025, farm_rows(2025))
    assert (got.closed, got.champion_team_code, got.decided_by) == (True, "AKP022", (2025, "F", 5))


# —— 驗收 6：系列未分勝負不觸發 ——

def test_2026_major_after_g5_three_two_does_not_close():
    """真實 C1–C5（味全 3 勝、兄弟 2 勝），C6 起尚未完賽 ⇒ 不收官、沒有 not_needed。"""
    games = [replace(g, completed=False, official_status="scheduled")
             if g.kind_code == "C" and g.game_sno >= 6 else g for g in major_games()]
    got = major(games)
    assert (got.closed, got.status) == (False, "undecided")
    assert not any(k[1] == "C" for k in got.not_needed_keys)


def test_2011_farm_with_real_tie_does_not_close():
    """2011 F G3 真和局 7:7（裁定 #12：和局停下不切，等人判斷）。"""
    got = sc.tally_farm_series(2011, farm_rows(2011))
    assert (got.closed, got.status) == (False, "undecided_tie")


def test_2026_farm_decider_must_be_official_final():
    games = farm_2026_from_raw()
    games[-1] = replace(games[-1], official_final=False)
    got = sc.tally_farm_series(2026, games)
    assert (got.closed, got.status, got.reason) == (False, "undecided", "decisive_game_not_official_final")


def test_2026_farm_after_two_games_does_not_close():
    got = sc.tally_farm_series(2026, [replace(g, completed=False) if g.game_sno == 3 else g
                                      for g in farm_2026_from_raw()])
    assert (got.closed, got.status) == (False, "undecided")


def test_farm_completed_game_after_decided_is_unknown_not_closed():
    """先達 3 勝後還有完賽列＝判準與事實矛盾（例：賽制改回七戰四勝），fail-open 為「繼續爬」。"""
    games = farm_rows(2025)
    extra = replace(games[-1], game_sno=6, game_date=date(2025, 10, 6))
    got = sc.tally_farm_series(2025, [*games, extra])
    assert (got.closed, got.status, got.reason) == (False, "unknown", "game_after_decided")


def test_farm_without_rows_is_no_data_and_open():
    got = sc.tally_farm_series(2026, [])
    assert (got.closed, got.status) == (False, "no_data")


def test_major_unknown_series_never_closes():
    """戰績讀不到 ⇒ compute_series 回 unknown ⇒ 不收官（主風險：提早停爬）。"""
    rule = pc.season_rule(2026)
    games = major_games()
    series, _ = pc.compute_series(rule, None, games, year=2026)
    got = sc.major_closure(2026, series, games, rule_version=rule.rule_version)
    assert (got.closed, got.status) == (False, "unknown")


# —— R1 甲：年度規則開放式沿用 ——

def test_season_rule_is_open_ended_from_2027_and_marked_assumed():
    r27 = pc.season_rule(2027)
    assert r27 is not None and r27.assumed and r27.rule_version == pc.SEASON_RULES[2026].rule_version
    assert r27.announcement is None and r27.arrangement == ()
    assert pc.season_rule(2026) is pc.SEASON_RULES[2026] and not pc.SEASON_RULES[2026].assumed
    assert pc.season_rule(2021) is None


def test_assumed_year_context_reports_sourced_assumed():
    ctx = pc.compute_series_context(pc.SeriesInputs(year=2030, games=[], standings=None), now=NOW)
    assert ctx["rule_status"] == "sourced_assumed"
    assert ctx["source_manifest"][0]["status"] == "assumed"


# —— 顯示面的契約：not_needed 不進 coverage ——

def test_series_context_coverage_ignores_not_needed_c7():
    ctx = pc.compute_series_context(pc.SeriesInputs(year=2026, games=major_games(), standings=standings()), now=NOW)
    assert ctx["series"]["C"]["series_status"] == "decided"
    assert ctx["coverage"] == "covered" and ctx["as_of"]["pending_games"] == []
    # 真實 C 列因延賽與公告日期錯開；以場鍵找格（不依公告格名），G7 列顯示為 not_needed。
    slot7 = next(s for s in ctx["arrangement"]["slots"]
                 if s["game_key"] and (s["game_key"]["kind_code"], s["game_key"]["game_sno"]) == ("C", 7))
    assert slot7["display_status"] == "not_needed" and slot7["hidden_not_needed"]


def test_series_context_coverage_still_flags_real_pending_games():
    """未分勝負時過期未完賽列照舊是 pending_update（不得被收官邏輯吃掉）。"""
    games = [replace(g, completed=False, official_status="scheduled")
             if g.kind_code == "C" and g.game_sno >= 6 else g for g in major_games()]
    ctx = pc.compute_series_context(pc.SeriesInputs(year=2026, games=games, standings=standings()), now=NOW)
    assert ctx["coverage"] == "pending_update"
    assert {(p["kind_code"], p["game_sno"]) for p in ctx["as_of"]["pending_games"]} == {("C", 6), ("C", 7)}


# —— override 與字彙 ——

def test_override_open_reopens_without_hiding_status():
    got = sc.apply_override(major(major_games()), {sc.OVERRIDE_ENV: "open"})
    assert (got.closed, got.status, got.override) == (False, "decided", "open")
    assert sc.apply_override(major(major_games()), {}).closed is True


def test_parse_and_format_leagues():
    assert sc.parse_leagues("farm, major") == frozenset({"major", "farm"})
    assert sc.parse_leagues("") == frozenset()
    assert sc.format_leagues({"farm", "major"}) == "major,farm"
    assert sc.kinds_of({"major"}) == ("A", "E", "C") and sc.kinds_of({"farm"}) == ("D", "F")
    with pytest.raises(ValueError):
        sc.parse_leagues("major,A")


def test_closure_json_shape():
    body = major(major_games()).to_json()
    assert body["decided_by"] == {"year": 2026, "kind_code": "C", "game_sno": 6}
    assert body["not_needed"] == [{"year": 2026, "kind_code": "C", "game_sno": 7}]
    assert body["decided_game_date"] == "2026-10-26"


# —— 驗收 7：不刪既有 games 列 ——

def test_no_code_path_deletes_games_rows():
    """全 repo 的 src／scripts 沒有任何 DELETE／TRUNCATE cpbl.games；收官判定模組只有 SELECT。
    真實列數前後相等的唯讀證據另存 ~/.wf-evidence/cpbl-analytics/391/exec-2/acc7-games-count-2026.json。"""
    import re

    root = Path(__file__).resolve().parents[1]
    pattern = re.compile(r"(DELETE\s+FROM|TRUNCATE[^;\n]*)\s+cpbl\.games\b", re.IGNORECASE)
    hits = [str(p.relative_to(root)) for base in ("src", "scripts") for p in (root / base).rglob("*")
            if p.suffix in (".py", ".sh", ".sql") and pattern.search(p.read_text(encoding="utf-8", errors="ignore"))]
    assert hits == []
    source = (root / "src" / "cpbl" / "season_close.py").read_text(encoding="utf-8")
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|TRUNCATE)\b", source.split('"""', 2)[2])
