"""#469：收官判定已確定冠軍、冠軍表缺該年 ⇒ 自動補上（只新增不覆蓋）＋ coverage 上界動態化。

收官值一律取自 #391 的真實樣本（``tests/test_season_close.py`` 的 2026 C 真實列推導：味全 AAA011、決勝
2026/C/6、亞軍中信兄弟 ACN011），⛔ 不自造冠軍判定。本檔不連 DB（假 cursor）；真 PostgreSQL 上的 SQL
契約在 ``tests/test_championship_autofill_db.py``（CI 資料基底才跑）。
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from cpbl import season_close as sc
from cpbl.ingest import championships as ch
from tests import test_season_close as real391

NOW = datetime(2026, 11, 29, 3, 10, tzinfo=UTC)
REAL_MAJOR_2026 = real391.major(real391.major_games())
# 決勝場 2026/C/6 的真實主客（tests/fixtures/ci_base/games.csv：主 味全 AAA011、客 中信兄弟 ACN011）。
DECISIVE_ROW = ("AAA011", "ACN011")


def test_real_2026_sample_is_decided_for_wei_chuan():
    """前提自證：下面的補列測試都建立在「2026 一軍真實推導＝味全、決勝 2026/C/6」上。"""
    assert REAL_MAJOR_2026.status == "decided"
    assert REAL_MAJOR_2026.champion_team_code == "AAA011"
    assert REAL_MAJOR_2026.decided_by == (2026, "C", 6)
    assert REAL_MAJOR_2026.season == 2026


# =========================================================================== 假 DB


class _Cur:
    """依 SQL 片段回應；記下每一句，讓測試看得到「寫了什麼／沒寫什麼」。"""

    def __init__(self, *, champion_row=None, manager_present=False, decisive=DECISIVE_ROW,
                 coaches=("葉君璋",)):
        self.champion_row, self.manager_present = champion_row, manager_present
        self.decisive, self.coaches = decisive, list(coaches)
        self.sql: list[tuple[str, object]] = []
        self.rowcount = 0
        self._one = None
        self._all: list = []

    def execute(self, sql, params=None):
        self.sql.append((sql, params))
        self.rowcount = 0
        if sql.lstrip().startswith("INSERT"):
            self.rowcount = 1
        elif "FROM cpbl.championships" in sql:
            self._one, self._all = self.champion_row, []  # 成員重建的冠軍清單：空（只驗順序）
        elif "FROM cpbl.championship_managers" in sql:
            self._one = (1,) if self.manager_present else None
        elif "FROM cpbl.games" in sql:
            self._one = self.decisive
        elif "FROM cpbl.coaches" in sql:
            self._all = [(n,) for n in self.coaches]

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all

    def inserts(self, table: str) -> list:
        return [p for s, p in self.sql if s.lstrip().startswith("INSERT") and f"cpbl.{table} " in s]


# =========================================================================== ensure 四情境


def test_decided_and_missing_year_inserts_champion_and_manager():
    cur = _Cur()

    out = ch.ensure_season_champion(cur, REAL_MAJOR_2026, now=NOW, env={})

    assert out["action"] == "inserted" and out["year"] == 2026
    assert out["manager"] == "inserted"
    [champ] = cur.inserts("championships")
    assert champ == {
        "year": 2026, "champion": "AAA011", "runner_up": "ACN011", "franchise": "AAA011",
        "source_url": "https://www.cpbl.com.tw/box?year=2026&KindCode=C&gameSno=6", "verified_at": NOW,
    }
    [mgr] = cur.inserts("championship_managers")
    assert mgr["year"] == 2026 and mgr["manager_name"] == "葉君璋" and mgr["franchise"] == "AAA011"
    assert mgr["source_url"] == "https://www.cpbl.com.tw/team/index?teamNo=AAA011"
    assert mgr["verified_at"] == NOW
    # 只新增、不覆蓋：寫入一律 ON CONFLICT DO NOTHING，⛔ 不得有 UPDATE／DELETE。
    writes = [s for s, _ in cur.sql if not s.lstrip().startswith("SELECT")]
    assert writes and all("ON CONFLICT (year) DO NOTHING" in s for s in writes)


def test_decided_and_year_present_does_not_write():
    cur = _Cur(champion_row=("AAA011", "AAA011"), manager_present=True)

    out = ch.ensure_season_champion(cur, REAL_MAJOR_2026, now=NOW, env={})

    assert out["action"] == "present" and out["manager"] == "present"
    assert cur.inserts("championships") == [] and cur.inserts("championship_managers") == []


@pytest.mark.parametrize("status", ["undecided", "unknown", "no_data", "undecided_tie"])
def test_not_decided_never_writes(status):
    closure = replace(REAL_MAJOR_2026, closed=False, status=status, champion_team_code=None, decided_by=None)
    cur = _Cur()

    out = ch.ensure_season_champion(cur, closure, now=NOW, env={})

    assert out["action"] == "not_decided"
    assert cur.sql == []


@pytest.mark.parametrize("status", ["undecided", "unknown"])
def test_status_alone_gates_the_write(status):
    """只改 status（冠軍與決勝場照留）也不得寫：status 守衛要能單獨擋下。"""
    cur = _Cur()

    out = ch.ensure_season_champion(cur, replace(REAL_MAJOR_2026, status=status), now=NOW, env={})

    assert out["action"] == "not_decided"
    assert cur.sql == []


def test_league_alone_gates_the_write():
    """只把軍別換成二軍（其餘照留一軍真實值）也不得寫：league 守衛要能單獨擋下。"""
    cur = _Cur()

    out = ch.ensure_season_champion(cur, replace(REAL_MAJOR_2026, league=sc.FARM), now=NOW, env={})

    assert out["action"] == "not_decided"
    assert cur.sql == []


def test_kill_switch_writes_nothing_and_reads_nothing():
    cur = _Cur()

    out = ch.ensure_season_champion(cur, REAL_MAJOR_2026, now=NOW, env={ch.AUTOFILL_ENV: "off"})

    assert out["action"] == "disabled"
    assert cur.sql == []


def test_override_open_or_reopened_still_counts_as_decided():
    """看 status 不看 closed：#392 切回／CPBL_SEASON_CLOSE=open 只讓爬蟲恢復，冠軍事實不變。"""
    for override in (sc.OVERRIDE_OPEN, sc.OVERRIDE_REOPENED):
        cur = _Cur()
        out = ch.ensure_season_champion(cur, replace(REAL_MAJOR_2026, closed=False, override=override),
                                        now=NOW, env={})
        assert out["action"] == "inserted"


