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
from dataclasses import dataclass

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
_COLS = "year,kind_code,acnt,role,metrics," + ",".join(c for c, _ in _LEGACY)


def _record(merged: dict, year: int, acnt: str, role: str, kind_code: str = "A") -> tuple:
    return (year, kind_code, acnt, role, json.dumps(merged)) + tuple(merged.get(jk) for _, jk in _LEGACY)


def _upsert(records: list[tuple]) -> int:
    if not records:
        return 0
    col_list = [c.strip() for c in _COLS.split(",")]
    ph = "(" + ",".join("%s::jsonb" if c == "metrics" else "%s" for c in col_list) + ")"
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in col_list[4:]) + ", updated_at=now()"  # PK 後(year,kind,acnt,role)
    with conn() as c:
        c.cursor().executemany(
            f"INSERT INTO cpbl.advanced_stats ({_COLS}) VALUES {ph} "
            f"ON CONFLICT (year, kind_code, acnt, role) DO UPDATE SET {updates}",
            records,
        )
    return len(records)


# 官方 leaderboard JSON API（/api/proxy 代理；免瀏覽器、含 gameKind=A/D、searchType=batter/pitcher）。
# 四表合併＝完整 ~65 指標/人。key 由 PascalCase 正規化為既有 lowerCamel（少數不規則列例外）。
_LEADERBOARDS = ("pr-table", "exit-velocity", "batted-ball", "pitch-tracking")
_KEY_FIX = {"Ev50th": "ev50Th", "Ev90th": "ev90Th", "DistanceAvgHR": "distanceAvgHr", "BrlsBBEp": "brlsBbEp"}


@dataclass(frozen=True)
class AdvancedScrapeResult:
    rows: int
    outcome: str
    error_codes: tuple[str, ...]


def _norm_key(k: str) -> str:
    if k in _KEY_FIX:
        return _KEY_FIX[k]
    return (k[0].lower() + k[1:]).replace("PR", "Pr")


def _fetch_leaderboards(client: httpx.Client, search_type: str, game_kind: str, year: int,
                        delay: float = 0.5) -> dict[str, dict]:
    """回 {acnt: 合併指標}。四個 leaderboard 依 Player.Acnt 合併，取所有純數值欄。"""
    out: dict[str, dict] = {}
    for lb in _LEADERBOARDS:
        r = client.get(f"{BASE}/api/proxy/v1/leaderboards/{lb}",
                       params={"searchType": search_type, "gameKind": game_kind, "year": str(year)})
        r.raise_for_status()
        rows = ((r.json().get("Data") or {}).get("Leaderboard") or [])
        for row in rows:
            acnt = (row.get("Player") or {}).get("Acnt")
            if not acnt:
                continue
            m = out.setdefault(acnt, {})
            for k, v in row.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    m[_norm_key(k)] = v
        time.sleep(delay)
    return out


def scrape_advanced_result(year: int, players: list[tuple[str, str]], delay: float = 1.0,
                           kind_code: str = "A") -> AdvancedScrapeResult:
    """抓官方進階並保留可觀測 outcome；不宣稱 game-level completion。"""
    client = httpx.Client(timeout=40.0, headers={"User-Agent": UA, "Accept": "application/json",
                                                 "Referer": f"{BASE}/rankings"}, follow_redirects=True)
    records: list[tuple] = []
    errors: list[str] = []
    want_b = {a for a, r in players if r == "batting"}
    want_p = {a for a, r in players if r == "pitching"}
    try:
        for role, search_type, want in (("batting", "batter", want_b), ("pitching", "pitcher", want_p)):
            if not want:
                continue
            try:
                lb = _fetch_leaderboards(client, search_type, kind_code, year, delay=min(delay, 0.5))
            except httpx.HTTPError as e:
                log.warning("leaderboard %s/%s 抓取失敗：%s", search_type, kind_code, e)
                errors.append(f"{role}_http_error")
                continue
            hit = [_record(m, year, a, role, kind_code) for a, m in lb.items() if a in want and m]
            records += hit
            log.info("進階 %s kind=%s：leaderboard %d 人，命中 %d", role, kind_code, len(lb), len(hit))
    finally:
        client.close()
    rows = _upsert(records)
    outcome = "error" if errors else ("available" if rows > 0 else "missing")
    return AdvancedScrapeResult(rows=rows, outcome=outcome, error_codes=tuple(errors))


def scrape_advanced(year: int, players: list[tuple[str, str]], delay: float = 1.0,
                    kind_code: str = "A") -> int:
    """相容既有 CLI 的整數介面；refresh instrumentation 使用 result 版本。"""
    return scrape_advanced_result(year, players, delay=delay, kind_code=kind_code).rows


def current_players() -> list[tuple[str, str]]:
    """本季登錄選手 [(acnt, role)]；同時是打者與投手者取打者（進攻數值較常看）。"""
    with conn() as c:
        bats = {r[0] for r in c.execute("SELECT DISTINCT player_id FROM cpbl.batting_current").fetchall()}
        pits = {r[0] for r in c.execute("SELECT DISTINCT player_id FROM cpbl.pitching_current").fetchall()}
    players = [(a, "batting") for a in sorted(bats)]
    players += [(a, "pitching") for a in sorted(pits - bats)]
    return players
