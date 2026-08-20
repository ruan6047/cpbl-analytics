"""DATA-PA-REBUILD-GAP1：受控接受路徑的閘門 ＋ 過期偵測選集的守衛（無 DB 依賴）。

守衛要證明的三件事（卡面 Q6）：
1. **不在碼內清單的場次拒絕**——而且是在**寫入路徑**拒絕，不是只擋 CLI。
2. **``invariant_violations`` 非空拒絕**，任何理由都不能覆寫。
3. **批次／自動路徑呼叫不到**——`build_scope` 連參數都沒有，構造上遞不進去。

外加過期偵測（Q1）與遙測（Q3）的形狀守衛。CI 無真實 Postgres，故一律用 fake cursor／
monkeypatch，不打真實 DB（比照 tests/test_refresh_pa_daily.py 既有作法）。
"""

from __future__ import annotations

import inspect
from contextlib import contextmanager
from datetime import date
from typing import Any

import pytest

from cpbl.ingest import pa_build as pb
from cpbl.ingest import run_refresh_recent as rr

# `2019/A/173` 的**真實** validation_summary.invariant_violations（自本機 DB 逐字取出，
# 兩筆 reconciliation build 皆為此值）。⚠️ 用真實樣本不是隨手構造的：構造的樣本會缺欄位
# 而走到另一條路徑，讓守衛看起來過了卻沒驗到東西。
REAL_INVARIANT_2019_A_173: list[dict[str, Any]] = [{"half": "1", "inning": 1, "out_pa": 4}]


# ---------------------------------------------------------------------------
# 閘門 1：碼內封閉清單就是實測過、且已 commit 過查核的那三場
# ---------------------------------------------------------------------------
def test_allowlist_is_exactly_what_was_reviewed() -> None:
    """放寬這個集合是決定，不是筆誤——多一場就會讓這條紅燈，逼它進 diff。"""
    assert pb.ACCEPTED_RECONCILIATIONS == frozenset({
        (2026, "D", 119), (2026, "D", 97), (2026, "A", 209),
    })


@pytest.mark.parametrize("year,kind,game", [
    (2019, "A", 173),   # 真實的危險樣本：不變式違反
    (2026, "D", 118),   # 下一場續賽：時效壓力最大的那場，也不得憑「很急」通過
    (2026, "A", 1),
    (2025, "D", 119),   # 只差年份
])
def test_rejects_games_outside_allowlist(year: int, kind: str, game: int) -> None:
    reasons = pb.reconciliation_accept_rejections(year, kind, game)
    assert any(r.startswith(pb.REJECT_NOT_ALLOWLISTED) for r in reasons)


def test_allowlisted_game_with_clean_invariant_passes() -> None:
    """反向：清單內＋不變式空＋有待收尾 → 零理由。否則這組守衛是恆真的。"""
    assert pb.reconciliation_accept_rejections(
        2026, "D", 119, invariant_violations=[], outstanding_builds=1,
    ) == []


# ---------------------------------------------------------------------------
# 閘門 2：不變式非空一律拒絕，且與清單**各自獨立**
# ---------------------------------------------------------------------------
def test_rejects_non_empty_invariant_violations_real_sample() -> None:
    reasons = pb.reconciliation_accept_rejections(
        2019, "A", 173, invariant_violations=REAL_INVARIANT_2019_A_173, outstanding_builds=2,
    )
    assert any(r.startswith(pb.REJECT_INVARIANT) for r in reasons)


def test_gates_do_not_short_circuit_both_reasons_surface() -> None:
    """`2019/A/173` 同時踩兩條。短路會讓其中一條永遠沒被證明過。"""
    reasons = pb.reconciliation_accept_rejections(
        2019, "A", 173, invariant_violations=REAL_INVARIANT_2019_A_173, outstanding_builds=2,
    )
    kinds = {r.split(":")[0] for r in reasons}
    assert kinds == {pb.REJECT_NOT_ALLOWLISTED, pb.REJECT_INVARIANT}


