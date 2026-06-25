"""球員旅外經歷爬蟲（資料源：淡江棒球維基 twbsball「臺灣旅外職棒球員列表」+ 各聯盟模板）。

twbsball 網頁有 Anubis 反爬挑戰，但 MediaWiki `action=query&prop=revisions` 可取得原始
wikitext（繞過挑戰）。各聯盟清單為 wikitext 表格，列含 [[連結]]；以「抽列內連結、依
年份/球隊/守位過濾出球員名」穩健解析（避免逐欄對齊的脆弱）。

只存能對到本站 cpbl.players 的球員（旅外後曾打中職者，如旅外回國），供球員頁標註旅外經歷。
一次性抓 + 手動刷新（不掛 cron）。
"""

from __future__ import annotations

import logging
import re
import urllib.parse

import httpx

from cpbl.db import conn

log = logging.getLogger("cpbl.overseas")

API = "https://twbsball.dils.tku.edu.tw/api.php"
UA = "cpbl-analytics/1.0 (baseball analytics)"

# 各聯盟 → 來源頁（Template 為各聯盟現成清單；主頁含韓國/墨西哥/多明尼加內嵌表）
_TEMPLATES = {
    "美國職棒": "Template:旅美球員",
    "日本職棒": "Template:日本職棒的台灣選手",
    "美國獨立聯盟": "Template:美國獨立聯盟的台灣選手",
    "日本獨立聯盟": "Template:日本獨立聯盟的台灣選手",
    "澳洲職棒": "Template:澳洲棒球聯盟的台灣選手",
}
# 主頁分節（== 標題 ==）→ 聯盟標籤
_MAIN_PAGE = "臺灣旅外職棒球員列表"
_MAIN_SECTIONS = {"韓國職棒": "韓國職棒", "墨西哥職棒": "墨西哥職棒", "多明尼加職棒": "多明尼加職棒"}

_POS = {"投手", "捕手", "內野手", "外野手", "一壘手", "二壘手", "三壘手", "游擊手", "指定打擊", "工具人"}


def _wikitext(client: httpx.Client, title: str) -> str:
    u = f"{API}?action=query&prop=revisions&rvprop=content&redirects=1&titles={urllib.parse.quote(title)}&format=json"
    d = client.get(u, timeout=25).json()
    pages = d["query"]["pages"]
    p = pages[next(iter(pages))]
    revs = p.get("revisions")
    return revs[0]["*"] if revs else ""


def _rows_from_table(table_wikitext: str, league: str) -> list[tuple[str, int, str | None]]:
    """解析單一 wikitext 表格 → [(球員名, 加盟年度, 球隊)]；處理 rowspan 年度。"""
    out = []
    cur_year: int | None = None
    for row in re.split(r"\n\|-", table_wikitext):
        if "colspan" in row and any(k in row for k in ("現役", "離開", "本職棒", "退役")):
            continue  # 狀態分隔列
        links = [m.split("|")[-1].strip() for m in re.findall(r"\[\[([^\]]+)\]\]", row)]
        ym = next((re.match(r"(\d{4})", d) for d in links if re.match(r"\d{4}年", d)), None)
        if ym:
            cur_year = int(ym.group(1))
        team = next((d for d in links if d.endswith("隊")), None)
        player = None
        for d in links:
            if re.match(r"\d{4}年", d) or d.endswith("隊") or d in _POS:
                continue
            if "聯盟" in d or "職棒" in d or d.endswith("年"):
                continue
            player = d.replace(" ", "").replace("　", "")  # 去全形空白（如「蕭　齊」）
            break
        if player and cur_year:
            out.append((player, cur_year, team))
    return out


def _parse_source(wikitext: str, league: str) -> list[tuple[str, int, str | None]]:
    out = []
    for tb in re.findall(r"\{\|.*?\|\}", wikitext, re.S):
        out += _rows_from_table(tb, league)
    return out


def scrape_overseas() -> dict:
    rows: list[tuple[str, int, str, str | None]] = []  # (name, year, league, team)
    with httpx.Client(headers={"User-Agent": UA}) as client:
        for league, title in _TEMPLATES.items():
            try:
                wt = _wikitext(client, title)
                rows += [(n, y, league, t) for n, y, t in _parse_source(wt, league)]
            except Exception as e:  # noqa: BLE001
                log.warning("%s（%s）失敗：%s", league, title, e)
        # 主頁韓國/墨西哥/多明尼加：依分節切，逐節標聯盟
        try:
            main = _wikitext(client, _MAIN_PAGE)
            for sec in re.split(r"\n==[^=]", main):
                league = next((lg for key, lg in _MAIN_SECTIONS.items() if key in sec[:30]), None)
                if league:
                    rows += [(n, y, league, t) for n, y, t in _parse_source(sec, league)]
        except Exception as e:  # noqa: BLE001
            log.warning("主頁失敗：%s", e)

    # 對到本站球員（同名唯一）→ 取每位每聯盟最早加盟年
    with conn() as c:
        cur = c.cursor()
        names = list({r[0] for r in rows})
        cur.execute(
            "SELECT name, max(id) FROM cpbl.players WHERE name = ANY(%s) GROUP BY name HAVING count(*)=1",
            (names,))
        pid_of = {n: pid for n, pid in cur.fetchall()}
        recs: dict[tuple, tuple] = {}
        for name, year, league, team in rows:
            pid = pid_of.get(name)
            if not pid:
                continue
            key = (pid, league)
            if key not in recs or year < recs[key][3]:
                recs[key] = (pid, league, team, year)
        if recs:
            cur.execute("TRUNCATE cpbl.overseas")
            cur.executemany(
                "INSERT INTO cpbl.overseas (player_id, league, team, from_year) VALUES (%s,%s,%s,%s) "
                "ON CONFLICT (player_id, league, from_year) DO UPDATE SET team=EXCLUDED.team",
                list(recs.values()))
    matched = len({r[0] for r in recs.values()})
    log.info("旅外列：解析 %d 列 / 對到 %d 位球員 / %d 筆(球員×聯盟)", len(rows), matched, len(recs))
    return {"parsed": len(rows), "players": matched, "records": len(recs)}
