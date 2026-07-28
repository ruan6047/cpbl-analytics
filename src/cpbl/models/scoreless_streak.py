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

1. **出賽 `earned_runs = 0`** → 該次出賽官方認定零自責分，其**全部**官方出局數計入
   （`strict_outs`）。純官方欄位，零推論；由對帳 R1 全母體逐場驗證。
2. **出賽 `earned_runs > 0`** → 連續紀錄在該次出賽內中斷。尾段用**官方逐局比分**
   （`cpbl.game_scoreboard`）取鴿籠下界：以對手逐局得分界定「零得分視窗」，採計
   `官方出局數 − 3 × 視窗外的局數`（見 `pigeonhole_tail_outs`）。零得分的局不管誰投都是
   零失分，故此下界**與誰在投球無關**；證明不到就是 0。

**尾段從不推論「他在某個半局拿了幾個出局」。** 這是七輪查核換來的結論：那種推論都需要
證明 livelog 沒有隱藏列，而 `pitch_cnt` 與 `main_event_no` 主序號**都不是列的唯一鍵**，
且不消耗投球的出局事件（牽制出局、盜壘刺、`pitch_cnt=0` 的三振／接殺）只以「列」存在
——**列的缺席偵測不到**。改問「這些局有沒有人得分」才有官方事實可答。

**唯一用到 livelog 的地方是 `last_pitch_inning()`**（ML-PITCHER-SCORELESS2 新增），而它
**只讀正向觀測、從不使用列的缺席**：累計投球數在第 i 局已達官方總數 ⇒ 其後不可能再有
投球。少了任何列，觀測最大值只會變小、達不到官方總數 ⇒ 不認證 ⇒ 退回原本的全場鴿籠
下界。**隱藏列只能讓結論變弱，不可能讓它變強**——這正是前七輪那條路走不通、而這條走得通
的分野。詳見該函式與 `pigeonhole_tail_outs` 的 docstring。

回走遇到任何不確定一律**中斷**（紅線 2：寧可少報一局，不可多報一局）：

| 情境 | 處理 |
|---|---|
| 官方 ER 或局數缺值 | 中斷 |
| 保留賽（`delay_kind='保留'`） | 中斷。該場橫跨 orig_date→game_date，任一種排序都可能把 ER 場排錯位置而高估；場次極少（2018+ 僅 8 場），直接中斷最乾淨 |
| ER>0 的那場沒有 `game_scoreboard`、或投手主客別缺值 | 尾段 0 出局數 |
| 零得分視窗太短，`官方出局數 − 3 × 視窗外局數 ≤ 0` | 尾段 0 出局數（`no_provable_scoreless_suffix`）。**這是本方法的主要成本，見下** |
| 出賽早於 `DATA_FROM_YEAR`（2018） | **截斷**並 `boundary_limited=True`（紅線 4）。取數層 SQL 也擋一次，兩層都 enforce——只在 payload 顯示年份不算執行 |
| 走完所有可得出賽仍未中斷 | `boundary_limited=True`（`pitching_gamelog` 僅 2018+，不得沉默截斷） |

## 方法邊界：尾段採計率仍然偏低，這是刻意的

2026-07-28 全母體實測（ML-PITCHER-SCORELESS2 之後）：一軍 343 個尾段查詢採得到 **29 個
（8.5%、156 outs）**、二軍 489 個中 **22 個（167 outs）**。基線（只有全場鴿籠下界）是
一軍 24 個／126 outs、二軍 19 個／152 outs。

沒有採計到的那些，成因仍是官方逐局比分**只知道某局有沒有得分，不知道那分是誰掉的**：
先發退場後、後援在後段掉分，就會把零得分視窗吃掉。`last_pitch_inning()` 認證只能把視窗
收到「他投最後一球的那一局」，**收不掉他退場之後那幾局的 3 outs／局罰則**——因為要證明
「他退場後一個出局都沒拿」就得回頭去證 livelog 完整，而那是七輪都走不通的路。

具體例子（黃子鵬 2026-07-26）：他第 1 局失分、之後投完第 6 局，真值是 5.0 局無自責分。
對手在**第 7 局對後援**又得分 ⇒ 全場式 `18 − 3×7 < 0` ⇒ 0；改用退場局式
`18 − 3×1 − 3×(9−6) = 6` ⇒ 採計 **2.0 局**。仍少報 3.0 局，**fail-closed 是正確處置**（紅線 2）。

