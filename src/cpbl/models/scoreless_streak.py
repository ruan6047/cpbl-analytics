"""投手「連續無**自責**分局數」——定位而非重建，輸出可證明不高估的下界。

**本模組不重建自責分。** 官方規則 9.16 讓自動重建不可行（9.16(a) 要求反事實重播與假想
第三出局；規則本身兩處寫明「判斷有疑慮時應對投手有利」；9.16(g) 繼承跑者按**人數**而非
按人歸屬）。因此 `cpbl.pitching_gamelog.earned_runs` 是官方紀錄員的值，就是權威——
本模組只讀它，不推翻它、不補算它。搜尋本檔不會找到任何失誤／捕逸／出局機會的判斷。

## 名詞（紅線 5）

本指標是「連續無**自責**分局數」，**不是**「連續無失分局數」。失誤造成的非自責失分
**不會**中斷本指標（與 ERA 語意一致），這是刻意的；所有對外欄位與文案都必須帶上
「自責」二字，`METRIC_NOTE` 是該說明的單一來源。

## 演算法：只做兩件事

以投手的出賽（appearance）由新到舊回走：

1. **出賽 `earned_runs = 0`** → 該次出賽官方認定零自責分，其**全部**官方出局數計入。
   不需要 livelog、不需要任何推論。
2. **出賽 `earned_runs > 0`** → 連續紀錄在該次出賽內中斷。改用 `cpbl.game_livelog`
   **定位**：把該場切成半局，尾段只採計「整個半局（不分投手）零得分」的半局。
   半局零得分 ⇒ 該半局沒有任何分數可被判給任何投手 ⇒ 對本投手零自責分。
   出局數則採 `forced_outs()`——**允許任意事件被隱藏後仍成立的下界**，不再用
   「他投完整個半局所以是 3 outs」這種需要證明事件齊全的推論（見該函式 docstring）。

回走遇到任何不確定一律**中斷**（紅線 2：寧可少報一局，不可多報一局）：

| 情境 | 處理 |
|---|---|
| 官方 ER 或局數缺值 | 中斷 |
| 保留賽（`delay_kind='保留'`） | 中斷。該場橫跨 orig_date→game_date，任一種排序都可能把 ER 場排錯位置而高估；場次極少（2018+ 僅 8 場），直接中斷最乾淨 |
| ER>0 的那場沒有 livelog | 尾段 0 出局數 |
| **該場 livelog 覆蓋不完整**（半局缺漏／重複、與 `game_scoreboard` 不一致、投手局序不連續、觀測出局數少於官方局數） | 尾段 0 出局數。**這是紅線 2 最關鍵的一道閘門**——缺漏的半局會被「跨過」而非被看見，導致更早的乾淨半局被誤採計。見 `coverage_reason` |
| 半局有任何得分跡象（livelog **或** `game_scoreboard`） | 停止採計（該半局及更早都不算） |
| 半局零得分但歸屬證明不到出局數 | 該半局採計 0 出局數，但**繼續**往前（零得分已足以證明零自責分） |
| 出局數歸屬 | 一律走 `forced_outs()` 的強制下界；證明不到就是 0，不做補插 |
| 出賽早於 `DATA_FROM_YEAR`（2018） | **截斷**並 `boundary_limited=True`（紅線 4）。取數層 SQL 也擋一次，兩層都 enforce——只在 payload 顯示年份不算執行 |
| 走完所有可得出賽仍未中斷 | `boundary_limited=True`（`game_livelog`／`pitching_gamelog` 皆僅 2018+，不得沉默截斷） |

## 賽別範圍：只算例行賽，季後賽「乾淨跳過、掉分中斷」

需求方裁定（2026-07-28）：本紀錄**只計例行賽局數**（一軍 A／二軍 D），不沿用
`KIND_GROUPS` 把季後賽併入同層。理由是 MLB／NPB 慣例即連續紀錄只算例行賽，使用者
手邊的媒體數字也是這個口徑，混入季後賽會被當成算錯。

跨季時中間的季後賽出賽（一軍 E／C、二軍 F）依 `counted_kinds` 之外的規則處理：

| 季後賽出賽 | 處理 | 為什麼 |
|---|---|---|
| 官方 `earned_runs = 0` | **跳過**：局數不計入，也不中斷 | 它不屬於本紀錄的母體，沒有中斷它的理由 |
| 官方 `earned_runs > 0` | **中斷**（`BREAK_POSTSEASON_EARNED_RUN`） | 見下 |

**為什麼掉分要中斷、而不是一律跳過**（此為執行者裁定，理由留痕）：

1. **紅線 2 的方向**。這條規則下的值同時是「只算例行賽（季後賽全跳過）」與「一軍所有
   比賽都算」**兩種讀法的下界**——任一讀法下都不會高估。一律跳過則只在前一種讀法下
   成立，遇到第二種讀法就是高估。
2. **可理解性**。一律跳過會產生「這條連續紀錄橫跨一場他被打爆的台灣大賽」的輸出，
   讀者無法接受，而本專案的產品價值在透明與教育。
3. **不變式好講也好驗**。此規則下「起算場之後、該投手在**任何**一軍賽別的出賽都沒有
   自責分」恆為真，是可窮舉驗證的強陳述（對帳 R7）。

被跳過的出賽以 `StreakResult.skipped` 留存，並經 API 對外揭露（`skipped_postseason_*`），
讓讀者知道紀錄中間發生過什麼——不做沉默跳過。

## 兩個值（兩種對帳基礎，皆為下界）

- `strict_outs`：只由**官方 ER=0 的整場出賽**組成。宣稱的每一局，其所屬出賽的官方
  `earned_runs` 必為 0 ——即卡面紅線 3 的**字面**對帳基礎（出賽層級的粒度）。
- `outs`：`strict_outs` ＋ 中斷那場的尾段半局。尾段的每一個半局另以**半局層級**的
  更強證明滿足紅線 3 的**意圖**：「整個半局、不分投手、零得分」⇒ 沒有任何分數存在
  可被判給任何人 ⇒ 對本投手零自責分。這比「該場 ER=0」更緊（連非自責分都沒有），
  並同時繞開自責／非自責分野與 9.16(g) 繼承跑者歸屬。

兩者各有獨立的窮舉對帳（`scripts/reconcile_scoreless_streak.py` 的 R1／R2），皆零例外。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

METRIC = "consecutive_earned_run_free_innings"
METRIC_LABEL = "連續無自責分局數（保守下界）"
METRIC_NOTE = (
    "本指標為「連續無**自責**分局數」，非「連續無失分局數」："
    "失誤造成的非自責失分不中斷本指標（與 ERA 語意一致）。"
    "自責分一律採官方紀錄（pitching_gamelog.earned_runs），本專案不重算。"
    "所有不確定情境一律往「中斷」解讀，故本值為**下界**，不會高估。"
)
DATA_FROM_YEAR = 2018
BOUNDARY_NOTE = (
    f"逐場 box 與逐打席 livelog 皆自 {DATA_FROM_YEAR} 年起有資料；"
    f"本值已走完所有可得出賽仍未中斷，實際連續局數可能更長（起算受資料邊界限制）。"
)

SUSPENDED = "保留"

# 回走中斷原因（對外原樣輸出，前端可直接對照）
BREAK_EARNED_RUN = "earned_run_allowed"
BREAK_POSTSEASON_EARNED_RUN = "postseason_earned_run_allowed"
BREAK_SUSPENDED = "suspended_game_uncertain"
BREAK_MISSING_LINE = "missing_official_line"
BREAK_DATA_BOUNDARY = "data_boundary"
BREAK_NONE = None


@dataclass(frozen=True)
class Appearance:
    """一次出賽的官方紀錄行（`cpbl.pitching_gamelog` ＋ `cpbl.games` 的場次脈絡）。

    `earned_runs` 一律是官方值；`outs` 由官方 `inning_pitched_cnt*3 + inning_pitched_div3`
    得出。本模組不修改、不重算這兩個欄位。
    """

    year: int
    kind_code: str
    game_sno: int
    game_date: date | None
    earned_runs: int | None
    outs: int | None
    delay_kind: str | None = None
    opponent: str | None = None
    team_code: str | None = None
    vht: str | None = None        # 該投手該場的主客別（'1'=客隊、'2'=主隊）

    @property
    def key(self) -> tuple[int, str, int]:
        return (self.year, self.kind_code, self.game_sno)



@dataclass(frozen=True)
class TailCredit:
    """ER>0 那場出賽的尾段採計（鴿籠下界）。"""

    key: tuple[int, str, int]
    outs: int
    suffix_from_inning: int | None = None   # 零得分後綴的起始局（該場對手打擊側）
    reason: str | None = None               # 採計為 0 時的原因


@dataclass
class StreakResult:
    outs: int = 0
    strict_outs: int = 0
    counted: list[Appearance] = field(default_factory=list)   # ER=0 整場出賽（新→舊）
    skipped: list[Appearance] = field(default_factory=list)   # 跳過的季後賽出賽（新→舊）
    tail: TailCredit | None = None
    boundary_limited: bool = False
    break_reason: str | None = BREAK_NONE
    break_key: tuple[int, str, int] | None = None

    @property
    def innings(self) -> float:
        return outs_to_innings(self.outs)

    @property
    def strict_innings(self) -> float:
        return outs_to_innings(self.strict_outs)


def outs_to_innings(outs: int) -> float:
    """出局數 → 棒球 .1/.2 局數記法（7 outs → 2.1）。"""
    return round(outs // 3 + (outs % 3) / 10, 1)


def pigeonhole_tail_outs(
    opponent_runs_by_inning: Mapping[int, int],
    official_outs: int | None,
) -> tuple[int, int | None]:
    """ER>0 那場出賽的尾段下界——**鴿籠原理，零假設**。回 `(outs, 後綴起始局)`。

    ## 為什麼換成問這個問題

    前七輪都在問「**他在這個半局拿了幾個出局**」，那需要證明 livelog 沒有隱藏列，
    而那做不到（`pitch_cnt`、`main_event_no` 主序號都不是列的唯一鍵）。

    這裡改問「**這些局有沒有人得分**」——那是 `game_scoreboard` 官方逐局比分直接給的
    事實，**與誰在投球無關**。零得分的局，不管誰投，對投球的人就是零失分。於是隱藏
    換投、規則 5.10(d) 的再入賽、牽制出局**全部不影響**：我們不需要知道他投了哪幾局。

    ## 推導

    令「零得分後綴」＝從比賽末端往回、對手連續零得分的局，`n_prefix` ＝ 最後一個
    有得分的局序（無得分則 0）。前綴只有 `n_prefix` 個半局、每個至多 3 個出局，故

        他在前綴的出局數 ≤ 3 × n_prefix
        ⇒ 他在後綴的出局數 ≥ 官方總出局數 − 3 × n_prefix

    後綴全是零得分的局 ⇒ 那些出局零失分 ⇒ 零自責分；後綴又在比賽末端 ⇒ 那些必定是他
    該場**最後**記下的出局，正好是連續紀錄需要的位置。

    此式只用兩個官方事實：`game_scoreboard` 的逐局得分、`pitching_gamelog` 的局數。
    不需要順序、不需要排除再入賽、不需要證明 livelog 完整。

    ## 隊別是式子的必要組成，不是實作細節

    `opponent_runs_by_inning` 必須是**對手打擊側**的逐局得分：目標投手在主隊（`vht='2'`）
    時看**客隊**的逐局得分（他守備時對手拿了幾分），反之亦然。取錯邊等於拿他自己隊的
    進攻得分當失分，結論全錯。

    另一種等價寫法是「後綴總出局數 − **同隊**其他投手出局數合計」——那個 `同隊` 是必要的：
    漏掉一位同隊投手會**高估**（開卡過程中需求方示範時就誤把對手投手當同隊，數字碰巧
    相同而沒露餡）。本函式改用「官方總出局數 − 3 × 前綴局數」正是為了**完全不需要那一項**，
    從源頭消除隊別配置錯誤的空間；隊別只剩「取哪一側的逐局得分」這一個決策點。

    ## 刻意保守之處

    - 用**得分 R** 而非自責分 ER 界定後綴：零得分必然零自責分，反之不然，故只會低估。
    - 前綴一律以每半局 3 個出局估上界（實際可能更少），故只會低估。
    - 投手橫跨有得分的局、或後綴太短時，下界 ≤ 0 → 採計 0（fail-closed）。
    """
    if official_outs is None:
        return 0, None
    if not opponent_runs_by_inning:
        return 0, None
    scored = [i for i, r in opponent_runs_by_inning.items() if r]
    n_prefix = max(scored) if scored else 0
    outs = official_outs - 3 * n_prefix
    if outs <= 0:
        return 0, None
    return min(outs, official_outs), n_prefix + 1


def tail_credit(
    key: tuple[int, str, int],
    opponent_runs_by_inning: Mapping[int, int],
    official_outs: int | None,
) -> TailCredit:
    """把 `pigeonhole_tail_outs` 的結果包成 `TailCredit`；證明不到就是 0。"""
    outs, suffix_from = pigeonhole_tail_outs(opponent_runs_by_inning, official_outs)
    reason = None if outs else (
        "no_scoreboard" if not opponent_runs_by_inning
        else "no_official_outs" if official_outs is None
        else "no_provable_scoreless_suffix")
    return TailCredit(key=key, outs=outs, suffix_from_inning=suffix_from, reason=reason)


def compute_streak(
    appearances: Sequence[Appearance],
    tail_lookup=None,
    counted_kinds: Sequence[str] | None = None,
    data_from_year: int = DATA_FROM_YEAR,
) -> StreakResult:
    """出賽（**舊→新**排序）→ 目前連續無自責分局數（下界）。

    `tail_lookup(appearance) -> TailCredit | None`：ER>0 那一場的尾段採計；
    給 None 或回 None 代表不採計尾段（等同「整場 ER=0 才計入」的更保守版本）。

    `counted_kinds`：計入局數的賽別（例行賽）。之外的賽別（季後賽）ER=0 跳過、
    ER>0 中斷——理由見模組 docstring「賽別範圍」。給 None 代表全部賽別都計入。

    `data_from_year`：**紅線 4 的實際執行點**。早於此年的出賽一律截斷並標示
    `boundary_limited`——`pitching_gamelog`／`game_livelog` 皆自 2018 年起才有資料，
    2017 以前的出賽即使被餵進來也不可信。這裡 enforce 而不是只在 payload 顯示年份，
    是因為「DB 目前最早就是 2018」是運氣不是保證；取數層另有 SQL 條件，兩層都擋。
    """
    res = StreakResult()
    if not appearances:
        return res
    counted_set = set(counted_kinds) if counted_kinds is not None else None

    for a in reversed(appearances):
        if a.year < data_from_year:
            res.break_reason, res.break_key = BREAK_DATA_BOUNDARY, a.key
            res.boundary_limited = True
            break
        if a.delay_kind == SUSPENDED:
            # 保留賽橫跨兩個日期，任一種排序都可能把它排在錯誤位置而導致高估 → 直接中斷。
            res.break_reason, res.break_key = BREAK_SUSPENDED, a.key
            break
        if a.earned_runs is None or a.outs is None:
            res.break_reason, res.break_key = BREAK_MISSING_LINE, a.key
            break
        if counted_set is not None and a.kind_code not in counted_set:
            # 季後賽不屬於本紀錄母體：乾淨就跳過（不計局數也不中斷），掉自責分則中斷。
            if a.earned_runs == 0:
                res.skipped.append(a)
                continue
            res.break_reason, res.break_key = BREAK_POSTSEASON_EARNED_RUN, a.key
            break
        if a.earned_runs == 0:
            res.strict_outs += a.outs
            res.counted.append(a)
            continue
        res.break_reason, res.break_key = BREAK_EARNED_RUN, a.key
        res.tail = tail_lookup(a) if tail_lookup else None
        break
    else:
        # 走完所有可得出賽都沒中斷 → 起算點被資料邊界卡住（紅線 4）。
        res.boundary_limited = True

    res.outs = res.strict_outs + (res.tail.outs if res.tail else 0)
    return res
