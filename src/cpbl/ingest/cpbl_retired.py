"""各隊退休背號（引退背號）— 來源＝中文維基各 franchise 條目「退休背號」段。

格式跨隊有變異：`'''23''' [[彭政閔]]（…）` / `85：[[徐生明]]` / `49: 張泰山（2025）` /
`10 球迷（…）`；子段 ===現存/已失效/已重新啟用===。球迷/球團＝非選手（不附 player）。
選手以姓名比對 players（含 `麥克·羅力`→`羅力` 的分隔段 fallback）；比不到標 needs_review。

一次抓 + 手動刷新（不掛 cron）。team_code 用 franchise（與 managers 同條目）。
"""

from __future__ import annotations

import logging
import re

from cpbl.db import conn
from cpbl.ingest.cpbl_managers import WIKI_TITLE
from cpbl.ingest.cpbl_wiki import fetch_wikitext

log = logging.getLogger("cpbl.retired")

# 維基誤植排除：(franchise team_code, number) — 維基條目誤列但事實上未退休（使用者查證）。
# 因爬蟲照抄維基，須在此攔截，否則每次重爬又回填。
WIKI_FALSE_RETIRED: set[tuple[str, int]] = {
    ("AAA011", 49),  # 味全龍：張泰山為隊上教練，非退休背號（真正退休＝徐生明 #85）
}

# 已查證正確但無法連結 players（受獎者為總教練/名宿，不在球員表）→ 不再標 needs_review。
WIKI_VERIFIED_NO_LINK: set[tuple[str, int]] = {
    ("ACN011", 67),  # 中信兄弟：曾紀恩（創隊名帥）
    ("AEO011", 85),  # 富邦悍將：徐生明（興農/義大時退、2021 恢復使用）
    ("AAA011", 85),  # 味全龍：徐生明（味全龍名帥）
}


def _parse_section(wt: str) -> list[dict]:
    m = re.search(r"==\s*退休背號\s*==", wt)
    if not m:
        return []
    sec = wt[m.end():]
    end = re.search(r"\n==[^=]", sec)
    if end:
        sec = sec[: end.start()]
    rows: list[dict] = []
    status = "active"
    for line in sec.splitlines():
        s = line.strip()
        if not s:
            continue
        hd = re.match(r"^={3,}\s*(.*?)\s*={3,}$", s)
        if hd:
            h = hd.group(1)
            status = "revoked" if ("失效" in h or "啟用" in h or "恢復" in h) else "active"
            continue
        lm = re.match(r"^\*+\s*(?:''')?\s*(\d+)\s*(?:''')?\s*(.*)$", s)
        if not lm:
            continue
        num = int(lm.group(1))
        rest = re.sub(r"<ref.*?(/>|</ref>)", "", lm.group(2), flags=re.S).strip()
        rest = re.sub(r"^[：:\s]+", "", rest)
        note_m = re.search(r"[（(](.+?)[）)]", rest)
        note = note_m.group(1).strip() if note_m else None
        ym = re.search(r"(\d{4})", note or rest)
        year = int(ym.group(1)) if ym else None
        if "球迷" in rest[:10]:
            rows.append({"number": num, "holder_type": "fans", "name": "球迷",
                         "year": year, "status": status, "note": note})
            continue
        if "球團" in rest[:8]:
            rows.append({"number": num, "holder_type": "org", "name": "球團",
                         "year": year, "status": status, "note": note})
            continue
        link = re.search(r"\[\[([^\]]+)\]\]", rest)
        if link:
            name = link.group(1).split("|")[-1].strip()
        else:
            name = re.split(r"[（(：:\s]", rest, maxsplit=1)[0].strip()
        if name:
            rows.append({"number": num, "holder_type": "player", "name": name,
                         "year": year, "status": status, "note": note})
    return rows


def _match(cur, name: str) -> tuple[str | None, bool]:
    """姓名→player_id；唯一才採，否則 needs_review。含 `麥克·羅力`→`羅力` fallback。"""
    for cand in (name, *re.split(r"[·•・]", name)[1:]):
        cur.execute("SELECT id FROM cpbl.players WHERE name=%s", (cand,))
        r = cur.fetchall()
        if len(r) == 1:
            return r[0][0], False
    return None, True


def scrape_retired() -> dict[str, int]:
    """抓 WIKI_TITLE 各 franchise 退休背號，冪等覆蓋 cpbl.retired_numbers。"""
    out: dict[str, int] = {}
    for code, title in WIKI_TITLE.items():
        wt = fetch_wikitext(title)
        rows = _parse_section(wt) if wt else []
        rows = [r for r in rows if (code, r["number"]) not in WIKI_FALSE_RETIRED]
        with conn() as c:
            cur = c.cursor()
            cur.execute("DELETE FROM cpbl.retired_numbers WHERE team_code=%s", (code,))
            for r in rows:
                pid, review = (None, False)
                if r["holder_type"] == "player":
                    pid, review = _match(cur, r["name"])
                if (code, r["number"]) in WIKI_VERIFIED_NO_LINK:
                    review = False
                cur.execute(
                    "INSERT INTO cpbl.retired_numbers"
                    "(team_code,number,holder_type,player_id,holder_name,retired_year,status,note,source,needs_review)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                    " ON CONFLICT (team_code,number) DO UPDATE SET holder_type=EXCLUDED.holder_type,"
                    " player_id=EXCLUDED.player_id, holder_name=EXCLUDED.holder_name,"
                    " retired_year=EXCLUDED.retired_year, status=EXCLUDED.status, note=EXCLUDED.note,"
                    " needs_review=EXCLUDED.needs_review",
                    (code, r["number"], r["holder_type"], pid, r["name"], r["year"],
                     r["status"], r["note"], title, review),
                )
        out[code] = len(rows)
        log.info("%s（%s）：%d 個退休背號", code, title, len(rows))
    return out
