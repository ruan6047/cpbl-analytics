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


# 官網排程 raw 詞彙 → canonical phase 字彙。**刻意與 live worker 的 `_STATUS_PHASE` 用同一
# 組字**（`final`／`scheduled`／`postponed`／`reserved`）：`/games/{sno}/status` 的
# `canonical_phase` 在沒有 live snapshot 時退回本表，兩條路徑講不同的話就等於同一場比賽有
# 兩種狀態語彙。
#
# key＝(`PresentStatus`, `GameResult`)。**`PresentStatus` 不是「已開打」**（`cpbl_site.py`
# `_primary_entry` 的註解用詞較鬆，易被沿用成錯誤前提）：同一 `sno` 每個排定日期各一列，
# `1`＝該列是**現行**那一筆、`0`＝已被改期取代的舊列。`GameResult` 依 GLOSSARY
# 〈保留賽／`delay_kind`〉：`0`＝該日打完、`1`＝延賽、`2`＝保留（已開賽中止）、空＝該日尚無結果。
#
# 本表**只收已觀測為「被選中列」的組合**，因為判定讀的就是被選中的那一列（見
# `official_status` 的選列規則）；raw 表裡出現過但從不會被選中的組合不算證據。可重跑證據
# （2026-08-10 本機 `cpbl.game_schedule_status_revisions`，600 場／797 列，全為 2026）：
#
#     WITH ranked AS (
#       SELECT *, ROW_NUMBER() OVER (PARTITION BY year, kind_code, game_sno
#         ORDER BY (raw_present_status = 1) DESC NULLS LAST, raw_game_date DESC NULLS LAST,
#                  COALESCE(last_seen_at, fetched_at) DESC) AS rn
#       FROM cpbl.game_schedule_status_revisions)
#     SELECT raw_present_status, COALESCE(raw_game_result,''), count(*)
#     FROM ranked WHERE rn=1 GROUP BY 1,2 ORDER BY 1,2;
#
# 被選中列只有四種組合，合計 600：`(1,'0')` 421／`(1,'')` 172／`(1,'1')` 3／`(1,'2')` 4。
# 對 `cpbl.games` 交叉驗證，四種各自的語意都站得住：
#
# - `(1,'0')`＝`final`：421 場**全部**有比分且無一排在未來。
# - `(1,'')`＝`scheduled`：172 場**全部**無比分，日期在該次爬取當下皆未過（含 22 場已改期的延賽
#   補賽日）。**「日期在未來」是快照性質、不是不變式**：官網還沒更新結果時，比賽日過了該列仍是
#   `(1,'')`（2026-08-13 10:10 爬蟲落庫**前**實測有 5 場 08-12 的比賽停在此組合，落庫後歸零）。
#   判定本身不看日期、只讀 raw 組合，所以這件事不影響映射；它反而正是 daily 那格要講的話——
#   「官方那側也還沒有結果」與「官方說打完了、我們卻還是 0–0」是兩回事。
# - `(1,'1')`＝`postponed`：3 場（A#14／254／255），皆 `delay_kind='延賽'`、無比分。官網宣告
#   延賽後、補賽日公布前，該列仍是現行列（A#254／255 實測 `game_date == orig_date`），故
#   `PresentStatus` 維持 1；原本要求 `PresentStatus=0` 才算 postponed 的規則因此**永遠命中
#   不到**，真正的延賽場全落到 `unknown`——這正是本卡要修的痛點。
# - `(1,'2')`＝`reserved`：4 場（D#117／118／164／165），皆 `delay_kind='保留'` 且補賽日在未來。
#
# `PresentStatus=0` 的舊列**一律不映射**：有 present=0 列的 57 場**全部**同時有現行列，那些
# 舊列從來不會被選中，沒有可驗證的證據 → 維持 fail closed 的 `unknown`。（原本的
# `(0,'1'): postponed` 一併移除：它不是保守規則，是一條無法被任何觀測驗證的死規則。）
_OFFICIAL_STATUS_BY_RAW: dict[tuple[Any, str], str] = {
    (1, "0"): "final",
    (1, ""): "scheduled",
    (1, "1"): "postponed",
    (1, "2"): "reserved",
}


def official_status(schedule_rows: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None]:
    """官方排程列 → (canonical 狀態, 依據的那一列)；未觀測過的組合一律 `unknown`。

    選列規則：現行列（`PresentStatus=1`）優先，再取最新 `raw_game_date`、同日再取最後觀測到
    的一筆。**第三個鍵不是贅語**——保留賽續賽完成時，官網是在**同一個日期**上把 `GameResult`
    由 `2` 改成 `0`（D#97@08-09、D#119@08-08 實測皆有同日兩列、僅 `last_seen_at` 不同），
    只比日期會取到舊值、把一場已打完的比賽讀成 `reserved`。

    `games`（單場狀態端點）與 `daily`（首頁未定案場次）兩 router 共用同一份判定；勿在任一側
    重寫，兩邊講不同的話就等於同一場比賽有兩種官方狀態。
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
