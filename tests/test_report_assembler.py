from datetime import UTC, date, datetime

from cpbl.reports import assembler, readers


def test_report_keeps_box_source_time_scope_and_x_counts_without_fabricating_population(monkeypatch):
    x = {"year": 2026, "kind_code": "E", "game_sno": 1, "game_date": date(2026, 10, 9),
         "completed": True, "away_team_code": "ADD011", "home_team_code": "ACN011",
         "away_score": 1, "home_score": 4}
    later = {**x, "game_sno": 2, "game_date": date(2026, 10, 10), "home_score": 9}
    fetched = datetime(2026, 10, 10, 3, tzinfo=UTC)
    monkeypatch.setattr(readers, "games", lambda *_: [x, later])
    monkeypatch.setattr(readers, "schedules", lambda *_: [])
    monkeypatch.setattr(readers, "source_revisions", lambda *_: [])
    def versions(cur, season, kind, snos):
        assert (season, kind, snos) == (2026, "E", [1])
        return [{"game_sno": 1, "player_id": "0000000001", "source_version": "fixture-hash",
                 "fetched_at": fetched, "last_seen_at": fetched}]
    monkeypatch.setattr(readers, "pitching_sources", versions)
    def box(cur, season, kind, snos, role):
        if kind == "A":
            assert snos == []
            return []
        assert snos == [1]
        return [{"player_id": "0000000001", "name": "測試投手", "game_sno": 1,
                 "game_key": "2026/E/1", "team_code": "ADD011", "opponent_code": "ACN011",
                 "role_type": "最後一任", "outs": 2, "pitch_cnt": 19,
                 "pa": 4, "h": 2, "hr": 0, "er": 0, "bb": 1, "so": 1}] if role == "pitching" else []
    monkeypatch.setattr(readers, "box", box)
    monkeypatch.setattr(readers, "people", lambda *_: {})
    result = assembler.build_report(object(), 2026, "E", 1)
    assert result["anchor"]["through_game_keys"] == ["2026/E/1"]
    source = next(s for s in result["sources"] if s["source"] == "box_pitching")
    assert source["scope"] == {"year": 2026, "kind": "E", "role": "pitching", "player_id": "0000000001"}
    assert source["source_version"] == "fixture-hash" and source["fetched_at"] == fetched
    assert source["updated_at"] is None  # 取得時間不能冒官方更正發生時刻。
    assert source["covered_game_keys"] == ["2026/E/1"] and source["cutoff_basis"] == "through_X"
    assert all(not r["complete"] for r in result["population"])
    assert result["announcements"]["lineup"]["status"] == "unverified"
    player = result["players"][0]
    assert player["periods"]["series"]["counts"]["ip"] == "0.2"
    assert player["pitching_usage"]["appearances"][0]["role_type"] == "最後一任"
    assert player["ability"]["status"] == "source_unverified"
