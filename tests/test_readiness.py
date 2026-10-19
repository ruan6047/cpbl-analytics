"""CLI 與依賴矩陣使用替身；本檔不得連線真服務。"""
import json
import subprocess
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from cpbl.readiness import check_api, main


def settings(**changes):
    values = dict(database_url="postgresql://app:secret@db/cpbl_test",
                  redis_url="redis://redis:6379/0",
                  model_fields_set={"database_url", "redis_url"})
    values.update(changes)
    return SimpleNamespace(**values)


class Database:
    def __init__(self, identity=("app", "cpbl_test"), error=None):
        self.identity = identity
        self.error = error
        self.statements = []

    @contextmanager
    def conn(self):
        yield self

    def execute(self, query, *args):
        self.statements.append(query)
        if self.error:
            raise self.error
        return self

    def fetchone(self):
        return self.identity


class Redis:
    def __init__(self, pong=b"PONG", error=None):
        self.pong = pong
        self.error = error
        self.closed = False

    def execute_command(self, command):
        assert command == "PING"
        if self.error:
            raise self.error
        return self.pong

    def close(self):
        self.closed = True


def check(config=None, database=None, redis=None):
    return check_api(config or settings(),
                     connect=(database or Database()).conn,
                     redis_factory=lambda _: redis or Redis())


def test_empty_games_is_legal_and_queries_are_read_only():
    database = Database()
    client = Redis()
    report = check(database=database, redis=client)
    assert report["ready"] is True
    assert report["result"] == "ready"
    assert any("FROM cpbl.games LIMIT 0" in sql for sql in database.statements)
    assert all(sql.startswith(("SELECT", "SET LOCAL")) for sql in database.statements)
    assert client.closed


@pytest.mark.parametrize("identity", [("other", "cpbl_test"), ("app", "other"), None])
def test_wrong_database_identity_is_not_ready(identity):
    report = check(database=Database(identity=identity))
    assert report["ready"] is False
    assert report["result"] == "not_ready"
    assert "db_identity_mismatch" in report["reasons"]


@pytest.mark.parametrize("pong", [True, False, "OK", b"OK", 1, None])
def test_redis_requires_exact_protocol_pong(pong):
    assert check(redis=Redis(pong=pong))["result"] == "not_ready"


@pytest.mark.parametrize("pong", [b"PONG", "PONG"])
def test_exact_pong_is_accepted(pong):
    assert check(redis=Redis(pong=pong))["ready"] is True


def test_missing_explicit_config_never_connects_to_defaults():
    def forbidden(*args):
        raise AssertionError("must not connect")
    report = check_api(settings(model_fields_set=set()), connect=forbidden, redis_factory=forbidden)
    assert report["result"] == "unknown"
    assert set(report["reasons"]) == {"db_config_missing", "redis_config_missing"}


@pytest.mark.parametrize("dsn", ["postgresql:///cpbl", "postgresql://app@db/", "service=prod"])
def test_ambiguous_identity_is_unknown_without_database_connection(dsn):
    def forbidden():
        raise AssertionError("must not connect")
    report = check_api(settings(database_url=dsn), connect=forbidden, redis_factory=lambda _: Redis())
    assert report["result"] == "unknown"


def test_errors_are_sanitized_and_known_failure_dominates_unknown():
    report = check(config=settings(redis_url=None), database=Database(error=OSError("secret@host")))
    assert report["result"] == "not_ready"
    assert "secret" not in json.dumps(report)
    assert "host" not in json.dumps(report)


def test_timeout_is_unknown():
    assert check(database=Database(error=TimeoutError("secret")))["result"] == "unknown"


def test_cli_emits_one_json_object_and_matching_exit(capsys):
    report = check()
    def runner(target):
        assert target == "api"
        return report, 0
    assert main(["--target", "api"], runner=runner) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["ready"] is True
    assert captured.err == ""


def test_cli_invalid_arguments_still_emit_json(capsys):
    assert main(["--target", "unknown"]) == 3
    assert json.loads(capsys.readouterr().out)["result"] == "unknown"


def test_cli_does_not_expose_exception_text(capsys):
    def runner(_):
        raise RuntimeError("secret-password")
    assert main(["--target", "worker"], runner=runner) == 3
    captured = capsys.readouterr()
    assert "secret" not in captured.out + captured.err
    assert json.loads(captured.out)["ready"] is False


def test_cli_rejects_code_payload_disagreement(capsys):
    assert main(["--target", "api"], runner=lambda _: (check(), 2)) == 3
    assert json.loads(capsys.readouterr().out)["ready"] is False


def test_cli_child_timeout_is_unknown(monkeypatch, capsys):
    def timeout(*args, **kwargs):
        assert kwargs["timeout"] < 10
        raise subprocess.TimeoutExpired("child", kwargs["timeout"])
    monkeypatch.setattr(subprocess, "run", timeout)
    assert main(["--target", "api"]) == 2
    assert json.loads(capsys.readouterr().out)["reasons"] == ["probe_timeout"]


@pytest.mark.parametrize("arguments", [[], ["--help"], ["--target", "api", "--extra"]])
def test_all_invalid_invocations_have_safe_json(arguments, capsys):
    assert main(arguments) == 3
    assert json.loads(capsys.readouterr().out)["ready"] is False


@pytest.mark.parametrize("error", [OSError("connection refused secret"),
                                    PermissionError("password secret")])
def test_redis_failures_are_not_ready_and_sanitized(error):
    report = check(redis=Redis(error=error))
    assert report["result"] == "not_ready"
    assert report["dependencies"]["redis"]["state"] == "error"
    assert "secret" not in json.dumps(report)


def test_redis_timeout_is_unknown_and_client_is_closed():
    client = Redis(error=TimeoutError("secret"))
    report = check(redis=client)
    assert report["result"] == "unknown"
    assert client.closed


def test_known_missing_games_structure_is_not_ready():
    class MissingGames(Database):
        def execute(self, query, *args):
            if "FROM cpbl.games" in query:
                raise RuntimeError("missing table secret")
            return super().execute(query, *args)
    report = check(database=MissingGames())
    assert report["result"] == "not_ready"
    assert report["dependencies"]["database"]["identity_match"] is True
    assert report["dependencies"]["database"]["games_shape"] is None
    assert "secret" not in json.dumps(report)


def test_redis_factory_error_is_sanitized():
    def fail(_):
        raise ValueError("redis://password@secret-host")
    report = check_api(settings(), connect=Database().conn, redis_factory=fail)
    assert report["result"] == "not_ready"
    assert "password" not in json.dumps(report)


@pytest.mark.parametrize("field,value", [("schema_version", 2), ("target", "worker"),
    ("ready", 1), ("checked_at", None), ("reasons", "secret")])
def test_cli_rejects_invalid_child_contract(field, value, capsys):
    result = check()
    result[field] = value
    assert main(["--target", "api"], runner=lambda _: (result, 0)) == 3
    assert json.loads(capsys.readouterr().out)["ready"] is False
