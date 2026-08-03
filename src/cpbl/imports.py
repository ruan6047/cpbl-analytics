"""洋將身分分類。

CPBL 洋將額度規則：外籍球員預設占「洋將」名額，但有兩類例外：
- 羅力條款（本土洋將）：未經選秀、在台累積一定球季並提出申請者，不占洋將名額
  （但仍屬外籍）。目前符合者僅羅力、伍鐸（官方認定，申請制、逐年可能變動，需人工確認）。
- 永田條款（外籍本土）：自台灣學生棒球體系經選秀進入職棒者，視同本土選手。
  目前僅高塩將樹一人。

基礎國籍取自 players.country。**這一欄會出現缺口，不是恆為非 NULL**：2026-07 曾有 14
位 2025 年登錄洋將同時缺 country／birthday（`INGEST-PLAYER-BIO-GAP1`，已補齊），成因是
opendata 只涵蓋到 2024、而 bio 爬蟲當時的 `parse_bio` 還讀不到這兩欄。country 為 NULL 時
`classify()` 保守回 'local'，缺口會直接變成**把洋將標成本土**的靜默錯誤（該次 2025 有
164 個先發席次被誤標，占該年 22.8%）。

維護註記：判斷某列的 bio 欄是否可信，**不能只看 `bio_updated_at` 非 NULL**——那只證明
「被走訪過」，不證明「被有能力讀該欄的解析器版本走訪過」。country／birthday 的解析能力
自 `cf9d8b8`（2026-07-06 09:19 UTC）才加入，時間戳早於它的列即使非 NULL 也可能是空值。
`cpbl-scrape-bio` 不在每日排程鏈上，且 `--skip-done` 依時間戳跳過，故這類缺口不會自癒。

上述兩條款為申請制、無法由現有資料推導，故以手動 override 維護（一次維護、手動刷新）。
新增/異動只改本檔常數即可。
"""

# 羅力條款 → 本土洋將（外籍，但不占洋將名額）
LOREE_PIDS = {
    "0000000121",  # 羅力 Mike Loree
    "0000000762",  # 伍鐸 Bryan Woodall
}

# 永田條款 → 外籍本土（外籍國籍，但視同本土、不受洋將限制）
NAGATA_PIDS = {
    "0000006818",  # 高塩將樹 Takashio Masaki（目前唯一）
}

# 分類碼 → 中文標籤
LABELS = {
    "local": "本土",
    "import": "洋將",
    "loree": "本土洋將",
    "nagata": "外籍本土",
}


def classify(player_id: str, country: str | None) -> str:
    """回傳身分碼：'local' | 'import' | 'loree' | 'nagata'。

    優先序：永田條款（外籍本土）> 本土國籍 > 羅力條款（本土洋將）> 一般洋將。
    country 為 None（資料缺）時保守視為本土，不誤標洋將。
    """
    if player_id in NAGATA_PIDS:
        return "nagata"
    if country is None or country == "中華民國":
        return "local"
    if player_id in LOREE_PIDS:
        return "loree"
    return "import"
