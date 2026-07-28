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
| **該場 livelog 覆蓋不完整**（半局缺漏／重複、與 `game_scoreboard` 不一致、投手局序不連續、觀測出局數少於官方局數） | 尾段 0 出局數。**這是紅線 2 最關鍵的一道閘門**——缺漏的半局會被「跨過」而非被看見，導致更早的乾淨半局被誤採計。見 `coverage_reason` |
| 半局有任何得分跡象（livelog **或** `game_scoreboard`） | 停止採計（該半局及更早都不算） |
| 半局零得分但該投手沒獨力投完 | 該半局採計 0 出局數，但**繼續**往前（零得分已足以證明零自責分） |
| 半局是全場最後一個半局（可能因再見／保護傘提前結束，無法證明有三出局） | 只採計最後一列的 `out_cnt`（打席前出局數）作下界 |
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
    has_pitcher: bool = False  # 目標投手在本半局有出現
    pitcher_outs: int = 0      # 觀測到的出局數，取**寬鬆上界**；只供覆蓋完整性比對。
                               # 與 provable_outs 方向相反：後者是可採計的**下界**。

    @property
    def key(self) -> tuple[int, str]:
        return (self.inning_seq, self.vht)

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
        # 後面還有半局 ⇒ 本半局必以三出局結束，但**必須看得到他投到第三個出局的那個
        # 打席**（最後一列 out_cnt == 2）。少了這個條件，「現存列只有他一位投手」會把
        # 「他 1 出局後換投、而換投後的事件整段缺漏」誤判成他投完整局——現存列一致
        # 證明不了列是齊全的。
        return 3 if self.last_out_cnt == 2 else 0


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
    coverage_reason: str | None = None   # 非 None 代表覆蓋不完整、尾段一律 0（見 coverage_reason()）


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
        is_last = idx == len(groups) - 1
        out.append(HalfInning(
            inning_seq=inning_seq,
            vht=vht,
            runs=runs,
            scored_flag=any(bool(e.get("is_score")) for e in evs),
            pitched_whole=pitched_whole,
            is_last_of_game=is_last,
            last_out_cnt=last_out,
            has_pitcher=any(e.get("pitcher_acnt") == pitcher_acnt for e in evs),
            pitcher_outs=_observed_outs(evs, pitcher_acnt),
        ))
    return out


def _observed_outs(evs: Sequence[dict], pitcher_acnt: str) -> int:
    """該投手在這個半局**觀測到**記下的出局數（`out_cnt` 差值），取**寬鬆上界**。

    用途只有一個：與官方局數比對，證明 livelog 沒有漏掉他投的內容（`coverage_reason`
    的 `pitcher_outs_below_official`）。**不是**採計值——採計走的是更嚴格的
    `HalfInning.provable_outs`。

    **方向必須是寬鬆的**：這個估計值偏低會讓覆蓋檢查誤報（例如再見安打結束的半局，
    保守估計只給 2 而官方記 3，就會把正常的場次判成缺漏）。他若是該半局最後一位投手，
    一律以 3 作結束基準；估高不會多採計任何一局，估低卻會殺掉正常尾段。
    """
    idxs = [i for i, e in enumerate(evs) if e.get("pitcher_acnt") == pitcher_acnt]
    if not idxs:
        return 0
    mine = [evs[i] for i in idxs if evs[i].get("out_cnt") is not None]
    if not mine:
        return 0
    start = int(mine[0]["out_cnt"])
    after = [e for e in evs[idxs[-1] + 1:] if e.get("out_cnt") is not None]
    end = int(after[0]["out_cnt"]) if after else 3
    return max(0, min(3, end - start))


