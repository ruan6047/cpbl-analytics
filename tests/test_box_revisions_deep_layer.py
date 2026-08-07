"""DATA-BOX-REVISION-SNAPSHOT1 深度層（每週近 N 天重抓）測試。

Coordinator iteration 2：每日 refresh 只看 [昨天,今天] 2 天窗，一場比賽被抓過一次
後不會再被自動排程碰到，若官方在 2 天後才修正 ER 就永遠觀測不到。這裡測的是
獨立的深度重抓 CLI（`cpbl-refresh-box-deep`）與其查詢/接線邏輯——不改動每日窗。
"""

from __future__ import annotations

import pytest

from cpbl.ingest import run_refresh_box_deep as deep


def test_parser_defaults_to_current_year_kind_a_days_back_30() -> None:
    ns = deep._parser().parse_args([])
    assert (ns.year, ns.kind, ns.days_back, ns.delay) == (None, None, 30, 1.2)


def test_parser_accepts_year_kind_days_back_and_delay_override() -> None:
    ns = deep._parser().parse_args(["2026", "D", "14", "--delay", "2.0"])
    assert (ns.year, ns.kind, ns.days_back, ns.delay) == (2026, "D", 14, 2.0)


def test_parser_rejects_unknown_kind() -> None:
    with pytest.raises(SystemExit):
        deep._parser().parse_args(["2026", "Z"])


def test_main_wires_completed_snos_within_days_into_scrape_gamelogs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """驗證接線：main() 用 (year, kind, days_back) 查場次，再把場次餵給 scrape_gamelogs；
    預設 kind='A'、delay=1.2（比每日窗 0.7 更保守）。不觸網、不觸 DB（全部 monkeypatch）。
    """
    calls: dict = {}

    def fake_query(year, kind, days_back):
        calls["query"] = (year, kind, days_back)
        return [101, 102]

    def fake_scrape(year, snos, kind, delay):
        calls["scrape"] = (year, snos, kind, delay)
        return {"games": len(snos)}

    monkeypatch.setattr(deep, "migrate", lambda: None)
    monkeypatch.setattr(deep, "completed_snos_within_days", fake_query)
    monkeypatch.setattr(deep, "scrape_gamelogs", fake_scrape)

    import sys
    monkeypatch.setattr(sys, "argv", ["cpbl-refresh-box-deep", "2026", "D", "10"])
    deep.main()

    assert calls["query"] == (2026, "D", 10)
    assert calls["scrape"] == (2026, [101, 102], "D", 1.2)


def test_main_defaults_kind_to_a_when_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict = {}

    def fake_query(year, kind, days_back):
        calls["query"] = (year, kind, days_back)
        return []

    def fake_scrape(year, snos, kind, delay):
        calls["scrape"] = (year, snos, kind, delay)
        return {"games": 0}

    monkeypatch.setattr(deep, "migrate", lambda: None)
    monkeypatch.setattr(deep, "completed_snos_within_days", fake_query)
    monkeypatch.setattr(deep, "scrape_gamelogs", fake_scrape)

    import sys
    monkeypatch.setattr(sys, "argv", ["cpbl-refresh-box-deep", "2026"])
    deep.main()

    assert calls["query"][1] == "A"
    assert calls["scrape"][2] == "A"


# --------------------------- 需本機 DB：completed_snos_within_days ---------------------------


def test_completed_snos_within_days_is_monotonic_subset_of_full_season(db) -> None:
    """近 N 天窗必須是全季完成場的子集，且窗越大涵蓋越多（唯讀查詢，不寫入不需清理）。"""
    from cpbl.ingest.cpbl_gamelog import completed_snos, completed_snos_within_days

    year, kind = 2026, "A"
    season_all = set(completed_snos(year, kind))
    if not season_all:
        pytest.skip("本機 DB 這個 year/kind 無完成場資料，無法驗證子集關係")

    narrow = set(completed_snos_within_days(year, kind, 3))
    wide = set(completed_snos_within_days(year, kind, 3650))  # 遠大於球季長度＝視同全season

    assert narrow <= wide <= season_all
    assert wide == season_all  # 10 年窗涵蓋整個 2026 season（season 不可能跨年）


@pytest.fixture()
def db():
    try:
        from cpbl.db import conn
        with conn() as c:
            c.execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001 — 無 DB 時 skip（CI 無 Postgres）
        pytest.skip(f"需本機 DB：{exc}")
    yield conn


def test_module_does_not_import_from_frozen_refresh_recent() -> None:
    """架構邊界：深度層是獨立 CLI，不掛在 run_refresh_recent.py 的執行路徑上
    （G4 觀測凍結、且卡面要求「深度層與每日窗分開，不要把每日窗撐大」）。

    只檢查實際 import 依賴（模組頂層 `import` 語句的來源），docstring 裡提到
    run_refresh_recent 這個名字純屬說明脈絡，不代表有程式碼依賴。
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(deep))
    imported_from = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert "cpbl.ingest.run_refresh_recent" not in imported_from
