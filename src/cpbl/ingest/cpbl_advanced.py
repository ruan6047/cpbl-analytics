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


def _payload_url(client: httpx.Client, path: str) -> str:
    """抓某路徑的 RSC push 串接、unicode unescape 還原 payload。"""
    html = client.get(f"{BASE}{path}").text
    chunks = _PUSH_RE.findall(html)
    return "".join(chunks).encode().decode("unicode_escape", errors="replace")


def _payload(client: httpx.Client, acnt: str) -> str:
    return _payload_url(client, f"/players/{acnt}")


def _object_at(payload: str, key: str) -> dict | None:
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


# 球員頁的進階彙總物件（wobaPr）為「球員個人值」；但 gbp/距離/barrel 區塊是「聯盟參考值」，
# 個人豐富指標需改抓 /rankings（每列一球員）。故主流程走 /rankings；player-page wobaPr 留作投手被打用。
def _merge_metrics(payload: str) -> dict:
    """球員頁 wobaPr 彙總物件的所有數值欄（球員個人值；投手即被打數值）。"""
    merged: dict = {}
    obj = _object_at(payload, "wobaPr")
    if obj:
        for k, v in obj.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                merged[k] = v
    return merged


_RANK_KV = re.compile(r'"([a-zA-Z][a-zA-Z0-9]+)":(-?\d+\.?\d*)')
_RANK_ACNT = re.compile(r'"acnt":"(\d+)"')
# 非指標的數值欄（JSON-LD/版面），不入 metrics
_SKIP_KEYS = {"position", "width", "height", "size"}


def _rankings(client: httpx.Client) -> dict[str, dict]:
    """抓 /rankings（官方進階排行榜）：每列一球員，回 {acnt: 完整指標 dict}。

    以 acnt 切視窗、擷取視窗內所有 "key":number（指標無關，自動含未來新增欄位）。
    各分類陣列中同 acnt 多次出現 → 自動合併成該球員完整指標。
    """
    payload = _payload_url(client, "/rankings")
    acnts = [(m.start(), m.group(1)) for m in _RANK_ACNT.finditer(payload)]
    out: dict[str, dict] = {}
    for i, (pos, acnt) in enumerate(acnts):
        end = acnts[i + 1][0] if i + 1 < len(acnts) else pos + 1500
        m = out.setdefault(acnt, {})
        for k, v in _RANK_KV.findall(payload[pos:end]):
            if k in _SKIP_KEYS:
                continue
            m[k] = float(v) if "." in v else int(v)
    return out


# legacy typed 欄位 ↔ metrics key（向後相容；分析改走 advanced_flat view）
_LEGACY = (
    ("pa", "pa"), ("woba", "woba"), ("woba_pr", "wobaPr"), ("ba", "ba"), ("ba_pr", "baPr"),
    ("slg", "slg"), ("slg_pr", "slgPr"), ("iso", "iso"), ("iso_pr", "isoPr"),
    ("obp", "obp"), ("obp_pr", "obpPr"), ("brl", "brl"), ("brl_pr", "brlPr"),
    ("brlp", "brlp"), ("brlp_pr", "prlpPr"), ("ev", "ev"), ("ev_pr", "evPr"),
    ("max_ev", "maxEv"), ("max_ev_pr", "maxEvPr"), ("hardhitp", "hardHitp"), ("hardhitp_pr", "hardHitpPr"),
    ("kp", "kp"), ("kp_pr", "kpPr"), ("bbp", "bbp"), ("bbp_pr", "bbpPr"),
    ("whiffp", "whiffp"), ("whiffp_pr", "whiffpPr"), ("chasep", "chasep"), ("chasep_pr", "chasepPr"),
)
_COLS = "year,acnt,role,metrics," + ",".join(c for c, _ in _LEGACY)


def _record(merged: dict, year: int, acnt: str, role: str) -> tuple:
    return (year, acnt, role, json.dumps(merged)) + tuple(merged.get(jk) for _, jk in _LEGACY)


def _upsert(records: list[tuple]) -> int:
    if not records:
        return 0
    col_list = [c.strip() for c in _COLS.split(",")]
    ph = "(" + ",".join("%s::jsonb" if c == "metrics" else "%s" for c in col_list) + ")"
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in col_list[3:]) + ", updated_at=now()"
    with conn() as c:
        c.cursor().executemany(
            f"INSERT INTO cpbl.advanced_stats ({_COLS}) VALUES {ph} "
            f"ON CONFLICT (year, acnt, role) DO UPDATE SET {updates}",
            records,
        )
    return len(records)


def scrape_advanced(year: int, players: list[tuple[str, str]], delay: float = 1.0) -> int:
    """打者進階走 /rankings（一次全員、含豐富指標）；投手被打進階走球員頁 wobaPr。UPSERT 回傳筆數。"""
    client = httpx.Client(timeout=40.0, headers={"User-Agent": UA}, follow_redirects=True)
    records: list[tuple] = []
    batters = {a for a, r in players if r == "batting"}
    pitchers = [a for a, r in players if r == "pitching"]
    try:
        # 1) 打者：/rankings 一次抓全（rich，~60 指標/人）
        try:
            rank = _rankings(client)
            for acnt, m in rank.items():
                if acnt in batters and m:
                    records.append(_record(m, year, acnt, "batting"))
            log.info("/rankings 解析 %d 人，命中本季打者 %d", len(rank), len(records))
        except httpx.HTTPError as e:
            log.warning("/rankings 抓取失敗：%s", e)

        # 2) 投手被打進階：球員頁 wobaPr 彙總物件（per-player）
        for idx, acnt in enumerate(pitchers, 1):
            time.sleep(delay)
            try:
                merged = _merge_metrics(_payload(client, acnt))
            except httpx.HTTPError as e:
                log.warning("[投手 %d/%d] acnt=%s HTTP 失敗：%s", idx, len(pitchers), acnt, e)
                continue
            if merged:
                records.append(_record(merged, year, acnt, "pitching"))
            if idx % 20 == 0:
                log.info("[投手 %d/%d] 進階數據抓取中…", idx, len(pitchers))
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