@dataclass(frozen=True)
class GameEvidence:
    """尾段採計所需的**場級外部證據**，全部來自 livelog 以外的來源。

    這個型別存在的理由：前兩輪查核連續抓到「再檢查一個看得見的量」的修法——
    R2 驗選中的半局乾淨、覆蓋閘門驗半局存在、`pitched_whole` 驗現存列一致，
    每一層都只用 livelog 自己說的話，於是下一層的缺漏又露出來。要跳出這個循環，
    證據必須來自 livelog **之外**：

    - `scoreboard`：逐局記分板（官網 box 的另一段 payload）
    - `official_outs`：**全場每位投手**的官方出局數（`pitching_gamelog`）

    官方 box 是關鍵——它知道有哪些投手、各記了幾個出局。livelog 若漏掉某位後援投手的
    事件，他的出局數就會沒有可見的位置可以安放，對帳立刻不平。
    """

    scoreboard: Mapping[tuple[int, str], int] | None = None
    official_outs: Mapping[str, int] | None = None
    official_pitches: Mapping[str, int] | None = None


def pitch_sequence_gaps(
    rows: Sequence[dict], official_pitches: Mapping[str, int] | None,
) -> str | None:
    """逐球序號閉合檢查：**唯一一個 event 粒度的完整性證明**。

    `game_livelog.pitch_cnt` 是該投手在該場的累計投球數，`pitching_gamelog.pitch_cnt`
    是官方的同一個量。若某位投手的 livelog 逐球序號集合**恰好**等於 `{1..官方投球數}`，
    就證明他的事件一顆都沒少（缺頭會少 1、缺中間會有洞、缺尾會少 max、多出來會超界）。

    **全場每位投手都閉合 ⇒ 整場 livelog 沒有任何事件缺漏**，於是半局內的出局數歸屬是
    「直接觀察到的」而非推導的。前三輪的檢查全部停在聚合量（半局集合、整場出局數總和），
    跨半局的相反誤配可以互相抵銷；逐球序號是**逐事件**的，沒有抵銷空間。
    """
    if not official_pitches:
        return "no_official_pitch_counts"
    seen: dict[str, set[int]] = {}
    for r in rows:
        if r.get("is_change_player") or r.get("pitch_cnt") is None:
            continue
        pid = r.get("pitcher_acnt")
        if pid is None:
            continue
        seen.setdefault(pid, set()).add(int(r["pitch_cnt"]))
    for pid, official in official_pitches.items():
        if official is None:
            return "official_pitch_count_missing"
        if seen.get(pid, set()) != set(range(1, int(official) + 1)):
            return "pitch_sequence_not_closed"
    for pid in seen:
        if pid not in official_pitches:
            return "livelog_pitcher_missing_from_box"
    return None


def out_allocation(rows: Sequence[dict]) -> dict[str, tuple[int, int]]:
    """livelog 事件 → 每位投手「記在他名下的出局數」區間 `{pitcher: (下界, 上界)}`。

    **注意這是整場加總**，只用來和官方整場出局數對帳。判斷某個半局能不能採計必須用
    `half_out_allocation()`——加總會讓跨半局的相反誤配互相抵銷（同一個聚合粒度的盲點）。

    以半局內的**投手更迭邊界**切段：某段的出局數＝下一段起始 `out_cnt` − 本段起始
    `out_cnt`；該半局最後一段則以 3 作結束（非全場最後半局必以三出局結束）。全場最後
    一個半局可能未達三出局，故該處下界取觀測值、上界取 3。

    這是 `coverage_reason` 拿來和官方 box 對帳的量：**缺漏的事件會讓某位投手的官方
    出局數落在他可見區間之外**。
    """
    cells = half_out_allocation(rows)
    lo: dict[str, int] = {}
    hi: dict[str, int] = {}
    for (pid, _half), (clo, chi) in cells.items():
        lo[pid] = lo.get(pid, 0) + clo
        hi[pid] = hi.get(pid, 0) + chi
    return {pid: (lo.get(pid, 0), hi.get(pid, 0)) for pid in set(lo) | set(hi)}


