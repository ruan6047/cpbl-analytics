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
        "is_change_player, content, action_name, hitter_acnt, hitter_name, "
        "defend_station_code, pitcher_acnt, catcher_acnt, first_base, second_base, third_base, "
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


_TRAITS_SQL = """
WITH ev AS (
  SELECT game_sno, main_event_no::bigint AS evt, hitter_acnt, pitcher_acnt,
         pitch_cnt, strike_cnt, batting_action_name,
         CASE WHEN hitter_acnt IS DISTINCT FROM
                   lag(hitter_acnt) OVER (PARTITION BY game_sno ORDER BY main_event_no::bigint)
              THEN 1 ELSE 0 END AS brk
  FROM cpbl.game_livelog
  WHERE year = %(year)s AND kind_code = %(kind)s
    AND hitter_acnt IS NOT NULL AND pitch_cnt IS NOT NULL
), pa AS (
  SELECT game_sno, hitter_acnt,
         sum(brk) OVER (PARTITION BY game_sno ORDER BY evt) AS pa_id,
         evt, pitch_cnt, strike_cnt, batting_action_name, pitcher_acnt
  FROM ev
), agg AS (
  SELECT game_sno, pa_id, min(hitter_acnt) AS hitter,
         (array_agg(pitcher_acnt ORDER BY evt DESC))[1] AS pitcher,
         max(pitch_cnt) - min(pitch_cnt) + 1 AS pitches,
         max(strike_cnt) AS max_strikes,
         (array_agg(batting_action_name ORDER BY evt DESC))[1] AS act
  FROM pa GROUP BY game_sno, pa_id
)
SELECT {key} AS player_id, count(*) AS pa,
       round(avg(pitches) FILTER (WHERE pitches BETWEEN 1 AND 20)::numeric, 2) AS p_pa,
       count(*) FILTER (WHERE act LIKE '%%滾' OR act = '雙殺') AS go,
       count(*) FILTER (WHERE act LIKE '%%飛' AND act NOT LIKE '界%%') AS fo,
       count(*) FILTER (WHERE left(act, 1) IN ('三', '游', '左')
                        AND (act LIKE '%%滾' OR act LIKE '%%飛' OR act LIKE '%%安')) AS dir_left,
       count(*) FILTER (WHERE left(act, 1) IN ('中', '投', '捕')
                        AND (act LIKE '%%滾' OR act LIKE '%%飛' OR act LIKE '%%安')) AS dir_center,
       count(*) FILTER (WHERE left(act, 1) IN ('一', '二', '右')
                        AND (act LIKE '%%滾' OR act LIKE '%%飛' OR act LIKE '%%安')) AS dir_right,
       count(*) FILTER (WHERE max_strikes >= 2) AS two_strike_pa,
       count(*) FILTER (WHERE max_strikes >= 2 AND act = '三振') AS two_strike_k,
       count(*) FILTER (WHERE max_strikes >= 2 AND (act LIKE '%%安' OR act = '全打')) AS two_strike_hit
FROM agg GROUP BY {key}
"""


