"""API 共用工具：預設球季、層級 kind 群組、cursor→dict、四捨五入、特徵字串解析、局數記法換算。"""

from __future__ import annotations

from collections.abc import Callable
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


# ---------------------------------------------------------------------------
# 選列規則（`DATA-OFFICIAL-STATUS-TIEBREAK1`）
#
# **一份規則，兩種轉譯。** 下面這張表是唯一的書面來源：SQL 片段與 Python 排序鍵由同一組
# `(sql, key)` 產生，改一邊就等於改另一邊，不可能只改到其中一側。
#
# 為什麼要這麼做：原本三條讀路徑用三套規則——`games` 單場排程列 `ORDER BY last_seen_at,
# fetched_at, id`、`games` 來源軌跡 `DISTINCT ON (source) … id`、`daily` 未定案批次**完全
# 沒有 `ORDER BY`**。前兩者的最終決勝鍵 `id` 是**兩機各自配號**的（生產端由
# `refresh-cpbl-prod.sh::sync_revision_table` 顯式欄位插入、不搬 `id`），所以同一筆事實在
# 本機與生產可以選到不同的列——2026/D/119 已實測發生。`daily` 更弱：它**完全沒有
# `ORDER BY`**，而無序讀取沒有任何順序契約；它又與 `games` 共用 `official_status`，Python
# `max()` 打平時取迭代順序的第一項，「餵進去的順序」因此本身就是判定的一部分。
#
# 2026/D/165 是「決勝鍵真的會被用到」的實證：該場兩列的 `last_seen_at` 與 `fetched_at`
# **完全相同**（各 1 個 distinct 值），業務欄卻差很多——`id=580` 是 `PresentStatus=0`／
# `2026-07-17`，`id=581` 是 `PresentStatus=1`／`2026-09-15`。舊 `games` 規則
# `last_seen_at DESC, fetched_at DESC, id DESC` 前兩鍵全打平，等於**整場由 `id` 決定**，
# 而 `id` 不跨機。選錯的後果是把同一場比賽顯示在差近兩個月的日期上。
#
# 新規則的最終錨是 `payload_hash`／`source_version`：兩者都是 `canonical_source_version()`
# 對整筆 raw entry 算的 SHA-256，且是各表 UNIQUE 鍵的成員。`payload_hash` 涵蓋
# `GameSeasonCode`，故雜湊相同即 season code 相同，**在讀取分區 `(year, kind_code,
# game_sno)` 內唯一是構造保證、不是觀測結果**。它由本機算出後整欄鏡像到生產，兩機同值。
# 代價是「雜湊比較大的那一筆」沒有業務意義——所以它只在前面所有業務鍵都打平時才生效。
_SCHEDULE_SELECTION_KEYS: tuple[tuple[str, Callable[[dict[str, Any]], Any]], ...] = (
    # 現行列優先。**刻意寫 `= 1` 而不是 `raw_present_status DESC`**：判定要的是「這一列是
    # 現行的那一筆」，不是「狀態碼比較大的那一筆」。今天值域只有 {0,1} 兩者同義，但官網若
    # 有天吐出 2，`DESC` 會讓它蓋過現行列，`= 1` 不會。
    #
    # **`COALESCE(…, FALSE)` 不是裝飾。** `raw_present_status` 在 migration 061 是 nullable，
    # 而 SQL 的 `NULL = 1` 是 `NULL`、不是 `FALSE`。寫成 `(raw_present_status = 1) DESC NULLS
    # LAST` 時 NULL 會被排到 `0` **之後**，Python 的 `None == 1` 卻是 `False`、與 `0` **打平**
    # ——同一份規則兩端給不同答案（實測對抗例：`NULL + 新日期` vs `0 + 舊日期`，SQL 選 `0`
    # 列、Python 選 `NULL` 列）。折成 `FALSE` 之後，NULL／0／2 在兩端一律都是「不是現行
    # 列」，四種取值逐一同構。
    ("COALESCE(raw_present_status = 1, FALSE) DESC",
     lambda row: row.get("raw_present_status") == 1),
    ("raw_game_date DESC NULLS LAST", lambda row: row.get("raw_game_date")),
    # 同日再取最後觀測到的一筆。**不是贅語**——保留賽續賽完成時官網是在**同一個日期**上把
    # `GameResult` 由 `2` 改成 `0`（D#97@08-09、D#119@08-08 實測皆有同日兩列、僅
    # `last_seen_at` 不同），只比日期會取到舊值、把一場已打完的比賽讀成 `reserved`。
    #
    # ⚠️ 以下三個鍵寫的是**裸 `DESC`**，而 PostgreSQL 的 `DESC` 預設是 **NULLS FIRST**
    # （實測 `ORDER BY v DESC` 對 `{1,NULL,0,2}` 回 `[NULL,2,1,0]`），與 `_nulls_last()` 的
    # 「`None` 排最後」相反。**刻意不補 `NULLS LAST`**：三者對應的欄位在 migration 061 都是
    # `NOT NULL`，SQL 端取不到 NULL，補上去是零行為差異的裝飾。第一個鍵之所以必須自己把
    # NULL 折掉，正因為它的欄位在 schema 就是 nullable——差別在**分歧構造上取不取得到**，
    # 不在「有沒有多寫兩個字」。若哪天 migration 把這三欄的 `NOT NULL` 拿掉，這裡要跟著改。
    ("COALESCE(last_seen_at, fetched_at) DESC",
     lambda row: row.get("last_seen_at") or row.get("fetched_at")),
    ("fetched_at DESC", lambda row: row.get("fetched_at")),
    ("payload_hash DESC", lambda row: row.get("payload_hash")),
)

