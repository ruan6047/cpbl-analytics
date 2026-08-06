"""UX-GAME-RECAP1：單場**打席事實流** [plate appearance fact stream]。

每個打席＝局面狀態＋結果＋ΔRE24。**三個消費者共用同一份事實**（賽況頁 live Recent
Plays／賽後 recap 五塊／#79 逐打席探索器），不各自重建打席邏輯——前科是 leaders 自建
勝敗序列與 special_records 分歧。

設計（供跨家族查核者複核）:

* **純核心 + 薄 adapter**：ΔRE24、關鍵打席選取、得分半局鏈、事實句、mini 對帳閘門全為
  純函式（只吃 dict list），DB／Redis 只出現在 :func:`facts_from_db`／
  :func:`facts_from_snapshot`／:func:`build_game_facts`。
* **雙源**（brief 2026-08-06 需求方修訂）：
  - **權威源**＝`cpbl.game_plate_appearances`（published build）＋`game_pa_events`＋
    `game_livelog`。**必吃 canonical PA 表**，不得從 raw livelog 重刻切界。
  - **後備源**＝live worker final snapshot（Redis，TTL 48h），以
    ``pa_build.plate_appearances()`` **同一份純函式**現算，不另刻輕量切界。
  spike 實測 2026/A 241–245 五場：兩源的打席邊界與逐打者 ΔRE24 **零分歧**
  （docs/research/INIT-GAME-RECAP/spike-report.md §5.2）。
* **fail closed**：snapshot 路徑先過 :func:`mini_reconcile`；任一項不過就不出暫定版
  （退簡版），**嚴禁以時間推斷硬切完賽**（`present_status` 對完賽零鑑別力）。

ΔRE24 慣例（與 ``models/sabr.build_re24`` 同一套 Retrosheet 慣例，打者桶／跑者桶分離）::

    ΔRE24 = RE(下一個真實打席的打席前狀態) + 終結事件得分 − RE(終結事件「之前」的狀態)
    半局最後一個打席的 RE(after) = 0

⚠️ **錨點是「終結事件之前」的出局數**，必須走 :func:`pa_build.derive_half_inning_outs`
取回；誤用 canonical ``post_state.outs``（＝終結事件**之後**）會讓全場每個打席系統性
偏移一個出局的 RE 差（實測固定 +0.2475＝RE(空壘,0出)−RE(空壘,1出)）。這也是本服務
必須同時吃 PA 表與 livelog 的原因——PA 表不存 terminal 事件的 before-outs。

與 ``batter_re24`` 的關係（spike §2.3 全季逐打席窮舉，2026/A 239 場）：17,536 筆完全
相同；差異全部落入 4 類**canonical 較正確**的語意差（out_cnt 錨點落後 306、代打合併
與截斷碎片 137、突破僵局非打席 49、記錄規則 9.15(b) 歸屬 1），**未歸類 0**。
``tests/test_pa_facts.py`` 以合成事件流把這四類逐一釘住。

紅線：唯讀（不寫任何表）；不改 ``pa_build``／每日鏈／G4 凍結檔。

WP 的用法（2026-08-06 需求方三階裁決後的現行界線，brief 已留痕）：關鍵打席**以 |ΔWP|
序數選取、顯示擺動量、並以勝率條視覺化打席前後的水平值**。

* 階一（選取）：unsupported 的是 WP 機率**水平值的文字宣稱**（VAL1 中段 ±4–6pt 校準
  偏差），辨別力則有實證（池化 Brier 0.153 vs 主場常數基準 0.245）；序數不依賴校準。
* 階二（顯示擺動量）：變化量的兩端點同帶偏差、方向性相消，比水平值穩。
* 階三（勝率條）：條顯示的是水平值的**視覺化**——與已上線的 WP 曲線同資訊類（曲線本來
  就逐點畫水平值），揭露沿曲線既有框架，不另開新的誠實暴露面。

守門：``plate_appearances``（逐打席頁籤）**不帶任何 WP 欄位**、WP 欄位只掛在
``key_plays``、降級一律由 ``key_play_selection`` 揭露、顯示夾層（非終點不顯示 0/100%）
由前端 ``lib/win-prob-display.ts`` 唯一擁有並靠 ``wp_after_terminal`` 判斷豁免。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from cpbl.completion import completed_games_sql_with_evidence
from cpbl.db import conn
from cpbl.ingest.pa_build import (
    derive_half_inning_outs,
    event_sort_key,
    load_taxonomy,
    plate_appearances,
)

# RE 矩陣 span：與 sabr.build_re24／winprob 生產 artifact 同一 span，勿各自挑。
RE_SPAN = "2018-2025"

# 垃圾時間門檻（v1.3 排序契約）：分差 ≥ 7 的打席**降飽和呈現，不剔除、不加權**。
# 一旦加權重，數字就從「可驗證的事實」變成「我們的意見」。
GARBAGE_TIME_MARGIN = 7

# 關鍵打席取幾筆（brief recap 五塊②「關鍵打席 3–5」）。
KEY_PLAY_LIMIT = 5
# 低於此 |ΔRE24| 不值得叫「關鍵」（一次尋常出局約 0.25）。**降級路徑**才用得到。
KEY_PLAY_MIN_ABS = 0.30
# |ΔWP| 選取路徑的門檻：低於 3 個百分點的勝率擺動不值得叫「關鍵」。
# 尋常一出局的擺動約 1–2pt，得分打席通常 ≥5pt——3pt 剛好切在「有事發生」那條線上。
KEY_PLAY_MIN_WP_ABS = 0.03

# 事實句分支門檻（2026-08-06 需求方裁決 Q1）。
BLOWOUT_MARGIN = 5
CLOSE_MARGIN = 2

HALF_LABEL = {"1": "上", "2": "下"}

# ΔRE24 不可得的**封閉原因集合**（fail closed 的骨幹）。
#
# spike 的定案證據是「2026/A 全季逐打席窮舉歸類，未歸類 = 0」；把那個保證帶進生產碼的
# 形式就是這個封閉集合——任何打席要嘛有 ΔRE24，要嘛有一個**這裡列得出來的**機器可讀
# 原因，**不存在第三種狀態**（`tests/test_pa_facts.py::test_no_unclassified_facts`
# 以真實全季資料釘住）。新增原因必須同時擴充本集合，否則測試紅燈。
UNAVAILABLE_REASONS = frozenset({
    "pa_state_non_pa",                 # 突破僵局跑者佈局列等：非打席，不進分母
    "pa_state_truncated",              # 截斷碎片（無打者結果）
    "pa_state_unreliable",             # action 未登錄 taxonomy → fail closed
    "pa_state_reconciliation_required",  # 來源修正待對帳
    "terminal_event_missing",          # PA 有 end_event_no 但 livelog 對不到該列
    "state_incomplete",                # pre/post 狀態缺關鍵欄
    "negative_runs_on_play",           # 比分修正列：歸跑者桶，不記打者
    "game_in_progress",                # 賽事進行中的最後一個打席：after 錨點尚不存在
})

# snapshot livelog 欄位 → pa_build Event 欄位（DB game_livelog 同名）。
# 缺席於 snapshot 的 DB 欄位（is_score／catcher_acnt／defend_station_code）皆不參與
# 切界與 ΔRE24，故不需補。
SNAPSHOT_FIELD_MAP = {
    "MainEventNo": "main_event_no",
    "InningSeq": "inning_seq",
    "VisitingHomeType": "visiting_home_type",
    "BattingOrder": "batting_order",
    "OutCnt": "out_cnt",
    "BallCnt": "ball_cnt",
    "StrikeCnt": "strike_cnt",
    "PitchCnt": "pitch_cnt",
    "IsBall": "is_ball",
    "IsStrike": "is_strike",
    "Content": "content",
    "ActionName": "action_name",
    "BattingActionName": "batting_action_name",
    "HitterAcnt": "hitter_acnt",
    "HitterName": "hitter_name",
    "PitcherAcnt": "pitcher_acnt",
    "PitcherName": "pitcher_name",
    "FirstBase": "first_base",
    "SecondBase": "second_base",
    "ThirdBase": "third_base",
    "VisitingScore": "visiting_score",
    "HomeScore": "home_score",
    "IsChangePlayer": "is_change_player",
    "IsSpecialEvent": "is_special_event",
}
_SNAPSHOT_BOOLS = ("is_ball", "is_strike", "is_change_player", "is_special_event")

# 渲染狀態（設計稿 §7 降級階梯；由上往下第一個成立者生效）
STATE_AUTHORITATIVE = "authoritative"        # 階 1：權威源完整
STATE_PROVISIONAL = "provisional"            # 階 2：snapshot final 且 mini 對帳全過
STATE_PROVISIONAL_SIMPLE = "provisional_simple"  # 階 3：mini 對帳不過 → 簡版
STATE_LIVE = "live"                          # 賽事進行中：事實流可用（供逐打席換底），不進賽後態
STATE_STALE_LIVE = "stale_live"              # 階 4：final 未到且來源已過期，停在賽中態
STATE_PENDING = "pending"                    # 階 5：無即時源、權威源也未到
STATE_POSTPONED = "postponed"                # 階 6：延賽／保留賽
STATE_RECONCILING = "reconciling"            # 階 7：PA build 待對帳 → 走簡版


# ===========================================================================
# 純核心：狀態鍵
# ===========================================================================
def bases_key(bases: Any) -> str:
    """壘況 list（如 ``["1","3"]``）→ RE 矩陣鍵 ``"1_3"``。"""
    occupied = set(bases or [])
    return ("1" if "1" in occupied else "_") + ("2" if "2" in occupied else "_") \
        + ("3" if "3" in occupied else "_")


def bases_of_event(event: dict) -> str:
    """livelog 事件列 → 壘況鍵。**livelog 的壘位是該事件「之前」的壘況**。"""
    return (("1" if event.get("first_base") else "_")
            + ("2" if event.get("second_base") else "_")
            + ("3" if event.get("third_base") else "_"))


def annotate_scores(events: list[dict]) -> list[dict]:
    """回傳依事件序排好、每列標上事件前／後比分的**新 list**（不改動輸入 dict 以外欄位）。

    livelog 快照時點（sabr.build_re24 已 codify 的關鍵語意）：**壘位／out_cnt 是事件前、
    比分是事件後**——比分直接記在造成得分的那一列，壘位要到下一列才更新。故「某事件
    自身造成幾分」＝該列事件後分 − 前一列事件後分。
    """
    ordered = sorted(events, key=event_sort_key)
    away = home = 0
    for event in ordered:
        event["_pre_away"], event["_pre_home"] = away, home
        if event.get("visiting_score") is not None:
            away = int(event["visiting_score"])
        if event.get("home_score") is not None:
            home = int(event["home_score"])
        event["_post_away"], event["_post_home"] = away, home
    return ordered


# ===========================================================================
# 純核心：逐打席 ΔRE24
# ===========================================================================
def _score_keys(half: str) -> tuple[str, str]:
    """半局 → (事件前, 事件後) 的**進攻方**比分欄位。half=1 是客隊進攻。"""
    return ("_pre_away", "_post_away") if str(half) == "1" else ("_pre_home", "_post_home")


def delta_re24(pa_rows: list[dict], events: list[dict],
               re_map: dict[tuple[str, int], float],
               *, game_completed: bool = True) -> list[dict]:
    """canonical PA rows × livelog × RE 矩陣 → 逐打席事實（純函式）。

    ``pa_rows`` 需依 ``pa_index`` 排序，每筆至少含 ``state``／``pre_state``／
    ``post_state``／``end_event_no``／``hitter_acnt``；欄位語意同
    ``cpbl.game_plate_appearances``（權威源與 snapshot 路徑共用同一 shape）。

    ``game_completed=False``（賽事進行中）時，**事件流最後一個打席**的 after 錨點尚不存在
    ——半局還沒結束、下一個打席也還沒發生——故標 ``game_in_progress`` 而非套用「半局末
    RE=0」的慣例（那會把進行中的打席算成一個假的負值）。

    回傳每筆打席一個 dict；``delta_re24`` 為 None 時附 ``unavailable_reason``——
    **fail closed，不以 0 冒充「沒有影響」**。
    """
    ordered = annotate_scores(events)
    outs_by_event = derive_half_inning_outs(ordered)
    by_event_no = {str(e["main_event_no"]): e for e in ordered}
    names = player_names(ordered)

    rows = sorted(pa_rows, key=lambda r: r["pa_index"])
    # after 錨點＝下一個**真實**打席（state != non_pa）的打席前狀態：突破僵局佈局列的
    # 快照在跑者佈局「前」（壘位恆空），拿來當錨點會低估延長局開局狀態。
    real_positions = [i for i, p in enumerate(rows) if p["state"] != "non_pa"]
    next_real = {
        pos: (real_positions[j + 1] if j + 1 < len(real_positions) else None)
        for j, pos in enumerate(real_positions)
    }

    facts: list[dict] = []
    for index, pa in enumerate(rows):
        pre = pa.get("pre_state") or {}
        post = pa.get("post_state") or {}
        half = str(pre.get("half") or "")
        pre_key, post_key = _score_keys(half)
        # ⚠️ 比分不能讀 `pre_state.away_score`／`post_state.home_score`：那是把**該事件列的
        # 比分欄**原樣存下來，而 livelog 的比分欄是**事件後**快照。單一事件就結束的得分打席
        # （例如首球全壘打），起始列＝終結列，`pre_state` 存到的已經是得分**後**的比分，拿去
        # 算「這打席讓比分變成幾比幾」會多加一次。改由事件流的前／後比分直接取。
        start_ev = by_event_no.get(str(pa.get("start_event_no"))) if pa.get("start_event_no") else None
        end_ev = by_event_no.get(str(pa.get("end_event_no"))) if pa.get("end_event_no") else None
        away_before = start_ev["_pre_away"] if start_ev else pre.get("away_score")
        home_before = start_ev["_pre_home"] if start_ev else pre.get("home_score")
        away_after = end_ev["_post_away"] if end_ev else None
        home_after = end_ev["_post_home"] if end_ev else None
        fact: dict[str, Any] = {
            "pa_id": pa.get("pa_id"),
            "pa_index": pa["pa_index"],
            "state": pa["state"],
            "inning": pre.get("inning"),
            "half": pre.get("half"),
            "outs_before": pre.get("outs"),
            "bases_before": pre.get("bases") or [],
            "away_score_before": away_before,
            "home_score_before": home_before,
            # 該打席結束後的比分（直接取終結事件的事件後快照，不做加法）
            "away_score_after": away_after,
            "home_score_after": home_after,
            "hitter": _person(pa.get("hitter_acnt"), names),
            "end_hitter": _person(pa.get("end_hitter_acnt"), names),
            "pitcher": _person(pa.get("end_pitcher_acnt"), names),
            "result_action": pa.get("result_action"),
            "outcome_family": pa.get("outcome_family"),
            "start_event_no": pa.get("start_event_no"),
            "end_event_no": pa.get("end_event_no"),
            # 成員事件（含附掛的換人公告列）：消費端據此以 canonical 邊界重組逐打席清單，
            # 不必在前端重刻「連續同打者」的近似切法（那會把打席中途代打切成兩段）。
            "member_event_nos": [str(m) for m in (pa.get("member_event_nos") or [])],
            "runs_on_play": None,
            "delta_re24": None,
            "unavailable_reason": None,
            "garbage_time": _is_garbage_time(away_before, home_before),
        }
        terminal = end_ev
        if pa["state"] != "ready" or terminal is None:
            fact["unavailable_reason"] = (
                f"pa_state_{pa['state']}" if pa["state"] != "ready" else "terminal_event_missing")
            facts.append(fact)
            continue
        outs_before_terminal = outs_by_event.get(str(pa["end_event_no"]), (None, None))[0]
        if outs_before_terminal is None or post.get("outs") is None:
            fact["unavailable_reason"] = "state_incomplete"
            facts.append(fact)
            continue

        re_before = re_map[(bases_of_event(terminal), min(int(outs_before_terminal), 2))]
        runs = terminal[post_key] - terminal[pre_key]
        if runs < 0:  # 比分修正列：與 sabr 同慣例歸跑者桶，不記打者
            fact["unavailable_reason"] = "negative_runs_on_play"
            facts.append(fact)
            continue
        re_after = 0.0
        nxt = next_real.get(index)
        if nxt is None and not game_completed:
            fact["unavailable_reason"] = "game_in_progress"
            facts.append(fact)
            continue
        if nxt is not None:
            next_pre = rows[nxt].get("pre_state") or {}
            same_half = (next_pre.get("inning"), str(next_pre.get("half"))) == (
                pre.get("inning"), half)
            if same_half:  # 半局最後一個打席 → RE(after)=0（再見局依慣例歸零、得分照記）
                re_after = re_map[(bases_key(next_pre.get("bases")),
                                   min(int(next_pre.get("outs") or 0), 2))]
        fact["runs_on_play"] = runs
        fact["delta_re24"] = round(re_after + runs - re_before, 4)
        facts.append(fact)
    return facts


def _is_garbage_time(away_before: Any, home_before: Any) -> bool:
    if away_before is None or home_before is None:
        return False
    return abs(int(home_before) - int(away_before)) >= GARBAGE_TIME_MARGIN


def _person(player_id: Any, names: dict[str, str]) -> dict[str, Any] | None:
    if not player_id:
        return None
    return {"player_id": str(player_id), "name": names.get(str(player_id))}


def player_names(events: list[dict]) -> dict[str, str]:
    """逐場來源的姓名對照（打者／投手）。

    **刻意不 join ``cpbl.players``**：該表會缺當季新登錄球員（實測 ``0000007822`` 威克
    無列，MVP 會顯示成 10 碼 ID），而 ``game_livelog.hitter_name`` 與 snapshot
    ``HitterName`` 兩源皆有正確中文名（spike §6.1 發現 2）。
    """
    names: dict[str, str] = {}
    for event in events:
        for id_key, name_key in (("hitter_acnt", "hitter_name"), ("pitcher_acnt", "pitcher_name")):
            pid, name = event.get(id_key), event.get(name_key)
            if pid and name and str(name).strip():
                names[str(pid)] = str(name).strip()
    return names


# ===========================================================================
# 純核心：關鍵打席／得分半局鏈
# ===========================================================================
def wp_before(fact: dict, scorer: Any) -> float | None:
    """該打席**打席前**局面的主隊 WP；狀態欄不全回 None（不猜）。

    與 ``api/routers/recap._score_pre`` 同一台解算器（``models/winprob_scorer``）、同一組
    輸入語意（diff＝主隊視角、bases/outs＝打擊方狀態），差別只在比分取事件流的
    打席前快照而非 ``pre_state``（後者對「單一事件就結束的得分打席」是得分**後**的值，
    見 :func:`delta_re24` 的說明）。
    """
    inning, half = fact.get("inning"), fact.get("half")
    outs = fact.get("outs_before")
    away, home = fact.get("away_score_before"), fact.get("home_score_before")
    if inning is None or half is None or outs is None or away is None or home is None:
        return None
    return scorer(int(inning), str(half), int(home) - int(away),
                  bases_key(fact.get("bases_before")), min(int(outs), 2))


def wp_swings(facts: list[dict], *, scorer: Any,
              final_outcome: float | None = None) -> dict[int, dict[str, Any]]:
    """``pa_index`` → ``{before, after, delta, terminal}``（純函式；缺值不進 map，**不以 0 冒充**）。

    ``before``／``after``＝該打席前後的**主隊勝率水平值**（供關鍵打席的勝率條視覺化；
    需求方 2026-08-06 第三階裁決「保留長條圖顯示當前勝率與該打席造成的變化」——水平值
    的視覺化與已上線的 WP 曲線同資訊類，曲線本來就逐點畫水平值，揭露沿曲線既有框架）。
    ``delta``＝``after − before``（主隊視角）。``terminal``＝該打席的 after 是終場結果
    （非局面推算值）→ 呼叫端的顯示夾層須豁免這一點（`lib/win-prob-display.ts`）。

    錨點語意與 ``/api/v1/games/{sno}/recap-wp`` **逐位一致**（同解算器、同 before/after
    捨入後相減）：after＝下一個真實打席（``state != 'non_pa'``）的打席前局面，最後一個
    真實打席收斂到終場結果（勝 1／負 0／和 0.5，含再見）。突破僵局的跑者佈局列不可作
    錨點（其快照在佈局前、壘位恆空）。

    **主隊視角**（正＝主隊勝率上升），與賽況頁 WP 曲線同視角、正負與曲線升降對齊——
    兩處對照不打架是顯示面的硬需求（2026-08-06 需求方裁決）。

    誠實邊界：WP 全 scope 時間外驗證 unsupported（WP-VAL1）——**機率水平值不作文字宣稱**，
    只作與既有 WP 曲線同框架的視覺化；變化量的兩端點同帶偏差、方向性相消。
    """
    if scorer is None:
        return {}
    real_positions = [i for i, f in enumerate(facts) if f.get("state") != "non_pa"]
    next_real = {
        pos: (real_positions[j + 1] if j + 1 < len(real_positions) else None)
        for j, pos in enumerate(real_positions)
    }
    out: dict[int, dict[str, Any]] = {}
    for index in real_positions:
        fact = facts[index]
        if fact.get("state") != "ready":
            continue  # fail closed：不可靠打席不給擺動值
        before = wp_before(fact, scorer)
        if before is None:
            continue
        nxt = next_real.get(index)
        after = final_outcome if nxt is None else wp_before(facts[nxt], scorer)
        if after is None:
            continue
        before, after = round(before, 4), round(after, 4)
        out[fact["pa_index"]] = {
            "before": before, "after": after, "delta": round(after - before, 4),
            # 最後一個真實打席的 after＝終場結果，不是局面推算值 → 顯示夾層豁免
            "terminal": nxt is None,
        }
    return out


def key_plays(facts: list[dict], *, wp_by_index: dict[int, dict[str, Any]] | None = None,
              limit: int = KEY_PLAY_LIMIT, min_abs: float = KEY_PLAY_MIN_ABS,
              min_wp_abs: float = KEY_PLAY_MIN_WP_ABS) -> list[dict]:
    """關鍵打席 3–5：**|ΔWP| 取前 N，回傳時改回時間序**（brief recap 五塊②）。

    選取訊號（2026-08-06 需求方第五輪人工審裁決，統計紅線修訂）：

    * **主路徑＝|ΔWP|**（``wp_by_index``）。原「禁 WPA 排序」禁令經需求方重查 VAL1 後
      精確化：unsupported 的是**機率水平值的宣稱**，辨別力則有實證（池化 Brier 0.153
      vs 主場常數基準 0.245），而**序數選取不依賴水平校準**——中段 ±4–6pt 的偏差不改變
      「哪幾個打席擺動最大」的排序。
    * **降級路徑＝|ΔRE24|**：WP 模型不可用（無分布 artifact／賽事類型不支援）時退回，
      由呼叫端在 ``key_play_selection`` 揭露，**不靜默改變選取準則**。

    候選必須同時有 ``delta_re24``（ΔRE24 chip 是呈現面的次要資訊，缺值不入選以免整列
    只剩擺動量）。回傳的是**淺拷貝**並掛上 ``delta_wp``／``wp_before``／``wp_after``／
    ``wp_after_terminal``（後三者供勝率條視覺化）：``plate_appearances``（逐打席頁籤）
    **不帶任何 WP 欄位**，顯示面差異靠資料本身守住，不靠前端自律。

    垃圾時間（分差 ≥7）在 |ΔWP| 路徑下**天然被壓到選不上**（大比分領先時任何打席的勝率
    擺動都接近 0），故不再需要呈現層降飽和；``garbage_time`` 旗標仍隨事實流保留，供
    其他消費者使用。
    """
    if wp_by_index:
        scored = [f for f in facts
                  if f.get("delta_re24") is not None
                  and f["pa_index"] in wp_by_index
                  and abs(wp_by_index[f["pa_index"]]["delta"]) >= min_wp_abs]
        top = sorted(scored,
                     key=lambda f: (-abs(wp_by_index[f["pa_index"]]["delta"]), f["pa_index"]))[:limit]
        return [{**f, "delta_wp": wp_by_index[f["pa_index"]]["delta"],
                 "wp_before": wp_by_index[f["pa_index"]]["before"],
                 "wp_after": wp_by_index[f["pa_index"]]["after"],
                 "wp_after_terminal": wp_by_index[f["pa_index"]]["terminal"]}
                for f in sorted(top, key=lambda f: f["pa_index"])]
    scored = [f for f in facts if f.get("delta_re24") is not None
              and abs(f["delta_re24"]) >= min_abs]
    top = sorted(scored, key=lambda f: (-abs(f["delta_re24"]), f["pa_index"]))[:limit]
    return [{**f, "delta_wp": None, "wp_before": None, "wp_after": None,
             "wp_after_terminal": False}
            for f in sorted(top, key=lambda f: f["pa_index"])]


def key_play_selection(wp_by_index: dict[int, dict[str, Any]] | None,
                       reason: str | None = None) -> dict[str, Any]:
    """關鍵打席選取準則的**機器可讀揭露**（呼叫端據此標示，不得靜默降級）。"""
    if wp_by_index:
        return {"signal": "delta_wp", "min_abs": KEY_PLAY_MIN_WP_ABS,
                "degraded": False, "reason": None}
    return {"signal": "delta_re24", "min_abs": KEY_PLAY_MIN_ABS,
            "degraded": True, "reason": reason or "winprob_unavailable"}


def scoring_chain(facts: list[dict]) -> list[dict]:
    """得分半局事實鏈：依時間序列出**有得分的半局**與該半局的得分打席。"""
    chain: list[dict] = []
    current: dict[str, Any] | None = None
    for fact in facts:
        if fact["inning"] is None or fact["half"] is None:
            continue
        key = (fact["inning"], str(fact["half"]))
        if current is None or current["_key"] != key:
            current = {"_key": key, "inning": fact["inning"], "half": str(fact["half"]),
                       "runs": 0, "plays": []}
            chain.append(current)
        runs = fact.get("runs_on_play") or 0
        if runs > 0:
            current["runs"] += runs
            current["plays"].append({
                "pa_index": fact["pa_index"], "pa_id": fact.get("pa_id"),
                "hitter": fact["hitter"], "result_action": fact["result_action"],
                "runs": runs, "delta_re24": fact.get("delta_re24"),
                "end_event_no": fact.get("end_event_no"),
                "start_event_no": fact.get("start_event_no"),
                # 得分後比分：三處逐列呈現才能用同一個得分標示元件
                # （前端不自行掃 livelog 重算比分，也不做加法）。
                "half": str(fact["half"]) if fact["half"] is not None else None,
                "away_score_after": fact["away_score_after"],
                "home_score_after": fact["home_score_after"],
            })
    return [{k: v for k, v in half.items() if k != "_key"} for half in chain if half["runs"] > 0]


def half_inning_breakdown(facts: list[dict]) -> dict[str, list[dict]]:
    """``"{inning}|{half}"`` → 該半局的逐打席列（linescore 展開用；含無得分半局）。"""
    out: dict[str, list[dict]] = {}
    for fact in facts:
        if fact["inning"] is None or fact["half"] is None:
            continue
        out.setdefault(f"{fact['inning']}|{fact['half']}", []).append(fact)
    return out


# ===========================================================================
# 純核心：一句事實句（模板 ＋ 事實槽）
# ===========================================================================
# 分支條件全部機器可判定；槽位全部是可查證事實。不含形容詞、**不含球迷暱稱**
# （brief 非目標：「球迷暱稱於 recap 正式文案」），不用 WPA。
SENTENCE_TEMPLATES = {
    "walkoff": ("{winner} {winner_score}：{loser_score} 擊敗 {loser}，"
                "{inning} 局下 {hitter} 的{action}是再見致勝的一擊（ΔRE24 {delta}）。"),
    "blowout": ("{winner} {winner_score}：{loser_score} 擊敗 {loser}，"
                "{big_inning} 局{big_half}的 {big_runs} 分是最大單局進帳；"
                "全場對得分期望值影響最大的打席是 {inning} 局{half} {hitter} 的{action}"
                "（ΔRE24 {delta}）。"),
    "close": ("{winner} {winner_score}：{loser_score} 擊敗 {loser}，"
              "全場對得分期望值影響最大的打席是 {inning} 局{half} {hitter} 的{action}"
              "（ΔRE24 {delta}），該半局共得 {half_runs} 分。"),
    # 分差 3–4：既非大比分也非一分差，用中性句，不硬套任一端的語氣
    "regular": ("{winner} {winner_score}：{loser_score} 擊敗 {loser}，"
                "全場對得分期望值影響最大的打席是 {inning} 局{half} {hitter} 的{action}"
                "（ΔRE24 {delta}）。"),
    "tie": ("{home} {home_score}：{away_score} {away} 和局；"
            "全場對得分期望值影響最大的打席是 {inning} 局{half} {hitter} 的{action}"
            "（ΔRE24 {delta}）。"),
    "score_only": "{home} {home_score}：{away_score} {away}。",
}


def game_shape(facts: list[dict], home_score: int, away_score: int) -> str:
    """賽果形狀（機器可判定）：walkoff / blowout / close / regular / tie。

    門檻為 2026-08-06 需求方裁決 Q1：``blowout ≥ 5``、``close ≤ 2``，中間的 3–4 分差
    走中性的 ``regular``（不硬套任一端的語氣）。
    """
    if home_score == away_score:
        return "tie"
    ready = [f for f in facts if f["state"] == "ready"]
    if home_score > away_score and ready:
        last = ready[-1]
        if str(last["half"]) == "2" and (last["inning"] or 0) >= 9:
            return "walkoff"
    margin = abs(home_score - away_score)
    if margin >= BLOWOUT_MARGIN:
        return "blowout"
    return "close" if margin <= CLOSE_MARGIN else "regular"


def conclusion(facts: list[dict], *, home_score: int, away_score: int,
               home_name: str, away_name: str,
               inning_runs: dict[tuple[int, str], int] | None = None) -> dict:
    """①結論行的一句事實句 ＋ 事實槽。

    ``inning_runs``＝``(inning, half) → runs``（來自 scoreboard／snapshot inning_score）；
    缺席時退回由打席事實流推導，兩者皆缺則降級為只有比分的句子。

    ⚠️ **再見打席的 ΔRE24 是負值**：半局結束使 RE(after)=0，一支只帶 1 分的再見安打會被
    記成 ``1 − RE(_2_,0)``。本函式（結論行）固定以賽果事實單獨承載再見，不依賴②的排序
    ——這正是 brief 把①②分開的理由（spike §6.1 發現 1）。改採 |ΔWP| 選取後②通常也會
    選到再見打席（勝率直接收斂到 1），但那是選取訊號的副產品，不是本函式的前提。
    """
    ranked = sorted([f for f in facts if f.get("delta_re24") is not None],
                    key=lambda f: (-abs(f["delta_re24"]), f["pa_index"]))
    shape = game_shape(facts, home_score, away_score)
    home_win = home_score > away_score
    slots: dict[str, Any] = {
        "home": home_name, "away": away_name,
        "home_score": home_score, "away_score": away_score,
        "winner": home_name if home_win else away_name,
        "loser": away_name if home_win else home_name,
        "winner_score": max(home_score, away_score),
        "loser_score": min(home_score, away_score),
    }
    if not ranked:
        return {"shape": "score_only", "sentence":
                SENTENCE_TEMPLATES["score_only"].format(**slots), "slots": slots}

    focus = ranked[0]
    if shape == "walkoff":
        ready = [f for f in facts if f["state"] == "ready"]
        focus = ready[-1] if ready else focus
    slots.update({
        "inning": focus["inning"],
        "half": HALF_LABEL.get(str(focus["half"]), ""),
        "hitter": _display_name(focus["hitter"]),
        "action": (focus["result_action"] or "").strip(),
        "delta": _signed(focus.get("delta_re24")),
    })

    runs_map = dict(inning_runs or {}) or _runs_from_facts(facts)
    if shape == "close":
        slots["half_runs"] = runs_map.get((focus["inning"], str(focus["half"])), 0)
    if shape == "blowout":
        if not runs_map:
            shape = "regular"  # 沒有逐局得分就講不出「最大單局」，退中性句而非編一個
        else:
            (big_inning, big_half), big_runs = max(
                runs_map.items(), key=lambda kv: (kv[1], -kv[0][0]))
            slots.update({"big_inning": big_inning,
                          "big_half": HALF_LABEL.get(big_half, ""), "big_runs": big_runs})
    return {"shape": shape, "sentence": SENTENCE_TEMPLATES[shape].format(**slots),
            "slots": slots, "focus_pa_index": focus["pa_index"]}


def _display_name(person: dict | None) -> str:
    if not person:
        return ""
    return person.get("name") or person.get("player_id") or ""


def _signed(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.2f}"


def _runs_from_facts(facts: list[dict]) -> dict[tuple[int, str], int]:
    runs: dict[tuple[int, str], int] = {}
    for fact in facts:
        got = fact.get("runs_on_play") or 0
        if got > 0 and fact["inning"] is not None:
            key = (fact["inning"], str(fact["half"]))
            runs[key] = runs.get(key, 0) + got
    return runs


# ===========================================================================
# 純核心：snapshot 事件正規化 + mini 對帳閘門
# ===========================================================================
def _as_bool(value: Any) -> bool | None:
    """官方 payload 的旗標是**字串 "0"/"1"**；DB ingest 已轉 bool，snapshot 未轉。

    不轉型會讓 ``pa_build._usable()`` 把每一列都當換人列（``"0"`` 是 truthy），
    PA 數直接歸零。
    """
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip() not in ("0", "false", "False")
    return bool(value)


def snapshot_events(snapshot: dict) -> list[dict]:
    """live snapshot 的 ``livelog`` → ``pa_build`` Event（純函式）。

    官方 LiveLog 的末列**可能重複**（實測 2026/A/241），以 ``main_event_no`` 去重。
    """
    events: list[dict] = []
    seen: set[str] = set()
    for row in snapshot.get("livelog") or []:
        event = {dst: row.get(src) for src, dst in SNAPSHOT_FIELD_MAP.items()}
        event["main_event_no"] = str(event["main_event_no"])
        if event["main_event_no"] in seen:
            continue
        seen.add(event["main_event_no"])
        for field in _SNAPSHOT_BOOLS:
            event[field] = _as_bool(event.get(field))
        for field in ("first_base", "second_base", "third_base"):
            event[field] = (str(event.get(field) or "")).strip() or None
        events.append(event)
    return events


def mini_reconcile(snapshot: dict, events: list[dict], pas: list) -> tuple[bool, str | None]:
    """當晚 mini 對帳閘門（**fail closed**）：不過即不出暫定 recap、退簡版。

    snapshot 屬 LIVE 暫態（#54 領域），暫定 recap 出手前必須自證內部一致。四項判準在
    spike 的 2026/A 241–245 五場皆通過（報告 §7.1）。
    """
    from cpbl.ingest.pa_build import half_inning_out_violations

    if snapshot.get("phase") != "final":
        return False, "phase_not_final"
    if not events:
        return False, "empty_livelog"
    # ``pinch_hit_slot`` 佐證要呼叫 ``_is_real_pitch()``，後者需要 is_strike/is_ball。
    # 缺這兩欄時該分支會變成「無條件合併」（跳過球數未回退的守門）→ 過度合併。
    # 2026/A 全季 8 次打席合併中 7 次走此分支，故缺欄一律 fail closed。
    if any(e.get("is_strike") is None or e.get("is_ball") is None for e in events):
        return False, "missing_ball_strike_flags"
    ordered = annotate_scores(events)
    last = ordered[-1]
    away, home = (snapshot.get("away") or {}).get("score"), (snapshot.get("home") or {}).get("score")
    if (last["_post_away"], last["_post_home"]) != (away, home):
        return False, "score_mismatch"
    if half_inning_out_violations(pas):
        return False, "half_inning_out_violation"
    return True, None


# ===========================================================================
# 薄 adapter：權威源（DB）
# ===========================================================================
_LIVELOG_COLS = (
    "main_event_no, inning_seq, visiting_home_type, batting_order, out_cnt, ball_cnt, "
    "strike_cnt, pitch_cnt, content, action_name, batting_action_name, hitter_acnt, "
    "hitter_name, pitcher_acnt, pitcher_name, first_base, second_base, third_base, "
    "is_strike, is_ball, is_score, is_change_player, is_special_event, "
    "visiting_score, home_score"
)
_PA_COLS = (
    "pa.pa_id::text AS pa_id, pa.pa_index, pa.state, pa.hitter_acnt, pa.end_hitter_acnt, "
    "pa.start_pitcher_acnt, pa.end_pitcher_acnt, pa.result_action, pa.outcome_family, "
    "pa.pre_state, pa.post_state, pa.start_event_no, pa.end_event_no"
)


def _rows(cur: Any) -> list[dict]:
    columns = [d[0] for d in cur.description]
    return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]


def load_re_matrix(cur: Any, kind_code: str, span: str = RE_SPAN) -> dict[tuple[str, int], float]:
    """RE 矩陣（24 列，process 級可 cache）。季後賽 kind 借一軍例行矩陣。"""
    lookup = "A" if kind_code in ("A", "C", "E") else kind_code
    cur.execute("SELECT bases, outs, re FROM cpbl.run_expectancy WHERE span=%s AND kind_code=%s",
                (span, lookup))
    return {(b, int(o)): float(v) for b, o, v in cur.fetchall()}


def load_livelog(cur: Any, season: int, kind_code: str, game_sno: int) -> list[dict]:
    cur.execute(
        f"SELECT {_LIVELOG_COLS} FROM cpbl.game_livelog "  # noqa: S608 (固定欄位常數)
        "WHERE year=%s AND kind_code=%s AND game_sno=%s",
        (season, kind_code, game_sno))
    return _rows(cur)


def load_published_pas(cur: Any, season: int, kind_code: str, game_sno: int) -> list[dict]:
    """published build 的 canonical 打席。**只吃 published**，不碰 superseded／待對帳。"""
    cur.execute(
        f"SELECT {_PA_COLS} FROM cpbl.game_plate_appearances pa "  # noqa: S608
        "JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id AND b.state = 'published' "
        "WHERE pa.year=%s AND pa.kind_code=%s AND pa.game_sno=%s ORDER BY pa.pa_index",
        (season, kind_code, game_sno))
    return _rows(cur)


def load_pa_members(cur: Any, season: int, kind_code: str,
                    game_sno: int) -> dict[int, list[str]]:
    """``pa_index`` → 成員事件號（依 ``event_position``）。published build only。"""
    cur.execute(
        "SELECT pa.pa_index, e.event_no FROM cpbl.game_pa_events e "
        "JOIN cpbl.game_plate_appearances pa ON pa.pa_row_id = e.pa_row_id "
        "JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id AND b.state = 'published' "
        "WHERE e.year=%s AND e.kind_code=%s AND e.game_sno=%s "
        "ORDER BY pa.pa_index, e.event_position",
        (season, kind_code, game_sno))
    members: dict[int, list[str]] = {}
    for pa_index, event_no in cur.fetchall():
        members.setdefault(int(pa_index), []).append(str(event_no))
    return members


def has_reconciliation_build(cur: Any, season: int, kind_code: str, game_sno: int) -> bool:
    """存在 ``reconciliation_required`` build＝來源有修正尚未對帳（設計稿 §7 階 7）。"""
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM cpbl.game_plate_appearances pa "
        "JOIN cpbl.game_recap_builds b ON b.build_id = pa.build_id "
        "WHERE pa.year=%s AND pa.kind_code=%s AND pa.game_sno=%s "
        "AND b.state = 'reconciliation_required')",
        (season, kind_code, game_sno))
    row = cur.fetchone()
    return bool(row and row[0])


def load_game(cur: Any, season: int, kind_code: str, game_sno: int) -> dict | None:
    """games 主列 ＋ 證據感知的完賽判準（`is_completed_game` 的 SQL 等價物）。"""
    cur.execute(
        "SELECT g.year, g.kind_code, g.game_sno, g.game_date, g.venue, g.delay_kind, "
        "g.home_team_code, g.home_team_name, g.home_score, "
        "g.away_team_code, g.away_team_name, g.away_score, "
        "g.winning_pitcher_id, g.losing_pitcher_id, g.closer_id, g.mvp_id, "
        f"{completed_games_sql_with_evidence('g')} AS completed "
        "FROM cpbl.games g WHERE g.year=%s AND g.kind_code=%s AND g.game_sno=%s",
        (season, kind_code, game_sno))
    rows = _rows(cur)
    return rows[0] if rows else None


def load_inning_runs(cur: Any, season: int, kind_code: str,
                     game_sno: int) -> dict[tuple[int, str], int]:
    cur.execute(
        "SELECT inning_seq, visiting_home_type, score_cnt FROM cpbl.game_scoreboard "
        "WHERE year=%s AND kind_code=%s AND game_sno=%s", (season, kind_code, game_sno))
    return {(int(i), str(h)): int(s or 0) for i, h, s in cur.fetchall() if i is not None}


# ===========================================================================
# 薄 adapter：後備源（snapshot）
# ===========================================================================
def pa_rows_from_snapshot(season: int, kind_code: str, game_sno: int,
                          events: list[dict]) -> tuple[list[dict], list]:
    """以 ``pa_build`` 的**同一份純函式**在 snapshot 事件上現算 canonical 打席。

    回傳 ``(權威源同 shape 的 dict list, PlateAppearance 物件 list)``；後者供
    :func:`mini_reconcile` 跑既有不變式。
    """
    pas = plate_appearances(season, kind_code, game_sno, events, load_taxonomy())
    rows = [{
        "pa_id": str(pa.pa_id),
        "pa_index": pa.pa_index,
        "state": pa.state,
        "hitter_acnt": pa.hitter_acnt,
        "end_hitter_acnt": pa.end_hitter_acnt,
        "start_pitcher_acnt": pa.start_pitcher_acnt,
        "end_pitcher_acnt": pa.end_pitcher_acnt,
        "result_action": pa.result_action,
        "outcome_family": pa.outcome_family,
        "pre_state": pa.pre_state,
        "post_state": pa.post_state,
        "start_event_no": pa.start_event_no,
        "end_event_no": pa.end_event_no,
        "member_event_nos": [m.event_no for m in pa.members],
    } for pa in pas]
    return rows, pas


def snapshot_inning_runs(snapshot: dict) -> dict[tuple[int, str], int]:
    """snapshot 的 ``inning_score``（``[{Seq, Score}]``）→ ``(inning, half) → runs``。"""
    runs: dict[tuple[int, str], int] = {}
    for side, half in (("away", "1"), ("home", "2")):
        for cell in (snapshot.get(side) or {}).get("inning_score") or []:
            seq, score = cell.get("Seq"), cell.get("Score")
            if seq is None:
                continue
            try:
                runs[(int(seq), half)] = int(score or 0)
            except (TypeError, ValueError):
                continue
    return runs


def snapshot_decisions(snapshot: dict) -> dict:
    """snapshot 的官方決勝欄位。

    ⚠️ 實測 2026/A 241–245：``mvp`` 5/5 可得，**``winning_pitcher``／
    ``losing_pitcher`` 只有 2/5**（spike §4.3）。故暫定期勝敗投一律標
    ``official_pending``，**不顯示可能錯誤的值、也不留白冒充「沒有勝投」**。
    """
    decisions = snapshot.get("decisions") or {}
    return {
        "winning_pitcher": decisions.get("winning_pitcher"),
        "losing_pitcher": decisions.get("losing_pitcher"),
        "closer": decisions.get("closer"),
        "mvp": decisions.get("mvp"),
        "availability": ("available" if decisions.get("winning_pitcher")
                         else "official_pending"),
    }


# ===========================================================================
# 服務入口
# ===========================================================================
def _empty(season: int, kind_code: str, game_sno: int, state: str, reason: str,
           game: dict | None = None) -> dict:
    return {
        "season": season, "kind_code": kind_code, "game_sno": game_sno,
        "source": None, "render_state": state, "reason": reason,
        "completed": False,
        "final": None if game is None else {
            "home_score": game.get("home_score"), "away_score": game.get("away_score")},
        "teams": None if game is None else _teams_of(game),
        "conclusion": None, "plate_appearances": [], "key_plays": [],
        # 沒有關鍵打席可選 → 選取準則不適用（null），不謊稱「降級」
        "key_play_selection": None,
        "scoring_chain": [], "half_innings": {},
        "re_matrix": {"span": RE_SPAN, "kind_code": kind_code},
    }


def _teams_of(game: dict) -> dict:
    return {
        "home": {"code": game.get("home_team_code"), "name": game.get("home_team_name")},
        "away": {"code": game.get("away_team_code"), "name": game.get("away_team_name")},
    }


def _db_decisions(game: dict, names: dict[str, str]) -> dict:
    """權威源決勝欄位。姓名走逐場來源（``names``），**不 join ``cpbl.players``**（§6.3）。"""
    return {
        "winning_pitcher": _person(game.get("winning_pitcher_id"), names),
        "losing_pitcher": _person(game.get("losing_pitcher_id"), names),
        "closer": _person(game.get("closer_id"), names),
        "mvp": _person(game.get("mvp_id"), names),
        "availability": "available",
    }


def _assemble(*, season: int, kind_code: str, game_sno: int, source: str, render_state: str,
              reason: str | None, game: dict, facts: list[dict], decisions: dict,
              inning_runs: dict[tuple[int, str], int], simple: bool = False,
              wp_by_index: dict[int, dict[str, Any]] | None = None,
              wp_reason: str | None = None) -> dict:
    home_score = int(game.get("home_score") or 0)
    away_score = int(game.get("away_score") or 0)
    result = ("home_win" if home_score > away_score
              else "away_win" if home_score < away_score else "tie")
    payload = {
        "season": season, "kind_code": kind_code, "game_sno": game_sno,
        "source": source, "render_state": render_state, "reason": reason,
        "completed": True,
        "final": {"home_score": home_score, "away_score": away_score, "result": result},
        "teams": _teams_of(game),
        "game_date": game.get("game_date"),
        "venue": game.get("venue"),
        "decisions": decisions,
        "conclusion": None,
        "plate_appearances": [] if simple else facts,
        "key_plays": [] if simple else key_plays(facts, wp_by_index=wp_by_index),
        # 簡版不出關鍵打席 → 選取準則不適用（null），不謊報「降級」
        "key_play_selection": None if simple else key_play_selection(wp_by_index, wp_reason),
        "scoring_chain": scoring_chain(facts) if facts else [],
        "half_innings": {} if simple else half_inning_breakdown(facts),
        "re_matrix": {"span": RE_SPAN, "kind_code": kind_code},
    }
    if not simple:
        payload["conclusion"] = conclusion(
            facts, home_score=home_score, away_score=away_score,
            home_name=str(game.get("home_team_name") or ""),
            away_name=str(game.get("away_team_name") or ""),
            inning_runs=inning_runs)
    else:
        slots = {"home": str(game.get("home_team_name") or ""),
                 "away": str(game.get("away_team_name") or ""),
                 "home_score": home_score, "away_score": away_score}
        payload["conclusion"] = {"shape": "score_only", "slots": slots,
                                 "sentence": SENTENCE_TEMPLATES["score_only"].format(**slots)}
    return payload


def _load_wp_swings(facts: list[dict], *, season: int, kind_code: str,
                    home_score: Any, away_score: Any) -> tuple[dict[int, dict[str, Any]], str | None]:
    """關鍵打席選取／顯示用的 ΔWP map；不可用時回 ``({}, reason)`` 讓呼叫端降級揭露。

    **絕不讓 WP 拖垮事實流**：ΔRE24、得分鏈、事實句全部不依賴 WP，故此處任何失敗都
    只降級關鍵打席的選取訊號（回 ``|ΔRE24|``），不讓整個 recap 掛掉。
    """
    from cpbl.models.winprob_scorer import DIST_SOURCE, get_scorer

    if kind_code not in DIST_SOURCE:
        return {}, "wp_scope_unsupported"  # 如 F（明星賽）：無分布，也不借用
    if home_score is None or away_score is None:
        return {}, "final_unknown"
    try:
        scorer, _model = get_scorer(kind_code, season)
    except Exception:  # noqa: BLE001 — artifact／解算器異常一律降級，不中斷事實流
        return {}, "winprob_model_error"
    if scorer is None:
        return {}, "winprob_model_not_built"
    home, away = int(home_score), int(away_score)
    final_outcome = 1.0 if home > away else (0.0 if home < away else 0.5)
    swings = wp_swings(facts, scorer=scorer, final_outcome=final_outcome)
    return swings, None if swings else "winprob_no_scored_plays"


def build_game_facts(season: int, kind_code: str, game_sno: int,
                     snapshot: dict | None = None) -> dict:
    """單場打席事實流：依設計稿 §7 的降級階梯決定資料源與呈現層級。

    ``snapshot``＝呼叫端（API）已取得的 live snapshot；None＝無即時源。
    唯讀，不寫任何表。
    """
    with conn() as connection:
        cur = connection.cursor()
        game = load_game(cur, season, kind_code, game_sno)
        if game is None:
            return _empty(season, kind_code, game_sno, STATE_PENDING, "game_not_found")

        # 階 6：延賽／保留賽——沿現行顯示，不進賽後態（保留賽帶比分但日期在未來，
        # is_completed_game 的日期界線本就排除）。
        if game.get("delay_kind") and not game["completed"]:
            return _empty(season, kind_code, game_sno, STATE_POSTPONED,
                          str(game["delay_kind"]), game)

        re_map = load_re_matrix(cur, kind_code)
        if not re_map:
            return _empty(season, kind_code, game_sno, STATE_PENDING,
                          "run_expectancy_missing", game)

        # 階 1：權威源（資料層完賽判準＝證據感知的 is_completed_game）
        if game["completed"]:
            pa_rows = load_published_pas(cur, season, kind_code, game_sno)
            events = load_livelog(cur, season, kind_code, game_sno)
            names = player_names(events)
            if pa_rows:
                members = load_pa_members(cur, season, kind_code, game_sno)
                for row in pa_rows:
                    row["member_event_nos"] = members.get(row["pa_index"], [])
                facts = delta_re24(pa_rows, events, re_map)
                swings, wp_reason = _load_wp_swings(
                    facts, season=season, kind_code=kind_code,
                    home_score=game.get("home_score"), away_score=game.get("away_score"))
                return _assemble(
                    season=season, kind_code=kind_code, game_sno=game_sno,
                    source="authoritative", render_state=STATE_AUTHORITATIVE, reason=None,
                    game=game, facts=facts, decisions=_db_decisions(game, names),
                    inning_runs=load_inning_runs(cur, season, kind_code, game_sno),
                    wp_by_index=swings, wp_reason=wp_reason)
            # 階 7：有 build 但待對帳 → 走簡版並揭露（不可靜默當成「沒有打席」）
            if has_reconciliation_build(cur, season, kind_code, game_sno):
                return _assemble(
                    season=season, kind_code=kind_code, game_sno=game_sno,
                    source="authoritative", render_state=STATE_RECONCILING,
                    reason="pa_build_reconciliation_required", game=game, facts=[],
                    decisions=_db_decisions(game, names),
                    inning_runs=load_inning_runs(cur, season, kind_code, game_sno),
                    simple=True)

        inning_runs_db = load_inning_runs(cur, season, kind_code, game_sno)

    # 階 2／3：後備源（snapshot）。**頁面層完賽觸發＝phase=final**，
    # 嚴禁以時間推斷硬切完賽（present_status 對完賽零鑑別力）。
    if snapshot is not None and snapshot.get("phase") == "final":
        events = snapshot_events(snapshot)
        pa_rows, pas = pa_rows_from_snapshot(season, kind_code, game_sno, events)
        ok, reason = mini_reconcile(snapshot, events, pas)
        snap_game = dict(game)
        snap_game["home_score"] = (snapshot.get("home") or {}).get("score", game.get("home_score"))
        snap_game["away_score"] = (snapshot.get("away") or {}).get("score", game.get("away_score"))
        inning_runs = snapshot_inning_runs(snapshot) or inning_runs_db
        if ok:
            facts = delta_re24(pa_rows, events, re_map)
            swings, wp_reason = _load_wp_swings(
                facts, season=season, kind_code=kind_code,
                home_score=snap_game.get("home_score"), away_score=snap_game.get("away_score"))
            return _assemble(
                season=season, kind_code=kind_code, game_sno=game_sno,
                source="provisional", render_state=STATE_PROVISIONAL, reason=None,
                game=snap_game, facts=facts, decisions=snapshot_decisions(snapshot),
                inning_runs=inning_runs, wp_by_index=swings, wp_reason=wp_reason)
        return _assemble(
            season=season, kind_code=kind_code, game_sno=game_sno,
            source="provisional", render_state=STATE_PROVISIONAL_SIMPLE, reason=reason,
            game=snap_game, facts=[], decisions=snapshot_decisions(snapshot),
            inning_runs=inning_runs, simple=True)

    # 階 4：有 snapshot 但 phase 仍非 final → **不硬切完賽**，停在賽中態等權威源。
    # 但事實流本身照給（live 逐打席換底的消費者需要 canonical 打席邊界）：
    # 進行中的最後一個打席不套「半局末 RE=0」，標 game_in_progress。
    if snapshot is not None:
        payload = _empty(
            season, kind_code, game_sno,
            STATE_LIVE if snapshot.get("freshness") != "stale" else STATE_STALE_LIVE,
            f"phase_{snapshot.get('phase')}", game)
        events = snapshot_events(snapshot)
        if events:
            pa_rows, _ = pa_rows_from_snapshot(season, kind_code, game_sno, events)
            payload["source"] = "provisional"
            payload["plate_appearances"] = delta_re24(
                pa_rows, events, re_map, game_completed=False)
            payload["half_innings"] = half_inning_breakdown(payload["plate_appearances"])
        return payload
    # 階 5：無即時源，權威源也未到
    return _empty(season, kind_code, game_sno, STATE_PENDING,
                  "awaiting_official_data", game)


def cache_directive(payload: dict, *, today: date | None = None) -> str:
    """設計稿 §8 快取策略 → ``Cache-Control`` 值。

    暫定源短窗（勝敗投可能在當晚補齊）；權威源當季 1 小時（讓 PA build 修正生效）；
    權威源歷史場次不可變 → 長快取。
    """
    if payload.get("source") != "authoritative":
        return "public, s-maxage=60, stale-while-revalidate=60"
    game_date = payload.get("game_date")
    season = payload.get("season")
    current_year = (today or date.today()).year
    if isinstance(season, int) and season < current_year and game_date is not None:
        return "public, s-maxage=31536000, immutable"
    return "public, s-maxage=3600, stale-while-revalidate=600"
