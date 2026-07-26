"""官網 ``/stats/hr`` 逐轟里程碑低頻 audit ingest。

此資料不是每日 refresh 的一部分。官網只在以 ``HomeRunType``、``Citizenship``
篩選時揭露該維度，故每個 year/kind 先抓全量基底，再用同一自然鍵回填兩種篩選
維度。所有請求共用一個 Playwright session；請僅於本機、白天及低頻執行。
"""

from __future__ import annotations

import html as html_lib
import logging
import re
from dataclasses import dataclass
from datetime import date

from cpbl.db import conn

log = logging.getLogger("cpbl.home_runs")

PAGE = "/stats/hr"
ACTION = "/stats/hraction"
KIND_CODES = ("A", "B", "C", "D", "D9", "E", "F", "G", "H", "X")
HOME_RUN_TYPES = (1, 2, 3, 4, 5)
CITIZENSHIPS = (0, 1)
_TOKEN_RE = re.compile(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"')
_PLAYER_RE = re.compile(r"/team/person\?acnt=(\d+)")


@dataclass
class HomeRunRecord:
    year: int
    kind_code: str
    game_sno: int
    inning: int
    hitter_acnt: str
    pitcher_acnt: str
    game_date: date | None
    venue: str | None
    hitter_name: str | None
    hitter_team_name: str | None
    pitcher_name: str | None
    pitcher_team_name: str | None
    rbi: int | None
    note: str | None
    home_run_type: int | None = None
    citizenship: int | None = None

    @property
    def key(self) -> tuple[int, str, int, int, str, str]:
        return (self.year, self.kind_code, self.game_sno, self.inning, self.hitter_acnt, self.pitcher_acnt)

    def values(self) -> tuple:
        return (
            self.year, self.kind_code, self.game_sno, self.inning, self.hitter_acnt, self.pitcher_acnt,
            self.game_date, self.venue, self.hitter_name, self.hitter_team_name,
            self.pitcher_name, self.pitcher_team_name, self.rbi, self.note,
            self.home_run_type, self.citizenship,
        )


def _text(cell: str | None) -> str | None:
    if cell is None:
        return None
    value = html_lib.unescape(re.sub(r"<[^>]+>", "", cell)).replace("\xa0", " ").strip()
    return value or None


def _to_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value.replace(",", "").strip())
    except ValueError:
        return None


def _to_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace(",", "").strip())
    except ValueError:
        return None


def _to_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.replace("/", "-"))
    except ValueError:
        return None


def _cells(row: str) -> list[str]:
    return re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)


def _player(cell: str | None) -> tuple[str | None, str | None]:
    if cell is None:
        return None, None
    match = _PLAYER_RE.search(cell)
    return (match.group(1) if match else None), _text(cell)


def parse_home_runs(fragment: str, kind_code: str) -> list[HomeRunRecord]:
    """解析 hraction HTML，缺少非 identity 欄位一律存 NULL。

    欄位以官網標題定位而非硬編 cell index；identity 缺失時不寫入，因 PostgreSQL
    primary key 不能表示「不確定的事件」。
    """
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", fragment, re.S | re.I)
    if not rows:
        return []
    headers = {_text(cell): i for i, cell in enumerate(_cells(rows[0])) if _text(cell)}

    def cell(cells: list[str], name: str) -> str | None:
        idx = headers.get(name)
        return cells[idx] if idx is not None and idx < len(cells) else None

    parsed: list[HomeRunRecord] = []
    for raw in rows[1:]:
        cells = _cells(raw)
        if not cells:
            continue
        year = _to_int(_text(cell(cells, "年度")))
        game_sno = _to_int(_text(cell(cells, "場次")))
        inning = _to_int(_text(cell(cells, "局數")))
        hitter_acnt, hitter_name = _player(cell(cells, "打者"))
        pitcher_acnt, pitcher_name = _player(cell(cells, "投手"))
        if None in (year, game_sno, inning, hitter_acnt, pitcher_acnt):
            log.warning("略過缺 identity 的 /stats/hr 列：year=%s game=%s inning=%s", year, game_sno, inning)
            continue
        parsed.append(HomeRunRecord(
            year=year, kind_code=kind_code, game_sno=game_sno, inning=inning,
            hitter_acnt=hitter_acnt, pitcher_acnt=pitcher_acnt,
            game_date=_to_date(_text(cell(cells, "日期"))), venue=_text(cell(cells, "場地")),
            hitter_name=hitter_name, hitter_team_name=_text(cell(cells, "打者所屬球隊")),
            pitcher_name=pitcher_name, pitcher_team_name=_text(cell(cells, "投手所屬球隊")),
            rbi=_to_int(_text(cell(cells, "打點"))), note=_text(cell(cells, "備註")),
        ))
    return parsed


