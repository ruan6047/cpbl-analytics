"""`scrape_gamelogs` 的母體對帳與失敗訊號契約（DATA-BOX-DEEP-SILENT-FAIL1，#131）。

被修的形狀：逐場抓取失敗被吞成 `log.warning` 後續抓，結尾只印成功數、不對帳函式
第一行自己宣告的目標場數，整批仍 `exit 0`。2026-08-10 週跑 kind=D 宣告 39 場、
成功 8 場、失敗 31 場，`done: {'games': 8}` 看在人眼裡無從判斷 8 是目標還是 39 分之 8。

三條各自獨立、少一條就漏掉一種復發方式：

1. **對帳**：回傳與 log 必須同時給出 target／ok／failed／失敗場號（計數不夠——
   卡面紅線 1 要求可列舉）。
2. **訊號**：預設拋例外，容忍者必須明寫 `allow_partial=True`（Q4 裁定＝乙）。
   選例外而非回傳欄位的理由見 `GamelogScrapeIncomplete` docstring。
3. **下游**：每日鏈的部分失敗用獨立退出碼 69，`scrape-daily.sh` 對它**仍執行**
   生產同步（Q3 裁定＝甲-2）。這條用真的跑一次 shell 副本來證，不讀碼宣稱。

回放資料是真的：`logs/weekly-box-revisions-20260810-141135.log` 的 kind=D 逐行
（31 個失敗場號、8 個成功場號、順序照 log）。失敗以**注入**重現，不打官網。
"""

from __future__ import annotations

import inspect
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import psycopg
import pytest

from cpbl.ingest import cpbl_gamelog, run_refresh_recent

ROOT = Path(__file__).resolve().parents[1]

# 2026-08-10 週跑 kind=D 的逐場結果（log 逐行抽出，順序即迴圈順序）。
REPLAY_20260810_D_FAILED = (
    51, 97, 102, 108, 119, 158, 159, 160, 161, 162, 163, 166, 167, 168, 169, 170,
    171, 172, 173, 174, 176, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187,
)
REPLAY_20260810_D_OK = (188, 189, 190, 191, 192, 193, 194, 195)
REPLAY_20260810_D_TARGET = 39   # log 首行「深度重抓 box：… kind=D … → 39 場」

_OK_PAYLOAD = json.dumps({
    "ScoreboardJson": json.dumps([{"TeamNo": "A", "InningSeq": 1}]),
    "LiveLogJson": "[]",
    "BattingJson": "[]",
    "PitchingJson": "[]",
})


class _InjectedSession:
    """假 browser session：指定場號拋例外（重現 08-10 的 ERR_INTERNET_DISCONNECTED），
    其餘回 200。刻意**不**連任何網路。"""

    def __init__(self, fail_snos: set[int], *, http_status: int | None = None,
                 body: str | None = None) -> None:
        self.fail_snos = fail_snos
        self.http_status = http_status
        self.body = body

    def page_html(self, _path: str, require=None) -> str:
        return '<input name="__RequestVerificationToken" value="replay-token">'

    def post(self, _box_path, _endpoint, form, **_kwargs) -> tuple[int, str]:
        sno = int(form["GameSno"])
        if sno in self.fail_snos:
            if self.http_status is not None:
                return self.http_status, "challenge"
            raise RuntimeError(
                "Page.goto: net::ERR_INTERNET_DISCONNECTED at https://www.cpbl.com.tw/box"
            )
        return 200, self.body if self.body is not None else _OK_PAYLOAD


@pytest.fixture
def injected(monkeypatch: pytest.MonkeyPatch):
    """把 session／DB 寫入／快照全部換掉，只留 scrape_gamelogs 自己的控制流。"""

    def _install(fail_snos, **kwargs) -> None:
        session = _InjectedSession(set(fail_snos), **kwargs)
        monkeypatch.setattr("cpbl.ingest._browser.session", lambda: session)
        monkeypatch.setattr(cpbl_gamelog.time, "sleep", lambda _delay: None)
        monkeypatch.setattr(cpbl_gamelog, "_upsert", lambda _t, _c, _pk, rows: len(rows))
        monkeypatch.setattr(cpbl_gamelog, "record_source_revision", lambda **_kw: None)
        monkeypatch.setattr(cpbl_gamelog, "record_box_pitching_revisions",
                            lambda *_a, **_kw: None)

    return _install


