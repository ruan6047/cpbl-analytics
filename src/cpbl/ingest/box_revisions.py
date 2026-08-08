"""官方 box 逐場逐投手 append-only 快照（DATA-BOX-REVISION-SNAPSHOT1）。

背景：cpbl.pitching_gamelog 只存最新一次 UPSERT 後的值，無版本歷史，導致
「官方賽後修正判決」與「我方 livelog 漏記」在單一快照上永遠分不開
（見 docs/research/ML-PITCHER-ER-REBUILD1/RESULTS.md §7.6）。本模組把每次
抓 box 的逐投手列存成快照（與該投手該場**最近一次觀測**比較的內容雜湊去重，
BOX-REVISION-R1-001 修正——不是全域去重，見 `record_box_pitching_revisions`
docstring），讓這件事從不可證偽變成可量測。

本卡刻意不解決任何現有的自責分不一致——只從上線日起累積未來的快照。

**零觀測不代表官方沒有改判**（BOX-REVISION-R1-002）：這份資料只涵蓋（1）部署
本功能之後才抓到的場次——2018–2026 既有歷史場次沒有回溯快照；且（2）目前實際
的抓取窗口（每日 refresh 近 2 天 + 週深度重抓近 30 天，見 `run_refresh_box_deep`）
觀測到的版本——官方改判的真實發生率未知，30 天以外或部署前發生的修正即使
真的存在，也不會出現在這裡。查不到修正 ≠ 沒有修正，只能說「這個窗口沒看到」。
"""

from __future__ import annotations

import json
from typing import Any

from cpbl.db import conn
from cpbl.ingest.game_source_revisions import canonical_source_version, sanitize_detail


def _i(v: Any) -> int | None:
    try:
        return int(float(v)) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


_UPSERT_LATEST_ONLY_SQL = """
    WITH latest AS (
        SELECT id, content_hash FROM cpbl.box_pitching_revisions
        WHERE year = %(year)s AND kind_code = %(kind_code)s AND game_sno = %(game_sno)s
          AND pitcher_acnt = %(pitcher_acnt)s
        ORDER BY fetched_at DESC, id DESC
        LIMIT 1
    ),
    touched AS (
        UPDATE cpbl.box_pitching_revisions t
        SET last_seen_at = now(), seen_count = t.seen_count + 1
        FROM latest
        WHERE t.id = latest.id AND latest.content_hash = %(content_hash)s
        RETURNING t.id
    )
    INSERT INTO cpbl.box_pitching_revisions
        (year, kind_code, game_sno, pitcher_acnt,
         inning_pitched_cnt, inning_pitched_div3, runs, earned_runs,
         content_hash, raw_payload)
    SELECT %(year)s, %(kind_code)s, %(game_sno)s, %(pitcher_acnt)s,
           %(inning_pitched_cnt)s, %(inning_pitched_div3)s, %(runs)s, %(earned_runs)s,
           %(content_hash)s, %(raw_payload)s::jsonb
    WHERE NOT EXISTS (SELECT 1 FROM touched)
"""


