from types import SimpleNamespace

import pytest

from cpbl.api.routers.ability import _ability_card, ability_cards
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