# ----------------------------------------------------------------- 1. 對帳


def test_replay_20260810_reports_target_and_every_failed_sno(injected, caplog) -> None:
    """08-10 情境回放：容忍模式下必須自陳 39/8/31 並列出 31 個失敗場號。"""
    injected(REPLAY_20260810_D_FAILED)
    snos = sorted(REPLAY_20260810_D_FAILED + REPLAY_20260810_D_OK)
    assert len(snos) == REPLAY_20260810_D_TARGET

    with caplog.at_level("WARNING", logger="cpbl.gamelog"):
        out = cpbl_gamelog.scrape_gamelogs(2026, snos, "D", delay=0, allow_partial=True)

    assert out["target"] == REPLAY_20260810_D_TARGET
    assert out["games"] == len(REPLAY_20260810_D_OK)
    assert out["failed"] == list(REPLAY_20260810_D_FAILED)
    # 母體恆等式：舊版只有 games=8，看不出分母；新版三者必須閉合。
    assert out["target"] == out["games"] + len(out["failed"])
    # ⚠️ 「每條路徑都有呼叫 _fail()」不等於恆等式成立——路徑也可能呼叫**兩次**。
    # 2026-08-19 實測過：428 之後重取 token 若失敗，同一場會被記兩次
    # （failed_snos=[97, 97, 188, 188]、target=2 卻 failed=4）。故要連重複一起釘。
    assert len(out["failed"]) == len(set(out["failed"])), "同一場不得被計入失敗兩次"
    reconcile = [r.getMessage() for r in caplog.records if "reconcile:" in str(r.msg)]
    assert reconcile, "有失敗時必須留下一行對帳（WARNING 級）"
    assert "target=39" in reconcile[0] and "ok=8" in reconcile[0] and "failed=31" in reconcile[0]
    assert "51" in reconcile[0] and "187" in reconcile[0], "失敗場號要可列舉，不是只給計數"


def test_full_success_reconciles_to_zero_failures(injected) -> None:
    injected([])
    out = cpbl_gamelog.scrape_gamelogs(2026, [188, 189], "D", delay=0)

    assert (out["target"], out["games"], out["failed"]) == (2, 2, [])


def test_empty_target_is_not_a_failure(injected) -> None:
    injected([])
    out = cpbl_gamelog.scrape_gamelogs(2026, [], "D", delay=0)

    assert out["target"] == 0 and out["failed"] == []


def test_http_non_200_counts_as_a_failed_game(injected) -> None:
    """428（HiNet 挑戰）與請求例外是同一件事：那一場沒抓到。"""
    injected([97], http_status=428)

    with pytest.raises(cpbl_gamelog.GamelogScrapeIncomplete) as excinfo:
        cpbl_gamelog.scrape_gamelogs(2026, [97, 188], "D", delay=0)

    assert excinfo.value.result["failures"] == [{"sno": 97, "error_code": "http_428"}]


def test_invalid_response_json_counts_as_a_failed_game(injected) -> None:
    injected([], body="<html>challenge</html>")

    with pytest.raises(cpbl_gamelog.GamelogScrapeIncomplete) as excinfo:
        cpbl_gamelog.scrape_gamelogs(2026, [188], "D", delay=0)

    assert excinfo.value.result["failures"] == [
        {"sno": 188, "error_code": "invalid_response_json"}
    ]


def test_broken_embedded_source_json_counts_as_a_failed_game(injected) -> None:
    """內嵌來源 JSON 壞掉＝那一場沒抓齊＝失敗（R1-01，2026-08-19 跨家族查核）。

    第一版把它列進 `degraded` 而不計入 `failed`，於是 `ScoreboardJson='{broken'`
    重放得到 `games=1, failed=[], exit 0`——**本卡要消滅的靜默缺口原封不動地留了一個**。
    查核裁定逐字：「應算逐場失敗，不只是 degraded。」
    """
    injected([], body=json.dumps({
        "ScoreboardJson": "{broken", "LiveLogJson": "[]",
        "BattingJson": "[]", "PitchingJson": "[]",
    }))

    with pytest.raises(cpbl_gamelog.GamelogScrapeIncomplete) as excinfo:
        cpbl_gamelog.scrape_gamelogs(2026, [188], "D", delay=0)

    result = excinfo.value.result
    assert result["failures"] == [{"sno": 188, "error_code": "invalid_source_json"}]
    assert result["games"] == 0
    assert result["target"] == result["games"] + len(result["failed"])


