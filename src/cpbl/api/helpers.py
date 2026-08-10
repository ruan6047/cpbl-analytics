"""API 共用工具：預設球季、層級 kind 群組、cursor→dict、四捨五入、特徵字串解析、局數記法換算。"""

from __future__ import annotations

from datetime import date as _date
from typing import Any

DEFAULT_SEASON = _date.today().year

# 層級 → 該層級包含的所有 kind_code（含季後賽）：
# 一軍 A ＋ 季後挑戰賽 E ＋ 台灣大賽 C；二軍 D ＋ 二軍季後 F。季後賽併入同層顯示。
KIND_GROUPS = {"A": ("A", "E", "C"), "D": ("D", "F")}


def kinds_of(kind_code: str) -> list[str]:
    """層級代碼 → 要查的 kind_code 清單；未知代碼原樣查（不猜測）。"""
    return list(KIND_GROUPS.get(kind_code, (kind_code,)))


def _batted_result(content: str | None) -> str:
    """從逐球 content 文字判斷擊球結果：hr/3b/2b/1b/out。
    content 在 DB 為雙重編碼（UTF-8 bytes 被當 latin-1 存），讀取時先還原。
    （tracking 與 games 兩 router 共用；勿在前端重寫分類，保持單一事實來源。）"""
    try:
        c = (content or "").encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        c = content or ""
    if "全壘打" in c:
        return "hr"
    if "三壘安打" in c:
        return "3b"
    if "二壘安打" in c:
        return "2b"
    if "一壘安打" in c or "內野安打" in c:
        return "1b"
    return "out"


def _ip_real(ip: float | None) -> float | None:
    """.1/.2 局數記法 → 真實局數（如 180.2 → 180⅔）。"""
    if ip is None:
        return None
    ip = float(ip)
    whole = int(ip)
    return whole + round((ip - whole) * 10) / 3.0


def _real_ip(ip: Any) -> float:
    """同 _ip_real，但 None → 0.0（加總用）。"""
    return _ip_real(ip) or 0.0


def _parse_features(features: str) -> list[str]:
    return [f.strip() for f in features.split(",") if f.strip()]
def _ip_disp(real: float | None) -> float | None:
    """真實局數 → .1/.2 棒球記法顯示（如 180⅔ → 180.2）。"""
    if real is None:
        return None
    real = float(real)
    whole = int(real + 1e-9)
    outs = round((real - whole) * 3)
    if outs >= 3:
        whole, outs = whole + 1, 0
    return round(whole + outs / 10, 1)
def _dicts(cur) -> list[dict]:
    """cursor → list[dict]，欄名取自 cursor.description；real 已是 float。"""
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
def _round(x: float | None, n: int) -> float | None:
    return round(x, n) if x is not None else None


# 官網排程 raw 詞彙 →  canonical phase 字彙。**刻意與 live worker 的 `_STATUS_PHASE` 用
# 同一組字**（`postponed`／`reserved`／`final`／`scheduled`）：`/games/{sno}/status` 的
# `canonical_phase` 在沒有 live snapshot 時退回本表，兩條路徑講不同的話就等於同一場比賽
# 有兩種狀態語彙。
#
# key＝(`PresentStatus`, `GameResult`)。**`PresentStatus` 不是「已開打」**（`cpbl_site.py`
# `_primary_entry` 的註解用詞較鬆）：同一 `sno` 每個排定日期各一列，`1`＝該列是**現行**
# 那一筆，`0`＝已被改期取代的舊列。`GameResult` 依 GLOSSARY〈保留賽／`delay_kind`〉：
# `0`＝該日打完、`1`＝延賽、`2`＝保留（已開賽中止）、空＝該日尚無結果。
#
# DB 實證（2026-08-10，`cpbl.game_schedule_status_revisions` 全庫 600 場逐場跑本表）：
# 六種組合皆已觀測，其中 `(1,'1')` 3 場、`(1,'2')` 4 場原本落到 `unknown`——
#
# - `(1,'1')`＝現行那一列該日延賽（A#14／254／255，`games.delay_kind='延賽'` 且無比分）。
#   官網宣告延賽後、補賽日公布前，該列仍是現行列，故 `PresentStatus` 維持 1；原本要求
#   `PresentStatus=0` 才算 postponed 的規則因此**永遠命中不到**（全庫 0 場走那條）。
# - `(1,'2')`＝現行那一列保留中、等續賽（D#117／118／164／165，皆 `delay_kind='保留'` 且
#   補賽日在未來）。續賽打完後官網把該列改成 `(1,'0')`（D#97／119 已實測完成這個轉換）。
#
# `PresentStatus=0` 的舊列一律不擴充：全庫每一場有 `(0,'2')` 的比賽都同時有現行列，那些
# 舊列從來不會被選中；沒有觀測就沒有證據，維持 fail closed 的 `unknown`。
_OFFICIAL_STATUS_BY_RAW: dict[tuple[Any, str], str] = {
    (1, "0"): "final",
    (1, ""): "scheduled",
    (1, "1"): "postponed",
    (1, "2"): "reserved",
    (0, "1"): "postponed",
}


def official_status(schedule_rows: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None]:
    """官方排程列 → (canonical 狀態, 依據的那一列)；未觀測過的組合一律 `unknown`。

    選列規則：現行列（`PresentStatus=1`）優先，再取最新 `raw_game_date`、同日取最後觀測到
    的一筆——一場保留賽續賽完成時，官網是在**同一個日期**上把 `GameResult` 由 `2` 改成
    `0`，只比日期會取到舊值。

    `games`（單場狀態）與 `daily`（首頁未定案場次）兩 router 共用；勿在任一側重寫判定。
    """
    if not schedule_rows:
        return "unknown", None
    active = [row for row in schedule_rows if row.get("raw_present_status") == 1]
    pool = active or schedule_rows
    selected = max(
        pool,
        key=lambda row: (
            row.get("raw_game_date") or _date.min,
            row.get("last_seen_at") or row.get("fetched_at"),
        ),
    )
    key = (selected.get("raw_present_status"), str(selected.get("raw_game_result") or ""))
    return _OFFICIAL_STATUS_BY_RAW.get(key, "unknown"), selected
