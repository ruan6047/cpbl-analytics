"""賽事完賽 [completion] 的最小共用契約。

**兩代判準並存中**（DATA-TIE-REMEDY1，兩段式切換）：

* :func:`completed_games_sql` / :func:`is_completed`——**舊判準**（比分自證）。
  每日 refresh 鏈（``run_refresh_recent``、``cpbl_pitch_tracking``、``cpbl_gamelog``
  的目標場清單）**本階段仍用它**：G4 觀測期進行中，換判準會改變爬取母體而污染觀測。
  Phase 2（G4 Phase B 之後）再切換。
* :func:`completed_games_sql_with_evidence` / :func:`is_completed_game`——**新判準**
  （比分 **OR** 外部證據），供非鏈消費端（API／features／models）。

為什麼需要新判準：一場真實的 **0:0 和局**滿足 ``0 + 0 = 0``，被舊判準判為「未完成」。
全庫實測 5 場（2018/A/124、2021/A/256、2023/A/119、2023/A/175、2025/A/233），
官方 ``standings.tie`` 1990–2024 逐年對帳 7/7 完全解釋，官方 box 頁亦已直接取證
（``game_detail`` 標記 ``final``、記分板皆滿規章 §38 的 5 局門檻）。

為什麼不能靠自家欄位硬湊：``present_status = 1`` 對「是否已完賽」毫無鑑別力
（全庫 13,480 場為 1，含 192 場未來日期）；實測會誤納 288 場 0:0 而其中僅 5 場為真。
「有無逐場資料」同樣無效——5 場真和局本身也 livelog／gamelog／scoreboard 三表全空
（爬蟲用同一判準選目標，故從未抓過它們，缺口自我隱蔽）。故判準**必須引入外部證據**，
證據來源見 ``cpbl.game_completion_evidence``（migration 070）。

⚠️ **括號是語意的一部分，不是排版**：日期界線必須包在最外層、``OR`` 子句必須加括號。
寫成尾隨的 ``AND`` 會因 SQL 的 ``AND`` 優先於 ``OR`` 而解析成
``score > 0 OR (evidence AND date)``——正比分的場次會完全繞過日期界線，實測誤納 5 場
掛未來日期的保留賽（2026/D 的 119/97/118/117/165）。
"""

from __future__ import annotations

from datetime import date

# DB timezone 為 UTC，``CURRENT_DATE`` 在台北 00:00–08:00 會指向前一日。
# 完成場的「今天」必須以台北日界為準（DATA-RULES-AUDIT1 D7）。
TAIPEI_TODAY_SQL = "(now() AT TIME ZONE 'Asia/Taipei')::date"

# 證據子查詢的別名：取不易與外層查詢碰撞的名字（外層常用 g/e/b/l）。
_EVIDENCE_ALIAS = "gce_"


def is_completed(
    home_score: int | None,
    away_score: int | None,
    game_date: date,
    as_of: date,
) -> bool:
    """**舊判準**：比分已產生且賽程日不晚於觀測日。

    僅供每日 refresh 鏈沿用至 Phase 2；新程式碼請用 :func:`is_completed_game`。
    """
    return (home_score or 0) + (away_score or 0) > 0 and game_date <= as_of


def completed_games_sql(as_of_sql: str = "CURRENT_DATE") -> str:
    """回傳與 :func:`is_completed` 等價、可嵌入 ``cpbl.games`` 查詢的 SQL 條件（**舊判準**）。"""
    return f"home_score + away_score > 0 AND game_date <= {as_of_sql}"


def is_completed_game(
    home_score: int | None,
    away_score: int | None,
    game_date: date,
    as_of: date,
    has_evidence: bool = False,
) -> bool:
    """**新判準**：日期界線 **AND**（比分 > 0 **OR** 有外部完賽證據）。

    ``has_evidence`` 來自 ``cpbl.game_completion_evidence``（官方 box 取證或需求方核准）。
    0:0 且**無**證據者一律回 ``False``——既不納入完成場，也不代表「這場沒打」，
    而是**隔離為待判讀**（全庫 288 場 0:0 中僅 5 場經證實為和局）。
    """
    if game_date > as_of:
        return False
    return (home_score or 0) + (away_score or 0) > 0 or has_evidence


def completed_games_sql_with_evidence(
    alias: str = "games",
    as_of_sql: str = TAIPEI_TODAY_SQL,
) -> str:
    """回傳與 :func:`is_completed_game` 等價、可嵌入 ``cpbl.games`` 查詢的 SQL 條件。

    ``alias``＝外層查詢給 ``cpbl.games`` 的別名（如 ``"g"``）。查詢未取別名時用預設的
    ``"games"``——PostgreSQL 允許以表名本身當限定詞。

    ⚠️ **外層欄位一律加限定詞，這是正確性要求不是風格**：相關子查詢 [correlated
    subquery] 內的**未限定**欄名會優先解析到**內層**表。若寫成
    ``WHERE gce_.year = year``，PostgreSQL 解析為 ``gce_.year = gce_.year``——恆真，
    EXISTS 退化成「證據表有沒有任何一列」，於是**每一場** 0:0 都被判完成
    （實測誤納 318 場，而非應有的 5 場）。

    產出的條件**自帶最外層括號**，可直接以 ``AND`` 串接進任何 ``WHERE``，
    不受呼叫端既有 ``OR`` 影響。
    """
    if not alias:
        raise ValueError("alias 不可為空：相關子查詢需要限定詞才能正確關聯外層 games")
    p = f"{alias}."
    e = _EVIDENCE_ALIAS
    return (
        f"({p}game_date <= {as_of_sql} AND ("
        f"{p}home_score + {p}away_score > 0 OR EXISTS ("
        f"SELECT 1 FROM cpbl.game_completion_evidence {e} "
        f"WHERE {e}.year = {p}year AND {e}.kind_code = {p}kind_code "
        f"AND {e}.game_sno = {p}game_sno)))"
    )


if __name__ == "__main__":
    print(completed_games_sql())
    print(completed_games_sql_with_evidence("g"))