def build_traits(year: int, kind: str = "A") -> dict:
    """重建打者/投手特性表（P/PA、滾飛、方向、兩好球後）。"""
    with conn() as c:
        c.execute("DELETE FROM cpbl.batter_traits WHERE year=%s AND kind_code=%s", (year, kind))
        c.execute("DELETE FROM cpbl.pitcher_traits WHERE year=%s AND kind_code=%s", (year, kind))
        cur = c.cursor()
        cur.execute(
            f"INSERT INTO cpbl.batter_traits (player_id, pa, p_pa, go, fo, dir_left, dir_center, "  # noqa: S608
            f"dir_right, two_strike_pa, two_strike_k, two_strike_hit, year, kind_code) "
            f"SELECT *, %(year)s, %(kind)s FROM ({_TRAITS_SQL.format(key='hitter')}) t",
            {"year": year, "kind": kind})
        nb = cur.rowcount
        cur.execute(
            f"INSERT INTO cpbl.pitcher_traits (player_id, bf, p_pa, go, fo, two_strike_pa, "  # noqa: S608
            f"two_strike_k, year, kind_code) "
            f"SELECT player_id, pa, p_pa, go, fo, two_strike_pa, two_strike_k, %(year)s, %(kind)s "
            f"FROM ({_TRAITS_SQL.format(key='pitcher')}) t",
            {"year": year, "kind": kind})
        np_ = cur.rowcount
    log.info("traits %s/%s：打者 %d / 投手 %d", year, kind, nb, np_)
    return {"batters": nb, "pitchers": np_}


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
            # 快照時點修正（2026-07-07，REBAS 對照抓出）：比分欄=事件後、壘位/out_cnt=事件前，
            # 且更換事件列的 out_cnt 是陳舊值 →
            # (1) 打席首事件只取「非更換且有打者」列（局初換投列曾把空壘0出局誤標成2出局）；
            # (2) 打席起始分用前一列的事件後分（單事件打席的比分欄已含自身得分，直接用會漏計）。
            pv, ph = 0, 0
            for e in events:
                e["_pre_vs"], e["_pre_hs"] = pv, ph
                pv = e["visiting_score"] if e.get("visiting_score") is not None else pv
                ph = e["home_score"] if e.get("home_score") is not None else ph
                e["_post_vs"], e["_post_hs"] = pv, ph
            # 依半局分組（保序）
            halves: dict[tuple, list[dict]] = defaultdict(list)
            order: list[tuple] = []
            for e in events:
                k = (e["inning_seq"], str(e["visiting_home_type"]))
                if k not in halves:
                    order.append(k)
                halves[k].append(e)
            for (_inn, vht) in order[:-1]:  # 只有最後一個半局可能被截斷（再見/裁定），
                evs = [e for e in halves[(_inn, vht)]          # 其餘必打滿三出局——
                       if not e.get("is_change_player") and e.get("hitter_acnt")]
                if not evs:
                    continue
                pre_k = "_pre_vs" if vht == "1" else "_pre_hs"
                post_k = "_post_vs" if vht == "1" else "_post_hs"
                end_score = max(e[post_k] for e in halves[(_inn, vht)])
                # 每打席首（非更換）事件 = 狀態快照
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
                    rest = end_score - e[pre_k]
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


# ───────────────────────── Phase A 進階指標（可靠度優先）─────────────────────────
# 設計原則：官方計數優先；推算只用在「會計恆等式可驗」處；樣本不足的指標（OAA/framing）不做。

_ZH_BASE = {"一": 1, "二": 2, "三": 3}
_SB_RE = re.compile(r"([一二三])壘跑者\S+?\s*(?:雙)?盜壘上([二三])壘")
_SBH_RE = re.compile(r"三壘跑者\S+?\s*(?:雙)?盜壘回本壘得分")
_CS_RE = re.compile(r"([一二三])壘跑者\S+?出局-盜壘刺")


def _load_re_matrix(cur, span: str, kind: str) -> dict[tuple[str, int], float]:
    cur.execute("SELECT bases, outs, re FROM cpbl.run_expectancy WHERE span=%s AND kind_code=%s",
                (span, kind))
    return {(b, o): float(r) for b, o, r in cur.fetchall()}


def _move_runner(bases: str, frm: int, to: int | None) -> str | None:
    """盜壘後壘位字串；to=None 表跑者移除（CS 出局/回本壘得分）。狀態不合回 None。"""
    if bases[frm - 1] == "_":
        return None
    out = list(bases)
    out[frm - 1] = "_"
    if to is not None:
        if out[to - 1] != "_":
            return None
        out[to - 1] = str(to)
    return "".join(out)