def test_broken_source_json_still_writes_the_sources_that_did_parse(injected, monkeypatch) -> None:
    """判失敗**不等於**丟掉已經解析成功的資料：壞的來源寫 0 列，好的來源照常 UPSERT。

    這條釘的是取捨本身。把整場的寫入一起放棄會讓「scoreboard 壞掉」連帶弄丟同一場
    完好的 livelog——那是拿資料去換一個比較整齊的語意，不划算；冪等 UPSERT 讓下次
    重抓自然收斂，先寫進去沒有代價。
    """
    upserts: list[tuple[str, int]] = []
    injected([], body=json.dumps({
        "ScoreboardJson": "{broken",
        "LiveLogJson": json.dumps([{"MainEventNo": "0001", "InningSeq": 1}]),
        "BattingJson": "[]", "PitchingJson": "[]",
    }))
    monkeypatch.setattr(cpbl_gamelog, "_upsert",
                        lambda table, _c, _pk, rows: upserts.append((table, len(rows))) or len(rows))

    with pytest.raises(cpbl_gamelog.GamelogScrapeIncomplete):
        cpbl_gamelog.scrape_gamelogs(2026, [188], "D", delay=0)

    written = dict(upserts)
    assert written["game_scoreboard"] == 0, "壞掉的來源不得硬湊出列"
    assert written["game_livelog"] == 1, "同一場解析成功的來源仍要寫進去"


def test_broken_box_json_is_a_counted_failure_not_an_uncaught_crash(injected) -> None:
    """`BattingJson`／`PitchingJson` 也必須納入逐場保護（R1-02，同一輪查核）。

    第一版把這兩行留在逐場 `try` 之外：`PitchingJson='{broken'` 會拋
    `JSONDecodeError` 炸掉整批，後面每一場一場都不會抓，且對帳行與
    `GamelogScrapeIncomplete` 都不會產生。查核裁定逐字：「它違反 Q3：單場失敗仍會擋
    整天同步。」——因為每日鏈拿到的是未知例外（exit 1）而不是 69。

    故本測試同時釘住兩件事：不得逸出 `JSONDecodeError`，且該場要計進失敗、
    **後續場次照抓**（`allow_partial` 下 189 仍要成功）。
    """
    broken = json.dumps({
        "ScoreboardJson": "[]", "LiveLogJson": "[]",
        "BattingJson": "[]", "PitchingJson": "{broken",
    })
    injected([], body=broken)

    out = cpbl_gamelog.scrape_gamelogs(2026, [188], "D", delay=0, allow_partial=True)

    assert out["failures"] == [{"sno": 188, "error_code": "invalid_source_json"}]
    assert out["games"] == 0 and out["target"] == 1


# --------------------------------------- 1b. 迴圈體的構造性保證（形狀，不是實例）

# 「合法 JSON、內容形狀不對」的 payload。這些**不是**要窮舉壞法——窮舉是開放集合，
# 同族已經失守四次（主路徑、查核 R1 兩條、PM 自審一條）。它們是**抽樣**：每個都落在
# 迴圈體的不同位置（第一個 row transform／最後一個 row transform），用來檢驗
# 「任何未預期例外都是那一場失敗」這條構造性保證，而不是檢驗個別型別檢查。
_MALFORMED_PAYLOADS = {
    "scoreboard_ints": {"ScoreboardJson": "[1,2,3]", "LiveLogJson": "[]",
                        "BattingJson": "[]", "PitchingJson": "[]"},
    "scoreboard_strings": {"ScoreboardJson": '["abc"]', "LiveLogJson": "[]",
                           "BattingJson": "[]", "PitchingJson": "[]"},
    "livelog_nested_list": {"ScoreboardJson": "[]", "LiveLogJson": "[[]]",
                            "BattingJson": "[]", "PitchingJson": "[]"},
    "pitching_ints": {"ScoreboardJson": "[]", "LiveLogJson": "[]",
                      "BattingJson": "[]", "PitchingJson": "[1]"},
    "batting_ints": {"ScoreboardJson": "[]", "LiveLogJson": "[]",
                     "BattingJson": "[1]", "PitchingJson": "[]"},
}


