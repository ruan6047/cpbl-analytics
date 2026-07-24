"""INGEST-GAME-TM-REFACTOR1 Gate 3：shadow harness 純邏輯單元測試（DB-free／network-free）。

只測 pure 函式（賽程分類、本機/官方狀態交叉核對、逐格對帳），不觸碰 DB 或 httpx；
IO 部分（fetch_schedule_month／run_shadow_cycle）留給實機驗證（見 handoff 報告的
第一次 run 紀錄）。fixture 欄位形狀取自 2026-07-24 對 stats.cpbl 的實測抽樣
（GameId/GameStatus/SkipTrackman/Visiting/Home/Field/PreExeDate）。
"""

from __future__ import annotations

from cpbl.ingest.game_tm_shadow import (
    ScheduleRow,
    classify_schedule,
    dedupe_latest_per_game,
    diff_rows,
    diff_schedule_status,
    parse_schedule_row,
    skip_trackman_anomaly,
)


def _sched(game_id: str, status: str, *, skip: bool = False, v: int = 0, h: int = 0,
          pre_exe_date: str = "2026-07-20T18:35:00") -> dict:
    _, kind, sno = game_id.split("-")
    return {
        "GameId": game_id, "SkipTrackman": skip, "GameStatus": status,
        "Visiting": {"Team": {"Code": "AJL011"}, "Score": v},
        "Home": {"Team": {"Code": "ACN011"}, "Score": h},
        "Field": {"No": "F19", "Abbe": "洲際"},
        "KindCode": kind, "GameSno": int(sno), "PreExeDate": pre_exe_date,
    }


def test_parse_schedule_row_year_from_game_id() -> None:
    """GameId 前綴年份優先於呼叫端傳入的 fallback_year（例如跨年窗口時保護正確歸年）。"""
    row = parse_schedule_row(_sched("2026-A-167", "FINISHED", v=1, h=0), fallback_year=1999)
    assert row is not None
    assert row.year == 2026 and row.kind_code == "A" and row.game_sno == 167
    assert row.game_status == "FINISHED" and row.visiting_score == 1 and row.home_score == 0


def test_parse_schedule_row_missing_identity_skipped() -> None:
    """缺 KindCode/GameSno/GameStatus 的殘缺物件回 None，不硬湊。"""
    assert parse_schedule_row({"GameId": "2026-A-1"}, fallback_year=2026) is None


def test_classify_schedule_known_and_unknown_status() -> None:
    """延期/保留賽/未開打/完賽四態各自入桶；未知狀態（官方新增值）進 UNKNOWN 不崩潰。"""
    rows = [
        parse_schedule_row(_sched("2026-A-1", "FINISHED", v=3, h=2), 2026),
        parse_schedule_row(_sched("2026-A-2", "POSTPONED"), 2026),
        parse_schedule_row(_sched("2026-A-3", "RESERVED"), 2026),
        parse_schedule_row(_sched("2026-A-4", "SCHEDULED"), 2026),
        parse_schedule_row(_sched("2026-A-5", "SUSPENDED"), 2026),  # 假設官方未來新增值
    ]
    buckets = classify_schedule(rows)  # type: ignore[arg-type]
    assert [r.game_sno for r in buckets["FINISHED"]] == [1]
    assert [r.game_sno for r in buckets["POSTPONED"]] == [2]
    assert [r.game_sno for r in buckets["RESERVED"]] == [3]
    assert [r.game_sno for r in buckets["SCHEDULED"]] == [4]
    assert [r.game_sno for r in buckets["UNKNOWN"]] == [5]


def test_reserved_and_scheduled_both_zero_zero_but_distinct_status() -> None:
    """保留賽與未開打皆 0-0（不能靠比分分辨），必須用官方 GameStatus 區分。"""
    reserved = parse_schedule_row(_sched("2026-A-10", "RESERVED"), 2026)
    scheduled = parse_schedule_row(_sched("2026-A-11", "SCHEDULED"), 2026)
    assert reserved.visiting_score == 0 and reserved.home_score == 0
    assert scheduled.visiting_score == 0 and scheduled.home_score == 0
    assert reserved.game_status != scheduled.game_status


def test_dedupe_latest_per_game_keeps_most_recent_status() -> None:
    """同一 game_sno 延期/保留賽改期會在賽程 feed 留下多筆歷史記錄（不同 PreExeDate）；
    去重須保留「最新一筆」而非任意順序，否則 FINISHED 可能被較舊的 POSTPONED/RESERVED
    覆蓋（2026-07-24 實測 2026-A-151 撞到：POSTPONED@06-09 → RESERVED@06-25 →
    FINISHED@06-28 三筆同時存在同月回應）。"""
    rows = [
        parse_schedule_row(_sched("2026-A-151", "POSTPONED", pre_exe_date="2026-06-09T18:35:00"), 2026),
        parse_schedule_row(_sched("2026-A-151", "FINISHED", v=3, h=2, pre_exe_date="2026-06-28T17:05:00"), 2026),
        parse_schedule_row(_sched("2026-A-151", "RESERVED", pre_exe_date="2026-06-25T00:00:00"), 2026),
    ]
    canonical = dedupe_latest_per_game(rows)  # type: ignore[arg-type]
    assert len(canonical) == 1
    assert canonical[0].game_status == "FINISHED" and canonical[0].visiting_score == 3


def test_dedupe_latest_per_game_distinct_snos_untouched() -> None:
    rows = [
        parse_schedule_row(_sched("2026-A-1", "FINISHED", v=1), 2026),
        parse_schedule_row(_sched("2026-A-2", "SCHEDULED"), 2026),
    ]
    canonical = dedupe_latest_per_game(rows)  # type: ignore[arg-type]
    assert {r.game_sno for r in canonical} == {1, 2}


