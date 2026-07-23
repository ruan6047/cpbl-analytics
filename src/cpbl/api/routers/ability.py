"""能力值卡：生涯/本季 rate 的全聯盟百分位（遊戲風雷達）。

生涯尺度含年代校正 [era adjustment]：各 rate 先除以「該年聯盟均值」、按各自分母
（PA/AB/G/IP）加權彙總成 era-relative rate，再取全聯盟 percent_rank——直接拿
1990 至今原始 rate 排名會有跨年代系統性偏差（三振率逐年代升→老球員接觸率灌水；
打高投低年代投手 ERA 被壓）。本季尺度為單一年母體，不需校正。
紅線：2018+/2026-only 數據（catcher_runs、官方進階 PR）僅入本季，不入生涯 PR 母體
——生涯母體若同池不同人組成不同，百分位即失去可比性。
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from cpbl.api.helpers import DEFAULT_SEASON
from cpbl.db import conn
from cpbl.ingest.advanced_snapshot import gating_predicate

# 只讀最後成功晉升的完整快照（INGEST-ADV-RECONCILE1）；晉升前的 scope 保留 legacy 行為。
_ADV_GATE = gating_predicate("a", "player_stats")

router = APIRouter()


def _grade(pr: float) -> str:
    for t, g in ((90, "S"), (80, "A"), (65, "B"), (50, "C"), (35, "D"), (20, "E"), (10, "F")):
        if pr >= t:
            return g
    return "G"


# 軸定義：(key, 中文標, 顯示格式, 來源指標說明)。順序＝SQL 輸出順序。
_ABILITY_AXES = {
    "batting": [
        ("contact", "控制", "pct", "接觸率 (PA-SO)/PA"),
        ("power", "力量", "f3", "純長打率 ISO"),
        ("eye", "選球", "pct", "保送率 BB%"),
        ("speed", "速度", "f2", "盜壘得分價值 wSB rate＋每場盜壘/三壘打"),
        ("defense", "守備", "f2", "守位內守備範圍／捕手阻殺率（本季捕手摻接捕 RA9）"),
    ],
    "pitching": [
        # 三振軸＝真技能、跨投手可比（舊「武器軸」取三振/滾地/飛球最突出者有數學下限
        # ~50：gb 與 fb 互為倒數、percent_rank 互補，GREATEST 恆 ≥~50，半個刻度永不
        # 使用；且風格≠能力）。滾地/飛球「風格」保留於 signature 徽章，資訊不遺失。
        ("weapon", "三振", "f2", "每9局三振 K/9（本季摻官方揮空率）"),
        ("control", "控球", "f2", "每9局保送 BB/9"),
        ("hr_suppress", "抑長打", "f2", "每9局被全壘打 HR/9"),
        ("command", "壓制", "f2", "防禦率 ERA＋守備獨立 FIP"),
        ("stamina", "續航", "f2", "先發 IP/G／後援登板數"),
    ],
}

# 各軸『綜合組成』：(來源, 鍵, 標籤, 基礎權重)。trad=傳統(SQL 算的 *_pr)；adv=進階官方 _pr
# （已定向為高=好，免反轉）。缺項自動移除並重正規化權重（進階僅本季且覆蓋稀疏；wsb 個別
# 缺 opp、cra9 僅本季捕手、fip 全覆蓋——無資料即退回其餘組成）。
_COMPOSITE = {
    "batting": {
        "contact": [("trad", "contact", "接觸率", 0.45), ("adv", "whiffp_pr", "揮空抑制", 0.55)],
        "power": [("trad", "power", "ISO", 0.30), ("adv", "ev_pr", "擊球初速", 0.25),
                  ("adv", "hardhitp_pr", "強擊球%", 0.25), ("adv", "brlp_pr", "Barrel%", 0.20)],
        "eye": [("trad", "eye", "保送率", 0.5), ("adv", "chasep_pr", "追打抑制", 0.5)],
        # 速度：wSB（盜壘得分價值 rate，含成功率與跑壘價值；係數本身逐年對聯盟校準，
        # 天然年代中性）為主，粗率 (SB+3B)/G 為輔。
        "speed": [("trad", "wsb", "盜壘得分價值 wSB", 0.6), ("trad", "speed", "盜壘＋三壘打", 0.4)],
        # 守備：本季捕手摻接捕時失分 RA9（livelog 推算，2018+ 故僅本季 scope）。
        "defense": [("trad", "defense", "守備範圍/阻殺", 0.6), ("trad", "cra9", "接捕失分抑制", 0.4)],
    },
    "pitching": {
        "weapon": [("trad", "weapon", "三振 K/9", 0.6), ("adv", "whiffp_pr", "揮空率", 0.4)],
        "control": [("trad", "control", "BB/9", 0.5), ("adv", "bbp_pr", "保送抑制", 0.25),
                    ("adv", "chasep_pr", "誘揮", 0.25)],
        "hr_suppress": [("trad", "hr_suppress", "HR/9", 0.4), ("adv", "brlp_pr", "Barrel抑制", 0.3),
                        ("adv", "hardhitp_pr", "強擊抑制", 0.3)],
        # 壓制：ERA 含守備與運氣 → 摻守備獨立 FIP（全史自算，FIP 常數逐年對聯盟 ERA 校準）。
        "command": [("trad", "command", "ERA", 0.5), ("trad", "fip", "FIP", 0.5)],
        "stamina": [("trad", "stamina", "續航", 1.0)],
    },
}

# 門檻：生涯較嚴、本季較鬆（本季賽程未過半）。
_ABILITY_MIN = {"batting": {"career": 300, "season": 50}, "pitching": {"career": 100, "season": 20}}


def _bat_ability_sql(scope: str) -> str:
    """打者能力 SQL：career=逐年年代校正後彙總(AB≥300)，season=本季(AB≥50)。

    守備用『守位內守備範圍 (PO+A)/G』並於同守位內取百分位（取主守位＝場次最多者），
    捕手改阻殺率；生涯守備同樣年代校正（聯盟 K 升→滾進球減→範圍值跨年代不可比）。
    wSB＝sum(wsb)/sum(opp)（rate），percent_rank 以 PARTITION BY IS NULL 隔離缺值列
    （否則 NULL 排序在後會拿到最高 PR）。
    """
    if scope == "career":
        base = """
        yr AS (   -- 每人每年（同年多隊加總）
            SELECT player_id, year, sum(pa) pa, sum(ab) ab, sum(h) h, sum(b2) b2,
                   sum(b3) b3, sum(hr) hr, sum(bb) bb, sum(hbp) hbp, sum(sf) sf,
                   sum(sb) sb, sum(so) so, sum(g) g
            FROM cpbl.batting_seasons GROUP BY player_id, year
        ), lg AS (   -- 各年聯盟均值（年代校正基準；全聯盟總和之 rate）
            SELECT year,
                sum(pa - so)::float/NULLIF(sum(pa),0) contact,
                sum(b2 + 2*b3 + 3*hr)::float/NULLIF(sum(ab),0) power,
                sum(bb)::float/NULLIF(sum(pa),0) eye,
                sum(sb + b3)::float/NULLIF(sum(g),0) speed,
                sum(h + bb + hbp)::float/NULLIF(sum(ab + bb + hbp + sf),0) obp,
                sum(h + b2 + 2*b3 + 3*hr)::float/NULLIF(sum(ab),0) slg
            FROM yr GROUP BY year
        ), base AS (   -- era-relative：各年 rate÷該年聯盟均值，按各自分母加權彙總
            SELECT y.player_id,
                sum((y.pa - y.so)/NULLIF(l.contact,0))/NULLIF(sum(y.pa),0)::float contact,
                sum((y.b2 + 2*y.b3 + 3*y.hr)/NULLIF(l.power,0))/NULLIF(sum(y.ab),0)::float power,
                sum(y.bb/NULLIF(l.eye,0))/NULLIF(sum(y.pa),0)::float eye,
                sum((y.sb + y.b3)/NULLIF(l.speed,0))/NULLIF(sum(y.g),0)::float speed,
                sum((y.h + y.bb + y.hbp)/NULLIF(l.obp,0))/NULLIF(sum(y.ab + y.bb + y.hbp + y.sf),0)::float
                  + sum((y.h + y.b2 + 2*y.b3 + 3*y.hr)/NULLIF(l.slg,0))/NULLIF(sum(y.ab),0)::float ops,
                sum(y.g) g   -- 生涯打擊出賽數：DH 佔比判定用
            FROM yr y JOIN lg l USING (year)
            GROUP BY y.player_id HAVING sum(y.ab) >= %(min)s
        )"""
        # 生涯守備：逐年除以「守位×年」聯盟均值再按出賽（捕手按阻殺機會）加權。
        fld = """
        pos_yr AS (
            SELECT player_id, pos, year, sum(g) g, sum(po) po, sum(a) a, sum(cs) cs, sum(sb) sba
            FROM cpbl.fielding_seasons GROUP BY player_id, pos, year
        ), pos_lg AS (
            SELECT pos, year,
                sum(po + a)::float/NULLIF(sum(g),0) mrf,
                CASE WHEN sum(cs) + sum(sba) > 0
                     THEN sum(cs)::float/(sum(cs) + sum(sba)) END mcs
            FROM pos_yr GROUP BY pos, year
        ), pos_rf AS (
            SELECT y.player_id, y.pos, sum(y.g) g,
                CASE WHEN y.pos = 'C' AND sum(y.cs) + sum(y.sba) > 0
                     THEN sum(y.cs/NULLIF(l.mcs,0))/(sum(y.cs) + sum(y.sba))::float
                     ELSE sum((y.po + y.a)/NULLIF(l.mrf,0))/NULLIF(sum(y.g),0)::float END rf
            FROM pos_yr y JOIN pos_lg l USING (pos, year)
            GROUP BY y.player_id, y.pos HAVING sum(y.g) >= 30
        )"""
        catcher = "'C'"
        wsb = "SELECT player_id, sum(wsb)::float/NULLIF(sum(opp),0) wsb FROM cpbl.batter_wsb GROUP BY player_id"
        cra9_col, cra9_cte = "", ""
        # 總守備出賽數（不設門檻）：用來區分「純 DH（生涯完全未上守備）」與
        # 「有守備但主守位未達 30 場門檻」——兩者 defense_pr 皆 NULL，僅此值可分流。
        fld_all = "SELECT player_id, sum(g) g FROM cpbl.fielding_seasons GROUP BY player_id"
    else:
        base = """
        base AS (
            SELECT player_id, ab, h, b2, b3, hr, bb, hbp, sf, pa, sb, so, g,
                (pa - so)::float/NULLIF(pa,0) contact,
                (b2 + 2*b3 + 3*hr)::float/NULLIF(ab,0) power,
                bb::float/NULLIF(pa,0) eye,
                (sb + b3)::float/NULLIF(g,0) speed,
                (h+bb+hbp)::float/NULLIF(ab+bb+hbp+sf,0)+(h+b2+2*b3+3*hr)::float/NULLIF(ab,0) ops
            FROM cpbl.batting_current WHERE year=%(yr)s AND ab >= %(min)s
        )"""
        fld = """
        pos_rf AS (
            SELECT player_id, pos, sum(g) g,
                CASE WHEN pos = '捕手' AND sum(cs)+sum(sba) > 0
                     THEN sum(cs)::float/(sum(cs)+sum(sba))
                     ELSE (sum(po)+sum(a))::float/NULLIF(sum(g),0) END rf
            FROM cpbl.fielding_current WHERE year=%(yr)s AND kind_code='A'
            GROUP BY player_id, pos HAVING sum(g) >= 8
        )"""
        catcher = "'捕手'"
        wsb = "SELECT player_id, sum(wsb)::float/NULLIF(sum(opp),0) wsb FROM cpbl.batter_wsb WHERE year=%(yr)s GROUP BY player_id"
        # 捕手接捕 RA9（越低越好 → DESC；母體＝該年 C 守備出局數≥150 的捕手，沿 players.py 門檻）
        cra9_col = ", CASE WHEN f.is_catcher THEN c9.cra9_pr END cra9_pr"
        cra9_cte = """, cra9 AS (
            SELECT cr.player_id,
                   percent_rank() OVER (ORDER BY cr.runs*27.0/fi.outs DESC) cra9_pr
            FROM cpbl.catcher_runs cr
            JOIN cpbl.fielding_innings fi ON fi.year=cr.year AND fi.kind_code=cr.kind_code
                 AND fi.player_id=cr.player_id AND fi.pos='C'
            WHERE cr.kind_code='A' AND cr.year=%(yr)s AND fi.outs >= 150
        )"""
        # 本季總守備出賽數（不設 8 場門檻，過濾二軍）：純 DH vs 樣本不足的分流訊號。
        fld_all = ("SELECT player_id, sum(g) g FROM cpbl.fielding_current "
                   "WHERE year=%(yr)s AND kind_code='A' GROUP BY player_id")
    rate_cols = "b.player_id, b.contact, b.power, b.eye, b.speed, b.ops, b.g AS bat_g"
    cra9_join ="LEFT JOIN cra9 c9 USING (player_id)" if scope == "season" else ""
    cra9_pass = ", cra9_pr" if scope == "season" else ""
    return f"""
        WITH {base},
        {fld}, pos_pr AS (
            SELECT player_id, pos, g, rf,
                   percent_rank() OVER (PARTITION BY pos ORDER BY rf) rf_pr
            FROM pos_rf WHERE rf IS NOT NULL
        ), fld AS (   -- 取主守位（場次最多）：守備值、守位內百分位、是否捕手
            SELECT DISTINCT ON (player_id) player_id, rf AS defense, rf_pr AS defense_pr,
                   (pos = {catcher}) AS is_catcher
            FROM pos_pr ORDER BY player_id, g DESC
        ), wsb AS ({wsb}){cra9_cte},
        fld_all AS ({fld_all}),
        rate AS (
            SELECT {rate_cols}, f.defense, f.defense_pr, f.is_catcher, w.wsb{cra9_col},
                   COALESCE(fa.g, 0) fld_g
            FROM base b LEFT JOIN fld f USING (player_id)
                 LEFT JOIN wsb w USING (player_id)
                 LEFT JOIN fld_all fa USING (player_id) {cra9_join}
        ), pr AS (
            SELECT player_id, contact, power, eye, speed, defense, defense_pr,
                   is_catcher, wsb, fld_g, bat_g{cra9_pass},
                percent_rank() OVER (ORDER BY contact) contact_pr,
                percent_rank() OVER (ORDER BY power) power_pr,
                percent_rank() OVER (ORDER BY eye) eye_pr,
                percent_rank() OVER (ORDER BY speed) speed_pr,
                CASE WHEN wsb IS NOT NULL THEN
                    percent_rank() OVER (PARTITION BY (wsb IS NULL) ORDER BY wsb) END wsb_pr,
                percent_rank() OVER (ORDER BY ops) ops_pr
            FROM rate
        ), ov AS (   -- 總評重排：OPS 為主(×3) + 速度軸(wSB 0.6/粗率 0.4，同軸組成) +
            -- 守備(缺→中性 0.5)，再取全聯盟百分位。
            SELECT *, percent_rank() OVER (ORDER BY
                3*ops_pr + 0.6*COALESCE(wsb_pr, speed_pr) + 0.4*speed_pr
                + COALESCE(defense_pr, 0.5)) ov_pr
            FROM pr
        ) SELECT contact, power, eye, speed, defense, wsb, fld_g, bat_g,
                 contact_pr, power_pr, eye_pr, speed_pr, defense_pr, wsb_pr{cra9_pass},
                 is_catcher, ov_pr
          FROM ov WHERE player_id = %(pid)s
    """


def _pit_ability_sql(scope: str) -> str:
    """投手能力 SQL：career=逐年年代校正後彙總(IP≥100)，season=本季(IP≥20)。越低越好者 DESC 反轉。

    FIP＝(13*HR+3*(BB+HBP)-2*SO)/IP＋常數，常數逐年校準到該年聯盟 ERA（HBP 缺值容 0
    沿 ingest 慣例）；生涯再除以該年聯盟 ERA 做年代校正。續航維持原始值（先發 IP/G、
    後援登板數＝實際負荷/長壽，跨年代差異屬真實使用量，刻意不校正）且於同類型內取百分位。
    gb/fb 僅供風格標籤（signature），percent_rank 以 PARTITION 隔離 NULL 列。
    """
    ip_expr = "floor(ip) + (ip - floor(ip))*10/3.0"
    if scope == "career":
        head = f"""
        yr AS (   -- 每人每年（同年多隊加總）
            SELECT player_id, year, sum({ip_expr}) ip, sum(so) so, sum(bb) bb,
                   sum(COALESCE(hbp, 0)) hbp, sum(hr) hr, sum(er) er,
                   sum(g) g, sum(gs) gs, sum(go) go, sum(fo) fo
            FROM cpbl.pitching_seasons GROUP BY player_id, year
        ), lg AS (   -- 各年聯盟均值＋FIP 核心（常數＝era-fipc0，逐年校準）
            SELECT year,
                sum(so)*9.0/NULLIF(sum(ip),0) k,
                sum(bb)*9.0/NULLIF(sum(ip),0) bb9,
                sum(hr)*9.0/NULLIF(sum(ip),0) hr9,
                sum(er)*9.0/NULLIF(sum(ip),0) era,
                sum(go)::float/NULLIF(sum(fo),0) gb,
                sum(fo)::float/NULLIF(sum(go),0) fb,
                (13*sum(hr) + 3*(sum(bb) + sum(COALESCE(hbp,0))) - 2*sum(so))/NULLIF(sum(ip),0) fipc0
            FROM yr GROUP BY year
        ), agg AS (   -- era-relative：各年 rate÷該年聯盟均值，按 IP 加權彙總
            SELECT y.player_id,
                sum(9.0*y.so/NULLIF(l.k,0))/NULLIF(sum(y.ip),0) k,
                sum(9.0*y.bb/NULLIF(l.bb9,0))/NULLIF(sum(y.ip),0) control,
                sum(9.0*y.hr/NULLIF(l.hr9,0))/NULLIF(sum(y.ip),0) hr_suppress,
                sum(9.0*y.er/NULLIF(l.era,0))/NULLIF(sum(y.ip),0) command,
                sum(y.ip*((13*y.hr + 3*(y.bb + y.hbp) - 2*y.so)/NULLIF(y.ip,0) + l.era - l.fipc0)
                    /NULLIF(l.era,0))/NULLIF(sum(y.ip),0) fip,
                sum(CASE WHEN y.go > 0 AND y.fo > 0 THEN y.ip*(y.go::float/y.fo)/NULLIF(l.gb,0) END)
                    /NULLIF(sum(y.ip) FILTER (WHERE y.go > 0 AND y.fo > 0),0) gb,
                sum(CASE WHEN y.go > 0 AND y.fo > 0 THEN y.ip*(y.fo::float/y.go)/NULLIF(l.fb,0) END)
                    /NULLIF(sum(y.ip) FILTER (WHERE y.go > 0 AND y.fo > 0),0) fb,
                sum(y.ip) ip, sum(y.g) g, sum(y.gs) gs
            FROM yr y JOIN lg l USING (year)
            GROUP BY y.player_id HAVING sum(y.ip) >= %(min)s
        ), rate AS (
            SELECT player_id, k, gb, fb, control, hr_suppress, command, fip,
                (gs*2 >= g) AS is_starter,
                CASE WHEN gs*2 >= g THEN ip/NULLIF(g,0) ELSE g::float END stamina
            FROM agg
        )"""
    else:
        head = f"""
        base AS (
            SELECT player_id, ({ip_expr}) ip, so, bb, COALESCE(hbp,0) hbp, hr, er, g, gs, goao gb
            FROM cpbl.pitching_current WHERE year=%(yr)s AND ({ip_expr}) >= %(min)s
        ), lg AS (   -- 該年全聯盟（不設門檻）：FIP 常數校準
            SELECT sum(er)*9.0/NULLIF(sum({ip_expr}),0) era,
                (13*sum(hr) + 3*(sum(bb) + sum(COALESCE(hbp,0))) - 2*sum(so))
                    /NULLIF(sum({ip_expr}),0) fipc0
            FROM cpbl.pitching_current WHERE year=%(yr)s
        ), rate AS (
            SELECT player_id, so*9.0/NULLIF(ip,0) k, gb,
                CASE WHEN gb > 0 THEN 1.0/gb END fb,   -- 飛球傾向 AO/GO（gb=GO/AO 之倒數）
                bb*9.0/NULLIF(ip,0) control, hr*9.0/NULLIF(ip,0) hr_suppress,
                er*9.0/NULLIF(ip,0) command,
                (13*hr + 3*(bb + hbp) - 2*so)/NULLIF(ip,0) + l.era - l.fipc0 fip,
                (gs*2 >= g) AS is_starter,
                CASE WHEN gs*2 >= g THEN ip/NULLIF(g,0) ELSE g::float END stamina
            FROM base CROSS JOIN lg l
        )"""
    return f"""
        WITH {head},
        prx AS (
            SELECT *, percent_rank() OVER (ORDER BY k) k_pr,
                CASE WHEN gb IS NOT NULL THEN
                    percent_rank() OVER (PARTITION BY (gb IS NULL) ORDER BY gb) END gb_pr,
                CASE WHEN fb IS NOT NULL THEN
                    percent_rank() OVER (PARTITION BY (fb IS NULL) ORDER BY fb) END fb_pr,
                percent_rank() OVER (ORDER BY control DESC) control_pr,
                percent_rank() OVER (ORDER BY hr_suppress DESC) hr_suppress_pr,
                percent_rank() OVER (ORDER BY command DESC) command_pr,
                percent_rank() OVER (ORDER BY fip DESC) fip_pr,
                percent_rank() OVER (PARTITION BY is_starter ORDER BY stamina) stamina_pr
            FROM rate
        ), pr AS (   -- 風格標籤（signature 徽章用）＝三振/滾地/飛球最突出者；軸本身固定 K
            SELECT *,
                CASE WHEN k_pr >= COALESCE(gb_pr,0) AND k_pr >= COALESCE(fb_pr,0) THEN '三振'
                     WHEN COALESCE(gb_pr,0) >= COALESCE(fb_pr,0) THEN '滾地' ELSE '飛球' END weapon_type
            FROM prx
        ), ov AS (   -- 總評重排：壓制為主(×3，ERA/FIP 各半，同軸組成) + 其餘，再全聯盟百分位
            SELECT *, percent_rank() OVER (ORDER BY
                3*(0.5*command_pr + 0.5*fip_pr) + k_pr + control_pr
                + hr_suppress_pr + stamina_pr) ov_pr
            FROM pr
        ) SELECT k AS weapon, control, hr_suppress, command, stamina, fip,
                 k_pr AS weapon_pr, control_pr, hr_suppress_pr, command_pr, stamina_pr, fip_pr,
                 is_starter, ov_pr, weapon_type
          FROM ov WHERE player_id = %(pid)s
    """


def _ability_card(cur, player_id: str, role: str, scope: str, year: int) -> dict:
    axes_def = _ABILITY_AXES[role]
    sql = _bat_ability_sql(scope) if role == "batting" else _pit_ability_sql(scope)
    cur.execute(sql, {"pid": player_id, "yr": year, "min": _ABILITY_MIN[role][scope]})
    row = cur.fetchone()
    if not row:
        return {"available": False, "role": role, "scope": scope}
    r = dict(zip([d.name for d in cur.description], row, strict=True))
    flag = r.get("is_catcher") if role == "batting" else r.get("is_starter")
    ov_pr = r.get("ov_pr")                 # 整體表現的全聯盟重排百分位
    weapon_type = r.get("weapon_type")     # 投手風格（三振/滾地/飛球，signature 徽章）
    # 傳統各指標 PR（percent_rank 0~1 → 0~100）；None=無資料（如 DH 無守備、無 wSB 機會）。
    trad = {k: (None if v is None else round(float(v) * 100))
            for k, v in r.items() if k.endswith("_pr")}

    # 進階官方 PR（僅本季、足量打席才採；已定向高=好）。覆蓋稀疏故多數球員為空。
    adv: dict[str, int] = {}
    if scope == "season":
        cur.execute(
            "SELECT a.pa, a.woba_pr, a.iso_pr, a.ev_pr, a.hardhitp_pr, a.brlp_pr, a.kp_pr, "
            "a.bbp_pr, a.whiffp_pr, a.chasep_pr "
            f"FROM cpbl.advanced_stats a WHERE a.acnt=%s AND a.year=%s AND a.role=%s "
            f"AND a.kind_code='A' AND {_ADV_GATE}",
            (player_id, year, role))
        ar = cur.fetchone()
        if ar and (ar[0] or 0) >= 30:
            for col, v in zip(["woba_pr", "iso_pr", "ev_pr", "hardhitp_pr", "brlp_pr",
                               "kp_pr", "bbp_pr", "whiffp_pr", "chasep_pr"], ar[1:], strict=True):
                if v is not None:
                    adv[col] = int(v)

    axes = []
    for key, label, _fmt, _src in axes_def:
        comps = []
        for src, ck, clabel, w in _COMPOSITE[role][key]:
            pr = trad.get(f"{ck}_pr") if src == "trad" else adv.get(ck)
            if src == "trad" and ck == "defense" and flag:
                clabel = "阻殺率"          # 捕手守備組成標籤特化
            if src == "trad" and key == "stamina" and flag is False:
                clabel = "登板數"          # 後援續航
            if pr is not None:
                comps.append({"label": clabel, "weight": w, "pr": pr})
        if not comps:
            axes.append({"key": key, "label": label, "pr": None, "grade": None, "components": []})
            continue
        tot = sum(c["weight"] for c in comps)
        final = round(sum(c["pr"] * c["weight"] for c in comps) / tot)
        for c in comps:                    # 權重正規化為百分比供 tooltip 顯示
            c["weight"] = round(c["weight"] / tot * 100)
        axes.append({"key": key, "label": label, "pr": final,
                     "grade": _grade(final), "components": comps})

    # 總評＝整體表現在全聯盟的『重排百分位』：把每位合格球員的各軸 PR 加總後再 percent_rank，
    # 故最強者→PR100→S、自然拉開分級（不像各軸平均會壓在中間害大家都 B/C）。
    rated = [a["pr"] for a in axes if a["pr"] is not None]
    overall = (round(float(ov_pr) * 100) if ov_pr is not None
               else (round(sum(rated) / len(rated)) if rated else 0))
    if role == "batting":
        power_pr = next((a["pr"] for a in axes if a["key"] == "power" and a["pr"] is not None), None)
        # 總評融入『力量軸』（已綜合官方 Barrel%/強擊球/初速＝擊球品質）：SQL 重排只看 OPS 結果，
        # 會低估「紮實接觸但結果衰運(低 BABIP)」的重砲手（如朱育賢 Barrel96 卻 OPS 中庸）。以
        # xStats 精神用擊球品質拉抬，無進階者力量軸退回 ISO 故仍合理（守住紅線：非抄計數型 HR/RBI）。
        # 只『拉抬』不『懲罰』：取 max，速度/守備型不會被低力量拖累。
        if ov_pr is not None and power_pr is not None:
            overall = max(overall, round(0.6 * overall + 0.4 * power_pr))
        # 守備軸缺值分流：「主要 DH」與「常守備但主守位樣本不足」的 defense_pr 皆為 NULL。
        # 需求方定案：主要打 DH 者即使有少量守備仍視為 DH——以守備出賽是否為少數判定
        # （守備場次 ≤ 打擊出賽之半＝以 DH 為主）。「資料不足」只留給守備佔多數卻分散到
        # 每守位皆未達門檻的工具人（雖無合格樣本，但確實常守備、不宜當 DH 代填力量）。
        fld_g = r.get("fld_g") or 0
        bat_g = r.get("bat_g") or 0
        mainly_dh = fld_g * 2 <= bat_g
        for a in axes:
            if a["key"] != "defense" or a["pr"] is not None:
                continue
            if mainly_dh and power_pr is not None:
                # 主要 DH（含少量守備）：以打擊火力代守備並標「指打」，免雷達 0 凹陷
                # 誤看成守備弱點；組成標籤已揭露此為代用值。
                a["label"], a["pr"], a["grade"] = "指打", power_pr, _grade(power_pr)
                a["components"] = [{"label": "打擊火力（代守備）", "weight": 100, "pr": power_pr}]
            else:
                # 守備佔多數卻無合格守位（或無力量值可代）：誠實標「資料不足」，
                # 不得填入與守備語意無關的力量 PR；雷達仍畫 0 但 tooltip 揭露原因。
                a["note"] = "守備樣本不足"
    # 特色標籤（彰顯球員類型，不合軸）。
    # 打者：取進攻工具中最突出者；多項 ≥80 → 全能。
    # 投手：取最突出的出局方式（weapon_type＝三振/滾地/飛球，後端 SQL 已算）。
    signature = None
    if role == "batting":
        names = {"power": "強打", "contact": "巧打", "eye": "選球", "speed": "快腿"}
        off = {a["key"]: a["pr"] for a in axes
               if a["key"] in names and a["pr"] is not None}
        if off:
            strong = [names[k] for k, v in off.items() if v >= 80]
            top = max(off, key=off.get)
            signature = "全能" if len(strong) >= 3 else "·".join(strong[:2]) if strong else names[top]
    elif role == "pitching":
        signature = weapon_type
    return {"available": True, "role": role, "scope": scope, "axes": axes,
            "has_advanced": bool(adv), "signature": signature,
            "overall": {"pr": overall, "grade": _grade(overall)}}


@router.get("/api/v1/players/{player_id}/ability-card")
def player_ability_card(player_id: str, season: int = Query(DEFAULT_SEASON)) -> dict:
    """遊戲風能力值卡：打者/投手雷達，含生涯與本季兩種尺度（rate 的全聯盟百分位）。"""
    with conn() as c:
        cur = c.cursor()
        out: dict = {"player_id": player_id}
        for role in ("batting", "pitching"):
            out[role] = {"career": _ability_card(cur, player_id, role, "career", season),
                         "season": _ability_card(cur, player_id, role, "season", season)}
        return out