def half_out_allocation(
    rows: Sequence[dict],
) -> dict[tuple[str, tuple[int, str]], tuple[int, int]]:
    """livelog 事件 → `{(pitcher, 半局): (出局數下界, 上界)}`——**不加總**。

    採計某個半局的判準必須看這一格：只有當該格是一個**點**（下界＝上界＝3）時，
    「這個半局是他 3 個出局」才是被逼出來的；區間代表還有別的可行配置，證明不了就不採計。
    """
    plays = [r for r in rows if not r.get("is_change_player")]
    groups: list[tuple[tuple[int, str], list[dict]]] = []
    prev_key = None
    for r in plays:
        key = (int(r["inning_seq"]), str(r["visiting_home_type"]))
        if key != prev_key:
            groups.append((key, []))
            prev_key = key
        groups[-1][1].append(r)

    out: dict[tuple[str, tuple[int, str]], tuple[int, int]] = {}
    for idx, (half_key, evs) in enumerate(groups):
        is_last = idx == len(groups) - 1
        seq = [e for e in evs if e.get("out_cnt") is not None]
        segments: list[tuple[str, list[dict]]] = []
        for e in seq:
            pid = e.get("pitcher_acnt")
            if not segments or segments[-1][0] != pid:
                segments.append((pid, [e]))
            else:
                segments[-1][1].append(e)
        for i, (pid, seg) in enumerate(segments):
            start = int(seg[0]["out_cnt"])
            if i + 1 < len(segments):
                end_lo = end_hi = int(segments[i + 1][1][0]["out_cnt"])
            elif not is_last:
                end_lo = end_hi = 3
            else:
                end_lo, end_hi = int(seg[-1]["out_cnt"]), 3
            cell = (pid, half_key)
            prev = out.get(cell, (0, 0))
            out[cell] = (prev[0] + max(0, end_lo - start),
                         prev[1] + max(0, end_hi - start))
    return out


def coverage_reason(
    halves: Sequence[HalfInning],
    scoreboard: Mapping[tuple[int, str], int] | None,
    official_outs: int | None,
    allocation: Mapping[str, tuple[int, int]] | None = None,
    box: Mapping[str, int] | None = None,
) -> str | None:
    """尾段採計前的**覆蓋完整性**閘門；回傳缺陷代號，None 代表覆蓋完整。

    **這道閘門是紅線 2 的關鍵**，理由值得寫下來：`tail_credit` 是反向走「**看得見的**」
    投手半局，若某個半局整段不存在於 livelog，它會被**跨過**而不是被看見——於是更早的
    乾淨半局仍被採計，而官方的自責分可能正落在那個消失的半局裡，形成**高估**。

    只驗「已選入的半局乾不乾淨」無法排除這條路徑：那證明的是選中的都乾淨，不是沒有
    漏掉的。量詞方向不同，必須另外證明**該有的半局都在**。

    缺陷一律 fail-closed（尾段回 0），不嘗試補救：

    | 代號 | 條件 |
    |---|---|
    | `duplicate_half_innings` | livelog 出現重複的半局鍵（事件序異常） |
    | `no_scoreboard` | 該場無 `game_scoreboard`，無從交叉驗證 |
    | `livelog_half_missing_from_scoreboard` | livelog 有、獨立來源沒有 → 兩來源不一致 |
    | `scoreboard_half_missing_from_livelog` | 獨立來源有、livelog 沒有，且非「未進行的最終局下半／超出 livelog 範圍且零得分」這類良性樣態 |
    | `pitcher_half_innings_not_contiguous` | 該投手的半局不是同一側、連號的一段 |
    | `pitcher_outs_below_official` | 觀測到的出局數少於官方局數 → livelog 缺了他投的內容 |
    | `no_official_box` | 拿不到全場官方投球紀錄，無從對帳 |
    | `box_pitcher_missing_from_livelog` | 官方 box 有這位投手，livelog 完全看不到他 |
    | `livelog_pitcher_missing_from_box` | livelog 有這位投手，官方 box 沒有 |
    | `official_outs_outside_visible_range` | **半局內事件缺漏的偵測點**：某位投手的官方出局數落在 livelog 可見區間之外，代表他的出局數沒有可見的位置可以安放 |

    最後一項是唯一能抓到「**半局內**事件缺漏」的檢查——前面幾項都只到半局層級，
    共享「半局存在即視為內部完整」的盲點。
    """
    keys = [h.key for h in halves]
    if len(keys) != len(set(keys)):
        return "duplicate_half_innings"
    if not halves:
        return "no_livelog"
    if not scoreboard:
        return "no_scoreboard"

    ll = set(keys)
    max_inning = max(h.inning_seq for h in halves)
    for k in ll:
        if k not in scoreboard:
            return "livelog_half_missing_from_scoreboard"
    for k, runs in scoreboard.items():
        if k in ll:
            continue
        inning, vht = k
        # 良性缺席：主隊未進行的最終局下半，或 scoreboard 超出 livelog 範圍的空白列。
        benign = (vht == "2" and inning == max_inning) or inning > max_inning
        if not benign or runs:
            return "scoreboard_half_missing_from_livelog"

    mine = [h for h in halves if h.has_pitcher]
    if not mine:
        return "pitcher_absent_from_livelog"
    sides = {h.vht for h in mine}
    innings = [h.inning_seq for h in mine]
    if len(sides) != 1 or innings != list(range(min(innings), max(innings) + 1)):
        return "pitcher_half_innings_not_contiguous"
    if official_outs is not None and sum(h.pitcher_outs for h in mine) < official_outs:
        return "pitcher_outs_below_official"

    # ---- 半局**內部**完整性：唯一不共享「半局存在即完整」盲點的檢查 ----
    if not box:
        return "no_official_box"
    alloc = allocation or {}
    for pid, outs in box.items():
        if pid not in alloc:
            if outs:
                return "box_pitcher_missing_from_livelog"
            continue
        lo, hi = alloc[pid]
        if not lo <= outs <= hi:
            return "official_outs_outside_visible_range"
    for pid in alloc:
        if pid not in box:
            return "livelog_pitcher_missing_from_box"
    return None


