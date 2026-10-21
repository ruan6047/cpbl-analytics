"""逐球（TrackMan）覆蓋落後判準的唯一 SQL（#293 fix-5 自 ``run_refresh_recent._lagging_pitch_games`` 原樣抽出）。

每日鏈的落後場自癒（``_lagging_pitch_games``）與晚間鏈 box／PA 階段的「逐球待更新」
（``postseason_sources.load_local_facts``）共用這一支，⛔ 不得各寫一套設備／落後判準。
判準與常數（近 10 場／0.80／0.85／≥50 球）的來由與政策地位見 ``_lagging_pitch_games`` 的 docstring
（需求方 2026-08-04 裁定的營運政策，執行者不得自行更動）。

放在這個輕量模組而不是 ``run_refresh_recent``：晚間鏈 plan 階段會讀它，而 plan 階段刻意不載入爬蟲模組。
"""

from __future__ import annotations

from cpbl.completion import daily_chain_completed_games_sql


def lagging_pitch_games_sql(completed_sql: str | None = None, *,
                            equipment_kinds: bool = False) -> str:
    """回傳查詢字串，結果每列一個 ``game_sno``。

    參數：預設 ``(year, kind_code, days_back)``；``equipment_kinds=True`` 時為
    ``(year, kind_code, year, equipment_kind_codes, days_back)``（``equipment_kind_codes`` 為 list）。

    ``completed_sql``＝完成場選場條件（別名 ``gm``）；省略即 ``daily_chain_completed_games_sql('gm')``。
    每日鏈在 ``run_refresh_recent`` 內顯式傳入同一支（該檔的選場點計數由
    ``tests/test_daily_chain_completion.py`` 釘住），兩邊產出的字串逐字相同（``tests/test_boxpa_tracking_late.py``）。

    落後＝該場所在球場**近期實證有設備**（最近 10 場完成場至少一場 ``pitches >= 50 AND
    tracked >= pitches * 0.80``），且該場 ``game_date >= CURRENT_DATE - days_back``、
    ``pitches >= 50 AND tracked < pitches * 0.85``。

    設備證據的母體：預設＝同一 ``(year, kind_code)`` 的完成場（每日鏈；⛔ 不得改動，sha256 由測試釘住）。
    ``equipment_kinds=True``＝同年、``equipment_kind_codes`` 內所有賽別的完成場（晚間鏈；#293 fix-5 需求方
    2026-10-21 依執行者建議裁定）：季後某賽別在某球場的第一場（新系列 G1）沒有同賽別歷史，改以同年一軍
    例行賽＋季後賽在該球場的近 10 場作設備證據；兩個常數與「近 10 場」窗口不變。"""
    if completed_sql is None:
        completed_sql = daily_chain_completed_games_sql("gm")
    counts = """
                (SELECT count(*) FROM cpbl.game_livelog ll WHERE ll.year=gm.year
                   AND ll.kind_code=gm.kind_code AND ll.game_sno=gm.game_sno
                   AND (ll.is_ball OR ll.is_strike)) AS pitches,
                (SELECT count(*) FROM cpbl.pitch_tracking pt WHERE pt.year=gm.year
                   AND pt.kind_code=gm.kind_code AND pt.game_sno=gm.game_sno) AS tracked"""
    evidence = "cov"
    extra = ""
    if equipment_kinds:
        evidence = "ev"
        extra = f"""
            ev AS (
              SELECT gm.venue, gm.game_sno, gm.game_date,{counts}
              FROM cpbl.games gm
              WHERE gm.year=%s AND gm.kind_code = ANY(%s) AND {completed_sql}),"""
    return f"""
            WITH cov AS (
              SELECT gm.venue, gm.game_sno, gm.game_date,{counts}
              FROM cpbl.games gm
              WHERE gm.year=%s AND gm.kind_code=%s AND {completed_sql}),{extra}
            r AS (SELECT *, row_number() OVER (PARTITION BY venue
                    ORDER BY game_date DESC, game_sno DESC) rn FROM {evidence}),
            equipped AS (
              SELECT venue FROM (
                SELECT venue, bool_or(pitches>=50 AND tracked>=pitches*0.80) AS equipped
                FROM r WHERE rn<=10 GROUP BY venue
              ) e WHERE e.equipped
            )
            SELECT cov.game_sno FROM cov
            JOIN equipped ON equipped.venue = cov.venue
            WHERE cov.game_date >= (CURRENT_DATE - %s::int)
              AND cov.pitches >= 50 AND cov.tracked < cov.pitches * 0.85
            ORDER BY cov.game_sno
            """