def build_run_values(from_year: int, to_year: int, kind: str = "A") -> dict:
    """在地 runSB/runCS：livelog 盜壘事件的實際 (壘位,出局) 分布 × RE 矩陣 ΔRE 平均。

    注意：out_cnt 是打席前出局數，同 content 內先三振後盜壘刺的少數事件出局數會偏 1，
    屬權重雜訊不影響 RE 值本身。雙盜壘各跑者分別計一次（以事件前狀態近似）。
    """
    span = f"{from_year}-{to_year}"
    with conn() as c:
        cur = c.cursor()
        re_map = _load_re_matrix(cur, span, kind)
        if not re_map:
            raise RuntimeError(f"run_expectancy 無 {span}/{kind}，先跑 build_run_expectancy")
        cur.execute(
            "SELECT content, first_base, second_base, third_base, out_cnt "
            "FROM cpbl.game_livelog WHERE year BETWEEN %s AND %s AND kind_code=%s "
            "AND content LIKE '%%盜壘%%'", (from_year, to_year, kind))
        rows = cur.fetchall()
    sb_sum, sb_n, cs_sum, cs_n, skipped = 0.0, 0, 0.0, 0, 0
    for content, b1, b2, b3, oc in rows:
        bases = ("1" if b1 else "_") + ("2" if b2 else "_") + ("3" if b3 else "_")
        outs = min(int(oc or 0), 2)
        src = re_map.get((bases, outs))
        if src is None:
            skipped += 1
            continue
        text = content or ""
        for frm_zh, to_zh in _SB_RE.findall(text):
            dest = _move_runner(bases, _ZH_BASE[frm_zh], _ZH_BASE[to_zh])
            if dest is None:
                skipped += 1
                continue
            sb_sum += re_map[(dest, outs)] - src
            sb_n += 1
        for _m in _SBH_RE.findall(text):
            dest = _move_runner(bases, 3, None)
            if dest is None:
                skipped += 1
                continue
            sb_sum += re_map[(dest, outs)] + 1.0 - src
            sb_n += 1
        for (frm_zh,) in (m if isinstance(m, tuple) else (m,) for m in _CS_RE.findall(text)):
            dest = _move_runner(bases, _ZH_BASE[frm_zh], None)
            if dest is None:
                skipped += 1
                continue
            after = re_map[(dest, outs + 1)] if outs + 1 <= 2 else 0.0
            cs_sum += after - src
            cs_n += 1
    if sb_n < 1000 or cs_n < 300:
        raise RuntimeError(f"盜壘事件樣本不足（SB={sb_n} CS={cs_n}），不產出係數")
    run_sb, run_cs = sb_sum / sb_n, cs_sum / cs_n
    with conn() as c:
        c.cursor().executemany(
            "INSERT INTO cpbl.sabr_run_values (span, kind_code, metric, value, samples) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (span, kind_code, metric) "
            "DO UPDATE SET value=EXCLUDED.value, samples=EXCLUDED.samples",
            [(span, kind, "run_sb", round(run_sb, 4), sb_n),
             (span, kind, "run_cs", round(run_cs, 4), cs_n)])
    log.info("run_values %s/%s：runSB=%.4f (n=%d) runCS=%.4f (n=%d) skipped=%d "
             "[對照 FG 慣用 runSB≈+0.2]", span, kind, run_sb, sb_n, run_cs, cs_n, skipped)
    return {"run_sb": run_sb, "run_cs": run_cs, "sb_n": sb_n, "cs_n": cs_n}


def build_wsb(span: str) -> dict:
    """打者 wSB（1990–今，一軍例行）：官方 SB/CS/1B/BB/IBB/HBP + 在地 run 係數。

    wSB_i = SB×runSB + CS×runCS − lgRate×opp_i，lgRate=聯盟(SB×runSB+CS×runCS)/Σopp、
    opp=1B+BB−IBB+HBP（IBB 缺值年代視 0，同 FanGraphs 對缺欄位的處理）。
    每年聯盟加總恆等於 0（構造保證），跨年代 run 係數固定並於方法說明揭露。
    """
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT metric, value FROM cpbl.sabr_run_values WHERE span=%s AND kind_code='A'",
                    (span,))
        rv = dict(cur.fetchall())
        if "run_sb" not in rv or "run_cs" not in rv:
            raise RuntimeError(f"sabr_run_values 無 {span} 係數，先跑 build_run_values")
        run_sb, run_cs = float(rv["run_sb"]), float(rv["run_cs"])
        cur.execute(
            "SELECT year, player_id, sum(coalesce(sb,0)), sum(coalesce(cs,0)), "
            "sum(coalesce(b1,0) + coalesce(bb,0) - coalesce(ibb,0) + coalesce(hbp,0)) "
            "FROM cpbl.batting_seasons GROUP BY year, player_id "
            "UNION ALL "
            "SELECT year, player_id, sum(coalesce(sb,0)), sum(coalesce(cs,0)), "
            "sum(coalesce(h,0) - coalesce(b2,0) - coalesce(b3,0) - coalesce(hr,0) "
            "    + coalesce(bb,0) - coalesce(ibb,0) + coalesce(hbp,0)) "
            "FROM cpbl.batting_current "
            "WHERE year NOT IN (SELECT DISTINCT year FROM cpbl.batting_seasons) "
            "GROUP BY year, player_id")
        rows = cur.fetchall()
    by_year: dict[int, list] = defaultdict(list)
    for year, pid, sb, cs, opp in rows:
        if (sb or cs or opp) and opp >= 0:
            by_year[year].append((pid, int(sb), int(cs), int(opp)))
    out_rows = []
    for year, ps in by_year.items():
        lg_num = sum(sb * run_sb + cs * run_cs for _, sb, cs, _o in ps)
        lg_opp = sum(o for *_x, o in ps)
        rate = lg_num / lg_opp if lg_opp else 0.0
        out_rows += [(year, pid, sb, cs, opp, round(sb * run_sb + cs * run_cs - rate * opp, 2))
                     for pid, sb, cs, opp in ps]
    with conn() as c:
        c.execute("DELETE FROM cpbl.batter_wsb")
        c.cursor().executemany(
            "INSERT INTO cpbl.batter_wsb (year, player_id, sb, cs, opp, wsb) "
            "VALUES (%s, %s, %s, %s, %s, %s)", out_rows)
    log.info("batter_wsb：%d 年 %d 列（runSB=%.4f runCS=%.4f）",
             len(by_year), len(out_rows), run_sb, run_cs)
    return {"years": len(by_year), "rows": len(out_rows)}


