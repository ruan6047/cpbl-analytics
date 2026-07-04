"""逐場投手角色判定：W/L 官方、HLD 官方（relief_point）、SV 依棒球規則 9.19 推算。

官方逐場資料沒有 save 旗標（pitching_gamelog.game_result 僅勝/敗/和），
故 SV 照規則 9.19（docs/reference/棒球規則.txt p.182）四要件自 livelog 重建：
  (a) 勝隊最後一任投手；(b) 非勝利投手；(c) 至少 1/3 局；(d) 下列其一：
    (1) 登板時領先 ≤3 分且至少投滿 1 局；
    (2) 登板時追平分在壘上/打擊區/準備區（lead ≤ 壘上跑者數 + 2）；
    (3) 至少投 3 局。
登板狀態取該投手於 livelog 的第一筆事件：分數只在得分事件當下更新、
壘包為該打席進行中狀態（含繼承跑者），故首筆事件即登板時的 lead/跑者。

2026 全季驗證：SV 對官方季累計 100%（見驗證紀錄）；HLD 直接用官方
relief_point。前端顯示 SV 仍標「推算」以示與官方逐場欄位的差異。
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
           home_score: int, away_score: int) -> dict[str, str]:
    """回傳 {pitcher_acnt: 'W'|'L'|'SV'|'HLD'}。和局或資料不足時盡量降級（W/L/HLD 仍可標）。"""
    out: dict[str, str] = {}
    for r in pitching:
        acnt = r["pitcher_acnt"]
        if r.get("game_result") == "勝":
            out[acnt] = "W"
        elif r.get("game_result") == "敗":
            out[acnt] = "L"
        elif r.get("relief_point"):
            out[acnt] = "HLD"
    if home_score == away_score or not livelog:
        return out
    win_home = home_score > away_score
    entry = _entry_states(livelog)
    # 勝隊最後一任 = 勝隊投手中登板順序最大者
    winners = [r for r in pitching
               if str(r["visiting_home_type"]) == ("2" if win_home else "1")
               and r["pitcher_acnt"] in entry]
    if len(winners) < 2:  # 先發完投 → 無救援
        return out
    last = max(winners, key=lambda r: entry[r["pitcher_acnt"]]["order"])
    acnt = last["pitcher_acnt"]
    if out.get(acnt) in ("W", "L"):
        return out
    thirds = (last.get("inning_pitched_cnt") or 0) * 3 + (last.get("inning_pitched_div3") or 0)
    st = entry[acnt]
    if thirds >= 1 and (
        (st["lead"] <= 3 and 0 < st["lead"] and thirds >= 3)   # (d1) 領先≤3 且投滿 1 局
        or (0 < st["lead"] <= st["runners"] + 2)               # (d2) 追平分已上壘/在打擊區/準備區
        or thirds >= 9                                          # (d3) 投滿 3 局
    ):
        out[acnt] = "SV"
    return out


def game_decisions(year: int, kind_code: str, game_sno: int) -> dict[str, str]:
    """自 DB 撈單場資料並判定（API 用）。"""
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT home_score, away_score FROM cpbl.games "
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
    return decide(livelog, pitching, g[0], g[1])
