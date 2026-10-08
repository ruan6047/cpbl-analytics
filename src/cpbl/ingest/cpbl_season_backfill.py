"""官方逐隊 teamscore 的永久季彙總；fetch 無 DB，persist 可共用交易。

舊 CLI 仍各角色呼叫且會 migrate，不提供成組安全入口；季末成組操作應先
收齊並驗證全部來源，再以同一 cpbl.db.conn 的 cursor 呼叫 persist_season_records。
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from html import unescape

from psycopg import sql

from cpbl.db import conn
from cpbl.ingest.cpbl_stats import CLUB_NOS, _teamscore_post, _teamscore_token

CLUB_NAME = {"AAA": "味全龍", "ACN": "中信兄弟", "ADD": "統一7-ELEVEn獅",
             "AEO": "富邦悍將", "AJL": "樂天桃猿", "AKP": "台鋼雄鷹"}
BATTING_COLUMNS = (
    'player_id', 'year', 'team_id', 'team_name', 'g', 'pa', 'ab', 'rbi', 'r', 'h',
    'b1', 'b2', 'b3', 'hr', 'tb', 'so', 'sb', 'gidp', 'sh', 'sf', 'bb', 'ibb',
    'hbp', 'cs', 'go', 'fo',
)
PITCHING_COLUMNS = (
    'player_id', 'year', 'team_id', 'team_name', 'g', 'gs', 'gr', 'cg', 'sho',
    'nbb', 'w', 'l', 'sv', 'hld', 'ip', 'bf', 'np', 'h', 'hr', 'bb', 'ibb',
    'hbp', 'so', 'wp', 'bk', 'r', 'er', 'go', 'fo',
)
FIELDING_COLUMNS = (
    'player_id', 'year', 'team_id', 'team_name', 'pos', 'g', 'tc', 'po', 'a',
    'e', 'dp', 'tp', 'pb', 'cs', 'sb',
)
_BATTING_HEADERS = dict(zip(BATTING_COLUMNS[4:], (
    '出賽數', '打席', '打數', '打點', '得分', '安打', '一安', '二安', '三安',
    '全壘打', '壘打數', '被三振', '盜壘', '雙殺打', '犧短', '犧飛', '四壞球',
    '（故四）', '死球', '盜壘刺', '滾地出局', '高飛出局',
), strict=True))
_PITCHING_HEADERS = dict(zip(PITCHING_COLUMNS[4:], (
    '出賽數', '先發', '救援', '完投', '完封', '無四死球', '勝場', '敗場',
    '救援成功', '中繼成功', '投球局數', '打席', '投球數', '被安打', '被全壘打',
    '四壞', '（故四）', '死球', '奪三振', '暴投', '投手犯規', '失分', '自責分',
    '滾地出局', '高飛出局',
), strict=True))
# 官方守備 CS/SB 與永久欄位契約尚未核定；不得按名字猜，固定留 NULL。
_FIELDING_HEADERS = dict(zip(FIELDING_COLUMNS[5:13], (
    '出賽數', '守備機會', '刺殺', '助殺', '失誤', '雙殺', '三殺', '捕逸',
), strict=True))


def _text(value: str) -> str:
    return re.sub(r'\s+', '', unescape(re.sub(r'<[^>]*>', '', value)))


def _value(cell: str | None, column: str):
    if cell is None or cell in ('', '-', '--', '—'):
        return None
    value = cell.replace(',', '')
    if column == 'ibb':
        value = value.strip('()（）')
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f'invalid {column}: {cell!r}') from exc
    if not number.is_finite() or number < 0:
        raise ValueError(f'invalid {column}: {cell!r}')
    if column == 'ip':
        if number * 10 != (number * 10).to_integral_value() or number % 1 not in (
            Decimal('0'), Decimal('.1'), Decimal('.2'),
        ):
            raise ValueError(f'invalid ip: {cell!r}')
        return number.quantize(Decimal('.1'))
    if number != number.to_integral_value():
        raise ValueError(f'invalid integer {column}: {cell!r}')
    return int(number)


def _parse(html: str, year: int, club: str, headers: dict, *, fielding=False) -> list[tuple]:
    if club not in CLUB_NOS:
        raise ValueError('unknown club')
    labels = [_text(h) for h in re.findall(r'<th\b[^>]*>(.*?)</th>', html, re.S)]
    if not labels or labels[0] != '球員' or len(set(labels)) != len(labels):
        raise ValueError('missing or conflicting headers')
    indices = {label: i for i, label in enumerate(labels[1:])}
    if not set(headers.values()) & indices.keys():
        raise ValueError('no supported statistics headers')
    if fielding and '守備位置' not in indices:
        raise ValueError('missing position header')
    records = []
    seen = set()
    for tr in re.findall(r'<tr\b[^>]*>(.*?)</tr>', html, re.S):
        mid = re.search(r'/team/person\?acnt=(\d+)', tr)
        if not mid:
            continue
        pid = mid.group(1)
        cells = [_text(n) for n in re.findall(r'<td\b[^>]*class="num"[^>]*>(.*?)</td>', tr, re.S)]
        if len(pid) != 10 or len(cells) != len(indices):
            raise ValueError('incomplete player row')
        base = (pid, year, club + '011', CLUB_NAME[club])
        if fielding:
            pos = cells[indices['守備位置']]
            if not pos:
                raise ValueError('missing position')
            base += (pos,)
        key = base[:3] + ((base[4],) if fielding else ())
        if key in seen:
            raise ValueError('duplicate natural key')
        seen.add(key)
        values = tuple(_value(cells[indices[label]] if label in indices else None, col)
                       for col, label in headers.items())
        records.append(base + values + ((None, None) if fielding else ()))
    if not records:
        raise ValueError('empty player source')
    return records


def parse_batting_season(html: str, year: int, club: str) -> list[tuple]:
    return _parse(html, year, club, _BATTING_HEADERS)


def parse_pitching_season(html: str, year: int, club: str) -> list[tuple]:
    return _parse(html, year, club, _PITCHING_HEADERS)


def parse_fielding_season(html: str, year: int, club: str) -> list[tuple]:
    """僅供完整可信逐隊守備源；CS/SB NULL，保留 team+pos。"""
    return _parse(html, year, club, _FIELDING_HEADERS, fielding=True)


def _fetch(year: int, position: str, parser) -> list[tuple]:
    token = _teamscore_token()
    records = []
    for club in CLUB_NOS:
        records.extend(parser(_teamscore_post(token, club, position, year, 'A'), year, club))
    return records


def fetch_batting_season(year: int) -> list[tuple]:
    return _fetch(year, '01', parse_batting_season)


def fetch_pitching_season(year: int) -> list[tuple]:
    return _fetch(year, '02', parse_pitching_season)


def _statement(table, columns, keys):
    return sql.SQL('INSERT INTO cpbl.{} ({}) VALUES ({}) ON CONFLICT ({}) DO UPDATE SET {}').format(
        sql.Identifier(table), sql.SQL(',').join(map(sql.Identifier, columns)),
        sql.SQL(',').join(sql.Placeholder() for _ in columns),
        sql.SQL(',').join(map(sql.Identifier, keys)),
        sql.SQL(',').join(sql.SQL('{}=EXCLUDED.{}').format(sql.Identifier(c), sql.Identifier(c))
                          for c in columns if c not in keys),
    )


_STATEMENTS = {
    'batting': _statement('batting_seasons', BATTING_COLUMNS, BATTING_COLUMNS[:3]),
    'pitching': _statement('pitching_seasons', PITCHING_COLUMNS, PITCHING_COLUMNS[:3]),
    'fielding': _statement('fielding_seasons', FIELDING_COLUMNS, (*FIELDING_COLUMNS[:3], 'pos')),
}


def persist_season_records(cur, batting: list[tuple], pitching: list[tuple],
                           fielding: list[tuple] = ()) -> dict[str, int]:
    """只用呼叫者 cursor，不建立／提交交易。呼叫前須驗完整來源與前值。"""
    counts = {}
    for role, records in (('batting', batting), ('pitching', pitching), ('fielding', fielding)):
        if records:
            cur.executemany(_STATEMENTS[role], records)
        counts[role] = len(records)
    return counts


def backfill_batting_season(year: int) -> int:
    records = fetch_batting_season(year)
    with conn() as c:
        return persist_season_records(c.cursor(), records, [])['batting']


def backfill_pitching_season(year: int) -> int:
    records = fetch_pitching_season(year)
    with conn() as c:
        return persist_season_records(c.cursor(), [], records)['pitching']
