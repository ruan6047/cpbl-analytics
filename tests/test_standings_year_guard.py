"""官方戰績爬蟲的年份對帳守衛（DATA-STANDINGS-YEAR-IGNORED1）。

缺陷：`www.cpbl.com.tw/standings/seasonaction` **忽略 `Year` 參數恆回當季**（2026-08-20
實證：`Year=2025` 與 `Year=2024` 回一字不差的 2026 當季數字），而回應的 16 個 cell 全是
隊名與數字、**沒有任何欄位帶年份**。舊版把請求的 `year` 直接蓋章寫入，於是
`cpbl.team_standings` 的 `year=2025` 12 列裝的是 2026 期中數字。

守衛：寫入前把回應的逐隊 `(g, w, t, l)` 與本地 `cpbl.games` 推導的該年戰績對帳，
不符即拒寫並拋 `StandingsYearMismatch`。

⚠️ 本檔的核心是**雙向**變異檢驗：光證明「當季會過」不算數——一個永遠不會紅的檢查
和沒有檢查是同一回事。所以每一個「通過」的斷言都配一個「必須失敗」的孿生斷言，
且golden 值取自真實資料（2024／2025／2026 由本地 `cpbl.games` 推導）。
"""

from __future__ import annotations

import logging
import pathlib

import pytest

from cpbl.ingest import cpbl_standings as cs

# ── 真實 golden 值（2026-08-20 由本地 cpbl.games 推導，kind_code='A'）──────────────
# ⭐ 2024 與 2025 每隊都是 120 場：這正是「只比 g 沒有鑑別力」的實例，
#    兩個都已完賽的球季 g 完全相同，只有 w/t/l 分得開。
G2024 = {"AAA011": (120, 58, 0, 62), "ACN011": (120, 70, 0, 50), "ADD011": (120, 66, 1, 53),
         "AEO011": (120, 53, 1, 66), "AJL011": (120, 62, 1, 57), "AKP011": (120, 49, 1, 70)}
G2025 = {"AAA011": (120, 55, 1, 64), "ACN011": (120, 70, 0, 50), "ADD011": (120, 66, 0, 54),
         "AEO011": (120, 46, 0, 74), "AJL011": (120, 62, 1, 57), "AKP011": (120, 59, 2, 59)}
# 2026 期中（sc=0 全年），即官網「當季」會回給我們的那一批
G2026 = {"AAA011": (88, 55, 0, 33), "ACN011": (87, 34, 2, 51), "ADD011": (88, 43, 1, 44),
         "AEO011": (87, 46, 0, 41), "AJL011": (87, 39, 2, 46), "AKP011": (89, 43, 1, 45)}
SCHEDULED = 720  # 6 隊 × 120 場（隊×場列數）


def _records(year: int, season_code: int, observed: dict[str, tuple[int, int, int, int]],
             kind_code: str = "A") -> list[tuple]:
    """組出與 `fetch_standings` 同形狀的 records（欄位順序＝ `_COLS`）。"""
    out = []
    for rank, (team, (g, w, t, l)) in enumerate(sorted(observed.items()), 1):
        out.append((year, kind_code, season_code, team, team, rank, g, w, t, l,
                    0.5, 0.0, None, None, None, None, None, "{}"))
    return out


# ══════════════════════════════════════════ 純函式對帳：雙向變異檢驗 ══════════════


def test_current_season_passes() -> None:
    """當季：回應＝本地推導 → 通過且回報「有資料可寫」。"""
    assert cs.check_year_consistency(2026, 0, G2026, SCHEDULED, G2026) is True


def test_past_year_request_receiving_current_season_is_rejected() -> None:
    """⭐ 核心變異檢驗：請求 2024、官網回當季(2026) → 必須拒寫。

    這正是 `cpbl-scrape-standings 2024` 會走到的路徑。
    """
    with pytest.raises(cs.StandingsYearMismatch) as e:
        cs.check_year_consistency(2024, 0, G2026, SCHEDULED, G2024)
    assert "2024" in str(e.value)


def test_2025_request_receiving_current_season_is_rejected() -> None:
    """實際造成污染的那一次（請求 2025 拿到 2026）必須被擋下。"""
    with pytest.raises(cs.StandingsYearMismatch):
        cs.check_year_consistency(2025, 0, G2026, SCHEDULED, G2025)


def test_g_alone_cannot_discriminate_two_finished_seasons() -> None:
    """⭐ 判準為何採 (g,w,t,l) 而非只用 g：2024 與 2025 的 g 完全相同。

    這個測試同時是設計理由的可執行證據——若有人把判準退回「只比 g」，
    前半段的斷言會讓他看見那樣完全分不出這兩年。
    """
    assert {k: v[0] for k, v in G2024.items()} == {k: v[0] for k, v in G2025.items()}
    with pytest.raises(cs.StandingsYearMismatch):
        cs.check_year_consistency(2024, 0, G2025, SCHEDULED, G2024)


