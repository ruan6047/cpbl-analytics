"""歷任總教練爬蟲（資料源：中文維基百科各球隊條目「按總教練分 / 歷屆總教練」表格）。

維基條目此表為逐季列、以 rowspan 群組同一總教練 → 解析時展開 rowspan 還原網格，再依
（時期, 任次, 姓名）彙總成每位教練的任期戰績（出賽/勝/敗/和/勝率/季後賽/總冠軍）。

特性：
- 維基人工編修、覆蓋不均：僅部分球隊條目有此表（中信兄弟/統一/樂天/三商虎…），
  其餘球隊抓不到屬正常，不報錯。
- **一次性抓取 + 手動刷新**（不掛 cron）：資料近乎靜態，要更新時手動跑 cpbl-scrape-managers。
- 一律標 source='wikipedia' + needs_review=true，提醒數據可能需人工複查。
- Wikipedia API 各地可達（非官網，不受台灣 IP 限制），本機/VPS 皆可跑。
"""

from __future__ import annotations

import html
import logging
import re

import httpx

from cpbl.db import conn

log = logging.getLogger("cpbl.managers")

WIKI_API = "https://zh.wikipedia.org/w/api.php"
UA = "cpbl-analytics/1.0 (baseball analytics; contact via github)"

# franchise team_code（對齊 team_dim）→ zh.wikipedia 條目標題（條目通常涵蓋整個 franchise 各時期）
WIKI_TITLE = {
    "ACN011": "中信兄弟",          # 含 兄弟象
    "ADD011": "統一7-ELEVEn獅",
    "AJL011": "樂天桃猿",          # 含 第一金剛 / La New / Lamigo
}


def _get(client: httpx.Client, **params) -> dict:
    params.setdefault("format", "json")
    r = client.get(WIKI_API, params=params, timeout=25)
    r.raise_for_status()
    return r.json()


def _manager_section(client: httpx.Client, title: str) -> str | None:
    """找出條目中「總教練」相關 section 的 index。"""
    d = _get(client, action="parse", page=title, prop="sections")
    if "error" in d:
        return None
    for s in d["parse"]["sections"]:
        if "總教練" in s["line"]:
            return s["index"]
    return None


def _cells(tr: str) -> list[tuple[str, int]]:
    out = []
    for m in re.finditer(r"<(t[hd])\b([^>]*)>(.*?)</\1>", tr, re.S):
        attrs, inner = m.group(2), m.group(3)
        rsm = re.search(r'rowspan="?(\d+)', attrs)
        txt = re.sub(r"<[^>]+>", "", html.unescape(inner)).strip()
        out.append((txt, int(rsm.group(1)) if rsm else 1))
    return out


def _expand(table_html: str, ncols: int) -> list[list[str]]:
    """展開 rowspan 還原成完整網格。"""
    carry: dict[int, list] = {}
    grid: list[list[str]] = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.S):
        cs = _cells(tr)
        row: list[str] = []
        ci = si = 0
        while ci < ncols:
            if ci in carry and carry[ci][1] > 0:
                row.append(carry[ci][0]); carry[ci][1] -= 1; ci += 1
            elif si < len(cs):
                txt, rs = cs[si]; si += 1; row.append(txt)
                if rs > 1:
                    carry[ci] = [txt, rs - 1]
                ci += 1
            else:
                break
        if row:
            grid.append(row)
    return grid


def _int(x: str) -> int:
    m = re.search(r"-?\d+", x or "")
    return int(m.group()) if m else 0


# 各球隊條目欄名不一致：姓名欄可能叫「姓名」或「總教練」；年份欄叫「球季」或「年度」。
_NAME_KEYS = ("姓名", "總教練")
_YEAR_KEYS = ("球季", "年度")


