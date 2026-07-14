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
from cpbl.franchises import franchise_of

log = logging.getLogger("cpbl.coaches_history")

API = "https://twbsball.dils.tku.edu.tw/api.php"
UA = "cpbl-analytics/1.0 (baseball analytics; contact via github)"

# 全歷史中職球隊隊名與代碼映射
CPBL_TEAM_MAP = {
    # 兄弟象 / 中信兄弟
    "中信兄弟": "ACN011",
    "兄弟象": "ACC011",
    # 統一獅 / 統一7-ELEVEn獅
    "統一7-ELEVEn獅": "ADD011",
    "統一7-ELEVEn": "ADD011",
    "統一獅": "ADD011",
    # 富邦悍將 / 興農牛 / 義大犀牛 / 俊國熊
    "富邦悍將": "AEO011",
    "義大犀牛": "AEM011",
    "興農牛": "AEG011",
    "興農": "AEG011",
    "俊國熊": "AEE011",
    # 樂天桃猿 / Lamigo桃猿 / La new熊 / 第一金剛
    "樂天桃猿": "AJL011",
    "Lamigo桃猿": "AJK011",
    "La New熊": "AJK011",
    "第一金剛": "AJJ011",
    # 台鋼雄鷹
    "台鋼雄鷹": "AKP011",
    # 味全龍
    "味全龍": "AAA011",
    # 三商虎
    "三商虎": "ABB011",
    # 時報鷹
    "時報鷹": "AFF011",
    # 中信鯨 / 和信鯨
    "中信鯨": "AHH011",
    "和信鯨": "AHH011",
    # 誠泰Cobras
    "誠泰Cobras": "AII011",
    "誠泰": "AII011",
    # 米迪亞暴龍
    "米迪亞暴龍": "AIL011",
    # 簡稱
    "兄弟": "ACN011",
    "統一": "ADD011",
    "富邦": "AEO011",
    "義大": "AEM011",
    "俊國": "AEE011",
    "樂天": "AJL011",
    "Lamigo": "AJK011",
    "La New": "AJK011",
    "第一": "AJJ011",
    "台鋼": "AKP011",
    "味全": "AAA011",
    "三商": "ABB011",
    "時報": "AFF011",
    "和信": "AHH011",
    "中信": "AHH011",
    "米迪亞": "AIL011",
}

# 隊名**簡稱**（上表中不含「隊」的鍵）只在該行明確標示「中華職棒」時才可採用。
# 沒有聯盟標示時用簡稱比對會誤判母企業旗下的其他隊伍與同名機構——實測踩到的坑：
#   富邦勇士**籃球隊**體能教練 → 誤掛富邦悍將；中信金融管理**學院**棒球隊 → 誤掛中信鯨；
#   兄弟**飯店**棒球隊／俊國**建設**棒球隊（業餘前身，1990 中職成立前）→ 誤掛現行球團。
# 全名（含「隊」或完整隊名，如 時報鷹隊／中信鯨隊）不受此限，因其本身已無歧義。
CPBL_TEAM_SHORT = {
    "兄弟", "統一", "富邦", "義大", "俊國", "樂天", "Lamigo", "La New",
    "第一", "台鋼", "味全", "三商", "時報", "和信", "中信", "米迪亞",
}


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


# 出生日期的實測寫法（逐一寫死會漏，故一條規則涵蓋）：
#   {{BD|1961-05-14||:}}（洪一中）／{{BD|1978/8/6}}（彭政閔）／{{生日|1973/09/13}}（陳連宏）
#   ／出生日期：1972年10月30日（純文字）
# 模板名不限 BD（另有「生日」），分隔符不限 `-`（另有 `/` 與 年月日）。
_BIRTH_RE = re.compile(
    r"出生日期：\s*(?:\{\{\s*[^|{}]*\|\s*)?"      # 可選的模板前綴（BD／生日／…）
    r"(\d{4})\s*[-/年]\s*(\d{1,2})\s*[-/月]\s*(\d{1,2})"
)


def parse_birthdate(wikitext: str) -> tuple[int, int, int] | None:
    """從 wikitext 中提取出生日期 (年, 月, 日) 以供身分比對。"""
    m = _BIRTH_RE.search(re.sub(r"\[\[|\]\]", "", wikitext))
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    return None