@pytest.mark.parametrize("shape", sorted(_MALFORMED_PAYLOADS))
def test_wellformed_json_with_wrong_content_is_one_games_failure(injected, shape) -> None:
    """合法 JSON、合法 list、元素不是 dict —— 通過所有型別檢查，卻在 row transform
    的 `r.get(...)` 炸掉（PM 自審 2026-08-19 發現的第四條同族路徑）。

    症狀與 R1-02 完全相同：未捕捉例外逸出 ⇒ 整批中止、後續場次一場未抓、無對帳行、
    每日鏈拿到 exit 1 而不是 69。要求是**那一場失敗、後面照抓**。
    """
    injected([], body=json.dumps(_MALFORMED_PAYLOADS[shape]))

    out = cpbl_gamelog.scrape_gamelogs(2026, [188, 189], "D", delay=0, allow_partial=True)

    assert out["failed"] == [188, 189], "壞內容不得中止整批"
    assert out["target"] == out["games"] + len(out["failed"])
    assert {f["error_code"] for f in out["failures"]} == {"unexpected_error"}


def test_unexpected_exception_anywhere_in_the_loop_body_is_that_games_failure(
    injected, monkeypatch,
) -> None:
    """保證的是**區域**不是**位置**：把例外注在迴圈體尾端（快照寫入）而不是 row
    transform，結論必須一樣。

    這條與上一條的差別是刻意的——上一條證明已知的壞 payload 被接住，這條證明接住它們
    的不是某個型別檢查，而是整個迴圈體被包住了。
    """
    injected([])

    def _boom(*_args, **_kwargs):
        raise KeyError("injected failure at the tail of the loop body")

    monkeypatch.setattr(cpbl_gamelog, "record_box_pitching_revisions", _boom)

    out = cpbl_gamelog.scrape_gamelogs(2026, [188, 189], "D", delay=0, allow_partial=True)

    assert out["failed"] == [188, 189] and out["games"] == 0


def test_token_renewal_failure_stays_a_batch_failure(injected, monkeypatch) -> None:
    """迴圈內重取 token 失敗＝整批性失敗，**不得**被降級成單場失敗。

    428 之後會重取 token；若那次重取也失敗，代表官網／挑戰整個掛了，不是某一場的事。
    Q 裁定明確不放寬取 token 階段的硬失敗，故這裡必須是原例外往上拋，
    而不是 `GamelogScrapeIncomplete`。
    """
    injected([97], http_status=428)
    calls = {"n": 0}
    session = cpbl_gamelog  # noqa: F841

    class _TokenDiesOnRenewal:
        def page_html(self, _path, require=None) -> str:
            calls["n"] += 1
            if calls["n"] == 1:
                return '<input name="__RequestVerificationToken" value="replay-token">'
            return "<html>challenge</html>"

        def post(self, *_args, **_kwargs) -> tuple[int, str]:
            return 428, "challenge"

    monkeypatch.setattr("cpbl.ingest._browser.session", lambda: _TokenDiesOnRenewal())

    with pytest.raises(RuntimeError) as excinfo:
        cpbl_gamelog.scrape_gamelogs(2026, [97, 188], "D", delay=0, allow_partial=True)

    assert not isinstance(excinfo.value, cpbl_gamelog.GamelogScrapeIncomplete)
    assert "token" in str(excinfo.value)


def test_database_outage_is_a_batch_failure_not_a_pile_of_game_failures(
    injected, monkeypatch,
) -> None:
    """DB 連線層失敗（含連線池 timeout）必須原樣往上拋。

    若把它記成「每一場都失敗」，每日鏈會拿到 69 ⇒ **本機 DB 掛著卻照樣同步生產**，
    那是拿一個誠實的退出碼去換一個錯誤的下游動作。psycopg 的
    `OperationalError` 是驅動自己的分類（`PoolTimeout`／`PoolClosed` 都繼承它），
    不是我們列舉出來的症狀清單。
    """
    injected([])

    def _db_down(*_args, **_kwargs):
        raise psycopg.OperationalError("connection to server failed")

    monkeypatch.setattr(cpbl_gamelog, "_upsert", _db_down)

    with pytest.raises(psycopg.OperationalError):
        cpbl_gamelog.scrape_gamelogs(2026, [188, 189], "D", delay=0, allow_partial=True)


