"""#470 冠軍隊年教練團：兩個維基的 wikitext 解析（純函式，不連網、不寫 DB）。

只服務 ``scripts/build_championship_staff.py``（一次性人工執行的產生器）。刻意**不**重用
``cpbl_team_history.parse_staff``／``parse_season``：研究（#470 research answer §4）實測
前者 36 個冠軍隊年頁有 16 頁抽不全、後者把頁名的「球隊自身第 N 年」當聯盟年；
修正既有爬蟲歸 #472（需求方 #470 規劃確認 D8），本模組不碰它。

年份一律以頁面內文的聯盟年核對（``league_year_mentioned``），不用頁名換算。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_CN_DIGITS = "零一二三四五六七八九"
_NAME_NOISE = re.compile(r"[\s　・·．‧•･]")


def norm(name: str | None) -> str:
    return _NAME_NOISE.sub("", name or "")


def cn_number(n: int) -> str:
    """1..99 → 中文數字（1→元 由呼叫端處理）。"""
    if n < 10:
        return _CN_DIGITS[n]
    tens, ones = divmod(n, 10)
    head = "" if tens == 1 else _CN_DIGITS[tens]
    return head + "十" + (_CN_DIGITS[ones] if ones else "")


def league_year_mentioned(wikitext: str, year: int) -> str | None:
    """頁面內文有沒有寫該年的聯盟年（職棒 N 年，N＝year−1989）；回傳命中的字樣。"""
    n = year - 1989
    forms = [f"職棒{n}年", f"職棒{cn_number(n)}年"]
    if n == 1:
        forms.append("職棒元年")
    for f in forms:
        if f in wikitext:
            return f
    return None


# ---------------------------------------------------------------------------
# 台灣棒球維基館：球隊年表頁
# ---------------------------------------------------------------------------

_LINE = re.compile(r"^[:*]+\s*(?P<label>[^：:\n]{1,40}?)\s*[：:](?P<body>.*)$")
_STAFF_LABELS = {"總教練", "教練", "教練團", "教練團成員", "一軍教練團", "二軍教練團",
                 "巡迴教練團", "一軍", "二軍"}
_SKIP_LABELS = {"領隊", "副領隊"}  # 不列（需求方 #470 第 8 題），但不終止名單區塊
_LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_PAREN = re.compile(r"[(（]([^()（）]*)[)）]")


def _plain(s: str) -> str:
    """去掉 wiki 連結與粗體標記，保留顯示文字。"""
    s = _LINK.sub(lambda m: m.group(2) or m.group(1), s)
    return s.replace("'''", "").strip()


def level_of(label: str) -> str:
    if label.startswith("一軍"):
        return "一軍"
    if label.startswith("二軍"):
        return "二軍"
    if label.startswith("巡迴"):
        return "巡迴"
    return "未分層"


@dataclass
class TwPerson:
    name: str                     # 顯示名（正規化）
    wiki_title: str | None        # 台灣棒球維基館個人條目頁名（純文字未連結＝None）
    level: str
    title: str | None = None      # 括號內職稱原文（含「教練」者）
    notes: list[str] = field(default_factory=list)
    manager_line: bool = False    # 出現在「總教練：」行（季中換帥、代理）


def _link_disp(m: re.Match) -> str:
    """連結顯示文字；無顯示文字時去掉頁名尾端的消歧義括號（例：呂文生(1962)）。"""
    return (m.group(2) or re.sub(r"\s*[(（][^()（）]*[)）]$", "", m.group(1))).strip()


def _parse_token(tok: str) -> tuple[str, str | None, list[str]]:
    m = _LINK.search(tok)
    sub = _LINK.sub(_link_disp, tok).replace("'''", "")
    parens = [x.strip() for x in _PAREN.findall(sub) if x.strip()]
    if m:
        wiki_title: str | None = m.group(1).strip()
        disp = _link_disp(m)
    else:
        wiki_title, disp = None, _PAREN.sub("", sub).strip()
    disp = re.sub(r"[。．.\s]+$", "", disp)
    return norm(disp), wiki_title, parens


def _split_body(body: str) -> tuple[list[str], str | None]:
    body = body.strip()
    line_note = None
    m = re.search(r"[。.]\s*[(（]([^()（）]*)[)）]\s*$", body)
    if m:  # 例：2001–2003「…吳思賢。(王光輝與劉義傳仍兼任球員)」
        line_note = _plain(m.group(1))
        body = body[: m.start()]
    body = body.rstrip("。. 　")
    # 以頓號／逗號分人；括號內不切
    toks, depth, cur = [], 0, ""
    for ch in body:
        if ch in "(（[":
            depth += 1
        elif ch in ")）]":
            depth -= 1
        if depth <= 0 and ch in "、，,":
            toks.append(cur)
            cur = ""
            continue
        cur += ch
    toks.append(cur)
    out: list[str] = []
    for t in toks:
        out += [x for x in re.split(r"-->|→", t) if x.strip()]
    return out, line_note


def _add(people: dict[str, TwPerson], p: TwPerson) -> None:
    old = people.get(p.name)
    if old is None:
        people[p.name] = p
        return
    if old.manager_line and not p.manager_line:
        old.level = p.level  # 同時出現在總教練行與教練行：層級以教練行為準
    old.manager_line = old.manager_line or p.manager_line
    old.wiki_title = old.wiki_title or p.wiki_title
    old.title = old.title or p.title
    old.notes += [n for n in p.notes if n not in old.notes]


def parse_tw_team_year(wikitext: str) -> list[TwPerson]:
    """抽球隊年表頁的教練名單區塊（含總教練行；領隊、副領隊不列）。"""
    if "'''總教練'''" in wikitext:  # 1999 表格式
        return _parse_tw_table(wikitext)
    people: dict[str, TwPerson] = {}
    started = False
    for raw in wikitext.splitlines():
        line = raw.strip()
        if line.startswith("="):
            if started:
                break
            continue
        m = _LINE.match(line)
        if not m:
            continue
        label = norm(_plain(m.group("label")))
        if label in _SKIP_LABELS:
            continue
        if label not in _STAFF_LABELS:
            if started:
                break
            continue
        started = True
        body = m.group("body")
        if not body.strip():
            continue
        toks, line_note = _split_body(body)
        is_mgr_line = label == "總教練"
        level = level_of(label)
        raw_text = f"{_plain(m.group('label'))}：{_plain(body).strip()}"
        for t in toks:
            name, wiki_title, parens = _parse_token(t)
            if not name or len(name) > 12:
                continue
            p = TwPerson(name=name, wiki_title=wiki_title, level=level, manager_line=is_mgr_line)
            for par in parens:
                if par == "二軍教練":
                    p.level = "二軍"
                    p.notes.append(f"原文註「{par}」")
                elif "教練" in par and "總教練" not in par:
                    p.title = par
                elif par == "總教練":
                    p.title = "總教練"
                else:
                    p.notes.append(f"原文註「{par}」")
            if is_mgr_line:
                p.notes.append(f"原文「{raw_text}」")
            if line_note and name in norm(line_note):
                p.notes.append(f"原文註「{line_note}」")
            _add(people, p)
    return list(people.values())


def _parse_tw_table(wikitext: str) -> list[TwPerson]:
    seg = wikitext[wikitext.find("'''總教練'''"): wikitext.find("'''投手'''")]
    people: dict[str, TwPerson] = {}
    mgr = True
    for line in seg.splitlines():
        if "'''教練'''" in line:
            mgr = False
            continue
        m = re.match(r"^\*\s*\d*\s*(.+)$", line.strip())
        if not m:
            continue
        name, wiki_title, _ = _parse_token(m.group(1))
        if name:
            p = TwPerson(name=name, wiki_title=wiki_title, level="未分層", manager_line=mgr)
            if mgr:
                p.notes.append("原文「總教練」")
            _add(people, p)
    return list(people.values())


def lines_mentioning(wikitext: str, name: str, limit: int = 2, window: int = 40) -> list[str]:
    """頁面中提到此人的原文片段（去標記；長行只取姓名前後 window 字），供矛盾附註。"""
    out = []
    for raw in wikitext.splitlines():
        if "Category:" in raw or "分類:" in raw:
            continue
        plain = re.sub(r"\s+", " ", _plain(raw).replace("<br>", " ").lstrip(":*# ")).strip()
        squashed = norm(plain)
        if not name or name not in squashed:
            continue
        if len(plain) > window * 2 + len(name):
            i = plain.find(name)
            if i < 0:  # 原文姓名中有全形空白（例「飛 勇」）：取正規化後字串
                plain, i = squashed, squashed.find(name)
            lo, hi = max(0, i - window), i + len(name) + window
            plain = ("…" if lo else "") + plain[lo:hi] + ("…" if hi < len(plain) else "")
        out.append(plain)
        if len(out) >= limit:
            break
    return out


def career_lines(wikitext: str, keywords: tuple[str, ...], year: int) -> list[str]:
    """個人條目「經歷」條列中，同時含隊名關鍵字、「教練」且起訖年涵蓋 year 的行（原文去標記）。"""
    out = []
    for raw in wikitext.splitlines():
        if not raw.lstrip(" :").startswith("*") or "Category:" in raw:
            continue
        line = _plain(raw).lstrip(":*# ").strip()
        if "教練" not in line or not any(k in line for k in keywords):
            continue
        rng = re.search(r"[（(]([^（）()]*\d{4}年[^（）()]*)[）)]", line)
        if rng and _covers(rng.group(1), year):
            out.append(line)
    return out


def _covers(span: str, year: int) -> bool:
    ys = [int(y) for y in re.findall(r"(\d{4})年", span)]
    if not ys:
        return False
    if len(ys) == 1:
        return ys[0] == year or (ys[0] <= year and bool(re.search(r"[～~－-]\s*$", span)))
    return min(ys) <= year <= max(ys)


# ---------------------------------------------------------------------------
# 中文維基百科：「XX年中華職棒總冠軍」導航模板
# ---------------------------------------------------------------------------

_ZH_ITEM = re.compile(
    r"^\s*(?P<title>[^\d\[\{<>|]*?)\s*(?P<num>\d+)?\s*"
    r"(?:\[\[(?P<link>[^\]|]+)(?:\|(?P<disp>[^\]]+))?\]\]"
    r"|\{\{Link-en\|(?P<le>[^|}]+)\|[^|}]*\|(?P<led>[^}]+)\}\})")


@dataclass
class ZhPerson:
    name: str
    title: str | None
    link: str


def parse_zh_template(wikitext: str) -> list[ZhPerson]:
    """取模板中「總教練」之後的教練（含總教練本人；由呼叫端排除）。"""
    body = re.sub(r"<noinclude>.*", "", wikitext, flags=re.S)
    body = body.replace("-{", "").replace("}-", "")
    body = body.split("|below", 1)[0]
    i = body.find("總教練")
    if i < 0:
        return []
    part = body[i:]
    part = re.sub(r"\{\{nowrap (?:begin|end)\}\}|</?span[^>]*>", "", part)
    items = re.split(r"\{\{!w?\}\}|<br\s*/?>|\n\*?", part)
    out: list[ZhPerson] = []
    seen: set[str] = set()
    for it in items:
        m = _ZH_ITEM.match(it)
        if not m:
            continue
        link = (m.group("link") or m.group("le") or "").strip()
        disp = (m.group("disp") or m.group("led") or link).strip()
        name = norm(re.sub(r"\s*[(（][^)）]*[)）]\s*$", "", disp))
        title = (m.group("title") or "").strip() or None
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(ZhPerson(name=name, title=title, link=link))
    return out
