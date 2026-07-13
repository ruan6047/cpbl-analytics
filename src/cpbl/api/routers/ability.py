"""能力值卡：生涯/本季 rate 的全聯盟百分位（遊戲風雷達）。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from cpbl.api.helpers import DEFAULT_SEASON
from cpbl.db import conn

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
        ("speed", "速度", "f2", "每場盜壘＋三壘打 (SB+3B)/G"),
        ("defense", "守備", "f2", "守位內守備範圍／捕手阻殺率"),
    ],
    "pitching": [
        # 「武器」＝出局方式特色軸：取該投手最突出者（三振/滾地/飛球），標籤與數值動態。
        ("weapon", "武器", "f2", "出局武器（三振 K9／滾地 GO/AO／飛球 AO/GO，取最突出者）"),
        ("control", "控球", "f2", "每9局保送 BB/9"),
        ("hr_suppress", "抑長打", "f2", "每9局被全壘打 HR/9"),
        ("command", "壓制", "f2", "防禦率 ERA"),
        ("stamina", "續航", "f2", "先發 IP/G／後援登板數"),
    ],
}

# 各軸『綜合組成』：(來源, 鍵, 標籤, 基礎權重)。trad=傳統(SQL 算的軸 PR)；adv=進階官方 _pr
# （已定向為高=好，免反轉）。進階僅本季有、覆蓋稀疏 → 缺項自動移除並重正規化權重（無進階
# 即退回純傳統單指標）。
_COMPOSITE = {
    "batting": {
        "contact": [("trad", "contact", "接觸率", 0.45), ("adv", "whiffp_pr", "揮空抑制", 0.55)],
        "power": [("trad", "power", "ISO", 0.30), ("adv", "ev_pr", "擊球初速", 0.25),
                  ("adv", "hardhitp_pr", "強擊球%", 0.25), ("adv", "brlp_pr", "Barrel%", 0.20)],
        "eye": [("trad", "eye", "保送率", 0.5), ("adv", "chasep_pr", "追打抑制", 0.5)],
        "speed": [("trad", "speed", "盜壘＋三壘打", 1.0)],
        "defense": [("trad", "defense", "守備範圍/阻殺", 1.0)],
    },
    "pitching": {
        "weapon": [("trad", "weapon", "武器", 1.0)],   # 標籤動態（三振/滾地/飛球）
        "control": [("trad", "control", "BB/9", 0.5), ("adv", "bbp_pr", "保送抑制", 0.25),
                    ("adv", "chasep_pr", "誘揮", 0.25)],
        "hr_suppress": [("trad", "hr_suppress", "HR/9", 0.4), ("adv", "brlp_pr", "Barrel抑制", 0.3),
                        ("adv", "hardhitp_pr", "強擊抑制", 0.3)],
        "command": [("trad", "command", "ERA", 0.5), ("adv", "woba_pr", "被 wOBA", 0.5)],
        "stamina": [("trad", "stamina", "續航", 1.0)],
    },
}

# 門檻：生涯較嚴、本季較鬆（本季賽程未過半）。
_ABILITY_MIN = {"batting": {"career": 300, "season": 50}, "pitching": {"career": 100, "season": 20}}


def _bat_ability_sql(scope: str) -> str:
    """打者能力 SQL：career=逐年彙總(AB≥300)，season=本季(AB≥50)。

    守備改用『守位內守備範圍 (PO+A)/G』並於同守位內取百分位（反映範圍而非僅不失誤；
    取主守位＝場次最多者），故守備 PR 由 fld 先算好，主 pr CTE 不再全域重排。
    """
    # 守備：野手＝守位內守備範圍 (PO+A)/G；捕手＝阻殺率 cs/(cs+被盜)。兩表欄位/守位碼不同。
    if scope == "career":
        base = ("SELECT player_id, sum(ab) ab, sum(h) h, sum(b2) b2, sum(b3) b3, sum(hr) hr,"
                " sum(bb) bb, sum(hbp) hbp, sum(sf) sf, sum(pa) pa, sum(sb) sb, sum(so) so, sum(g) g"
                " FROM cpbl.batting_seasons GROUP BY player_id HAVING sum(ab) >= %(min)s")
        fld_src, catcher, sba_col, fld_min = "cpbl.fielding_seasons", "'C'", "sb", 30
    else:
        base = ("SELECT player_id, ab, h, b2, b3, hr, bb, hbp, sf, pa, sb, so, g"
                " FROM cpbl.batting_current WHERE year=%(yr)s AND ab >= %(min)s")
        fld_src, catcher, sba_col, fld_min = (
            "(SELECT * FROM cpbl.fielding_current WHERE year=%(yr)s) fc", "'捕手'", "sba", 8)
    return f"""
        WITH base AS ({base}),
        pos_rf AS (
            SELECT player_id, pos, sum(g) g,
                CASE WHEN pos = {catcher} AND sum(cs)+sum({sba_col}) > 0
                     THEN sum(cs)::float/(sum(cs)+sum({sba_col}))
                     ELSE (sum(po)+sum(a))::float/NULLIF(sum(g),0) END rf
            FROM {fld_src} GROUP BY player_id, pos HAVING sum(g) >= {fld_min}
        ), pos_pr AS (
            SELECT player_id, pos, g, rf,
                   percent_rank() OVER (PARTITION BY pos ORDER BY rf) rf_pr
            FROM pos_rf
        ), fld AS (   -- 取主守位（場次最多）：守備值、守位內百分位、是否捕手
            SELECT DISTINCT ON (player_id) player_id, rf AS defense, rf_pr AS defense_pr,
                   (pos = {catcher}) AS is_catcher
            FROM pos_pr ORDER BY player_id, g DESC
        ), rate AS (
            SELECT b.player_id,
                (pa - so)::float/NULLIF(pa,0) contact,
                (b2+2*b3+3*hr)::float/NULLIF(ab,0) power,
                bb::float/NULLIF(pa,0) eye,
                (sb+b3)::float/NULLIF(g,0) speed,
                f.defense, f.defense_pr, f.is_catcher,
                (h+bb+hbp)::float/NULLIF(ab+bb+hbp+sf,0)+(h+b2+2*b3+3*hr)::float/NULLIF(ab,0) ops
            FROM base b LEFT JOIN fld f USING (player_id)
        ), pr AS (
            SELECT player_id, contact, power, eye, speed, defense, defense_pr, is_catcher,
                percent_rank() OVER (ORDER BY contact) contact_pr,
                percent_rank() OVER (ORDER BY power) power_pr,
                percent_rank() OVER (ORDER BY eye) eye_pr,
                percent_rank() OVER (ORDER BY speed) speed_pr,
                percent_rank() OVER (ORDER BY ops) ops_pr
            FROM rate
        ), ov AS (   -- 總評重排：以打擊產能 OPS 為主(權重3，已綜合接觸/力量/選球，強打不被低接觸拖累)
            -- + 速度/守備為輔(各1)，再取全聯盟百分位（守備缺→中性 0.5）。
            SELECT *, percent_rank() OVER (ORDER BY
                3 * ops_pr + speed_pr + COALESCE(defense_pr, 0.5)) ov_pr
            FROM pr
        ) SELECT contact, power, eye, speed, defense,
                 contact_pr, power_pr, eye_pr, speed_pr, defense_pr, is_catcher, ov_pr
          FROM ov WHERE player_id = %(pid)s
    """


def _pit_ability_sql(scope: str) -> str:
    """投手能力 SQL：career=逐年彙總(IP≥100)，season=本季(IP≥20)。越低越好者 DESC 反轉。

    續航：先發＝每場局數 IP/G、後援＝登板數 G（後援按設計只投 1 局，用 IP/G 不公平）；
    且 stamina 百分位在『同類型（先發/後援）』內計算。is_starter＝先發場數佔半數以上。
    """
    ip_expr = "floor(ip) + (ip - floor(ip))*10/3.0"
    if scope == "career":
        base = (f"SELECT player_id, sum({ip_expr}) ip, sum(so) so, sum(bb) bb, sum(hr) hr,"
                " sum(er) er, sum(g) g, sum(gs) gs, sum(go)::float/NULLIF(sum(fo),0) gb"
                f" FROM cpbl.pitching_seasons GROUP BY player_id HAVING sum({ip_expr}) >= %(min)s")
    else:
        base = (f"SELECT player_id, ({ip_expr}) ip, so, bb, hr, er, g, gs, goao gb"
                f" FROM cpbl.pitching_current WHERE year=%(yr)s AND ({ip_expr}) >= %(min)s")
    return f"""
        WITH base AS ({base}),
        rate AS (
            SELECT player_id, so*9.0/NULLIF(ip,0) k, gb,
                CASE WHEN gb > 0 THEN 1.0/gb END fb,   -- 飛球傾向 AO/GO（gb=GO/AO 之倒數）
                bb*9.0/NULLIF(ip,0) control, hr*9.0/NULLIF(ip,0) hr_suppress,
                er*9.0/NULLIF(ip,0) command, (gs*2 >= g) AS is_starter,
                CASE WHEN gs*2 >= g THEN ip/NULLIF(g,0) ELSE g::float END stamina
            FROM base
        ), prx AS (
            SELECT *, percent_rank() OVER (ORDER BY k) k_pr,
                percent_rank() OVER (ORDER BY gb) gb_pr,
                percent_rank() OVER (ORDER BY fb) fb_pr,
                percent_rank() OVER (ORDER BY control DESC) control_pr,
                percent_rank() OVER (ORDER BY hr_suppress DESC) hr_suppress_pr,
                percent_rank() OVER (ORDER BY command DESC) command_pr,
                percent_rank() OVER (PARTITION BY is_starter ORDER BY stamina) stamina_pr
            FROM rate
        ), pr AS (   -- 武器＝三振/滾地/飛球中 PR 最高者（最突出的出局方式）
            SELECT *,
                GREATEST(k_pr, COALESCE(gb_pr,0), COALESCE(fb_pr,0)) weapon_pr,
                CASE WHEN k_pr >= COALESCE(gb_pr,0) AND k_pr >= COALESCE(fb_pr,0) THEN '三振'
                     WHEN COALESCE(gb_pr,0) >= COALESCE(fb_pr,0) THEN '滾地' ELSE '飛球' END weapon_type,
                CASE WHEN k_pr >= COALESCE(gb_pr,0) AND k_pr >= COALESCE(fb_pr,0) THEN k
                     WHEN COALESCE(gb_pr,0) >= COALESCE(fb_pr,0) THEN gb ELSE fb END weapon_val
            FROM prx
        ), ov AS (   -- 總評重排：以壓制 ERA 為主(權重3，bottom-line 防失分) + 其餘為輔，再全聯盟百分位
            SELECT *, percent_rank() OVER (ORDER BY
                3 * command_pr + weapon_pr + control_pr + hr_suppress_pr + stamina_pr) ov_pr
            FROM pr
        ) SELECT weapon_val, control, hr_suppress, command, stamina,
                 weapon_pr, control_pr, hr_suppress_pr, command_pr, stamina_pr,
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
    n = len(axes_def)
    values, prs = row[:n], row[n:2 * n]
    flag = row[2 * n] if len(row) > 2 * n else None      # 打者=是否捕手 / 投手=是否先發
    ov_pr = row[2 * n + 1] if len(row) > 2 * n + 1 else None  # 整體表現的全聯盟重排百分位
    weapon_type = row[2 * n + 2] if len(row) > 2 * n + 2 else None  # 投手武器型（三振/滾地/飛球）
    # 傳統各軸 PR（percent_rank 0~1 → 0~100）；None=該軸無資料（如 DH 無守備）。
    trad_pr = {axes_def[i][0]: (None if values[i] is None else round(float(prs[i]) * 100))
               for i in range(n)}

    # 進階官方 PR（僅本季、足量打席才採；已定向高=好）。覆蓋稀疏故多數球員為空。
    adv: dict[str, int] = {}
    if scope == "season":
        cur.execute(
            "SELECT pa, woba_pr, iso_pr, ev_pr, hardhitp_pr, brlp_pr, kp_pr, bbp_pr, whiffp_pr, chasep_pr "
            "FROM cpbl.advanced_stats WHERE acnt=%s AND year=%s AND role=%s AND kind_code='A'",
            (player_id, year, role))
        ar = cur.fetchone()
        if ar and (ar[0] or 0) >= 30:
            for col, v in zip(["woba_pr", "iso_pr", "ev_pr", "hardhitp_pr", "brlp_pr",
                               "kp_pr", "bbp_pr", "whiffp_pr", "chasep_pr"], ar[1:], strict=True):
                if v is not None:
                    adv[col] = int(v)

    axes = []
    for key, label, _fmt, _src in axes_def:
        ax_label = weapon_type if (key == "weapon" and weapon_type) else label  # 武器軸動態標籤
        comps = []
        for src, ck, clabel, w in _COMPOSITE[role][key]:
            pr = trad_pr.get(ck) if src == "trad" else adv.get(ck)
            if src == "trad" and key == "defense" and flag:
                clabel = "阻殺率"          # 捕手守備組成標籤特化
            if src == "trad" and key == "stamina" and flag is False:
                clabel = "登板數"          # 後援續航
            if src == "trad" and key == "weapon" and weapon_type:
                clabel = weapon_type       # 武器＝三振/滾地/飛球
            if pr is not None:
                comps.append({"label": clabel, "weight": w, "pr": pr})
        if not comps:
            axes.append({"key": key, "label": ax_label, "pr": None, "grade": None, "components": []})
            continue
        tot = sum(c["weight"] for c in comps)
        final = round(sum(c["pr"] * c["weight"] for c in comps) / tot)
        for c in comps:                    # 權重正規化為百分比供 tooltip 顯示
            c["weight"] = round(c["weight"] / tot * 100)
        axes.append({"key": key, "label": ax_label, "pr": final,
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
        # DH（無守備數據）守備軸改以打擊火力呈現——「DH 用強棒守備」，免雷達 0 凹陷誤看成弱點。
        if power_pr is not None:
            for a in axes:
                if a["key"] == "defense" and a["pr"] is None:
                    a["label"], a["pr"], a["grade"] = "指打", power_pr, _grade(power_pr)
                    a["components"] = [{"label": "打擊火力（代守備）", "weight": 100, "pr": power_pr}]
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
