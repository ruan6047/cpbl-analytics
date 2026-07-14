"""台灣棒球維基館 (TwBsBall) 個人經歷節爬取與解析。

針對現役教練團與歷任總教練，抓取其在 TwBsBall 的完整生平經歷，
解析年份、隊伍（映射至 6 大 active franchise 隊碼）與職稱角色，
存入 cpbl.coach_history，供前端生平時間軸展示。
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.request

from cpbl.db import conn

log = logging.getLogger("cpbl.coaches_history")

API = "https://twbsball.dils.tku.edu.tw/api.php"
UA = "cpbl-analytics/1.0 (baseball analytics; contact via github)"

# 6 大現役中職 Franchise 的關鍵字映射（依精確到模糊順序排列）
TEAM_KEYWORDS = [
    # ACN011: 中信兄弟 / 兄弟象
    ("中信兄弟", "ACN011"),
    ("兄弟象", "ACN011"),
    ("兄弟", "ACN011"),
    # ADD011: 統一獅
    ("統一7-ELEVEn獅", "ADD011"),
    ("統一獅", "ADD011"),
    ("統一", "ADD011"),
    # AEO011: 富邦悍將 / 義大犀牛 / 興農牛 / 俊國熊
    ("富邦悍將", "AEO011"),
    ("富邦", "AEO011"),
    ("義大犀牛", "AEO011"),
    ("義大", "AEO011"),
    ("興農牛", "AEO011"),
    ("興農", "AEO011"),
    ("俊國熊", "AEO011"),
    ("俊國", "AEO011"),
    # AJL011: 樂天桃猿 / Lamigo桃猿 / La New熊 / 第一金剛
    ("樂天桃猿", "AJL011"),
    ("樂天", "AJL011"),
    ("Lamigo桃猿", "AJL011"),
    ("Lamigo", "AJL011"),
    ("La New熊", "AJL011"),
    ("La New", "AJL011"),
    ("第一金剛", "AJL011"),
    # AKP011: 台鋼雄鷹
    ("台鋼雄鷹", "AKP011"),
    ("台鋼", "AKP011"),
    # AAA011: 味全龍
    ("味全龍", "AAA011"),
    ("味全", "AAA011"),
]


def _get(params: dict) -> dict:
    """調用 TwBsBall API，帶退避重試。"""
    params = {**params, "format": "json"}
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())
        except Exception:
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))
    return {}


def fetch_wikitext(title: str) -> str | None:
    """取得 TwBsBall 條目的 wikitext，跟隨重導。"""
    d = _get({
        "action": "query", "prop": "revisions", "rvprop": "content",
        "redirects": "1", "titles": title,
    })
    pages = d.get("query", {}).get("pages", {})
    for p in pages.values():
        if "revisions" in p:
            return p["revisions"][0]["*"]
    return None


def parse_birthdate(wikitext: str) -> tuple[int, int, int] | None:
    """從 wikitext 中提取出生日期 (年, 月, 日) 以供身分比對。"""
    # 消除 [[ 連結符號以便正則匹配
    text = re.sub(r"\[\[|\]\]", "", wikitext)
    m = re.search(r"出生日期：\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    return None


def parse_experience_lines(wikitext: str) -> list[str]:
    """提取 ==經歷== 節底下的所有清單列。"""
    in_exp = False
    exp_lines: list[str] = []
    for line in wikitext.splitlines():
        line_s = line.strip()
        if line_s.startswith("==") and ("經歷" in line_s or "年表" in line_s):
            in_exp = True
            continue
        elif in_exp and line_s.startswith("=="):
            in_exp = False
        if in_exp and (line_s.startswith("*") or line_s.startswith(":*")):
            # 移出條列符號
            clean_line = re.sub(r"^:\*+|\*+", "", line_s).strip()
            if clean_line:
                exp_lines.append(clean_line)
    return exp_lines


def parse_experience_row(raw_line: str) -> dict | None:
    """解析單行經歷，提取年分、球隊與角色職稱。"""
    # 1. 展開 wiki 連結，如 [[中信兄弟隊|中信兄弟]] -> 中信兄弟，[[阪神虎隊]] -> 阪神虎隊
    clean_text = re.sub(r"\[\[([^\]|]*)\|([^\]]*)\]\]", r"\2", raw_line)
    clean_text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", clean_text)

    # 2. 提取末尾的年份括號，如（2020年12月07日～2023年05月10日）
    ym = re.search(r"[（(]([^）)]+)[）)]\s*$", clean_text)
    from_year = None
    to_year = None
    pos_body = clean_text

    if ym:
        yrs_text = ym.group(1)
        pos_body = clean_text[:ym.start()].strip()
        # 尋找 4 碼數字年份
        yrs = [int(y) for y in re.findall(r"(\d{4})\s*年", yrs_text)]
        if yrs:
            from_year = yrs[0]
            if any(c in yrs_text for c in ("～", "-", "—", "~")):
                if len(yrs) > 1:
                    to_year = yrs[1]
                else:
                    to_year = None  # 進行中 (ongoing)
            else:
                to_year = from_year

    # 3. 識別聯盟
    league = None
    for lg in ["中華職棒", "台灣大聯盟", "日本職棒", "美國職棒", "澳洲職棒", "韓國職棒"]:
        if lg in pos_body:
            league = lg
            break

    # 4. 識別現役 6 大球團與 team_code
    team_code = None
    team_raw = None
    for kw, code in TEAM_KEYWORDS:
        if kw in pos_body:
            team_code = code
            idx = pos_body.find(kw)
            matched = kw
            # 若後方緊接「隊」則一併抓入 team_raw，如 中信兄弟隊
            if idx + len(kw) < len(pos_body) and pos_body[idx + len(kw)] == '隊':
                matched = kw + '隊'
            team_raw = matched
            break

    # 5. 提取角色與職稱
    if team_raw:
        role = pos_body
        if league and league in role:
            role = role.replace(league, "", 1)
        if team_raw and team_raw in role:
            role = role.replace(team_raw, "", 1)
    else:
        # 沒匹配到 CPBL 球隊，使用 隊字 分割發明
        temp_body = pos_body
        if league and league in temp_body:
            temp_body = temp_body.replace(league, "", 1).strip()
        if "隊" in temp_body:
            idx = temp_body.find("隊")
            team_raw = temp_body[:idx+1].strip()
            role = temp_body[idx+1:].strip()
        else:
            team_raw = temp_body
            role = ""

    # 清理 role 開頭和結尾的無用字元
    role = re.sub(r"^[兼，,、\s]+", "", role).strip()
    role = re.sub(r"[兼，,、\s]+$", "", role).strip()

    # 6. 分類 phase (player | coach | other | amateur)
    coach_kws = ["總教練", "首席教練", "打擊教練", "投手教練", "守備教練", "跑壘教練", "牛棚教練", "戰術教練", "復健教練", "教練", "監督", "指導員", "技術教練"]
    admin_kws = ["副領隊", "領隊", "總監", "顧問", "球探", "情蒐", "特別助理", "代表", "處長", "經理", "球評"]
    amateur_kws = ["少棒", "青少棒", "青棒", "大學", "國小", "國中", "高中", "學校", "棒球隊", "業餘", "乙組"]

    if any(kw in role for kw in coach_kws):
        phase = "coach"
    elif any(kw in role for kw in admin_kws):
        phase = "other"
    elif any(kw in pos_body for kw in amateur_kws) or (not league and not team_code and any(kw in pos_body for kw in ["少棒", "青少棒", "青棒", "學校", "大學"])):
        phase = "amateur"
    else:
        phase = "player"

    # 若 role 經提取後變為空，則直接沿用 team_raw
    if not role:
        role = team_raw

    return {
        "phase": phase,
        "league": league,
        "team_raw": team_raw or pos_body,
        "team_code": team_code,
        "pos": role,
        "from_year": from_year,
        "to_year": to_year,
    }


def _targets(cur) -> list[tuple[str, str | None, object | None]]:
    """自 coaches 與 managers 中抓出所有教練種子名單。"""
    sql = """
    WITH t AS (
      SELECT name FROM cpbl.coaches
      UNION
      SELECT name FROM cpbl.managers
    )
    SELECT t.name, p.id AS player_id, p.birthday
    FROM t
    LEFT JOIN cpbl.players p ON p.name = t.name
    ORDER BY t.name
    """
    cur.execute(sql)
    return cur.fetchall()


def _store(cur, name: str, player_id: str | None, rows: list[dict], review: bool) -> None:
    cur.execute("DELETE FROM cpbl.coach_history WHERE name=%s", (name,))
    for r in rows:
        cur.execute(
            """
            INSERT INTO cpbl.coach_history
            (player_id, name, raw_text, phase, league, team_raw, team_code, pos, from_year, to_year, needs_review)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (player_id, name, r["raw_text"], r["phase"], r.get("league"), r.get("team_raw"),
             r.get("team_code"), r.get("pos"), r.get("from_year"), r.get("to_year"), review),
        )


