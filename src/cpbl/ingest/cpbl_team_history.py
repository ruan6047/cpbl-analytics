"""隊史年表爬蟲（twbsball「分類:職棒球隊年表」，246 個「球隊×年度」頁）。

補三個缺口：歷年教練團、歷年改名／異動、二軍獎項。**職稱與獎項名稱一律照抄原文**——
早期只有「總教練」與「教練」兩級（ruan6047 07-15 指正），不得腦補成助理教練／投手教練；
獎項名稱不做正規化，避免把不同年代的獎項硬歸成同一種。

不收逐年球員陣容：頁面自述來源為「本站歷年球員背號頁」與民生報年鑑，屬次級來源，而球員
資料已有官網逐場一手來源。
"""

from __future__ import annotations

import logging
import re
import time

from cpbl.db import conn
from cpbl.franchises import franchise_of
from cpbl.ingest.cpbl_coaches_history import CPBL_TEAM_MAP, _get, fetch_wikitext

log = logging.getLogger("cpbl.team_history")

CATEGORY = "分類:職棒球隊年表"

# 職棒元年＝1990；「職棒N年」→ 1989 + N
_CN_NUM = {"元": 1, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
           "八": 8, "九": 9, "十": 10}


def parse_season(title: str) -> int | None:
    """`…的職棒三十四年` → 2023（職棒元年＝1990）。"""
    m = re.search(r"職棒([元一二三四五六七八九十]+)年", title)
    if not m:
        return None
    s = m.group(1)
    if s == "元":
        n = 1
    elif "十" in s:
        head, _, tail = s.partition("十")
        n = (_CN_NUM.get(head, 1) if head else 1) * 10 + (_CN_NUM.get(tail, 0) if tail else 0)
    else:
        n = _CN_NUM.get(s, 0)
    return 1989 + n if n else None