# 同名消歧義的人工指定（ruan6047 裁決）。自動規則無法確信時，答案寫在這裡而不是猜。
# 大威：2014 義大犀牛總教練；D.W／D.D 皆有中職教練經歷、生日又對不上 DB 同名球員，
# 自動規則 fail-closed → 由使用者指定 D.W（教練經歷 6 行，最多）。
MANUAL_PAGE_TITLES = {
    "大威": "大威D.W",
}


def strip_team_rename(role: str) -> str:
    """剝掉職務欄裡的球隊沿革前綴：`La New熊隊→總教練` → `總教練`。

    維基把改名寫成「A隊→B隊 職務」，解析器認出後面的隊名、把「A隊→」留在職務欄。
    只影響顯示、不影響語意；沿革本身已由 team_raw／team_code 表達。
    末段若仍是隊名（無職稱關鍵字）代表該行本就沒有職務（純效力年資），回空字串
    交由呼叫端 fallback 成 team_raw。
    """
    if "→" not in role:
        return role
    tail = role.split("→")[-1].strip()
    if tail.endswith("隊") and not any(k in tail for k in ("教練", "監督", "領隊", "球員")):
        return ""
    return tail


def is_disambiguation(wikitext: str) -> bool:
    """twbsball 同名者多時，主條目為消歧義頁（無經歷節）。"""
    return "{{Disambig}}" in wikitext or "您要找的是" in wikitext


