"""永久季表原語：純測試，不接 DB／來源。"""
from contextlib import contextmanager

import pytest

from cpbl.ingest import cpbl_season_backfill as bf


def source(headers, values, pid="0000000001"):
    return '<table><tr><th>球員</th>' + ''.join(f'<th>{h}</th>' for h in headers) + '</tr><tr><td><a href="/team/person?acnt=' + pid + '">甲</a></td>' + ''.join(f'<td class="num">{v}</td>' for v in values) + '</tr></table>'


def test_existing_backfill_uses_current_browser_signature(monkeypatch):
    monkeypatch.setattr(bf, '_teamscore_token', lambda: 'token')
    monkeypatch.setattr(bf, '_teamscore_post', lambda token, club, position, year, kind: source(['出賽數', '打席'], [1, 2]))
    monkeypatch.setattr(bf, 'conn', lambda: pytest.fail('fetch must complete before persistence'))
    # 先直接驗 fetch，既有實作尚無此原語。
    rows = bf.fetch_batting_season(2026)
    assert len(rows) == 6
    assert {r[2] for r in rows} == {c + '011' for c in bf.CLUB_NOS}


def test_headers_missing_values_and_multiteam():
    html = source(['打席', '打數', '（故四）', '安打'], ['10', '8', '（0）', '-'])
    a = bf.parse_batting_season(html, 2026, 'AAA')[0]
    b = bf.parse_batting_season(html, 2026, 'ACN')[0]
    assert a[:3] == ('0000000001', 2026, 'AAA011')
    assert a[bf.BATTING_COLUMNS.index('pa')] == 10
    assert a[bf.BATTING_COLUMNS.index('g')] is None
    assert a[bf.BATTING_COLUMNS.index('h')] is None
    assert a[bf.BATTING_COLUMNS.index('ibb')] == 0
    assert a[0] == b[0] and a[2] != b[2]


def test_pitching_ip_keeps_baseball_notation():
    r = bf.parse_pitching_season(source(['投球局數', '先發'], ['12.2', '1']), 2026, 'AAA')[0]
    assert str(r[bf.PITCHING_COLUMNS.index('ip')]) == '12.2'
    with pytest.raises(ValueError, match='ip'):
        bf.parse_pitching_season(source(['投球局數'], ['12.3']), 2026, 'AAA')


@pytest.mark.parametrize('html', ['<table></table>', source(['打席'], ['1', '2']), source(['打席'], ['invalid']), source(['打席'], ['1']) + source(['打席'], ['1'])])
def test_incomplete_or_conflicting_source_rejected(html):
    with pytest.raises(ValueError):
        bf.parse_batting_season(html, 2026, 'AAA')


def test_fetch_failure_never_writes(monkeypatch):
    monkeypatch.setattr(bf, '_teamscore_token', lambda: 'token')
    def post(token, club, position, year, kind):
        if club == 'AKP':
            raise RuntimeError('source failure')
        return source(['打席'], ['1'])
    monkeypatch.setattr(bf, '_teamscore_post', post)
    monkeypatch.setattr(bf, 'conn', lambda: pytest.fail('source failure must be zero writes'))
    with pytest.raises(RuntimeError, match='source failure'):
        bf.backfill_batting_season(2026)


def test_bundle_one_transaction_rollback_and_idempotence(monkeypatch):
    committed = {}
    pending = {}
    fail = [True]
    class Cursor:
        def executemany(self, sql, rows):
            if 'pitching_seasons' in str(sql) and fail[0]:
                raise RuntimeError('second role fails')
            for row in rows:
                pending[(str(sql), row[:3])] = row
    class Connection:
        def cursor(self):
            return Cursor()
    @contextmanager
    def connection():
        try:
            yield Connection()
        except Exception:
            pending.clear()
            raise
        else:
            committed.update(pending)
            pending.clear()
    monkeypatch.setattr(bf, 'conn', connection)
    bat = bf.parse_batting_season(source(['打席'], ['1']), 2026, 'AAA')
    pit = bf.parse_pitching_season(source(['先發'], ['1']), 2026, 'AAA')
    with pytest.raises(RuntimeError, match='second role fails'):
        with bf.conn() as c:
            bf.persist_season_records(c.cursor(), bat, pit)
    assert committed == {}
    fail[0] = False
    for _ in range(2):
        with bf.conn() as c:
            assert bf.persist_season_records(c.cursor(), bat, pit) == {'batting': 1, 'pitching': 1, 'fielding': 0}
    assert len(committed) == 2


def test_season_aggregation_and_target_year_boundary(monkeypatch):
    from cpbl.features import batting
    class Cursor:
        def execute(self, sql):
            self.sql = sql
            if 'batting_seasons' in sql:
                assert 'GROUP BY player_id, year' in sql
        def fetchall(self):
            if 'batting_seasons' not in self.sql:
                return []
            # 同年多隊讀取由SQL合併，未來/目標年高數值不能洩漏至lag。
            return [('p', 2025, 120, 100, 20, 1, 0, 0, 21, 10, 1, 1, 2),
                    ('p', 2026, 240, 200, 80, 2, 0, 0, 82, 20, 2, 2, 4),
                    ('p', 2027, 360, 300, 180, 3, 0, 0, 183, 30, 3, 3, 6)]
    class Connection:
        def cursor(self):
            return Cursor()
    @contextmanager
    def connection():
        yield Connection()
    monkeypatch.setattr(batting, 'conn', connection)
    rows = {r['target_year']: r for r in batting.build_batting_dataset()}
    assert rows[2026]['pa_lag1'] == 120
    assert rows[2026]['avg_lag1'] == .2
    assert rows[2027]['pa_lag1'] == 240
    assert rows[2027]['avg_lag1'] == .4


def test_fielding_keeps_team_position_and_unverified_cs_sb_null():
    html = source(['守備位置', '出賽數', '刺殺', '盜壘阻殺', '被盜成功'], ['游擊手', '3', '2', '9', '8'])
    a = bf.parse_fielding_season(html, 2026, 'AAA')[0]
    b = bf.parse_fielding_season(html, 2026, 'ACN')[0]
    assert a[:5] == ('0000000001', 2026, 'AAA011', '味全龍', '游擊手')
    assert a[-2:] == (None, None)
    assert a[0] == b[0] and a[2] != b[2]


def test_whole_innings_matches_numeric_database_scale():
    row = bf.parse_pitching_season(source(['投球局數'], ['12']), 2026, 'AAA')[0]
    assert str(row[bf.PITCHING_COLUMNS.index('ip')]) == '12.0'
