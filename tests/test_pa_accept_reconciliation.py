"""DATA-PA-REBUILD-GAP1：受控接受路徑的閘門 ＋ 過期偵測選集的守衛（無 DB 依賴）。

守衛要證明的三件事（卡面 Q6）：
1. **不在碼內清單的場次拒絕**——而且是在**寫入路徑**拒絕，不是只擋 CLI。
2. **``invariant_violations`` 非空拒絕**，任何理由都不能覆寫。
3. **批次／自動路徑呼叫不到**——`build_scope` 連參數都沒有，構造上遞不進去。

外加過期偵測（Q1）與遙測（Q3）的形狀守衛。CI 無真實 Postgres，故一律用 fake cursor／
monkeypatch，不打真實 DB（比照 tests/test_refresh_pa_daily.py 既有作法）。

⭐ 例外：檔尾 C1–C5 是**並行**守衛（iteration 2 查核 R2-001）。「兩個交易能不能越過
彼此」由 Postgres 的鎖與可見性語意決定，fake cursor 在構造上量不到——那正是 R2 報告把
它標成「未驗」的原因，而「人工單發 CLI」是理由不是證明。故 C1–C5 用**兩條真連線**打
一個拋棄式資料庫，預設 skip（見該節說明）。
"""

from __future__ import annotations

import inspect
import os
from contextlib import contextmanager
from datetime import date
from pathlib import Path
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


# ---------------------------------------------------------------------------
# R2-001：同場序列化——鎖的**位置**與收尾的**作用域**（無 DB，CI 必跑）
# ---------------------------------------------------------------------------
def test_game_lock_key_is_stable_and_per_game() -> None:
    """同場跨行程同一把、不同場不同把；值本身釘死，改了要進 diff（會使跨版本互不互斥）。"""
    assert pb.game_lock_key(2026, "D", 119) == -6109938732155617607
    assert pb.game_lock_key(2026, "D", 97) == -4508149334657502290
    keys = {pb.game_lock_key(y, k, g)
            for y in (2025, 2026) for k in ("A", "D") for g in range(1, 200)}
    assert len(keys) == 2 * 2 * 199, "鍵碰撞會讓無關的兩場互相等待"
    assert all(-(2 ** 63) <= k < 2 ** 63 for k in keys), "必須落在 bigint 範圍內"


@pytest.mark.parametrize("accept", [False, True])
def test_game_lock_is_the_very_first_statement_on_both_paths(accept: bool) -> None:
    """⭐ 鎖的位置是承重的：它必須早於 `outstanding_reconciliations`（接受判定的輸入）
    與 `_fetch_events`（來源讀取）。晚一句，判定與重建就仍建立在鎖外的快照上。

    兩條路徑都驗——查核者找到的交錯是「accept vs **正常** build」，只鎖其中一條等於沒鎖。
    """
    cur = _WriteCountingCursor(outstanding=[], published_pas=[PUBLISHED_PA_ROW])
    try:
        pb.build_game(cur, 2026, "D", 119, accept_reconciliation=accept)
    except pb.ReconciliationAcceptRejected:
        pass
    assert cur.statements[0] == "SELECT pg_advisory_xact_lock(%s)", (
        f"第一句不是取鎖，而是 {cur.statements[0]!r}"
    )


def test_accept_closeout_is_scoped_to_build_ids_not_to_the_game() -> None:
    """收尾 UPDATE 不得再用 year/kind/game 場次級條件——那會收掉沒審過的列。"""
    src = inspect.getsource(pb.build_game)
    closeout = src[src.index("if accepted:"):]
    assert "build_id = ANY(%s::uuid[])" in closeout
    assert "AND state='reconciliation_required'" in closeout
    assert "game_sno=%s" not in closeout.split("log.warning", 1)[0], (
        "收尾條件裡不得再出現場次級欄位"
    )


