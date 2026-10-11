from datetime import UTC, date, datetime

import pytest

from cpbl.reports import assembler, readers
from cpbl.reports.context import bounded_context


def enriched_inputs(monkeypatch):
    x = {"year": 2026, "kind_code": "E", "game_sno": 1, "game_date": date(2026, 10, 9),
         "completed": True, "away_team_code": "ADD011", "home_team_code": "ACN011",
         "away_score": 1, "home_score": 4}
    a = {**x, "kind_code": "A", "game_date": date(2026, 9, 30)}
    schedule = {"year": 2026, "kind_code": "E", "game_sno": 2,
                "raw_game_date": date(2026, 10, 10), "raw_present_status": 1,
                "raw_game_result": "", "is_play_ball": "N", "payload_hash": "fixture",
                "fetched_at": datetime(2026, 10, 10, tzinfo=UTC),
                "away_p": "dual", "home_p": "other-p",
                "raw_payload": {"VisitingTeamCode": "ADD011", "HomeTeamCode": "ACN011"}}
    games, schedules = [a, x], [schedule]
    monkeypatch.setattr(readers, "games", lambda *_: games)
    monkeypatch.setattr(readers, "schedules", lambda *_: schedules)
    monkeypatch.setattr(readers, "lineup_revisions", lambda *_: [])
    monkeypatch.setattr(readers, "source_revisions", lambda *_: [])
    monkeypatch.setattr(readers, "pitching_sources", lambda *_: [])
    def box(cur, season, kind, snos, role):
        common = {"game_sno": 1, "game_key": f"2026/{kind}/1", "team_code": "ADD011",
                  "opponent_code": "ACN011", "name": "fixture", "pa": 4, "h": 1,
                  "hr": 0, "bb": 1, "so": 1}
        if role == "pitching":
            return [{**common, "player_id": "pitch-only", "role_type": "最後一任",
                     "outs": 2, "pitch_cnt": 19, "er": 0}]
        return [{**common, "player_id": pid, "ab": 3, "b2": 0, "b3": 0,
                 "hbp": 0, "sf": 0, "ibb": 0} for pid in ("hitter", "dual")]
    monkeypatch.setattr(readers, "box", box)
    monkeypatch.setattr(readers, "people", lambda *_: {})
    monkeypatch.setattr(readers, "fielding", lambda *_: [])
    monkeypatch.setattr(assembler.background, "current_matches", lambda *_: {})
    monkeypatch.setattr(assembler.background, "team_background", lambda *_: [])
    monkeypatch.setattr(assembler.background, "player_background", lambda *a, **k: {})
    return x, games, schedules


def test_enrichment_pairs_only_batting_roles_and_preserves_dual_player(monkeypatch):
    x, games, schedules = enriched_inputs(monkeypatch)
    calls = []
    def pairs(cur, season, hitters, pitchers):
        calls.append(hitters)
        return {(pid, "other-p"): {"pitcher_acnt": "other-p", "pa": 3, "ab": 3,
                                  "h": 1, "b2": 0, "b3": 0, "hr": 0, "bb": 0,
                                  "hbp": 0, "sf": 0, "so": 2, "updated_at": None}
                for pid in ("pitch-only", "dual")}
    monkeypatch.setattr(readers, "matchups", pairs)
    context = bounded_context(x, games, schedules)
    assert context["rows"][0]["game_date"] == "2026-10-10"  # DB date 已經統一 JSON 化。
    result = assembler.build_report(object(), 2026, "E", 1, "E", 2, context["context_hash"])
    assert set(calls[0]) == {"hitter", "dual"}
    pitchers = [p for p in result["players"] if p["role"] == "pitching"]
    assert all(p["vs_starter"]["status"] == "not_applicable" and p["vs_starter"]["pitcher_id"] is None for p in pitchers)
    dual = next(p for p in result["players"] if p["player_id"] == "dual" and p["role"] == "batting")
    assert dual["vs_starter"]["status"] == "available"