def test_no_local_schedule_fails_closed() -> None:
    """本地沒有該年賽程 → 沒有東西可對帳 → 拒寫（不得因為「沒有反例」而放行）。

    這條擋掉的是「季前所有隊 g 都是 0，對一個我們沒有賽程的年份恆真通過」那種
    構造上不會失敗的檢查。
    """
    with pytest.raises(cs.StandingsYearMismatch) as e:
        cs.check_year_consistency(2030, 0, {}, 0, {})
    assert "沒有這一年的賽程" in str(e.value)


def test_empty_response_with_local_completed_games_is_rejected() -> None:
    """官網回空、但本地已有完成場 → 異常，拒寫。"""
    with pytest.raises(cs.StandingsYearMismatch):
        cs.check_year_consistency(2024, 0, {}, SCHEDULED, G2024)


def test_empty_response_before_any_game_is_not_an_error() -> None:
    """季前／下半季未開打：官網回空、本地也還沒有完成場 → 不是錯誤，但也不寫。"""
    zeros = dict.fromkeys(G2026, (0, 0, 0, 0))
    assert cs.check_year_consistency(2027, 2, {}, 360, zeros) is False


def test_team_set_mismatch_is_rejected() -> None:
    """回應少一隊／多一隊（不同年代的球隊組成）→ 拒寫。"""
    partial = {k: v for k, v in G2026.items() if k != "AKP011"}
    with pytest.raises(cs.StandingsYearMismatch) as e:
        cs.check_year_consistency(2026, 0, partial, SCHEDULED, G2026)
    assert "球隊集合" in str(e.value)


def test_single_game_drift_is_rejected() -> None:
    """一場之差也拒寫：守衛是嚴格相等，不留「差不多就好」的縫。"""
    drifted = dict(G2026)
    drifted["AAA011"] = (89, 56, 0, 33)
    with pytest.raises(cs.StandingsYearMismatch):
        cs.check_year_consistency(2026, 0, drifted, SCHEDULED, G2026)


# ══════════════════════════════════════════ 寫入邊界：拒寫而非寫後告警 ═════════════


def _no_db(*_a, **_k):  # pragma: no cover - 只在守衛失效時才會被呼叫
    raise AssertionError("守衛失效：對帳沒過卻仍然開了連線要寫入")


def test_upsert_refuses_to_write_on_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """`upsert_standings` 自己就會擋——任何取得 records 的路徑都繞不過。"""
    monkeypatch.setattr(cs, "_local_expectation", lambda *a, **k: (SCHEDULED, G2024))
    monkeypatch.setattr(cs, "conn", _no_db)
    with pytest.raises(cs.StandingsYearMismatch):
        cs.upsert_standings(_records(2024, 0, G2026))


class _FakeConn:
    """記錄 executemany 收到的列；用來斷言「有沒有真的寫下去」。"""

    def __init__(self, sink: list[list[tuple]]) -> None:
        self._sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def cursor(self):
        return self

    def executemany(self, _sql, rows):  # noqa: ANN001
        self._sink.append(list(rows))


def test_upsert_writes_when_reconciled(monkeypatch: pytest.MonkeyPatch) -> None:
    """孿生斷言：對帳過就照常寫（否則上一條可能只是「永遠拒寫」）。"""
    written: list[list[tuple]] = []
    monkeypatch.setattr(cs, "_local_expectation", lambda *a, **k: (SCHEDULED, G2026))
    monkeypatch.setattr(cs, "conn", lambda: _FakeConn(written))
    assert cs.upsert_standings(_records(2026, 0, G2026)) == 6
    assert len(written) == 1 and len(written[0]) == 6


def test_upsert_rejects_mixed_year_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    """一批 records 混了兩個年份就無從對帳 → 拒寫。"""
    monkeypatch.setattr(cs, "_local_expectation", lambda *a, **k: (SCHEDULED, G2026))
    monkeypatch.setattr(cs, "conn", _no_db)
    with pytest.raises(cs.StandingsYearMismatch):
        cs.upsert_standings(_records(2026, 0, G2026) + _records(2025, 0, G2025))


# ══════════════════════════════════════════ scrape_standings 的兩種失敗 ═══════════


