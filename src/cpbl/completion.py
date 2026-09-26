"""賽事完賽 [completion] 的最小共用契約。

**兩代判準並存中**（DATA-TIE-REMEDY1，兩段式切換）：

* :func:`completed_games_sql` / :func:`is_completed`——**舊判準**（比分自證）。
  手動回填 CLI（``cpbl_pitch_tracking``、``cpbl_gamelog`` 的目標場清單）與覆蓋檢查仍用它。
* :func:`daily_chain_completed_games_sql`——每日 refresh 鏈（``run_refresh_recent``）的
  選場（#213）：2026 起只認官方 final／完賽證據，比分不作依據；更早球季仍走舊判準。
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
_SCHEDULE_ALIAS = "gss_"

# ⛔ 必須與 ``cpbl.api.helpers.OFFICIAL_SCHEDULE_ORDER_BY`` 逐字相同（官方排程選列規則）。
# 抄一份是因為 models 層經本模組載入時不得 import ``cpbl.api``（分層守衛見
# ``tests/test_winprob_val.py``）；兩邊相等由 ``tests/test_daily_chain_completion.py`` 釘住。
_OFFICIAL_SCHEDULE_ORDER_BY = (
    "COALESCE(raw_present_status = 1, FALSE) DESC, raw_game_date DESC NULLS LAST, "
    "COALESCE(last_seen_at, fetched_at) DESC, fetched_at DESC, payload_hash DESC"
)

# 每日鏈改用「官方 final／核准證據」選場的起始球季（#213）。更早球季沿用舊判準、不批量改動。
DAILY_CHAIN_FINAL_FROM_YEAR = 2026


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
    現存的呼叫端是 ``run_check_coverage`` 與手動回填 CLI（每日鏈自 #213 改走
    :func:`daily_chain_completed_games_sql`），
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
    official_final: bool = False,
) -> bool:
    """**新判準**：日期界線 **AND**（比分 > 0 **OR** 有外部完賽證據 **OR** 0:0 且官方 final）。

    ``has_evidence`` 來自 ``cpbl.game_completion_evidence``（官方 box 取證或需求方核准）；
    ``official_final`` 為官方排程現行列標示 final（:func:`official_final_sql`，#213）。
    0:0 且兩者皆無者一律回 ``False``——既不納入完成場，也不代表「這場沒打」，
    而是**隔離為待判讀**（全庫 288 場 0:0 中僅 5 場經證實為和局）。
    """
    if game_date > as_of:
        return False
    # 0:0 分支要求兩邊比分都**不是 None**：SQL 端 ``NULL + NULL = 0`` 為 NULL、不成立。
    return ((home_score or 0) + (away_score or 0) > 0 or has_evidence
            or (official_final and home_score == 0 and away_score == 0))


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

    ⭐ 0:0 另有「官方 final」分支（#213）：2026/D/234 官方標示五局 0:0 完賽卻無證據列；
    只收 0:0 的那一支，帶比分場的判定不變。
    """
    p = f"{_require_alias(alias)}."
    return (
        f"({p}game_date <= {as_of_sql} AND ("
        f"{p}home_score + {p}away_score > 0 OR {_evidence_exists_sql(alias)} OR ("
        f"{p}home_score + {p}away_score = 0 AND {official_final_sql(alias)})))"
    )


def _require_alias(alias: str) -> str:
    if not alias:
        raise ValueError("alias 不可為空：相關子查詢需要限定詞才能正確關聯外層 games")
    return alias


def _evidence_exists_sql(alias: str) -> str:
    p = f"{_require_alias(alias)}."
    e = _EVIDENCE_ALIAS
    return (
        f"EXISTS (SELECT 1 FROM cpbl.game_completion_evidence {e} "
        f"WHERE {e}.year = {p}year AND {e}.kind_code = {p}kind_code "
        f"AND {e}.game_sno = {p}game_sno)"
    )


def official_final_sql(alias: str = "games") -> str:
    """外層 ``cpbl.games`` 那一場的官方排程**被選中列**是否為 ``final``（相關子查詢）。

    與 :func:`cpbl.api.helpers.official_status` 同一套選列規則（``_OFFICIAL_SCHEDULE_ORDER_BY``）
    與同一個 raw 組合 ``(PresentStatus=1, GameResult='0')``——⛔ 勿另寫一套，兩邊講不同的話
    就等於同一場比賽有兩種官方狀態。ORDER BY 的欄名未限定，只解析得到內層排程表。
    查無排程列 → 不成立（fail closed，與 ``official_status`` 的 ``unknown`` 同向）。
    """
    p = f"{_require_alias(alias)}."
    s = _SCHEDULE_ALIAS
    return (
        f"EXISTS (SELECT 1 FROM (SELECT {s}.raw_present_status, {s}.raw_game_result "
        f"FROM cpbl.game_schedule_status_revisions {s} "
        f"WHERE {s}.year = {p}year AND {s}.kind_code = {p}kind_code "
        f"AND {s}.game_sno = {p}game_sno "
        f"ORDER BY {_OFFICIAL_SCHEDULE_ORDER_BY} LIMIT 1) {s}sel "
        f"WHERE {s}sel.raw_present_status = 1 AND {s}sel.raw_game_result = '0')"
    )