def tail_credit(
    key: tuple[int, str, int],
    rows: Sequence[dict],
    pitcher_acnt: str,
    evidence: GameEvidence,
) -> TailCredit:
    """ER>0 那場出賽的尾段：從該投手最後一個半局往回，採計連續的「零得分半局」。

    半局一有得分跡象即停止（該半局與更早的都不採計）——因為官方已判定本場有自責分，
    我們不去猜是哪一分，只認「整個半局零得分」這個無可爭議的事實。

    **先過 `coverage_reason` 的覆蓋完整性閘門**（fail-closed，缺陷即回 0 出局數）。
    介面刻意收成「原始事件列 ＋ `GameEvidence`」：解析與閘門都在函式內做，呼叫端
    無法只餵半局清單而繞過證據檢查。
    """
    scoreboard = evidence.scoreboard
    box = evidence.official_outs or {}
    official_outs = box.get(pitcher_acnt)
    halves = half_innings_of(rows, pitcher_acnt)
    reason = (pitch_sequence_gaps(rows, evidence.official_pitches)
              or coverage_reason(halves, scoreboard, official_outs,
                                 out_allocation(rows), box))
    if reason:
        return TailCredit(key=key, outs=0, coverage_reason=reason)

    cells = half_out_allocation(rows)
    mine = [h for h in halves if h.has_pitcher]
    outs = 0
    credited: list[tuple[int, str]] = []
    passed: list[tuple[int, str]] = []
    for h in reversed(mine):
        # 採計半局必須在獨立來源也是零得分——runtime 交叉驗證，不只在對帳腳本裡驗。
        if not h.run_free or scoreboard.get(h.key):  # type: ignore[union-attr]
            break
        got = h.provable_outs
        # **歸屬只能採計被逼出來的部分**：看「該投手 × 該半局」這一格的**下界**——
        # 在所有可行配置中他至少記下這麼多出局。加總過的整場區間會讓跨半局的相反誤配
        # 互相抵銷，必須看這一格（不加總）才擋得住。
        got = min(got, cells.get((pitcher_acnt, h.key), (0, 0))[0])
        outs += got
        (credited if got else passed).append(h.key)
    clamped = official_outs is not None and outs > official_outs
    if clamped:
        outs = official_outs  # type: ignore[assignment]
    return TailCredit(key=key, outs=max(outs, 0), credited=tuple(credited),
                      passed=tuple(passed), clamped=clamped)


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