def _post(token: str, year: int, kind_code: str, **filters: int) -> str:
    from cpbl.ingest._browser import session

    form = {
        "__RequestVerificationToken": token,
        "Year": str(year), "KindCode": kind_code,
        "FieldNo": "", "HitterTeamNo": "", "PitcherTeamNo": "",
        "HomeRunType": "", "Citizenship": "", "ExecAction": "Q", "IndexOfPages": "0",
    }
    form.update({key: str(value) for key, value in filters.items()})
    status, response = session().post(PAGE, ACTION, form)
    if status != 200:
        raise RuntimeError(f"hraction HTTP {status}（反爬挑戰未過或官網改版）")
    return response


def apply_dimension(
    base: list[HomeRunRecord], candidates: list[HomeRunRecord], field: str, value: int
) -> None:
    """僅以已驗證 natural key 對齊官網篩選子集，未知列不可憑名稱猜測。"""
    by_key = {row.key: row for row in base}
    unmatched = 0
    for candidate in candidates:
        target = by_key.get(candidate.key)
        if target is None:
            unmatched += 1
            continue
        setattr(target, field, value)
    if unmatched:
        log.warning("/stats/hr %s=%s 有 %d 筆未對到全量基底，未寫入", field, value, unmatched)


def fetch_home_runs(year: int, kind_code: str) -> list[HomeRunRecord]:
    """抓一個 year/kind 的全量列並以官方篩選結果回填新維度。"""
    from cpbl.ingest._browser import session

    page = session().page_html(PAGE, require=_TOKEN_RE)
    token_match = _TOKEN_RE.search(page)
    if not token_match:
        raise RuntimeError("找不到 hr __RequestVerificationToken（官網可能改版）")
    token = token_match.group(1)
    records = parse_home_runs(_post(token, year, kind_code), kind_code)
    for value in HOME_RUN_TYPES:
        apply_dimension(records, parse_home_runs(
            _post(token, year, kind_code, HomeRunType=value), kind_code), "home_run_type", value)
    for value in CITIZENSHIPS:
        apply_dimension(records, parse_home_runs(
            _post(token, year, kind_code, Citizenship=value), kind_code), "citizenship", value)
    return records


def upsert_home_runs(records: list[HomeRunRecord]) -> int:
    if not records:
        return 0
    with conn() as connection:
        connection.cursor().executemany(
            """
            INSERT INTO cpbl.home_run_log (
                year, kind_code, game_sno, inning, hitter_acnt, pitcher_acnt,
                game_date, venue, hitter_name, hitter_team_name, pitcher_name, pitcher_team_name,
                rbi, source_note, home_run_type, citizenship
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (year, kind_code, game_sno, inning, hitter_acnt, pitcher_acnt) DO UPDATE SET
                game_date=EXCLUDED.game_date, venue=EXCLUDED.venue,
                hitter_name=EXCLUDED.hitter_name, hitter_team_name=EXCLUDED.hitter_team_name,
                pitcher_name=EXCLUDED.pitcher_name, pitcher_team_name=EXCLUDED.pitcher_team_name,
                rbi=EXCLUDED.rbi, source_note=EXCLUDED.source_note,
                home_run_type=EXCLUDED.home_run_type, citizenship=EXCLUDED.citizenship,
                fetched_at=now()
            """,
            [record.values() for record in records],
        )
    return len(records)


def scrape_home_runs(start_year: int, end_year: int, kind_codes: tuple[str, ...]) -> dict[tuple[int, str], int]:
    totals: dict[tuple[int, str], int] = {}
    for year in range(start_year, end_year + 1):
        for kind_code in kind_codes:
            count = upsert_home_runs(fetch_home_runs(year, kind_code))
            totals[(year, kind_code)] = count
            log.info("home runs %s %s: %d rows", year, kind_code, count)
    return totals
