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


def test_upsert_writes_when_reconciled(monkeypatch: pytest.MonkeyPatch) -> None:
    """孿生斷言：對帳過就照常寫（否則上一條可能只是「永遠拒寫」）。"""
    written: list[list[tuple]] = []

    class _Cur:
        def executemany(self, _sql, rows):  # noqa: ANN001
            written.append(list(rows))

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def cursor(self):
            return _Cur()

    monkeypatch.setattr(cs, "_local_expectation", lambda *a, **k: (SCHEDULED, G2026))
    monkeypatch.setattr(cs, "conn", lambda: _Conn())
    assert cs.upsert_standings(_records(2026, 0, G2026)) == 6
    assert len(written) == 1 and len(written[0]) == 6


def test_upsert_rejects_mixed_year_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    """一批 records 混了兩個年份就無從對帳 → 拒寫。"""
    monkeypatch.setattr(cs, "_local_expectation", lambda *a, **k: (SCHEDULED, G2026))
    monkeypatch.setattr(cs, "conn", _no_db)
    with pytest.raises(cs.StandingsYearMismatch):
        cs.upsert_standings(_records(2026, 0, G2026) + _records(2025, 0, G2025))


# ══════════════════════════════════════════ scrape_standings 的兩種失敗 ═══════════


def test_scrape_propagates_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """對帳失敗必須外拋——不得被 per-SeasonCode 的 except 降級成 warning。"""
    monkeypatch.setattr(cs, "fetch_standings",
                        lambda year, sc, kind="A": _records(year, sc, G2026))
    monkeypatch.setattr(cs, "_local_expectation", lambda *a, **k: (SCHEDULED, G2024))
    monkeypatch.setattr(cs, "conn", _no_db)
    with pytest.raises(cs.StandingsYearMismatch):
        cs.scrape_standings(2024)


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
    assert cs.scrape_standings(2026) == {}


def test_scrape_verifies_even_when_response_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """空回應也要驗：本地有完成場卻拿到空表 → 拋，不得靜靜當成「0 隊」。"""
    monkeypatch.setattr(cs, "fetch_standings", lambda *a, **k: [])
    monkeypatch.setattr(cs, "_local_expectation", lambda *a, **k: (SCHEDULED, G2026))
    monkeypatch.setattr(cs, "conn", _no_db)
    with pytest.raises(cs.StandingsYearMismatch):
        cs.scrape_standings(2026)


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
    """`cpbl-scrape-standings <非當季年份>` 必須失敗——驗收條件的機器化版本。"""
    from cpbl.ingest import run_scrape_standings as cli

    monkeypatch.setattr(cli, "migrate", lambda: None)
    monkeypatch.setattr(cli, "scrape_standings", _raise_mismatch)
    monkeypatch.setattr("sys.argv", ["cpbl-scrape-standings", "2024"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 1


def test_cli_exits_zero_when_reconciled(monkeypatch: pytest.MonkeyPatch) -> None:
    """孿生斷言：對帳過就正常結束（否則上一條可能只是「永遠失敗」）。"""
    from cpbl.ingest import run_scrape_standings as cli

    monkeypatch.setattr(cli, "migrate", lambda: None)
    monkeypatch.setattr(cli, "scrape_standings", lambda year: {0: 6, 1: 6, 2: 6})
    monkeypatch.setattr("sys.argv", ["cpbl-scrape-standings", "2026"])
    cli.main()  # 不得拋 SystemExit


def _raise_mismatch(year: int, kind_code: str = "A"):
    raise cs.StandingsYearMismatch(f"{year} 對不上")