def _parse_managers(section_html: str, default_era: str = "") -> list[dict]:
    """從 section HTML 抽出總教練表，彙總成每位總教練一列（容忍各隊欄位差異）。
    無「時期」欄者以 default_era 墊；無「季後賽/總冠軍」欄者該值為 0。"""
    tables = re.findall(r"<table\b[^>]*>(.*?)</table>", section_html, re.S)
    table = next((t for t in tables
                  if any(k in t for k in _NAME_KEYS) and "勝" in t and "敗" in t), None)
    if not table:
        return []
    header = [c for c, _ in _cells(re.search(r"<tr[^>]*>(.*?)</tr>", table, re.S).group(1))]
    idx = {h: i for i, h in enumerate(header)}
    name_key = next((k for k in _NAME_KEYS if k in idx), None)
    year_key = next((k for k in _YEAR_KEYS if k in idx), None)
    if name_key is None or year_key is None:
        return []
    grid = _expand(table, len(header))

    def col(row, key):
        i = idx.get(key)
        return row[i] if i is not None and i < len(row) else ""

    has_seq = "任次" in idx
    agg: dict[tuple, dict] = {}
    order: list[tuple] = []
    for row in grid[1:]:
        name = col(row, name_key)
        if not name or name in _NAME_KEYS:
            continue
        era = col(row, "時期") or default_era
        seq = col(row, "任次") if has_seq else name  # 無任次欄則同名併為一任
        year = _int(col(row, year_key))
        if not year:
            continue
        key = (era, seq, name)
        if key not in agg:
            agg[key] = {"era_name": era, "name": name, "from_year": year, "to_year": year,
                        "g": 0, "w": 0, "l": 0, "t": 0, "postseason": 0, "championships": 0}
            order.append(key)
        a = agg[key]
        a["from_year"] = min(a["from_year"], year); a["to_year"] = max(a["to_year"], year)
        a["g"] += _int(col(row, "出賽")); a["w"] += _int(col(row, "勝"))
        a["l"] += _int(col(row, "敗")); a["t"] += _int(col(row, "和"))
        a["postseason"] += _int(col(row, "季後賽")); a["championships"] += _int(col(row, "總冠軍"))
    out = []
    for key in order:
        a = agg[key]
        gp = a["w"] + a["l"]
        a["win_pct"] = round(a["w"] / gp, 3) if gp else None
        out.append(a)
    return out


def scrape_managers() -> dict[str, int]:
    """抓 WIKI_TITLE 各 franchise 的歷任總教練，冪等覆蓋 cpbl.managers。回傳各隊筆數。"""
    out: dict[str, int] = {}
    with httpx.Client(headers={"User-Agent": UA}) as client:
        for code, title in WIKI_TITLE.items():
            try:
                sec = _manager_section(client, title)
                if sec is None:
                    log.warning("%s（%s）找不到總教練 section", code, title); continue
                d = _get(client, action="parse", page=title, section=sec, prop="text")
                managers = _parse_managers(d["parse"]["text"]["*"])
            except Exception as e:  # noqa: BLE001
                log.warning("%s（%s）抓取失敗：%s", code, title, e); continue
            if not managers:
                log.warning("%s（%s）解析不到總教練表", code, title); continue
            with conn() as c:
                c.execute("DELETE FROM cpbl.managers WHERE team_code=%s", (code,))
                c.cursor().executemany(
                    "INSERT INTO cpbl.managers (team_code, era_name, name, from_year, to_year, "
                    "g, w, l, t, win_pct, postseason, championships) "
                    "VALUES (%(team_code)s,%(era_name)s,%(name)s,%(from_year)s,%(to_year)s,"
                    "%(g)s,%(w)s,%(l)s,%(t)s,%(win_pct)s,%(postseason)s,%(championships)s) "
                    "ON CONFLICT (team_code, era_name, name, from_year) DO UPDATE SET "
                    "to_year=EXCLUDED.to_year, g=EXCLUDED.g, w=EXCLUDED.w, l=EXCLUDED.l, t=EXCLUDED.t, "
                    "win_pct=EXCLUDED.win_pct, postseason=EXCLUDED.postseason, championships=EXCLUDED.championships",
                    [{**m, "team_code": code} for m in managers],
                )
            out[code] = len(managers)
            log.info("%s（%s）總教練 %d 位", code, title, len(managers))
    return out
