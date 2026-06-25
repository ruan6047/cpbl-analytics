"""洋將身分分類。

CPBL 洋將額度規則：外籍球員預設占「洋將」名額，但有兩類例外：
- 羅力條款（本土洋將）：未經選秀、在台累積一定球季並提出申請者，不占洋將名額
  （但仍屬外籍）。目前符合者僅羅力、伍鐸（官方認定，申請制、逐年可能變動，需人工確認）。
- 永田條款（外籍本土）：自台灣學生棒球體系經選秀進入職棒者，視同本土選手。
  目前僅高塩將樹一人。

基礎國籍取自 players.country（已完整無 NULL）；上述兩條款為申請制、無法由現有資料
推導，故以手動 override 維護（一次維護、手動刷新）。新增/異動只改本檔常數即可。
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
