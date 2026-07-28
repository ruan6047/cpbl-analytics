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
   **定位**：把該場切成半局，只採計「整個半局（不分投手）零得分」且該投手獨力投完的
   尾段半局。半局零得分 ⇒ 該半局沒有任何分數可被判給任何投手 ⇒ 對本投手零自責分。
   這是純粹的觀察，不含任何自責／非自責的判定。

回走遇到任何不確定一律**中斷**（紅線 2：寧可少報一局，不可多報一局）：

| 情境 | 處理 |
|---|---|
| 官方 ER 或局數缺值 | 中斷 |
| 保留賽（`delay_kind='保留'`） | 中斷。該場橫跨 orig_date→game_date，任一種排序都可能把 ER 場排錯位置而高估；場次極少（2018+ 僅 8 場），直接中斷最乾淨 |
| ER>0 的那場沒有 livelog | 尾段 0 出局數 |
| 半局有任何得分跡象 | 停止採計（該半局及更早都不算） |
| 半局零得分但該投手沒獨力投完 | 該半局採計 0 出局數，但**繼續**往前（零得分已足以證明零自責分） |
| 半局是全場最後一個半局（可能因再見／保護傘提前結束，無法證明有三出局） | 只採計最後一列的 `out_cnt`（打席前出局數）作下界 |
| 走完所有可得出賽仍未中斷 | `boundary_limited=True`（紅線 4：`game_livelog`／`pitching_gamelog` 皆僅 2018+，不得沉默截斷） |

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

from collections.abc import Iterable, Sequence
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

    @property
    def key(self) -> tuple[int, str, int]:
        return (self.year, self.kind_code, self.game_sno)


@dataclass(frozen=True)
class HalfInning:
    """livelog 切出的一個半局（`vht` 1=上半／客隊進攻、2=下半／主隊進攻）。"""

    inning_seq: int
    vht: str
    runs: int                 # 該半局全隊得分（不分投手）
    scored_flag: bool         # 該半局有任何 is_score 事件
    pitched_whole: bool       # 目標投手獨力投完整個半局（首列 out_cnt=0 且全列同一投手）
    is_last_of_game: bool
    last_out_cnt: int | None  # 該半局最後一列的「打席前出局數」

    @property
    def run_free(self) -> bool:
        """整個半局零得分——沒有任何分數可被判給任何投手，故對本投手零自責分。"""
        return self.runs == 0 and not self.scored_flag

    @property
    def provable_outs(self) -> int:
        """可證明由該投手記下的出局數（下界）。無法證明時回 0。"""
        if not self.pitched_whole:
            return 0
        if self.is_last_of_game:
            # 全場最後一個半局可能因再見安打／保護傘／天候而未達三出局，
            # 只能採計最後一列的「打席前出局數」。
            return self.last_out_cnt if self.last_out_cnt in (0, 1, 2) else 0
        # 後面還有半局 ⇒ 本半局必以三出局結束。
        return 3 if self.last_out_cnt in (0, 1, 2) else 0


@dataclass(frozen=True)
class TailCredit:
    """ER>0 那場出賽的尾段採計（半局皆為新→舊）。

    - `credited`：**有貢獻出局數**的半局（該投手獨力投完且整個半局零得分）。對帳時要用
      最嚴格的條件驗這一組。
    - `passed`：整個半局零得分、但無法證明該投手記下幾個出局（例如他中途接手）。
      這種半局採計 **0** 出局數卻**不中斷**連續紀錄——零得分已足以證明零自責分。
      分成兩組是為了讓對帳只對「真的被宣稱的局」下嚴格條件，不混為一談。
    """

    key: tuple[int, str, int]
    outs: int
    credited: tuple[tuple[int, str], ...] = ()
    passed: tuple[tuple[int, str], ...] = ()
    clamped: bool = False   # 被該場官方出局數夾擠過（livelog 異常的防線）


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