def test_scrape_records_mismatch_without_aborting(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    """⭐ 岔路 1 裁定：對帳失敗**不連坐**（不外拋），但**必須看得見**。

    看得見的三個面：拒寫（`out` 不含該 sc）、`_FAILURES` 進帳、`log.error`（不是 warning）。
    ⚠️ 只驗「沒拋」是不夠的——那正好是被裁定否決的「降級成沒人讀的 warning」。
    """
    monkeypatch.setattr(cs, "fetch_standings",
                        lambda year, sc, kind="A": _records(year, sc, G2026))
    monkeypatch.setattr(cs, "_local_expectation", lambda *a, **k: (SCHEDULED, G2024))
    monkeypatch.setattr(cs, "conn", _no_db)
    with caplog.at_level(logging.DEBUG, logger="cpbl.standings"):
        assert cs.scrape_standings(2024) == {}          # 一列都沒寫
    failures = cs.standings_failures()
    assert [f["season_code"] for f in failures] == [0, 1, 2]
    assert {f["kind"] for f in failures} == {"year_mismatch"}
    levels = {r.levelno for r in caplog.records if "對帳失敗" in r.getMessage()}
    assert levels == {logging.ERROR}, f"對帳失敗必須是 ERROR，實際 {levels}"


def test_scrape_clears_the_ledger_between_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """一次執行一份帳：上一輪的失敗不得被讀成這一輪的。"""
    monkeypatch.setattr(cs, "fetch_standings",
                        lambda year, sc, kind="A": _records(year, sc, G2026))
    monkeypatch.setattr(cs, "_local_expectation", lambda *a, **k: (SCHEDULED, G2024))
    monkeypatch.setattr(cs, "conn", _no_db)
    cs.scrape_standings(2024)
    assert cs.standings_failures()
    monkeypatch.setattr(cs, "_local_expectation", lambda *a, **k: (SCHEDULED, G2026))
    monkeypatch.setattr(cs, "conn", lambda: _FakeConn([]))
    assert cs.scrape_standings(2026) == {0: 6, 1: 6, 2: 6}
    assert cs.standings_failures() == []


def test_reset_clears_a_stale_ledger() -> None:
    """替身取代 scrape 時沒人清帳——呼叫端要能自己清（每日鏈就是這樣用）。"""
    cs._FAILURES.append({"season_code": 0, "kind": "year_mismatch", "error": "舊帳"})
    cs.reset_standings_failures()
    assert cs.standings_failures() == []


def test_scrape_still_tolerates_transient_fetch_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    """抓取失敗（token/428/逾時）＝什麼都沒拿到，不會寫錯資料 → 維持略過該 SeasonCode。

    這條把「兩種失敗不同命」釘死：若有人把守衛做成「全部例外都外拋」，
    每日鏈會被反爬偶發打斷，那是本卡射程外的行為退化。
    """
    def _boom(*_a, **_k):
        raise RuntimeError("standings HTTP 428（反爬挑戰未過？）")

    monkeypatch.setattr(cs, "fetch_standings", _boom)
    monkeypatch.setattr(cs, "conn", _no_db)
    with caplog.at_level(logging.DEBUG, logger="cpbl.standings"):
        assert cs.scrape_standings(2026) == {}
    assert {f["kind"] for f in cs.standings_failures()} == {"fetch"}
    levels = {r.levelno for r in caplog.records if "略過" in r.getMessage()}
    assert levels == {logging.WARNING}, "抓取失敗＝什麼都沒拿到，不該與對帳失敗同級"


def test_scrape_verifies_even_when_response_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """⭐ 岔路 2 裁定：本地有完成場卻拿到空表＝硬失敗，不得靜靜當成「0 隊」。

    但依岔路 1，硬失敗走的是進帳而不是外拋。
    """
    monkeypatch.setattr(cs, "fetch_standings", lambda *a, **k: [])
    monkeypatch.setattr(cs, "_local_expectation", lambda *a, **k: (SCHEDULED, G2026))
    monkeypatch.setattr(cs, "conn", _no_db)
    assert cs.scrape_standings(2026) == {}
    assert [f["kind"] for f in cs.standings_failures()] == ["year_mismatch"] * 3


# ══════════════════════════════════════════ 真實 DB：判準本身站不站得住 ═══════════


def _db_expectation(year: int, season_code: int):
    try:
        return cs._local_expectation(year, season_code, "A")
    except Exception as e:  # noqa: BLE001 — 無 DB 環境（CI）直接 skip
        pytest.skip(f"無本機 DB，略過真實資料對帳：{e}")


@pytest.mark.parametrize("season_code", [0, 1, 2])
def test_real_db_current_season_reconciles(season_code: int) -> None:
    """真實資料：本地推導的 2026 各半季戰績，餵回守衛必須通過。"""
    scheduled, expected = _db_expectation(2026, season_code)
    if not expected or all(v == (0, 0, 0, 0) for v in expected.values()):
        pytest.skip("本機 DB 沒有 2026 完成場")
    assert cs.check_year_consistency(2026, season_code, expected, scheduled, expected) is True


@pytest.mark.parametrize("season_code", [0, 1, 2])
def test_real_db_rejects_current_season_stamped_as_2024(season_code: int) -> None:
    """孿生變異檢驗（真實資料）：把 2026 的數字蓋章成 2024 → 必須被擋。"""
    _, observed = _db_expectation(2026, season_code)
    scheduled, expected = _db_expectation(2024, season_code)
    if not observed or not expected:
        pytest.skip("本機 DB 缺 2024 或 2026 資料")
    with pytest.raises(cs.StandingsYearMismatch):
        cs.check_year_consistency(2024, season_code, observed, scheduled, expected)


# ══════════════════════════════════════════ CLI：對帳失敗必須非 0 退出 ════════════


def test_cli_exits_nonzero_on_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """`cpbl-scrape-standings <非當季年份>` 必須以非 0 退出——驗收條件的機器化版本。

    ⚠️ 退出碼是唯一不依賴「有人讀 log」的訊號；裁定要求不連坐每日鏈，但沒有放寬這一條。
    """
    from cpbl.ingest import run_scrape_standings as cli

    monkeypatch.setattr(cli, "migrate", lambda: None)
    monkeypatch.setattr(cs, "fetch_standings",
                        lambda year, sc, kind="A": _records(year, sc, G2026))
    monkeypatch.setattr(cs, "_local_expectation", lambda *a, **k: (SCHEDULED, G2024))
    monkeypatch.setattr(cs, "conn", _no_db)
    monkeypatch.setattr("sys.argv", ["cpbl-scrape-standings", "2024"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 1


def test_cli_exits_zero_when_reconciled(monkeypatch: pytest.MonkeyPatch) -> None:
    """孿生斷言：對帳過就正常結束（否則上一條可能只是「永遠失敗」）。"""
    from cpbl.ingest import run_scrape_standings as cli

    monkeypatch.setattr(cli, "migrate", lambda: None)
    monkeypatch.setattr(cs, "fetch_standings",
                        lambda year, sc, kind="A": _records(year, sc, G2026))
    monkeypatch.setattr(cs, "_local_expectation", lambda *a, **k: (SCHEDULED, G2026))
    monkeypatch.setattr(cs, "conn", lambda: _FakeConn([]))
    monkeypatch.setattr("sys.argv", ["cpbl-scrape-standings", "2026"])
    cli.main()  # 不得拋 SystemExit


def test_cli_history_flag_routes_to_the_history_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """`--history` 必須真的改走 history 路徑，不是只多一個沒接線的旗標。"""
    from cpbl.ingest import run_scrape_standings as cli

    called: list[str] = []
    monkeypatch.setattr(cli, "migrate", lambda: None)
    monkeypatch.setattr(cli, "scrape_standings", lambda y: called.append("season") or {})
    monkeypatch.setattr(cli, "scrape_history_standings", lambda y: called.append("history") or {})
    monkeypatch.setattr(cli, "standings_failures", list)
    monkeypatch.setattr("sys.argv", ["cpbl-scrape-standings", "2025", "--history"])
    cli.main()
    assert called == ["history"]


# ══════════════════════════════════════ /standings/history（2025 補救來源）═══════

# 真實回應片段：2026-08-20 14:06 唯讀探查 `/standings/history` 預設渲染（Year=2025）的
# 「全年戰績」表，原樣保留只壓縮空白。⚠️ 刻意不手工精簡成 2、3 隊——手工樣本會缺欄位
# 而走到另一條路徑，那正是本專案踩過的坑（記憶 `verification-sample-must-be-a-passing-one`）。
_HISTORY_FULL_SEASON_2025 = (
    "<table><tbody><tr><th class=\"sticky\"><div class=\"sticky_wrap\"><div class=\"rank\">排名</"
    "div><div class=\"team-w-trophy\">球隊</div></div></th><th class=\"num\">出賽數</th><th class="
    "\"num\">勝-和-敗</th><th class=\"num\">勝率</th><th class=\"num\">勝差</th><th class=\"num\">統一7-EL"
    "EVEn獅</th><th class=\"num\">中信兄弟</th><th class=\"num\">樂天桃猿</th><th class=\"num\">台鋼雄鷹</th"
    "><th class=\"num\">味全龍</th><th class=\"num\">富邦悍將</th><th class=\"num\">主場戰績</th><th class"
    "=\"num\">客場戰績</th></tr><tr><td class=\"sticky\"><div class=\"sticky_wrap\"><div class=\"ran"
    "k\">1</div><div class=\"team-w-trophy\"><a href=\"/team?TeamNo=ACN011\">中信兄弟</a></div></d"
    "iv></td><td class=\"num\">120</td><td class=\"num\">70-0-50</td><td class=\"num\">0.583</t"
    "d><td class=\"num\">-</td><td class=\"num\">16-0-8</td><td class=\"num\">&nbsp;</td><td cl"
    "ass=\"num\">14-0-10</td><td class=\"num\">10-0-14</td><td class=\"num\">13-0-11</td><td cl"
    "ass=\"num\">17-0-7</td><td class=\"num\">36-0-24</td><td class=\"num\">34-0-26</td></tr><t"
    "r><td class=\"sticky\"><div class=\"sticky_wrap\"><div class=\"rank\">2</div><div class=\"t"
    "eam-w-trophy\"><a href=\"/team?TeamNo=ADD011\">統一7-ELEVEn獅</a></div></div></td><td clas"
    "s=\"num\">120</td><td class=\"num\">66-0-54</td><td class=\"num\">0.55</td><td class=\"num\""
    ">4</td><td class=\"num\">&nbsp;</td><td class=\"num\">8-0-16</td><td class=\"num\">12-0-12"
    "</td><td class=\"num\">15-0-9</td><td class=\"num\">14-0-10</td><td class=\"num\">17-0-7</"
    "td><td class=\"num\">35-0-25</td><td class=\"num\">31-0-29</td></tr><tr><td class=\"stick"
    "y\"><div class=\"sticky_wrap\"><div class=\"rank\">3</div><div class=\"team-w-trophy\"><a h"
    "ref=\"/team?TeamNo=AJL011\">樂天桃猿</a></div></div></td><td class=\"num\">120</td><td class"
    "=\"num\">62-1-57</td><td class=\"num\">0.521</td><td class=\"num\">7.5</td><td class=\"num\""
    ">12-0-12</td><td class=\"num\">10-0-14</td><td class=\"num\">&nbsp;</td><td class=\"num\">"
    "11-1-12</td><td class=\"num\">12-0-12</td><td class=\"num\">17-0-7</td><td class=\"num\">3"
    "3-1-26</td><td class=\"num\">29-0-31</td></tr><tr><td class=\"sticky\"><div class=\"stick"
    "y_wrap\"><div class=\"rank\">4</div><div class=\"team-w-trophy\"><a href=\"/team?TeamNo=AK"
    "P011\">台鋼雄鷹</a></div></div></td><td class=\"num\">120</td><td class=\"num\">59-2-59</td><"
    "td class=\"num\">0.5</td><td class=\"num\">10</td><td class=\"num\">9-0-15</td><td class=\""
    "num\">14-0-10</td><td class=\"num\">12-1-11</td><td class=\"num\">&nbsp;</td><td class=\"n"
    "um\">12-1-11</td><td class=\"num\">12-0-12</td><td class=\"num\">33-1-26</td><td class=\"n"
    "um\">26-1-33</td></tr><tr><td class=\"sticky\"><div class=\"sticky_wrap\"><div class=\"ran"
    "k\">5</div><div class=\"team-w-trophy\"><a href=\"/team?TeamNo=AAA011\">味全龍</a></div></di"
    "v></td><td class=\"num\">120</td><td class=\"num\">55-1-64</td><td class=\"num\">0.462</td"
    "><td class=\"num\">14.5</td><td class=\"num\">10-0-14</td><td class=\"num\">11-0-13</td><t"
    "d class=\"num\">12-0-12</td><td class=\"num\">11-1-12</td><td class=\"num\">&nbsp;</td><td"
    " class=\"num\">11-0-13</td><td class=\"num\">30-0-30</td><td class=\"num\">25-1-34</td></t"
    "r><tr><td class=\"sticky\"><div class=\"sticky_wrap\"><div class=\"rank\">6</div><div clas"
    "s=\"team-w-trophy\"><a href=\"/team?TeamNo=AEO011\">富邦悍將</a></div></div></td><td class=\""
    "num\">120</td><td class=\"num\">46-0-74</td><td class=\"num\">0.383</td><td class=\"num\">2"
    "4</td><td class=\"num\">7-0-17</td><td class=\"num\">7-0-17</td><td class=\"num\">7-0-17</"
    "td><td class=\"num\">12-0-12</td><td class=\"num\">13-0-11</td><td class=\"num\">&nbsp;</t"
    "d><td class=\"num\">28-0-32</td><td class=\"num\">18-0-42</td></tr></tbody></table>"
)

_HISTORY_HTML_2025 = "<!--上半季戰績--><table></table><!--下半季戰績--><table></table>" \
                     "<!--全年戰績-->" + _HISTORY_FULL_SEASON_2025

# 官方 2025 全年戰績 golden（與本地 cpbl.games 推導 18/18 相符，PM 已獨立複算）
OFFICIAL_2025_FULL = {"ACN011": (120, 70, 0, 50), "ADD011": (120, 66, 0, 54),
                       "AJL011": (120, 62, 1, 57), "AKP011": (120, 59, 2, 59),
                       "AAA011": (120, 55, 1, 64), "AEO011": (120, 46, 0, 74)}


def test_history_table_is_anchored_on_the_section_comment() -> None:
    """三張表用 HTML 註解錨定，不是用出現順序——順序是排版，改版會靜靜錯位。"""
    assert cs._history_table(_HISTORY_HTML_2025, "<!--全年戰績-->") is not None
    assert cs._history_table(_HISTORY_HTML_2025, "<!--季後賽戰績-->") is None


def test_history_parser_reads_the_real_response() -> None:
    """真實回應片段 → 逐隊 (g,w,t,l) 必須等於官方 golden。"""
    table = cs._history_table(_HISTORY_HTML_2025, "<!--全年戰績-->")
    records = cs._parse_history_table(table, 2025, "A", 0)
    got = {r[cs._IDX_TEAM]: (r[cs._IDX_G], r[cs._IDX_W], r[cs._IDX_T], r[cs._IDX_L])
            for r in records}
    assert got == OFFICIAL_2025_FULL


def test_history_parser_writes_null_for_the_three_missing_columns() -> None:
    """需求方裁定：`elim`／`streak`／`last10` 寫 NULL，不保留現值（錯值比缺值危險）。"""
    table = cs._history_table(_HISTORY_HTML_2025, "<!--全年戰績-->")
    for r in cs._parse_history_table(table, 2025, "A", 0):
        assert r[12] is None, "elim 必須是 NULL"
        assert r[15] is None, "streak 必須是 NULL"
        assert r[16] is None, "last10 必須是 NULL"
        assert r[13] and r[14], "主客場戰績本頁有，不該一併變 NULL"


def test_history_h2h_uses_the_header_order_not_a_fixed_constant() -> None:
    """H2H 欄序由表頭實抽：球隊數逐年不同（2022 只有 5 隊），寫死會整排錯位。"""
    import json
    table = cs._history_table(_HISTORY_HTML_2025, "<!--全年戰績-->")
    by_team = {r[cs._IDX_TEAM]: json.loads(r[17]) for r in cs._parse_history_table(table, 2025, "A", 0)}
    assert by_team["ACN011"]["ADD011"] == "16-0-8"   # 中信 vs 統一（表頭第一欄）
    assert "ACN011" not in by_team["ACN011"], "自己對自己那格是 &nbsp;，不得入 h2h"


def test_history_scrape_still_reconciles_before_writing(monkeypatch: pytest.MonkeyPatch) -> None:
    """⚠️ history 頁遵守 Year **不等於**豁免對帳：官網哪天改壞了照樣要拒寫。"""
    table = cs._history_table(_HISTORY_HTML_2025, "<!--全年戰績-->")
    records = cs._parse_history_table(table, 2025, "A", 0)
    monkeypatch.setattr(cs, "fetch_history_standings", lambda *a, **k: {0: records})
    monkeypatch.setattr(cs, "_local_expectation", lambda *a, **k: (SCHEDULED, G2026))  # 對不上
    monkeypatch.setattr(cs, "conn", _no_db)
    assert cs.scrape_history_standings(2025) == {}
    assert [f["kind"] for f in cs.standings_failures()] == ["year_mismatch"]


def test_history_scrape_writes_when_it_reconciles(monkeypatch: pytest.MonkeyPatch) -> None:
    """孿生斷言：對得上就寫，且失敗帳是空的。"""
    table = cs._history_table(_HISTORY_HTML_2025, "<!--全年戰績-->")
    records = cs._parse_history_table(table, 2025, "A", 0)
    written: list[list[tuple]] = []
    monkeypatch.setattr(cs, "fetch_history_standings", lambda *a, **k: {0: records})
    monkeypatch.setattr(cs, "_local_expectation", lambda *a, **k: (SCHEDULED, OFFICIAL_2025_FULL))
    monkeypatch.setattr(cs, "conn", lambda: _FakeConn(written))
    assert cs.scrape_history_standings(2025) == {0: 6}
    assert cs.standings_failures() == []
    assert len(written[0]) == 6


# ══════════════════════════════════ 每日鏈：看得見，但不連坐 ═══════════════════


def _stub_daily_chain(monkeypatch: pytest.MonkeyPatch, standings_result, failures,
                      calls: list[str], logged: dict) -> None:
    """把 run_refresh_recent 的每一步換成替身，只留下「戰績失敗怎麼傳遞」這條線。"""
    from cpbl.ingest import run_refresh_recent as rr

    monkeypatch.setattr(rr, "_GAMELOG_GAPS", [])
    monkeypatch.setattr(rr.sys, "argv", ["cpbl-refresh-recent", "fast"])
    for name, value in (
        ("migrate", lambda: None),
        ("scrape_games", lambda *a, **k: 0),
        ("scrape_all", lambda *a, **k: {}),
        ("scrape_standings", lambda *a, **k: standings_result),
        ("standings_failures", lambda: list(failures)),
        ("reset_standings_failures", lambda: None),
        ("scrape_transactions", lambda *a, **k: 0),
        ("build_championships", lambda *a, **k: 0),
        ("scrape_game_details", lambda *a, **k: 0),
        ("build_splits", lambda *a, **k: {}),
        ("build_career", lambda *a, **k: 0),
        ("_sync_player_names", lambda: 0),
        ("_recent_counts", lambda *a, **k: []),
        ("_missing_gamelog_snos", lambda _year, _kc: []),
        ("_pa_build_step", lambda *a, **k: calls.append("pa_build") or {
            "games": 0, "actions": {}, "build_states": {}, "errors": []}),
        ("_log_refresh", lambda _s, _f, _t, _tot, _c, detail, ok, note:
            logged.update(ok=ok, note=note, detail=detail)),
    ):
        monkeypatch.setattr(rr, name, value)


def test_daily_chain_reports_standings_failure_without_stopping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """⭐ 岔路 1 的每日鏈端：失敗要進 refresh_log 與退出碼，但**後續步驟照跑**。

    ⚠️ 「不連坐」與「看得見」是一組的，缺任何一半這個裁定就沒被實作到：
    只有不連坐＝生產靜默落後；只有看得見卻中止＝連坐無關的步驟。
    """
    from cpbl.ingest import cpbl_gamelog
    from cpbl.ingest import run_refresh_recent as rr

    calls: list[str] = []
    logged: dict = {}
    failures = [{"season_code": 0, "kind": "year_mismatch", "error": "對不上"}]
    _stub_daily_chain(monkeypatch, {1: 6, 2: 6}, failures, calls, logged)

    with pytest.raises(SystemExit) as e:
        rr.main()

    assert e.value.code == cpbl_gamelog.EXIT_INCOMPLETE_SCRAPE == 69
    assert "pa_build" in calls, "戰績對帳失敗不得中止後續步驟"
    assert logged["ok"] is False, "有 SeasonCode 沒寫進去就不是成功的刷新"
    assert "sc=0" in logged["note"] and "year_mismatch" in logged["note"]
    assert logged["detail"]["standings_failures"] == failures
    assert logged["detail"]["standings"] == {1: 6, 2: 6}


def test_daily_chain_exits_zero_when_standings_are_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """負控制：零失敗時必須正常結束、ok=True（69 不是隨便亮的）。"""
    from cpbl.ingest import run_refresh_recent as rr

    calls: list[str] = []
    logged: dict = {}
    _stub_daily_chain(monkeypatch, {0: 6, 1: 6, 2: 6}, [], calls, logged)

    rr.main()  # 不得拋 SystemExit

    assert logged["ok"] is True
    assert logged["detail"]["standings_failures"] == []


def test_history_sections_map_by_comment_not_by_document_order() -> None:
    """⚠️ 區塊 → season_code 的對應必須由註解決定。

    這條擋的是「改成照出現順序」這種**不會報錯、只會靜靜錯位**的退化：把真表放在
    最後、以及把真表放到最前（區塊順序打亂），兩種排法都必須得到同一個 season_code。
    """
    tail_first = cs.split_history_sections(_HISTORY_HTML_2025, 2025, "A")
    shuffled = ("<!--全年戰績-->" + _HISTORY_FULL_SEASON_2025
                + "<!--上半季戰績--><table></table><!--下半季戰績--><table></table>")
    head_first = cs.split_history_sections(shuffled, 2025, "A")
    for result in (tail_first, head_first):
        got = {r[cs._IDX_TEAM]: (r[cs._IDX_G], r[cs._IDX_W], r[cs._IDX_T], r[cs._IDX_L])
               for r in result[0]}
        assert got == OFFICIAL_2025_FULL, "全年那張表必須落在 season_code=0"
        assert result[1] == [] and result[2] == [], "兩個半季區塊在本樣本是空表"


def test_history_missing_section_fails_closed() -> None:
    """官網改版把註解拿掉 → 直接炸，不得靜靜少寫一個 season_code。"""
    with pytest.raises(RuntimeError, match="找不到區塊"):
        cs.split_history_sections("<!--全年戰績--><table></table>", 2025, "A")


# ═══════════════════════ R1-01：history 的寫入路徑限制在已驗證範圍 ══════════════
#
# 查核者的判定：`--history` 開了一個新的污染面。`NAME_CODE` 只認現役六隊，歷史年份的
# `team_name` 會退化、H2H 對手會被靜默省略，而 `(g,w,t,l)` 對帳**攔不住欄位品質問題**
# ——那四個數字對歷史年份也會對得上（2018–2024 實測零差異）。而 `/api/v1/standings`
# 又優先採用這張表。故限制必須落在**寫入路徑**，不能只擋 CLI。


def _history_records(year: int = 2025) -> list[tuple]:
    table = cs._history_table(_HISTORY_HTML_2025, "<!--全年戰績-->")
    return cs._parse_history_table(table, year, "A", 0)


def test_supported_scope_is_exactly_what_was_verified() -> None:
    """允許清單就是實測過的那一格；放寬它是決定，不是筆誤。"""
    assert cs.HISTORY_SUPPORTED == frozenset({(2025, "A")})


@pytest.mark.parametrize("year,kind", [(2024, "A"), (2013, "A"), (2026, "A"), (2025, "D")])
def test_parser_refuses_unverified_scope(year: int, kind: str) -> None:
    """⭐ 最深的一道：**所有** history records 都經過 parser，範圍外造不出任何一列。

    這條擋的正是「只擋 CLI」——任何 import 這個模組的呼叫端都繞不過。
    """
    table = cs._history_table(_HISTORY_HTML_2025, "<!--全年戰績-->")
    with pytest.raises(cs.HistoryScopeUnsupported):
        cs._parse_history_table(table, year, kind, 0)


def _block_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    """任何情況都不得從測試裡打到官網。

    ⚠️ 這不是防禦性裝飾：跑變異檢驗時把允許清單短路掉，這幾條測試就會一路走到
    `fetch_history_standings` 的真實 Playwright session——**守衛壞掉的那一刻，
    驗證守衛的測試自己會去爬官網**。實際發生過一次（M-B，本輪）。
    """
    def _no_session():  # pragma: no cover - 只有守衛失效時才會被呼叫
        raise AssertionError("測試不得開瀏覽器：守衛應該在碰到網路之前就擋下來")

    monkeypatch.setattr("cpbl.ingest._browser.session", _no_session)


def test_fetch_refuses_unverified_scope_before_touching_the_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不為一個必定被拒的請求去打官網（爬蟲紅線：每一次冷啟動都是成本）。"""
    _block_browser(monkeypatch)
    with pytest.raises(cs.HistoryScopeUnsupported):
        cs.fetch_history_standings(2013, "A")


def test_scrape_history_refuses_unverified_scope_into_the_ledger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI 那一層要拿得到失敗帳（→ 退出碼），而不是吃到一個未處理的例外。"""
    _block_browser(monkeypatch)
    monkeypatch.setattr(cs, "conn", _no_db)
    assert cs.scrape_history_standings(2024) == {}
    assert [f["kind"] for f in cs.standings_failures()] == ["scope_unsupported"]


def test_scrape_history_accepts_the_verified_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    """孿生斷言：2025/A 仍然走得通（否則上面幾條可能只是「永遠拒絕」）。"""
    written: list[list[tuple]] = []
    monkeypatch.setattr(cs, "fetch_history_standings", lambda *a, **k: {0: _history_records()})
    monkeypatch.setattr(cs, "_local_expectation", lambda *a, **k: (SCHEDULED, OFFICIAL_2025_FULL))
    monkeypatch.setattr(cs, "conn", lambda: _FakeConn(written))
    assert cs.scrape_history_standings(2025) == {0: 6}
    assert cs.standings_failures() == []


def test_cli_history_flag_cannot_bypass_the_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    """`--history` 帶未驗證年份 → 非 0 退出、一列未寫。"""
    from cpbl.ingest import run_scrape_standings as cli

    _block_browser(monkeypatch)
    monkeypatch.setattr(cli, "migrate", lambda: None)
    monkeypatch.setattr(cs, "conn", _no_db)
    monkeypatch.setattr("sys.argv", ["cpbl-scrape-standings", "2024", "--history"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 1


# ── 第二道：範圍內但身分解析不出來（官網改隊名／擴編）→ 拒寫，不靜默省略 ──


def test_unmappable_h2h_header_is_rejected_not_silently_dropped() -> None:
    """⚠️ 靜默省略會讓 h2h 少一個對手卻仍通過 (g,w,t,l) 對帳——數字對、內容缺。"""
    mangled = _HISTORY_FULL_SEASON_2025.replace(
        '<th class="num">樂天桃猿</th>', '<th class="num">LamiGo桃猿</th>', 1)
    with pytest.raises(cs.HistoryIdentityUnresolved, match="H2H 表頭"):
        cs._parse_history_table(mangled, 2025, "A", 0)


def test_unmappable_team_code_is_rejected_not_degraded() -> None:
    """舊版會退回「第一格文字去掉名次數字」，寫出**數字對、名字錯**的列。改成拒寫。"""
    mangled = _HISTORY_FULL_SEASON_2025.replace("TeamNo=ACN011", "TeamNo=AJK011", 1)
    with pytest.raises(cs.HistoryIdentityUnresolved, match="NAME_CODE"):
        cs._parse_history_table(mangled, 2025, "A", 0)


def test_identity_failure_lands_in_the_ledger(monkeypatch: pytest.MonkeyPatch) -> None:
    """身分解析失敗要與抓取失敗分開記帳，值班才知道該修哪一種。"""
    def _boom(*_a, **_k):
        raise cs.HistoryIdentityUnresolved("隊名對不上")

    monkeypatch.setattr(cs, "fetch_history_standings", _boom)
    monkeypatch.setattr(cs, "conn", _no_db)
    assert cs.scrape_history_standings(2025) == {}
    assert [f["kind"] for f in cs.standings_failures()] == ["identity_unresolved"]


# ═══════════════════════ R1-02：退出碼 69 的契約文字不得過期 ════════════════════


def test_exit_code_69_contract_names_both_sources() -> None:
    """69 現在有兩個來源，模組 docstring 必須兩個都講（R1-02）。

    讀的是 **import 進來的模組**的 docstring（`inspect.getdoc`），不是檔案文字——
    測的正是值班從 `pydoc`／原始碼頂端會看到的那段。

    ⚠️ 這條測的是**文件與行為一致**，不是文件存在：
    `test_daily_chain_reports_standings_failure_without_stopping` 已證行為確實會亮 69。

    ⚠️⚠️ **`scrape-daily.sh`（在 `scripts/` 下）的同一段文字已一併更新，但沒有機器守衛**：
    要在測試裡讀它就得引用它的路徑，而 `script_inventory` 對「字面」與「分段組裝」兩種
    形式都會計入 → 那份自動產生的清冊必須重新產生，而它不在本卡的資源宣告內。
    這是**已知缺口不是疏漏**，補法見交付報告。（連這行註解寫出完整路徑都會被計入。）
    """
    import inspect

    from cpbl.ingest import run_refresh_recent as rr

    doc = inspect.getdoc(rr) or ""
    start = doc.index("結束碼")
    region = doc[start:doc.index("uv run cpbl-refresh-recent", start)]
    assert "69" in region, "找錯區塊了"
    assert "gamelog" in region, "69 的說明應保留 gamelog 這個來源"
    assert "戰績" in region, "69 的說明未提到官方戰績對帳失敗這個來源"


def test_exit_code_69_contract_is_not_the_stale_wording() -> None:
    """孿生斷言：舊的「只代表 gamelog」措辭必須整檔消失，不只是被新句子稀釋。"""
    import inspect

    from cpbl.ingest import run_refresh_recent as rr

    source = pathlib.Path(inspect.getsourcefile(rr)).read_text(encoding="utf-8")
    for stale in ("逐場 gamelog 有失敗但其餘完成", "逐場 gamelog 有失敗、其餘步驟照常完成"):
        assert stale not in source, f"仍宣稱 69 只代表 gamelog 失敗（{stale}）"