def record_box_pitching_revisions(
    year: int, kind_code: str, game_sno: int, pitching_rows: list[dict[str, Any]],
) -> int:
    """把一場抓到的逐投手 PitchingJson 存成快照；同投手同內容重複抓取不新增列。

    去重只比較**該 (year, kind_code, game_sno, pitcher_acnt) 最近一次觀測**
    （`fetched_at DESC LIMIT 1`），不是全域內容去重（BOX-REVISION-R1-001 修正，
    migration 072）：
    - 與最近一列內容相同 → 只更新該列 last_seen_at / seen_count，append-only 不長列。
    - 與最近一列內容不同（含「改回舊值」，例如 A→B→A 的第三次觀測）→ 新增一列，
      舊列原封不動保留，形成該投手在該場的完整版本歷史，**不會**因為內容剛好
      等於更早之前（非最近一次）的某一版而被誤判成「沒變」。

    冪等**不再由 DB UNIQUE 約束提供**（071 的全域 UNIQUE(...,content_hash) 已在
    072 拿掉），改由本函式的寫入語句保證：`INSERT ... WHERE NOT EXISTS(該 PK
    最近一列 content_hash 相同)`，配合前面的 `UPDATE ... RETURNING` 判斷「要不要
    插入」。**併發假設**：本函式目前只有兩個呼叫端——每日 refresh 鏈的
    `scrape_gamelogs`（2 天窗）與週排程深度重抓（都受同一把
    `/private/tmp/cpbl-analytics-refresh.lock` 互斥、忙碌即跳過），對同一
    (year, kind_code, game_sno, pitcher_acnt) 不會有兩個行程同時寫入；若未來
    出現真正並行寫入同一 PK 的呼叫端，這裡的「先 SELECT 最近一列、再決定
    INSERT/UPDATE」不是原子的（兩個並發交易可能都讀到同一個「最近一列」、都判定
    要插入），需要額外的鎖或序列化保證，目前刻意不處理。

    回傳實際處理的列數（INSERT 或 UPDATE 各算一次），不是新增列數——新增與否由
    每列自己的 WHERE NOT EXISTS 判斷決定，呼叫端不需要也不應該用回傳值反推。
    """
    if not pitching_rows:
        return 0
    params: list[dict[str, Any]] = []
    for r in pitching_rows:
        acnt = r.get("PitcherAcnt")
        if not acnt:
            continue
        safe_payload = sanitize_detail(r)
        content_hash = canonical_source_version(safe_payload)
        params.append({
            "year": year, "kind_code": kind_code, "game_sno": game_sno, "pitcher_acnt": acnt,
            "inning_pitched_cnt": _i(r.get("InningPitchedCnt")),
            "inning_pitched_div3": _i(r.get("InningPitchedDiv3Cnt")),
            "runs": _i(r.get("RunCnt")), "earned_runs": _i(r.get("EarnedRunCnt")),
            "content_hash": content_hash,
            "raw_payload": json.dumps(safe_payload, ensure_ascii=False),
        })
    if not params:
        return 0
    with conn() as c:
        cur = c.cursor()
        for p in params:
            cur.execute(_UPSERT_LATEST_ONLY_SQL, p)
    return len(params)


ZERO_OBSERVATION_CAVEAT = (
    "零觀測不代表官方沒有改判：本快照只涵蓋（1）部署本功能之後才抓到的場次"
    "（2018–2026 既有歷史場次無回溯快照）且（2）目前抓取窗口內（每日近 2 天、"
    "週深度重抓近 30 天）實際觀測到的版本。官方改判的真實發生率未知，30 天以外"
    "或部署前發生的修正即使真的存在也不會出現在這裡——查不到修正只代表「這個"
    "窗口沒看到」，不能當作「沒有發生過」的證據（BOX-REVISION-R1-002）。"
)