def test_row_level_database_error_is_only_that_games_failure(injected, monkeypatch) -> None:
    """負控制：資料造成的 DB 錯誤（DataError／IntegrityError）是那一列的問題，
    不是整庫的問題，故仍算單場失敗、後續照抓。這條與上一條的分界就是驅動的類別階層。"""
    injected([])

    def _bad_row(*_args, **_kwargs):
        raise psycopg.DataError("value too long for type character varying(8)")

    monkeypatch.setattr(cpbl_gamelog, "_upsert", _bad_row)

    out = cpbl_gamelog.scrape_gamelogs(2026, [188, 189], "D", delay=0, allow_partial=True)

    assert out["failed"] == [188, 189] and out["games"] == 0


# ----------------------------------------------------------------- 2. 失敗訊號


def test_any_failure_raises_when_caller_did_not_opt_in(injected) -> None:
    """預設即硬失敗——呼叫端什麼都不做時拿到的不能是靜默成功。"""
    injected(REPLAY_20260810_D_FAILED)
    snos = sorted(REPLAY_20260810_D_FAILED + REPLAY_20260810_D_OK)

    with pytest.raises(cpbl_gamelog.GamelogScrapeIncomplete) as excinfo:
        cpbl_gamelog.scrape_gamelogs(2026, snos, "D", delay=0)

    # 例外訊息本身就是對帳行：traceback 最後一行即可回答「幾分之幾、哪幾場」。
    message = str(excinfo.value)
    assert "target=39" in message and "ok=8" in message and "failed=31" in message
    assert excinfo.value.result["failed"] == list(REPLAY_20260810_D_FAILED)


def test_tolerance_is_keyword_only_and_defaults_to_off() -> None:
    """契約釘死：`allow_partial` 只能具名傳、預設 False。

    位置參數會讓「第 5 個位置剛好是個真值」變成意外容忍；預設 True 則等於沒改。
    """
    parameter = inspect.signature(cpbl_gamelog.scrape_gamelogs).parameters["allow_partial"]

    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is False


def test_token_failure_still_hard_fails_regardless_of_tolerance(monkeypatch) -> None:
    """取 token 階段失敗＝整批一場都沒抓（08-10 的 kind=A），`allow_partial` 不吃它。"""
    class _NoToken:
        def page_html(self, _path, require=None) -> str:
            return "<html>challenge</html>"

    monkeypatch.setattr("cpbl.ingest._browser.session", lambda: _NoToken())

    with pytest.raises(RuntimeError) as excinfo:
        cpbl_gamelog.scrape_gamelogs(2026, [188], "D", delay=0, allow_partial=True)

    assert not isinstance(excinfo.value, cpbl_gamelog.GamelogScrapeIncomplete)


# --------------------------------------------------- 3. 每日鏈：容忍後仍要有帳


def test_daily_chain_records_tolerated_gap_and_keeps_result(monkeypatch) -> None:
    monkeypatch.setattr(run_refresh_recent, "_GAMELOG_GAPS", [])
    result = {"kind_code": "D", "target": 3, "games": 2, "failed": [51],
              "failures": [{"sno": 51, "error_code": "request_error"}]}

    returned = run_refresh_recent._tolerate_gamelog_gap(result, "測試理由")

    assert returned is result
    assert run_refresh_recent._GAMELOG_GAPS[0]["failed"] == [51]
    assert run_refresh_recent._GAMELOG_GAPS[0]["why"] == "測試理由"


def test_daily_chain_note_lists_failed_snos_and_is_none_when_clean() -> None:
    assert run_refresh_recent._gamelog_gap_note([]) is None
    note = run_refresh_recent._gamelog_gap_note(
        [{"kind_code": "A", "failed": [7]}, {"kind_code": "D", "failed": [51, 97]}]
    )
    assert "3 場" in note and "[7]" in note and "[51, 97]" in note


