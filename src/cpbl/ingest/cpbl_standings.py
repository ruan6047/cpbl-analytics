"""官方球隊戰績爬蟲（standings/seasonaction，含上下半季）。

回傳 HTML 表格；每列 16 cell：排名+隊名 / 出賽 / 勝-和-敗 / 勝率 / 勝差 / 淘汰指數 /
對戰各隊×6 / 主場 / 客場 / 連勝敗 / 近十場。SeasonCode：0全年 1上半 2下半。冪等 UPSERT。

⚠️ **官網忽略 `Year` 參數，恆回當季**（2026-08-20 實證：`Year=2025` 與 `Year=2024` 回一字
不差的 2026 當季數字）。而回應的 16 個 cell 全是隊名與數字，**沒有任何欄位帶年份**，所以
「我拿到的是不是我請求的那一年」無法由回應自證。舊版直接把請求的 `year` 蓋章寫入，
`ON CONFLICT DO UPDATE` 再覆蓋原本正確的資料——`team_standings` 的 `year=2025` 12 列因此
裝的是 2026 期中數字。

修法是**在寫入邊界對帳**：回應的每隊 `(g, w, t, l)` 必須與本地 `cpbl.games` 推導的該年
（該半季）完成場戰績**逐隊完全相符**，不符即拒寫並拋 :class:`StandingsYearMismatch`。
判準採 `(g, w, t, l)` 四元組而非只用 `g`：不同年份的例行賽總場數可能相同（2024 與 2025
皆為每隊 120 場），只比 `g` 對「兩個都已完賽的球季」沒有鑑別力。

⭐ 壞掉的**只有 `Year`**：`SeasonCode` 實測**有被遵守**（2026-08-20 跑當季，0/1/2 三個
SeasonCode 分別對上本地推導的全年 88/87…、上半 60/59…、下半 28/27… 且逐隊相符；若
`SeasonCode` 也被忽略，三次會拿到同一批數字、後兩次必然對帳失敗）。
"""

from __future__ import annotations

import json
import logging
import re

from cpbl.completion import completed_games_sql_with_evidence
from cpbl.db import conn

log = logging.getLogger("cpbl.standings")

BASE = "https://www.cpbl.com.tw"
PAGE = f"{BASE}/standings/season"
ACTION = f"{BASE}/standings/seasonaction"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_TOKEN_RE = re.compile(r"RequestVerificationToken:\s*'([^']+)'")

# H2H 欄位固定順序（對應表頭）→ team_code
H2H_ORDER = ["AAA011", "AEO011", "AKP011", "ADD011", "AJL011", "ACN011"]
NAME_CODE = {"味全龍": "AAA011", "中信兄弟": "ACN011", "統一7-ELEVEn獅": "ADD011",
             "富邦悍將": "AEO011", "樂天桃猿": "AJL011", "台鋼雄鷹": "AKP011"}
_TXT = re.compile(r"<[^>]+>")


def _clean(html: str) -> str:
    return re.sub(r"\s+", "", _TXT.sub("", html)).replace("\xa0", "")