def test_accept_wrapper_reports_the_reviewed_set_from_the_write_primitive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``resolved_builds`` 必須由 `build_game`（鎖內）回傳，wrapper 不得自己再查一次。

    wrapper 的查詢發生在**取鎖之前**，回報的集合可能與實際收尾的那一組不同——
    「兩份判定會漂移」在 iteration 1 已經以閘門輸入的形態發生過一次。
    """
    assert "outstanding_reconciliations(" not in inspect.getsource(pb.accept_reconciliation)

    class _Conn:
        def cursor(self, **_k: Any) -> Any:
            return object()

        def commit(self) -> None:
            return None

        def rollback(self) -> None:
            return None

    @contextmanager
    def _fake_conn():
        yield _Conn()

    monkeypatch.setattr("cpbl.db.conn", _fake_conn)
    monkeypatch.setattr(pb, "downstream_staleness", lambda *_a, **_k: [])
    monkeypatch.setattr(pb, "build_game", lambda *_a, **_k: pb.GameBuildResult(
        2026, "D", 119, "new", "accept_publish", "published",
        summary={"reconcile": {}, "box_pa": 1}, resolved_builds=["reviewed-1", "reviewed-2"],
    ))

    assert pb.accept_reconciliation(2026, "D", 119)["resolved_builds"] == [
        "reviewed-1", "reviewed-2"
    ]


def test_build_scope_commits_once_per_game() -> None:
    """鎖是交易級的，`build_scope` 的逐場 commit 因此不是效能選擇，是這把鎖的前提：
    一個交易累積多場的鎖，兩個取鎖順序相反的呼叫端就能互鎖。"""
    src = inspect.getsource(pb.build_scope)
    loop = src[src.index("for i, (year, kind, game) in enumerate(games):"):]
    body = loop[:loop.index("if (i + 1) % log_every")]
    assert "c.commit()" in body, "逐場 commit 消失 → 鎖會在單一交易內累積"


# ===========================================================================
# C1–C5：兩連線交錯（需拋棄式資料庫，預設 skip）
# ===========================================================================
# 為什麼非得打真 DB：R2-001 講的是「READ COMMITTED 下每個 statement 各取一次 snapshot，
# 於是交易 A 查完集合 S 之後、收尾之前，交易 B 提交的新列 A 看得見」。這是 Postgres 的
# 語意，不是本專案的程式碼分支——monkeypatch 出來的 cursor 沒有交易、沒有鎖、沒有可見性，
# 量到的只會是我自己寫的假象。R2 報告把這條標「未驗」正是因為當時只有 fake cursor。
#
# 一次性準備（資料庫本身拋棄式；schema 由測試自己重建，不依賴既有內容）：
#   createdb -h localhost -p 5433 -U cpbl cpbl_pa_lock1
#   PA_BUILD_LOCK_TEST_DATABASE_URL=postgresql://cpbl:...@localhost:5433/cpbl_pa_lock1 \
#     uv run pytest tests/test_pa_accept_reconciliation.py -q
#
# ⚠️ 每個測試都 `DROP SCHEMA cpbl CASCADE` 重來，所以**不得**指向開發或生產資料庫；
# 名稱斷言（`_EXPECTED_LOCK_DB_NAME`）是機器層的防呆。
_LOCK_DB_URL_ENV = "PA_BUILD_LOCK_TEST_DATABASE_URL"
_EXPECTED_LOCK_DB_NAME = "cpbl_pa_lock1"
_MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"

# 阻塞斷言的等待上限。撞不到鎖時測試會等滿這段時間才判 FAIL；取得鎖時 0 等待。
_LOCK_TIMEOUT = "250ms"

requires_lock_db = pytest.mark.skipif(
    not os.getenv(_LOCK_DB_URL_ENV),
    reason=f"requires a throwaway PostgreSQL via {_LOCK_DB_URL_ENV}",
)

# 續賽後才發生的第三列：欄位集**逐欄沿用**上面那兩列真實 livelog（同一場、同一次爬取），
# 只改事件序／打序／打者／結果。⚠️ 隨手構造的列會缺欄位而走到另一條路徑，讓情境看起來
# 建好了卻沒踩到 reconcile——故 `_seed_published_plus_outstanding` 對兩次 build 的
# action 各下一條 assert，樣本漂掉會當場紅燈而不是靜默變成零資訊。
CONTINUATION_ROW_2026_D_119: dict[str, Any] = {
    **REAL_LIVELOG_ROWS_2026_D_119[-1],
    "main_event_no": "0120001000", "batting_order": 2, "pitch_cnt": 4, "strike_cnt": 1,
    "content": "擊出中外野飛球，接殺出局。", "action_name": "中飛 ",
    "batting_action_name": "中飛", "hitter_acnt": "0000007611",
}


def _fresh_schema(url: str) -> None:
    """把拋棄式資料庫的 `cpbl` schema 重建成**真實 DDL**：直接跑 `migrations/*.sql`。

    刻意不手寫精簡版 schema——手寫的會和生產漂移，而這裡要驗的正是與生產同一套約束下
    的鎖行為（partial unique index、FK、state CHECK 全部在場）。
    """
    import psycopg

    assert url.rsplit("/", 1)[-1] == _EXPECTED_LOCK_DB_NAME, "只在專用拋棄式資料庫上跑"
    with psycopg.connect(url) as setup:
        setup.execute("DROP SCHEMA IF EXISTS cpbl CASCADE")
        setup.execute("CREATE SCHEMA cpbl")
        for sql_file in sorted(_MIGRATIONS.glob("*.sql")):
            setup.execute(sql_file.read_text(encoding="utf-8"))
        setup.commit()


@pytest.fixture
def lock_db() -> str:
    url = os.environ[_LOCK_DB_URL_ENV]
    _fresh_schema(url)
    return url


def _insert_livelog(cur: Any, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        cols = list(row)
        cur.execute(
            f"INSERT INTO cpbl.game_livelog ({','.join(cols)}) "  # noqa: S608 — 欄名來自本檔常數
            f"VALUES ({','.join(['%s'] * len(cols))}) ON CONFLICT DO NOTHING",
            [row[c] for c in cols],
        )


def _seed_published_plus_outstanding(cur: Any, connection: Any) -> None:
    """用**真實 builder** 造出「舊 published ＋ 一筆待收尾」——本缺陷的真實現場形狀。

    不手工 INSERT build 列：手工列的 `validation_summary`／fingerprint 不是 builder 產的，
    接受路徑會走到不同分支。兩條 assert 釘住情境確實成立。
    """
    _insert_livelog(cur, REAL_LIVELOG_ROWS_2026_D_119)
    connection.commit()
    first = pb.build_game(cur, 2026, "D", 119)
    connection.commit()
    assert first.action == "publish", f"情境沒建起來：首建 action={first.action}"

    _insert_livelog(cur, [CONTINUATION_ROW_2026_D_119])   # 續賽：來源長大
    connection.commit()
    second = pb.build_game(cur, 2026, "D", 119)
    connection.commit()
    assert second.action == "reconcile", f"情境沒建起來：續建 action={second.action}"


@contextmanager
def _two_connections(url: str):
    """A／B 兩條真連線；B 設 `lock_timeout`，撞到鎖時以 `LockNotAvailable` 現形而非乾等。"""
    import psycopg

    with psycopg.connect(url) as a, psycopg.connect(url) as b:
        from psycopg.rows import dict_row

        cur_a, cur_b = a.cursor(row_factory=dict_row), b.cursor(row_factory=dict_row)
        cur_b.execute(f"SET lock_timeout = '{_LOCK_TIMEOUT}'")
        yield a, cur_a, b, cur_b
        a.rollback()
        b.rollback()


@requires_lock_db
def test_c1_normal_build_blocks_a_concurrent_accept_on_the_same_game(lock_db: str) -> None:
    """⭐ 查核者找到的交錯，方向一：正常 `build_game` 在途 → 同場 accept 進不來。

    ⚠️ **A 這一側刻意不寫任何列**（該場無 livelog → `skip_no_events`，測試自己驗
    `game_recap_builds` 仍為空），因為這條測試要隔離的是 advisory lock。第一版讓 A 跑
    一個有資料的 build，結果它在拿掉鎖的變異版本下**依然**紅不了——B 撞到的是 A 未提交
    列的 row lock 與 `uq_game_recap_builds_one_published` 這個 partial unique index，
    不是我要驗的東西。同一支 `LockNotAvailable` 可以由三種不同機制產生，不隔離就分不出來。

    修好後的失敗形態是 `LockNotAvailable`——**不是** `ReconciliationAcceptRejected`
    （那代表 B 已走到閘門，也就是鎖沒攔住；C4 拿掉鎖後看到的正是後者）。
    """
    import psycopg

    with _two_connections(lock_db) as (a, cur_a, _b, cur_b):
        assert pb.build_game(cur_a, 2026, "D", 119).action == "skip_no_events"
        cur_a.execute("SELECT count(*) AS n FROM cpbl.game_recap_builds")
        assert cur_a.fetchone()["n"] == 0, "A 若寫了列，B 可能是撞 row lock 而非 advisory lock"

        with pytest.raises(psycopg.errors.LockNotAvailable):
            pb.build_game(cur_b, 2026, "D", 119, accept_reconciliation=True)


@requires_lock_db
def test_c2_accept_blocks_a_concurrent_normal_build_from_its_first_statement(
    lock_db: str,
) -> None:
    """⭐ 方向二：accept 交易一開始就持鎖 → 同場正常 build 插不進來。

    這條釘住「鎖在閘門**之前**」：A 的 accept 被閘門拒絕（該場無待收尾），交易並未
    rollback，鎖仍在——若鎖擺在閘門之後，A 這條路徑根本沒拿到鎖，B 會直接通過。
    """
    import psycopg

    with _two_connections(lock_db) as (_a, cur_a, _b, cur_b):
        with pytest.raises(pb.ReconciliationAcceptRejected):
            pb.build_game(cur_a, 2026, "D", 97, accept_reconciliation=True)

        with pytest.raises(psycopg.errors.LockNotAvailable):
            pb.build_game(cur_b, 2026, "D", 97)


@requires_lock_db
def test_c3_lock_is_per_game_so_other_games_are_not_serialized(lock_db: str) -> None:
    """對照組：鎖必須是**逐場**的。少了這條，「一把全域鎖」也會讓 C1／C2 全綠，
    而那會把每日回填串成單線。B 打不同場時走到閘門被拒＝它確實通過了取鎖那一句。"""
    with _two_connections(lock_db) as (_a, cur_a, _b, cur_b):
        assert pb.build_game(cur_a, 2026, "D", 119).action == "skip_no_events"  # A 持 119 的鎖

        with pytest.raises(pb.ReconciliationAcceptRejected) as exc:
            pb.build_game(cur_b, 2026, "D", 97, accept_reconciliation=True)
        assert [r.split(":")[0] for r in exc.value.reasons] == [pb.REJECT_NOTHING_OUTSTANDING]


@requires_lock_db
def test_c4_lock_probe_is_not_vacuous_without_it_the_accept_walks_straight_in(
    lock_db: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⭐ 變異檢驗：先講什麼結果會推翻 C1——把取鎖換成 no-op。

    若 C1 的 `LockNotAvailable` 其實來自別的東西（例如某張表的 row lock），那拿掉
    advisory lock 之後它應該照樣阻塞。這裡證明它不會：沒有鎖，B 一路走到閘門。
    """
    monkeypatch.setattr(pb, "lock_game_for_build", lambda *_a, **_k: 0)

    with _two_connections(lock_db) as (_a, cur_a, _b, cur_b):
        assert pb.build_game(cur_a, 2026, "D", 119).action == "skip_no_events"

        # 與 C1 逐字相同的第二步。差別只有「有沒有鎖」這一個變因。
        with pytest.raises(pb.ReconciliationAcceptRejected) as exc:
            pb.build_game(cur_b, 2026, "D", 119, accept_reconciliation=True)
        assert [r.split(":")[0] for r in exc.value.reasons] == [pb.REJECT_NOTHING_OUTSTANDING]


