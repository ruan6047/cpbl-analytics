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
            'observed_at':'2026-10-08','members':[{'player_id':'0000000001','role':'pitching','name':'測試投手'}]}
    assert adapt([record],2026,'E','ACN011')['complete']
    assert not adapt([record],2026,'C','ACN011')['complete']
    unresolved=deepcopy(record);unresolved['members'][0]['player_id']=None
    assert not adapt([unresolved],2026,'E','ACN011')['complete']
    assert adapt([],2026,'E','ACN011')['status']=='unverified'


def test_population_source_version_and_identity_metadata_are_pinned_with_both_reads():
    x=game(1,9)
    source={"source":"official_registration","source_version":"roster-v1",
            "scope":{"year":2026,"kind":"E","team_code":"ACN011"},
            "reference":"https://www.cpbl.com.tw/fixture","published_date":"2026-10-08",
            "published_at":None,"published_precision":"date",
            "observed_at":"2026-10-11T17:33:07.351Z",
            "identity_verified_at":"2026-10-11T18:56:05.097767+00:00"}
    context=bounded_context(x,[x],[schedule(2,10)],population_sources=[source])
    same=bounded_context(x,[x],[schedule(2,10)],population_sources=[deepcopy(source)])
    assert context==same and context["population_sources"]==[source]
    changed=bounded_context(x,[x],[schedule(2,10)],population_sources=[{**source,"source_version":"roster-v2"}])
    with pytest.raises(ContextChanged):
        validate_target(changed,"E",2,context["context_hash"])
    assert validate_target(same,"E",2,context["context_hash"])["game_sno"]==2



def test_selected_announcement_material_changes_context_without_read_time_or_late_result():
    x=game(1,9)
    material=[{"game_key":"2026/E/2","lineup":{"status":"unverified","source_version":"v1"}}]
    initial=bounded_context(x,[x],[schedule(2,10)],announcement_materials=material)
    changed=bounded_context(x,[x],[schedule(2,10)],announcement_materials=[{"game_key":"2026/E/2","lineup":{"status":"unverified","source_version":"v2"}}])
    assert initial["context_hash"]!=changed["context_hash"]
    with pytest.raises(ContextChanged):
        validate_target(changed,"E",2,initial["context_hash"])
    assert bounded_context(x,[x],[schedule(2,10)],announcement_materials=[])==bounded_context(x,[x],[schedule(2,10)])


def test_future_published_identity_can_be_compared_without_faking_starter_announcement():
    # 官方future正常schedule revision，沒有IsPlayBall=N仍有真C身分；不是C1完賽。
    x=game(4,12)
    published={**schedule(1,17,flag=None,fetched=13),"kind_code":"C","raw_present_status":0,
               "raw_payload":{"VisitingTeamCode":"ACN011","HomeTeamCode":"AAA011","FieldAbbe":"大巨蛋"}}
    ctx=bounded_context(x,[x],[published])
    y=validate_target(ctx,"C",1,ctx["context_hash"])
    assert y["away_team_code"]=="ACN011" and y["home_team_code"]=="AAA011"
    assert y["completed"] is False
    assert ctx["sources"][0]["cutoff_basis"]=="published_identity_before_started"
    from cpbl.api.between_games import pregame_schedule
    assert pregame_schedule([published],date(2026,10,17))["away_starter"]["status"]=="unverified"
    only_started={**published,"is_play_ball":"Y","fetched_at":datetime(2026,10,17,tzinfo=UTC)}
    assert bounded_context(x,[x],[only_started])["rows"]==[]
