from contextlib import contextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from cpbl.api.routers import report
from cpbl.reports.context import ContextChanged


def client(monkeypatch, result=None, failure=None):
    calls=[]
    class Connection:
        def execute(self, sql):
            calls.append(sql)
        def cursor(self):
            return object()
    @contextmanager
    def read():
        yield Connection()
    def build(*args, **kwargs):
        calls.append(args)
        calls.append(kwargs)
        if failure:
            raise failure
        return result or {'status':'not_found'}
    monkeypatch.setattr(report,'conn',read)
    monkeypatch.setattr(report,'build_report',build)
    app=FastAPI();app.include_router(report.router)
    return TestClient(app), calls


def test_get_only_sets_repeatable_read_read_only(monkeypatch):
    c,calls=client(monkeypatch)
    assert c.get('/api/v1/games/1/report?season=2026&kind_code=E').status_code==200
    assert calls[0]=='SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'
    assert calls[1][1:4]==(2026,'E',1)
    assert c.post('/api/v1/games/1/report?season=2026&kind_code=E').status_code==405


def test_pair_and_hash_required_before_connection(monkeypatch):
    c,calls=client(monkeypatch)
    for query in ('next_kind=E','next_sno=2','next_kind=E&next_sno=2'):
        assert c.get(f'/api/v1/games/1/report?season=2026&kind_code=E&{query}').status_code==422
    assert not calls


def test_context_change_409_vs_invalid_candidate_422(monkeypatch):
    for error,status in ((ContextChanged('更新中'),409),(ValueError('不符候選'),422)):
        c,_=client(monkeypatch,failure=error)
        assert c.get('/api/v1/games/1/report?season=2026&kind_code=E&next_kind=E&next_sno=2&context_hash='+'a'*64).status_code==status


def test_router_passes_formal_population_records_without_year_or_round_substitution(monkeypatch):
    for year,kind,count in [(2026,"E",64),(2026,"C",0),(2025,"E",0)]:
        c,calls=client(monkeypatch)
        assert c.get(f"/api/v1/games/1/report?season={year}&kind_code={kind}").status_code==200
        records=calls[2]["population_records"]
        assert sum(len(r["members"]) for r in records if r["round"]==kind)==count
        assert all(r["year"]==year and r["round"] in ("E","C") for r in records)


def test_router_loads_each_round_once_for_base_and_enrichment(monkeypatch):
    for query in ("", "&next_kind=C&next_sno=901&context_hash="+"a"*64):
        requested=[]
        c,_=client(monkeypatch)
        monkeypatch.setattr(report.official_population,"load",lambda year,kind: requested.append((year,kind)) or [])
        assert c.get("/api/v1/games/4/report?season=2026&kind_code=E"+query).status_code==200
        assert requested==[(2026,"E"),(2026,"C")]


def test_report_anchor_is_read_only_and_only_returns_x_identity(monkeypatch):
    c,calls=client(monkeypatch)
    monkeypatch.setattr(report,'report_anchor',lambda cur,season,kind,sno: calls.append((season,kind,sno)) or {'status':'ok','anchor':{'kind_code':'E','game_sno':4}})
    r=c.get('/api/v1/games/901/report-anchor?season=2026&kind_code=C')
    assert r.status_code==200 and r.json()['anchor']=={'kind_code':'E','game_sno':4}
    assert calls==['SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY',(2026,'C',901)]
    assert c.get('/api/v1/games/901/report-anchor?season=2026&kind_code=A').status_code==422
    assert c.post('/api/v1/games/901/report-anchor?season=2026&kind_code=C').status_code==405