@requires_lock_db
def test_c5_closeout_spares_a_build_that_appeared_after_the_reviewed_set_was_taken(
    lock_db: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⭐ 第二道：即使有寫入端**不走這把鎖**（有人手打原生 SQL），收尾也只准動審過的那組。

    交錯精確重現在查核者指的那一點——`outstanding_reconciliations` 回來之後、收尾之前，
    另一條連線提交一筆新的 `reconciliation_required`。

    先講什麼結果會推翻它：舊的場次級收尾條件
    （`WHERE year/kind_code/game_sno AND state='reconciliation_required'`）會連注入的那筆
    一起 supersede。測試末尾把那個舊條件當**查詢**跑一次，證明它此刻確實命中注入列——
    所以「注入列還活著」不是因為沒東西可收，而是因為收尾換了作用域。
    """
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(lock_db) as a, psycopg.connect(lock_db) as intruder:
        cur_a = a.cursor(row_factory=dict_row)
        _seed_published_plus_outstanding(cur_a, a)

        injected: dict[str, str] = {}
        real_query = pb.outstanding_reconciliations

        def _query_then_inject(cur: Any, year: int, kind: str, game: int) -> list[dict[str, Any]]:
            reviewed = real_query(cur, year, kind, game)
            if not injected:
                cur_i = intruder.cursor(row_factory=dict_row)
                cur_i.execute(
                    "INSERT INTO cpbl.game_recap_builds (build_id, year, kind_code, game_sno,"
                    " livelog_revision_id, builder_version, taxonomy_version, state,"
                    " validation_summary)"
                    " VALUES (gen_random_uuid(), %s, %s, %s, %s, 'intruder', 'intruder',"
                    " 'reconciliation_required', '{}'::jsonb) RETURNING build_id",
                    (year, kind, game, reviewed[0]["livelog_revision_id"]),
                )
                injected["build_id"] = str(cur_i.fetchone()["build_id"])
                intruder.commit()
            return reviewed

        monkeypatch.setattr(pb, "outstanding_reconciliations", _query_then_inject)
        result = pb.build_game(cur_a, 2026, "D", 119, accept_reconciliation=True)
        a.commit()

        assert result.action == "accept_publish"
        assert injected, "注入沒有發生 → 這條測試什麼也沒證明"
        assert injected["build_id"] not in result.resolved_builds

        cur_a.execute("SELECT state FROM cpbl.game_recap_builds WHERE build_id = %s",
                      (injected["build_id"],))
        assert cur_a.fetchone()["state"] == "reconciliation_required", (
            "未經審核的 build 被順手 supersede 了"
        )

        # 正向：審過的那組**確實**被收掉。少了這一半，上面那條可能只是「收尾根本沒跑」。
        cur_a.execute(
            "SELECT build_id, state FROM cpbl.game_recap_builds WHERE build_id = ANY(%s::uuid[])",
            (result.resolved_builds,),
        )
        reviewed_states = {r["state"] for r in cur_a.fetchall()}
        assert result.resolved_builds and reviewed_states == {"superseded"}

        # 舊條件此刻的命中數＝1（就是注入列）→ 未修版本會把它一起收掉。
        cur_a.execute(
            "SELECT count(*) AS n FROM cpbl.game_recap_builds"
            " WHERE year=2026 AND kind_code='D' AND game_sno=119"
            "   AND state='reconciliation_required'"
        )
        assert cur_a.fetchone()["n"] == 1, "舊的場次級條件若已經零命中，這條變異檢驗是空的"
        a.rollback()
