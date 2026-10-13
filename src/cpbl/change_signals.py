"""官方賽程異動訊號 ``cpbl.official_change_signals``（#268 D1，需求方裁定 6142259348）。

缺口：官方改期／改球場／改主客，或公布下一輪新場次後，本站正式資料尚未反映（入庫前，或晚間鏈偵測到
後 www／同步失敗）時，三入口照舊顯示原值且沒有任何待更新提示——偵測結果原本只活在晚間鏈的狀態檔。

* **寫**：只有季後晚間事件鏈（``cpbl.ingest.postseason_evening``）。偵測到異動 upsert；同步對帳通過
  （或資料已由其他路徑入庫、偵測不再成立）後寫 ``resolved_at``。
* **到正式站**（#268 B1，需求方裁定 6142744045）：``refresh-cpbl-prod.sh`` 的 ``sync_postseason_results``
  （晚間 POSTSEASON_RESULTS_ONLY 與既有每日鏈共用）把本表與季後三表一起非破壞性鏡像到 production；
  本機訊號表變動而三表沒變（www／同步失敗、對帳後才解決）時，晚間鏈另走一次「僅訊號變動」的
  已驗證備份→同步→data-only 對帳。prod 不另寫本表。
* **讀**：``daily.summary`` 與 ``postseason_contract`` 各一次 :data:`UNRESOLVED_SQL`，經
  :func:`signal_games` 併入 ``coverage``（reason ``official_change_not_ingested``，狀態 pending_update）。

這是**訊號**，不是賽程或完賽來源：不改 ``cpbl.games``、不作完賽判準、不從這裡推場號或比分。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import date, datetime

FIELDS = ("game", "date", "teams", "venue")   # game＝本站沒有的新場次（official_value＝官方開賽時刻）

UNRESOLVED_SQL = """
    SELECT s.year, s.kind_code, s.game_sno, s.field, s.official_value, s.detected_at,
           (SELECT min(g.game_date) FROM cpbl.games g
             WHERE g.year = s.year AND g.kind_code = s.kind_code
               AND g.game_sno = s.game_sno) AS local_game_date
    FROM cpbl.official_change_signals s
    WHERE s.resolved_at IS NULL AND s.kind_code = ANY(%(kinds)s)
      AND (%(season)s::int IS NULL OR s.year = %(season)s)
    ORDER BY s.year, s.kind_code, s.game_sno, s.field
"""

# 同一 (場次, 欄位) 仍未解決時保留首次偵測時刻；已解決後再次偵測＝重新開啟（新的 detected_at）。
UPSERT_SQL = """
    INSERT INTO cpbl.official_change_signals
        (year, kind_code, game_sno, field, official_value, detected_at)
    VALUES (%(year)s, %(kind_code)s, %(game_sno)s, %(field)s, %(official_value)s, %(now)s)
    ON CONFLICT (year, kind_code, game_sno, field) DO UPDATE SET
        official_value = EXCLUDED.official_value,
        detected_at = CASE WHEN cpbl.official_change_signals.resolved_at IS NULL
                           THEN cpbl.official_change_signals.detected_at
                           ELSE EXCLUDED.detected_at END,
        resolved_at = NULL
    WHERE cpbl.official_change_signals.resolved_at IS NOT NULL
       OR cpbl.official_change_signals.official_value IS DISTINCT FROM EXCLUDED.official_value
"""

# 該季仍未解決、但已不在「應維持開啟」集合者 → 解決。
RESOLVE_SQL = """
    UPDATE cpbl.official_change_signals SET resolved_at = %(now)s
    WHERE year = %(year)s AND resolved_at IS NULL
      AND (kind_code, game_sno, field) NOT IN (
          SELECT * FROM unnest(%(kinds)s::text[], %(snos)s::int[], %(fields)s::text[]))
"""

_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}")


def write_signals(cursor, year: int, rows: Iterable[Mapping], now: datetime) -> int:
    """把「應維持開啟」的訊號集合寫成表的現況：逐列 upsert，其餘未解決者寫 ``resolved_at``。冪等。

    回傳**實際變動的列數**（upsert 的 WHERE 擋掉「值沒變」的列，故重複寫同一集合回 0）。晚間鏈據此
    判斷本機訊號表是否與正式站不同、需要一次「僅訊號變動」的同步（#268 B1，需求方裁定 6142744045）。"""
    rows = list(rows)
    changed = 0
    for row in rows:
        cursor.execute(UPSERT_SQL, {"year": year, "kind_code": row["kind_code"],
                                    "game_sno": int(row["game_sno"]), "field": row["field"],
                                    "official_value": row.get("official_value"), "now": now})
        changed += max(cursor.rowcount, 0)
    cursor.execute(RESOLVE_SQL, {"year": year, "now": now,
                                 "kinds": [r["kind_code"] for r in rows],
                                 "snos": [int(r["game_sno"]) for r in rows],
                                 "fields": [r["field"] for r in rows]})
    return changed + max(cursor.rowcount, 0)


def _day(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    match = _DAY.match(str(value or ""))
    return match.group(0) if match else None


def signal_games(rows: Iterable[Mapping]) -> list[dict]:
    """未解決訊號列 → 每場一筆（``year``、``kind_code``、``game_sno``、``game_date``）。

    ``game_date`` 優先取官方新值（``game``／``date`` 欄），否則取本站現有日期；兩者皆無為 ``None``
    （不猜）。"""
    games: dict[tuple[int, str, int], dict] = {}
    for row in rows:
        key = (int(row["year"]), str(row["kind_code"]), int(row["game_sno"]))
        game = games.setdefault(key, {"official": None, "local": None})
        if row["field"] in ("game", "date"):
            game["official"] = _day(row.get("official_value")) or game["official"]
        game["local"] = _day(row.get("local_game_date")) or game["local"]
    return [{"year": k[0], "kind_code": k[1], "game_sno": k[2],
             "game_date": g["official"] or g["local"]} for k, g in sorted(games.items())]
