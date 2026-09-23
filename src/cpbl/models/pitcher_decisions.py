"""逐場投手角色判定：W/L 官方、HLD 官方（relief_point）、SV 官方優先、無官方才依規則 9.19 推算。

SV 來源（需求方 2026-09-23 裁定「救援成功也改用官方」，見 `official_saves`）：
  1. `pitching_game_flags.is_save_ok`（stats.cpbl 單場 API，2026 起）；
  2. `games.closer_id`（官網逐場欄位）；
  3. 兩者皆無 ⇒ 照規則 9.19（docs/reference/棒球規則.txt p.182）四要件自 livelog 重建：
  (a) 勝隊最後一任投手；(b) 非勝利投手；(c) 至少 1/3 局；(d) 下列其一：
    (1) 登板時領先 ≤3 分且至少投滿 1 局；
    (2) 登板時追平分在壘上/打擊區/準備區（lead ≤ 壘上跑者數 + 2）；
    (3) 至少投 3 局。
登板狀態取該投手於 livelog 的第一筆事件：分數只在得分事件當下更新、
壘包為該打席進行中狀態（含繼承跑者），故首筆事件即登板時的 lead/跑者。
⚠️ 已知誤判：首筆事件本身就是得分事件時，lead 會少算那一分（2023-A-189 登板領先 4 分被讀成
3 分 ⇒ 誤記救援；官方季累計該投手 2 次、推算 3 次）。有官方來源的場次不受影響。

對官方季累計（逐投手）的驗證，2026-09-23：
  - is_save_ok：2026 一軍 177 次、逐投手全對；
  - closer_id：只會漏、不會多——2024 漏 5、2025 漏 3、2026 漏 3（A-99／229／313），
    2018–2026 從未出現「closer_id 有值但與真實救援者不同」；
  - 推算：2018–2025 一軍只錯 2023-A-189 一場（多 1）；2026 逐場與 is_save_ok 全同（A 330 場、D 232 場）。
"""

from __future__ import annotations

from cpbl.db import conn


def _entry_states(livelog: list[dict]) -> dict[str, dict]:
    """{pitcher_acnt: {order, lead_for(主客通用前置量), runners}}——以首筆事件重建登板狀態。

    livelog 需含 main_event_no/visiting_home_type/pitcher_acnt/
    first_base/second_base/third_base/visiting_score/home_score，任意順序。
    """
    rows = sorted(livelog, key=lambda r: int(r["main_event_no"]))
    out: dict[str, dict] = {}
    for i, r in enumerate(rows):
        p = r.get("pitcher_acnt")
        if not p or p in out:
            continue
        vs, hs = int(r["visiting_score"] or 0), int(r["home_score"] or 0)
        # 投手所屬隊＝守備方：vht='1'（客隊打擊）時投手是主隊
        is_home_pitcher = str(r["visiting_home_type"]) == "1"
        lead = (hs - vs) if is_home_pitcher else (vs - hs)
        runners = sum(1 for b in ("first_base", "second_base", "third_base") if r.get(b))
        out[p] = {"order": i, "home": is_home_pitcher, "lead": lead, "runners": runners}
    return out


def decide(livelog: list[dict], pitching: list[dict],
           home_score: int, away_score: int,
           saves: set[str] | None = None) -> dict[str, str]:
    """回傳 {pitcher_acnt: 'W'|'L'|'SV'|'HLD'}。和局或資料不足時盡量降級（W/L/HLD 仍可標）。

    saves：官方救援成功投手（`official_saves` 的回傳）。None＝該場沒有官方來源，SV 才依規則
    9.19 推算；空集合＝官方判定本場無人救援成功，⛔ 不得再推算（推算會誤記，見模組說明）。
    """
    out: dict[str, str] = {}
    for r in pitching:
        acnt = r["pitcher_acnt"]
        if r.get("game_result") == "勝":
            out[acnt] = "W"
        elif r.get("game_result") == "敗":
            out[acnt] = "L"
        elif r.get("relief_point"):
            out[acnt] = "HLD"
    if saves is None:
        saves = _inferred_saves(livelog, pitching, home_score, away_score, out)
    for acnt in saves:
        # 規則 9.19(b) 勝投不得記救援；官方資料（2026 A/D 全季）無此組合，故只防呆不並存。
        if out.get(acnt) not in ("W", "L"):
            out[acnt] = "SV"
    return out