def test_daily_chain_exits_69_after_finishing_every_other_step(monkeypatch) -> None:
    """端到端（`fast` 路徑）：補缺迴圈抓不到一場時——

    1. 後續步驟（PA build／分項重算／名稱同步）仍然全部跑完；
    2. refresh_log 記 ok=False 且 note 帶失敗場號；
    3. 程序以 69 退出（不是 0、也不是 1）。
    """
    calls: list[str] = []
    logged: dict = {}
    monkeypatch.setattr(run_refresh_recent, "_GAMELOG_GAPS", [])
    monkeypatch.setattr(run_refresh_recent.sys, "argv", ["cpbl-refresh-recent", "fast"])

    def _fake_scrape_gamelogs(year, snos, kind_code="A", delay=0.7, *, allow_partial=False):
        assert allow_partial is True, "每日鏈的呼叫端必須明示容忍，否則就地拋例外"
        calls.append(f"gamelog:{kind_code}")
        return {"kind_code": kind_code, "target": len(snos), "games": 0,
                "failed": list(snos), "failures": [{"sno": s, "error_code": "request_error"}
                                                   for s in snos]}

    for name, value in (
        ("migrate", lambda: None),
        ("scrape_games", lambda *a, **k: 0),
        ("scrape_all", lambda *a, **k: {}),
        ("scrape_standings", lambda *a, **k: 0),
        ("scrape_transactions", lambda *a, **k: 0),
        ("build_championships", lambda *a, **k: 0),
        ("scrape_game_details", lambda *a, **k: 0),
        ("build_splits", lambda *a, **k: {}),
        ("build_career", lambda *a, **k: 0),
        ("_sync_player_names", lambda: 0),
        ("_recent_counts", lambda *a, **k: []),
        ("_missing_gamelog_snos", lambda _year, kc: [51] if kc == "D" else []),
        ("scrape_gamelogs", _fake_scrape_gamelogs),
    ):
        monkeypatch.setattr(run_refresh_recent, name, value)

    def _fake_pa_build(*_a, **_k):
        calls.append("pa_build")
        return {"games": 0, "actions": {}, "build_states": {}, "errors": []}

    def _fake_log_refresh(_scope, _frm, _to, _total, _completed, detail, ok, note):
        logged.update(ok=ok, note=note, detail=detail)

    monkeypatch.setattr(run_refresh_recent, "_pa_build_step", _fake_pa_build)
    monkeypatch.setattr(run_refresh_recent, "_log_refresh", _fake_log_refresh)

    with pytest.raises(SystemExit) as excinfo:
        run_refresh_recent.main()

    assert excinfo.value.code == cpbl_gamelog.EXIT_INCOMPLETE_SCRAPE == 69
    assert "pa_build" in calls, "逐場失敗不得中止後續步驟"
    assert logged["ok"] is False
    assert "[51]" in logged["note"]
    assert logged["detail"]["gamelog_gaps"][0]["failed"] == [51]


def test_daily_chain_exits_zero_when_nothing_failed(monkeypatch) -> None:
    """負控制：同一條路徑在零失敗時必須正常結束（69 不是隨便亮的）。"""
    monkeypatch.setattr(run_refresh_recent, "_GAMELOG_GAPS", [])
    monkeypatch.setattr(run_refresh_recent.sys, "argv", ["cpbl-refresh-recent", "fast"])
    logged: dict = {}
    for name, value in (
        ("migrate", lambda: None),
        ("scrape_games", lambda *a, **k: 0),
        ("scrape_all", lambda *a, **k: {}),
        ("scrape_standings", lambda *a, **k: 0),
        ("scrape_transactions", lambda *a, **k: 0),
        ("build_championships", lambda *a, **k: 0),
        ("scrape_game_details", lambda *a, **k: 0),
        ("build_splits", lambda *a, **k: {}),
        ("build_career", lambda *a, **k: 0),
        ("_sync_player_names", lambda: 0),
        ("_recent_counts", lambda *a, **k: []),
        ("_missing_gamelog_snos", lambda _year, _kc: []),
        ("_pa_build_step", lambda *a, **k: {"games": 0, "actions": {}, "build_states": {},
                                            "errors": []}),
        ("_log_refresh", lambda *a, **k: logged.update(ok=k.get("ok"))),
    ):
        monkeypatch.setattr(run_refresh_recent, name, value)

    run_refresh_recent.main()   # 不得拋 SystemExit

    assert logged["ok"] is True


