"""教練團奪冠紀錄（#470；唯讀）。

資料來源是 repo 內版本化資料檔 ``resources/championship_staff.v1.json``，由
``scripts/build_championship_staff.py`` 一次性人工執行產生（兩個維基合併；不進每日鏈、
不寫 DB）。本模組只做載入、結構驗證、以正式庫冠軍表過濾年份與讀取時歸戶。

刻意設計（⛔ 不得推出別的結論）：

- **不併入個人冠軍次數**：教練團奪冠是獨立欄位，``championship_members`` 與紀錄頁
  個人冠軍榜的計法（球員＋總教練）不受影響（需求方 #470 第 4 題）。
- **年份以正式庫 ``cpbl.championships`` verified 為準**：資料檔的冠軍隊碼與該年
  verified 隊碼不同、或該年未 verified 時，該年整筆不回（不靠資料檔自證）。
- **歸戶只歸唯一同名**：球員頁以 ``players.name`` 對資料檔姓名／別名，該名在 players
  唯一才歸；資料檔有人工明填 ``player_id`` 時只以 id 歸，不再以姓名歸到別人。
  同名多人時不歸戶（只留在以姓名定址的教練頁）——嚴禁腦補歸戶。
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

RESOURCE = Path(__file__).resolve().parent.parent / "resources" / "championship_staff.v1.json"

LEVELS = frozenset({"一軍", "二軍", "未分層", "巡迴"})
STATUSES = frozenset({"listed", "missing"})
SOURCE_SITES = frozenset({"twbsball", "zhwiki"})
SOURCE_LABELS = {"twbsball": "台灣棒球維基館", "zhwiki": "中文維基百科"}

# 姓名正規化：只去掉排版差異（全形／半形空白、各種間隔號），不做模糊比對。
_NAME_NOISE = re.compile(r"[\s　・·．‧•･]")


def norm_name(name: str | None) -> str:
    return _NAME_NOISE.sub("", name or "")


@lru_cache(maxsize=1)
def load(path: str | None = None) -> dict[str, Any]:
    p = Path(path) if path else RESOURCE
    return json.loads(p.read_text(encoding="utf-8"))


def validate(data: dict[str, Any]) -> list[str]:
    """結構驗證；回傳錯誤訊息清單（空＝通過）。"""
    errs: list[str] = []
    for k in ("schema_version", "through_year", "generated_at", "generator", "note", "team_years"):
        if k not in data:
            errs.append(f"top-level missing {k}")
    years = [ty.get("year") for ty in data.get("team_years", [])]
    if len(years) != len(set(years)):
        errs.append("duplicate team_year")
    for ty in data.get("team_years", []):
        y = ty.get("year")
        if ty.get("status") not in STATUSES:
            errs.append(f"{y}: bad status {ty.get('status')!r}")
        if not ty.get("champion_team_code"):
            errs.append(f"{y}: missing champion_team_code")
        sites = {s.get("site") for s in ty.get("sources", [])}
        for s in ty.get("sources", []):
            if s.get("site") not in SOURCE_SITES or not str(s.get("url", "")).startswith("https://"):
                errs.append(f"{y}: bad source {s!r}")
        if ty.get("status") == "listed" and not ty.get("staff"):
            errs.append(f"{y}: listed without staff")
        if ty.get("status") == "missing" and ty.get("staff"):
            errs.append(f"{y}: missing with staff")
        seen: set[str] = set()
        for p in ty.get("staff", []):
            nm = norm_name(p.get("name"))
            if not nm:
                errs.append(f"{y}: staff without name")
            if nm in seen:
                errs.append(f"{y}: duplicate staff {nm}")
            seen.add(nm)
            if p.get("level") not in LEVELS:
                errs.append(f"{y} {nm}: bad level {p.get('level')!r}")
            src = p.get("sources") or []
            if not src and not p.get("supplement_urls"):
                errs.append(f"{y} {nm}: no source")
            for s in src:
                if s not in sites:
                    errs.append(f"{y} {nm}: source {s!r} not in team-year sources")
            if p.get("single_source") != (len(set(src)) == 1):
                errs.append(f"{y} {nm}: single_source inconsistent")
            for u in p.get("supplement_urls") or []:
                if not str(u).startswith("https://"):
                    errs.append(f"{y} {nm}: bad supplement url {u!r}")
    return errs


def _item(ty: dict[str, Any], p: dict[str, Any]) -> dict[str, Any]:
    by_site = {s["site"]: s for s in ty.get("sources", [])}
    sources = [{"site": s, "label": SOURCE_LABELS.get(s, s), "url": by_site[s]["url"]}
               for s in p.get("sources") or [] if s in by_site]
    sources += [{"site": "supplement", "label": "補充來源", "url": u}
                for u in p.get("supplement_urls") or []]
    return {
        "year": ty["year"],
        "team_code": ty["champion_team_code"],
        "team_name": ty.get("team_name"),
        "level": p["level"],
        "title": p.get("title"),
        "single_source": bool(p.get("single_source")),
        "sources": sources,
        "note": p.get("note"),
    }


def _collect(data: dict[str, Any], verified: dict[int, str], match) -> dict[str, Any] | None:
    items: list[dict[str, Any]] = []
    missing: list[int] = []
    for ty in data.get("team_years", []):
        y = ty.get("year")
        if verified.get(y) != ty.get("champion_team_code"):
            continue
        if ty.get("status") == "missing":
            missing.append(y)
            continue
        items += [_item(ty, p) for p in ty.get("staff", []) if match(p)]
    if not items:
        return None
    items.sort(key=lambda i: i["year"], reverse=True)
    return {"through_year": data.get("through_year"), "items": items,
            "missing_years": sorted(missing), "note": data.get("note")}


def _names(p: dict[str, Any]) -> set[str]:
    return {norm_name(n) for n in [p.get("name"), *(p.get("aliases") or [])] if n}


def staff_for_player(data: dict[str, Any], verified: dict[int, str], player_id: str,
                     pname: str | None, name_unique: bool) -> dict[str, Any] | None:
    key = norm_name(pname)

    def match(p: dict[str, Any]) -> bool:
        if p.get("player_id"):
            return p["player_id"] == player_id
        return bool(key) and name_unique and key in _names(p)

    return _collect(data, verified, match)


def staff_for_name(data: dict[str, Any], verified: dict[int, str],
                   name: str) -> dict[str, Any] | None:
    key = norm_name(name)
    return _collect(data, verified, lambda p: bool(key) and key in _names(p))


# ---------------------------------------------------------------------------
# DB 讀取薄層（唯讀；API 只呼叫這兩支）
# ---------------------------------------------------------------------------

_VERIFIED_SQL = ("SELECT year, champion_team_code FROM cpbl.championships "
                 "WHERE verification_status = 'verified'")


def _verified(cur) -> dict[int, str]:
    cur.execute(_VERIFIED_SQL)
    return {int(y): code for y, code in cur.fetchall()}


def fetch_for_player(cur, player_id: str) -> dict[str, Any] | None:
    cur.execute("SELECT name FROM cpbl.players WHERE id = %s", (player_id,))
    row = cur.fetchone()
    pname = row[0] if row else None
    data = load()
    unique = False
    if pname:
        cur.execute("SELECT count(*) FROM cpbl.players WHERE name = %s", (pname,))
        unique = int(cur.fetchone()[0] or 0) == 1
    return staff_for_player(data, _verified(cur), player_id, pname, unique)


def fetch_for_coach(cur, name: str) -> dict[str, Any] | None:
    return staff_for_name(load(), _verified(cur), name)
