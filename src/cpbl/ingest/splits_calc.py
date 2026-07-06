"""分項數據重算——從已入庫資料算 splits，取代逐日爬官網 apart 頁。

三層來源分解（Phase 0 驗證設計，詳 AI_RUNBOOK 討論）：
- T1 場次級：{batting,pitching}_gamelog（官方單場線）join games
  → 打者家族 1 主客 / 8 月份 / 9 球場 + vs各隊；投手家族 1 主客 / 4 角色 / 9 月份 / 10 球場 + vs各隊。
  官方在這些家族才填 W/L/IP/R/ER/SV，全取官方單場值加總，無重建風險。
- T2 打席級：game_livelog PA island 重建（連續同打者切界，見記憶 livelog-data-semantics）
  → 打者家族 3 vs投手 / 4 壘上 / 5 出局 / 6 局數 / 7 比分 / 10 棒次；
    投手家族 3 vs打者 / 5 壘上 / 6 出局 / 7 局數 / 8 比分。
  官方在這些家族只填打席級欄位（PA/H/HR/BB/SO/球數…），不含 IP/R/ER。

紅線：未知 batting_action_name 一律收集進 diagnostics 並由 verify CLI fail-loud，
不得靜默略過；分類規則未經 harness 對照官方值前不得上線。

每位選手可帶 cutoff 日期（官方 splits 的 updated_at::date）：只納入 game_date < cutoff
的場次，使重算值與「官方快照當下」可精確對照（官方分項只在該員出賽日被刷新，
直接全量對照會把快照時差誤判成重建錯誤）。
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from cpbl.db import conn
from cpbl.imports import classify

_RBI = re.compile(r"(\d+)分打點")


def _is_local(pid: str, country: str) -> bool:
    """官方分項「本土/外籍」用名額語意：永田條款(高塩將樹)視同本土、
    羅力條款仍屬外籍（harness 實證：髙塩官方計本土投手）。"""
    return classify(pid, country or None) in ("local", "nagata")

# (acnt, item_group_code, item_name) → 各欄計數
Key = tuple[str, str, str]
Table = dict[Key, Counter]

MONTH_NAMES = {1: "一月", 2: "二月", 3: "三月", 4: "四月", 5: "五月", 6: "六月",
               7: "七月", 8: "八月", 9: "九月", 10: "十月", 11: "十一月", 12: "十二月"}
INNING_NAMES = {1: "第一局", 2: "第二局", 3: "第三局", 4: "第四局", 5: "第五局", 6: "第六局",
                7: "第七局", 8: "第八局", 9: "第九局", 10: "第十局", 11: "第十一局", 12: "第十二局"}
ORDER_NAMES = {1: "第一棒", 2: "第二棒", 3: "第三棒", 4: "第四棒", 5: "第五棒",
               6: "第六棒", 7: "第七棒", 8: "第八棒", 9: "第九棒"}
OUT_NAMES = {0: "無人出局", 1: "一出局", 2: "二出局"}
BASE_NAMES = {
    frozenset(): "無跑者", frozenset({1}): "跑者一壘", frozenset({2}): "跑者二壘",
    frozenset({3}): "跑者三壘", frozenset({1, 2}): "跑者一、二壘",
    frozenset({1, 3}): "跑者一、三壘", frozenset({2, 3}): "跑者二、三壘",
    frozenset({1, 2, 3}): "滿壘",
}
ROLE_VS = {"先發": "VS. 先發", "中繼": "VS. 中繼", "最後一任": "VS. 救援"}

# games.venue 短名 → 官方分項 item_name（官方用名與 venue_dim 全名不同：臺/台、縣立/市立變體）
VENUE_OFFICIAL = {
    "樂天桃園": "樂天桃園棒球場", "大巨蛋": "臺北大巨蛋", "天母": "天母棒球場",
    "洲際": "台中洲際棒球場", "新莊": "新北市立新莊棒球場", "澄清湖": "高雄市澄清湖棒球場",
    "花蓮": "花蓮縣立棒球場", "台東": "台東縣立棒球場", "嘉義市": "嘉義市立體育棒球場",
    "斗六": "雲林縣斗六棒球場", "亞太主": "臺南亞太國際棒球訓練中心成棒主球場",
    "亞太副": "臺南亞太國際棒球訓練中心成棒副球場", "台南": "台南市立棒球場",
    "嘉義縣": "嘉義縣立棒球場", "屏東": "屏東縣立體育棒球場",
    "園區": "中國信託公益園區棒球場", "皇鷹學院": "台鋼集團職業運動訓練基地皇鷹學院",
    "青埔": "青埔運動公園球場", "立德": "高雄市立德棒球場", "羅東": "宜蘭縣立羅東運動公園棒球場",
    "新竹": "新竹市中正棒球場", "龍潭": "龍潭棒球場", "台北市": "台北市立棒球場",
    "國體": "國立台灣體育運動大學台中棒球場", "體大": "國立體育大學棒球場",
}


def _venue(short: str) -> str:
    return VENUE_OFFICIAL.get(short, short)

# ── 打席結果分類：batting_action_name → 打者統計增量 ─────────────────────────
# 依 2026A livelog 全量詞彙表建立（45 種）。tb 由安打型推導。
# go/fo 語意（harness 全員最小平方擬合定案，GO R²=0.91）：官方計的是
# 「滾地型/飛球型非安打擊球」= 出局 + 失誤上壘 + 犧打——犧短/內野失誤計 go、
# 犧飛/外野失誤計 fo；趁傳/雙殺/野選/界飛照滾飛歸類（係數≈0 證實）。
_H1 = {"pa": 1, "ab": 1, "h": 1, "singles": 1, "tb": 1}
_H2 = {"pa": 1, "ab": 1, "h": 1, "doubles": 1, "tb": 2}
_H3 = {"pa": 1, "ab": 1, "h": 1, "triples": 1, "tb": 3}
_HR = {"pa": 1, "ab": 1, "h": 1, "home_runs": 1, "tb": 4}
_GO = {"pa": 1, "ab": 1, "go": 1}
_FO = {"pa": 1, "ab": 1, "fo": 1}
PA_OUTCOME: dict[str, dict[str, int]] = {
    "一安": _H1, "內安": _H1, "場安": _H1,
    "二安": _H2, "場二": _H2,
    "三安": _H3,
    "全打": _HR, "內全": _HR,
    "三振": {"pa": 1, "ab": 1, "so": 1},
    "不死三振": {"pa": 1, "ab": 1, "so": 1},
    "四壞": {"pa": 1, "bb": 1},
    "故四": {"pa": 1, "bb": 1, "ibb": 1},
    "死球": {"pa": 1, "hbp": 1},
    "犧短": {"pa": 1, "sh": 1, "go": 1},
    "犧短誤": {"pa": 1, "sh": 1, "go": 1},
    "犧選": {"pa": 1, "sh": 1, "go": 1},
    "犧飛": {"pa": 1, "sf": 1, "fo": 1},
    "界犧飛": {"pa": 1, "sf": 1, "fo": 1},
    "一滾": _GO, "二滾": _GO, "三滾": _GO, "游滾": _GO, "投滾": _GO, "捕滾": _GO,
    "雙殺": _GO, "野選": _GO,
    "一飛": _FO, "二飛": _FO, "三飛": _FO, "游飛": _FO, "投飛": _FO, "捕滾飛": _FO,
    "中飛": _FO, "左飛": _FO, "右飛": _FO, "捕飛": _FO, "界飛": _FO, "內飛": _FO,
    # 失誤上壘：打數計、無安打；官方 go/fo 含失誤擊球（內野→go、外野→fo）
    "一失": {"pa": 1, "ab": 1, "go": 1}, "二失": {"pa": 1, "ab": 1, "go": 1},
    "三失": {"pa": 1, "ab": 1, "go": 1}, "游失": {"pa": 1, "ab": 1, "go": 1},
    "投失": {"pa": 1, "ab": 1, "go": 1}, "捕失": {"pa": 1, "ab": 1, "go": 1},
    "中失": {"pa": 1, "ab": 1, "fo": 1}, "左失": {"pa": 1, "ab": 1, "fo": 1},
    "右失": {"pa": 1, "ab": 1, "fo": 1},
    "違規": {"pa": 1, "ab": 1},     # 違規被判出局（違規擊球/觸擊）：型態不明不歸滾飛
    "礙打": {"pa": 1},              # 妨礙打擊（捕手干擾）：PA 不計打數
    "礙守": {"pa": 1, "ab": 1, "go": 1},   # 滾地遭跑者妨礙，官方計 go
    "雙礙守": {"pa": 1, "ab": 1, "go": 1},
    "三呎線": {"pa": 1, "ab": 1, "go": 1},
}

# 打者 T2 增量 → batting_splits 欄名
_BAT_COLS = {"pa": "plate_appearances", "ab": "at_bats", "h": "hits", "rbi": "rbi",
             "singles": "singles",
             "doubles": "doubles", "triples": "triples", "home_runs": "home_runs",
             "tb": "total_bases", "sh": "sac_hit", "sf": "sac_fly", "bb": "bb", "ibb": "ibb",
             "hbp": "hbp", "so": "so", "go": "ground_outs", "fo": "fly_outs"}
# 投手 T2 增量 → pitching_splits 欄名（無 1B/2B/3B/TB/GO/FO 欄）
_PIT_COLS = {"pa": "plate_appearances", "h": "hits", "home_runs": "home_runs",
             "sh": "sac_hit", "sf": "sac_fly", "bb": "bb", "ibb": "ibb",
             "hbp": "hbp", "so": "so"}


def _month_of(d: date) -> str:
    return MONTH_NAMES[d.month]


def _cut(cutoff: dict[str, date] | None, acnt: str, gd: date) -> bool:
    """True = 應排除該場。cutoff=None 為 build 模式（全量、不過濾）；
    dict 為 harness 對照模式（排除官方快照日之後與官方無此人者）。"""
    if cutoff is None:
        return False
    c = cutoff.get(acnt)
    return c is None or gd >= c


# ── T1 場次級 ────────────────────────────────────────────────────────────────

def calc_batting_t1(year: int, kind: str, cutoff: dict[str, date]) -> tuple[Table, Table]:
    """回傳 (splits 家族 1/8/9, vs各隊)。欄值 = 官方單場線加總。"""
    sql = """
        SELECT bg.hitter_acnt, bg.visiting_home_type, g.game_date, g.venue,
               g.home_team_name, g.away_team_name,
               bg.plate_appearances, bg.at_bats, bg.hits, bg.rbi, bg.runs,
               bg.singles, bg.doubles, bg.triples, bg.home_runs, bg.total_bases,
               bg.gidp, bg.sac_hit, bg.sac_fly, bg.bb, bg.ibb, bg.hbp, bg.so, bg.sb, bg.cs
        FROM cpbl.batting_gamelog bg
        JOIN cpbl.games g ON g.year = bg.year AND g.kind_code = bg.kind_code
                         AND g.game_sno = bg.game_sno
        WHERE bg.year = %s AND bg.kind_code = %s AND g.game_date <= CURRENT_DATE
    """
    # game_date 在未來卻有比分 = 保留比賽殘段（delay_kind='保留'、按 sno 聚合、
    # game_date=續賽日）——官方分項排除至續完日（harness 實證），故一併排除
    splits: Table = {}
    vs_team: Table = {}
    with conn() as c:
        rows = c.execute(sql, (year, kind)).fetchall()
    for (acnt, vh, gd, venue, home_nm, away_nm, pa, ab, h, rbi, runs, b1, b2, b3, hr,
         tb, gidp, sh, sf, bb, ibb, hbp, so, sb, cs) in rows:
        if _cut(cutoff, acnt, gd):
            continue
        vh = str(vh)  # gamelog vht 為 text（'1'=客 '2'=主）
        line = {"plate_appearances": pa, "at_bats": ab, "hits": h, "rbi": rbi,
                "singles": b1, "doubles": b2, "triples": b3, "home_runs": hr,
                "total_bases": tb, "sac_hit": sh, "sac_fly": sf, "bb": bb, "ibb": ibb,
                "hbp": hbp, "so": so}
        for grp, item in (("1", "主場" if vh == "2" else "客場"),
                          ("8", _month_of(gd)), ("9", _venue(venue))):
            cnt = splits.setdefault((acnt, grp, item), Counter())
            for k, v in line.items():
                cnt[k] += v or 0
        # vs各隊：對手 = 自隊另一側；含 games/runs/gidp/盜壘
        opp = away_nm if vh == "2" else home_nm
        cnt = vs_team.setdefault((acnt, "VT", opp), Counter())
        cnt["total_games"] += 1
        for k, v in {**line, "runs": runs, "gidp": gidp, "sb_ok": sb, "sb_fail": cs}.items():
            cnt[k] += v or 0
    return splits, vs_team


def calc_pitching_t1(year: int, kind: str, cutoff: dict[str, date]) -> tuple[Table, Table]:
    """回傳 (splits 家族 1/4/9/10, vs各隊)。save_ok 由 games.closer_id 判定。"""
    sql = """
        SELECT pg.pitcher_acnt, pg.visiting_home_type, g.game_date, g.venue,
               g.home_team_name, g.away_team_name, g.closer_id,
               pg.role_type, pg.game_result, pg.is_complete_game, pg.is_shutout,
               pg.relief_point,
               pg.inning_pitched_div3, pg.plate_appearances, pg.pitch_cnt,
               pg.strike_cnt, pg.ball_cnt, pg.hits, pg.home_runs, pg.sac_hit, pg.sac_fly,
               pg.bb, pg.ibb, pg.hbp, pg.so, pg.wild_pitch, pg.balk, pg.runs, pg.earned_runs
        FROM cpbl.pitching_gamelog pg
        JOIN cpbl.games g ON g.year = pg.year AND g.kind_code = pg.kind_code
                         AND g.game_sno = pg.game_sno
        WHERE pg.year = %s AND pg.kind_code = %s AND g.game_date <= CURRENT_DATE
    """
    splits: Table = {}
    vs_team: Table = {}
    with conn() as c:
        rows = c.execute(sql, (year, kind)).fetchall()
    for (acnt, vh, gd, venue, home_nm, away_nm, closer, role, result, cg, sho, rp,
         ip3, pa, pc, stk, bl, h, hr, sh, sf, bb, ibb, hbp, so, wp, bk, r, er) in rows:
        if _cut(cutoff, acnt, gd):
            continue
        vh = str(vh)
        line = {"wins": 1 if result == "勝" else 0, "loses": 1 if result == "敗" else 0,
                "starts": 1 if role == "先發" else 0, "complete_games": 1 if cg else 0,
                "shutouts": 1 if sho else 0, "save_ok": 1 if closer == acnt else 0,
                "inning_pitched_div3": ip3, "plate_appearances": pa, "pitch_cnt": pc,
                "strikes": stk, "balls": bl, "hits": h, "home_runs": hr, "sac_hit": sh,
                "sac_fly": sf, "bb": bb, "ibb": ibb, "hbp": hbp, "so": so,
                "wild_pitch": wp, "balk": bk, "runs": r, "earned_runs": er}
        for grp, item in (("1", "主場" if vh == "2" else "客場"), ("4", role),
                          ("9", _month_of(gd)), ("10", _venue(venue))):
            cnt = splits.setdefault((acnt, grp, item), Counter())
            for k, v in line.items():
                cnt[k] += v or 0
        opp = away_nm if vh == "2" else home_nm
        cnt = vs_team.setdefault((acnt, "VT", opp), Counter())
        cnt["total_games"] += 1
        # closes/holds 僅 vs各隊表有欄位，不進 splits 桶（避免 harness 誤比）
        cnt["closes"] += 1 if role == "最後一任" else 0
        cnt["holds"] += 1 if (rp or 0) > 0 else 0
        for k, v in line.items():
            # 官方 pitching_vs_team 的 strikes/balls/sac_hit/sac_fly 欄語意與
            # gamelog 不同（getfighterscore 另有定義，對調測試亦不成立），
            # 不宣稱重算此四欄
            if k not in ("strikes", "balls", "sac_hit", "sac_fly"):
                cnt[k] += v or 0
    return splits, vs_team


# ── T2 打席級（livelog PA island）────────────────────────────────────────────

def _load_bio() -> dict[str, tuple[str, str, str]]:
    with conn() as c:
        rows = c.execute("SELECT id, bats, throws, country FROM cpbl.players").fetchall()
    return {r[0]: (r[1] or "", r[2] or "", r[3] or "") for r in rows}


def _batter_side(bats: str, p_throws: str) -> str | None:
    """打者實際站位。左右開弓推定站投手反側；資料缺回 None。"""
    if bats in ("左打", "右打"):
        return bats
    if bats == "左右開弓":
        if p_throws == "右投":
            return "左打"
        if p_throws == "左投":
            return "右打"
    return None


def calc_t2(year: int, kind: str, bat_cut: dict[str, date],
            pit_cut: dict[str, date]) -> tuple[Table, Table, Table, dict]:
    """livelog 單趟重建。

    回傳 (打者家族 3/4/5/6/7/10, 投手家族 3/5/6/7/8,
          打者家族 1/8/9 的 go/fo 補充值, diagnostics)。
    """
    bio = _load_bio()
    with conn() as c:
        roles = {(sno, a): r for sno, a, r in c.execute(
            "SELECT game_sno, pitcher_acnt, role_type FROM cpbl.pitching_gamelog "
            "WHERE year = %s AND kind_code = %s", (year, kind)).fetchall()}
        gmeta = {sno: (gd, venue) for sno, gd, venue in c.execute(
            "SELECT game_sno, game_date, venue FROM cpbl.games "
            "WHERE year = %s AND kind_code = %s", (year, kind)).fetchall()}
        rows = c.execute(
            """
            SELECT game_sno, inning_seq, visiting_home_type, main_event_no,
                   hitter_acnt, pitcher_acnt, batting_order, out_cnt,
                   first_base, second_base, third_base,
                   batting_action_name, is_strike, is_ball,
                   visiting_score, home_score, is_change_player, content
            FROM cpbl.game_livelog
            WHERE year = %s AND kind_code = %s
            ORDER BY game_sno, inning_seq, visiting_home_type, main_event_no
            """, (year, kind)).fetchall()

    bat: Table = {}
    pit: Table = {}
    bat_gofo: Table = {}
    diag = {"unknown_action": Counter(), "missing_batter_bio": Counter(),
            "missing_pitcher_bio": Counter(), "missing_role": Counter(),
            "islands": 0, "pa": 0, "skipped_no_outcome": 0,
            "skipped_no_pitch": Counter()}

    pa_seq: dict[tuple, int] = {}  # (game_sno, vht) → 該隊已完成 PA 數（打序重建用）

    def flush(island: list, score_before: tuple[int, int]) -> None:
        first = island[0]
        outcome = next((r[11] for r in reversed(island) if r[11]), None)
        diag["islands"] += 1
        if not outcome:
            diag["skipped_no_outcome"] += 1
            return
        delta = PA_OUTCOME.get(outcome)
        if delta is None:
            diag["unknown_action"][outcome] += 1
            return
        # 幽靈島：換人公告列會掛「即將上場打者」acnt + 傳播的結果字串自成一島，
        # 但無任何投球列 → 非 PA（harness 實證 box 不計，全季 117 例）
        lp = next((i for i in range(len(island) - 1, -1, -1)
                   if island[i][12] or island[i][13]), None)
        if lp is None:
            diag["skipped_no_pitch"][outcome] += 1
            return
        diag["pa"] += 1
        # 官方分項取「打席結束時」狀態（harness 實證：島尾分布≈官方、島首差數百）。
        # 錨定「最後一顆投球列」而非島尾列：打席後的跑壘事件（K後抓盜壘、安打後牽制）
        # 會以同打者掛在島尾，其 out_cnt/壘包已含打席後變化，不可作為情境
        last = island[lp]
        sno, inning, vh, hitter = first[0], last[1], str(first[2]), first[4]
        pitcher, outs = last[5], last[7]
        b1, b2, b3 = last[8], last[9], last[10]
        # 打序：livelog batting_order 是「該半局第幾位」非打序；打擊為嚴格輪轉，
        # 打序 = 該隊本場第 n 個完成 PA % 9 + 1（代打自然繼承棒位；未完成打席不進位）
        seq = pa_seq.get((sno, vh), 0)
        pa_seq[(sno, vh)] = seq + 1
        order = seq % 9 + 1
        gd, venue = gmeta[sno]
        if gd > date.today():   # 未完成保留賽殘段：官方分項排除至續完日
            return
        strikes = sum(1 for r in island if r[12])
        balls = sum(1 for r in island if r[13])
        # 打點：官方 T2 家族有填 rbi，由 content「N分打點」標記解析（僅結果列帶標記）
        rbi = sum(int(m.group(1)) for r in island for m in _RBI.finditer(r[17] or ""))
        bases = frozenset(n for n, v in ((1, b1), (2, b2), (3, b3)) if v not in (None, ""))
        # 比分取最後一顆投球「前」的比分（終局打點不得改變該打席的情境歸類）
        if lp > 0 and island[lp - 1][14] is not None and island[lp - 1][15] is not None:
            v_sc, h_sc = island[lp - 1][14], island[lp - 1][15]
        else:
            v_sc, h_sc = score_before
        my_sc, opp_sc = (h_sc, v_sc) if vh == "2" else (v_sc, h_sc)
        score_item = ("比分領先" if my_sc > opp_sc
                      else "比分落後" if my_sc < opp_sc else "相同比分")
        p_bats, p_throws, p_country = bio.get(pitcher, ("", "", ""))
        h_bats, _h_throws, h_country = bio.get(hitter, ("", "", ""))

        # ── 打者側 ──
        if not _cut(bat_cut, hitter, gd):
            buckets: list[tuple[str, str]] = [
                ("4", BASE_NAMES[bases]),
                ("5", OUT_NAMES.get(outs, "二出局")),
                ("6", INNING_NAMES.get(inning, "")),
                ("7", score_item),
            ]
            if order in ORDER_NAMES:
                buckets.append(("10", ORDER_NAMES[order]))
            if p_throws:
                buckets.append(("3", f"VS. {'左投' if p_throws == '左投' else '右投'}"))
                buckets.append(("3", "VS. 本土投手" if _is_local(pitcher, p_country)
                                else "VS. 外籍投手"))
            else:
                diag["missing_pitcher_bio"][pitcher] += 1
            role = roles.get((sno, pitcher))
            if role in ROLE_VS:
                buckets.append(("3", ROLE_VS[role]))
            else:
                diag["missing_role"][(sno, pitcher)] += 1
            for grp, item in buckets:
                cnt = bat.setdefault((hitter, grp, item), Counter())
                for k, v in delta.items():
                    cnt[_BAT_COLS[k]] += v
                cnt["rbi"] += rbi
            # 家族 1/8/9 的 go/fo（gamelog 無此二欄，由 livelog 補）
            for grp, item in (("1", "主場" if vh == "2" else "客場"),
                              ("8", _month_of(gd)), ("9", _venue(venue))):
                cnt = bat_gofo.setdefault((hitter, grp, item), Counter())
                cnt["ground_outs"] += delta.get("go", 0)
                cnt["fly_outs"] += delta.get("fo", 0)

        # ── 投手側（vh 反轉視角）──
        if not _cut(pit_cut, pitcher, gd):
            p_my, p_opp = opp_sc, my_sc
            p_score = ("比分領先" if p_my > p_opp
                       else "比分落後" if p_my < p_opp else "相同比分")
            pbuckets: list[tuple[str, str]] = [
                ("5", BASE_NAMES[bases]),
                ("6", OUT_NAMES.get(outs, "二出局")),
                ("7", INNING_NAMES.get(inning, "")),
                ("8", p_score),
            ]
            side = _batter_side(h_bats, p_throws)
            if side:
                pbuckets.append(("3", f"VS. {side}"))
            else:
                diag["missing_batter_bio"][hitter] += 1
            if h_country:
                pbuckets.append(("3", "VS. 本土打者" if _is_local(hitter, h_country)
                                 else "VS. 外籍打者"))
            for grp, item in pbuckets:
                cnt = pit.setdefault((pitcher, grp, item), Counter())
                for k, v in delta.items():
                    if k in _PIT_COLS:
                        cnt[_PIT_COLS[k]] += v
                cnt["pitch_cnt"] += strikes + balls
                cnt["strikes"] += strikes
                cnt["balls"] += balls

    cur_game = None
    running = (0, 0)
    score_before = (0, 0)
    island: list = []
    ikey = None
    for r in rows:
        sno, inning, vh, _, hitter = r[0], r[1], r[2], r[3], r[4]
        if sno != cur_game:
            if island:
                flush(island, score_before)
            cur_game, running, island, ikey = sno, (0, 0), [], None
        if not hitter:
            # 特殊事件列（突破僵局上壘/更替等）：不切打席界，只推進比分
            v_sc, h_sc = r[14], r[15]
            if v_sc is not None and h_sc is not None:
                running = (v_sc, h_sc)
            continue
        key = (inning, vh, hitter)
        if key != ikey:
            if island:
                flush(island, score_before)
            island, ikey, score_before = [], key, running
        island.append(r)
        v_sc, h_sc = r[14], r[15]
        if v_sc is not None and h_sc is not None:
            running = (v_sc, h_sc)
    if island:
        flush(island, score_before)
    return bat, pit, bat_gofo, diag


# ── Phase 1 writer：重算寫回官方表（取代本季 apart/vs-team 爬蟲）─────────────
# 官方表 PK 含 item_index/item_note，字典自官方既有列 dump 固化於此；
# 未知 item（新球場等）一律 fail-loud，禁止靜默略過。

# 官方球場代碼（item_note=F 碼、item_index 恆 1）
VENUE_CODE = {
    "宜蘭縣立羅東運動公園棒球場": "F01", "新竹市中正棒球場": "F02",
    "國立台灣體育運動大學台中棒球場": "F03", "台南市立棒球場": "F04",
    "高雄市立德棒球場": "F05", "屏東縣立體育棒球場": "F06",
    "嘉義市立體育棒球場": "F07", "新北市立新莊棒球場": "F08",
    "高雄市澄清湖棒球場": "F09", "天母棒球場": "F10", "龍潭棒球場": "F11",
    "花蓮縣立棒球場": "F12", "雲林縣斗六棒球場": "F13", "嘉義縣立棒球場": "F14",
    "台北市立棒球場": "F15", "國立體育大學棒球場": "F16", "台東縣立棒球場": "F17",
    "台中洲際棒球場": "F19", "樂天桃園棒球場": "F23", "青埔運動公園球場": "F24",
    "中國信託公益園區棒球場": "F26", "臺北大巨蛋": "F29",
    "臺南亞太國際棒球訓練中心成棒副球場": "F30", "臺南亞太國際棒球訓練中心成棒主球場": "F31",
    "台鋼集團職業運動訓練基地皇鷹學院": "F32",
}

_HOME_META = {"主場": (1, "2"), "客場": (2, "1")}   # note=官方 vht 碼
_BASE_ORDER = ["無跑者", "跑者一壘", "跑者二壘", "跑者三壘",
               "跑者一、二壘", "跑者一、三壘", "跑者二、三壘", "滿壘"]
_BASE_META = {n: (i + 1, n) for i, n in enumerate(_BASE_ORDER)}
_OUT_META = {"無人出局": (1, "0"), "一出局": (2, "1"), "二出局": (3, "2")}
_SCORE_META = {"比分落後": (1, "落後"), "比分領先": (2, "領先"), "相同比分": (3, "平手")}
_INN_META = {n: (i, str(i)) for i, n in INNING_NAMES.items()}
_INN_META[""] = (13, "13")   # 13局以上官方 name 空、index=局數；現制延長至12局，惟保底
_MONTH_META = {n: (i, str(i)) for i, n in MONTH_NAMES.items()}
_ORDER_META = {n: (i, str(i)) for i, n in ORDER_NAMES.items()}
_VSP_META = {"VS. 右投": (1, "R"), "VS. 左投": (2, "L"), "VS. 本土投手": (3, "0"),
             "VS. 外籍投手": (4, "1"), "VS. 先發": (5, "先發"), "VS. 中繼": (6, "中繼"),
             "VS. 救援": (7, "最後一任")}
_VSB_META = {"VS. 右打": (1, "R"), "VS. 左打": (2, "L"),
             "VS. 本土打者": (3, "0"), "VS. 外籍打者": (4, "1")}
_ROLE_META = {"先發": (1, "先發"), "中繼": (2, "中繼"), "最後一任": (3, "最後一任")}
_VENUE_META = {n: (1, c) for n, c in VENUE_CODE.items()}

_META = {
    "bat": {"1": _HOME_META, "3": _VSP_META, "4": _BASE_META, "5": _OUT_META,
            "6": _INN_META, "7": _SCORE_META, "8": _MONTH_META, "9": _VENUE_META,
            "10": _ORDER_META},
    "pit": {"1": _HOME_META, "3": _VSB_META, "4": _ROLE_META, "5": _BASE_META,
            "6": _OUT_META, "7": _INN_META, "8": _SCORE_META, "9": _MONTH_META,
            "10": _VENUE_META},
}


def _meta(side: str, grp: str, name: str) -> tuple[int, str]:
    m = _META[side].get(grp, {}).get(name)
    if m is None:
        raise ValueError(f"未知分項 item：side={side} group={grp} name={name!r}（字典需更新）")
    return m


def _ratio(num: float, den: float, nd: int) -> float | None:
    """分子/分母 → 四捨五入（HALF_UP，棒球慣例）nd 位。Decimal 精確除法，
    避免 float 中介 + Python round 的銀行家捨入在半值（如 .3125）偏差。
    註：官方站 rate 欄為「截斷」4 位（實測 obp 0.4014 vs round 0.4015），
    我方採 round 與 API _merge_splits 路徑一致——顯示層 ±0.0001 差異可接受。"""
    if not den:
        return None
    q = Decimal(1).scaleb(-nd)
    return float((Decimal(num) / Decimal(den)).quantize(q, rounding=ROUND_HALF_UP))


def _bat_rates(c: Counter) -> dict:
    """官方存欄口徑：avg 3 位、obp/slg/ops/goao 4 位（同 API _merge_splits 公式）。"""
    ab, h = c["at_bats"], c["hits"]
    bb, hbp, sf = c["bb"], c["hbp"], c["sac_fly"]
    obp = _ratio(h + bb + hbp, ab + bb + hbp + sf, 4)
    slg = _ratio(c["total_bases"], ab, 4)
    ops = (round((obp or 0) + (slg or 0), 4)
           if (obp is not None or slg is not None) else None)
    return {"avg": _ratio(h, ab, 3), "obp": obp, "slg": slg, "ops": ops,
            "goao": _ratio(c["ground_outs"], c["fly_outs"], 4)}


def _blown_saves(year: int, kind: str) -> Counter:
    """(acnt, 對手隊名) → 救援失敗 BS 次數。批次撈 livelog/gamelog 按場呼叫 blown()。"""
    from cpbl.models.pitcher_decisions import blown
    out: Counter = Counter()
    with conn() as c:
        cur = c.cursor()
        cur.execute(
            "SELECT ll.game_sno, ll.main_event_no, ll.visiting_home_type, ll.pitcher_acnt, "
            "ll.first_base, ll.second_base, ll.third_base, ll.visiting_score, ll.home_score "
            "FROM cpbl.game_livelog ll JOIN cpbl.games g ON g.year=ll.year "
            "AND g.kind_code=ll.kind_code AND g.game_sno=ll.game_sno "
            "WHERE ll.year=%s AND ll.kind_code=%s AND g.game_date <= CURRENT_DATE "
            "ORDER BY ll.game_sno", (year, kind))
        cols = [d.name for d in cur.description]
        ll_by_game: dict[int, list[dict]] = {}
        for r in cur.fetchall():
            ll_by_game.setdefault(r[0], []).append(dict(zip(cols, r, strict=True)))
        cur.execute(
            "SELECT game_sno, pitcher_acnt, visiting_home_type, game_result FROM "
            "cpbl.pitching_gamelog WHERE year=%s AND kind_code=%s", (year, kind))
        pcols = [d.name for d in cur.description]
        pg_by_game: dict[int, list[dict]] = {}
        for r in cur.fetchall():
            pg_by_game.setdefault(r[0], []).append(dict(zip(pcols, r, strict=True)))
        opp = {}
        for sno, hn, an in c.execute(
                "SELECT game_sno, home_team_name, away_team_name FROM cpbl.games "
                "WHERE year=%s AND kind_code=%s", (year, kind)).fetchall():
            opp[sno] = {"1": hn, "2": an}   # 投手隊=守備方：vht(打擊方)反side即對手
    side_of = {}
    for sno, pgs in pg_by_game.items():
        for p in pgs:
            side_of[(sno, p["pitcher_acnt"])] = str(p["visiting_home_type"])
    for sno, ll in ll_by_game.items():
        for acnt, tag in blown(ll, pg_by_game.get(sno, [])).items():
            if tag != "BS":
                continue
            # 對手：pitching_gamelog vht 為投手自隊側，客隊投手(1)的對手=主隊名
            my = side_of.get((sno, acnt))
            if my:
                out[(acnt, opp[sno][my])] += 1
    return out


def _team_maps(year: int, kind: str) -> tuple[dict, dict, dict]:
    """(隊名→隊碼, 打者acnt→自隊碼, 投手acnt→自隊碼)。自隊取最近一場所屬側。"""
    with conn() as c:
        name2code = {}
        for hn, hc, an, ac in c.execute(
                "SELECT home_team_name, home_team_code, away_team_name, away_team_code "
                "FROM cpbl.games WHERE year=%s AND kind_code=%s", (year, kind)).fetchall():
            name2code[hn] = hc
            name2code[an] = ac
        own_b, own_p = {}, {}
        for tbl, acol, own in (("batting_gamelog", "hitter_acnt", own_b),
                               ("pitching_gamelog", "pitcher_acnt", own_p)):
            rows = c.execute(
                f"SELECT DISTINCT ON (x.{acol}) x.{acol}, "  # noqa: S608 — tbl/acol 內部常數
                "CASE WHEN x.visiting_home_type='2' THEN g.home_team_code "
                "ELSE g.away_team_code END "
                f"FROM cpbl.{tbl} x JOIN cpbl.games g ON g.year=x.year "
                "AND g.kind_code=x.kind_code AND g.game_sno=x.game_sno "
                "WHERE x.year=%s AND x.kind_code=%s AND g.game_date <= CURRENT_DATE "
                f"ORDER BY x.{acol}, g.game_date DESC",
                (year, kind)).fetchall()
            own.update(dict(rows))
    return name2code, own_b, own_p


def build_splits(year: int, kinds: tuple[str, ...] = ("A", "D")) -> dict:
    """重算並寫回四張分項表（本季）。每 kind 一交易：DELETE 該 year+kind 全列後 INSERT。

    取代每日爬蟲的本季 apart 分項與 vs-team（生涯 9999 仍走爬蟲，Phase 2 再改）。
    寫回後官方爬值即被覆蓋——cpbl-verify-splits 僅對「新爬回的官方值」有對照意義。
    """
    summary: dict = {}
    for kind in kinds:
        bat_t1, bat_vt = calc_batting_t1(year, kind, None)
        pit_t1, pit_vt = calc_pitching_t1(year, kind, None)
        bat_t2, pit_t2, bat_gofo, diag = calc_t2(year, kind, None, None)
        if diag["unknown_action"]:
            raise ValueError(f"未知打席結果詞彙，中止寫入：{dict(diag['unknown_action'])}")
        for key, cnt in bat_gofo.items():
            bat_t1.setdefault(key, Counter()).update(cnt)
        bat_t1.update(bat_t2)
        pit_t1.update(pit_t2)
        name2code, own_b, own_p = _team_maps(year, kind)
        bs_cnt = _blown_saves(year, kind)

        b_rows = []
        for (acnt, grp, item), c in sorted(bat_t1.items()):
            idx, note = _meta("bat", grp, item)
            r = _bat_rates(c)
            b_rows.append((year, kind, acnt, grp, idx, item, note,
                           c["plate_appearances"], c["at_bats"], c["hits"], c["rbi"],
                           c["singles"], c["doubles"], c["triples"], c["home_runs"],
                           c["total_bases"], c["sac_hit"], c["sac_fly"], c["bb"], c["ibb"],
                           c["hbp"], c["so"], c["ground_outs"], c["fly_outs"],
                           r["goao"], r["avg"], r["obp"], r["slg"], r["ops"]))
        p_rows = []
        for (acnt, grp, item), c in sorted(pit_t1.items()):
            idx, note = _meta("pit", grp, item)
            outs = c["inning_pitched_div3"]
            p_rows.append((year, kind, acnt, grp, idx, item, note,
                           c["wins"], c["loses"], c["starts"], c["complete_games"],
                           c["shutouts"], c["save_ok"], outs // 3, outs % 3,
                           c["plate_appearances"], c["pitch_cnt"], c["strikes"], c["balls"],
                           c["hits"], c["home_runs"], c["sac_hit"], c["sac_fly"],
                           c["bb"], c["ibb"], c["hbp"], c["so"],
                           c["wild_pitch"], c["balk"], c["runs"], c["earned_runs"]))
        bvt_rows = []
        for (acnt, _, opp_name), c in sorted(bat_vt.items()):
            code = name2code[opp_name]
            att = c["sb_ok"] + c["sb_fail"]
            r = _bat_rates(c)
            ta_den = c["at_bats"] - c["hits"] + c["sb_fail"] + c["gidp"]
            ta_num = c["total_bases"] + c["bb"] + c["hbp"] + c["sb_ok"] - c["sb_fail"]
            sb_pct = _ratio(c["sb_ok"], att, 4)
            bvt_rows.append((year, kind, acnt, code, opp_name, own_b.get(acnt),
                             c["total_games"], c["plate_appearances"], c["at_bats"],
                             c["hits"], c["rbi"], c["runs"], c["singles"], c["doubles"],
                             c["triples"], c["home_runs"], c["total_bases"], c["gidp"],
                             c["sac_hit"], c["sac_fly"], c["bb"], c["ibb"], c["hbp"],
                             c["so"], c["sb_ok"], c["sb_fail"],
                             sb_pct if sb_pct is not None else 0,
                             r["avg"], r["obp"], r["slg"],
                             _ratio(ta_num, ta_den, 4) if ta_den > 0 else None, r["ops"]))
        pvt_rows = []
        for (acnt, _, opp_name), c in sorted(pit_vt.items()):
            code = name2code[opp_name]
            outs = c["inning_pitched_div3"]
            pvt_rows.append((year, kind, acnt, code, opp_name, own_p.get(acnt),
                             c["total_games"], c["starts"], c["closes"],
                             c["complete_games"], c["shutouts"], c["wins"], c["loses"],
                             c["save_ok"], bs_cnt.get((acnt, opp_name), 0), c["holds"],
                             outs // 3, outs % 3,
                             _ratio((c["hits"] + c["bb"]) * 3, outs, 2),   # WHIP=(H+BB)/IP
                             _ratio(c["earned_runs"] * 27, outs, 2),      # ERA=ER*9/IP
                             c["plate_appearances"], c["pitch_cnt"], c["hits"],
                             c["home_runs"], c["bb"], c["ibb"], c["hbp"], c["so"],
                             c["wild_pitch"], c["balk"], c["runs"], c["earned_runs"]))

        with conn() as cx:  # 每 kind 單一交易：四表原子換版
            for tbl, cols, rows in (
                ("batting_splits",
                 "year, kind_code, acnt, item_group_code, item_index, item_name, item_note, "
                 "plate_appearances, at_bats, hits, rbi, singles, doubles, triples, home_runs, "
                 "total_bases, sac_hit, sac_fly, bb, ibb, hbp, so, ground_outs, fly_outs, "
                 "goao, avg, obp, slg, ops", b_rows),
                ("pitching_splits",
                 "year, kind_code, acnt, item_group_code, item_index, item_name, item_note, "
                 "wins, loses, starts, complete_games, shutouts, save_ok, inning_pitched_cnt, "
                 "inning_pitched_div3, plate_appearances, pitch_cnt, strikes, balls, hits, "
                 "home_runs, sac_hit, sac_fly, bb, ibb, hbp, so, wild_pitch, balk, runs, "
                 "earned_runs", p_rows),
                ("batting_vs_team",
                 "year, kind_code, acnt, fight_team_code, fight_team_name, team_no, "
                 "total_games, plate_appearances, at_bats, hits, rbi, runs, singles, doubles, "
                 "triples, home_runs, total_bases, gidp, sac_hit, sac_fly, bb, ibb, hbp, so, "
                 "sb_ok, sb_fail, sb_pct, avg, obp, slg, ta, ops", bvt_rows),
                ("pitching_vs_team",
                 "year, kind_code, acnt, fight_team_code, fight_team_name, team_no, "
                 "total_games, starts, closes, complete_games, shutouts, wins, loses, save_ok, "
                 "save_fail, holds, inning_pitched_cnt, inning_pitched_div3, whip, era, "
                 "plate_appearances, pitch_cnt, hits, home_runs, bb, ibb, hbp, so, "
                 "wild_pitch, balk, runs, earned_runs", pvt_rows),
            ):
                cx.execute(
                    f"DELETE FROM cpbl.{tbl} WHERE year=%s AND kind_code=%s",  # noqa: S608
                    (year, kind))
                ph = ", ".join(["%s"] * len(cols.split(", "))) + ", now()"
                with cx.cursor() as cur:
                    cur.executemany(
                        f"INSERT INTO cpbl.{tbl} ({cols}, updated_at) VALUES ({ph})",  # noqa: S608
                        rows)
        summary[kind] = {"bsplit": len(b_rows), "psplit": len(p_rows),
                         "bvt": len(bvt_rows), "pvt": len(pvt_rows),
                         "pa": diag["pa"], "blown_saves": sum(bs_cnt.values())}
    return summary


# ── Phase 2：生涯 anchor + accrual（停爬生涯 apart）──────────────────────────
# 生涯(9999) = base(純歷史基底) + 本季重算。base 錨定法：官方 apart 頁同刻回傳
# 本季與生涯（同 transaction 入庫），「官方生涯 − 官方本季」同源同刻相減，
# apart 頁滯後互相抵消 → base 零錯位。C/E 本季無場 → base=官方生涯原值（凍結）。
# 跨年 roll：base += 上季終值（純 DB 運算，見 cpbl-anchor-career docstring）。

_BSCB_COLS = ["plate_appearances", "at_bats", "hits", "rbi", "singles", "doubles",
              "triples", "home_runs", "total_bases", "sac_hit", "sac_fly", "bb", "ibb",
              "hbp", "so", "ground_outs", "fly_outs"]
_PSCB_COLS = ["wins", "loses", "starts", "complete_games", "shutouts", "save_ok",
              "inning_pitched_div3", "plate_appearances", "pitch_cnt", "strikes", "balls",
              "hits", "home_runs", "sac_hit", "sac_fly", "bb", "ibb", "hbp", "so",
              "wild_pitch", "balk", "runs", "earned_runs"]
BaseKey = tuple[str, str, str, int, str]   # (kind, acnt, group, index, name)


def _csv_season_official(path: str, season: int, cols: list[str],
                         pitching: bool) -> dict[BaseKey, Counter]:
    """讀 Phase 1 覆蓋前的官方本季備份 CSV → 計數。IP 轉總出局數存 div3 欄。"""
    import csv
    out: dict[BaseKey, Counter] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if int(r["year"]) != season:
                continue
            key = (r["kind_code"], r["acnt"], r["item_group_code"],
                   int(r["item_index"]), r["item_name"])
            c = Counter({k: int(r[k] or 0) for k in cols if k != "inning_pitched_div3"})
            if pitching:
                c["inning_pitched_div3"] = (int(r["inning_pitched_cnt"] or 0) * 3
                                            + int(r["inning_pitched_div3"] or 0))
            out[key] = c
    return out


def anchor_career(season: int, csv_dir: str) -> dict:
    """錨定生涯基底：base = 表中官方生涯(9999) − 備份 CSV 官方本季（同刻相減）。

    一次性操作（重錨/跨年 roll 見 CLI docstring）。寫入 *_career_base（全刪重建）。
    負值代表官方站內自我不一致（Phase 0 已知，如出局家族自砍），原樣保留——
    合成寫回時會與本季相加、彼此抵消，不 clamp。
    """
    summary = {}
    for side, table, cols, note_key in (
        ("bat", "batting_splits", _BSCB_COLS, "batting_splits_career_base"),
        ("pit", "pitching_splits", _PSCB_COLS, "pitching_splits_career_base"),
    ):
        pitching = side == "pit"
        season_off = _csv_season_official(
            f"{csv_dir}/backup_{table}.csv", season, cols, pitching)
        with conn() as c:
            sel = ", ".join(k for k in cols if k != "inning_pitched_div3")
            ip = (", inning_pitched_cnt*3 + inning_pitched_div3" if pitching else "")
            rows = c.execute(
                f"SELECT kind_code, acnt, item_group_code, item_index, item_name, "  # noqa: S608
                f"item_note, {sel}{ip} FROM cpbl.{table} WHERE year = 9999").fetchall()
        base_rows = []
        neg = 0
        n_named = len(cols) - (1 if pitching else 0)
        for r in rows:
            key: BaseKey = (r[0], r[1], r[2], r[3], r[4])
            note = r[5]
            vals = Counter(dict(zip([k for k in cols if k != "inning_pitched_div3"],
                                    [v or 0 for v in r[6:6 + n_named]], strict=True)))
            if pitching:
                vals["inning_pitched_div3"] = r[6 + n_named] or 0
            vals.subtract(season_off.get(key, Counter()))
            if any(v < 0 for v in vals.values()):
                neg += 1
            base_rows.append((*key, note, *[vals[k] for k in cols]))
        with conn() as c:
            c.execute(f"DELETE FROM cpbl.{note_key}")  # noqa: S608 — 常數表名
            ph = ", ".join(["%s"] * (6 + len(cols)))
            with c.cursor() as cur:
                cur.executemany(
                    f"INSERT INTO cpbl.{note_key} (kind_code, acnt, item_group_code, "  # noqa: S608
                    f"item_index, item_name, item_note, {', '.join(cols)}) VALUES ({ph})",
                    base_rows)
        summary[side] = {"rows": len(base_rows), "season_rows": len(season_off),
                         "neg_rows": neg}
    return summary


def build_career(season: int, kinds: tuple[str, ...] = ("A", "D")) -> dict:
    """生涯(9999) = base + 本季重算（讀主表 year=season 的已重算列）。

    寫回 9999 全部 kind：A/D 為 base+本季；C/E 本季無場即 base 原值（凍結，
    季後賽時把 C/E 加進 build_splits 的 kinds 即自動累加）。
    """
    summary = {}
    for side, table, base_table, cols in (
        ("bat", "batting_splits", "batting_splits_career_base", _BSCB_COLS),
        ("pit", "pitching_splits", "pitching_splits_career_base", _PSCB_COLS),
    ):
        pitching = side == "pit"
        career: dict[BaseKey, Counter] = {}
        notes: dict[BaseKey, str | None] = {}
        with conn() as c:
            for r in c.execute(
                    f"SELECT kind_code, acnt, item_group_code, item_index, item_name, "  # noqa: S608
                    f"item_note, {', '.join(cols)} FROM cpbl.{base_table}").fetchall():
                key: BaseKey = (r[0], r[1], r[2], r[3], r[4])
                notes[key] = r[5]
                career[key] = Counter(dict(zip(cols, [v or 0 for v in r[6:]], strict=True)))
            sel = ", ".join(k for k in cols if k != "inning_pitched_div3")
            ip = (", inning_pitched_cnt*3 + inning_pitched_div3" if pitching else "")
            n_named = len(cols) - (1 if pitching else 0)
            for r in c.execute(
                    f"SELECT kind_code, acnt, item_group_code, item_index, item_name, "  # noqa: S608
                    f"item_note, {sel}{ip} FROM cpbl.{table} "
                    "WHERE year = %s AND kind_code = ANY(%s)", (season, list(kinds))).fetchall():
                key = (r[0], r[1], r[2], r[3], r[4])
                notes.setdefault(key, r[5])
                vals = Counter(dict(zip([k for k in cols if k != "inning_pitched_div3"],
                                        [v or 0 for v in r[6:6 + n_named]], strict=True)))
                if pitching:
                    vals["inning_pitched_div3"] = r[6 + n_named] or 0
                career.setdefault(key, Counter()).update(vals)

        out_rows = []
        for key, c9 in sorted(career.items()):
            kind, acnt, grp, idx, name = key
            if pitching:
                outs = c9["inning_pitched_div3"]
                out_rows.append((9999, kind, acnt, grp, idx, name, notes.get(key),
                                 c9["wins"], c9["loses"], c9["starts"], c9["complete_games"],
                                 c9["shutouts"], c9["save_ok"], outs // 3, outs % 3,
                                 c9["plate_appearances"], c9["pitch_cnt"], c9["strikes"],
                                 c9["balls"], c9["hits"], c9["home_runs"], c9["sac_hit"],
                                 c9["sac_fly"], c9["bb"], c9["ibb"], c9["hbp"], c9["so"],
                                 c9["wild_pitch"], c9["balk"], c9["runs"], c9["earned_runs"]))
            else:
                r = _bat_rates(c9)
                out_rows.append((9999, kind, acnt, grp, idx, name, notes.get(key),
                                 c9["plate_appearances"], c9["at_bats"], c9["hits"],
                                 c9["rbi"], c9["singles"], c9["doubles"], c9["triples"],
                                 c9["home_runs"], c9["total_bases"], c9["sac_hit"],
                                 c9["sac_fly"], c9["bb"], c9["ibb"], c9["hbp"], c9["so"],
                                 c9["ground_outs"], c9["fly_outs"],
                                 r["goao"], r["avg"], r["obp"], r["slg"], r["ops"]))
        ins_cols = ("plate_appearances, at_bats, hits, rbi, singles, doubles, triples, "
                    "home_runs, total_bases, sac_hit, sac_fly, bb, ibb, hbp, so, "
                    "ground_outs, fly_outs, goao, avg, obp, slg, ops" if not pitching else
                    "wins, loses, starts, complete_games, shutouts, save_ok, "
                    "inning_pitched_cnt, inning_pitched_div3, plate_appearances, pitch_cnt, "
                    "strikes, balls, hits, home_runs, sac_hit, sac_fly, bb, ibb, hbp, so, "
                    "wild_pitch, balk, runs, earned_runs")
        with conn() as cx:
            cx.execute(f"DELETE FROM cpbl.{table} WHERE year = 9999")  # noqa: S608
            n_ph = 7 + len(ins_cols.split(", "))
            ph = ", ".join(["%s"] * n_ph) + ", now()"
            with cx.cursor() as cur:
                cur.executemany(
                    f"INSERT INTO cpbl.{table} (year, kind_code, acnt, item_group_code, "  # noqa: S608
                    f"item_index, item_name, item_note, {ins_cols}, updated_at) "
                    f"VALUES ({ph})", out_rows)
        summary[side] = len(out_rows)
    return summary
