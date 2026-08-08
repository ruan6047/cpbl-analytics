"""投手「連續無**自責**分出賽」／「連續無**失**分出賽」——定位而非重建。

主值是只採官方判準值為 0 的整場出賽，因而零推論。局數仍保留為輔助下界，尾段會用
鴿籠原理；改變主標不是解決尾段的粒度限制。

本模組支援**兩個口徑**（`Basis`），演算法完全共用，差別只在「回走時看哪一個官方欄位」：

| 口徑 | 判準欄位 | 對外指標 |
|---|---|---|
| `EARNED_RUN_BASIS`（預設，既有） | `pitching_gamelog.earned_runs` | 連續無**自責**分出賽 |
| `RUN_BASIS`（ML-PITCHER-RUNLESS1 新增） | `pitching_gamelog.runs` | 連續無**失**分出賽 |

**兩個口徑都不重算官方欄位。** 自責分那條線受規則 9.16 的**主觀條款**支配——9.16(c)(d)
要求反事實重播（「若無失誤是否仍能得分」）、9.16(f) 明文「判斷有疑慮時應對投手有利」
——那是記錄員的判斷，不是可自動化的推導（`ML-PITCHER-ER-REBUILD1` 量到逐場落差中
17.82pp 來自這三條，見該卡交付；本模組不依賴那份結果，只引為佐證）。

**失分那條線並非完全不受 9.16 規範**：9.16(g) 本文即為失分歸屬的規範性條款——
「在同一局中更換投手，在後援投手上場後壘上原有之跑壘員得分⋯⋯該失分（**無論自責分或
非自責分**）皆不為後援投手之責任」（`docs/reference/棒球規則.txt` L6208-6211）。
本模組**直接讀官方 `runs` 欄**，該歸屬已由聯盟記錄員套用完畢，我方一次判斷都不用做。
真正繞開的是 9.16 的**主觀條款**（(c)(d) 的反事實重播與 (f) 的對投手有利），失分口徑
完全不碰。搜尋本檔不會找到任何失誤／捕逸／出局機會／繼承跑者的判定。

## 名詞（紅線 5）

**兩個指標不可互相冒名**。2026 一軍 2018+ 母體中「失分 ≠ 自責分」的出賽數以對帳腳本
輸出為準（`scripts/reconcile_scoreless_streak.py` 的 X1），差額全部來自非自責失分：
自責分口徑**不**中斷、失分口徑**會**中斷。每個口徑的對外文案由自己的 `Basis.metric_note`
提供，那是該說明的單一來源；`METRIC_NOTE` 是自責分口徑的向後相容別名。

## 演算法：只做兩件事（兩口徑共用）

以投手的出賽（appearance）由新到舊回走，令 `charged` ＝ 該口徑的官方判準欄位：

1. **出賽 `charged = 0`** → 該次出賽官方認定零（自責）失分，其**全部**官方出局數計入
   （`strict_outs`）。純官方欄位，零推論；由對帳 R1 全母體逐場驗證。
2. **出賽 `charged > 0`** → 連續紀錄在該次出賽內中斷。尾段改用**官方逐局比分**
   （`cpbl.game_scoreboard`）取鴿籠下界：以對手逐局得分界定「零得分後綴」，採計
   `官方出局數 − 3 × 前綴局數`（見 `pigeonhole_tail_outs`）。零得分的局不管誰投都是
   零失分，故此下界**與誰在投球無關**；證明不到就是 0。

## 為什麼失分口徑「兩段一致」，而自責分口徑不是

尾段判準（官方逐局零得分）本來就是**失分**口徑的證據。接在哪一段中段上，性質不同：

| 口徑 | 中段證明的命題 | 尾段證明的命題 | 關係 |
|---|---|---|---|
| 自責分 | 該出賽官方 ER=0 | 該局零**得分** | 尾段命題**蘊含**中段所需（零得分 ⇒ 零自責分），但兩段的證據標準不同層 |
| 失分 | 該出賽官方 R=0 | 該局零**得分** | **同一個量**，只是粒度不同（出賽 vs 局） |

**這不是說自責分口徑會高估**——尾段的證明較強，混用的結果仍是自責分口徑的合法下界。
差別在**證據標準是否齊一**：自責分口徑的尾段被要求證到「連非自責分都沒有」，比它自己
的中段嚴格一層，於是「這條紀錄是用什麼證出來的」必須分兩段講；失分口徑下兩段講的是
同一個量，敘述與對帳都少一層轉換。

**口徑一致化不會提高尾段採計率**，也不宣稱如此：尾段採計率低的成因是鴿籠法要求零得分
後綴一路開到比賽末端（先發退場後後援掉分就整段吃掉），兩個口徑受同一個限制。實際的
採計場次與出局數由對帳腳本逐口徑輸出。

**尾段完全不讀逐打席資料（`game_livelog`）。** 這是七輪查核換來的結論：任何「他在這個
半局拿了幾個出局」的推論都需要證明 livelog 沒有隱藏列，而 `pitch_cnt` 與
`main_event_no` 主序號**都不是列的唯一鍵**，且不消耗投球的出局事件（牽制出局、盜壘刺、
`pitch_cnt=0` 的三振／接殺）只以「列」存在——**列的缺席偵測不到**。改問「這些局有沒有
人得分」才有官方事實可答。

回走遇到任何不確定一律**中斷**（紅線 2：寧可少報一局，不可多報一局）：

| 情境 | 處理 |
|---|---|
| 官方判準值（ER 或 R）或局數缺值 | 中斷 |
| 保留賽（`delay_kind='保留'`） | 中斷。該場橫跨 orig_date→game_date，任一種排序都可能把掉分的場排錯位置而高估；場次極少（2018+ 僅 8 場），直接中斷最乾淨 |
| 判準值>0 的那場沒有 `game_scoreboard`、或投手主客別缺值 | 尾段 0 出局數 |
| 零得分後綴太短，`官方出局數 − 3 × 前綴局數 ≤ 0` | 尾段 0 出局數（`no_provable_scoreless_suffix`）。**這是本方法的主要成本，見下** |
| 出賽早於 `DATA_FROM_YEAR`（2018） | **截斷**並 `boundary_limited=True`（紅線 4）。取數層 SQL 也擋一次，兩層都 enforce——只在 payload 顯示年份不算執行 |
| 走完所有可得出賽仍未中斷 | `boundary_limited=True`（`pitching_gamelog` 僅 2018+，不得沉默截斷） |

## 方法邊界：尾段採計率低是本質代價，不是缺陷——**且換口徑不會消除它**

**多數中斷場採計不到尾段**——2026-07-28 全母體實測（自責分口徑），一軍 343 個尾段查詢
只有 **24 個（7%）** 採得到，二軍 489 個中 19 個。原因是官方逐局比分**只知道某局有沒有
得分，不知道那分是誰掉的**：先發退場後、後援在後段掉分，就會把零得分後綴整個吃掉。
失分口徑的對應數字由對帳腳本輸出（本檔不重述），**但成因與限制完全相同**。

具體例子（黃子鵬 2026-07-26）：他第 1 局失分、之後投完第 6 局，真值是 5.0 局無自責分；
但對手在**第 7 局對後援**又得分 ⇒ 最後得分局＝7 ⇒ `18 − 3×7 < 0` ⇒ 尾段採計 **0**。
官方逐局比分無從區分第 7 局那分不是他的責任，**fail-closed 是正確處置**（紅線 2）。

**「中途登板／中途退場且該局有得分時只能給下界」這個限制不因改用失分口徑而消失。**
它的成因是官方逐場只記整場的量、不記事件時點，與判準用 ER 還是 R 無關；失分口徑改善的
是**證據標準的齊一性**與**名詞對得上媒體**，不是鴿籠推論本身。

要改善只有兩條路，都不在本卡範圍：拿到官方的「逐局責任投手」對照，或改變產品宣稱
（例如改以「連續無自責分／無失分**出賽**」為主詞，局數退為附帶總計——`strict_outs`
就是該值，由對帳 R1 逐場窮舉驗證、零推論）。**不要為了提高採計率而放寬證據標準。**

### 零得分後綴的右端**必須是比賽末端**（ML-PITCHER-SCORELESS2 的結論）

看起來很誘人的一招是「把視窗收到他投最後一球的那一局」——退場後那幾局的得分不算他的
——採計率立刻上升。**這條在 ML-PITCHER-SCORELESS2 被規則反例推翻並撤回**：它的前提是
「讓跑者上壘一定要投球」，而規則允許**零投球**的自責分——

- 總教練**手勢**故意四壞（用語定義 BASE ON BALLS／5.05(b)(1)、9.14(d)）＝ 不投球即送保送；
- **投手犯規**（6.02(a) 罰則／5.06(c)(3)）＝ 不投球即推進所有跑者，三壘跑者得分；
- 9.16 明文「無論任何情況，故意四壞球皆認定為四壞球」，9.16(a)【註 2】① 把故意四壞與
  投手犯規都列為**自責分因素**。

也就是說：投球數耗盡**證不出**「其後不會再產生他的自責分」。且該做法的增益區**包含於**
反例適用區（有嚴格增益 ⇒ `last_pitch` 之後有得分局；反之不成立，兩區並不相等）——
排除掉不安全的情形之後剩下的增益為零，**沒有部分可救的中間地帶**——
證明見 `tests/test_scoreless_streak.py` 的窮舉測試與
`docs/research/ML-PITCHER-SCORELESS2_RESULTS.md`。同理，鏡像做法（以「第一球投在第幾局」
砍掉前綴容量）也不成立：規則 5.10(g)【加註】允許後援投手以**牽制出局**結束該局後被替換，
＝ 零投球也能拿到出局數。**投球數是投球的證據，不是出局數或自責分的證據。**

## 賽別範圍：只算例行賽，季後賽「乾淨跳過、掉分中斷」

需求方裁定（2026-07-28）：本紀錄**只計例行賽局數**（一軍 A／二軍 D），不沿用
`KIND_GROUPS` 把季後賽併入同層。理由是 MLB／NPB 慣例即連續紀錄只算例行賽，使用者
手邊的媒體數字也是這個口徑，混入季後賽會被當成算錯。

跨季時中間的季後賽出賽（一軍 E／C、二軍 F）依 `counted_kinds` 之外的規則處理：

| 季後賽出賽 | 處理 | 為什麼 |
|---|---|---|
| 官方判準值（該口徑的 ER 或 R）＝ 0 | **跳過**：局數不計入，也不中斷 | 它不屬於本紀錄的母體，沒有中斷它的理由 |
| 官方判準值 > 0 | **中斷**（`Basis.postseason_break_reason`） | 見下 |

**為什麼掉分要中斷、而不是一律跳過**（此為執行者裁定，理由留痕）：

1. **紅線 2 的方向**。這條規則下的值同時是「只算例行賽（季後賽全跳過）」與「一軍所有
   比賽都算」**兩種讀法的下界**——任一讀法下都不會高估。一律跳過則只在前一種讀法下
   成立，遇到第二種讀法就是高估。
2. **可理解性**。一律跳過會產生「這條連續紀錄橫跨一場他被打爆的台灣大賽」的輸出，
   讀者無法接受，而本專案的產品價值在透明與教育。
3. **不變式好講也好驗**。此規則下「起算場之後、該投手在**任何**一軍賽別的出賽都沒有
   （自責）失分」恆為真，是可窮舉驗證的強陳述（對帳 R7）。

被跳過的出賽以 `StreakResult.skipped` 留存，並經 API 對外揭露（`skipped_postseason_*`），
讓讀者知道紀錄中間發生過什麼——不做沉默跳過。

## 主值與輔助值（兩種對帳基礎）

- `appearances_counted`：只計**官方判準值＝0 的整場出賽**。這是零推論的主值；每一場的
  官方欄位（`earned_runs` 或 `runs`）必為 0 ——即卡面紅線 3 的**字面**對帳基礎。
- `strict_outs`：上述零推論出賽的官方出局數合計，供需要局數的消費者稽核。
- `outs`：`strict_outs` ＋ 中斷那場的尾段半局。尾段的每一個半局另以**半局層級**的證明
  滿足紅線 3 的**意圖**：「整個半局、不分投手、零得分」⇒ 沒有任何分數存在可被判給
  任何人 ⇒ 對本投手零失分、從而零自責分。在**失分**口徑下這與中段是同一個量的兩個
  粒度；在**自責分**口徑下它比「該場 ER=0」更緊（連非自責分都沒有），並同時繞開
  自責／非自責分野與 9.16(g) 繼承跑者歸屬。

兩者各有獨立的窮舉對帳（`scripts/reconcile_scoreless_streak.py` 的 R1／R2），皆零例外。

## 兩口徑的大小關係（可證且逐人驗證）

`runs = 0 ⇒ earned_runs = 0`（自責分是失分的子集），故失分口徑的採計視窗必為自責分
口徑視窗的**後綴**，且中斷場落在自責分視窗之內 ⇒ **失分口徑的總出局數恆 ≤ 自責分口徑**。
唯一能翻轉這個關係的資料形態是「`runs` 非 NULL 而 `earned_runs` 為 NULL」（那會讓自責分
口徑先中斷）；該形態的母體筆數由對帳腳本的 X2 逐次輸出，**不靠假設它是 0**。
逐人比對由對帳腳本 X3 對全母體執行。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

DATA_FROM_YEAR = 2018
BOUNDARY_NOTE = (
    f"逐場 box 與逐打席 livelog 皆自 {DATA_FROM_YEAR} 年起有資料；"
    f"本值已走完所有可得出賽仍未中斷，實際連續局數可能更長（起算受資料邊界限制）。"
)

SUSPENDED = "保留"

# 回走中斷原因（對外原樣輸出，前端可直接對照）
BREAK_EARNED_RUN = "earned_run_allowed"
BREAK_POSTSEASON_EARNED_RUN = "postseason_earned_run_allowed"
BREAK_RUN = "run_allowed"
BREAK_POSTSEASON_RUN = "postseason_run_allowed"
BREAK_SUSPENDED = "suspended_game_uncertain"
BREAK_MISSING_LINE = "missing_official_line"
BREAK_DATA_BOUNDARY = "data_boundary"
BREAK_NONE = None

# 判準欄位名（＝ `Appearance` 上的屬性名，也是 `pitching_gamelog` 的欄位名）
FIELD_EARNED_RUNS = "earned_runs"
FIELD_RUNS = "runs"


@dataclass(frozen=True)
class Appearance:
    """一次出賽的官方紀錄行（`cpbl.pitching_gamelog` ＋ `cpbl.games` 的場次脈絡）。

    `earned_runs`／`runs` 一律是官方值；`outs` 由官方
    `inning_pitched_cnt*3 + inning_pitched_div3` 得出。本模組不修改、不重算這些欄位。

    `runs` 預設 `None` 是為了讓既有（自責分口徑）的呼叫端與測試不必改；但**失分口徑下
    `None` 代表「不知道」，會直接觸發 `BREAK_MISSING_LINE`**，不會被當成 0。
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
    runs: int | None = None       # 官方失分（pitching_gamelog.runs），失分口徑的判準值

    @property
    def key(self) -> tuple[int, str, int]:
        return (self.year, self.kind_code, self.game_sno)


