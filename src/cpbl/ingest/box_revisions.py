"""官方 box 逐場逐投手 append-only 快照（DATA-BOX-REVISION-SNAPSHOT1）。

背景：cpbl.pitching_gamelog 只存最新一次 UPSERT 後的值，無版本歷史，導致
「官方賽後修正判決」與「我方 livelog 漏記」在單一快照上永遠分不開
（見 docs/research/ML-PITCHER-ER-REBUILD1/RESULTS.md §7.6）。本模組把每次
抓 box 的逐投手列存成快照（內容雜湊去重），讓這件事從不可證偽變成可量測。

本卡刻意不解決任何現有的自責分不一致——只從上線日起累積未來的快照。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from cpbl.db import conn
from cpbl.ingest.game_source_revisions import canonical_source_version, sanitize_detail


def _i(v: Any) -> int | None:
    try:
        return int(float(v)) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def record_box_pitching_revisions(
    year: int, kind_code: str, game_sno: int, pitching_rows: list[dict[str, Any]],
) -> int:
    """把一場抓到的逐投手 PitchingJson 存成快照；同投手同內容重複抓取不新增列。

    以 (year, kind_code, game_sno, pitcher_acnt, content_hash) 當 UNIQUE key：
    - 內容不變 → ON CONFLICT 只更新 last_seen_at / seen_count，append-only 不長列。
    - 內容變了（例如官方賽後改判自責分）→ hash 不同，新增一列，舊列原封不動保留，
      形成該投手在該場的版本歷史。

    回傳實際嘗試寫入的列數（含被去重合併的），不是新增列數——新增與否由 DB 決定。
    """
    if not pitching_rows:
        return 0
    records: list[tuple[Any, ...]] = []
    for r in pitching_rows:
        acnt = r.get("PitcherAcnt")
        if not acnt:
            continue
        safe_payload = sanitize_detail(r)
        content_hash = canonical_source_version(safe_payload)
        records.append((
            year, kind_code, game_sno, acnt,
            _i(r.get("InningPitchedCnt")), _i(r.get("InningPitchedDiv3Cnt")),
            _i(r.get("RunCnt")), _i(r.get("EarnedRunCnt")),
            content_hash, json.dumps(safe_payload, ensure_ascii=False),
        ))
    if not records:
        return 0
    with conn() as c:
        c.cursor().executemany(
            """
            INSERT INTO cpbl.box_pitching_revisions
                (year, kind_code, game_sno, pitcher_acnt,
                 inning_pitched_cnt, inning_pitched_div3, runs, earned_runs,
                 content_hash, raw_payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (year, kind_code, game_sno, pitcher_acnt, content_hash) DO UPDATE SET
                last_seen_at = now(),
                seen_count = cpbl.box_pitching_revisions.seen_count + 1
            """,
            records,
        )
    return len(records)


def pitcher_er_revision_report(
    year: int, kind_code: str, game_sno: int, pitcher_acnt: str | None = None,
) -> list[dict[str, Any]]:
    """回答「某場某投手的 ER 賽後被改過幾次、每次改了什麼」。

    回傳依 pitcher_acnt、fetched_at 排序的版本序列；每列附上與「前一版」的
    diff（changed_fields）與距離比賽日的天數（days_since_game，game_date 缺值
    時為 None）。第一版（revision_no=1）的 changed_fields 恆為 {}（沒有前一版
    可比較，不代表「沒有被改過」）。
    """
    query = """
        SELECT
            r.pitcher_acnt, r.fetched_at, r.inning_pitched_cnt, r.inning_pitched_div3,
            r.runs, r.earned_runs, r.seen_count, g.game_date,
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
        (acnt, fetched_at, ip_cnt, ip_div3, runs, er, seen_count, game_date, rev_no,
         prev_ip_cnt, prev_ip_div3, prev_runs, prev_er) = row
        changed: dict[str, tuple[Any, Any]] = {}
        if rev_no > 1:
            if ip_cnt != prev_ip_cnt or ip_div3 != prev_ip_div3:
                changed["outs"] = ((prev_ip_cnt, prev_ip_div3), (ip_cnt, ip_div3))
            if runs != prev_runs:
                changed["runs"] = (prev_runs, runs)
            if er != prev_er:
                changed["earned_runs"] = (prev_er, er)
        days_since_game = (
            (fetched_at.date() if isinstance(fetched_at, datetime) else fetched_at) - game_date
        ).days if game_date else None
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
    return out


def revision_counts_within_days(
    year: int, kind_code: str, game_sno: int, within_days: int,
) -> dict[str, int]:
    """摘要版：某場每位投手在賽後 N 天內被改過幾次（=該窗內版本數 - 1，下限 0）。

    只計「賽後 N 天內出現的版本」——N 天後才出現的新版本不計入這個窗。
    """
    report = pitcher_er_revision_report(year, kind_code, game_sno)
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
]