#: `cpbl.game_schedule_status_revisions` 的選列規則（SQL 轉譯）。`games` 與 `daily` 兩條
#: 讀路徑都必須用它——「三條讀路徑共用一份規則」的那一份指的就是這個常數。
OFFICIAL_SCHEDULE_ORDER_BY = ", ".join(sql for sql, _ in _SCHEDULE_SELECTION_KEYS)

#: `cpbl.game_source_revisions` 的選列規則（SQL）。該表沒有 `raw_present_status`／
#: `raw_game_date`，最終錨是 `source_version`（同為 `canonical_source_version()` 的 SHA-256
#: 與 UNIQUE 鍵成員）。這條路徑的選列**全在 SQL**（`DISTINCT ON`），故無 Python 對應鍵。
SOURCE_REVISION_ORDER_BY = (
    "COALESCE(last_seen_at, fetched_at) DESC, fetched_at DESC, source_version DESC"
)


def _nulls_last(value: Any) -> tuple[bool, Any]:
    """`max()` 用的排序元素：`None` 一律排最後，對應 SQL 的 `DESC NULLS LAST`。

    兩個 `None` 相比時 tuple 先比 `False == False`、再比 `None == None`，皆相等即進到下一
    個鍵，不會對 `None` 做 `<`。程式端收的是 `list[dict]`，欄位沒被投影就是 `None`，缺值時
    會與 `datetime` 相比而 `TypeError`；這裡把它變成有定義的順序。

    **它對第一個鍵是 inert 的**：`row.get(...) == 1` 是全函式（永遠回 `bool`、不回 `None`），
    所以第一個元素恆為 `True`，排序完全由 `bool` 本身決定——這正是要的，因為對應的 SQL 已用
    `COALESCE(…, FALSE)` 把 NULL 折成 `FALSE`。兩端都不再有「第三種狀態」。其餘四個鍵才真的
    靠這層定義 `None` 的位置。
    """
    return (value is not None, value)


def official_status(schedule_rows: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None]:
    """官方排程列 → (canonical 狀態, 依據的那一列)；未觀測過的組合一律 `unknown`。

    選列規則見 `_SCHEDULE_SELECTION_KEYS`——**與呼叫端 SQL 的 `ORDER BY` 是同一份**。

    **為什麼下推到 SQL 之後這一層仍然保留**：本函式的簽章收的是 `list[dict]`，收不到「這串
    列已經排好序」這個前提。改成取 `rows[0]` 會讓正確性依賴一個型別表達不出來的不變式，而
    `daily.py` 當初正是這樣掉進無 `ORDER BY` 的狀態的——那種錯誤會靜默地給出錯答案，不會
    炸。所以這一層**保留為防呆**，但從 `max()`（打平時取迭代順序的第一項）升級為與 SQL 同構
    的**全序**，兩層各自都不再倚賴對方的順序。

    ⚠️ 最終錨 `payload_hash` 缺席時（呼叫端沒投影該欄）全序退化為原本的業務鍵，完全打平時
    仍會落回迭代順序。三條讀路徑都投影了該欄；新增呼叫端請一併投影。

    `games`（單場狀態端點）與 `daily`（首頁未定案場次）兩 router 共用同一份判定；勿在任一側
    重寫，兩邊講不同的話就等於同一場比賽有兩種官方狀態。
    """
    if not schedule_rows:
        return "unknown", None
    selected = max(
        schedule_rows,
        key=lambda row: tuple(_nulls_last(key(row)) for _, key in _SCHEDULE_SELECTION_KEYS),
    )
    key = (selected.get("raw_present_status"), str(selected.get("raw_game_result") or ""))
    return _OFFICIAL_STATUS_BY_RAW.get(key, "unknown"), selected