@dataclass(frozen=True)
class Basis:
    """一個口徑：判準欄位 ＋ 對外名詞 ＋ 中斷原因碼。**口徑語意的單一來源。**

    `field` 同時是 `Appearance` 的屬性名與 `pitching_gamelog` 的欄位名，取值一律走
    `charged()`；不要在別處另寫 `a.earned_runs if ... else a.runs` 之類的分岔。
    """

    field: str
    metric: str
    metric_label: str
    metric_note: str
    strict_basis: str
    break_reason: str
    postseason_break_reason: str

    def charged(self, a: Appearance) -> int | None:
        """該次出賽官方判給這位投手的分數（本口徑的判準值）。`None` ＝ 未知，不是 0。"""
        return a.earned_runs if self.field == FIELD_EARNED_RUNS else a.runs


EARNED_RUN_BASIS = Basis(
    field=FIELD_EARNED_RUNS,
    metric="consecutive_earned_run_free_appearances",
    metric_label="連續無自責分出賽",
    metric_note=(
        "本指標為「連續無**自責**分出賽」，非「連續無失分出賽」："
        "失誤造成的非自責失分不中斷本指標（與 ERA 語意一致）。"
        "自責分一律採官方紀錄（pitching_gamelog.earned_runs），本專案不重算。"
        "主值只計官方 earned_runs=0 的整場出賽，**零推論**。"
        "局數輔助欄位仍含鴿籠下界；這是改變主標，不是消除中途登板／退場的粒度限制。"
    ),
    strict_basis="官方 earned_runs=0 的整場出賽",
    break_reason=BREAK_EARNED_RUN,
    postseason_break_reason=BREAK_POSTSEASON_EARNED_RUN,
)