def test_farm_closure_is_never_written_as_major_champion():
    farm = sc.tally_farm_series(2026, real391.farm_2026_from_raw())
    assert farm.status == "decided"
    cur = _Cur()

    assert ch.ensure_season_champion(cur, farm, now=NOW, env={})["action"] == "not_decided"
    assert cur.sql == []


@pytest.mark.parametrize("decisive", [None, ("AJL011", "ACN011")])
def test_decisive_game_missing_or_inconsistent_writes_nothing(decisive):
    cur = _Cur(decisive=decisive)

    out = ch.ensure_season_champion(cur, REAL_MAJOR_2026, now=NOW, env={})

    assert out["action"] == "no_decisive_game"
    assert cur.inserts("championships") == [] and cur.inserts("championship_managers") == []


@pytest.mark.parametrize(("coaches", "state"), [((), "missing"), (("葉君璋", "代理某某"), "ambiguous")])
def test_manager_written_only_when_exactly_one_head_coach(coaches, state):
    """R2：官網球隊頁現任一軍總教練，該隊該年恰 1 位才寫；否則標缺（冠軍列照補）。"""
    cur = _Cur(coaches=coaches)

    out = ch.ensure_season_champion(cur, REAL_MAJOR_2026, now=NOW, env={})

    assert out["action"] == "inserted" and out["manager"] == state
    assert len(cur.inserts("championships")) == 1
    assert cur.inserts("championship_managers") == []


def test_present_champion_with_missing_manager_backfills_manager_only():
    cur = _Cur(champion_row=("AAA011", "AAA011"), manager_present=False)

    out = ch.ensure_season_champion(cur, REAL_MAJOR_2026, now=NOW, env={})

    assert out["action"] == "present" and out["manager"] == "inserted"
    assert cur.inserts("championships") == []
    assert len(cur.inserts("championship_managers")) == 1


def test_present_row_for_another_team_is_left_alone():
    """既有列與收官判定不一致：⛔ 不覆蓋、也不在不一致的列上掛總教練。"""
    cur = _Cur(champion_row=("ACN011", "ACN011"), manager_present=False)

    out = ch.ensure_season_champion(cur, REAL_MAJOR_2026, now=NOW, env={})

    assert out["action"] == "present_conflict"
    assert cur.inserts("championships") == [] and cur.inserts("championship_managers") == []


# =========================================================================== coverage 動態上界


def test_through_year_follows_latest_decided_major_season():
    assert ch.coverage_through_year(REAL_MAJOR_2026) == 2026
    undecided = replace(REAL_MAJOR_2026, status="undecided", champion_team_code=None, decided_by=None)
    assert ch.coverage_through_year(undecided) == 2025
    # 2027 開打、尚未封王 ⇒ 上界 2026（缺 2026 仍看得見）。
    assert ch.coverage_through_year(replace(undecided, season=2027)) == 2026
    # 判不出球季 ⇒ 不低於既有 canonical 上界。
    assert ch.coverage_through_year(sc.LeagueClosure(sc.MAJOR, None, False, "no_data")) == 2025
    assert ch.coverage_through_year(None) == 2025


def test_coverage_fails_closed_when_decided_year_is_missing():
    years = list(range(1990, 2026))

    cov = ch.championship_coverage(years, as_of=None, through_year=ch.coverage_through_year(REAL_MAJOR_2026))

    assert cov["through_year"] == 2026
    assert cov["complete"] is False and cov["missing_years"] == [2026]
    assert ch.championship_coverage([*years, 2026], as_of=None, through_year=2026)["complete"] is True


