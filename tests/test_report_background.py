from types import SimpleNamespace

import pytest

from cpbl.api.routers.ability import _ability_card, ability_cards
from cpbl.api.routers.players import _player_traits
from tests.test_ability_card import _BAT_COLS, _PIT_COLS, _bat_row, _Cur, _pit_row


class BatchCursor:
    def __init__(self, outputs):
        self.outputs=list(outputs)
        self.calls=[]
    def execute(self, sql, params):
        self.calls.append((sql,params));self.cols,self.rows=self.outputs.pop(0)
    @property
    def description(self):
        return [SimpleNamespace(name=n) for n in self.cols]
    def fetchall(self):
        return self.rows


@pytest.mark.parametrize('role,cols,row', [('batting',_BAT_COLS,_bat_row()),('pitching',_PIT_COLS,_pit_row())])
def test_batch_ability_preserves_single_algorithm_and_missing_player(role, cols, row):
    one=_ability_card(_Cur([(cols,row),(['pa'],None)]),'P1',role,'season',2026)
    cur=BatchCursor([(['player_id',*cols],[['P1',*row]]),(['acnt'],[])])
    bulk=ability_cards(cur,['P1','never-appeared'],role,2026)
    assert bulk['P1']==one
    assert not bulk['never-appeared']['available']
    assert len(cur.calls)==2
    assert 'player_id = ANY(%(pids)s)' in cur.calls[0][0]
    assert cur.calls[0][1]['yr']==2026
    assert "kind_code='A'" in cur.calls[1][0]


class TraitsCursor:
    def __init__(self, average=(3, 1, 20)):
        self.calls = []
        self.average = average
        self.description = []
    def execute(self, sql, params):
        self.calls.append((sql, params))
    def fetchall(self):
        return []
    def fetchone(self):
        return self.average


@pytest.mark.parametrize('average', [(3, 1, 20), None])
def test_traits_league_cached_only_within_request_role_and_year(average):
    cached = TraitsCursor(average)
    cache = {}
    cases = [('P1', 2026, 'batting'), ('P2', 2026, 'batting'),
             ('P1', 2027, 'batting'), ('P1', 2026, 'pitching')]
    for pid, year, role in cases:
        plain = TraitsCursor(average)
        assert _player_traits(cached, pid, year, role, league_cache=cache) == _player_traits(plain, pid, year, role)
        assert len(plain.calls) == 2  # 原公開單人 API 行為維持。
    averages = [(sql, params) for sql, params in cached.calls if 'avg(p_pa)' in sql]
    assert len(cached.calls) == 7 and len(averages) == 3
    assert all("kind_code='A'" in sql for sql, _ in averages)
    assert 'pa >= 100' in averages[0][0] and 'bf >= 100' in averages[2][0]
    another = TraitsCursor(average)
    _player_traits(another, 'P3', 2026, 'batting', league_cache={})
    assert len(another.calls) == 2  # 不跨 transaction／request 沿用。