def test_invariant_gate_survives_allowlist_being_short_circuited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⭐ 變異檢驗：把清單放寬到涵蓋 `2019/A/173`，不變式**仍須**拒絕。

    這條擋的是「兩道閘門其實是同一道」——若拒絕全靠清單，放寬清單後就會靜默放行
    一場已證損壞的資料。
    """
    monkeypatch.setattr(
        pb, "ACCEPTED_RECONCILIATIONS", frozenset({(2019, "A", 173)}),
    )
    reasons = pb.reconciliation_accept_rejections(
        2019, "A", 173, invariant_violations=REAL_INVARIANT_2019_A_173, outstanding_builds=2,
    )
    assert [r.split(":")[0] for r in reasons] == [pb.REJECT_INVARIANT]


def test_rejects_when_nothing_is_outstanding() -> None:
    """接受路徑只收尾**既有的** reconciliation，不能被拿來對任意場次強制發布。"""
    reasons = pb.reconciliation_accept_rejections(
        2026, "D", 119, invariant_violations=[], outstanding_builds=0,
    )
    assert [r.split(":")[0] for r in reasons] == [pb.REJECT_NOTHING_OUTSTANDING]


# ---------------------------------------------------------------------------
# 閘門在**寫入原語**：直接 import `build_game` 的呼叫端一樣繞不過
#
# ⚠️ iteration 1 的教訓（查核 R1-001）：閘門「有被呼叫」不等於「擋得住」。當時
# `build_game` 的首道閘門只傳 year/kind/game（`outstanding_builds=None` ＝ 明示略過），
# 歷史 invariant 只在 `accept_reconciliation` wrapper 裡查——於是直接呼叫寫入原語，
# 兩道有效檢查全部落空。**故守衛必須打寫入原語本人，而且要數寫入語句**：
# 只驗「有拋例外」不足以分辨「擋住了」與「擋錯地方」。
# ---------------------------------------------------------------------------
# 2026/D/119 的**真實** livelog 列（逐欄自本機 DB 取出，欄位集＝`pa_build._EVENT_COLS`）。
# ⚠️ 用真實列不是排場：隨手構造的列會缺欄位而走到另一條路徑，讓探針看起來過了卻沒
# 推到寫入語句——那樣「零寫入」就變成零資訊。
REAL_LIVELOG_ROWS_2026_D_119: list[dict[str, Any]] = [
    {"year": 2026, "kind_code": "D", "game_sno": 119, "main_event_no": "0110001000",
     "inning_seq": 1, "visiting_home_type": "1", "batting_order": 1, "out_cnt": 0,
     "ball_cnt": 0, "strike_cnt": 1, "pitch_cnt": 1, "content": "好球沒揮棒。",
     "action_name": "一壘安打 ", "batting_action_name": "一安",
     "hitter_acnt": "0000007610", "pitcher_acnt": "0000007570",
     "first_base": None, "second_base": None, "third_base": None,
     "is_strike": True, "is_ball": False, "is_score": False,
     "is_change_player": False, "is_special_event": False,
     "visiting_score": 0, "home_score": 0},
    {"year": 2026, "kind_code": "D", "game_sno": 119, "main_event_no": "0110003000",
     "inning_seq": 1, "visiting_home_type": "1", "batting_order": 1, "out_cnt": 0,
     "ball_cnt": 0, "strike_cnt": 2, "pitch_cnt": 3,
     "content": "擊出左外野平飛球，一壘安打 。",
     "action_name": "一壘安打 ", "batting_action_name": "一安",
     "hitter_acnt": "0000007610", "pitcher_acnt": "0000007570",
     "first_base": None, "second_base": None, "third_base": None,
     "is_strike": True, "is_ball": False, "is_score": False,
     "is_change_player": False, "is_special_event": False,
     "visiting_score": 0, "home_score": 0},
]

# 既有 published build 的一個 PA（pa_id 與上面兩列產生的不同 → reconcile 而非首建
# publish，接受路徑才會真的被引動）。
PUBLISHED_PA_ROW: dict[str, Any] = {
    "pa_id": "00000000-0000-5000-8000-000000000001",
    "hitter_acnt": "0000009999", "end_hitter_acnt": "0000009999",
    "start_pitcher_acnt": "0000007570", "end_pitcher_acnt": "0000007570",
    "result_action": "三振", "start_event_no": "0110900000",
    "end_event_no": "0110900000", "member_fps": ["deadbeef"],
}


class _WriteCountingCursor:
    """密封 cursor：餵得動整條 build 路徑，並**逐句記錄寫入語句**。

    路由以 SQL 片段比對，回應足以讓 `build_game` 一路走到 INSERT／UPDATE；
    `mutations` 為 0 才代表「拒絕發生在任何寫入之前」。
    """

    def __init__(self, outstanding: list[dict[str, Any]],
                 published_pas: list[dict[str, Any]] | None = None) -> None:
        self.outstanding = outstanding
        self.published_pas = published_pas or []
        self.statements: list[str] = []
        self.mutations: list[str] = []
        self.rowcount = 0  # `build_game` 的 accept 收尾 log 會讀它
        self._pending: tuple[str, Any] = ("one", None)
        self._pa_row_id = 0

    @staticmethod
    def _norm(sql: str) -> str:
        return " ".join(sql.split())

    def _record(self, sql: str) -> str:
        norm = self._norm(sql)
        self.statements.append(norm)
        if norm.split(" ", 1)[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            self.mutations.append(norm)
        return norm

    def execute(self, sql: str, _params: Any = None) -> _WriteCountingCursor:
        norm = self._record(sql)
        if "state='reconciliation_required'" in norm:
            self._pending = ("all", self.outstanding)
        elif "FROM cpbl.game_livelog" in norm:
            self._pending = ("all", REAL_LIVELOG_ROWS_2026_D_119)
        elif "FROM cpbl.pitch_tracking" in norm:
            self._pending = ("all", [])
        elif "INSERT INTO cpbl.game_recap_source_revisions" in norm:
            self._pending = ("one", {"id": 9001})
        elif "INSERT INTO cpbl.game_plate_appearances" in norm:
            self._pa_row_id += 1
            self._pending = ("one", {"pa_row_id": self._pa_row_id})
        elif "FROM cpbl.game_plate_appearances pa" in norm:
            self._pending = ("all", self.published_pas)
        else:
            self._pending = ("one", None)
        return self

    def executemany(self, sql: str, _seq: Any) -> None:
        self._record(sql)

    def fetchone(self) -> Any:
        kind, value = self._pending
        return value if kind == "one" else (value[0] if value else None)

    def fetchall(self) -> list[Any]:
        kind, value = self._pending
        return value if kind == "all" else ([value] if value else [])


def _iteration1_gate(year: int, kind: str, game: int, **_dropped: Any) -> None:
    """**逐字復刻 iteration 1 的閘門行為**：只看清單，丟掉兩個資料相依的輸入。

    用途是變異檢驗——證明 `_WriteCountingCursor` 真的看得見寫入。若下面兩條
    「零寫入」守衛在這個壞閘門下**依然**是零寫入，那它們就沒有在證明任何事。
    """
    reasons = pb.reconciliation_accept_rejections(year, kind, game)
    if reasons:
        raise pb.ReconciliationAcceptRejected(year, kind, game, reasons)


def test_build_game_refuses_unlisted_game_without_writing() -> None:
    """⭐ 最深的一道：擋 CLI 擋不住 import 本模組的呼叫端，故 `build_game` 自己要擋。"""
    cur = _WriteCountingCursor(outstanding=[])
    with pytest.raises(pb.ReconciliationAcceptRejected) as exc:
        pb.build_game(cur, 2026, "D", 118, accept_reconciliation=True)
    assert any(r.startswith(pb.REJECT_NOT_ALLOWLISTED) for r in exc.value.reasons)
    assert cur.mutations == []


def test_build_game_refuses_allowlisted_game_with_nothing_outstanding() -> None:
    """⭐ R1-001 之一：清單內、但**沒有東西可收尾** → 寫入原語自己必須拒絕。

    iteration 1 這裡回 `published` 並抵達 3 個寫入語句——接受路徑被拿來對任意
    allowlisted 場次強制發布。閘門邏輯本來就對，錯的是它沒拿到 `outstanding_builds`。
    """
    cur = _WriteCountingCursor(outstanding=[])
    with pytest.raises(pb.ReconciliationAcceptRejected) as exc:
        pb.build_game(cur, 2026, "D", 119, accept_reconciliation=True)

    assert [r.split(":")[0] for r in exc.value.reasons] == [pb.REJECT_NOTHING_OUTSTANDING]
    assert cur.mutations == [], f"拒絕前不得有任何寫入，實際抵達：{cur.mutations}"
    # 讀是允許的：那兩個 SELECT 正是閘門的輸入來源，且它們必須在第一個寫入之前。
    assert any("state='reconciliation_required'" in s for s in cur.statements)


def test_build_game_refuses_historical_invariant_even_when_rebuild_is_clean() -> None:
    """⭐ R1-001 之二：**歷史** `validation_summary` 的不變式必須擋得住。

    本次重算完全乾淨（兩列真實 livelog 不可能違反半局出局數），所以第二道閘門
    什麼也抓不到——唯一能擋的是待收尾 build 上記著的歷史 invariant。iteration 1
    在這個情境下完成 `accept_publish`、抵達 4 個寫入語句，log 還印「resolved 0
    outstanding build」。
    """
    cur = _WriteCountingCursor(
        outstanding=[{
            "build_id": "11111111-1111-4111-8111-111111111111",
            "livelog_revision_id": 9001, "built_at": None,
            "invariant_violations": REAL_INVARIANT_2019_A_173,
        }],
        published_pas=[PUBLISHED_PA_ROW],
    )
    with pytest.raises(pb.ReconciliationAcceptRejected) as exc:
        pb.build_game(cur, 2026, "D", 119, accept_reconciliation=True)

    assert [r.split(":")[0] for r in exc.value.reasons] == [pb.REJECT_INVARIANT]
    assert cur.mutations == [], f"拒絕前不得有任何寫入，實際抵達：{cur.mutations}"


@pytest.mark.parametrize("outstanding,published_pas", [
    ([], None),
    ([{"build_id": "11111111-1111-4111-8111-111111111111",
       "livelog_revision_id": 9001, "built_at": None,
       "invariant_violations": REAL_INVARIANT_2019_A_173}], [PUBLISHED_PA_ROW]),
])
def test_write_counting_probe_is_not_vacuous(
    monkeypatch: pytest.MonkeyPatch,
    outstanding: list[dict[str, Any]],
    published_pas: list[dict[str, Any]] | None,
) -> None:
    """⭐ 變異檢驗：把閘門換回 iteration 1 的版本，同一支探針**必須**看到寫入。

    先講什麼結果會推翻上面兩條守衛：若這條也是零寫入，代表探針根本推不到寫入語句，
    那「`mutations == []`」證明的只是探針自己短命，不是閘門擋住了。
    """
    monkeypatch.setattr(pb, "require_reconciliation_accepted", _iteration1_gate)
    cur = _WriteCountingCursor(outstanding=outstanding, published_pas=published_pas)

    pb.build_game(cur, 2026, "D", 119, accept_reconciliation=True)

    assert cur.mutations, "探針推不到寫入語句 → 零寫入斷言是零資訊"
    assert any(s.startswith("INSERT INTO cpbl.game_recap_source_revisions")
               for s in cur.mutations)


def test_build_game_default_does_not_engage_accept_path() -> None:
    """預設路徑不得碰閘門——否則每日鏈會被一個安全性閘門擋住而全面停擺。"""
    sig = inspect.signature(pb.build_game)
    assert sig.parameters["accept_reconciliation"].default is False
    assert sig.parameters["accept_reconciliation"].kind is inspect.Parameter.KEYWORD_ONLY


# ---------------------------------------------------------------------------
# 閘門 3：批次／自動路徑**構造上**遞不進 accept
# ---------------------------------------------------------------------------
def test_build_scope_has_no_accept_parameter() -> None:
    """回填編排連這個參數都沒有——不是「沒傳」，是「傳不了」。"""
    assert "accept_reconciliation" not in inspect.signature(pb.build_scope).parameters


def test_build_scope_never_passes_accept_to_build_game(monkeypatch: pytest.MonkeyPatch) -> None:
    """實際跑一次編排，攔截每一次 `build_game` 呼叫，確認沒有人偷偷帶旗標。"""
    seen: list[dict[str, Any]] = []

    class _Cur:
        def execute(self, *_a: Any, **_k: Any) -> None:
            return None

        def fetchall(self) -> list[dict[str, Any]]:
            return []

    class _Conn:
        def cursor(self, **_k: Any) -> _Cur:
            return _Cur()

        def commit(self) -> None:
            return None

        def rollback(self) -> None:
            return None

    @contextmanager
    def _fake_conn():
        yield _Conn()

    def _spy(cur: Any, year: int, kind: str, game: int, **kwargs: Any) -> pb.GameBuildResult:
        seen.append(kwargs)
        return pb.GameBuildResult(year, kind, game, "b", "publish", "published")

    monkeypatch.setattr("cpbl.db.conn", _fake_conn)
    monkeypatch.setattr(pb, "build_game", _spy)

    pb.build_scope(2026, 2026, ["A"], only_games=[(2026, "A", 1), (2026, "A", 2)])

    assert len(seen) == 2
    assert all("accept_reconciliation" not in kw for kw in seen)


def test_daily_refresh_does_not_import_accept_path() -> None:
    """每日鏈只用 `build_scope`；接受路徑不得出現在自動流程的呼叫面上。"""
    src = inspect.getsource(rr)
    assert "accept_reconciliation" not in src
    assert "ACCEPTED_RECONCILIATIONS" not in src


# ---------------------------------------------------------------------------
# Q4：接受不得靜默完成——回傳一律帶下游過期清單
# ---------------------------------------------------------------------------
def test_downstream_tables_are_named_and_marked_not_wired_into_daily_refresh() -> None:
    tables = {t["table"] for t in pb.PA_DOWNSTREAM_TABLES}
    assert {"cpbl.batter_re24", "cpbl.pitcher_re24"} <= tables
    assert all(t["wired_into_daily_refresh"] is False for t in pb.PA_DOWNSTREAM_TABLES)


def test_downstream_staleness_reports_every_table_as_stale() -> None:
    class _Cur:
        def execute(self, *_a: Any, **_k: Any) -> None:
            return None

        def fetchone(self) -> dict[str, int]:
            return {"n": 166}

    rows = pb.downstream_staleness(_Cur(), 2026, "A")
    assert len(rows) == len(pb.PA_DOWNSTREAM_TABLES)
    assert all(r["stale"] is True for r in rows)
    assert all("rows_for_scope" in r and "scope" in r for r in rows)


# ---------------------------------------------------------------------------
# Q1：過期偵測選集的 SQL 形狀（三分支聯集 ＋ 取最新 revision）
# ---------------------------------------------------------------------------
class _FakeCursor:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows
        self.sql: str | None = None
        self.params: tuple | None = None

    def execute(self, sql: str, params: tuple | None = None) -> _FakeCursor:
        self.sql, self.params = sql, params
        return self

    def fetchall(self) -> list[tuple]:
        return self._rows


class _FakeConnection:
    def __init__(self, rows: list[tuple]) -> None:
        self.cursor = _FakeCursor(rows)

    def execute(self, sql: str, params: tuple | None = None) -> _FakeCursor:
        return self.cursor.execute(sql, params)


def _fake_conn_factory(rows: list[tuple]):
    holder = _FakeConnection(rows)

    @contextmanager
    def fake_conn():
        yield holder

    return fake_conn, holder


def test_targets_query_carries_stale_revision_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn, holder = _fake_conn_factory([(2026, "D", 97)])
    monkeypatch.setattr(rr, "conn", fake_conn)

    assert rr._pa_build_targets(2026, ["D"], [date(2026, 8, 20), date(2026, 8, 21)]) == [
        (2026, "D", 97)
    ]
    sql = holder.cursor.sql
    assert "game_date = ANY(%s)" in sql                     # 分支一：當日窗
    assert "state = 'published'" in sql                     # 分支二：全域缺口
    assert "game_recap_source_revisions" in sql             # 分支三：過期偵測
    assert "source_kind = 'livelog'" in sql                 # 只比 livelog，不比 tracking
    assert "IS DISTINCT FROM" in sql                        # NULL 安全比對


def test_targets_query_takes_latest_revision_not_arbitrary_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⚠️ `2026/D/119` 有兩筆 revision；取錯會把已處理的場次誤報成漂移。"""
    fake_conn, holder = _fake_conn_factory([])
    monkeypatch.setattr(rr, "conn", fake_conn)

    rr._pa_build_targets(2026, ["D"], [date(2026, 8, 21)])

    sql = " ".join(holder.cursor.sql.split())
    assert "ORDER BY r.id DESC LIMIT 1" in sql