def disambiguation_candidates(name: str, wikitext: str) -> list[str]:
    """消歧義頁列出的候選條目標題（如 `呂文生(1962)`）。"""
    seen: list[str] = []
    for target in re.findall(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", wikitext):
        t = target.strip()
        if t.startswith(name) and t != name and t not in seen:
            seen.append(t)
    return seen


def _cpbl_coach_score(wikitext: str) -> int:
    """該條目的中職教練經歷行數；用於無生日可比對時挑出正確的同名者。"""
    return sum(
        1 for line in parse_experience_lines(wikitext)
        if "中華職棒" in line and ("教練" in line or "監督" in line)
    )


def resolve_disambiguation(
    name: str, wikitext: str, db_births: list[tuple[int, int, int]],
) -> tuple[str, str, bool] | None:
    """消歧義頁 → 實際條目。回 (title, wikitext, 生日已核對)；無法確信時回 None（不腦補歸戶）。

    **先教練、後生日**（順序是紅線）：種子名單來自 coaches/managers，要找的是「教練這個人」，
    故第一道篩選必須是「該條目有中職教練經歷」。生日只用來在多位教練候選之間裁決。

    反例（實測）：路易士有 4 位同名者，其中 `路易士R.L` 的生日對得上 DB 球員但**毫無教練
    經歷**——若讓生日優先，就會把球員的生平掛到教練頭上。洋將譯名相同者根本是不同人，
    生日能認出「同名球員是誰」，不能認出「教練是誰」。

    第三個回傳值標示是否經生日核對：僅靠「唯一教練候選」選出者未經核對，呼叫端須標
    needs_review。
    """
    cands: list[tuple[str, str]] = []
    for title in disambiguation_candidates(name, wikitext):
        wt = fetch_wikitext(title)
        if wt and not is_disambiguation(wt):
            cands.append((title, wt))
        time.sleep(0.3)

    coaches = [(t, w) for t, w in cands if _cpbl_coach_score(w) > 0]
    if len(coaches) > 1 and db_births:  # 多位教練候選 → 生日裁決
        matched = [(t, w) for t, w in coaches if parse_birthdate(w) in db_births]
        if len(matched) == 1:
            return (*matched[0], True)
    if len(coaches) == 1:
        return (*coaches[0], False)
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
            # 同一行常同時出現在「經歷」與「年表」兩節（實測 8 列重複），去重。
            if clean_line and clean_line not in exp_lines:
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

    # 4. 判斷是否為中職
    # 只有 league == '中華職棒' 或 league 為 None 且不含國外/業餘指標時，才允許匹配中職隊碼
    is_cpbl = False
    if league == "中華職棒":
        is_cpbl = True
    elif league is None:
        has_foreign_or_amateur = any(
            x in pos_body for x in [
                "日本", "美國", "韓國", "澳洲", "大聯盟", "MLB", "NPB", "KBO", "ABL",
                "少棒", "青少棒", "青棒", "大學", "中學", "小學", "高中", "學校", "學院",
                "代表隊", "國家隊", "中華隊", "奧運", "亞運", "洲際盃", "世界盃",
                "東北樂天", "樂天金鷲", "金鷲",
                "籃球", "建設", "飯店", "俱樂部", "科技",  # 母企業旗下的非中職隊伍／同名機構
            ]
        )
        if not has_foreign_or_amateur:
            is_cpbl = True

    team_code = None
    team_raw = None

    if is_cpbl:
        # 依關鍵字長度由長到短排序匹配
        for kw, code in sorted(CPBL_TEAM_MAP.items(), key=lambda x: len(x[0]), reverse=True):
            if kw in pos_body:
                # 特殊防禦：避免東北樂天金鷲匹配到樂天
                if kw == "樂天" and any(x in pos_body for x in ["東北", "金鷲", "樂天金鷲"]):
                    continue
                # 簡稱僅在明確標示中華職棒時可用（見 CPBL_TEAM_SHORT 註解的誤判實例）
                if kw in CPBL_TEAM_SHORT and league != "中華職棒":
                    continue
                team_code = franchise_of(code)
                idx = pos_body.find(kw)
                matched = kw
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
    role = strip_team_rename(role)

    # 6. 分類 phase (player | coach | other | amateur | note)
    # 判斷是否為敘事列或無年份列：如果是，標 phase = 'note'
    is_narrative = False
    if from_year is None:
        is_narrative = True
    elif len(role) > 40:
        is_narrative = True
    elif "。" in role or "--" in role or "宣布" in role or "擔任" in role or "宣告" in role:
        is_narrative = True

    if is_narrative:
        phase = "note"
    else:
        coach_kws = ["總教練", "首席教練", "打擊教練", "投手教練", "守備教練", "跑壘教練", "牛棚教練", "戰術教練", "復健教練", "教練", "監督", "指導員", "技術教練"]
        admin_kws = ["副領隊", "領隊", "總監", "顧問", "球探", "情蒐", "特別助理", "代表", "處長", "經理", "球評"]
        amateur_kws = ["少棒", "青少棒", "青棒", "大學", "國小", "國中", "高中", "學校", "棒球隊", "業餘", "乙組"]

        # role 為空代表沒對到球隊、整行都是隊名＋職務（如「獨立聯盟 XX 隊總教練」）；
        # 此時要用整行判斷，否則會落到預設值「球員」——史耐德的獨立聯盟總教練即曾被誤判。
        judged = role or pos_body

        if any(kw in judged for kw in coach_kws):
            phase = "coach"
        elif any(kw in judged for kw in admin_kws):
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


def seed_confirms_identity(parsed_rows: list[dict], seed: list[tuple[int, str]]) -> bool:
    """條目的中職執教紀錄是否對得上我們自己資料庫記載的實際任職（隊別＋年份）。

    **為什麼需要這條**：原本只用「生日對得上中職**球員**」驗證身分，但教練不一定當過中職
    球員——王建民在大聯盟出賽、中職無出賽紀錄，這個條件他永遠無法滿足，於是被永久標
    「待查」。而種子名單（coaches/managers）本身就記載了他在哪一隊、哪一年任職；條目裡
    若有相符的中職執教紀錄，這個人就是我們要找的教練，不必繞道球員生日。

    比對採「同隊且任期涵蓋該年」，避免只憑姓名或只憑球隊就認定。
    """
    for seed_year, seed_team in seed:
        for r in parsed_rows:
            if r.get("team_code") != seed_team or r.get("from_year") is None:
                continue
            if r["from_year"] <= seed_year <= (r.get("to_year") or 9999):
                return True
    return False


def _seed_tenures(cur, name: str) -> list[tuple[int, str]]:
    """該教練在我們資料庫中的實際任職（年份, 隊碼），供身分交叉驗證。"""
    cur.execute(
        "SELECT year, team_code FROM cpbl.coaches WHERE name = %s "
        "UNION SELECT from_year, team_code FROM cpbl.managers WHERE name = %s",
        (name, name),
    )
    return [(y, t) for y, t in cur.fetchall() if y and t]


def _targets(cur) -> list[str]:
    """自 coaches 與 managers 中抓出所有教練種子名稱。"""
    sql = """
    SELECT DISTINCT name FROM cpbl.coaches
    UNION
    SELECT DISTINCT name FROM cpbl.managers
    ORDER BY name
    """
    cur.execute(sql)
    return [r[0] for r in cur.fetchall()]


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

    st = {"targets": len(targets), "page": 0, "matched": 0, "nopage": 0, "records": 0,
          "disambig": 0, "disambig_unresolved": 0}

    for name in targets:
        manual_title = MANUAL_PAGE_TITLES.get(name)
        wt = fetch_wikitext(manual_title or name)
        if not wt:
            st["nopage"] += 1
            time.sleep(throttle)
            continue

        # 查詢同名球員名冊
        with conn() as c:
            cur = c.cursor()
            cur.execute("SELECT id, birthday FROM cpbl.players WHERE name = %s", (name,))
            db_players = cur.fetchall()

        # 條目身分是否已確信：人工指定＝已確信；消歧義自動解析須看是否經生日核對
        identity_verified = manual_title is not None
        if manual_title:
            st["manual"] = st.get("manual", 0) + 1
            log.info("%s 人工指定 → %s", name, manual_title)
        # 同名者多 → 主條目是消歧義頁（無經歷節，過去會靜默產生 0 筆，整個人不見）
        elif is_disambiguation(wt):
            st["disambig"] += 1
            births = [(b.year, b.month, b.day) for _, b in db_players if b]
            resolved = resolve_disambiguation(name, wt, births)
            if not resolved:
                st["disambig_unresolved"] += 1
                log.warning("%s 消歧義頁無法確信解析，略過（不腦補歸戶）", name)
                time.sleep(throttle)
                continue
            title, wt, identity_verified = resolved
            log.info("%s 消歧義 → %s（生日核對=%s）", name, title, identity_verified)
        else:
            identity_verified = True  # 唯一條目，無同名歧義

        st["page"] += 1

        # 取得 Wiki 出生日期
        info_birth = parse_birthdate(wt)

        player_id = None
        review = False

        if len(db_players) == 0:
            # DB 無同名球員（日籍/洋將教練居多）：player_id 本就為 NULL，不存在歸錯戶的風險。
            # 僅在「條目身分未確信」（消歧義頁靠教練經歷選出、未經生日核對）時才標 needs_review，
            # 避免整頁列皆掛「待查」而失去訊號量。
            player_id = None
            review = not identity_verified
        elif len(db_players) == 1:
            pid, bday = db_players[0]
            if info_birth and bday:
                if (bday.year, bday.month, bday.day) == info_birth:
                    player_id = pid
                    review = False
                else:
                    # 生日不符＝同名但**不是同一人**（教練另有其人）。正解是不歸戶；
                    # 條目身分若已確信（人工指定／唯一條目）就不必標「待查」——該旗標的語意是
                    # 「身分未確認」，不是「沒歸戶」。
                    player_id = None
                    review = not identity_verified
            else:
                # 缺少一方的生日資訊 → 仍歸戶但無法交叉核對，這是真的有歸錯戶風險，標「待查」
                player_id = pid
                review = True
        else:
            # 同名同姓歧義：若 Wiki 有生日且與其中一個 DB 生日唯一匹配，則通過
            if info_birth:
                matches = []
                for pid, bday in db_players:
                    if bday and (bday.year, bday.month, bday.day) == info_birth:
                        matches.append(pid)
                if len(matches) == 1:
                    player_id = matches[0]
                    review = False
                else:
                    player_id = None
                    review = not identity_verified
            else:
                # Wiki 無生日，且 DB 有同名多人：嚴禁腦補歸戶，player_id = None
                player_id = None
                review = not identity_verified

        raw_lines = parse_experience_lines(wt)
        parsed_rows = []
        for line in raw_lines:
            row = parse_experience_row(line)
            if row:
                row["raw_text"] = line
                parsed_rows.append(row)

        # 身分的第二條驗證路徑：條目的中職執教紀錄 vs 我們資料庫記載的實際任職（隊＋年）。
        # 教練不一定當過中職球員（王建民只有大聯盟出賽紀錄），單靠球員生日永遠無法確認他們，
        # 會被永久誤標「待查」。種子名單本身就是權威的任職紀錄，對得上即為同一人。
        if review and not identity_verified:
            with conn() as c:
                seed = _seed_tenures(c.cursor(), name)
            if seed_confirms_identity(parsed_rows, seed):
                review = False
                st["seed_verified"] = st.get("seed_verified", 0) + 1
                log.info("%s 以種子任職紀錄確認身分（%s）", name, seed)

        with conn() as c:
            _store(c.cursor(), name, player_id, parsed_rows, review)
        
        st["matched"] += 1
        st["records"] += len(parsed_rows)
        log.info("教練 %s: 解析了 %d 筆職歷 (needs_review=%s, player_id=%s)", name, len(parsed_rows), review, player_id)
        time.sleep(throttle)
        
    return st