def pitcher_er_revision_report(
    year: int, kind_code: str, game_sno: int, pitcher_acnt: str | None = None,
) -> dict[str, Any]:
    """回答「某場某投手的 ER 賽後被改過幾次、每次改了什麼」。

    回傳 ``{"revisions": [...], "caveat": ZERO_OBSERVATION_CAVEAT}``——限制文字
    隨資料一起回傳，消費者不必回頭翻 Runbook 才知道「查不到修正」不等於「沒有
    修正」（BOX-REVISION-R1-002：查核明確要求數字與限制不能分開放）。

    ``revisions`` 依 pitcher_acnt、fetched_at 排序的版本序列；每列附上與「前一版」
    的 diff（changed_fields）與距離比賽日的天數（days_since_game，game_date 缺值
    時為 None）。第一版（revision_no=1）的 changed_fields 恆為 {}（沒有前一版
    可比較，不代表「沒有被改過」）。因為 072 修掉了全域內容去重，這個序列現在
    正確保留「改回舊值」的事件（A→B→A 的第三版會出現在這裡，changed_fields 會
    顯示 (B, A)，不會因為內容等於更早的 A 而被誤判成沒變）。
    """
    # 天數差在 SQL 端算：game_date 是台灣賽程日曆日（無時區），DB session 是 UTC
    # （`now()` 在台北 00:00–08:00 會落在前一個 UTC 曆日，與 completion.py 記載的
    # 同一類日界問題——D7）。混用 Python `datetime.date()`（沿用 timestamptz 原始
    # tzinfo）與台灣曆日會系統性算錯，故統一先把 fetched_at 轉到 Asia/Taipei 曆日
    # 再相減，兩邊都在同一個時區基準上。
    query = """
        SELECT
            r.pitcher_acnt, r.fetched_at, r.inning_pitched_cnt, r.inning_pitched_div3,
            r.runs, r.earned_runs, r.seen_count,
            CASE WHEN g.game_date IS NULL THEN NULL
                 ELSE (r.fetched_at AT TIME ZONE 'Asia/Taipei')::date - g.game_date END
                AS days_since_game,
            ROW_NUMBER() OVER (PARTITION BY r.pitcher_acnt ORDER BY r.fetched_at) AS revision_no,
            LAG(r.inning_pitched_cnt) OVER w AS prev_inning_pitched_cnt,
            LAG(r.inning_pitched_div3) OVER w AS prev_inning_pitched_div3,
            LAG(r.runs) OVER w AS prev_runs,
            LAG(r.earned_runs) OVER w AS prev_earned_runs
        FROM cpbl.box_pitching_revisions r
        LEFT JOIN cpbl.games g
            ON g.year = r.year AND g.kind_code = r.kind_code AND g.game_sno = r.game_sno
        WHERE r.year = %s AND r.kind_code = %s AND r.game_sno = %s
          AND (%s::text IS NULL OR r.pitcher_acnt = %s)
        WINDOW w AS (PARTITION BY r.pitcher_acnt ORDER BY r.fetched_at)
        ORDER BY r.pitcher_acnt, r.fetched_at
    """
    with conn() as c:
        rows = c.execute(query, (year, kind_code, game_sno, pitcher_acnt, pitcher_acnt)).fetchall()

    out: list[dict[str, Any]] = []
    for row in rows:
        (acnt, fetched_at, ip_cnt, ip_div3, runs, er, seen_count, days_since_game, rev_no,
         prev_ip_cnt, prev_ip_div3, prev_runs, prev_er) = row
        changed: dict[str, tuple[Any, Any]] = {}
        if rev_no > 1:
            if ip_cnt != prev_ip_cnt or ip_div3 != prev_ip_div3:
                changed["outs"] = ((prev_ip_cnt, prev_ip_div3), (ip_cnt, ip_div3))
            if runs != prev_runs:
                changed["runs"] = (prev_runs, runs)
            if er != prev_er:
                changed["earned_runs"] = (prev_er, er)
        out.append({
            "pitcher_acnt": acnt,
            "revision_no": rev_no,
            "fetched_at": fetched_at,
            "days_since_game": days_since_game,
            "inning_pitched_cnt": ip_cnt,
            "inning_pitched_div3": ip_div3,
            "runs": runs,
            "earned_runs": er,
            "seen_count": seen_count,
            "changed_fields": changed,
        })
    return {"revisions": out, "caveat": ZERO_OBSERVATION_CAVEAT}


def revision_counts_within_days(
    year: int, kind_code: str, game_sno: int, within_days: int,
) -> dict[str, int]:
    """摘要版：某場每位投手在賽後 N 天內被改過幾次（=該窗內版本數 - 1，下限 0）。

    只計「賽後 N 天內出現的版本」——N 天後才出現的新版本不計入這個窗。回傳只有
    計數（不含 caveat）；要拿完整限制文字請直接呼叫 `pitcher_er_revision_report`。
    """
    report = pitcher_er_revision_report(year, kind_code, game_sno)["revisions"]
    counts: dict[str, int] = {}
    for entry in report:
        d = entry["days_since_game"]
        if d is None or d > within_days:
            continue
        acnt = entry["pitcher_acnt"]
        counts[acnt] = max(counts.get(acnt, 0), entry["revision_no"] - 1)
    return counts


__all__ = [
    "record_box_pitching_revisions",
    "pitcher_er_revision_report",
    "revision_counts_within_days",
    "ZERO_OBSERVATION_CAVEAT",
]