def build_team_der() -> dict:
    """Team DER（1990–今）：1 − (H−HR)/(BF−BB−HBP−SO−HR)，官方投球總計，零推算。

    歷年=pitching_seasons 隊-年加總；current 年（2026+）=pitching_current 按 team_code
    前 3 碼（franchise 代碼）加總對齊 seasons 的 team_id 空間。
    """
    with conn() as c:
        cur = c.cursor()
        # team_id 一律取前 3 碼：opendata 歷史=3 碼，但 2025 起 seasons 由 current 回填帶 6 碼
        cur.execute(
            "SELECT year, left(team_id, 3), sum(bf), sum(h), sum(hr), sum(bb), "
            "sum(coalesce(hbp,0)), sum(so) FROM cpbl.pitching_seasons "
            "GROUP BY year, left(team_id, 3) "
            "UNION ALL "
            "SELECT year, left(team_code, 3), sum(pa), sum(h), sum(hr), sum(bb), "
            "sum(coalesce(hbp,0)), sum(so) FROM cpbl.pitching_current "
            "WHERE year NOT IN (SELECT DISTINCT year FROM cpbl.pitching_seasons) "
            "GROUP BY year, left(team_code, 3)")
        rows = cur.fetchall()
    out_rows = []
    for year, tid, bf, h, hr, bb, hbp, so in rows:
        den = (bf or 0) - (bb or 0) - (hbp or 0) - (so or 0) - (hr or 0)
        if not tid or not bf or den <= 0:
            continue
        der = 1.0 - ((h or 0) - (hr or 0)) / den
        out_rows.append((year, tid, bf, h, hr, bb, hbp, so, round(der, 4)))
    with conn() as c:
        c.execute("DELETE FROM cpbl.team_der")
        c.cursor().executemany(
            "INSERT INTO cpbl.team_der (year, team_id, bf, h, hr, bb, hbp, so, der) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", out_rows)
    log.info("team_der：%d 列", len(out_rows))
    return {"rows": len(out_rows)}


def build_catcher_runs(year: int, kind: str = "A") -> dict:
    """捕手接捕時失分（RA 非 ERA——自責分無法拆段，誠實命名）→ catcher_runs。

    score 欄位是「事件開始時比分」：打擊方比分在事件 i→i+1 間增加，該分數屬事件 i
    的守備段，記給事件 i 的 catcher_acnt。終場殘差（再見分）補記給末事件捕手。
    驗證：Σ捕手失分 ≈ Σ完成場總得分（恆等式，容差=無捕手事件的漏記）。
    """
    runs: dict[str, int] = defaultdict(int)
    gset: dict[str, set] = defaultdict(set)
    leaked = 0
    with conn() as c:
        cur = c.cursor()
        cur.execute("SELECT DISTINCT game_sno FROM cpbl.game_livelog "
                    "WHERE year=%s AND kind_code=%s ORDER BY game_sno", (year, kind))
        snos = [r[0] for r in cur.fetchall()]
        for sno in snos:
            events = _load_game(cur, year, kind, sno)
            if not events:
                continue
            prev = {"1": 0, "2": 0}
            last_evt: dict[str, dict | None] = {"1": None, "2": None}
            for e in events:
                s = str(e["visiting_home_type"])
                key = "visiting_score" if s == "1" else "home_score"
                cur_score = e.get(key) or 0
                if cur_score > prev[s]:
                    # 比分欄=事件後快照 → 得分屬本列的守備捕手；本列缺值才退回前列
                    le = last_evt[s]
                    ca = e.get("catcher_acnt") or (le.get("catcher_acnt") if le else None)
                    if ca:
                        runs[ca] += cur_score - prev[s]
                    else:
                        leaked += cur_score - prev[s]
                    prev[s] = cur_score
                if e.get("catcher_acnt"):
                    gset[e["catcher_acnt"]].add(sno)
                last_evt[s] = e
            # 終場殘差（末打席得分未反映在後續事件的 score 快照）
            cur.execute("SELECT away_score, home_score FROM cpbl.games "
                        "WHERE year=%s AND kind_code=%s AND game_sno=%s", (year, kind, sno))
            fin = cur.fetchone()
            if fin:
                for s, final in (("1", fin[0]), ("2", fin[1])):
                    d = (final or 0) - prev[s]
                    le = last_evt[s]
                    ca = le.get("catcher_acnt") if le else None
                    if d > 0 and ca:
                        runs[ca] += d
                    elif d > 0:
                        leaked += d
    with conn() as c:
        c.execute("DELETE FROM cpbl.catcher_runs WHERE year=%s AND kind_code=%s", (year, kind))
        c.cursor().executemany(
            "INSERT INTO cpbl.catcher_runs (year, kind_code, player_id, runs, games) "
            "VALUES (%s, %s, %s, %s, %s)",
            [(year, kind, p, r, len(gset[p])) for p, r in runs.items()])
    total = sum(runs.values())
    log.info("catcher_runs %s/%s：%d 場 %d 捕手，歸段 %d 分（漏記 %d）",
             year, kind, len(snos), len(runs), total, leaked)
    return {"games": len(snos), "catchers": len(runs), "runs": total, "leaked": leaked}