def test_usage_box_coverage_is_explicit_and_separate_from_roster(monkeypatch):
    enriched_inputs(monkeypatch)
    result = assembler.build_report(object(), 2026, "E", 1)
    pitcher = next(p for p in result["players"] if p["player_id"] == "pitch-only")
    assert not result["population"][0]["complete"]
    assert pitcher["pitching_usage"]["coverage_status"] == "complete"
    assert pitcher["pitching_usage"]["dates_trusted"] is True


def test_missing_series_box_does_not_claim_precise_usage_interval(monkeypatch):
    x, games, _ = enriched_inputs(monkeypatch)
    games.append({**x, "game_sno": 2, "game_date": date(2026, 10, 10)})
    result = assembler.build_report(object(), 2026, "E", 2)
    pitcher = next(p for p in result["players"] if p["player_id"] == "pitch-only")
    assert pitcher["pitching_usage"]["coverage_status"] == "partial"
    assert pitcher["pitching_usage"]["consecutive_days"] is None
    assert pitcher["pitching_usage"]["days_to_next"] is None


def test_identical_game_sides_rejected_before_roster_or_box_reads(monkeypatch):
    x, _, _ = enriched_inputs(monkeypatch)
    monkeypatch.setattr(readers, "games", lambda *_: [{**x, "home_team_code": x["away_team_code"]}])
    with pytest.raises(ValueError, match="隊伍"):
        assembler.build_report(object(), 2026, "E", 1)


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



def official_inputs(monkeypatch):
    from cpbl.reports.official_population import load
    x,games,schedules=enriched_inputs(monkeypatch)
    original=readers.box
    ids={"pitch-only":"0000006818","hitter":"0000006716","dual":"0000003645"}
    def box(*args):
        return [{**r,"player_id":ids[r["player_id"]],"name":"年度別名"} for r in original(*args)]
    monkeypatch.setattr(readers,"box",box)
    return load(2026,"E"),x,games,schedules


def test_all_64_registered_members_present_with_literal_names_and_honest_provenance(monkeypatch):
    records,_,_,_=official_inputs(monkeypatch)
    monkeypatch.setattr(readers,"box",lambda *_: [])
    result=assembler.build_report(object(),2026,"E",1,population_records=records)
    assert len(result["players"])==64
    assert all(r["complete"] and r["registration_complete"] for r in result["population"])
    official={m["player_id"]:m["name"] for r in records for m in r["members"]}
    assert {p["player_id"]:p["name"] for p in result["players"]}==official
    assert all(p["periods"]["series"]["status"]=="missing" for p in result["players"])
    sources=[s for s in result["sources"] if s["source"]=="official_registration"]
    assert len(sources)==2
    for source in sources:
        assert source["published_at"] is None and source["published_precision"]=="date"
        assert source["published_date"]=="2026-10-08"
        assert source["fetched_at"] is None and source["updated_at"] is None
        assert source["observed_at"]=="2026-10-11T17:33:07.351Z"
        assert source["identity_verified_at"]=="2026-10-11T18:56:05.097767+00:00"
    assert [{k:v for k,v in s.items() if k!="read_at"} for s in sources]==result["journey_context"]["population_sources"]


def test_game_range_rows_plus_registered_mother_do_not_prove_nonappearance(monkeypatch):
    records,_,_,_=official_inputs(monkeypatch)
    result=assembler.build_report(object(),2026,"E",1,population_records=records)
    assert all(r["complete"] for r in result["population"])
    unobserved=next(p for p in result["players"] if p["player_id"]=="0000007293")
    period=unobserved["periods"]["series"]
    assert period["coverage_status"]=="complete"  # 現有 game-range：同隊每場至少一row。
    assert period["status"]=="missing"  # 不是全box的陰性出場證據。
    assert period["counts"]["ip"] is None and period["sample"]["pa"] is None
    assert unobserved["pitching_usage"] is None
    observed=next(p for p in result["players"] if p["player_id"]=="0000006818")
    assert observed["name"]=="髙塩將樹" and observed["periods"]["series"]["counts"]["ip"]=="0.2"