def daily_chain_completed_games_sql(
    alias: str = "games",
    as_of_sql: str = TAIPEI_TODAY_SQL,
) -> str:
    """每日 refresh 鏈（``run_refresh_recent``）的選場條件（#213）。

    * ``year >= DAILY_CHAIN_FINAL_FROM_YEAR``：日期界線 **AND**（官方 final **OR** 完賽證據）。
      ⛔ **比分不作完賽依據**——賽中已得分場、帶中止比分的保留賽（``reserved``）、官方尚未
      定案的昨日場都不納入；0:0 且官方 final（2026/D/234）則納入。
    * 更早球季：原樣走舊判準（比分自證），不批量改動歷史。

    代價（規劃已接受）：官方 final 晚於隔天才出現時，整季缺口掃描（gamelog／PA build）
    會追上，只掃當日窗的對戰增量可能漏補。
    """
    p = f"{_require_alias(alias)}."
    return (
        f"(CASE WHEN {p}year >= {DAILY_CHAIN_FINAL_FROM_YEAR} "
        f"THEN {p}game_date <= {as_of_sql} AND ("
        f"{official_final_sql(alias)} OR {_evidence_exists_sql(alias)}) "
        f"ELSE {p}home_score + {p}away_score > 0 AND {p}game_date <= {as_of_sql} END)"
    )


if __name__ == "__main__":
    # stdout 是 shell 契約：refresh-cpbl-prod.sh 以 $(python -m cpbl.completion …)
    # 直接內插進 SQL，輸出必須恰為一行。
    #
    # ⚠️ **同步閘門必須走 ``--with-evidence``**（DATA-TZ-BOUNDARY-SUCCESSION1 (3c)，已修）。
    # 原本閘門吃**預設分支**（舊判準 ＋ ``CURRENT_DATE``）而 ``/api/info``（info.py:52／:88）
    # 吃 ``completed_games_sql_with_evidence("games")``（新判準 ＋ 台北），兩者被
    # ``verify_refresh_info.py`` 拿去做**精確相等**比對，不等就擋同步——擋在**備份已完成、
    # 正要 upsert** 的位置。錯配有兩層，兩層都已收斂到同一支 helper：
    #   * **判準層**：舊判準漏判經取證的 0:0 真和局。本機實測分類差**恰 5 場**
    #     （2018/A/124、2021/A/256、2023/A/119、2023/A/175、2025/A/233）。
    #   * **日界層**：閘門在 ``docker exec psql`` 求值——那是 **pool 之外**的 session，
    #     ``cpbl.db`` 的 ``configure`` 管不到它，其 ``CURRENT_DATE`` 仍是 UTC
    #     （2026-08-20 20:2x UTC 實測：該 session ``SHOW timezone`` = UTC、
    #     ``CURRENT_DATE`` = 2026-08-20，而台北已是 08-21）。所以這一處**不能靠 session
    #     timezone 解決**，修法必須讓產生的 SQL **文字**自帶時區——:data:`TAIPEI_TODAY_SQL`
    #     即是，而它正是 ``completed_games_sql_with_evidence`` 的預設 as_of。
    # ⚠️ ``--with-evidence`` 的輸出**帶 ``g.`` 別名前綴**（相關子查詢的正確性要求，見
    # :func:`completed_games_sql_with_evidence` 的說明），故呼叫端的查詢來源必須寫成
    # ``FROM cpbl.games g``。回歸釘在
    # ``tests/test_backup_prod_db.py::test_refresh_uses_shared_completed_game_contract``
    # 與 ``::test_refresh_gate_and_info_metric_share_one_criterion``（後者逐字比對兩側，
    # 只准差在別名）。⚠️ 預設分支**沒有**改：它仍是舊判準 ＋ ``CURRENT_DATE``，
    # 授權在 ``#53 G4 Phase B``。
    import sys

    if "--with-evidence" in sys.argv[1:]:
        print(completed_games_sql_with_evidence("g"))
    else:
        print(completed_games_sql())
