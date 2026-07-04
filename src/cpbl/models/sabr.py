"""Sabermetrics 打底：守備局數（fielding_innings）+ 得分期望矩陣（run_expectancy）。

資料源＝game_livelog（2018+）。皆為推算（官方無守備局數/RE 資料），方法：

守備局數
  - 投手/捕手：每事件都有 pitcher_acnt/catcher_acnt → 逐出局精算。
  - 其他七守位：兩類訊號重建「守位 × 時間」分段——
    (a) 觀測：打者打席的 defend_station_code（該員此刻的守位登錄）；
    (b) 更換事件：content 結構化文字（更換守備：名-三壘手=>二壘手 / 更換選手：
        捕手-A=>捕手-B / 更換代打…），含精確時點與 from/to 守位。
    分段規則：球員的守位在相鄰兩個「自身異動事件」之間恆定，觀測值 pin 該段守位、
    異動事件的 from/to 分別界定前後段（可回填開賽至首次觀測前的守位）。
  - 出局計時：掃事件流，半局內 out_cnt 遞增 + 半局結束補滿 3 出局；每個守備出局
    記給當下在位者。DH/PH/PR 不計守備。

RE 矩陣
  - 每打席首事件的 (壘位, 出局數) 為狀態；該半局終了得分 − 當下得分 = 剩餘得分。
  - 排除未打滿三出局的半局（再見安打/裁定截斷會系統性低估）。
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict

from cpbl.db import conn

log = logging.getLogger("cpbl.sabr")

# 更換事件守位中文 → 代碼（livelog defend_station_code 同一套代碼）
POS_ZH = {"投手": "P", "捕手": "C", "一壘手": "1B", "二壘手": "2B", "三壘手": "3B",
          "游擊手": "SS", "左外野手": "LF", "中外野手": "CF", "右外野手": "RF",
          "指定打擊": "DH"}
FIELD_POS = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"}  # 投捕另計/野手七位＋捕手
_CHG = re.compile(r"更換(守備|選手|代打|代跑|投手)：([^=\s]+?)(?:-([^=\s]*?))?=>(?:([^-\s]+?)-)?([^。\s]+)")


def _rows(cur) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def _load_game(cur, year: int, kind: str, sno: int) -> list[dict]:
    cur.execute(
        "SELECT main_event_no, inning_seq, visiting_home_type, batting_order, out_cnt, "
        "is_change_player, content, hitter_acnt, hitter_name, defend_station_code, "
        "pitcher_acnt, catcher_acnt, first_base, second_base, third_base, "
        "visiting_score, home_score FROM cpbl.game_livelog "
        "WHERE year=%s AND kind_code=%s AND game_sno=%s", (year, kind, sno))
    return sorted(_rows(cur), key=lambda r: int(r["main_event_no"]))


def _name_map(cur, year: int, kind: str, sno: int) -> dict[str, str]:
    """該場 名→acnt（打者+投手 box；重名以先出現者，聯盟內單場重名極罕見）。"""
    cur.execute(
        "SELECT hitter_name, hitter_acnt FROM cpbl.batting_gamelog "
        "WHERE year=%s AND kind_code=%s AND game_sno=%s "
        "UNION SELECT pitcher_name, pitcher_acnt FROM cpbl.pitching_gamelog "
        "WHERE year=%s AND kind_code=%s AND game_sno=%s",
        (year, kind, sno, year, kind, sno))
    out: dict[str, str] = {}
    for nm, ac in cur.fetchall():
        if nm and ac:
            out.setdefault(nm.strip(), ac)
    return out


def _timeline(events: list[dict], names: dict[str, str]) -> dict[str, dict[str, list]]:
    """重建兩隊守備 (player, pos) 分段。回 {side: {player: [(t_from, t_to, pos)]}}。

    side='1' 客隊守備（主隊打擊時）/'2' 主隊守備。t 為事件索引。
    """
    n = len(events)
    # 每球員的訊號：(t, kind, pos_from, pos_to)；觀測 kind='obs' 只有 pos_to
    sig: dict[tuple[str, str], list] = defaultdict(list)   # (side, player) -> signals
    for t, e in enumerate(events):
        bat_side = str(e["visiting_home_type"])            # 打擊方
        def_side = "2" if bat_side == "1" else "1"          # 守備方（相對打擊方）
        # (a) 打者守位觀測：屬於打擊方球員，作用於其守備時段
        pos = (e.get("defend_station_code") or "").strip()
        if e.get("hitter_acnt") and pos in FIELD_POS:
            sig[(bat_side, e["hitter_acnt"])].append((t, "obs", None, pos))
        # (b) 更換事件：作用於當下守備方（代打/代跑作用於打擊方，先記 PH 換人）
        if e.get("is_change_player") and e.get("content"):
            for kind_zh, a_name, a_pos, _b_pos, b_tail in _CHG.findall(e["content"]):
                # 格式歧異整理：更換守備：A-三壘手=>二壘手（同員換位）
                #              更換守備：A-=>三壘手（入場/由 PH 補位）
                #              更換選手：捕手-A=>捕手-B（B 接替 A 守位）
                #              更換代打/代跑：A=>B（B 上場打擊/跑壘，守位待後續事件）
                if kind_zh == "守備":
                    ac = names.get(a_name.strip())
                    to = POS_ZH.get(b_tail.strip("。 "), None)
                    frm = POS_ZH.get((a_pos or "").strip(), None)
                    if ac and to in FIELD_POS | {"DH"}:
                        sig[(def_side, ac)].append((t, "chg", frm, to))
                elif kind_zh == "選手":
                    # a_name=守位、a_pos=舊員；b_pos_pre=守位、b_tail=新員
                    pos_c = POS_ZH.get(a_name.strip())
                    old_ac = names.get((a_pos or "").strip())
                    new_ac = names.get(b_tail.strip("。 "))
                    if pos_c in FIELD_POS:
                        if old_ac:
                            sig[(def_side, old_ac)].append((t, "chg", pos_c, None))
                        if new_ac:
                            sig[(def_side, new_ac)].append((t, "chg", None, pos_c))
                # 代打/代跑：新員接手打序，守位交由之後的守備觀測/更換事件界定
    # 分段：相鄰異動事件切段，段內守位 = 觀測值或異動 from/to 推得
    out: dict[str, dict[str, list]] = {"1": defaultdict(list), "2": defaultdict(list)}
    for (side, player), ss in sig.items():
        ss.sort(key=lambda x: x[0])
        cuts = [s for s in ss if s[1] == "chg"]
        obs = [s for s in ss if s[1] == "obs"]
        bounds = [0] + [c[0] for c in cuts] + [n]
        for i in range(len(bounds) - 1):
            lo, hi = bounds[i], bounds[i + 1]
            pos = None
            if i > 0 and cuts[i - 1][3]:            # 段首異動的 to
                pos = cuts[i - 1][3]
            if pos is None:                          # 段內觀測
                for o in obs:
                    if lo <= o[0] < hi:
                        pos = o[3]
                        break
            if pos is None and i < len(cuts) and cuts[i][2]:  # 段尾異動的 from 回填
                pos = cuts[i][2]
            if pos in FIELD_POS:
                out[side][player].append((lo, hi, pos))
    return out


def _defensive_outs(events: list[dict]) -> list[tuple[int, str]]:
    """回傳 [(事件索引, 守備方)] 的逐出局時點（半局內 out_cnt 遞增 + 半局收尾補滿）。"""
    outs: list[tuple[int, str]] = []
    cur_half: tuple | None = None
    cur_outs = 0
    last_t = 0
    for t, e in enumerate(events):
        half = (e["inning_seq"], str(e["visiting_home_type"]))
        def_side = "2" if half[1] == "1" else "1"
        if cur_half is not None and half != cur_half:
            prev_def = "2" if cur_half[1] == "1" else "1"
            for _ in range(max(0, 3 - cur_outs)):   # 半局結束補滿三出局
                outs.append((last_t, prev_def))
            cur_outs = 0
        cur_half = half
        oc = e.get("out_cnt") or 0
        if oc > cur_outs:
            outs.extend((t, def_side) for _ in range(oc - cur_outs))
            cur_outs = oc
        last_t = t
    # 末半局：主隊勝的再見局可能未滿三出局，不補（避免灌水）——投捕逐事件不受影響
    return outs


def build_fielding_innings(year: int, kind: str = "A") -> dict:
    """重建整季守備局數 → UPSERT cpbl.fielding_innings。回統計摘要。"""
    acc: dict[tuple[str, str], int] = defaultdict(int)      # (player,pos) -> outs
    gset: dict[tuple[str, str], set] = defaultdict(set)     # (player,pos) -> games
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT DISTINCT game_sno FROM cpbl.game_livelog "
                    "WHERE year=%s AND kind_code=%s ORDER BY game_sno", (year, kind))
        snos = [r[0] for r in cur.fetchall()]
        for sno in snos:
            events = _load_game(cur, year, kind, sno)
            if not events:
                continue
            names = _name_map(cur, year, kind, sno)
            tl = _timeline(events, names)
            outs = _defensive_outs(events)
            # 投捕：逐出局取當下事件的 pitcher/catcher_acnt
            for t, side in outs:
                e = events[min(t, len(events) - 1)]
                if str(e["visiting_home_type"]) != side:  # 該出局屬守備方=side
                    if e.get("pitcher_acnt"):
                        acc[(e["pitcher_acnt"], "P")] += 1
                        gset[(e["pitcher_acnt"], "P")].add(sno)
                    if e.get("catcher_acnt"):
                        acc[(e["catcher_acnt"], "C")] += 1
                        gset[(e["catcher_acnt"], "C")].add(sno)
                # 野手：時間線分段內
                for player, segs in tl[side].items():
                    for lo, hi, pos in segs:
                        if lo <= t < hi and pos != "C":
                            acc[(player, pos)] += 1
                            gset[(player, pos)].add(sno)
                            break
    with conn() as c:
        c.execute("DELETE FROM cpbl.fielding_innings WHERE year=%s AND kind_code=%s",
                  (year, kind))
        c.cursor().executemany(
            "INSERT INTO cpbl.fielding_innings (year, kind_code, player_id, pos, outs, games) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            [(year, kind, p, pos, o, len(gset[(p, pos)]))
             for (p, pos), o in acc.items()])
    total = sum(acc.values())
    log.info("fielding_innings %s/%s：%d 場，%d 列，共 %d 出局",
             year, kind, len(snos), len(acc), total)
    return {"games": len(snos), "rows": len(acc), "outs": total}


def build_run_expectancy(from_year: int, to_year: int, kind: str = "A") -> dict:
    """建 RE 矩陣（排除未滿三出局的半局）→ UPSERT cpbl.run_expectancy。"""
    span = f"{from_year}-{to_year}"
    stats: dict[tuple[str, int], list[int]] = defaultdict(lambda: [0, 0])  # (bases,outs)->[sum,cnt]
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT DISTINCT year, game_sno FROM cpbl.game_livelog "
                    "WHERE year BETWEEN %s AND %s AND kind_code=%s", (from_year, to_year, kind))
        games = cur.fetchall()
        for gy, sno in games:
            events = _load_game(cur, gy, kind, sno)
            # 依半局分組（保序）
            halves: dict[tuple, list[dict]] = defaultdict(list)
            order: list[tuple] = []
            for e in events:
                k = (e["inning_seq"], str(e["visiting_home_type"]))
                if k not in halves:
                    order.append(k)
                halves[k].append(e)
            for (_inn, vht) in order[:-1]:  # 只有最後一個半局可能被截斷（再見/裁定），
                evs = halves[(_inn, vht)]   # 其餘必打滿三出局——用 max_out 判會漏掉雙殺
                                            # 收尾的快局，系統性高估 RE
                score_key = "visiting_score" if vht == "1" else "home_score"
                end_score = max((e.get(score_key) or 0) for e in evs)
                # 每打席首事件 = 狀態快照
                seen: set = set()
                for e in evs:
                    pa_key = (e.get("batting_order"), e.get("hitter_acnt"))
                    if pa_key in seen:
                        continue
                    seen.add(pa_key)
                    bases = (("1" if e.get("first_base") else "_")
                             + ("2" if e.get("second_base") else "_")
                             + ("3" if e.get("third_base") else "_"))
                    outs = min(int(e.get("out_cnt") or 0), 2)
                    rest = end_score - (e.get(score_key) or 0)
                    if rest < 0:
                        continue
                    s = stats[(bases, outs)]
                    s[0] += rest
                    s[1] += 1
    with conn() as c:
        c.cursor().executemany(
            "INSERT INTO cpbl.run_expectancy (span, kind_code, bases, outs, re, samples) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (span, kind_code, bases, outs) DO UPDATE SET "
            "re=EXCLUDED.re, samples=EXCLUDED.samples",
            [(span, kind, b, o, round(s / n, 4), n)
             for (b, o), (s, n) in stats.items() if n >= 10])
    log.info("run_expectancy %s/%s：%d 場，%d 狀態", span, kind, len(games), len(stats))
    return {"games": len(games), "states": len(stats)}
