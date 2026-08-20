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

# 一次執行一份帳：本次 scrape 的失敗清單，呼叫端用 :func:`standings_failures` 讀。
# ⚠️ 為什麼是模組級累積器而不是回傳值：`scrape_standings` 的回傳型別
# `{season_code: 隊數}` 已被既有呼叫端與其測試替身依賴（`tests/test_gamelog_reconcile.py`
# 以 `lambda *a, **k: 0` 替身），改型別會在本卡宣告外的檔案造成連鎖改動。
# 與 `run_refresh_recent._GAMELOG_GAPS` 同一模式：失敗要進帳、要被退出碼與
# `refresh_log` 看見，但不得靠改變回傳型別去達成。
_FAILURES: list[dict] = []


def reset_standings_failures() -> None:
    """清帳。⚠️ 呼叫端在一次執行的開頭要先清一次——`scrape_standings` 自己也會清，
    但那在它被測試替身取代時不會發生，於是上一次的失敗會被讀成這一次的
    （與 `run_refresh_recent._GAMELOG_GAPS.clear()` 同一理由與同一位置）。
    """
    _FAILURES.clear()


def standings_failures() -> list[dict]:
    """最近一次 scrape 的失敗清單；每筆 `{season_code, kind, error}`。

    `kind` 值域：`fetch`＝抓取／解析失敗（什麼都沒拿到，不會寫錯資料）；
    `year_mismatch`＝對帳失敗（拿到別的球季或空表，**已拒寫**）。
    """
    return list(_FAILURES)

BASE = "https://www.cpbl.com.tw"
PAGE = f"{BASE}/standings/season"
ACTION = f"{BASE}/standings/seasonaction"
HISTORY_PAGE = "/standings/history"
HISTORY_ACTION = "/standings/historyaction"
# history 頁一次給三張表，各自由前置的 HTML 註解標示。⚠️ 用註解錨定而不是用出現順序：
# 順序是官網排版，改版就會錯位且不會報錯；註解是語意標記，改掉會直接找不到 → fail closed。
HISTORY_SECTIONS = (("<!--上半季戰績-->", 1), ("<!--下半季戰績-->", 2), ("<!--全年戰績-->", 0))
_TEAMNO_RE = re.compile(r"TeamNo=([A-Z0-9]+)")
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


def _history_table(html: str, tag: str) -> str | None:
    """取出 `tag` 註解之後的第一張表；找不到回 None（由呼叫端 fail closed）。"""
    at = html.find(tag)
    if at < 0:
        return None
    m = re.search(r"<table.*?</table>", html[at:], re.S)
    return m.group(0) if m else None


