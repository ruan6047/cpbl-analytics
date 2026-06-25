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
import time

import httpx

from cpbl.db import conn

log = logging.getLogger("cpbl.managers")

WIKI_API = "https://zh.wikipedia.org/w/api.php"
UA = "cpbl-analytics/1.0 (baseball analytics; contact via github)"

# franchise team_code（對齊 team_dim）→ zh.wikipedia 條目標題（條目通常涵蓋整個 franchise 各時期）。
# 各隊總教練資料格式不一：有的有專表（中信兄弟「按總教練分」），有的嵌在逐年戰績表的
# 「總教練」欄並以「○○時期」分隔列分段（富邦＝俊國/興農/義大/富邦、味全、台鋼）。
# _parse_managers 會自動找「含 姓名/總教練 欄 + 勝場」的表，兩種格式皆通吃。
WIKI_TITLE = {
    "AAA011": "味全龍",
    "ACN011": "中信兄弟",          # 含 兄弟象
    "ADD011": "統一7-ELEVEn獅",
    "AEO011": "富邦悍將",          # 含 俊國熊 / 興農牛 / 義大犀牛
    "AJL011": "樂天桃猿",          # 含 第一金剛 / La New / Lamigo
    "AKP011": "台鋼雄鷹",
}


def _get(client: httpx.Client, **params) -> dict:
    params.setdefault("format", "json")
    params.setdefault("maxlag", "5")
    for attempt in range(4):  # 429/maxlag → 退避重試（維基限速）
        r = client.get(WIKI_API, params=params, timeout=25)
        if r.status_code == 429 or (r.status_code == 200 and "maxlag" in r.text[:200]):
            time.sleep(2 * (attempt + 1)); continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return r.json()


def _clean_name(name: str) -> str:
    """去掉維基姓名後的註記（如「竹之內雅史（日语：…）」）。"""
    return re.sub(r"[（(].*$", "", name).strip()


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


def _col_idx(header: list[str], *names: str) -> int | None:
    for n in names:
        if n in header:
            return header.index(n)
    return None


def _best_table(article_html: str) -> tuple[str, list[str]] | None:
    """全文找「含 姓名/總教練 欄 + 勝(場) 欄」的表，取列數最多者（最完整）。"""
    best = None
    best_rows = -1
    for tb in re.findall(r"<table\b[^>]*>(.*?)</table>", article_html, re.S):
        htr = re.search(r"<tr[^>]*>(.*?)</tr>", tb, re.S)
        if not htr:
            continue
        hdr = [c for c, _ in _cells(htr.group(1))]
        if not any(k in hdr for k in _NAME_KEYS) or not any(w in hdr for w in ("勝", "勝場")):
            continue
        n = len(re.findall(r"<tr", tb))
        if n > best_rows:
            best, best_rows = (tb, hdr), n
    return best


def _parse_managers(article_html: str, default_era: str = "") -> list[dict]:
    """從整篇條目找總教練表並彙總每位任期戰績。通吃兩種格式：
    (a) 專表（中信兄弟「按總教練分」：時期/任次/姓名…）；
    (b) 逐年戰績表含「總教練」欄、以「○○時期」分隔列分段（富邦/味全/台鋼）。
    欄名容差：姓名↔總教練、球季↔年度、勝↔勝場、出賽↔執教場次。缺欄者該值 0/沿用 default。"""
    found = _best_table(article_html)
    if not found:
        return []
    table, header = found
    name_i = _col_idx(header, *_NAME_KEYS)
    year_i = _col_idx(header, *_YEAR_KEYS)
    if name_i is None or year_i is None:
        return []
    g_i = _col_idx(header, "出賽", "執教場次", "場次")
    w_i = _col_idx(header, "勝", "勝場")
    l_i = _col_idx(header, "敗", "敗場")
    t_i = _col_idx(header, "和", "和局")
    po_i = _col_idx(header, "季後賽")
    ch_i = _col_idx(header, "總冠軍")
    era_i = _col_idx(header, "時期")
    seq_i = _col_idx(header, "任次")
    ncols = len(header)

    def val(row, i):
        return row[i] if i is not None and i < len(row) else ""

    agg: dict[tuple, dict] = {}
    order: list[tuple] = []
    cur_era = default_era
    carry: dict[int, list] = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S):
        cs = _cells(tr)
        if len(cs) == 1:  # 時期分隔列（如「俊國熊時期」）
            txt = cs[0][0].strip()
            if txt and not any(k in txt for k in ("勝", *_NAME_KEYS)):
                cur_era = re.sub(r"時期$", "", txt).strip() or cur_era
            carry = {}
            continue
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
        name = _clean_name(val(row, name_i))
        if not name or name in _NAME_KEYS or name in ("--", "—", "-", "合計", "總計", "小計", "累計"):
            continue
        year = _int(val(row, year_i))
        if year < 1989 or year > 2035:  # 跳過合計/累計列（年份非合理球季）
            continue
        era = (val(row, era_i) if era_i is not None else "") or cur_era
        seq = val(row, seq_i) if seq_i is not None else name  # 無任次欄則同名併為一任
        key = (era, seq, name)
        if key not in agg:
            agg[key] = {"era_name": era, "name": name, "from_year": year, "to_year": year,
                        "g": 0, "w": 0, "l": 0, "t": 0, "postseason": 0, "championships": 0}
            order.append(key)
        a = agg[key]
        a["from_year"] = min(a["from_year"], year); a["to_year"] = max(a["to_year"], year)
        a["g"] += _int(val(row, g_i)); a["w"] += _int(val(row, w_i))
        a["l"] += _int(val(row, l_i)); a["t"] += _int(val(row, t_i))
        a["postseason"] += _int(val(row, po_i)); a["championships"] += _int(val(row, ch_i))
    out = []
    for key in order:
        a = agg[key]
        gp = a["w"] + a["l"]
        a["win_pct"] = round(a["w"] / gp, 3) if gp else None
        out.append(a)
    return out


def scrape_managers() -> dict[str, int]:
    """抓 WIKI_TITLE 各 franchise 的歷任總教練，冪等覆蓋 cpbl.managers。回傳各隊筆數。
    抓整篇條目自動找總教練表（專表或逐年戰績表的總教練欄皆可），跨隊教練（洪一中@富邦、
    葉君璋@味全）由各自球隊的逐年表自然涵蓋。"""
    out: dict[str, int] = {}
    with httpx.Client(headers={"User-Agent": UA}) as client:
        for code, title in WIKI_TITLE.items():
            time.sleep(0.6)  # 維基限速
            try:
                d = _get(client, action="parse", page=title, prop="text")
                if "error" in d:
                    log.warning("%s（%s）無條目", code, title); continue
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
