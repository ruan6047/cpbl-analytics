"""官方先發公告分類（#320 A2）：目標場全部官方賽程修訂列 → 每隊先發分類＋整場分類（純函式）。

第 4 區「官方先發投手」與第 1 區 ``next_game`` 都經 :func:`cpbl.playoffs.watch_reader.official_starters`
取得先發，本模組只回答「目前值之外，賽前歷程還出現過什麼」。目前值（選列＋既有 gate）仍由
``official_starters`` 決定，本模組 ⛔ 重新選列。

規則（plan-1 §1.1，需求方裁定 #320 6261389955 取代 #314 Q3「不標更換」）：

- **賽前歷程**：``raw_present_status=1``、結果空、``IsPlayBall='N'``、``raw_game_date``＝目標日，且客／主隊碼與
  目標場相同的列（與 ``between_games.pregame_schedule`` 賽前候選同形；改期後只看新日期的列）。
- 每隊 S＝賽前歷程中該側**不同的非空 acnt**（以 acnt 去重，⛔ 以列數或 payload 數判斷：同一先發會因其他
  欄位變動對應多列）。
- 目前有值：|S|≤1 ⇒ ``announced``；|S|>1 ⇒ ``changed``（含 A→B→A，目前是 A）。只看 S、⛔ 把目前值併入 S
  （審核第 1 輪 #320 6262922767：照核定定義；目前值來自非賽前列時不另判更換）。
- 目前空：S 非空 ⇒ ``retracted``；S 空 ⇒ ``pending``。來源讀取失敗 ⇒ ``unknown``（由呼叫端判定）。
- 整場：任一隊 ``unknown`` ⇒ ``unknown``；剛好一隊屬 {announced, changed} ⇒ ``partial``；兩隊皆屬 ⇒
  ``announced``；否則 ``pending``。

⛔ 輸出任何公告時刻（#314 Q1：``fetched_at``／``last_seen_at`` 只是本站觀測時刻）。

已知限制（照實揭露，plan-1 §1.1）：A→撤回→A 會是 ``announced``（撤回歷程不呈現）；每個 payload 只保留首見
與末見時刻，多次往返無法完整重建；若官方撤回的形態是整列消失而非清空先發欄，目前值會停在舊值，本模組偵測不到。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

ANNOUNCED = "announced"
CHANGED = "changed"
RETRACTED = "retracted"
PENDING = "pending"
UNKNOWN = "unknown"
PARTIAL = "partial"

#: 有姓名可顯示的兩類（「已公告」語意）；整場 partial 以此計數。
_PUBLISHED = frozenset({ANNOUNCED, CHANGED})

CHANGED_SUFFIX = "（已更換）"
RETRACTED_TEXT = "待公告（先前公告已撤回）"


def _clean(v) -> str | None:
    v = str(v).strip() if v is not None else ""
    return v or None


def _as_date(v) -> date | None:
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def pregame_rows(rows: Iterable[dict], *, target_date: date | None, teams: list[str]) -> list[dict]:
    """目標場的賽前歷程列（見模組說明）；``target_date`` 為 None ⇒ 空。"""
    if target_date is None:
        return []
    return [r for r in rows
            if r.get("raw_present_status") == 1 and (r.get("raw_game_result") in (None, ""))
            and r.get("is_play_ball") == "N" and _as_date(r.get("raw_game_date")) == target_date
            and [r.get("visiting_team_code"), r.get("home_team_code")] == list(teams)]


def history_acnts(pregame: Iterable[dict], side: str) -> frozenset[str]:
    """賽前歷程中 ``side``（visiting／home）出現過的不同非空 acnt。"""
    return frozenset(a for r in pregame if (a := _clean(r.get(f"{side}_pitcher_acnt"))))


def classify_side(current_acnt: str | None, history: frozenset[str]) -> str:
    """單隊分類；``current_acnt`` 為 gate 之後的目前值（空 ⇒ None）。"""
    current = _clean(current_acnt)
    if current is not None:
        return CHANGED if len(history) > 1 else ANNOUNCED
    return RETRACTED if history else PENDING


def classify_game(classes: Iterable[str]) -> str:
    """整場分類（客、主兩隊的單隊分類）。"""
    cs = list(classes)
    if UNKNOWN in cs:
        return UNKNOWN
    published = sum(c in _PUBLISHED for c in cs)
    if published == len(cs) and cs:
        return ANNOUNCED
    return PARTIAL if published == 1 else PENDING
