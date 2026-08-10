"""未定案場次（過去日期卻仍 0–0）與它們的官方排程狀態。

`cpbl.games` 對這些場次只看得到 0–0，分不出「刷新落後」與「官方宣告延賽／保留」。
唯一分得開的證據在官網排程歷程（`game_schedule_status_revisions`），判定共用
`helpers.official_status`——與單場狀態端點同一份，不在任何呼叫端重寫。

三種讀法只有一種要人行動：

- `postponed`／`reserved`：官方已宣告，資料沒有落後，**沒有人需要做事**；
- `scheduled`：官方那邊也還沒有結果（開賽前，或官網自己還沒更新）；
- `final`：**官方說打完了、我們卻還是 0–0**——真的刷新落後，唯一要人去看的一格。

本模組由 `routers/daily`（首頁逐場 status）與 `routers/info`（維護者計數）共用。
"""

from __future__ import annotations

from cpbl.api.helpers import _dicts, official_status
from cpbl.completion import TAIPEI_TODAY_SQL

# 只把近期的未定案場次當成刷新落後訊號；更早的 0–0 屬歷史資料問題，不在本契約範圍。
UNRESOLVED_WINDOW_DAYS = 30


def statuses_for(cursor, rows: list[dict]) -> dict[tuple[int, str, int], str]:
    """未定案場次 → 官方排程狀態。`rows` 需帶 `season`／`kind_code`／`game_sno`。

    `rows` 為空時完全不查（休兵日與絕大多數日子的常態就是 0 筆），呼叫端的查詢數
    因此只在真的有未定案場次時才 +1。表尚未 migrate／權限不足時整批回空，由呼叫端
    退回 `unknown`——缺證據就別宣稱（同 `daily._last_refresh` 的立場）。
    """
    if not rows:
        return {}
    years = [r["season"] for r in rows]
    kinds = [r["kind_code"] for r in rows]
    snos = [r["game_sno"] for r in rows]
    try:
        cursor.execute(
            """
            SELECT year, kind_code, game_sno, raw_present_status, raw_game_result,
                   raw_game_date, fetched_at, last_seen_at
            FROM cpbl.game_schedule_status_revisions
            WHERE (year, kind_code, game_sno)
                  IN (SELECT * FROM unnest(%s::int[], %s::text[], %s::int[]))
            """,
            (years, kinds, snos),
        )
        revisions = _dicts(cursor)
    except Exception:  # noqa: BLE001 — 缺表／權限問題退回無證據，不讓呼叫端掛掉
        return {}
    by_game: dict[tuple[int, str, int], list[dict]] = {}
    for row in revisions:
        by_game.setdefault((row["year"], row["kind_code"], row["game_sno"]), []).append(row)
    return {key: official_status(group)[0] for key, group in by_game.items()}


def pending_result_count(cursor) -> int:
    """官方已宣告完成、本站卻仍是 0–0 的場次數（近 `UNRESOLVED_WINDOW_DAYS` 天，全層級）。

    **刻意只數這一種**，不數未定案總數：延賽與保留已經在首頁的最近比賽日卡上有徽章，
    把它們加進同一個數字只會讓一個本來該恆為 0 的健康指標長期停在非零——這個專案已經
    有「告警響了兩個半月無人讀」的前例，一個永遠不是 0 的數字就是下一個。

    日界用台北（`TAIPEI_TODAY_SQL`，新程式碼的既定選擇）。`daily` 那一側的 `as_of` 仍是
    容器本地日，屬 DATA-TZ-BOUNDARY1 明確擱置、排在 REMEDY1 Phase 2 一起切換的範圍，
    故台北 00:00–08:00 這 8 小時兩邊的窗口可能差一天；生產排程在 10:10 CST，落在窗外。
    """
    cursor.execute(
        f"""
        SELECT year AS season, kind_code, game_sno
        FROM cpbl.games
        WHERE home_score + away_score = 0
          AND game_date < {TAIPEI_TODAY_SQL}
          AND game_date >= {TAIPEI_TODAY_SQL} - %s
        """,
        (UNRESOLVED_WINDOW_DAYS,),
    )
    rows = _dicts(cursor)
    return sum(1 for status in statuses_for(cursor, rows).values() if status == "final")
