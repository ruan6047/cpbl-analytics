from copy import deepcopy
from datetime import UTC, date, datetime

import pytest

from cpbl.reports.context import ContextChanged, bounded_context, validate_target
from cpbl.reports.population import adapt


def game(sno, day, *, kind='E', complete=True, home=1, away=3):
    return {'year': 2026, 'kind_code': kind, 'game_sno': sno, 'game_date': date(2026,10,day),
            'home_team_code':'ACN011','away_team_code':'ADD011','home_score':home,'away_score':away,
            'completed':complete}


def schedule(sno, day, *, flag='N', fetched=8, payload='v1'):
    return {'year':2026,'kind_code':'E','game_sno':sno,'raw_present_status':1,'raw_game_result':None,
            'is_play_ball':flag,'raw_game_date':date(2026,10,day),'payload_hash':payload,
            'fetched_at':datetime(2026,10,fetched,tzinfo=UTC),
            'raw_payload':{'VisitingTeamCode':'ADD011','HomeTeamCode':'ACN011','FieldAbbe':'洲際'}}


def test_later_result_does_not_change_fixed_x_context():
    x,y = game(1,9), game(2,10,complete=False,away=0,home=0)
    before=bounded_context(x,[x,y],[schedule(2,10)])
    after=bounded_context(x,[x,{**y,'completed':True,'home_score':10,'away_score':0}],[schedule(2,10)])
    assert before == after
    assert before['through_game_keys'] == ['2026/E/1']
    assert before['rows'][0]['home_score'] == 0
    assert validate_target(before,'E',2,before['context_hash'])['game_date']=='2026-10-10'


def test_last_seen_is_not_semantic_and_first_started_blocks_late_version():
    x=game(1,9)
    old=schedule(2,10)
    before=bounded_context(x,[x],[old])
    assert bounded_context(x,[x],[{**old,'last_seen_at':datetime(2026,10,12,tzinfo=UTC)}]) == before
    started=schedule(2,10,flag='Y',fetched=10,payload='started')
    late=schedule(2,11,fetched=11,payload='late')
    assert bounded_context(x,[x],[old,started,late]) == before


def test_context_rejects_changed_inputs_and_arbitrary_candidate():
    x=game(1,9); context=bounded_context(x,[x],[schedule(2,10)])
    changed=bounded_context({**x,'home_score':5},[{**x,'home_score':5}],[schedule(2,10)])
    with pytest.raises(ContextChanged):
        validate_target(changed,'E',2,context['context_hash'])
    with pytest.raises(ValueError):
        validate_target(context,'C',99,context['context_hash'])
    with pytest.raises(ValueError):
        validate_target(context,'E',1,context['context_hash'])


def test_c_context_only_has_previous_e_and_c_through_x():
    x=game(2,18,kind='C')
    ctx=bounded_context(x,[game(1,9),game(1,17,kind='C'),x,game(3,20,kind='C')],[])
    assert ctx['through_game_keys']==['2026/C/1','2026/C/2']
    assert {s['kind_code']:len(s['games']) for s in ctx['summary']}=={'E':1,'C':2}


def test_official_full_mother_requires_ids_roles_and_round():
    record={'year':2026,'round':'E','team_code':'ACN011','official':True,'complete':True,
            'source_url':'https://www.cpbl.com.tw/official-fixture','roster_version':'fixture-v1',
            'observed_at':'2026-10-08','members':[{'player_id':'p','role':'pitching'}]}
    assert adapt([record],2026,'E','ACN011')['complete']
    assert not adapt([record],2026,'C','ACN011')['complete']
    unresolved=deepcopy(record);unresolved['members'][0]['player_id']=None
    assert not adapt([unresolved],2026,'E','ACN011')['complete']
    assert adapt([],2026,'E','ACN011')['status']=='unverified'