要再往上只有兩條路，都不在本卡範圍：拿到官方的「逐局責任投手」對照
（`stats.cpbl.com.tw` 單場 API 尚未查證），或改變產品宣稱（例如改以「連續無自責分
**出賽**」為主詞，局數退為附帶總計——`strict_outs` 就是該值，由對帳 R1 逐場窮舉驗證、
零推論）。**不要為了提高採計率而放寬證據標準。**

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
    opponent_score: int | None = None   # 官方終場對手得分（games），用來驗逐局比分完整
    player_id: str | None = None        # 投手 ID；尾段要用它取該投手的官方／觀測投球數
    official_pitches: int | None = None  # 官方投球數（pitching_gamelog.pitch_cnt）

    @property
    def key(self) -> tuple[int, str, int]:
        return (self.year, self.kind_code, self.game_sno)



@dataclass(frozen=True)
class TailCredit:
    """ER>0 那場出賽的尾段採計（鴿籠下界）。"""

    key: tuple[int, str, int]
    outs: int
    suffix_from_inning: int | None = None   # 零得分視窗的起始局（該場對手打擊側）
    reason: str | None = None               # 採計為 0 時的原因
    suffix_to_inning: int | None = None     # 零得分視窗的**結束局**（含）
    last_pitch_inning: int | None = None    # 官方投球數耗盡的局（無認證則 None）


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


def last_pitch_inning(
    observed_max_pitch_by_inning: Mapping[int, int | None],
    official_pitches: int | None,
    innings_in_game: int,
) -> int | None:
    """官方投球數**耗盡**的那一局；證明不到回 `None`（fail-closed）。

    ## 這條認證在證什麼

    `cpbl.game_livelog.pitch_cnt` 是「該投手該場**累計**投球數」，`pitching_gamelog.pitch_cnt`
    是官方的同一個量。累計量隨時間單調不減，所以：**只要在第 i 局觀測到累計值已達官方
    總數，該投手在第 i 局之後就不可能再投出任何一球**——因為之後的球累計值會超過官方總數。

    ## 為什麼這不是「已排除的路徑」

    前七輪失敗的共同結構是「以某個可見量設界，再證明**資料完整**」，而列的缺席偵測不到。
    本函式**從不使用列的缺席**：它只讀「有沒有觀測到某一列」這個**正向**事實。
    livelog 少了任何列，觀測到的累計最大值只會**變小**、達不到官方總數，於是回 `None`
    ＝不認證＝退回原本的全場鴿籠下界。**隱藏列只能讓結論變弱，不可能讓它變強**，
    這正是卡面要求的「不管資料完不完整，這個界都成立」。

    注意 `pitch_cnt` **不是列的唯一鍵**（全庫 68,372 組重複）——那正是 iteration 4 被推翻的
    原因。本函式不受影響：它不數列、不要求序號閉合、也不要求每個序號只出現一次，
    只取**每局的最大值**再問「哪一局起累計值已達官方總數」。重複列不改變最大值。

    ## 為什麼取「最早達成的局」而不是「出現該值的最後一局」

    換投列（`is_change_player`）會帶著被換下投手的最終累計投球數出現在**下一局**
    （實例 `2026/A/223` 黃子鵬第 7 局的換人列仍帶 `pitch_cnt=91`）。取最後一局會把退場
    局往後推、白白放棄採計。取**最早**達成的局在邏輯上同樣成立：該局內已存在一列顯示
    累計值等於官方總數，故其後不可能再有投球。本函式因此完全不需要判讀 `is_change_player`
    這個旗標——少一個要相信的欄位。

    ## fail-closed 條件（任一成立即回 `None`）

    | 條件 | 為什麼 |
    |---|---|
    | 官方投球數缺值或 ≤ 0 | 沒有可耗盡的總數 |
    | 沒有任何觀測 | 無正向事實 |
    | 任一局的觀測值為 `None` | **未知不得折成已知**（見 `pigeonhole_tail_outs`） |
    | 觀測局序超出 `1..innings_in_game` | 與官方逐局比分矛盾，整場不可信 |
    | 觀測到的最大值 **>** 官方總數 | 兩個官方量互相矛盾，不可用來設界 |
    | 累計值從未達到官方總數 | 觀測不足以證明耗盡（多半是 livelog 缺列——正是要 fail-closed 的情形） |
    """
    if official_pitches is None or official_pitches <= 0:
        return None
    if not observed_max_pitch_by_inning:
        return None
    if any(v is None for v in observed_max_pitch_by_inning.values()):
        return None
    if any(i < 1 or i > innings_in_game for i in observed_max_pitch_by_inning):
        return None
    if max(observed_max_pitch_by_inning.values()) > official_pitches:  # type: ignore[type-var]
        return None
    running = 0
    for inning in sorted(observed_max_pitch_by_inning):
        running = max(running, observed_max_pitch_by_inning[inning])  # type: ignore[type-var]
        if running == official_pitches:
            return inning
    return None


