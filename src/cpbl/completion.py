"""賽事完賽 [completion] 的最小共用契約。

**兩代判準並存中**（DATA-TIE-REMEDY1，兩段式切換）：

* :func:`completed_games_sql` / :func:`is_completed`——**舊判準**（比分自證）。
  每日 refresh 鏈（``run_refresh_recent``、``cpbl_pitch_tracking``、``cpbl_gamelog``
  的目標場清單）**本階段仍用它**：#53 的 G4 Phase B 尚未完成，且其資源宣告佔用鏈端
  writer；換判準會改變爬取母體。Phase 2（G4 Phase B 之後）再切換。
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

**日界落差（DATA-TZ-BOUNDARY-SUCCESSION1 已收斂大半，2026-08-21）**：session timezone
現由 ``cpbl.db`` 的 pool ``configure`` 明示為 ``Asia/Taipei``，故**在應用程式連線內**
``CURRENT_DATE`` ≡ :data:`TAIPEI_TODAY_SQL`，兩支 helper 的預設**在實務上已同日**。
落差只在 **pool 之外**求值時仍然存在（``docker exec psql``、任何不經本模組連線的 session）。

下面這段是**歷史推導**，記錄當初為什麼「擱置」是合理的；前提（DB session ＝ UTC）已被
上述改動取代，但兩支 helper 預設**字面上**仍不同，故保留原文以免下一個人重推一次：

原文——兩支 helper 的預設 ``as_of`` **不同**（舊判準用 :data:`UTC_TODAY_SQL`、新判準用
:data:`TAIPEI_TODAY_SQL`），DB 跑 UTC，故台北 00:00–08:00 這 8 小時兩者相差一天。
這**不是**遺漏：

* 兩者都是 ``game_date <= as_of`` 的**上界**用法。UTC 落後只會「晚 8 小時納入」，
  方向保守，DATA-TZ-BOUNDARY1 盤點後明確擱置、排在 REMEDY1 Phase 2 隨判準一起切。
* 舊判準的呼叫端全在每日 refresh 鏈（``run_refresh_recent``）上，現由 #53 的 G4 Phase B
  資源宣告佔用；改日界＝改爬取母體。且鏈的排程是 10:10 CST，落在窗外，**排程情境下不觸發
  此落差**。

實測落差面（2026-08-08 00:45 CST 窗內，唯讀全庫）：同一判準換 as_of，母體差**恰 1 場**
——``2026/D/119``（保留賽，原訂 06-16、續賽日 08-08，帶中止比分 5:4）。這不是巧合而是
結構性的：台北日 T 當天 00:00–08:00 時，**排在 T 的一般場次尚未開打**（0:0 無證據，
兩種 as_of 都不納入），唯一會被日界翻轉的就是**改期後帶著中止比分的保留賽**。

⚠️ 因此 ``completed_games_sql(...)`` 與 ``completed_games_sql_with_evidence(...)``
**不可在同一個比較中混用預設值**——那會把「判準差」與「日界差」混淆成同一個量。
要比判準就把同一個 ``as_of`` 明示傳給兩邊（見 ``tests/test_completion_evidence.py``）。

⚠️ **括號是語意的一部分，不是排版**：日期界線必須包在最外層、``OR`` 子句必須加括號。
寫成尾隨的 ``AND`` 會因 SQL 的 ``AND`` 優先於 ``OR`` 而解析成
``score > 0 OR (evidence AND date)``——正比分的場次會完全繞過日期界線，實測誤納 5 場
掛未來日期的保留賽（2026/D 的 119/97/118/117/165）。
"""

from __future__ import annotations

from datetime import date

# 台北日界，**自帶時區、不依賴執行它的 session**。這一點是刻意的：SQL 文字有時會離開
# 應用程式（見本檔 ``__main__`` 的 shell 契約），在 pool 管不到的 session 裡求值。
TAIPEI_TODAY_SQL = "(now() AT TIME ZONE 'Asia/Taipei')::date"