def _inferred_saves(livelog: list[dict], pitching: list[dict], home_score: int,
                    away_score: int, base: dict[str, str]) -> set[str]:
    """規則 9.19 推算的救援成功投手（0 或 1 人）。base＝已標好的 W/L/HLD。"""
    if home_score == away_score or not livelog:
        return set()
    win_home = home_score > away_score
    entry = _entry_states(livelog)
    # 勝隊最後一任 = 勝隊投手中登板順序最大者
    winners = [r for r in pitching
               if str(r["visiting_home_type"]) == ("2" if win_home else "1")
               and r["pitcher_acnt"] in entry]
    if len(winners) < 2:  # 先發完投 → 無救援
        return set()
    last = max(winners, key=lambda r: entry[r["pitcher_acnt"]]["order"])
    acnt = last["pitcher_acnt"]
    if base.get(acnt) in ("W", "L"):
        return set()
    thirds = (last.get("inning_pitched_cnt") or 0) * 3 + (last.get("inning_pitched_div3") or 0)
    st = entry[acnt]
    if thirds >= 1 and (
        (st["lead"] <= 3 and 0 < st["lead"] and thirds >= 3)   # (d1) 領先≤3 且投滿 1 局
        or (0 < st["lead"] <= st["runners"] + 2)               # (d2) 追平分已上壘/在打擊區/準備區
        or thirds >= 9                                          # (d3) 投滿 3 局
    ):
        return {acnt}
    return set()


def official_saves(flags: list[tuple[str, bool | None]],
                   closer_id: str | None) -> set[str] | None:
    """官方救援成功投手（純函式）。flags＝該場 `[(pitcher_acnt, is_save_ok), ...]`。

    順序：is_save_ok 有人 → 那些人；否則 closer_id 有值 → 它；否則該場有旗標列 → 空集合
    （官方判定無人救援成功）；兩個官方來源都沒有 → None，交給呼叫端推算。
    ⚠️ closer_id 為空 ⛔ 不代表無人救援：它只會漏不會錯（模組說明的驗證），故空值不能當「官方說沒有」。
    「有旗標」與 `blown_for_game` 同一判準：該場有任何列即算。
    """
    ok = {acnt for acnt, flag in flags if flag is True}
    if ok:
        return ok
    if closer_id:
        return {closer_id}
    return set() if flags else None


def official_closer_sql(g: str) -> str:
    """SQL 運算式：games 別名 `g` 那場的官方救援成功投手 acnt，無則 NULL。

    與 `official_saves` 同一順序的 SQL 版（is_save_ok → closer_id），給只能在 SQL 裡數救援的
    消費端（splits、隊史彙總、球員生涯、單場頁累計次數與救援欄、戰報）。⛔ 新消費端不得直接讀
    `games.closer_id`：它 2024–2026 共漏 11 場（模組說明）。SQL 版沒有推算這一層，兩個官方
    來源都沒有時就是 NULL（與改版前只讀 closer_id 時相同）。規則上一場至多一位救援成功，
    `min()` 只是讓多列時仍有確定結果（官方資料至今無多列）。
    """
    return (f"coalesce((SELECT min(sgf.pitcher_acnt) FROM cpbl.pitching_game_flags sgf "
            f"WHERE sgf.year={g}.year AND sgf.kind_code={g}.kind_code "
            f"AND sgf.game_sno={g}.game_sno AND sgf.is_save_ok), {g}.closer_id)")


def _save_situation(lead: int, runners: int) -> bool:
    """登板時是否為救援/中繼情境：領先且（領先≤3 或追平分在壘上/打擊區/準備區）。"""
    return 0 < lead and (lead <= 3 or lead <= runners + 3)


def blown(livelog: list[dict], pitching: list[dict]) -> dict[str, str]:
    """中繼/救援失敗 [Blown Hold/Save]（推算）：登板時處救援情境、
    在位期間把領先葬送（該隊領先一度 ≤0＝被追平/反超）者。回 {acnt: 'BS'|'BH'}。

    BS(救援失敗)＝該場最後一任投手（有救援資格者搞砸）；BH(中繼失敗)＝中途接手者。

    ⚠️ 有官方逐場旗標的場次**不再使用本推算**（需求方 2026-09-23 裁定，見 `blown_for_game`）：
    官方判定與本推算不同——2026-A-341 官方給 3 位救援失敗，其中 2 位是中繼角色，本函式只會把
    BS 記給最後一任。本函式保留給沒有官方旗標的場次（季後賽、凍結場、往年）。
    領先歸屬：投手所屬隊＝守備方（vht='1' 客隊打擊時投手為主隊）。
    """
    if not livelog:
        return {}
    rows = sorted(livelog, key=lambda r: int(r["main_event_no"]))
    stint: dict[str, dict] = {}
    order = 0
    last_pitcher: str | None = None
    for e in rows:
        p = e.get("pitcher_acnt")
        if not p:
            continue
        last_pitcher = p
        is_home = str(e["visiting_home_type"]) == "1"
        vs, hs = int(e["visiting_score"] or 0), int(e["home_score"] or 0)
        lead = (hs - vs) if is_home else (vs - hs)
        if p not in stint:
            runners = sum(1 for b in ("first_base", "second_base", "third_base") if e.get(b))
            stint[p] = {"order": order, "entry_lead": lead, "entry_runners": runners,
                        "min_lead": lead}
            order += 1
        else:
            stint[p]["min_lead"] = min(stint[p]["min_lead"], lead)
    result_by: dict[str, str] = {r["pitcher_acnt"]: (r.get("game_result") or "")
                                 for r in pitching}
    out: dict[str, str] = {}
    for acnt, s in stint.items():
        if result_by.get(acnt) == "勝":     # 勝投＝球隊反超救回，不算搞砸
            continue
        if _save_situation(s["entry_lead"], s["entry_runners"]) and s["min_lead"] <= 0:
            out[acnt] = "BS" if acnt == last_pitcher else "BH"
    return out