def half_innings_of(rows: Sequence[dict], pitcher_acnt: str) -> list[HalfInning]:
    """逐球 livelog 事件 → 半局清單（時序）。`rows` 需已按 `main_event_no` 排序。

    只看事實欄位：得分（跑分欄的遞增與 `is_score`）、投手代號、`out_cnt`。
    `is_change_player` 換人公告列一律排除——實測其 `out_cnt` 為上一個半局的殘值
    （例：第 7 局上開頭的換投列帶 `out_cnt=2`），且其 `pitcher_acnt` 是**換下**的投手。
    """
    plays = [r for r in rows if not r.get("is_change_player")]
    groups: list[tuple[tuple[int, str], list[dict]]] = []
    for r in plays:
        key = (int(r["inning_seq"]), str(r["visiting_home_type"]))
        if not groups or groups[-1][0] != key:
            groups.append((key, []))
        groups[-1][1].append(r)

    out: list[HalfInning] = []
    prev_away = prev_home = 0
    for idx, ((inning_seq, vht), evs) in enumerate(groups):
        # 跑分欄以「前綴最大值」讀，換人列殘值或個別缺值都不會造成漏偵測得分。
        cur_away = max([prev_away, *[int(e["visiting_score"] or 0) for e in evs]])
        cur_home = max([prev_home, *[int(e["home_score"] or 0) for e in evs]])
        runs = (cur_away - prev_away) if vht == "1" else (cur_home - prev_home)
        prev_away, prev_home = cur_away, cur_home

        firsts = [e for e in evs if e.get("out_cnt") is not None]
        pitched_whole = (
            bool(firsts)
            and all(e.get("pitcher_acnt") == pitcher_acnt for e in evs)
            and int(firsts[0]["out_cnt"]) == 0
        )
        last_out = int(firsts[-1]["out_cnt"]) if firsts else None
        out.append(HalfInning(
            inning_seq=inning_seq,
            vht=vht,
            runs=runs,
            scored_flag=any(bool(e.get("is_score")) for e in evs),
            pitched_whole=pitched_whole,
            is_last_of_game=(idx == len(groups) - 1),
            last_out_cnt=last_out,
        ))
    return out


def tail_credit(
    key: tuple[int, str, int],
    halves: Sequence[HalfInning],
    pitcher_halves: Iterable[tuple[int, str]],
    official_outs: int | None,
) -> TailCredit:
    """ER>0 那場出賽的尾段：從該投手最後一個半局往回，採計連續的「零得分半局」。

    半局一有得分跡象即停止（該半局與更早的都不採計）——因為官方已判定本場有自責分，
    我們不去猜是哪一分，只認「整個半局零得分」這個無可爭議的事實。

    `official_outs` 為該場官方出局數，作為上限夾擠（防止 livelog 異常灌水）。
    """
    want = set(pitcher_halves)
    mine = [h for h in halves if (h.inning_seq, h.vht) in want]
    outs = 0
    credited: list[tuple[int, str]] = []
    passed: list[tuple[int, str]] = []
    for h in reversed(mine):
        if not h.run_free:
            break
        got = h.provable_outs
        outs += got
        (credited if got else passed).append((h.inning_seq, h.vht))
    clamped = official_outs is not None and outs > official_outs
    if clamped:
        outs = official_outs  # type: ignore[assignment]
    return TailCredit(key=key, outs=max(outs, 0), credited=tuple(credited),
                      passed=tuple(passed), clamped=clamped)


def compute_streak(
    appearances: Sequence[Appearance],
    tail_lookup=None,
    counted_kinds: Sequence[str] | None = None,
) -> StreakResult:
    """出賽（**舊→新**排序）→ 目前連續無自責分局數（下界）。

    `tail_lookup(appearance) -> TailCredit | None`：ER>0 那一場的尾段採計；
    給 None 或回 None 代表不採計尾段（等同「整場 ER=0 才計入」的更保守版本）。

    `counted_kinds`：計入局數的賽別（例行賽）。之外的賽別（季後賽）ER=0 跳過、
    ER>0 中斷——理由見模組 docstring「賽別範圍」。給 None 代表全部賽別都計入。
    """
    res = StreakResult()
    if not appearances:
        return res
    counted_set = set(counted_kinds) if counted_kinds is not None else None

    for a in reversed(appearances):
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