def parse_team(title: str) -> str | None:
    """由頁名前綴判隊；回 franchise 隊碼（與 championships／managers 同一空間）。"""
    head = title.split("/")[0]
    for kw, code in sorted(CPBL_TEAM_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if kw in head:
            return franchise_of(code)
    return None


def _clean(s: str) -> str:
    """展開 wiki 連結取顯示文字、去粗體與全形空白。"""
    s = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[\[|\]\]|'''|''", "", s)
    return s.replace("　", "").strip()


def _split_names(raw: str, split_arrow: bool = False) -> list[tuple[str, str | None]]:
    """`王鏡銘(8月20日)、潘傑楷(季後，10月26日)` → [(王鏡銘, 8月20日), (潘傑楷, 季後，10月26日)]。

    **不能直接用頓號/逗號切**——括號內的註記本身含逗號（「季後，10月26日」），直接切會把
    人名切碎（實測潘彥廷的改名紀錄因此整筆消失）。改為逐字掃描，括號內的分隔符不視為斷點。

    `split_arrow` 只給**教練名單**用（季中換人寫成「黃煚隆→林瑋恩」＝兩個人）。改名欄的
    「舊名-->新名」也是箭頭但**語意相反**（同一個人），若一併切開會讓改名解析全滅——
    實測就踩過這個回歸，故以參數區隔而非一律切。
    """
    text = _clean(raw)
    parts, buf, depth = [], [], 0
    for ch in text:
        if ch in "（(":
            depth += 1
        elif ch in "）)":
            depth = max(0, depth - 1)
        if ch in "、,，" and depth == 0:
            parts.append("".join(buf)); buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))

    out: list[tuple[str, str | None]] = []
    for part in parts:
        part = part.strip().rstrip("。")
        if not part:
            continue
        # 原文偶有漏掉分隔符：「郭泰源（總教練）高政華」→ 括號後仍有下一個人名。
        # 也有季中換人寫成「黃煚隆→林瑋恩」→ 兩人皆收，箭頭留作 note。
        for seg in re.split(r"(?<=[\)）])(?=[^\)）\s])", part):
            segs = re.split(r"\s*(?:→|-->|->)\s*", seg) if split_arrow else [seg]
            for i, nm in enumerate(segs):
                nm = nm.strip()
                if not nm:
                    continue
                m = re.match(r"^([^\(（]+)[\(（]([^\)）]*)[\)）]?$", nm)
                if m:
                    out.append((m.group(1).strip(), m.group(2).strip()))
                elif 1 < len(nm) <= 12:
                    out.append((nm, "接替前任" if i else None))
    return out


_SECTION = re.compile(r"^={2,4}\s*([^=]+?)\s*={2,4}$", re.M)


def _section(wikitext: str, name: str) -> str:
    """取某區塊內容（到下一個標題為止）。"""
    m = re.search(rf"^={{2,4}}\s*{re.escape(name)}\s*={{2,4}}$(.*?)(?=^={{2,4}})",
                  wikitext, re.M | re.S)
    return m.group(1) if m else ""


_STAFF_ROLES = ("總教練", "教練", "領隊", "副領隊")


def parse_staff(wikitext: str) -> list[tuple[str, str, str, str | None]]:
    """歷年教練團 → [(role, name, level, note)]。role／level **照抄原文**，不自創分類。

    兩種頁面格式（早期與近年並存，必須都支援）：
      早期：`*總教練：田宮謙次郎` / `*教　練：中村典夫、成田幸洋`（無一二軍分層）
      近年：`*教練團成員：` → `:*一軍教練團：黃甘霖（總教練）、高政華、劉育辰(下半季代理總教練)`
            → 括號內有職稱者照抄該職稱，其餘為「教練」；level 記一軍／二軍。
    """
    out: list[tuple[str, str, str, str | None]] = []
    body = "\n".join(_section(wikitext, s) for s in
                     ("球隊人員", "行政團隊", "球隊陣容", "選手陣容"))

    level = ""
    for line in body.splitlines():
        s = line.strip()

        m2 = re.match(r"^:+\*+\s*(一軍|二軍)教練團：\s*(.+)$", s)
        if m2:                                    # 近年格式
            level = m2.group(1)
            for name, note in _split_names(m2.group(2), split_arrow=True):
                role = "教練"
                if note:
                    hit = next((r for r in _STAFF_ROLES if r in note), None)
                    if hit:
                        role = hit               # 「（總教練）」「(下半季起代理總教練)」
                out.append((role, name, level, note))
            continue

        m = re.match(r"^\*+\s*([^：\n]{2,6})：\s*(.+)$", s)
        if not m:
            continue
        role = m.group(1).replace("　", "").strip()
        if role not in _STAFF_ROLES:
            continue          # 投手／捕手／內野手／外野手＝逐年陣容（次級來源，不收）
        for name, note in _split_names(m.group(2), split_arrow=True):
            out.append((role, name, "", note))
    return out


def parse_name_changes(wikitext: str) -> list[tuple[str, str, str | None]]:
    """`更改姓名：薛惟中-->薛种帷、潘彥廷-->潘傑楷(季後，10月26日)` → [(舊, 新, 備註)]。"""
    out: list[tuple[str, str, str | None]] = []
    for line in _section(wikitext, "球隊異動").splitlines():
        m = re.match(r"^\*+\s*更改姓名：\s*(.+)$", line.strip())
        if not m:
            continue
        # 用括號感知的切法：註記本身含逗號（「(季後，10月26日)」），直接切會漏掉整筆
        for new_with_note, note in _split_names(m.group(1)):
            mm = re.match(r"^(.+?)\s*(?:-->|→|—>|->)\s*(.+)$", new_with_note)
            if mm:
                out.append((mm.group(1).strip(), mm.group(2).strip(), note))
    return out


_MOVE_KINDS = ("合約所屬轉註冊", "註銷註冊", "新進人員", "離隊人員")


def parse_moves(wikitext: str) -> list[tuple[str, str, str | None]]:
    """球隊異動 → [(kind, name, detail)]。kind 照抄原文。"""
    out: list[tuple[str, str, str | None]] = []
    kind: str | None = None
    for line in _section(wikitext, "球隊異動").splitlines():
        s = line.strip()
        m = re.match(r"^\*+\s*([^：\n]{2,8})：\s*(.*)$", s)
        if m and m.group(1).strip() in _MOVE_KINDS:
            kind = m.group(1).strip()
            for name, det in _split_names(m.group(2)):
                out.append((kind, name, det))
            continue
        if kind and re.match(r"^[:#]+", s):       # 新進/離隊的次層（教練：／球員：／選拔會指名…）
            body = re.sub(r"^[:#\*\)\s]+", "", s)
            body = re.sub(r"^[^：]{2,10}：", "", body)   # 去掉「教練：」「球員：」等次標
            for name, det in _split_names(body):
                out.append((kind, name, det))
    return out


def parse_awards(wikitext: str) -> list[tuple[str, str, str]]:
    """獲獎紀錄 → [(level, name, award_raw)]。獎項名稱不正規化（避免跨年代硬歸類）。"""
    out: list[tuple[str, str, str]] = []
    level: str | None = None
    for line in _section(wikitext, "獲獎紀錄").splitlines():
        s = _clean(line.strip())
        if re.match(r"^\*\s*(一軍|二軍)\s*$", line.strip()):
            level = re.sub(r"[\*\s]", "", line.strip())
            continue
        if not level or not s or not line.strip().startswith(":"):
            continue
        s = re.sub(r"^[:\*#\s]+", "", s)        # 剝掉項目符號（否則人名前會黏著「:*」）
        m = re.match(r"^([一-鿿A-Za-z．・\.]{2,6})(獲得|獲選|榮獲)(.+)$", s)
        if m:
            out.append((level, m.group(1).strip(), m.group(3).strip().rstrip("。")))
    return out


def category_pages() -> list[str]:
    d = _get({"action": "query", "list": "categorymembers",
              "cmtitle": CATEGORY, "cmlimit": 500})
    return [x["title"] for x in d.get("query", {}).get("categorymembers", [])]


def run(throttle: float = 0.4) -> dict:
    """爬 246 頁隊史年表入庫。冪等：每頁先清該年該隊再寫。"""
    pages = category_pages()
    st = {"pages": len(pages), "parsed": 0, "skipped": 0,
          "staff": 0, "name_changes": 0, "moves": 0, "awards": 0}

    for title in pages:
        year, team = parse_season(title), parse_team(title)
        if not year or not team:
            st["skipped"] += 1
            log.warning("略過（無法判定年份／球隊）：%s", title)
            continue
        wt = fetch_wikitext(title)
        if not wt:
            st["skipped"] += 1
            continue

        staff = parse_staff(wt)
        changes = parse_name_changes(wt)
        moves = parse_moves(wt)
        awards = parse_awards(wt)

        with conn() as c:
            cur = c.cursor()
            for tbl in ("team_year_staff", "player_name_changes", "team_year_awards",
                        "roster_moves"):
                cur.execute(f"DELETE FROM cpbl.{tbl} WHERE year=%s AND team_code=%s",
                            (year, team))
            for role, name, level, note in staff:
                cur.execute("INSERT INTO cpbl.team_year_staff "
                            "(year, team_code, role, name, level, note) "
                            "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                            (year, team, role, name, level, note))
            for old, new, note in changes:
                cur.execute("INSERT INTO cpbl.player_name_changes "
                            "(year, team_code, old_name, new_name, note) VALUES (%s,%s,%s,%s,%s) "
                            "ON CONFLICT DO NOTHING", (year, team, old, new, note))
            for kind, name, det in moves:
                cur.execute("INSERT INTO cpbl.roster_moves (year, team_code, kind, name, detail) "
                            "VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                            (year, team, kind, name, det))
            for level, name, award in awards:
                cur.execute("INSERT INTO cpbl.team_year_awards "
                            "(year, team_code, level, name, award_raw) VALUES (%s,%s,%s,%s,%s) "
                            "ON CONFLICT DO NOTHING", (year, team, level, name, award))

        st["parsed"] += 1
        st["staff"] += len(staff)
        st["name_changes"] += len(changes)
        st["moves"] += len(moves)
        st["awards"] += len(awards)
        time.sleep(throttle)

    log.info("team history: %s", st)
    return st
