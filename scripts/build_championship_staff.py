# LIFECYCLE: standing · 常設工具——這就是給你跑的；不要刪
"""#470 產生器：冠軍隊年教練團 → ``src/cpbl/resources/championship_staff.v1.json``。

一次性人工執行（不進每日鏈、不註冊 ``cpbl-*`` 入口、不連 DB、不寫 DB）。用法::

    uv run python scripts/build_championship_staff.py --cache <原文快取目錄> [--offline]

資料流（#470 已核定規劃 §3）：
1. 正式站公開 API ``/api/v1/records/championships`` 取 verified 冠軍年、冠軍隊碼、奪冠總教練，
   並與 repo 種子（migration 052／054）逐年核對；2026 只在正式站已有 verified 列時才納入。
2. 台灣棒球維基館（主來源）各冠軍隊年年表頁：人、層級、異動原文。
   年份以頁面內文聯盟年核對（不用頁名換算），頁面隊名對不上冠軍隊碼即標 ``missing``。
3. 中文維基百科「XX年中華職棒總冠軍」模板：逐人補職稱並比對；只一邊有＝單一來源。
4. 補充來源：只對「只在中文維基有」與「層級衝突」者查台灣棒球維基館個人條目（D7）。
5. 正式站 ``/api/v1/people/coach/{name}`` 只取歸戶資訊（player_id／同名歧義），寫進比對報告；
   ``player_id`` 只在下方 ``MANUAL_PLAYER_ID`` 人工明填時寫入資料檔（不自動推定）。

網路上限與停止條件（規劃 §7）：維基只 GET、間隔 ≥0.7 秒、合計 ≤120 次、全程重試 ≤10 次；
正式站只 GET、間隔 ≥0.3 秒、≤250 次、重試 ≤5 次；同一請求第二次失敗、連續 3 次非 JSON、
重試用完、或正式站連續 3 次非 200 即停（保留已抓原文，raise）。
所有回應原文存 ``--cache``；``--offline`` 只讀快取重建（零網路）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from cpbl.ingest import championship_staff_wiki as w  # noqa: E402

OUT = REPO / "src" / "cpbl" / "resources" / "championship_staff.v1.json"
REPORT = REPO / "docs" / "research" / "CHAMPIONSHIP_STAFF_470_REPORT.md"
TW_API = "https://twbsball.dils.tku.edu.tw/api.php"
ZH_API = "https://zh.wikipedia.org/w/api.php"
PROD = "https://cpbl.ruan-ruan.com"
UA = "generic-client/1.0"
NOTE = "名單取自台灣棒球維基館球隊年表與中文維基百科冠軍模板，不保證完整。"

# 冠軍隊年 → 台灣棒球維基館年表頁（頁名的「職棒N年」是球隊自身年次，非聯盟年；
# 年份另以內文核對）。來源：#470 研究 work/champ_titles.json（36 頁全查）。
TW_PAGES: dict[int, str] = {
    1990: "味全龍隊/味全龍隊的職棒元年", 1991: "統一獅隊/統一獅隊的職棒二年",
    1992: "兄弟象隊/兄弟象隊的職棒三年", 1993: "兄弟象隊/兄弟象隊的職棒四年",
    1994: "兄弟象隊/兄弟象隊的職棒五年", 1995: "統一獅隊/統一獅隊的職棒六年",
    1996: "統一獅隊/統一獅隊的職棒七年", 1997: "味全龍隊/味全龍隊的職棒八年",
    1998: "味全龍隊/味全龍隊的職棒九年", 1999: "味全龍隊/味全龍隊的職棒十年",
    2000: "統一獅隊/統一獅隊的職棒十一年", 2001: "兄弟象隊/兄弟象隊的職棒十二年",
    2002: "兄弟象隊/兄弟象隊的職棒十三年", 2003: "兄弟象隊/兄弟象隊的職棒十四年",
    2004: "興農牛隊/興農牛隊的職棒九年", 2005: "興農牛隊/興農牛隊的職棒十年",
    2006: "La New熊隊/La New熊隊的職棒三年", 2007: "統一獅隊/統一獅隊的職棒十八年",
    2008: "統一7-ELEVEn獅隊/統一7-ELEVEn獅隊的職棒十九年",
    2009: "統一7-ELEVEn獅隊/統一7-ELEVEn獅隊的職棒二十年",
    2010: "兄弟象隊/兄弟象隊的職棒二十一年",
    2011: "統一7-ELEVEn獅隊/統一7-ELEVEn獅隊的職棒二十二年",
    2012: "Lamigo桃猿隊/Lamigo桃猿隊的職棒九年",
    2013: "統一7-ELEVEn獅隊/統一7-ELEVEn獅隊的職棒二十四年",
    2014: "Lamigo桃猿隊/Lamigo桃猿隊的職棒十一年", 2015: "Lamigo桃猿隊/Lamigo桃猿隊的職棒十二年",
    2016: "義大犀牛隊/義大犀牛隊的職棒四年", 2017: "Lamigo桃猿隊/Lamigo桃猿隊的職棒十四年",
    2018: "Lamigo桃猿隊/Lamigo桃猿隊的職棒十五年", 2019: "Lamigo桃猿隊/Lamigo桃猿隊的職棒十六年",
    2020: "統一7-ELEVEn獅隊/統一7-ELEVEn獅隊的職棒三十一年",
    2021: "中信兄弟隊/中信兄弟隊的職棒八年", 2022: "中信兄弟隊/中信兄弟隊的職棒九年",
    2023: "味全龍隊/味全龍隊的職棒十五年", 2024: "中信兄弟隊/中信兄弟隊的職棒十一年",
    2025: "樂天桃猿隊/樂天桃猿隊的職棒六年",
    2026: "味全龍隊/味全龍隊的職棒十八年",  # 只在正式站已有 2026 verified 列時才抓
}

# 年表頁的球隊（頁名前綴）→ 冠軍隊碼（migration 052 的 champion_team_code）。
TEAM_CODE = {
    "味全龍隊": "AAA011", "統一獅隊": "ADD011", "統一7-ELEVEn獅隊": "ADD011",
    "兄弟象隊": "ACC011", "興農牛隊": "AEG011", "La New熊隊": "AJK011",
    "Lamigo桃猿隊": "AJK011", "樂天桃猿隊": "AJL011", "中信兄弟隊": "ACN011",
    "義大犀牛隊": "AEM011",
}
# 個人條目補充核對用的隊名關鍵字（經歷行需同時含隊名與「教練」與涵蓋該年）。
TEAM_KEYWORD = {
    "AAA011": "味全", "ADD011": "統一", "ACC011": "兄弟", "AEG011": "興農",
    "AJK011": ("La New", "Lamigo"), "AJL011": "樂天", "ACN011": "中信", "AEM011": "義大",
}

# 人工別名表（#470 規劃 §3.3：明列、不做模糊比對）：同一人的不同寫法。每組第一個是比對鍵。
# 來源：#470 研究 §3 列出的寫法差異，再由比對報告「只出現在一邊的姓名」逐筆人工確認。
ALIAS_GROUPS: list[tuple[str, ...]] = [
    ("竹之內雅史", "竹之内雅史"),   # 內／内 異體字
    ("曹竣崵", "曹竣揚"),           # 崵／揚
    ("凃壯勳", "涂壯勳"),           # 凃／涂
    ("平野惠一", "平野恵一"),       # 惠／恵（日文新字體）
]
# 人工歸戶例外（改名／譯名不同而正式站以姓名對不上者）：(year, name) → player_id。理由見報告。
MANUAL_PLAYER_ID: dict[tuple[int, str], str] = {
    # 台灣棒球維基「吳志峯」出生 1981-06-02（revid 1571663）＝正式站 players 0000003165「吳志峰」
    # birthday 1981-06-02；峯／峰為異體字。cpbl-opendata players.csv 同 id 同生日。
    (2011, "吳志峯"): "0000003165",
}


class Budget:
    def __init__(self, name: str, cap: int, retries: int, gap: float):
        self.name, self.cap, self.retries, self.gap = name, cap, retries, gap
        self.count = 0
        self.retry_used = 0
        self.bad_streak = 0
        self.last = 0.0

    def wait(self) -> None:
        delta = time.monotonic() - self.last
        if delta < self.gap:
            time.sleep(self.gap - delta)
        self.last = time.monotonic()


class Fetcher:
    def __init__(self, cache: Path, offline: bool):
        self.cache, self.offline = cache, offline
        self.cache.mkdir(parents=True, exist_ok=True)
        self.wiki = Budget("wiki", 120, 10, 0.7)
        self.prod = Budget("prod", 250, 5, 0.3)
        self.log: list[dict] = []

    def _key(self, url: str) -> Path:
        return self.cache / f"{hashlib.sha256(url.encode()).hexdigest()[:24]}.json"

    def _legacy_key(self, url: str) -> Path:
        # 第一次實跑時的快取檔名（網址尾段 180 字）；讀到即轉存為新格式（含網址，可核對）
        return self.cache / (re.sub(r"[^0-9A-Za-z一-鿿_.-]+", "_", url)[-180:] + ".json")

    def cached(self) -> list[dict]:
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(self.cache.glob("*.json"))
                if not p.name.startswith("_") and len(p.stem) == 24]

    def get(self, url: str, budget: Budget, *, ok_404: bool = False) -> Any:
        path = self._key(url)
        if path.exists():
            rec = json.loads(path.read_text(encoding="utf-8"))
            if rec.get("url") != url:
                raise SystemExit(f"cache key collision: {path}")
            return rec["data"]
        legacy = self._legacy_key(url)
        if legacy.exists():
            data = json.loads(legacy.read_text(encoding="utf-8"))
            path.write_text(json.dumps({"url": url, "fetched_at": None, "via": "legacy-cache",
                                        "data": data}, ensure_ascii=False), encoding="utf-8")
            return data
        if self.offline:
            raise SystemExit(f"offline: cache miss {url}")
        for attempt in (1, 2):
            if budget.count >= budget.cap:
                raise SystemExit(f"STOP {budget.name}: request cap {budget.cap} reached")
            budget.wait()
            budget.count += 1
            t0 = dt.datetime.now(dt.UTC).isoformat()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=60) as r:
                    status, raw = r.status, r.read()
            except urllib.error.HTTPError as e:
                status, raw = e.code, b""
            except Exception as e:  # noqa: BLE001 - 逾時等：冷卻後單次重抓
                self.log.append({"t": t0, "url": url, "error": type(e).__name__})
                if attempt == 2 or budget.retry_used >= budget.retries:
                    raise SystemExit(f"STOP {budget.name}: second failure / retries used ({url})") from e
                budget.retry_used += 1
                time.sleep(30)
                continue
            self.log.append({"t": t0, "url": url, "status": status})
            if status == 404 and ok_404:
                budget.bad_streak = 0
                data = {"_status": 404}
            elif status != 200:
                budget.bad_streak += 1
                if budget.bad_streak >= 3:
                    raise SystemExit(f"STOP {budget.name}: 3 consecutive non-200")
                if attempt == 2 or budget.retry_used >= budget.retries:
                    raise SystemExit(f"STOP {budget.name}: status {status} twice ({url})")
                budget.retry_used += 1
                continue
            else:
                try:
                    data = json.loads(raw)
                except ValueError as e:
                    budget.bad_streak += 1
                    if budget.bad_streak >= 3:
                        raise SystemExit(f"STOP {budget.name}: 3 consecutive non-JSON") from e
                    if attempt == 2 or budget.retry_used >= budget.retries:
                        raise SystemExit(f"STOP {budget.name}: non-JSON twice ({url})") from e
                    budget.retry_used += 1
                    continue
                budget.bad_streak = 0
            path.write_text(json.dumps({"url": url, "fetched_at": t0, "data": data},
                                       ensure_ascii=False), encoding="utf-8")
            with (self.cache / "_requests.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(self.log[-1], ensure_ascii=False) + "\n")
            return data
        raise SystemExit(f"STOP {budget.name}: exhausted ({url})")


def api_url(base: str, params: dict) -> str:
    return base + "?" + urllib.parse.urlencode({**params, "format": "json"})


def wiki_pages(f: Fetcher, base: str, titles: list[str], *, zh: bool) -> dict[str, dict | None]:
    """批次取頁面原文＋revid（每批 ≤10 頁）；回 {要求頁名: {title,revid,timestamp,text}|None}。"""
    out: dict[str, dict | None] = {}
    for i in range(0, len(titles), 10):
        batch = titles[i:i + 10]
        params = {"action": "query", "prop": "revisions", "rvprop": "ids|timestamp|content",
                  "titles": "|".join(batch), "redirects": "1"}
        if zh:
            params.update({"rvslots": "main", "variant": "zh-tw"})
        d = f.get(api_url(base, params), f.wiki)
        q = d.get("query", {})
        alias = {x["from"]: x["to"] for x in q.get("normalized", []) + q.get("redirects", [])}
        pages = {p["title"]: p for p in q.get("pages", {}).values()}
        for t in batch:
            tt = alias.get(alias.get(t, t), alias.get(t, t))
            p = pages.get(tt)
            if not p or "revisions" not in p:
                out[t] = None
                continue
            rv = p["revisions"][0]
            text = rv["slots"]["main"]["*"] if zh else rv["*"]
            out[t] = {"title": p["title"], "revid": rv.get("revid"),
                      "timestamp": rv.get("timestamp"), "text": text}
    return out


def tw_url(title: str) -> str:
    return "https://twbsball.dils.tku.edu.tw/wiki/index.php/" + title.replace(" ", "_")


def zh_url(title: str) -> str:
    return "https://zh.wikipedia.org/wiki/" + title.replace(" ", "_")


def seed_rows(path: Path, pattern: str) -> dict[int, tuple[str, ...]]:
    out = {}
    for m in re.finditer(pattern, path.read_text(encoding="utf-8")):
        out[int(m.group(1))] = m.groups()[1:]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True, type=Path)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    f = Fetcher(args.cache, args.offline)

    # 1. 冠軍年（正式站 verified）× repo 種子核對
    champs = f.get(PROD + "/api/v1/records/championships", f.prod)
    prod_rows = {s["year"]: s for s in champs.get("seasons", [])}
    seed_ch = seed_rows(REPO / "migrations/052_championships.sql", r"\((\d{4}), '(\w+)',")
    seed_mg = seed_rows(REPO / "migrations/054_championship_managers.sql", r"\((\d{4}), '([^']+)',")
    problems: list[str] = []
    years: list[int] = []
    for y in sorted(prod_rows):
        if y not in TW_PAGES:
            problems.append(f"{y}: 正式站有冠軍列但產生器沒有對應年表頁，未納入")
            continue
        if y in seed_ch and seed_ch[y][0] != prod_rows[y]["champion_team_code"]:
            problems.append(f"{y}: 正式站冠軍隊碼 {prod_rows[y]['champion_team_code']} ≠ 種子 {seed_ch[y][0]}")
        years.append(y)
    for y in seed_ch:
        if y not in prod_rows:
            problems.append(f"{y}: 種子有、正式站 verified 無，未納入")
    managers = {y: w.norm(prod_rows[y].get("manager_name") or (seed_mg.get(y) or ("",))[0])
                for y in years}

    # 2–3. 兩個維基
    tw_titles = [TW_PAGES[y] for y in years]
    tw = wiki_pages(f, TW_API, tw_titles, zh=False)
    zh_titles = {}
    cat = f.get(api_url(ZH_API, {"action": "query", "list": "categorymembers",
                                 "cmtitle": "Category:中華職棒年度總冠軍導航模板",
                                 "cmlimit": "100"}), f.wiki)
    for m in cat["query"]["categorymembers"]:
        mm = re.search(r"(\d{4})年中華職棒總冠軍", m["title"])
        if mm and int(mm.group(1)) in years:
            zh_titles[int(mm.group(1))] = m["title"]
    zh = wiki_pages(f, ZH_API, list(zh_titles.values()), zh=True)

    canon_of = {w.norm(n): w.norm(g[0]) for g in ALIAS_GROUPS for n in g}
    group_of = {w.norm(g[0]): [w.norm(n) for n in g] for g in ALIAS_GROUPS}

    def canon(n: str) -> str:
        return canon_of.get(n, n)

    managers = {y: canon(m) for y, m in managers.items()}
    team_years: list[dict] = []
    report_rows: list[dict] = []
    supplement_needed: list[tuple[int, str, str | None, str]] = []
    prev_names: tuple[int, frozenset[str]] | None = None
    for y in years:
        code = prod_rows[y]["champion_team_code"]
        title = TW_PAGES[y]
        team_prefix = title.split("/")[0]
        team_name = team_prefix.removesuffix("隊")
        page = tw.get(title)
        ztitle = zh_titles.get(y)
        zpage = zh.get(ztitle) if ztitle else None
        ty = {"year": y, "champion_team_code": code, "team_name": team_name, "status": "missing",
              "league_year_check": None, "sources": [], "suspected_copy_of": None, "staff": []}
        team_years.append(ty)
        if page is None:
            problems.append(f"{y}: 台灣棒球維基館年表頁不存在（{title}），標缺漏")
            continue
        ly = w.league_year_mentioned(page["text"], y)
        ty["league_year_check"] = ly
        if not ly:
            problems.append(f"{y}: 年表頁內文找不到聯盟年字樣，停該年、標缺漏")
            continue
        if TEAM_CODE.get(team_prefix) != code:
            problems.append(f"{y}: 年表頁球隊 {team_prefix} 對不上冠軍隊碼 {code}，停該年、標缺漏")
            continue
        ty["sources"].append({"site": "twbsball", "title": page["title"], "url": tw_url(page["title"]),
                              "revid": page["revid"], "timestamp": page["timestamp"]})
        if zpage:
            ty["sources"].append({"site": "zhwiki", "title": zpage["title"], "url": zh_url(zpage["title"]),
                                  "revid": zpage["revid"], "timestamp": zpage["timestamp"]})
        else:
            problems.append(f"{y}: 中文維基冠軍模板不存在，僅單一來源")
        tw_people = {canon(p.name): p for p in w.parse_tw_team_year(page["text"])}
        zh_people = {canon(zp.name): zp for zp in (w.parse_zh_template(zpage["text"]) if zpage else [])}
        mgr = managers[y]
        names = frozenset(n for n in tw_people if n != mgr)
        if prev_names and prev_names[1] == names:
            ty["suspected_copy_of"] = prev_names[0]
        prev_names = (y, names)
        unmatched_zh = sorted(n for n in zh_people if n not in tw_people and n != mgr)
        unmatched_tw = sorted(n for n in tw_people if n not in zh_people and n != mgr)
        conflicts: list[str] = []
        for name in sorted(set(tw_people) | set(zh_people)):
            if name == mgr:
                continue
            tp, zp = tw_people.get(name), zh_people.get(name)
            src = [s for s, x in (("twbsball", tp), ("zhwiki", zp)) if x is not None]
            notes = list(tp.notes) if tp else []
            level = tp.level if tp else "未分層"
            ztitle_ = zp.title if zp and zp.title and zp.title != "總教練" else None
            ttl = ztitle_ or (tp.title if tp and tp.title and "教練" in tp.title else None)
            if zp and zp.title == "總教練":
                notes.append("中文維基百科冠軍模板列為「總教練」")
            if tp and zp and tp.level == "二軍":
                notes.append("層級：台灣棒球維基館列二軍；中文維基百科列入冠軍模板（未分層）")
                conflicts.append(name)
                supplement_needed.append((y, name, tp.wiki_title, "層級衝突"))
            if zp and not tp:
                ctx = w.lines_mentioning(page["text"], name)
                if ctx:
                    notes.append("台灣棒球維基館同頁原文：" + "／".join(ctx))
                supplement_needed.append((y, name, None, "只在中文維基"))
            display = tp.name if tp else zp.name
            raw_aliases = sorted((set(group_of.get(name, [])) | {name} | ({zp.name} if zp else set()))
                                 - {display})
            ty["staff"].append({
                "name": display,
                "wiki_title": tp.wiki_title if tp else None,
                "aliases": raw_aliases,
                "level": level,
                "title": ttl,
                "sources": src,
                "single_source": len(src) == 1,
                "supplement_urls": [],
                "note": "；".join(notes) or None,
                "player_id": MANUAL_PLAYER_ID.get((y, name)),
            })
        ty["status"] = "listed" if ty["staff"] else "missing"
        report_rows.append({"year": y, "team": team_name, "tw_n": len(names),
                            "zh_n": len([n for n in zh_people if n != mgr]),
                            "unmatched_zh": unmatched_zh, "unmatched_tw": unmatched_tw,
                            "conflicts": conflicts, "copy_of": ty["suspected_copy_of"]})

    # 4. 個人條目補充（D7：只查只在中文維基與層級衝突者）
    sup_titles = sorted({t or n for _, n, t, _ in supplement_needed})
    sup_pages = wiki_pages(f, TW_API, sup_titles, zh=False) if sup_titles else {}
    supplement_log = []
    by_year = {ty["year"]: ty for ty in team_years}
    for y, name, t, why in supplement_needed:
        pg = sup_pages.get(t or name)
        ty = by_year[y]
        kw = TEAM_KEYWORD.get(ty["champion_team_code"], ())
        kws = (kw,) if isinstance(kw, str) else kw
        hits = w.career_lines(pg["text"], kws, y) if pg else []
        hit = "／".join(hits) or None
        supplement_log.append({"year": y, "name": name, "why": why, "page": pg["title"] if pg else None,
                               "hit": hit})
        if pg and hit:
            for p in ty["staff"]:
                if canon(w.norm(p["name"])) == name:
                    p["supplement_urls"].append(tw_url(pg["title"]))
                    p["note"] = "；".join(filter(None, [p["note"], f"個人條目：{hit}"]))

    # 5. 歸戶資訊（只寫報告；資料檔 player_id 只取人工明填）
    attrib = {}
    for name in sorted({p["name"] for ty in team_years for p in ty["staff"]}):
        d = f.get(PROD + "/api/v1/people/coach/" + urllib.parse.quote(name), f.prod)
        attrib[name] = {"player_id": d.get("player_id"), "ambiguous": d.get("player_ambiguous"),
                        "has_player_phase": any(h.get("phase") == "player" for h in d.get("history", []))}

    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True,
                            text=True, check=False).stdout.strip() or None
    data = {
        "schema_version": 1,
        "through_year": max(y for y in years),
        "generated_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds"),
        "generator": {"script": "scripts/build_championship_staff.py", "commit": commit},
        "note": NOTE,
        "team_years": team_years,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    write_report(data, report_rows, supplement_log, attrib, problems, f)
    print(json.dumps({"wiki_requests": f.wiki.count, "wiki_retries": f.wiki.retry_used,
                      "prod_requests": f.prod.count, "prod_retries": f.prod.retry_used,
                      "team_years": len(team_years),
                      "staff_rows": sum(len(t["staff"]) for t in team_years),
                      "problems": problems}, ensure_ascii=False, indent=1))
    return 0


def write_report(data, rows, sup, attrib, problems, f) -> None:
    hosts: dict[str, int] = {}
    for rec in f.cached():
        k = "prod" if rec["url"].startswith(PROD) else "wiki"
        hosts[k] = hosts.get(k, 0) + 1
    L = ["# #470 冠軍隊年教練團比對報告", "",
         "由 `scripts/build_championship_staff.py` 產生，與 `src/cpbl/resources/championship_staff.v1.json` 同一次執行。",
         f"- 產生時間：{data['generated_at']}；generator commit：`{data['generator']['commit']}`",
         f"- 資料截至：{data['through_year']}；冠軍隊年 {len(data['team_years'])} 個；"
         f"教練團列 {sum(len(t['staff']) for t in data['team_years'])} 筆",
         f"- 網路請求（快取內每個成功回應一檔；本次執行新增：維基 {f.wiki.count}、正式站 {f.prod.count}）："
         f"維基 {hosts.get('wiki', 0)} 次、正式站 {hosts.get('prod', 0)} 次", "",
         "## 問題與停止條件", ""]
    L += [f"- {p}" for p in problems] or ["- 無"]
    L += ["", "## 逐年", "",
          "| 年 | 冠軍隊 | 狀態 | 聯盟年核對 | tw 人數 | zh 人數 | 單一來源 | 疑似沿用 |",
          "|---|---|---|---|---|---|---|---|"]
    by = {r["year"]: r for r in rows}
    for t in data["team_years"]:
        r = by.get(t["year"], {})
        single = sum(1 for p in t["staff"] if p["single_source"])
        L.append(f"| {t['year']} | {t['team_name']} | {t['status']} | {t['league_year_check'] or '—'} | "
                 f"{r.get('tw_n', '—')} | {r.get('zh_n', '—')} | {single} | {t['suspected_copy_of'] or ''} |")
    L += ["", "## 只出現在一邊的姓名（逐年；人工核對寫法差異用）", ""]
    for r in rows:
        if r["unmatched_zh"] or r["unmatched_tw"]:
            L.append(f"- {r['year']}：只在中文維基 {('、'.join(r['unmatched_zh']) or '—')}；"
                     f"只在台灣棒球維基 {('、'.join(r['unmatched_tw']) or '—')}")
    L += ["", "## 人工別名表（ALIAS_GROUPS；同一人的不同寫法，不做模糊比對）", ""]
    L += [f"- {'＝'.join(g)}" for g in ALIAS_GROUPS]
    L += ["", "## 層級衝突（台灣棒球維基列二軍、中文維基列入冠軍模板；照台灣棒球維基並附註，D4）", ""]
    L += [f"- {r['year']}：{'、'.join(r['conflicts'])}" for r in rows if r["conflicts"]] or ["- 無"]
    L += ["", "## 附註含原文的列（季中異動、前任／代理總教練、矛盾原文）", ""]
    for t in data["team_years"]:
        for p in t["staff"]:
            if p["note"]:
                L.append(f"- {t['year']} {p['name']}（{p['level']}；{'／'.join(p['sources'])}）：{p['note']}")
    L += ["", "## 個人條目補充（D7）", ""]
    for s in sup:
        L.append(f"- {s['year']} {s['name']}（{s['why']}）：條目 {s['page'] or '不存在'}；"
                 f"{'採用：' + s['hit'] if s['hit'] else '未找到同時含隊名、教練、涵蓋該年的經歷行，未附網址'}")
    L += ["", "## 歸戶（正式站 /api/v1/people/coach/{name}；資料檔不寫入，讀取時再以 players 唯一同名歸戶）", ""]
    amb = [n for n, a in attrib.items() if a["ambiguous"]]
    maybe = [n for n, a in attrib.items() if not a["player_id"] and a["has_player_phase"]]
    linked = [n for n, a in attrib.items() if a["player_id"]]
    L.append(f"- 唯一同名對到球員：{len(linked)} 人；同名歧義（不歸戶）：{len(amb)} 人；"
             f"無球員頁：{len(attrib) - len(linked) - len(amb)} 人")
    L.append(f"- 同名歧義：{'、'.join(amb) or '無'}")
    L.append(f"- 有球員經歷但對不到 player_id（可能改名或譯名不同，人工決定）：{'、'.join(maybe) or '無'}")
    L.append(f"- 人工歸戶例外（MANUAL_PLAYER_ID）：{MANUAL_PLAYER_ID or '無'}")
    L += ["", "## 疑似沿用前一年名單（D9：頁面不標，只記錄）", ""]
    L += [f"- {t['year']}＝{t['suspected_copy_of']}" for t in data["team_years"] if t["suspected_copy_of"]] or ["- 無"]
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