def test_coverage_reports_years_without_manager():
    years = list(range(1990, 2027))

    cov = ch.championship_coverage(years, as_of=None, through_year=2026, manager_years=range(1990, 2026))

    assert cov["complete"] is True
    assert cov["managers_missing_years"] == [2026]


# =========================================================================== 入口：autofill／build


class _Conn:
    def __init__(self, cur):
        self.cur = cur

    def cursor(self):
        return self.cur


def _fake_conn(monkeypatch, cur):
    @contextmanager
    def fake():
        yield _Conn(cur)
    monkeypatch.setattr(ch, "conn", fake)


def test_autofill_reads_major_closure_and_writes(monkeypatch):
    cur = _Cur()
    _fake_conn(monkeypatch, cur)

    out = ch.autofill_champion(now=NOW, env={}, read_closure=lambda: REAL_MAJOR_2026)

    assert out["action"] == "inserted"
    assert len(cur.inserts("championships")) == 1


def test_autofill_kill_switch_does_not_read_closure(monkeypatch):
    _fake_conn(monkeypatch, _Cur())

    out = ch.autofill_champion(now=NOW, env={ch.AUTOFILL_ENV: "off"},
                               read_closure=lambda: pytest.fail("read closure while disabled"))

    assert out["action"] == "disabled"


def test_build_runs_ensure_before_truncate(monkeypatch):
    cur = _Cur()
    _fake_conn(monkeypatch, cur)

    out = ch.build_championships(now=NOW, env={}, read_closure=lambda: REAL_MAJOR_2026)

    assert out["autofill"]["action"] == "inserted"
    stmts = [s for s, _ in cur.sql]
    first_insert = next(i for i, s in enumerate(stmts) if "INSERT INTO cpbl.championships " in s)
    truncate = next(i for i, s in enumerate(stmts) if "TRUNCATE cpbl.championship_members" in s)
    assert first_insert < truncate


def test_build_still_rebuilds_members_when_closure_read_fails(monkeypatch):
    """補列失敗不得連坐成員重建（每日鏈其餘步驟照跑）；失敗寫進回傳值、不吞成成功。"""
    cur = _Cur()
    _fake_conn(monkeypatch, cur)

    def boom():
        raise RuntimeError("closure down")

    out = ch.build_championships(now=NOW, env={}, read_closure=boom)

    assert out["autofill"]["action"] == "error" and out["autofill"]["error"] == "RuntimeError"
    assert any("TRUNCATE cpbl.championship_members" in s for s, _ in cur.sql)
    assert cur.inserts("championships") == []


def test_cli_exits_nonzero_when_autofill_errors(monkeypatch):
    from cpbl.ingest import run_build_championships as cli

    monkeypatch.setattr(cli, "migrate", lambda: [])
    monkeypatch.setattr(cli, "build_championships",
                        lambda: {"autofill": {"action": "error", "error": "RuntimeError"}})
    monkeypatch.setattr("sys.argv", ["cpbl-build-championships"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1

    monkeypatch.setattr(cli, "build_championships", lambda: {"autofill": {"action": "inserted"}})
    assert cli.main() is None


# =========================================================================== API coverage


def test_records_coverage_uses_dynamic_upper_bound(monkeypatch):
    from cpbl.api.routers import leaders

    monkeypatch.setattr(leaders, "_major_closure", lambda: REAL_MAJOR_2026)
    seasons = [{"year": y, "manager_name": "x"} for y in range(1990, 2026)]

    cov = leaders._championship_coverage(seasons, *leaders._safe_major_closure())

    assert cov["through_year"] == 2026
    assert cov["complete"] is False and cov["missing_years"] == [2026]


def test_records_endpoint_reads_closure_before_borrowing_its_connection(monkeypatch):
    """⛔ 不在持有端點連線時巢狀借第二條（池上限 8，併發會互卡）。"""
    from cpbl.api.routers import leaders

    order = []

    @contextmanager
    def fake_conn():
        order.append("conn")
        raise RuntimeError("stop after ordering check")
        yield  # pragma: no cover

    monkeypatch.setattr(leaders, "_major_closure", lambda: order.append("closure") or REAL_MAJOR_2026)
    monkeypatch.setattr(leaders, "conn", fake_conn)
    with pytest.raises(RuntimeError):
        leaders.championships.__wrapped__(limit=10)
    assert order == ["closure", "conn"]


def test_records_coverage_fails_closed_when_closure_unreadable(monkeypatch):
    from cpbl.api.routers import leaders

    def boom():
        raise RuntimeError("closure down")

    monkeypatch.setattr(leaders, "_major_closure", boom)
    seasons = [{"year": y, "manager_name": "x"} for y in range(1990, 2027)]

    cov = leaders._championship_coverage(seasons, *leaders._safe_major_closure())

    assert cov["complete"] is False
    assert cov["reason"] == "closure_unavailable"
