"""DEV-CLI-HELP-GUARD1 回歸測試：CLI 探索必須零副作用。

事故（2026-08-05 跨家族查核）：查核者為了看用法打 `cpbl-scrape-pitches --help`，
`--help` 被當成位置參數吞掉，直接對官方 stats 站開真實爬蟲並寫入 DB（+46 列）。

本檔鎖住三件事，全部**不觸網、不觸 DB**：

1. **`--help` / `-h` 零副作用**：對每個 ingest 入口，把所有對外副作用出口換成會拋
   `SideEffectReached` 的 stub 之後才呼叫 `main()`。若護欄失效、主流程真的跑起來，
   stub 會先被呼叫 → 測試炸掉，而不是真的送出請求。
2. **非法參數不執行主流程**：未知旗標 → `SystemExit(code != 0)`；必填參數缺漏同理。
3. **向後相容**：launchd 排程（`scripts/scrape-daily.sh`、`scripts/weekly-game-pitches.sh`、
   `scripts/refresh-cpbl-prod.sh`）與各模組 docstring 裡的既有指令形式，逐一驗證解析結果
   與改版前語意相同。這層是本卡「不得為了加護欄而弄壞排程」的紅線。

排除：`run_refresh_recent` 與 `cpbl_pitch_tracking` 由 INGEST-GAME-TM-REFACTOR1-G4
觀測凍結，本卡明文不改，故不納入斷言範圍（它們的現況記錄在
`docs/research/DEV-CLI-HELP-GUARD1/cli-help-audit.md`）。
"""

from __future__ import annotations

import importlib
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# G4 觀測凍結：本卡只盤點不修改。
FROZEN_MODULES = {
    "cpbl.ingest.run_refresh_recent",
    "cpbl.ingest.cpbl_pitch_tracking",
}

# 護欄本身沒有 I/O，封印它會把「護欄有生效」誤判成「主流程被觸發」。
UNSEALED_MODULES = {"cpbl.ingest._cli"}


class SideEffectReached(RuntimeError):
    """副作用 stub 被呼叫＝主流程真的跑起來了。"""


def _ingest_entries() -> list:
    scripts = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    params = []
    for script, target in sorted(scripts.items()):
        module, func = target.split(":")
        if module.startswith("cpbl.ingest.") and module not in FROZEN_MODULES:
            params.append(pytest.param(script, module, func, id=script))
    return params


INGEST_ENTRIES = _ingest_entries()


def test_entry_discovery_actually_found_the_ingest_clis() -> None:
    """守住探索邏輯本身：清單若因 pyproject 改格式而變空，下面的參數化會全部靜默跳過。"""
    ids = {p.id for p in INGEST_ENTRIES}
    assert len(ids) >= 25
    # 事故當事者與幾支排程實際會跑的入口必須在範圍內
    assert {"cpbl-scrape-pitches", "cpbl-scrape-game-pitches", "cpbl-scrape-games",
            "cpbl-scrape-stats", "cpbl-scrape-detail", "cpbl-scrape-fighting"} <= ids
    assert "cpbl-refresh-recent" not in ids  # G4 凍結，明文排除


def _seal(module, monkeypatch: pytest.MonkeyPatch) -> None:
    """把副作用出口全部換成會拋例外的 stub（monkeypatch 會自動還原）。"""
    def _stub(label: str):
        def _raise(*_a, **_kw):
            raise SideEffectReached(label)
        return _raise

    for name in dir(module):
        if name.startswith("__"):
            continue
        obj = getattr(module, name)
        owner = getattr(obj, "__module__", "") or ""
        if not callable(obj) or owner in UNSEALED_MODULES:
            continue
        if owner.startswith("cpbl.") and owner != module.__name__:
            monkeypatch.setattr(module, name, _stub(f"{owner}.{name}"))

    # 來源模組也封死，堵住函式內延遲 import
    import cpbl.db as _db
    for name in ("migrate", "conn", "pool"):
        monkeypatch.setattr(_db, name, _stub(f"cpbl.db.{name}"))

    # 最後一道保險：任何漏網的網路／子行程呼叫一律拋例外，不會真的送出去
    import socket
    monkeypatch.setattr(socket.socket, "connect", _stub("socket.connect"))
    monkeypatch.setattr(socket, "create_connection", _stub("socket.create_connection"))
    monkeypatch.setattr(subprocess, "run", _stub("subprocess.run"))
    monkeypatch.setattr(subprocess, "Popen", _stub("subprocess.Popen"))