# ------------------------------------------- 4. scrape-daily.sh：69 仍要同步


def _run_daily(tmp_path: Path, *, uv_exit: int) -> tuple[subprocess.CompletedProcess[str], dict]:
    """跑 `scrape-daily.sh` 的**副本**，外部指令換成假樁（形狀沿用 test_scrape_daily.py）。

    `uv` 的退出碼＝`cpbl-refresh-recent` 的退出碼，正是本測試要注入的變因。
    """
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    fake_bin = tmp_path / "bin"
    scripts.mkdir(parents=True)
    fake_bin.mkdir()
    shutil.copy2(ROOT / "scripts" / "scrape-daily.sh", scripts / "scrape-daily.sh")
    shutil.copy2(ROOT / "scripts" / "refresh_status.py", scripts / "refresh_status.py")

    for name, body in (
        ("docker", "#!/bin/sh\nprintf 'cpbl-analytics-db-1\\n'\n"),
        ("uv", f"#!/bin/sh\nexit {uv_exit}\n"),
    ):
        path = fake_bin / name
        path.write_text(body, encoding="utf-8")
        path.chmod(0o755)
    sync_marker = tmp_path / "sync-ran"
    sync = scripts / "refresh-cpbl-prod.sh"
    sync.write_text(f"#!/bin/sh\n: > {sync_marker}\nexit 0\n", encoding="utf-8")
    sync.chmod(0o755)

    env = os.environ.copy()
    env.update({
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "REFRESH_TRIGGER": "manual",
        "REFRESH_LOCK_DIR": str(tmp_path / "refresh.lock"),
        "SYNC_PROD": "1",
    })
    result = subprocess.run(["/bin/bash", str(scripts / "scrape-daily.sh")],
                            cwd=repo, env=env, text=True, capture_output=True, check=False)
    status_path = repo / "logs" / "last-status.json"
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    status["_sync_ran"] = sync_marker.exists()
    return result, status


def test_partial_scrape_still_syncs_production_and_stays_nonzero(tmp_path: Path) -> None:
    """Q3 裁定＝甲-2：69 之下 SYNC 分支必須真的被走到（由假樁留下的檔案作證），
    同時整體退出碼仍非零、狀態檔仍記 failed——不擋下游 ≠ 假裝沒事。"""
    result, status = _run_daily(tmp_path, uv_exit=cpbl_gamelog.EXIT_INCOMPLETE_SCRAPE)

    assert status["_sync_ran"] is True
    assert status["sync_attempted"] is True and status["sync_ok"] is True
    assert result.returncode == cpbl_gamelog.EXIT_INCOMPLETE_SCRAPE
    assert status["state"] == "failed" and status["failed_phase"] == "scrape"
    assert status["exit_code"] == cpbl_gamelog.EXIT_INCOMPLETE_SCRAPE


def test_hard_scrape_failure_still_blocks_sync(tmp_path: Path) -> None:
    """負控制：放行的只有 69 這一個碼。硬失敗照舊不同步——若這條也綠，
    上一條證明的就不是「69 被特別放行」而是「什麼碼都放行」。

    ⚠️ 注入碼刻意用 9 而不是 1：實作過程中 `scrape-daily.sh` 曾因 `set -u` 撞到未初始化
    的變數而自己 `exit 1`，本測試若也用 1 就會在腳本壞掉時照樣變綠（實際發生過）。
    """
    result, status = _run_daily(tmp_path, uv_exit=9)

    assert status["_sync_ran"] is False
    assert status["sync_attempted"] is False
    assert result.returncode == 9
    assert "unbound variable" not in result.stderr


def test_shell_and_python_agree_on_the_partial_exit_code() -> None:
    """shell 讀不到 Python 常數，只能存字面複本——這裡機械比對，不靠人記得同步改。"""
    source = (ROOT / "scripts" / "scrape-daily.sh").read_text(encoding="utf-8")
    match = re.search(r'\[ "\$CODE" -eq (\d+) \]; \} && \[ "\$SYNC_ENABLED"', source)

    assert match, "找不到 scrape-daily.sh 放行同步的退出碼判斷（條件被改寫過？）"
    assert int(match.group(1)) == cpbl_gamelog.EXIT_INCOMPLETE_SCRAPE