# 舊 helper（:func:`completed_games_sql`）的預設日界，**且自 SUCCESSION1 起只剩這一個用途**。
#
# ⚠️ **名字與行為的關係已經變了，讀之前先看這裡**：pool 的 session timezone 現為
# ``Asia/Taipei``（``cpbl.db.SESSION_TIMEZONE``），所以在**應用程式連線內**求值時
# ``CURRENT_DATE`` ≡ :data:`TAIPEI_TODAY_SQL`。它仍叫 UTC，是因為它**唯一**的用途是釘住
# 「舊 helper 的預設沒有被人動過」這件事——那個預設在等 ``#53 G4 Phase B`` 的授權
# （見 ``tests/test_tz_boundary.py::test_legacy_chain_helper_deliberately_keeps_utc_default``
# 的 docstring），本卡無權替它決定。在 pool 之外（如 ``docker exec psql``）求值時它仍是 UTC。
#
# ⚠️ 換句話說：這個常數現在是一個**佔位的歷史標記**，不是「我要 UTC」的宣告。要一個真正
# 不隨 session 飄動的 UTC 日界，得寫 ``(now() AT TIME ZONE 'UTC')::date``——目前無人需要。
UTC_TODAY_SQL = "CURRENT_DATE"

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


def completed_games_sql(as_of_sql: str = UTC_TODAY_SQL) -> str:
    """回傳與 :func:`is_completed` 等價、可嵌入 ``cpbl.games`` 查詢的 SQL 條件（**舊判準**）。

    ⚠️ **預設值刻意原封不動**（DATA-TZ-BOUNDARY-SUCCESSION1 2026-08-21 再次確認）：本函式
    現存的呼叫端都在每日 refresh 鏈上（``run_refresh_recent``、``run_check_coverage``），
    切換授權在 ``#53 G4 Phase B``，不歸本函式的任何一次改動決定。實測依據：把這個預設改成
    台北後全套 **6 failed**，其中三條落在 ``_lagging_pitch_games``／``_pa_build_targets``／
    ``_active_kinds``——那是**改預設會讓別的檔案行為改變、而那個檔案的 diff 裡一行都看不到**
    的形狀。回歸釘在 ``tests/test_tz_boundary.py::test_legacy_chain_helper_deliberately_keeps_utc_default``。

    ⚠️ 但**行為**已經變了，別把「預設沒改」讀成「日界沒變」：pool 的 session timezone 自
    SUCCESSION1 起為 ``Asia/Taipei``，所以經 ``cpbl.db.conn()`` 求值時 ``CURRENT_DATE``
    ≡ :data:`TAIPEI_TODAY_SQL`。仍是 UTC 的只有 **pool 之外**的 session。

    新程式碼請用 :func:`completed_games_sql_with_evidence`（判準較新，且預設已是台北）。
    """
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
    # stdout 是 shell 契約：refresh-cpbl-prod.sh 以 $(python -m cpbl.completion)
    # 直接內插進 SQL，輸出必須恰為一行、不得帶表別名前綴。
    #
    # ⚠️ **已知未修：同步閘門與 /api/info 用兩套判準做精確相等比對**
    # （DATA-TZ-BOUNDARY-SUCCESSION1 驗收 (3c)，本卡**未**修，見交付報告）。
    #   * 閘門（refresh-cpbl-prod.sh:386）吃**預設分支**＝舊判準 ＋ ``CURRENT_DATE``，
    #     且在 ``docker exec psql``——那是 **pool 之外**的 session，仍是 UTC。
    #     pool 的 ``configure`` 管不到它，所以這一處**不能靠 session timezone 解決**；
    #     修法必須讓產生的 SQL 文字自帶時區（本檔的 :data:`TAIPEI_TODAY_SQL` 即是）。
    #   * ``/api/info``（info.py:52／:88）吃 ``completed_games_sql_with_evidence("games")``
    #     ＝新判準 ＋ 台北。
    #   兩者被 verify_refresh_info.py 拿去做**精確相等**比對，不等就擋同步。
    # 2026-08-21 02:5x 實測兩側皆 454、尚未分歧；分歧條件是「窗內有當日完成場」或
    # 「該季存在經取證的 0:0」。修這一處必須同時改
    # ``tests/test_backup_prod_db.py::test_refresh_uses_shared_completed_game_contract``
    # （它逐字釘住 ``COMPLETED_GAMES_SQL="$(uv run python -m cpbl.completion)"``），
    # 而該檔不在本卡資源宣告內，故留給後續卡。
    import sys

    if "--with-evidence" in sys.argv[1:]:
        print(completed_games_sql_with_evidence("g"))
    else:
        print(completed_games_sql())