def game_decisions(year: int, kind_code: str, game_sno: int) -> dict[str, str]:
    """自 DB 撈單場資料並判定（API 用）。SV 與救援失敗皆官方優先（`official_saves`／`blown_for_game`）。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT home_score, away_score, closer_id FROM cpbl.games "
            "WHERE year=%s AND kind_code=%s AND game_sno=%s", (year, kind_code, game_sno))
        g = cur.fetchone()
        if not g or g[0] is None:
            return {}
        cur.execute(
            "SELECT main_event_no, visiting_home_type, pitcher_acnt, first_base, second_base, "
            "third_base, visiting_score, home_score FROM cpbl.game_livelog "
            "WHERE year=%s AND kind_code=%s AND game_sno=%s", (year, kind_code, game_sno))
        cols = [d[0] for d in cur.description]
        livelog = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
        cur.execute(
            "SELECT pitcher_acnt, visiting_home_type, game_result, relief_point, "
            "inning_pitched_cnt, inning_pitched_div3 FROM cpbl.pitching_gamelog "
            "WHERE year=%s AND kind_code=%s AND game_sno=%s", (year, kind_code, game_sno))
        cols = [d[0] for d in cur.description]
        pitching = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
        cur.execute(
            "SELECT pitcher_acnt, is_save_ok, is_save_fail FROM cpbl.pitching_game_flags "
            "WHERE year=%s AND kind_code=%s AND game_sno=%s", (year, kind_code, game_sno))
        flags = cur.fetchall()
    saves = official_saves([(a, ok) for a, ok, _ in flags], g[2])
    dec = decide(livelog, pitching, g[0], g[1], saves=saves)
    return merge_blown(dec, blown_for_game([(a, fail) for a, _, fail in flags], livelog, pitching))


def official_blown(flags: list[tuple[str, bool | None]]) -> dict[str, str]:
    """官方逐場旗標 `[(pitcher_acnt, is_save_fail), ...]` → `{acnt: 'BS'}`（純函式）。

    官方沒有「中繼失敗」分類：救援情境中把領先弄丟的後援一律記救援失敗，不分登板順序。
    故有官方旗標的場次只標 BS、不標 BH——同一件事不能同時被官方記 BS、又被推算記 BH。
    """
    return {acnt: "BS" for acnt, fail in flags if fail is True}


def blown_for_game(flags: list[tuple[str, bool | None]], livelog: list[dict],
                   pitching: list[dict]) -> dict[str, str]:
    """救援／中繼失敗的單一入口：該場有官方旗標就用官方，沒有才推算（需求方 2026-09-23 裁定）。

    「有官方旗標」以該場在 `pitching_game_flags` 有任何列為準（整場都是 0 也算有，代表官方
    判定本場無人救援失敗）。沒有列的場次＝季後賽、凍結場、往年等，退回 `blown()` 推算。
    單場頁（`game_decisions`）與 splits（`splits_calc._blown_saves`）共用本函式，兩處不得各自判定。
    """
    return official_blown(flags) if flags else blown(livelog, pitching)


def merge_blown(dec: dict[str, str], bl: dict[str, str]) -> dict[str, str]:
    """救援／中繼失敗併入勝負標記：與 W／L 並存（'W·BS'、'L·BS'），與 SV／HLD 互斥。

    ⚠️ 原本只有 L 會並存，W 會被整個蓋成 'BS'——搞砸領先後球隊再超前拿下勝投的投手，勝投
    因此消失。官方旗標下這種情形常見，故一併修正。前端以「·」切開逐個顯示（box-tabs.tsx）。
    """
    out = dict(dec)
    for acnt, tag in bl.items():
        base = out.get(acnt)
        out[acnt] = f"{base}·{tag}" if base in ("W", "L") else tag
    return out
