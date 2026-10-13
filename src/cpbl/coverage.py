"""資料「涵蓋」判定 [coverage]（#268 B2）：本站是否已收到最新已完賽場次。

與 ``refresh_log`` 的「最後一次刷新是否成功」是**兩條獨立的軸**：

* ``last_refresh`` 只回答「排程跑了沒、自陳成功與否」，**不**回答「資料庫有沒有昨晚那一場」。
  #268 的反例正是這個差：10/12 E4 已完賽、刷新紀錄仍是成功，首頁於是標「資料為最新」卻停在 E3。
* ``coverage`` 只回答「日期已過（或即時來源已終場）的場次，正式完賽判準是否已成立」。

純函式、無 I/O、不讀時鐘；呼叫端注入台北日與官方狀態。判準本身**不在這裡**——「這場完成了沒」
一律由呼叫端以 :func:`cpbl.completion.is_completed_game`／``completed_games_sql_with_evidence``
決定後傳入，本模組只把已判定為未完成的場次分類。⛔ 不把即時快取的 final 當完賽（#237）：
它只是一個「待更新」訊號。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

COVERED = "covered"
PENDING_UPDATE = "pending_update"
UNKNOWN = "unknown"
COVERAGE_STATUSES = (COVERED, PENDING_UPDATE, UNKNOWN)

# 官方已宣告「這一場目前不會有賽果」：延賽／保留。資料沒有落後，不算待更新。
OFFICIAL_NOT_LAGGING = frozenset({"postponed", "reserved"})

# 待更新原因（機器可讀；呈現端自行對文案，不在 API 寫成句子）。
REASON_OFFICIAL_FINAL = "official_final_not_ingested"   # 官方排程已 final，正式完賽判準未成立
REASON_PAST_NO_RESULT = "past_game_without_result"      # 台北日已過、官方排程仍非終止狀態
REASON_LIVE_FINAL = "live_final_not_ingested"           # 即時來源已終場，正式資料尚未入庫
REASON_STATUS_UNKNOWN = "official_status_unknown"       # 讀不到官方狀態 → 無從判斷
REASON_LIVE_UNOBSERVED = "live_status_unavailable"      # 今天的場次未完賽，且即時來源取不到或已中斷 → 無從確認是否已終場
REASON_OFFICIAL_CHANGE = "official_change_not_ingested"  # 官方賽程異動／新場次已偵測，正式資料尚未反映（#268 D1）

_TAIPEI = ZoneInfo("Asia/Taipei")

GameKey = tuple[int, str, int]


def taipei_date(now: datetime) -> date:
    """台北日界的「今天」。naive datetime 視為 UTC（與 ``daily._age_seconds`` 同一慣例）。"""
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(_TAIPEI).date()


def _as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _key(row: Mapping) -> GameKey:
    year = row.get("season", row.get("year"))
    return (int(year), str(row["kind_code"]), int(row["game_sno"]))


def coverage_verdict(
    past_uncompleted: Iterable[Mapping],
    official_statuses: Mapping[GameKey, str] | None,
    *,
    taipei_day: date,
    live_final_uncompleted: Iterable[Mapping] = (),
    today_unobserved: Iterable[Mapping] = (),
    change_signals: Iterable[Mapping] = (),
) -> dict:
    """未完成場次 → 涵蓋判定。

    參數：

    * ``past_uncompleted``：呼叫端已用正式判準判為**未完成**的場次（帶 ``season``／``year``、
      ``kind_code``、``game_sno``、``game_date``）。本函式只看 ``game_date < taipei_day`` 者，
      其餘忽略——台北當天還沒過的場次可能仍在進行，不能說它落後。
    * ``official_statuses``：``(year, kind, sno) → official_status``（``helpers.official_status``
      的值域）。``None``＝官方狀態查詢本身失敗，所有過去場次一律 ``unknown``（fail closed）。
    * ``live_final_uncompleted``：即時來源已 ``final``、但正式判準仍未成立的場次（不論日期）。
    * ``today_unobserved``：台北今天、正式判準未成立、且**即時來源取不到或已中斷**的場次。
      沒有任何觀測訊號時無從知道它是否已終場，所以不得說 covered（#268：同晚即時來源不可用時，
      首頁原本會在午夜前一直標「資料為最新」）。官方已宣告延賽／保留者由呼叫端先排除。
    * ``change_signals``：``cpbl.change_signals.signal_games`` 的每場一筆——官方賽程異動或新場次已由
      晚間鏈偵測、本站正式資料尚未反映（#268 D1）。確定待更新；``game_date`` 可為 ``None``（不猜）。

    判定（嚴重度由高到低）：任一場待更新 → ``pending_update``；否則任一場讀不到官方狀態 →
    ``unknown``；否則 ``covered``。延賽／保留不算落後。

    ``pending_games`` 列出**所有**造成非 covered 的場次（含 unknown 者），供呈現端逐場說明。
    """
    pending: list[dict] = []
    unknown: list[dict] = []
    seen: set[GameKey] = set()
    for row in past_uncompleted:
        game_day = _as_date(row["game_date"])
        if game_day >= taipei_day:
            continue
        key = _key(row)
        if key in seen:
            continue
        seen.add(key)
        status = "unknown" if official_statuses is None else official_statuses.get(key, "unknown")
        if status in OFFICIAL_NOT_LAGGING:
            continue
        entry = {"year": key[0], "kind_code": key[1], "game_sno": key[2],
                 "game_date": game_day.isoformat(), "official_status": status}
        if status == "unknown":
            unknown.append({**entry, "reason": REASON_STATUS_UNKNOWN})
        elif status == "final":
            pending.append({**entry, "reason": REASON_OFFICIAL_FINAL})
        else:
            pending.append({**entry, "reason": REASON_PAST_NO_RESULT})
    for row in live_final_uncompleted:
        key = _key(row)
        if key in seen:
            continue
        seen.add(key)
        status = (official_statuses or {}).get(key, "unknown")
        pending.append({"year": key[0], "kind_code": key[1], "game_sno": key[2],
                        "game_date": _as_date(row["game_date"]).isoformat(),
                        "official_status": status, "reason": REASON_LIVE_FINAL})
    # 異動訊號排在「無從判斷」之前：同一場既有異動又無觀測時，以確定待更新為準。
    for row in change_signals:
        key = _key(row)
        if key in seen:
            continue
        seen.add(key)
        day = row.get("game_date")
        pending.append({"year": key[0], "kind_code": key[1], "game_sno": key[2],
                        "game_date": _as_date(day).isoformat() if day else None,
                        "official_status": (official_statuses or {}).get(key, "unknown"),
                        "reason": REASON_OFFICIAL_CHANGE})
    for row in today_unobserved:
        key = _key(row)
        if key in seen:
            continue
        seen.add(key)
        unknown.append({"year": key[0], "kind_code": key[1], "game_sno": key[2],
                        "game_date": _as_date(row["game_date"]).isoformat(),
                        "official_status": (official_statuses or {}).get(key, "unknown"),
                        "reason": REASON_LIVE_UNOBSERVED})

    if pending:
        status = PENDING_UPDATE
    elif unknown:
        status = UNKNOWN
    else:
        status = COVERED
    games = sorted(pending + unknown, key=lambda g: (g["game_date"] or "", g["kind_code"], g["game_sno"]))
    return {"status": status, "taipei_date": taipei_day.isoformat(), "pending_games": games}
