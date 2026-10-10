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
    def build(*args):
        calls.append(args)
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
