"""官方進階數據爬蟲（stats.cpbl.com.tw）。

該站為 Next.js App Router，資料內嵌於 RSC 串流（self.__next_f.push）。流程：
1. GET /players/{acnt} → 取出所有 push 字串串接、unicode unescape 還原 payload。
2. 以括號配對擷取含 "wobaPr" 的彙總物件（打者=進攻、投手=被打；PR 官方已定向）。
冪等 UPSERT。無公開 JSON API，解析較脆弱：站改版時 _summary_object 會抓不到，據此判斷。
"""

from __future__ import annotations

import json
import logging
import re
import time

import httpx

from cpbl.db import conn

log = logging.getLogger("cpbl.advanced")

BASE = "https://stats.cpbl.com.tw"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')


def _payload(client: httpx.Client, acnt: str) -> str:
    html = client.get(f"{BASE}/players/{acnt}").text
    chunks = _PUSH_RE.findall(html)
    return "".join(chunks).encode().decode("unicode_escape", errors="replace")


def _summary_object(payload: str, key: str = "wobaPr") -> dict | None:
    """以括號配對擷取「含 key 的最內層物件」並解析。找不到/解析失敗回 None。"""
    i = payload.find(f'"{key}"')
    if i < 0:
        return None
    depth, j = 0, i
    while j > 0:  # 往左找物件開頭
        c = payload[j]
        if c == "}":
            depth += 1
        elif c == "{":
            if depth == 0:
                break
            depth -= 1
        j -= 1
    depth, k = 0, j
    while k < len(payload):  # 往右括號配對找結尾
        c = payload[k]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                break
        k += 1
    try:
        return json.loads(payload[j:k + 1])
    except (json.JSONDecodeError, ValueError):
        return None


def _record(d: dict, year: int, acnt: str, role: str) -> tuple:
    g = d.get
    return (
        year, acnt, role, g("pa"),
        g("woba"), g("wobaPr"), g("ba"), g("baPr"), g("slg"), g("slgPr"),
        g("iso"), g("isoPr"), g("obp"), g("obpPr"),
        g("brl"), g("brlPr"), g("brlp"), g("prlpPr"),  # 官方 barrel% PR 鍵為 prlpPr
        g("ev"), g("evPr"), g("maxEv"), g("maxEvPr"),
        g("hardHitp"), g("hardHitpPr"), g("kp"), g("kpPr"), g("bbp"), g("bbpPr"),
        g("whiffp"), g("whiffpPr"), g("chasep"), g("chasepPr"),
    )


_COLS = ("year,acnt,role,pa,woba,woba_pr,ba,ba_pr,slg,slg_pr,iso,iso_pr,obp,obp_pr,"
         "brl,brl_pr,brlp,brlp_pr,ev,ev_pr,max_ev,max_ev_pr,hardhitp,hardhitp_pr,"
         "kp,kp_pr,bbp,bbp_pr,whiffp,whiffp_pr,chasep,chasep_pr")


def _upsert(records: list[tuple]) -> int:
    if not records:
        return 0
    col_list = [c.strip() for c in _COLS.split(",")]
    ph = "(" + ",".join(["%s"] * len(col_list)) + ")"
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in col_list[3:]) + ", updated_at=now()"
    with conn() as c:
        c.cursor().executemany(
            f"INSERT INTO cpbl.advanced_stats ({_COLS}) VALUES {ph} "
            f"ON CONFLICT (year, acnt, role) DO UPDATE SET {updates}",
            records,
        )
    return len(records)


def scrape_advanced(year: int, players: list[tuple[str, str]], delay: float = 1.0) -> int:
    """players = [(acnt, role)]；抓官方進階彙總並 UPSERT。回傳成功筆數。"""
    client = httpx.Client(timeout=40.0, headers={"User-Agent": UA}, follow_redirects=True)
    records: list[tuple] = []
    try:
        for idx, (acnt, role) in enumerate(players, 1):
            time.sleep(delay)
            try:
                obj = _summary_object(_payload(client, acnt))
            except httpx.HTTPError as e:
                log.warning("[%d/%d] acnt=%s HTTP 失敗：%s", idx, len(players), acnt, e)
                continue
            if not obj:
                log.warning("[%d/%d] acnt=%s 無進階資料（或站改版）", idx, len(players), acnt)
                continue
            records.append(_record(obj, year, acnt, role))
            if idx % 20 == 0:
                log.info("[%d/%d] 進階數據抓取中…", idx, len(players))
    finally:
        client.close()
    return _upsert(records)


def current_players() -> list[tuple[str, str]]:
    """本季登錄選手 [(acnt, role)]；同時是打者與投手者取打者（進攻數值較常看）。"""
    with conn() as c:
        bats = {r[0] for r in c.execute("SELECT DISTINCT player_id FROM cpbl.batting_current").fetchall()}
        pits = {r[0] for r in c.execute("SELECT DISTINCT player_id FROM cpbl.pitching_current").fetchall()}
    players = [(a, "batting") for a in sorted(bats)]
    players += [(a, "pitching") for a in sorted(pits - bats)]
    return players