RUN_BASIS = Basis(
    field=FIELD_RUNS,
    metric="consecutive_run_free_appearances",
    metric_label="連續無失分出賽",
    metric_note=(
        "本指標為「連續無**失**分出賽」，非「連續無自責分出賽」："
        "失誤造成的非自責失分**會**中斷本指標（與媒體慣用的「無失分」一致）。"
        "失分一律採官方紀錄（pitching_gamelog.runs）；9.16(g) 的繼承跑者歸屬已由聯盟"
        "記錄員套用於該欄，本專案直接讀取、不重算，也不觸及 9.16(c)(d)(f) 的主觀判斷。"
        "主值只計官方 runs=0 的整場出賽，**零推論**。"
        "局數輔助欄位仍含鴿籠下界；這是改變主標，不是消除中途登板／退場的粒度限制。"
    ),
    strict_basis="官方 runs=0 的整場出賽",
    break_reason=BREAK_RUN,
    postseason_break_reason=BREAK_POSTSEASON_RUN,
)

BASES = {EARNED_RUN_BASIS.field: EARNED_RUN_BASIS, RUN_BASIS.field: RUN_BASIS}

# 向後相容別名：既有呼叫端／測試沿用自責分口徑的模組層常數。
METRIC = EARNED_RUN_BASIS.metric
METRIC_LABEL = EARNED_RUN_BASIS.metric_label
METRIC_NOTE = EARNED_RUN_BASIS.metric_note



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
    opponent_runs_by_inning: Mapping[int, int | None],
    official_outs: int | None,
    opponent_final_score: int | None,
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
    """
    if official_outs is None or opponent_final_score is None:
        return 0, None
    if not opponent_runs_by_inning:
        return 0, None
    # 缺值（DB NULL）＝這一局得幾分不知道，不是 0 分 → fail-closed。
    if any(r is None for r in opponent_runs_by_inning.values()):
        return 0, None
    # 逐局比分完整性：官方對官方。總和對不上代表 scoreboard 缺列，缺的若是得分局就會高估。
    if sum(opponent_runs_by_inning.values()) != opponent_final_score:  # type: ignore[arg-type]
        return 0, None
    scored = [i for i, r in opponent_runs_by_inning.items() if r]
    # `else 0` 在此**不是**把未知折成已知：能走到這行代表完整性已通過（無 None、
    # 逐局總和 ＝ 官方終場得分），所以「沒有任何得分局」是**已證實的事實**，
    # 前綴長度確實是 0（整場零得分 → 後綴涵蓋全場）。
    n_prefix = max(scored) if scored else 0
    outs = official_outs - 3 * n_prefix
    if outs <= 0:
        return 0, None
    return min(outs, official_outs), n_prefix + 1


def tail_credit(
    key: tuple[int, str, int],
    opponent_runs_by_inning: Mapping[int, int | None],
    official_outs: int | None,
    opponent_final_score: int | None,
) -> TailCredit:
    """把 `pigeonhole_tail_outs` 的結果包成 `TailCredit`；證明不到就是 0。"""
    outs, suffix_from = pigeonhole_tail_outs(
        opponent_runs_by_inning, official_outs, opponent_final_score)
    reason = None if outs else (
        "no_scoreboard" if not opponent_runs_by_inning
        else "no_official_outs" if official_outs is None
        else "no_official_final_score" if opponent_final_score is None
        else "scoreboard_has_null_inning"
        if any(r is None for r in opponent_runs_by_inning.values())
        else "scoreboard_incomplete"
        if sum(opponent_runs_by_inning.values()) != opponent_final_score  # type: ignore[arg-type]
        else "no_provable_scoreless_suffix")
    return TailCredit(key=key, outs=outs, suffix_from_inning=suffix_from, reason=reason)


def compute_streak(
    appearances: Sequence[Appearance],
    tail_lookup=None,
    counted_kinds: Sequence[str] | None = None,
    data_from_year: int = DATA_FROM_YEAR,
    basis: Basis = EARNED_RUN_BASIS,
) -> StreakResult:
    """出賽（**舊→新**排序）→ 目前連續無（自責）失分局數（下界）。

    `basis`：判準口徑。`EARNED_RUN_BASIS`（預設，向後相容）看官方 `earned_runs`；
    `RUN_BASIS` 看官方 `runs`。**演算法一字不改**，只換讀哪個官方欄位與對外原因碼——
    這正是「兩個口徑是同一套定位法的兩個判準」這句話的可執行形式。

    `tail_lookup(appearance) -> TailCredit | None`：判準值>0 那一場的尾段採計；
    給 None 或回 None 代表不採計尾段（等同「整場判準值=0 才計入」的更保守版本）。

    `counted_kinds`：計入局數的賽別（例行賽）。之外的賽別（季後賽）判準值=0 跳過、
    >0 中斷——理由見模組 docstring「賽別範圍」。給 None 代表全部賽別都計入。

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
        charged = basis.charged(a)
        # 判準值缺值（DB NULL）＝「這場掉幾分不知道」，不是 0 → 中斷。失分口徑下
        # `Appearance.runs` 的預設值也是 None，所以忘了餵 runs 會 fail-closed 中斷，
        # 不會被靜默當成「零失分」而高估。
        if charged is None or a.outs is None:
            res.break_reason, res.break_key = BREAK_MISSING_LINE, a.key
            break
        if counted_set is not None and a.kind_code not in counted_set:
            # 季後賽不屬於本紀錄母體：乾淨就跳過（不計局數也不中斷），掉分則中斷。
            if charged == 0:
                res.skipped.append(a)
                continue
            res.break_reason, res.break_key = basis.postseason_break_reason, a.key
            break
        if charged == 0:
            res.strict_outs += a.outs
            res.counted.append(a)
            continue
        res.break_reason, res.break_key = basis.break_reason, a.key
        res.tail = tail_lookup(a) if tail_lookup else None
        break
    else:
        # 走完所有可得出賽都沒中斷 → 起算點被資料邊界卡住（紅線 4）。
        res.boundary_limited = True

    res.outs = res.strict_outs + (res.tail.outs if res.tail else 0)
    return res