def _wtl(s: str) -> tuple[int | None, int | None, int | None]:
    m = re.match(r"(\d+)-(\d+)-(\d+)", s or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (None, None, None)


def fetch_standings(year: int, season_code: int, kind_code: str = "A") -> list[tuple]:
    from cpbl.ingest._browser import session
    s = session()
    m = _TOKEN_RE.search(s.page_html("/standings/season", require=_TOKEN_RE))
    if not m:
        raise RuntimeError("standings 找不到 RequestVerificationToken（官網可能改版）")
    status, html = s.post(
        "/standings/season", "/standings/seasonaction",
        {"Year": str(year), "KindCode": kind_code, "SeasonCode": str(season_code)},
        headers={"RequestVerificationToken": m.group(1)},
    )
    if status != 200:
        raise RuntimeError(f"standings HTTP {status}（反爬挑戰未過？）")
    first = html[: html.find("</table>") + 8]  # 只取第一張（戰績）表
    records = []
    for tr in re.findall(r"<tr>(.*?)</tr>", first, re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(tds) < 16:
            continue
        name = next((n for n in NAME_CODE if n in tr), None)
        if not name:
            continue
        code = NAME_CODE[name]
        rank_m = re.search(r'rank">(\d+)', tds[0])
        g = _clean(tds[1])
        w, t, l = _wtl(_clean(tds[2]))
        wp = _clean(tds[3])
        gb_raw = _clean(tds[4])
        h2h = {H2H_ORDER[i]: _clean(tds[6 + i]) for i in range(6)
               if H2H_ORDER[i] != code and re.match(r"\d+-\d+-\d+", _clean(tds[6 + i]))}
        records.append((
            year, kind_code, season_code, code, name,
            int(rank_m.group(1)) if rank_m else None, int(g) if g.isdigit() else None,
            w, t, l, float(wp) if re.match(r"[0-9.]+$", wp) else None,
            0.0 if gb_raw in ("-", "") else (float(gb_raw) if re.match(r"[0-9.]+$", gb_raw) else None),
            _clean(tds[5]) or None, _clean(tds[12]) or None, _clean(tds[13]) or None,
            _clean(tds[14]) or None, _clean(tds[15]) or None, json.dumps(h2h, ensure_ascii=False),
        ))
    return records


_COLS = ("year,kind_code,season_code,team_code,team_name,rank,g,w,t,l,win_pct,gb,elim,"
         "home_record,away_record,streak,last10,h2h")

# records 元組的欄位位置（與 _COLS 同序）——對帳只用得到這幾個
_IDX_YEAR, _IDX_KIND, _IDX_SC, _IDX_TEAM = 0, 1, 2, 3
_IDX_G, _IDX_W, _IDX_T, _IDX_L = 6, 7, 8, 9


class StandingsYearMismatch(RuntimeError):
    """回應內容對不上「我請求的年份」——官網忽略 `Year` 參數的已知缺陷。

    這是**正確性違規不是暫時性故障**：拿到的是別的球季的數字，寫下去就是污染。
    故它與抓取失敗（token 沒拿到、428、逾時）刻意分開處理——後者是「什麼都沒拿到」，
    不會產生錯資料，維持既有的略過該 SeasonCode 行為；前者必須外拋。
    """


def _local_expectation(
    year: int, season_code: int, kind_code: str = "A",
) -> tuple[int, dict[str, tuple[int, int, int, int]]]:
    """由本地 `cpbl.games` 推導該年（該半季）的逐隊 `(g, w, t, l)`。

    回傳 `(賽程列數, {team_code: (g, w, t, l)})`。賽程列數＝該年該半季 `cpbl.games` 的
    隊×場列數（含未完成場），用來判斷「本地根本沒有這一年的賽程」——那種情況下沒有任何
    東西可以拿來對帳，必須 fail closed，否則就成了一個構造上不會失敗的檢查
    （例：季前所有隊 g 都是 0，對一個我們沒有賽程的年份會恆真通過）。

    `season_code` 0＝全年（不篩半季）、1/2＝上/下半季，對應 `games.game_season_code`。
    完成場判定沿用全案 canonical 的 `completed_games_sql_with_evidence`。
    """
    done = completed_games_sql_with_evidence("games")
    seg = " AND games.game_season_code = %s" if season_code in (1, 2) else ""
    seg_params: tuple = (str(season_code),) if season_code in (1, 2) else ()
    base = (year, kind_code, *seg_params)
    with conn() as c:
        sched = c.execute(
            "SELECT tc, count(*) FROM ("
            f"  SELECT games.home_team_code AS tc FROM cpbl.games WHERE games.year=%s AND games.kind_code=%s{seg}"
            "  UNION ALL"
            f"  SELECT games.away_team_code FROM cpbl.games WHERE games.year=%s AND games.kind_code=%s{seg}"
            ") x WHERE tc IS NOT NULL GROUP BY tc",
            base + base,
        ).fetchall()
        played = c.execute(
            "SELECT tc, count(*), count(*) FILTER (WHERE rs > ra), "
            "count(*) FILTER (WHERE rs = ra), count(*) FILTER (WHERE rs < ra) FROM ("
            "  SELECT games.home_team_code AS tc, games.home_score AS rs, games.away_score AS ra "
            f"    FROM cpbl.games WHERE games.year=%s AND games.kind_code=%s AND {done}{seg}"
            "  UNION ALL"
            "  SELECT games.away_team_code, games.away_score, games.home_score "
            f"    FROM cpbl.games WHERE games.year=%s AND games.kind_code=%s AND {done}{seg}"
            ") x WHERE tc IS NOT NULL GROUP BY tc",
            base + base,
        ).fetchall()
    expected = {tc: (0, 0, 0, 0) for tc, _ in sched}
    expected.update({tc: (g, w, t, l) for tc, g, w, t, l in played})
    return sum(n for _, n in sched), expected


def check_year_consistency(
    year: int,
    season_code: int,
    observed: dict[str, tuple[int, int, int, int]],
    scheduled: int,
    expected: dict[str, tuple[int, int, int, int]],
) -> bool:
    """純函式對帳：回應的逐隊 `(g, w, t, l)` 是否真的是 `year` 那一年的戰績。

    回傳 True＝驗證通過且有資料可寫；False＝回應為空但本地該半季也還沒有完成場
    （季前／下半季未開打的正常狀態，沒有東西可寫也沒有東西可驗）。
    對不上一律拋 :class:`StandingsYearMismatch`——**寧可不寫，不可寫錯**。
    """
    if scheduled == 0:
        raise StandingsYearMismatch(
            f"{year} SeasonCode={season_code}：本地 cpbl.games 沒有這一年的賽程，"
            "無從對帳（官網忽略 Year 恆回當季，無法確認拿到的是哪一年）→ 拒寫")
    if not observed:
        if any(v != (0, 0, 0, 0) for v in expected.values()):
            raise StandingsYearMismatch(
                f"{year} SeasonCode={season_code}：官網回應無任何球隊列，但本地已有完成場"
                f"（{ {k: v[0] for k, v in sorted(expected.items()) if v[0]} }）→ 拒寫")
        return False
    if set(observed) != set(expected):
        raise StandingsYearMismatch(
            f"{year} SeasonCode={season_code}：球隊集合對不上——回應 {sorted(observed)}／"
            f"本地賽程 {sorted(expected)} → 拒寫")
    diffs = [(tc, observed[tc], expected[tc]) for tc in sorted(expected)
             if observed[tc] != expected[tc]]
    if diffs:
        raise StandingsYearMismatch(
            f"{year} SeasonCode={season_code}：回應的 (g,w,t,l) 與本地 cpbl.games 推導的 "
            f"{year} 年戰績不符 → 拒寫。官網已知忽略 Year 參數恆回當季，這通常表示拿到的"
            "是**當季**而不是請求的年份。逐隊差異（隊: 回應 vs 本地）："
            + "；".join(f"{tc} {o} vs {e}" for tc, o, e in diffs))
    return True


def verify_year(
    year: int, season_code: int, kind_code: str,
    observed: dict[str, tuple[int, int, int, int]],
) -> bool:
    """取本地期望值後做 :func:`check_year_consistency` 對帳。"""
    scheduled, expected = _local_expectation(year, season_code, kind_code)
    return check_year_consistency(year, season_code, observed, scheduled, expected)


def _observed(records: list[tuple]) -> dict[str, tuple[int, int, int, int]]:
    return {r[_IDX_TEAM]: (r[_IDX_G], r[_IDX_W], r[_IDX_T], r[_IDX_L]) for r in records}


def upsert_standings(records: list[tuple]) -> int:
    """寫入前一律對帳；不符即拋，**絕不先寫再記 warning**。

    對帳放在寫入邊界（而不是 fetch 之後）是刻意的：任何取得 records 的路徑都不可能
    繞過它。年份／半季由 records 自帶的欄位取得——那正是要被驗證的「蓋章值」。
    """
    if not records:
        return 0
    years = {r[_IDX_YEAR] for r in records}
    kinds = {r[_IDX_KIND] for r in records}
    codes = {r[_IDX_SC] for r in records}
    if len(years) != 1 or len(kinds) != 1 or len(codes) != 1:
        raise StandingsYearMismatch(
            f"一次 upsert 混了多個 (year, kind_code, season_code)：{sorted(years)} "
            f"{sorted(kinds)} {sorted(codes)}——無法對帳 → 拒寫")
    verify_year(years.pop(), codes.pop(), kinds.pop(), _observed(records))
    cols = [c.strip() for c in _COLS.split(",")]
    ph = "(" + ",".join(["%s"] * (len(cols) - 1) + ["%s::jsonb"]) + ")"
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols[4:]) + ", updated_at=now()"
    with conn() as c:
        c.cursor().executemany(
            f"INSERT INTO cpbl.team_standings ({_COLS}) VALUES {ph} "
            f"ON CONFLICT (year, kind_code, season_code, team_code) DO UPDATE SET {updates}",
            records,
        )
    return len(records)


def scrape_standings(year: int, kind_code: str = "A") -> dict:
    """抓全年(0)+上半(1)+下半(2)。回傳 {season_code: 隊數}。

    ⚠️ 兩種失敗刻意不同命：
    - **抓取／解析失敗**（token、428、逾時）＝什麼都沒拿到，不會產生錯資料 →
      維持既有行為，記 warning 並略過該 SeasonCode。
    - **對帳失敗** :class:`StandingsYearMismatch` ＝拿到的是別的球季 → **外拋**。
      這是資料正確性違規，吞掉它就等於把硬失敗降級成沒人讀的 warning。
    """
    out = {}
    for sc in (0, 1, 2):
        # ⚠️ try 只包 fetch，這是結構性的、不是排版：對帳與寫入刻意留在 try 之外，
        # StandingsYearMismatch 才不可能被這個 except 降級成 warning。
        try:
            records = fetch_standings(year, sc, kind_code)
        except Exception as e:  # noqa: BLE001
            log.warning("SeasonCode=%s 略過：%s", sc, e)
            continue
        if not records:
            verify_year(year, sc, kind_code, {})  # 空回應也要驗：本地有完成場就是異常
            out[sc] = 0
            log.info("standings %s SeasonCode=%s: 官網無資料（本地該半季亦無完成場）", year, sc)
            continue
        n = upsert_standings(records)
        out[sc] = n
        log.info("standings %s SeasonCode=%s: %d 隊", year, sc, n)
    return out