def test_observed_outside_official_registration_remains_visible_and_conflict_is_explicit(monkeypatch):
    records,_,_,_=official_inputs(monkeypatch)
    original=readers.box
    def box(*args):
        rows=original(*args)
        return rows+[{**rows[0],"player_id":"9999999999","name":"名單外觀測"}] if args[-1]=="batting" else rows
    monkeypatch.setattr(readers,"box",box)
    result=assembler.build_report(object(),2026,"E",1,population_records=records)
    lions=next(r for r in result["population"] if r["team_code"]=="ADD011")
    assert len(lions["members"])==32 and lions["registration_complete"] is True
    assert lions["complete"] is False and lions["status"]=="conflict"
    assert lions["observed_outside_population"]==["9999999999"]
    assert any(p["player_id"]=="9999999999" and p["name"]=="名單外觀測" for p in result["players"])
    assert len(result["players"])==65


def test_enrichment_requires_same_official_population_version(monkeypatch):
    records,_,_,_=official_inputs(monkeypatch)
    base=assembler.build_report(object(),2026,"E",1,population_records=records)
    changed=[{**r,"roster_version":"changed-version"} for r in records]
    from cpbl.reports.context import ContextChanged
    with pytest.raises(ContextChanged):
        assembler.build_report(object(),2026,"E",1,"E",2,base["journey_context"]["context_hash"],population_records=changed)



def test_same_batch_lineup_used_for_context_and_output_without_inventing_mother(monkeypatch):
    from cpbl.ingest.lineup_announcements import content_hash, project
    records,_,_,_=official_inputs(monkeypatch)
    source_ids=[f"900000000{i}" for i in range(1,10)]
    positions=["C","1B","2B","3B","SS","LF","CF","RF","DH"]
    raw={"GameId":"2026-E-2","GameSno":2,"KindCode":"E","PreExeDate":"2026-10-10T17:05:00","GameStatus":"SCHEDULED",
         "Visiting":{"Team":{"Code":"ADD011"},"Hitters":[{"Lineup":i,"HitterAcnt":pid,"HitterName":f"公告{i}","DefendStation":pos} for i,(pid,pos) in enumerate(zip(source_ids,positions,strict=True),1)]},
         "Home":{"Team":{"Code":"ACN011"},"Hitters":[]}}
    payload=project("2026-E-2",raw)
    revision={"year":2026,"kind_code":"E","game_sno":2,"source_type":"stats_datagame","source_url":"https://stats.cpbl.com.tw/api/proxy/v1/games/2026-E-2","raw_status":"SCHEDULED","raw_payload":payload,"content_hash":content_hash(payload),"fetched_at":datetime(2026,10,10,1,tzinfo=UTC),"last_seen_at":datetime(2026,10,10,1,tzinfo=UTC)}
    calls=[]
    monkeypatch.setattr(readers,"matchups",lambda *args: {})
    monkeypatch.setattr(readers,"lineup_revisions",lambda *args:calls.append(args) or [revision])
    base=assembler.build_report(object(),2026,"E",1,population_records=records)
    assert len(calls)==1
    calls.clear()
    enriched=assembler.build_report(object(),2026,"E",1,"E",2,base["journey_context"]["context_hash"],population_records=records)
    assert len(calls)==1
    lineup=enriched["announcements"]["lineup"]
    assert lineup["team_evidence"]["ADD011"]["status"]=="announced" and lineup["status"]=="partial"
    assert "is_play_ball" not in lineup["pregame_evidence"]
    assert {i["player_id"] for i in lineup["items"]}==set(source_ids)
    assert all(any(p["player_id"]==pid and p["role"]=="batting" and p["name"]==f"公告{i}" for p in enriched["players"]) for i,pid in enumerate(source_ids,1))
    assert all(len(r["members"])==32 for r in enriched["population"])
    assert enriched["population"]==base["population"]  # 公告9不當完整母體或實際使用。