@pytest.mark.parametrize("flag", ["--help", "-h"])
@pytest.mark.parametrize(("script", "module", "func"), INGEST_ENTRIES)
def test_help_exits_zero_with_no_side_effects(
    script: str, module: str, func: str, flag: str,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> None:
    mod = importlib.import_module(module)
    _seal(mod, monkeypatch)
    monkeypatch.setattr(sys, "argv", [script, flag])

    with pytest.raises(SystemExit) as exc:  # SideEffectReached 會直接讓測試失敗
        getattr(mod, func)()

    assert exc.value.code == 0, f"{script} {flag} 應以 0 退出"
    assert script in capsys.readouterr().out, f"{script} {flag} 應印出含 prog 名稱的 usage"


@pytest.mark.parametrize(("script", "module", "func"), INGEST_ENTRIES)
def test_unknown_flag_exits_nonzero_with_no_side_effects(
    script: str, module: str, func: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = importlib.import_module(module)
    _seal(mod, monkeypatch)
    monkeypatch.setattr(sys, "argv", [script, "--zzz-not-a-real-flag"])

    with pytest.raises(SystemExit) as exc:
        getattr(mod, func)()

    assert exc.value.code not in (0, None), f"{script} 收到未知旗標應以非零碼退出"


@pytest.mark.parametrize(("script", "module", "func"), [
    p for p in INGEST_ENTRIES
    if p.id in ("cpbl-anchor-career", "cpbl-backfill-season", "cpbl-live-game")
])
def test_missing_required_args_exit_nonzero(
    script: str, module: str, func: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """必填參數的入口：不帶參數要報 usage 並非零退出，不能落入預設值就開跑。"""
    mod = importlib.import_module(module)
    _seal(mod, monkeypatch)
    monkeypatch.setattr(sys, "argv", [script])

    with pytest.raises(SystemExit) as exc:
        getattr(mod, func)()

    assert exc.value.code not in (0, None)


# --------------------------------------------------------------- 向後相容
# 來源：各模組 docstring 的用法範例 + scripts/ 底下排程實際送出的參數。
# 期望值＝改版前 sys.argv 手寫解析算出來的值，逐項對齊。

LEGACY_POSITIONAL_FORMS = [
    # cpbl-scrape-games（refresh-cpbl-prod.sh:145 送 "$YEAR" "$YEAR"）
    ("cpbl.ingest.run_scrape", [], {"start_year": None, "end_year": None}),
    ("cpbl.ingest.run_scrape", ["2020", "2024"], {"start_year": 2020, "end_year": 2024}),
    ("cpbl.ingest.run_scrape", ["2026", "2026"], {"start_year": 2026, "end_year": 2026}),
    # cpbl-scrape-stats（refresh-cpbl-prod.sh:146 送 "$PREV" "$YEAR"）
    ("cpbl.ingest.run_scrape_stats", [], {"start_year": None, "end_year": None}),
    ("cpbl.ingest.run_scrape_stats", ["2025", "2026"], {"start_year": 2025, "end_year": 2026}),
    # cpbl-scrape-fighting（refresh-cpbl-prod.sh:152 送 9999 1.2 cur）
    ("cpbl.ingest.run_scrape_fighting", ["9999", "1.2", "cur"],
     {"year": 9999, "delay": 1.2, "scope": "cur"}),
    ("cpbl.ingest.run_scrape_fighting", ["2026"], {"year": 2026, "delay": 1.2, "scope": None}),
    ("cpbl.ingest.run_scrape_fighting", ["2026", "2.0"],
     {"year": 2026, "delay": 2.0, "scope": None}),
    ("cpbl.ingest.run_scrape_fighting", [], {"year": None, "delay": 1.2, "scope": None}),
    # cpbl-scrape-detail（refresh-cpbl-prod.sh:153 送 1.2）
    ("cpbl.ingest.run_scrape_detail", ["1.2"], {"delay": 1.2, "group": None}),
    ("cpbl.ingest.run_scrape_detail", ["2.0"], {"delay": 2.0, "group": None}),
    ("cpbl.ingest.run_scrape_detail", ["1.2", "pitchers"], {"delay": 1.2, "group": "pitchers"}),
    ("cpbl.ingest.run_scrape_detail", ["1.2", "batters"], {"delay": 1.2, "group": "batters"}),
    ("cpbl.ingest.run_scrape_detail", [], {"delay": 1.2, "group": None}),
    # cpbl-scrape-advanced
    ("cpbl.ingest.run_scrape_advanced", [], {"delay": 0.5, "kinds": "A"}),
    ("cpbl.ingest.run_scrape_advanced", ["0.8"], {"delay": 0.8, "kinds": "A"}),
    ("cpbl.ingest.run_scrape_advanced", ["0.5", "A,D"], {"delay": 0.5, "kinds": "A,D"}),
    # 單一年份型
    ("cpbl.ingest.run_scrape_gamelog", [], {"year": None}),
    ("cpbl.ingest.run_scrape_gamelog", ["2026"], {"year": 2026}),
    ("cpbl.ingest.run_scrape_roster", ["2026"], {"year": 2026}),
    ("cpbl.ingest.run_scrape_standings", ["2025"], {"year": 2025}),
    ("cpbl.ingest.run_scrape_coaches", ["2026"], {"year": 2026}),
    ("cpbl.ingest.run_backfill_season", ["2025"], {"year": 2025}),
    # cpbl-scrape-wiki / legends / field / bio
    ("cpbl.ingest.run_scrape_wiki", [], {"limit": None}),
    ("cpbl.ingest.run_scrape_wiki", ["30"], {"limit": 30}),
    ("cpbl.ingest.run_scrape_legends", [], {"delay": 1.2}),
    ("cpbl.ingest.run_scrape_legends", ["2.0"], {"delay": 2.0}),
    ("cpbl.ingest.run_scrape_field", [], {"venues": []}),
    ("cpbl.ingest.run_scrape_field", ["大巨蛋", "天母"], {"venues": ["大巨蛋", "天母"]}),
    ("cpbl.ingest.run_scrape_bio", [], {"scope": "current", "skip_done": False}),
    ("cpbl.ingest.run_scrape_bio", ["all"], {"scope": "all", "skip_done": False}),
    ("cpbl.ingest.run_scrape_bio", ["all", "--skip-done"], {"scope": "all", "skip_done": True}),
    ("cpbl.ingest.run_scrape_bio", ["--skip-done", "all"], {"scope": "all", "skip_done": True}),
    # 重算 / 驗證類
    ("cpbl.ingest.run_build_splits", [], {"year": None, "kinds": None}),
    ("cpbl.ingest.run_build_splits", ["2025"], {"year": 2025, "kinds": None}),
    ("cpbl.ingest.run_build_splits", ["2026", "A,D"], {"year": 2026, "kinds": "A,D"}),
    ("cpbl.ingest.run_check_coverage", [], {"year": None, "kind": "A"}),
    ("cpbl.ingest.run_check_coverage", ["2026", "A"], {"year": 2026, "kind": "A"}),
    ("cpbl.ingest.run_verify_splits", [], {"year": 2026, "kind": "A"}),
    ("cpbl.ingest.run_verify_splits", ["2026", "D"], {"year": 2026, "kind": "D"}),
    ("cpbl.ingest.run_anchor_career", ["2026", "/tmp/backup-csv"],
     {"season": 2026, "backup_csv_dir": "/tmp/backup-csv"}),
    ("cpbl.ingest.run_scrape_transactions", [], {"start_year": None, "end_year": None}),
    ("cpbl.ingest.run_scrape_transactions", ["2025", "2026"],
     {"start_year": 2025, "end_year": 2026}),
    ("cpbl.ingest.run_live_game", ["2026", "A", "186"],
     {"year": 2026, "kind": "A", "sno": 186, "dump": None}),
    ("cpbl.ingest.run_live_game", ["2026", "A", "186", "/tmp/g186.json"],
     {"year": 2026, "kind": "A", "sno": 186, "dump": "/tmp/g186.json"}),
]


@pytest.mark.parametrize(("module", "argv", "expected"), LEGACY_POSITIONAL_FORMS,
                         ids=[f"{m.rsplit('.', 1)[-1]}({' '.join(a)})"
                              for m, a, _ in LEGACY_POSITIONAL_FORMS])
def test_documented_invocations_still_parse(module: str, argv: list[str], expected: dict) -> None:
    ns = importlib.import_module(module)._parser().parse_args(argv)
    assert {k: getattr(ns, k) for k in expected} == expected


# 順序無關嗅探型入口：語意留在 `_parse_args`，故直接對它斷言。
SNIFFING_FORMS = [
    # cpbl-scrape-pitches（docstring 四種形式）
    ("cpbl.ingest.run_scrape_pitches", ["2026", "D"], (2026, "D", 1.0)),
    ("cpbl.ingest.run_scrape_pitches", ["2026", "A", "1.5"], (2026, "A", 1.5)),
    ("cpbl.ingest.run_scrape_pitches", ["2025", "E"], (2025, "E", 1.0)),
    ("cpbl.ingest.run_scrape_pitches", ["D", "2026"], (2026, "D", 1.0)),  # 順序無關
    # cpbl-scrape-game-pitches（weekly-game-pitches.sh:70 送 "$YEAR" "$KIND"）
    ("cpbl.ingest.run_scrape_game_pitches", ["2026", "A"], (2026, "A", [], None)),
    ("cpbl.ingest.run_scrape_game_pitches", ["2026", "D"], (2026, "D", [], None)),
    ("cpbl.ingest.run_scrape_game_pitches", ["2026", "A", "7"], (2026, "A", [], 7)),
    ("cpbl.ingest.run_scrape_game_pitches", ["2026", "A", "99", "100"], (2026, "A", [99, 100], None)),
]


@pytest.mark.parametrize(("module", "argv", "expected"), SNIFFING_FORMS,
                         ids=[f"{m.rsplit('.', 1)[-1]}({' '.join(a)})"
                              for m, a, _ in SNIFFING_FORMS])
def test_sniffing_parsers_preserve_semantics(module: str, argv: list[str], expected: tuple) -> None:
    mod = importlib.import_module(module)
    assert mod._parse_args(mod._parser().parse_args(argv).args) == expected


def test_scrape_pitches_rejects_unrecognised_token() -> None:
    """事故的核心：舊版把無法辨識的 token 靜默略過，`--help` 就是這樣被吞掉的。"""
    mod = importlib.import_module("cpbl.ingest.run_scrape_pitches")
    with pytest.raises(SystemExit) as exc:
        mod._parse_args(["zzz-not-a-real-value"])
    assert exc.value.code != 0


def test_shadow_game_tm_report_flag_and_positionals() -> None:
    mod = importlib.import_module("cpbl.ingest.run_shadow_game_tm")
    parser = mod._parser()

    ns = parser.parse_args(["--report"])
    assert mod._parse_args(ns.args, ns.report) == (True, 0, "A", 0)

    ns = parser.parse_args(["2026", "A", "5"])
    assert mod._parse_args(ns.args, ns.report) == (False, 2026, "A", 5)

    ns = parser.parse_args([])
    report_only, _, kind, window = mod._parse_args(ns.args, ns.report)
    assert (report_only, kind, window) == (False, "A", 3)


def test_scrape_transactions_rejects_half_given_range(monkeypatch: pytest.MonkeyPatch) -> None:
    """舊版單給一個年份會被靜默忽略而爬成當年——靜默吞參數正是本卡要消滅的模式。"""
    mod = importlib.import_module("cpbl.ingest.run_scrape_transactions")
    _seal(mod, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["cpbl-scrape-transactions", "2025"])
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code not in (0, None)


def test_ruff_excludes_ai_workflow_submodule() -> None:
    """`.ai-workflow` 是獨立 repo 的 submodule，掃進來會產生本 repo 無權修的假 findings。"""
    cfg = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    excluded = cfg["tool"]["ruff"].get("extend-exclude", []) + cfg["tool"]["ruff"].get("exclude", [])
    assert ".ai-workflow" in excluded