def pigeonhole_tail_outs(
    opponent_runs_by_inning: Mapping[int, int | None],
    official_outs: int | None,
    opponent_final_score: int | None,
    last_pitch: int | None = None,
) -> tuple[int, int | None, int | None]:
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

    ## 輸入前提必須驗證：逐局比分要完整

    公式的正確性建立在「`opponent_runs_by_inning` 是完整的逐局比分」之上。**缺一個有
    得分的局就會高估**——例如 `{1:0, 3:0}` 與 21 outs 會算出後綴自第 1 局；若缺掉的第 2 局
    其實有分，真正的下界是更小的值。`game_scoreboard` 是逐列 UPSERT、沒有完整性
    constraint，所以這不是純理論。

    因此本函式要求 `opponent_final_score`（`games` 的官方終場對手得分），並驗
    **逐局得分總和 ＝ 官方終場得分**；不等、或任一為 NULL，一律回 `(0, None)`。
    這是**官方對官方**的交叉檢查，不引入任何新假設。

    **任一局的得分為 `None`（DB 的 NULL）即 fail-closed。** `None` 的意思是「這一局得
    幾分不知道」，不是「這一局 0 分」——把未知折成 0 會讓官方終場得分為 0 的比賽以
    `0 == 0` 通過總和對帳，缺值的局被當成零得分而採計。**未知必須有自己的名字，不能被
    靜默折疊進某個已知值。**

    ## 刻意保守之處

    - 用**得分 R** 而非自責分 ER 界定後綴：零得分必然零自責分，反之不然，故只會低估。
    - 前綴一律以每半局 3 個出局估上界（實際可能更少），故只會低估。
    - 投手橫跨有得分的局、或後綴太短時，下界 ≤ 0 → 採計 0（fail-closed）。

    ## 第二個下界：以「他最後一球投在第幾局」把視窗提早收掉（ML-PITCHER-SCORELESS2）

    上式把視窗一路開到**比賽末端**，所以只要投手退場後對手還有得分，`n_prefix` 就被推到
    很後面而下界歸零——一軍 343 次尾段查詢有 319 次卡在這裡（黃子鵬 2026-07-26 的 5.0 局
    真值被算成 0 就是這樣來的）。

    給定 `last_pitch`（＝官方投球數耗盡的局，見 `last_pitch_inning()`），可以另外導出一條
    **獨立的**下界。令 `S` ＝ 對手打擊的總局數、`m` ＝ **不晚於 `last_pitch`** 的最後一個
    得分局（沒有則 0）：

        他在第 1..m 局的出局數            ≤ 3 × m                  （每半局至多 3 個出局）
        他在第 last_pitch+1..S 局的出局數 ≤ 3 × (S − last_pitch)   （同上）
        ⇒ 他在第 m+1..last_pitch 局的出局數 ≥ 官方總出局數 − 3m − 3(S − last_pitch)

    第 `m+1..last_pitch` 局依 `m` 的定義**全部零得分**，所以這些出局零失分、零自責分。

    ### 為什麼這些出局在「他最後一次自責失分之後」

    自責分只會記在**他讓跑者上壘的那一局**（跑者不跨局）。而讓跑者上壘一定要投球——
    安打／四壞／觸身／被打出去的失誤／不死三振／捕手妨礙**都需要一顆球**。唯一不需要
    投球就出現的跑者是延長賽的指定跑者，而規則 **7.01(b)(2)(C)** 明文「為符合規則 9.16
    自責分的計算，每半局開始位於二壘的跑壘員，**視為守備失誤上壘**」＝**非自責**，不會
    記到任何投手的自責分上。

    所以：他的自責分只可能發生在第 `1..last_pitch` 局；而第 `m+1..last_pitch` 局零得分，
    故他最後一次自責失分必在第 `m` 局或更早——採計的出局全都在那之後。∎

    ### 兩條下界都成立，取大的那條

    `last_pitch = S`（沒有認證）時第二式退化成第一式，故本函式回傳兩者的最大值，
    **永遠不低於原本的鴿籠下界**（原有輸出不會因為本次擴充而變小）。

    ### 刻意不做的收緊

    第 `last_pitch+1..S` 局其實不太可能有他的出局（他沒再投球，只剩牽制／促請裁決這類
    不消耗投球的出局），規則 5.10(g) 的【加註】也把後援投手綁在「投球至第 1 位擊球員
    出局或上壘，或結束該局」。照這條可以把每局罰則從 3 收到 1，數字會好看很多。
    **本函式不這樣做**：那需要一串以規則為前提的推論，而 iteration 6 正是栽在自創規則上。
    每半局至多 3 個出局是**原本這條式子就已經在用**的同一個前提，不引進新的。
    """
    if official_outs is None or opponent_final_score is None:
        return 0, None, None
    if not opponent_runs_by_inning:
        return 0, None, None
    # 缺值（DB NULL）＝這一局得幾分不知道，不是 0 分 → fail-closed。
    if any(r is None for r in opponent_runs_by_inning.values()):
        return 0, None, None
    # 逐局比分完整性：官方對官方。總和對不上代表 scoreboard 缺列，缺的若是得分局就會高估。
    if sum(opponent_runs_by_inning.values()) != opponent_final_score:  # type: ignore[arg-type]
        return 0, None, None
    scored = [i for i, r in opponent_runs_by_inning.items() if r]
    innings = max(opponent_runs_by_inning)
    # `else 0` 在此**不是**把未知折成已知：能走到這行代表完整性已通過（無 None、
    # 逐局總和 ＝ 官方終場得分），所以「沒有任何得分局」是**已證實的事實**，
    # 前綴長度確實是 0（整場零得分 → 後綴涵蓋全場）。
    n_prefix = max(scored) if scored else 0
    outs = official_outs - 3 * n_prefix
    window = (n_prefix + 1, innings)
    if last_pitch is not None and 1 <= last_pitch <= innings:
        before = [i for i in scored if i <= last_pitch]
        m = max(before) if before else 0
        candidate = official_outs - 3 * m - 3 * (innings - last_pitch)
        if candidate > outs:
            outs, window = candidate, (m + 1, last_pitch)
    if outs <= 0:
        return 0, None, None
    return min(outs, official_outs), window[0], window[1]


def tail_credit(
    key: tuple[int, str, int],
    opponent_runs_by_inning: Mapping[int, int | None],
    official_outs: int | None,
    opponent_final_score: int | None,
    last_pitch: int | None = None,
) -> TailCredit:
    """把 `pigeonhole_tail_outs` 的結果包成 `TailCredit`；證明不到就是 0。"""
    outs, suffix_from, suffix_to = pigeonhole_tail_outs(
        opponent_runs_by_inning, official_outs, opponent_final_score, last_pitch)
    reason = None if outs else (
        "no_scoreboard" if not opponent_runs_by_inning
        else "no_official_outs" if official_outs is None
        else "no_official_final_score" if opponent_final_score is None
        else "scoreboard_has_null_inning"
        if any(r is None for r in opponent_runs_by_inning.values())
        else "scoreboard_incomplete"
        if sum(opponent_runs_by_inning.values()) != opponent_final_score  # type: ignore[arg-type]
        else "no_provable_scoreless_suffix")
    return TailCredit(key=key, outs=outs, suffix_from_inning=suffix_from, reason=reason,
                      suffix_to_inning=suffix_to, last_pitch_inning=last_pitch)


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