# ───────────────────────── Phase B：RE24 ─────────────────────────
_OUTS_ANN = re.compile(r"(\d)人出局")


def _bases_of(e: dict) -> str:
    return (("1" if e.get("first_base") else "_")
            + ("2" if e.get("second_base") else "_")
            + ("3" if e.get("third_base") else "_"))


def build_re24(year: int, kind: str = "A", span: str = "2018-2025") -> dict:
    """打者/投手 RE24（Retrosheet 慣例）→ batter_re24 / pitcher_re24。

    **快照時點（關鍵）**：livelog 同一列的「壘位/out_cnt=事件前、比分=事件後」——
    壘位在下一列才更新，得分直接記在造成得分的那一列。故先全場預跑一次，給每列標
    事件前比分 `_pre`（=前一列的事件後比分，跨半局連續）。

    打者歸因 = RE(下一打席起始態) − RE(本打席末事件態) + 末事件得分
    （末事件得分 = 末列事件後分 − 末列事件前分，再見打席自動入帳）。
    打席**中途**跑壘異動（盜壘/暴投/牽制）落在「跑者桶」，不污染打者/投手。
    - 打席切界：同半局內連續同 hitter 的**非更換**事件（更換列 out_cnt 陳舊、代打列帶新打者）。
    - 末事件態出局數 = 打席起始 out_cnt + 末事件**之前**內文宣告「N人出局」補正；≥3 即截斷。
    - 截斷碎片（末事件 action_name 空 = 無打者結果）歸跑者桶。
    - 半局末打席 RE_after=0（再見局 RE 依慣例歸零、得分照記）。
    - 投手 = 末事件 pitcher_acnt，記同值（打者觀點，負=壓制）。
    驗證恆等式：Σ打者+Σ跑者 = Σ得分 − 半局數×RE(空壘,0)（望遠鏡求和，結構性成立；
    有意義的體檢是跑者桶量級應小——年 ±百分級，非千分級）。
    """
    bat: dict[str, list] = defaultdict(lambda: [0, 0.0])   # player -> [pa, re24]
    pit: dict[str, list] = defaultdict(lambda: [0, 0.0])
    runner_sum, runs_total, n_halves, skipped_pa = 0.0, 0, 0, 0
    with conn() as c:
        cur = c.cursor()
        re_map = _load_re_matrix(cur, span, kind)
        if not re_map:
            raise RuntimeError(f"run_expectancy 無 {span}/{kind}，先跑 build_run_expectancy")
        re_start = re_map[("___", 0)]
        cur.execute("SELECT DISTINCT game_sno FROM cpbl.game_livelog "
                    "WHERE year=%s AND kind_code=%s ORDER BY game_sno", (year, kind))
        snos = [r[0] for r in cur.fetchall()]
        for sno in snos:
            events = _load_game(cur, year, kind, sno)
            if not events:
                continue
            # 預跑：每列標「事件前比分」（None 比分沿用前值）
            pv, ph = 0, 0
            for e in events:
                e["_pre_vs"], e["_pre_hs"] = pv, ph
                pv = e["visiting_score"] if e.get("visiting_score") is not None else pv
                ph = e["home_score"] if e.get("home_score") is not None else ph
                e["_post_vs"], e["_post_hs"] = pv, ph
            # 依半局分組（保序）
            halves: dict[tuple, list[dict]] = {}
            order: list[tuple] = []
            for e in events:
                k = (e["inning_seq"], str(e["visiting_home_type"]))
                if k not in halves:
                    halves[k] = []
                    order.append(k)
                halves[k].append(e)
            for hk in order:
                vht = hk[1]
                pre_k = "_pre_vs" if vht == "1" else "_pre_hs"
                post_k = "_post_vs" if vht == "1" else "_post_hs"
                evs = [e for e in halves[hk] if not e.get("is_change_player")
                       and e.get("hitter_acnt")]
                if not evs:
                    continue
                n_halves += 1
                runs_total += halves[hk][-1][post_k] - halves[hk][0][pre_k]
                # 打席切界：連續同 hitter
                pas: list[list[dict]] = []
                for e in evs:
                    if pas and pas[-1][-1]["hitter_acnt"] == e["hitter_acnt"]:
                        pas[-1].append(e)
                    else:
                        pas.append([e])
                for pi, pa in enumerate(pas):
                    first, final = pa[0], pa[-1]
                    s_state = (_bases_of(first), min(int(first.get("out_cnt") or 0), 2))
                    outs_f = int(first.get("out_cnt") or 0)
                    for e in pa[:-1]:
                        for m in _OUTS_ANN.findall(e.get("content") or ""):
                            outs_f = max(outs_f, int(m))
                    runs_play = final[post_k] - final[pre_k]      # 末事件自身的得分
                    mid_runs = final[pre_k] - first[pre_k]        # 打席中途（跑者）得分
                    if pi + 1 < len(pas):
                        nxt = pas[pi + 1][0]
                        re_after = re_map[(_bases_of(nxt), min(int(nxt.get("out_cnt") or 0), 2))]
                    else:
                        re_after = 0.0
                    truncated = outs_f >= 3 or not (final.get("action_name") or "").strip()
                    re_f = re_map[(_bases_of(final), min(outs_f, 2))]
                    # 跑者桶：打席中途異動（起始態→末事件前態 + 中途得分）
                    runner_sum += re_f + mid_runs - re_map[s_state]
                    delta = re_after + runs_play - re_f
                    if truncated or runs_play < 0:
                        runner_sum += delta
                        skipped_pa += 1
                        continue
                    bat[final["hitter_acnt"]][0] += 1
                    bat[final["hitter_acnt"]][1] += delta
                    if final.get("pitcher_acnt"):
                        p = pit[final["pitcher_acnt"]]
                        p[0] += 1
                        p[1] += delta
    with conn() as c:
        c.execute("DELETE FROM cpbl.batter_re24 WHERE year=%s AND kind_code=%s", (year, kind))
        c.execute("DELETE FROM cpbl.pitcher_re24 WHERE year=%s AND kind_code=%s", (year, kind))
        c.cursor().executemany(
            "INSERT INTO cpbl.batter_re24 (year, kind_code, player_id, pa, re24) "
            "VALUES (%s, %s, %s, %s, %s)",
            [(year, kind, p, n, round(v, 2)) for p, (n, v) in bat.items()])
        c.cursor().executemany(
            "INSERT INTO cpbl.pitcher_re24 (year, kind_code, player_id, bf, re24) "
            "VALUES (%s, %s, %s, %s, %s)",
            [(year, kind, p, n, round(v, 2)) for p, (n, v) in pit.items()])
    bat_sum = sum(v for _n, v in bat.values())
    resid = bat_sum + runner_sum - (runs_total - n_halves * re_start)
    log.info("re24 %s/%s：%d 場 %d 半局；打者Σ=%+.1f 跑者Σ=%+.1f 得分=%d "
             "恆等式殘差=%+.1f（截斷/異常打席 %d）",
             year, kind, len(snos), n_halves, bat_sum, runner_sum, runs_total,
             resid, skipped_pa)
    return {"halves": n_halves, "batters": len(bat), "pitchers": len(pit),
            "bat_sum": round(bat_sum, 1), "runner_sum": round(runner_sum, 1),
            "residual": round(resid, 1)}