def run(throttle: float = 0.8, limit: int | None = None) -> dict:
    """抓取 TwBsBall 教練經歷入庫。"""
    with conn() as c:
        targets = _targets(c.cursor())
    
    if limit:
        targets = targets[:limit]

    st = {"targets": len(targets), "page": 0, "matched": 0, "nopage": 0, "records": 0}
    
    for name, player_id, bday in targets:
        wt = fetch_wikitext(name)
        if not wt:
            st["nopage"] += 1
            time.sleep(throttle)
            continue
        
        st["page"] += 1
        
        # 身分生日核對
        review = False
        info_birth = parse_birthdate(wt)
        if info_birth and bday:
            if (bday.year, bday.month, bday.day) != info_birth:
                log.warning("%s 同名不同人生日不符 (DB: %s, Wiki: %s)，跳過", name, bday, info_birth)
                time.sleep(throttle)
                continue
        elif not bday:
            # 無生日可比對（無 player_id 或 DB 無生日），標記 needs_review
            review = True

        raw_lines = parse_experience_lines(wt)
        parsed_rows = []
        for line in raw_lines:
            row = parse_experience_row(line)
            if row:
                row["raw_text"] = line
                parsed_rows.append(row)
        
        with conn() as c:
            _store(c.cursor(), name, player_id, parsed_rows, review)
        
        st["matched"] += 1
        st["records"] += len(parsed_rows)
        log.info("教練 %s: 解析了 %d 筆職歷 (needs_review=%s)", name, len(parsed_rows), review)
        time.sleep(throttle)
        
    return st
