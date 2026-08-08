from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

from tests import conftest


def test_report_header_identifies_current_git_worktree(monkeypatch) -> None:
    values = iter(("abc1234", "feature/example"))
    monkeypatch.setattr(conftest, "_git_output", lambda *_: next(values))

    assert conftest._location_header() == [
        f"pytest location: cwd={conftest.Path.cwd()}",
        "pytest location: git_head=abc1234",
        "pytest location: git_branch=feature/example",
    ]


def test_report_header_marks_unavailable_git_metadata(monkeypatch) -> None:
    monkeypatch.setattr(conftest, "_git_output", lambda *_: None)

    assert conftest._location_header()[1:] == [
        "pytest location: git_head=unavailable",
        "pytest location: git_branch=detached",
    ]


def test_quiet_mode_writes_location_header(monkeypatch) -> None:
    lines: list[str] = []
    reporter = SimpleNamespace(write_line=lines.append)
    session = SimpleNamespace(
        config=SimpleNamespace(
            option=SimpleNamespace(quiet=1),
            pluginmanager=SimpleNamespace(get_plugin=lambda _: reporter),
        )
    )
    monkeypatch.setattr(conftest.psycopg, "connect", lambda *_, **__: nullcontext())
    monkeypatch.setattr(conftest, "_location_header", lambda: ["location"])

    conftest.pytest_sessionstart(session)

    assert lines == ["location"]