def _parse_history_table(table: str, year: int, kind_code: str, season_code: int) -> list[tuple]:
    """解析 history 頁單張戰績表 → records（欄位順序同 `_COLS`）。

    ⚠️ 本頁**沒有** `elim`／`streak`／`last10` 三欄，一律填 None。需求方 2026-08-20 裁定
    「缺欄寫 NULL、不保留現值」——那三欄現存的是別的球季的值，**錯值比缺值危險**
    （已知受害者：`data_rules_audit1` 拿 `streak` 當和局斷連的 ground truth）。
    ⚠️ 這裡刻意不寫該檔的完整路徑：`scripts/README.md` 是由 `script_inventory` 掃描
    `scripts/<name>.<ext>` 字面路徑產生的清冊，多一處字面就得重新產生那份清冊，
    而它不在本卡的資源宣告內。名字足以定位，路徑留給後續卡一併補。

    H2H 的欄位順序**由表頭實抽**，不用固定常數：球隊數逐年不同（2022 只有 5 隊），
    寫死順序在歷史年份會整排錯位。
    """
    rows = re.findall(r"<tr>(.*?)</tr>", table, re.S)
    if not rows:
        return []
    ths = [_clean(x) for x in re.findall(r"<th[^>]*>(.*?)</th>", rows[0], re.S)]
    h2h_names = ths[5:-2]  # 排名球隊/出賽數/勝-和-敗/勝率/勝差 … 主場戰績/客場戰績
    h2h_codes = [NAME_CODE.get(n) for n in h2h_names]
    out: list[tuple] = []
    for tr in rows[1:]:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(tds) != 5 + len(h2h_codes) + 2:
            continue
        code_m = _TEAMNO_RE.search(tds[0])
        if not code_m:
            continue
        code = code_m.group(1)
        rank_m = re.search(r'rank">(\d+)', tds[0])
        g = _clean(tds[1])
        w, t, l = _wtl(_clean(tds[2]))
        wp = _clean(tds[3])
        gb_raw = _clean(tds[4])
        h2h = {c: _clean(tds[5 + i]) for i, c in enumerate(h2h_codes)
               if c and c != code and re.match(r"\d+-\d+-\d+", _clean(tds[5 + i]))}
        # 退路的隊名要去掉開頭的名次數字（第一格是「排名＋隊名」兩個 div）。
        # ⚠️ NAME_CODE 只有現役六隊，歷史年份（兄弟象、LamiGo…）走的就是這條退路。
        name = next((n for n, c in NAME_CODE.items() if c == code),
                    re.sub(r"^\d+", "", _clean(tds[0])) or None)
        out.append((
            year, kind_code, season_code, code, name,
            int(rank_m.group(1)) if rank_m else None, int(g) if g.isdigit() else None,
            w, t, l, float(wp) if re.match(r"[0-9.]+$", wp) else None,
            0.0 if gb_raw in ("-", "") else (float(gb_raw) if re.match(r"[0-9.]+$", gb_raw) else None),
            None, _clean(tds[-2]) or None, _clean(tds[-1]) or None, None, None,
            json.dumps(h2h, ensure_ascii=False),
        ))
    return out


def split_history_sections(html: str, year: int,
                           kind_code: str = "A") -> dict[int, list[tuple]]:
    """把 history 頁的三個區塊各自解析成 records，key＝`season_code`。

    ⚠️ 區塊與 `season_code` 的對應**由 HTML 註解決定，不由出現順序決定**。抽成獨立純
    函式的理由是可測性：走網路的 `fetch_history_standings` 沒辦法用測試釘住「換成
    看順序也會過」這種退化。
    """
    out: dict[int, list[tuple]] = {}
    for tag, sc in HISTORY_SECTIONS:
        table = _history_table(html, tag)
        if table is None:
            raise RuntimeError(f"standings/history 找不到區塊 {tag}（官網可能改版）")
        out[sc] = _parse_history_table(table, year, kind_code, sc)
    return out


def fetch_history_standings(year: int, kind_code: str = "A") -> dict[int, list[tuple]]:
    """由 `/standings/history` 抓**已完賽球季**的官方戰績，一次拿到三個 season_code。

    ⭐ 與 `seasonaction` 的關鍵差別：**本頁遵守 `Year`**（2026-08-20 實測 `Year=2024`／
    `Year=2022` 各自回正確年份，且與 opendata `cpbl.standings` 逐隊吻合）。但這**不構成
    豁免**——寫入仍走 `upsert_standings` 的同一道對帳，官網哪天改壞了照樣拒寫。

    ⚠️ token 走 **form body**（hidden input），不是 header：本頁的 AJAX 是
    `form.serialize()`，與 `seasonaction` 用 header 的型態不同（誤用型態的症狀見
    `docs/CPBL_SITE_MAP.md` §5「用錯 token 型態」）。此處兩種都帶，以實測可行為準。
    """
    from cpbl.ingest._browser import session
    s = session()
    page = s.page_html(HISTORY_PAGE)
    hidden = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', page)
    inline = _TOKEN_RE.search(page)
    if not hidden and not inline:
        raise RuntimeError("standings/history 找不到 RequestVerificationToken（官網可能改版）")
    form = {"Year": str(year), "Kindcode": kind_code, "IndexOfPages": "1", "ExecAction": ""}
    if hidden:
        form["__RequestVerificationToken"] = hidden.group(1)
    status, html = s.post(
        HISTORY_PAGE, HISTORY_ACTION, form,
        headers={"RequestVerificationToken": inline.group(1)} if inline else {},
    )
    if status != 200:
        raise RuntimeError(f"standings/history HTTP {status}（反爬挑戰未過？）")
    return split_history_sections(html, year, kind_code)



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


