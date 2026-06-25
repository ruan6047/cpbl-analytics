"""中文維基百科 `{{Infobox CPBL player}}` 個人頁爬取 + 解析 + 身分比對。

動機：補足 DB 沒有的資料——尤其**教練的所屬球隊紀錄**（infobox `teams` 欄已分
「球員時期/教練時期」），另含國際賽獎牌（`medaltemplates`）與歷年獎項（`awards`，
含官網 yearaward 沒有的台灣大聯盟等舊聯盟）。

比對：以 infobox 的出生日期（birthdate）+ 左右打/投對 `cpbl.players`（birthday/bats/
throws 皆 100% 完整）做高信心 name+birthday 比對，避免同名誤認。

維基可達（非 twbsball 的 Anubis 擋）；需 User-Agent，會 429 → 節流 + maxlag + 退避。
資料一次抓 + 手動刷新（不掛 cron）。
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

API = "https://zh.wikipedia.org/w/api.php"
UA = "cpbl-analytics/0.1 (https://cpbl.ruan-ruan.com; ruan6047@gmail.com)"

# 維基左右打/投 → 本站 players.bats/throws 格式
_HAND = {"右": "右打", "左": "左打", "雙": "左右開弓", "右左": "左右開弓", "左右": "左右開弓"}


def _get(params: dict) -> dict:
    """帶 maxlag + 退避的 GET。"""
    params = {**params, "format": "json", "maxlag": "5"}
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(5):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read())
            if "error" in data and data["error"].get("code") == "maxlag":
                time.sleep(2 * (attempt + 1))
                continue
            return data
        except Exception:
            if attempt == 4:
                raise
            time.sleep(1.5 * (attempt + 1))
    return {}


def fetch_wikitext(title: str) -> str | None:
    """取條目 wikitext（跟隨重導）。無此頁回 None。"""
    d = _get({
        "action": "query", "prop": "revisions", "rvprop": "content",
        "rvslots": "main", "redirects": "1", "titles": title,
    })
    pages = d.get("query", {}).get("pages", {})
    for p in pages.values():
        if "revisions" in p:
            return p["revisions"][0]["slots"]["main"]["*"]
    return None


# ---- infobox 欄位切割（處理巢狀 {{}} / [[]]）----

def _infobox(wt: str) -> str | None:
    """抓出棒球員 infobox 整段（含巢狀），非此樣板回 None。

    涵蓋 `Infobox CPBL player`（多數中職球員）與通用 `Infobox baseball biography`
    /`Infobox baseball player`（如彭政閔）——欄位相同。
    """
    m = re.search(r"\{\{\s*Infobox\s+(?:CPBL player|baseball)", wt, re.I)
    if not m:
        return None
    i = m.start()
    depth = 0
    for j in range(i, len(wt)):
        if wt[j] == "{":
            depth += 1
        elif wt[j] == "}":
            depth -= 1
            if depth == 0:
                return wt[i:j + 1]
    return wt[i:]


def _field(box: str, key: str) -> str | None:
    """從 infobox 取 | key = value（到下一個頂層 | 或樣板結尾）。"""
    m = re.search(r"\n\s*\|\s*" + re.escape(key) + r"\s*=", box)
    if not m:
        return None
    depth = 0
    out: list[str] = []
    for ch in box[m.end():]:
        if ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
        if depth < 0:  # 走到 infobox 收尾 }}
            break
        if ch == "|" and depth == 0:
            break
        out.append(ch)
    return "".join(out).strip()


def _clean(s: str) -> str:
    """去 wiki 標記，留純文字。"""
    s = re.sub(r"<nowiki>.*?</nowiki>", "", s, flags=re.S)
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"<ref[^>]*/>", "", s)
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"\{\{\s*(?:link-en|ill|le|tsl|interlang)\s*\|([^|}]+)(?:\|[^}]*)?\}\}",
               r"\1", s, flags=re.I)        # 跨語言連結 → 取中文名
    s = re.sub(r"\{\{\\\}\}", "/", s)         # {{\}} = 隊名改名分隔
    s = re.sub(r"\[\[(?:File|Image|檔案|文件):[^\[\]]*\]\]", "", s, flags=re.I)  # 去圖片連結
    s = re.sub(r"\[\[(?:[^\[\]|]*\|)?([^\[\]]+)\]\]", r"\1", s)  # [[a|b]]→b
    s = re.sub(r"'''?", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    return s.strip()


def _years(text: str) -> tuple[int | None, int | None]:
    """從『（2004年–2015年）』/『（2022年–）』取起訖年。"""
    yrs = [int(y) for y in re.findall(r"(\d{4})\s*年", text)]
    if not yrs:
        return None, None
    if re.search(r"年\s*[–\-—~]\s*）", text) or text.rstrip().endswith("年–") or "–）" in text:
        return yrs[0], None  # 進行中
    if len(yrs) == 1:
        return yrs[0], yrs[0]
    return yrs[0], yrs[-1]


# ---- 解析結果 ----

@dataclass
class WikiInfo:
    title: str
    birth: tuple[int, int, int] | None = None
    bats: str | None = None
    throws: str | None = None
    tenures: list[dict] = field(default_factory=list)   # {phase, seq, team, from, to}
    medals: list[dict] = field(default_factory=list)    # {color, competition, event, year}
    awards: list[dict] = field(default_factory=list)    # {award, years:[..], note}


def _parse_birth(raw: str | None) -> tuple[int, int, int] | None:
    if not raw:
        return None
    m = re.search(r"\{\{\s*(?:bda|birth[ _]date[ _and_]*age?|birth[ _]date)\b([^}]*)\}\}", raw, re.I)
    nums = re.findall(r"\d+", m.group(1)) if m else re.findall(r"\d+", raw)
    nums = [int(n) for n in nums if len(n) <= 4]
    if len(nums) >= 3 and nums[0] > 1000:
        return nums[0], nums[1], nums[2]
    return None


# 教練職稱（拆出 team 用，較長者在前避免被「教練」先吃）
_ROLES = sorted(
    ["代理總教練", "總教練", "首席教練", "打擊教練", "投手教練", "守備教練",
     "跑壘教練", "牛棚教練", "戰術教練", "復健教練", "二軍教練", "一軍教練",
     "客座教練", "技術教練", "教練", "監督", "指導員"],
    key=len, reverse=True,
)
_ROLE_RE = re.compile("(" + "|".join(_ROLES) + r")\s*$")

# 行政／球團職稱（phase=other 用，後綴剝離；可被「兼」串接）
_EXEC_TOKEN = (r"(?:執行副領隊|副領隊|領隊|球團代表|球團|農場總監|農場主管|農場|"
               r"球員發展|球探|情蒐|顧問|總監|特別助理|主管|總經理|經理|處長|召集人)")
_EXEC_RE = re.compile(r"(" + _EXEC_TOKEN + r"(?:兼?" + _EXEC_TOKEN + r")*)\s*$")


def _phase_of(header: str) -> str:
    if "球員" in header or "選手" in header:
        return "player"
    if "教練" in header or "監督" in header:
        return "coach"
    return "other"   # 行政人員/領隊/球團…


def _parse_tenures(raw: str | None) -> list[dict]:
    if not raw:
        return []
    rows: list[dict] = []
    phase = "player"
    seq = 0
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("'''") and "時期" in s:   # 任意『XX時期』分段標頭
            phase = _phase_of(s)
            continue
        if not re.match(r"^\*+\s*", s):
            continue
        body = re.sub(r"^\*+\s*", "", s)
        ym = re.search(r"[（(][^（）()]*[）)]\s*$", body)   # 全/半形年份括號
        yrs_text = ym.group(0) if ym else ""
        names_part = body[: ym.start()] if ym else body
        names = _clean(names_part)
        if not names:
            continue
        fr, to = _years(yrs_text)
        for team in re.split(r"\s*/\s*", names):
            team = team.strip("（）()、， ").strip()
            if not team:
                continue
            role = None
            role_re = _EXEC_RE if phase == "other" else _ROLE_RE
            rm = role_re.search(team)
            if rm and rm.start() > 0:        # 職稱前須仍有隊名
                role = rm.group(1)
                team = team[: rm.start()].strip()
            lm = re.search(r"([一二三]軍)$", team)   # 軍級併入職稱、隊名留乾淨
            if lm and team[: lm.start()].strip():
                team = team[: lm.start()].strip()
                role = (lm.group(1) + (role or "")) or None
            rows.append({"phase": phase, "seq": seq, "team": team, "role": role,
                         "from": fr, "to": to})
            seq += 1
    return rows


def _parse_medals(raw: str | None) -> list[dict]:
    if not raw:
        return []
    rows: list[dict] = []
    comp = None
    color_map = {"Gold": "金", "Silver": "銀", "Bronze": "銅"}
    for m in re.finditer(r"\{\{\s*Medal(Competition|Gold|Silver|Bronze)\s*\|([^}]*)\}\}", raw):
        kind, arg = m.group(1), m.group(2)
        if kind == "Competition":
            comp = _clean(arg).strip("| ")
        else:
            txt = _clean(arg).strip("| ")
            yr = re.search(r"(\d{4})", txt)
            rows.append({
                "color": color_map[kind], "competition": comp,
                "event": txt, "year": int(yr.group(1)) if yr else None,
            })
    return rows


def _parse_awards(raw: str | None) -> list[dict]:
    if not raw:
        return []
    rows: list[dict] = []
    for line in raw.splitlines():
        s = line.strip()
        if not re.match(r"^\*+\s*", s):
            continue
        body = _clean(re.sub(r"^\*+\s*", "", s))
        if "：" not in body and ":" not in body:
            continue
        head, tail = re.split(r"[：:]", body, maxsplit=1)
        head = re.sub(r"\s*[（(]\d+[）)]\s*$", "", head)   # 去『 (7)』次數註記
        note = None
        pm = re.search(r"[（(]([^）)]*)[）)]", head)
        if pm:
            note = pm.group(1)
            head = head[: pm.start()].strip()
        years = [int(y) for y in re.findall(r"(\d{4})", tail)]
        award = head.strip()
        if award:
            rows.append({"award": award, "years": years, "note": note})
    return rows


def parse(title: str, wt: str) -> WikiInfo | None:
    box = _infobox(wt)
    if box is None:
        return None
    info = WikiInfo(title=title)
    info.birth = _parse_birth(_field(box, "birthdate"))
    b = _field(box, "bats")
    t = _field(box, "throws")
    info.bats = _HAND.get(_clean(b)) if b else None
    info.throws = _HAND.get(_clean(t)) if t else None
    info.tenures = _parse_tenures(_field(box, "teams"))
    info.medals = _parse_medals(_field(box, "medaltemplates"))
    info.awards = _parse_awards(_field(box, "awards"))
    return info


# ---- 目標清單 + 比對 + 入庫 ----

# 現役 + 教練/總教練 + 歷史排行前段（用戶指定：張泰山、彭政閔…）
_TARGET_SQL = """
WITH t AS (
  SELECT DISTINCT player_id FROM cpbl.batting_current WHERE year=%(yr)s
  UNION SELECT DISTINCT player_id FROM cpbl.pitching_current WHERE year=%(yr)s
  UNION SELECT p.id FROM cpbl.coaches c JOIN cpbl.players p ON p.name=c.name
  UNION SELECT p.id FROM cpbl.managers m JOIN cpbl.players p ON p.name=m.name
  UNION SELECT player_id FROM (SELECT player_id, sum(h) v FROM cpbl.batting_seasons
        GROUP BY player_id ORDER BY v DESC NULLS LAST LIMIT 40) a
  UNION SELECT player_id FROM (SELECT player_id, sum(hr) v FROM cpbl.batting_seasons
        GROUP BY player_id ORDER BY v DESC NULLS LAST LIMIT 40) b
  UNION SELECT player_id FROM (SELECT player_id, sum(so) v FROM cpbl.pitching_seasons
        GROUP BY player_id ORDER BY v DESC NULLS LAST LIMIT 30) d
)
SELECT p.id, p.name, p.birthday FROM t JOIN cpbl.players p ON p.id=t.player_id
WHERE p.name IS NOT NULL ORDER BY p.id
"""


def _targets(cur, year: int) -> list[tuple]:
    cur.execute(_TARGET_SQL, {"yr": year})
    return cur.fetchall()


def _store(cur, pid: str, info: WikiInfo, review: bool) -> None:
    for tbl in ("wiki_tenures", "wiki_medals", "wiki_awards"):
        cur.execute(f"DELETE FROM cpbl.{tbl} WHERE player_id=%s", (pid,))
    for t in info.tenures:
        cur.execute(
            "INSERT INTO cpbl.wiki_tenures"
            "(player_id,phase,seq,team_raw,role,from_year,to_year,source,needs_review)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (pid, t["phase"], t["seq"], t["team"], t.get("role"),
             t["from"], t["to"], info.title, review),
        )
    for i, m in enumerate(info.medals):
        cur.execute(
            "INSERT INTO cpbl.wiki_medals"
            "(player_id,seq,color,competition,event,year,source)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (pid, i, m["color"], m["competition"], m["event"], m["year"], info.title),
        )
    for i, a in enumerate(info.awards):
        cur.execute(
            "INSERT INTO cpbl.wiki_awards(player_id,seq,award,note,years,source)"
            " VALUES (%s,%s,%s,%s,%s,%s)",
            (pid, i, a["award"], a["note"], a["years"], info.title),
        )


def run(year: int = 2026, throttle: float = 0.8, limit: int | None = None) -> dict:
    """爬目標球員維基頁，以 name+birthday 比對後入庫。回傳統計。"""
    from cpbl.db import conn

    with conn() as c:
        targets = _targets(c.cursor(), year)
    if limit:
        targets = targets[:limit]

    st = {"targets": len(targets), "page": 0, "matched": 0,
          "mismatch": 0, "nopage": 0, "unverified": 0}
    for pid, name, bday in targets:
        wt = fetch_wikitext(name)
        info = parse(name, wt) if wt else None
        if not info:
            st["nopage"] += 1
            time.sleep(throttle)
            continue
        st["page"] += 1
        review = False
        if info.birth and bday:
            if (bday.year, bday.month, bday.day) != info.birth:
                st["mismatch"] += 1   # 同名不同人 → 跳過
                time.sleep(throttle)
                continue
        else:
            review = True             # 無生日可驗證 → 採信但標記
            st["unverified"] += 1
        with conn() as c:
            _store(c.cursor(), pid, info, review)
        st["matched"] += 1
        time.sleep(throttle)
    return st