def test_targets_subqueries_qualify_outer_columns() -> None:
    """相關子查詢內的未限定欄名會解析到內層表 → 條件恆真（completion.py 已記載的陷阱）。"""
    src = inspect.getsource(rr._pa_build_targets)
    body = src[src.index("SELECT g.year"):]
    for unqualified in (" year =", " kind_code =", " game_sno ="):
        assert unqualified not in body, f"未限定欄名 {unqualified!r} 會靜默失效"


# ---------------------------------------------------------------------------
# Q3：遙測帶天數，而且天數會動
# ---------------------------------------------------------------------------
def test_coverage_reports_outstanding_and_oldest_days(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_conn, holder = _fake_conn_factory([("A", 250, 250, 0, 0), ("D", 191, 191, 1, 12)])
    monkeypatch.setattr(rr, "conn", fake_conn)

    coverage = rr._pa_build_coverage(2026, ["A", "D"])

    assert coverage == {
        "A": {"completed": 250, "published": 250, "gap": 0,
              "reconciliation_outstanding": 0, "oldest_days": 0},
        "D": {"completed": 191, "published": 191, "gap": 0,
              "reconciliation_outstanding": 1, "oldest_days": 12},
    }
    assert "reconciliation_required" in holder.cursor.sql


def test_step_warns_when_outstanding_even_though_gap_is_zero(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    """⭐ 這條釘住機制事實 (E)：舊版 gap=0 就印「覆蓋恆真」，而 D/119 正卡在第 11 天。"""
    monkeypatch.setattr(rr, "_build_pa_daily", lambda *_a, **_k: {
        "games": 0, "actions": {}, "build_states": {}, "errors": [],
        "coverage": {"D": {"completed": 191, "published": 191, "gap": 0,
                           "reconciliation_outstanding": 1, "oldest_days": 12}},
    })
    with caplog.at_level("INFO"):
        rr._pa_build_step(2026, [date(2026, 8, 21)], include_farm=True)

    assert any(r.levelname == "WARNING" for r in caplog.records)
    assert not any("覆蓋恆真" in r.message for r in caplog.records)


def test_step_tolerates_legacy_coverage_shape_without_new_keys(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    """coverage 形狀是本卡才擴充的；舊形狀不得讓 fail-closed 外層炸成 error。"""
    monkeypatch.setattr(rr, "_build_pa_daily", lambda *_a, **_k: {
        "games": 0, "actions": {}, "build_states": {}, "errors": [],
        "coverage": {"A": {"completed": 5, "published": 5, "gap": 0}},
    })
    with caplog.at_level("INFO"):
        result = rr._pa_build_step(2026, [date(2026, 8, 21)], include_farm=True)

    assert "error" not in result
    assert any("覆蓋恆真" in r.message for r in caplog.records)