def test_diff_schedule_status_flags_dangerous_direction() -> None:
    """本機已判完成（score>0）但官方非 FINISHED（保留賽/延期）＝危險方向，須記為
    schedule_status_mismatch；官方 FINISHED 但本機未同步只記 local_lag（非錯誤，僅觀察）。"""
    schedule_by_sno = {
        10: ScheduleRow(2026, "A", 10, "RESERVED", False, None, 0, 0, None, {}),
        11: ScheduleRow(2026, "A", 11, "FINISHED", False, None, 3, 2, None, {}),
        12: ScheduleRow(2026, "A", 12, "FINISHED", False, None, 1, 0, None, {}),
    }
    # 本機誤判 10（保留賽卻有比分被判完成）；11 本機也判完成（正常一致）；12 本機尚未同步
    local_completed = {10, 11}
    diffs = diff_schedule_status(local_completed, schedule_by_sno)
    mismatch = [d for d in diffs if d["diff_type"] == "schedule_status_mismatch"]
    lag = [d for d in diffs if d["diff_type"] == "local_lag"]
    assert [d["game_sno"] for d in mismatch] == [10]
    assert [d["game_sno"] for d in lag] == [12]


def test_diff_rows_pk_and_cell_mismatch() -> None:
    shadow = [
        {"year": 2026, "kind_code": "A", "game_sno": 99, "pitcher_acnt": "P1", "pitch_cnt": 1, "rel_speed": 146.0},
        {"year": 2026, "kind_code": "A", "game_sno": 99, "pitcher_acnt": "P1", "pitch_cnt": 2, "rel_speed": 140.0},
    ]
    prod = [
        {"year": 2026, "kind_code": "A", "game_sno": 99, "pitcher_acnt": "P1", "pitch_cnt": 1, "rel_speed": 999.0},
        {"year": 2026, "kind_code": "A", "game_sno": 99, "pitcher_acnt": "P1", "pitch_cnt": 3, "rel_speed": 130.0},
    ]
    diffs = diff_rows(shadow, prod)
    by_type = {d["diff_type"]: d for d in diffs}
    assert "only_shadow_pk" in by_type and by_type["only_shadow_pk"]["detail"]["pk"][-1] == 2
    assert "only_prod_pk" in by_type and by_type["only_prod_pk"]["detail"]["pk"][-1] == 3
    assert "cell_mismatch" in by_type
    assert by_type["cell_mismatch"]["detail"]["fields"]["rel_speed"] == {"shadow": 146.0, "prod": 999.0}


def test_diff_rows_ignores_float4_storage_precision_noise() -> None:
    """cpbl.pitch_tracking 的物理欄位是 `real`（float4）；shadow jsonb 保存 parse_pitches
    算出的原生 float64。同一數值兩邊比對不能用裸 `==`，否則正式表存入時的精度截斷會讓
    每一列都「假陽性」不一致（2026-07-24 首次 bootstrap 實測撞到：1184 列全部誤判）。
    這裡用實測樣本（rel_side/rel_speed）驗證截斷後應視為相同。"""
    shadow = [{"year": 2026, "kind_code": "A", "game_sno": 211, "pitcher_acnt": "P1", "pitch_cnt": 1,
               "rel_side": 0.458577696, "rel_speed": 133.67097000576}]
    prod = [{"year": 2026, "kind_code": "A", "game_sno": 211, "pitcher_acnt": "P1", "pitch_cnt": 1,
             "rel_side": 0.4585777, "rel_speed": 133.67097}]
    assert diff_rows(shadow, prod) == []


def test_diff_rows_still_catches_genuine_real_column_mismatch() -> None:
    """float4 容忍度只吸收儲存精度噪音，真正不同的球速值仍要抓出來。"""
    shadow = [{"year": 2026, "kind_code": "A", "game_sno": 211, "pitcher_acnt": "P1", "pitch_cnt": 1,
               "rel_speed": 146.0}]
    prod = [{"year": 2026, "kind_code": "A", "game_sno": 211, "pitcher_acnt": "P1", "pitch_cnt": 1,
             "rel_speed": 130.0}]
    diffs = diff_rows(shadow, prod)
    assert len(diffs) == 1 and diffs[0]["diff_type"] == "cell_mismatch"


def test_diff_rows_no_diff_when_equal() -> None:
    rows = [{"year": 2026, "kind_code": "A", "game_sno": 99, "pitcher_acnt": "P1", "pitch_cnt": 1, "rel_speed": 146.0}]
    assert diff_rows(rows, rows) == []


def test_skip_trackman_anomaly_only_when_data_present() -> None:
    sched = ScheduleRow(2026, "A", 5, "FINISHED", True, None, 1, 0, "亞太主", {})
    assert skip_trackman_anomaly(sched, [], []) is None
    anomaly = skip_trackman_anomaly(sched, [{"pitch_cnt": 1}], [])
    assert anomaly is not None and anomaly["diff_type"] == "skip_trackman_anomaly"


def test_skip_trackman_false_not_anomaly_regardless_of_data() -> None:
    """SkipTrackman=false 不是 skip 語意本體，即使雙邊都沒資料也不判 anomaly（false 只是
    未觀測到 skip，不是「保證有資料」也不是「保證沒資料」）。"""
    sched = ScheduleRow(2026, "A", 6, "FINISHED", False, None, 1, 0, None, {})
    assert skip_trackman_anomaly(sched, [], []) is None