def _write_verified(year: int, season_code: int, kind_code: str,
                    records: list[tuple], out: dict, label: str) -> None:
    """對帳→寫入；對帳失敗**拒寫並進帳**，不外拋。

    ⚠️ 不外拋 ≠ 降級成 warning（需求方 2026-08-20 岔路 1 裁定）：外拋會讓
    `run_refresh_recent` 的整段爬取中止，連帶 transactions／championships／PA build／
    splits 重算／改名同步全部不跑——那只是把「靜默失敗」換成「生產靜默落後」，
    兩者一樣沒人在看（與 `DATA-BOX-DEEP-SILENT-FAIL1` #131 的 Q3 同一判準）。
    所以失敗改走 `log.error` ＋ `_FAILURES` 進帳，由退出碼與 `refresh_log` 呈現。
    """
    try:
        if not records:
            verify_year(year, season_code, kind_code, {})  # 空回應也要驗：本地有完成場就是異常
            out[season_code] = 0
            log.info("%s %s SeasonCode=%s: 官網無資料（本地該半季亦無完成場）",
                     label, year, season_code)
            return
        n = upsert_standings(records)
    except StandingsYearMismatch as e:
        log.error("%s %s SeasonCode=%s 對帳失敗，未寫入任何資料：%s", label, year, season_code, e)
        _FAILURES.append({"season_code": season_code, "kind": "year_mismatch", "error": str(e)})
        return
    out[season_code] = n
    log.info("%s %s SeasonCode=%s: %d 隊", label, year, season_code, n)


def scrape_standings(year: int, kind_code: str = "A") -> dict:
    """抓當季全年(0)+上半(1)+下半(2)。回傳 {season_code: 隊數}（失敗的 sc 不在其中）。

    ⚠️ 兩種失敗都不外拋、但都必須看得見——讀 :func:`standings_failures`：
    - **抓取／解析失敗**（token、428、逾時）＝什麼都沒拿到，不會產生錯資料 → `log.warning`。
    - **對帳失敗**＝拿到別的球季或空表 → **拒寫** ＋ `log.error` ＋ 進帳。
    """
    _FAILURES.clear()
    out: dict[int, int] = {}
    for sc in (0, 1, 2):
        try:
            records = fetch_standings(year, sc, kind_code)
        except Exception as e:  # noqa: BLE001
            log.warning("SeasonCode=%s 略過：%s", sc, e)
            _FAILURES.append({"season_code": sc, "kind": "fetch", "error": str(e)})
            continue
        _write_verified(year, sc, kind_code, records, out, label="standings")
    return out


def scrape_history_standings(year: int, kind_code: str = "A") -> dict:
    """已完賽球季的官方戰績 → `team_standings`（三個 season_code 一次寫）。

    ⚠️ 這是 `year=2025` 污染列的補救路徑（需求方 2026-08-20 裁定 UPSERT 覆蓋、不刪除：
    `sync_table()` 是純 UPSERT 無 DELETE，刪本機只會讓生產那批凍結成永遠不更新的假
    資料；UPSERT 則會經現有同步鏈自動修好生產）。對帳與失敗處理與 `scrape_standings`
    同一套——本函式不對任何一列豁免。
    """
    _FAILURES.clear()
    out: dict[int, int] = {}
    try:
        sections = fetch_history_standings(year, kind_code)
    except Exception as e:  # noqa: BLE001
        log.warning("history %s 抓取失敗：%s", year, e)
        _FAILURES.append({"season_code": None, "kind": "fetch", "error": str(e)})
        return out
    for sc, records in sorted(sections.items()):
        _write_verified(year, sc, kind_code, records, out, label="history")
    return out
