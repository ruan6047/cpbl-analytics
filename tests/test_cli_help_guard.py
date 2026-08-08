"""DEV-CLI-HELP-GUARD1／GUARD2 回歸測試：CLI 探索必須零副作用。

事故（2026-08-05 跨家族查核）：查核者為了看用法打 `cpbl-scrape-pitches --help`，
`--help` 被當成位置參數吞掉，直接對官方 stats 站開真實爬蟲並寫入 DB（+46 列）。

涵蓋範圍：GUARD1 修 `cpbl.ingest.*`，GUARD2 補上 `cpbl.models.*` 與 `cpbl.features.*`
——後者被 `--help` 觸發的是重訓練／全量重建，代價比爬蟲更高。

本檔鎖住三件事，全部**不觸網、不觸 DB**：

1. **`--help` / `-h` 零副作用**：對每個入口，把所有對外副作用出口換成會拋
   `SideEffectReached` 的 stub 之後才呼叫 `main()`。若護欄失效、主流程真的跑起來，
   stub 會先被呼叫 → 測試炸掉，而不是真的送出請求。
2. **非法參數不執行主流程**：未知旗標 → `SystemExit(code != 0)`；必填參數缺漏同理。
3. **向後相容**：launchd 排程（`scripts/scrape-daily.sh`、`scripts/weekly-game-pitches.sh`、
   `scripts/refresh-cpbl-prod.sh`）與各模組 docstring 裡的既有指令形式，逐一驗證解析結果
   與改版前語意相同。這層是本卡「不得為了加護欄而弄壞排程」的紅線。

排除：`run_refresh_recent` 與 `cpbl_pitch_tracking` 由 #53 的 INGEST-GAME-TM-REFACTOR1-G4
Phase B 資源佔用，本卡明文不改，故不納入斷言範圍（它們的現況記錄在
`docs/research/DEV-CLI-HELP-GUARD1/cli-help-audit.md`）。
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# #53 的 G4 Phase B 資源佔用：本卡只盤點，不把 CLI 護欄改動併入逐球 writer。
FROZEN_MODULES = {
    "cpbl.ingest.run_refresh_recent",
    "cpbl.ingest.cpbl_pitch_tracking",
}

# 護欄本身沒有 I/O，封印它會把「護欄有生效」誤判成「主流程被觸發」。
UNSEALED_MODULES = {"cpbl.ingest._cli"}

# 硬封鎖的 I/O 出口：(import 名, 擁有者屬性路徑（空字串＝模組本身）, 屬性名)。
#
# ⚠️ 與 `docs/research/DEV-CLI-HELP-GUARD1/audit_cli_help.py` 的同名常數必須逐項一致，
# 由 `test_seal_surface_matches_audit_tool` 擋住漂移。
#
# psycopg 的連線入口有數個彼此獨立的符號——`psycopg.connect` **不是**
# `psycopg.Connection.connect`（實測 `is` 為 False），非同步版又是另外一個；pool 亦分
# 同步／非同步／null 四類。初版只封了 `psycopg.connect` 與同步 `ConnectionPool`，
# 於是 `psycopg.AsyncConnection.connect` 與 `AsyncConnectionPool` 是開的，
# 「探針碰不到 DB」不成立（查核 CLIHG1-R1-01）。
#
# ⚠️ **socket 層封鎖擋不住 psycopg**：實測（打 127.0.0.1:1 無人監聽的埠）在
# `socket.socket.connect` / `create_connection` / `getaddrinfo` 全封的情況下，
# `psycopg.connect` 與 `psycopg.AsyncConnection.connect` **仍照常發出連線**，回的是
# libpq 的 OperationalError 而非 stub 例外——連線由 libpq 在 C 層自己做，不經過
# Python socket 模組。psycopg 這幾個入口因此不是「多一層保險」，而是唯一擋得住 DB
# 連線的地方；漏掉 async 版就是真的會連出去。
IO_TARGETS = (
    ("socket", "socket", "connect"),
    ("socket", "", "create_connection"),
    ("socket", "", "getaddrinfo"),          # DNS 解析本身也是對外流量
    ("subprocess", "", "run"),
    ("subprocess", "", "Popen"),
    ("psycopg", "", "connect"),
    ("psycopg", "Connection", "connect"),
    ("psycopg", "AsyncConnection", "connect"),
    ("psycopg_pool", "", "ConnectionPool"),
    ("psycopg_pool", "", "AsyncConnectionPool"),
    ("psycopg_pool", "", "NullConnectionPool"),
    ("psycopg_pool", "", "AsyncNullConnectionPool"),
)


def _io_target_labels() -> tuple[str, ...]:
    return tuple(f"{m}.{o + '.' if o else ''}{a}" for m, o, a in IO_TARGETS)


def _io_target_owner(mod_name: str, owner_path: str):
    owner = importlib.import_module(mod_name)
    for part in filter(None, owner_path.split(".")):
        owner = getattr(owner, part)
    return owner


def _raw_attr(mod_name: str, owner_path: str, attr: str):
    """取屬性的**穩定身分**——`vars()` 而非 `getattr()`。

    `getattr(SomeClass, 'a_classmethod')` 每次都回傳新的 bound method，用 `is`
    比較無論封沒封都會「不相同」。本檔初版的正控制就是這樣寫成空斷言的，靠負控制
    腳本才抓到。`vars(owner)[attr]` 拿到的是底層描述子／函式本身，身分才穩定。

    有些屬性繼承自基底（`socket.socket.connect` 實際定義在 C 層 `_socket.socket`），
    自身 `vars()` 裡沒有，需往 MRO 找封印前的原值；封印後則會落在自身 `vars()`。
    """
    owner = _io_target_owner(mod_name, owner_path)
    if attr in vars(owner):
        return vars(owner)[attr]
    for base in getattr(owner, "__mro__", ())[1:]:
        if attr in vars(base):
            return vars(base)[attr]
    return getattr(owner, attr)


class SideEffectReached(RuntimeError):
    """副作用 stub 被呼叫＝主流程真的跑起來了。"""


# GUARD2 起涵蓋 models/ 與 features/ 入口，不再限於 ingest。
GUARDED_PACKAGES = ("cpbl.ingest.", "cpbl.models.", "cpbl.features.")

# macOS host 上 LightGBM 缺 `libomp` 無法 import（CLAUDE.md 既知限制，需容器內跑）。
# 這兩支的護欄改由**容器內**密封探針取證（DEV-CLI-HELP-GUARD2 交付報告附輸出）；
# 在有 libgomp 的環境（容器／Linux CI）本檔照常驗它們，不會跳過。
CONTAINER_ONLY_MODULES = {"cpbl.models.train", "cpbl.models.train_pitching"}


def _guarded_entries() -> list:
    scripts = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    params = []
    for script, target in sorted(scripts.items()):
        module, func = target.split(":")
        if module.startswith(GUARDED_PACKAGES) and module not in FROZEN_MODULES:
            params.append(pytest.param(script, module, func, id=script))
    return params


GUARDED_ENTRIES = _guarded_entries()


def _import_entry(module: str):
    """import 入口模組；只有列舉過的容器限定模組才允許以 skip 收場。"""
    try:
        return importlib.import_module(module)
    except Exception as exc:  # noqa: BLE001 — 什麼型別都要判斷是否屬於已知環境限制
        if module in CONTAINER_ONLY_MODULES:
            pytest.skip(f"{module} 在此環境無法 import（{type(exc).__name__}）——"
                        "LightGBM 缺 libomp，護欄由容器內密封探針取證")
        raise


def test_entry_discovery_actually_found_the_clis() -> None:
    """守住探索邏輯本身：清單若因 pyproject 改格式而變空，下面的參數化會全部靜默跳過。"""
    ids = {p.id for p in GUARDED_ENTRIES}
    assert len(ids) >= 33
    # 事故當事者、幾支排程實際會跑的入口，與 GUARD2 補的 models/features 入口
    assert {"cpbl-scrape-pitches", "cpbl-scrape-game-pitches", "cpbl-scrape-games",
            "cpbl-scrape-stats", "cpbl-scrape-detail", "cpbl-scrape-fighting",
            "cpbl-build-features", "cpbl-build-sabr", "cpbl-classify-pitches",
            "cpbl-train-outcome", "cpbl-train-outcome-simple", "cpbl-train-pa-sim",
            "cpbl-train", "cpbl-train-pitching"} <= ids
    assert "cpbl-refresh-recent" not in ids  # 仍有 CLI 副作用，且其 writer 由 #53 佔用


def test_only_declared_modules_are_unimportable_in_this_environment() -> None:
    """跳過必須是列舉的——新的無法 import 模組不得躲在 skip 後面靜默失去覆蓋。"""
    unimportable = set()
    for param in GUARDED_ENTRIES:
        module = param.values[1]
        try:
            importlib.import_module(module)
        except Exception:  # noqa: BLE001
            unimportable.add(module)
    assert unimportable <= CONTAINER_ONLY_MODULES, (
        f"未列舉的模組無法 import：{sorted(unimportable - CONTAINER_ONLY_MODULES)}")


def _seal(module, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """把副作用出口換成會拋例外的 stub（monkeypatch 自動還原）。回傳實際封住的 I/O 出口。"""
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

    # 最後一道保險：列舉的網路／DB／子行程出口一律拋例外，不會真的送出去。
    # 同步與非同步開口必須對齊——只封同步版等於留了一扇沒鎖的門。
    sealed: list[str] = []
    for mod_name, owner_path, attr in IO_TARGETS:
        label = f"{mod_name}.{owner_path + '.' if owner_path else ''}{attr}"
        try:
            owner = importlib.import_module(mod_name)
            for part in filter(None, owner_path.split(".")):
                owner = getattr(owner, part)
            getattr(owner, attr)  # 符號不存在就別假裝封住了
            monkeypatch.setattr(owner, attr, _stub(label))
        except (ImportError, AttributeError):
            continue
        sealed.append(label)
    return sealed


# ------------------------------------------------- 探針封鎖面本身（CLIHG1-R1-01）
# 上面每一條 `--help` 斷言的前提都是「主流程真的跑起來就會被 stub 攔下」。前提若破，
# 測試會從「證明護欄有效」退化成「證明什麼都沒發生」。以下直接驗證前提。

SEAL_SAMPLE_MODULE = "cpbl.ingest.run_scrape_pitches"  # 事故當事者，任一入口皆可
_DEAD_DSN = "postgresql://sealed.invalid/never-connects"


def test_seal_reports_every_declared_io_target_as_sealed(monkeypatch: pytest.MonkeyPatch) -> None:
    """漏封必須看得見：`_seal` 回報的清單要與宣告的出口逐項相符。"""
    mod = importlib.import_module(SEAL_SAMPLE_MODULE)
    assert _seal(mod, monkeypatch) == list(_io_target_labels())


def test_seal_actually_installs_a_stub_at_every_declared_io_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """正控制：每個宣告的出口都確實被換成 stub，不是「剛好沒被呼叫到」。

    身分比較走 `vars()`——`getattr` 對 classmethod 每次回傳新物件，用它做斷言等於
    沒斷言（見 `_raw_attr` docstring）。
    """
    before = {t: _raw_attr(*t) for t in IO_TARGETS}
    _seal(importlib.import_module(SEAL_SAMPLE_MODULE), monkeypatch)

    for target in IO_TARGETS:
        after = _raw_attr(*target)
        label = f"{target[0]}.{target[1] + '.' if target[1] else ''}{target[2]}"
        assert after is not before[target], f"{label} 未被替換"
        assert getattr(after, "__name__", None) == "_raise", f"{label} 換上的不是 stub"


def test_sealed_probe_blocks_async_psycopg_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    """走真正的 async/await 路徑：`await AsyncConnection.connect(...)` 必須被攔下。

    初版探針只封 `psycopg.connect` 與同步 `ConnectionPool`，這條路是通的——查核
    CLIHG1-R1-01 據此判定「物理上不可能碰 DB」的宣稱不成立。
    """
    import asyncio

    import psycopg

    _seal(importlib.import_module(SEAL_SAMPLE_MODULE), monkeypatch)

    async def _open_async_connection():
        return await psycopg.AsyncConnection.connect(_DEAD_DSN)

    with pytest.raises(SideEffectReached, match="AsyncConnection.connect"):
        asyncio.run(_open_async_connection())


@pytest.mark.parametrize("pool_attr", ["AsyncConnectionPool", "AsyncNullConnectionPool",
                                       "ConnectionPool", "NullConnectionPool"])
def test_sealed_probe_blocks_every_psycopg_pool_class(
    pool_attr: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import psycopg_pool

    _seal(importlib.import_module(SEAL_SAMPLE_MODULE), monkeypatch)
    with pytest.raises(SideEffectReached, match=pool_attr):
        getattr(psycopg_pool, pool_attr)(_DEAD_DSN)


@pytest.mark.parametrize("call", ["module", "classmethod"])
def test_sealed_probe_blocks_sync_psycopg_connect(
    call: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`psycopg.connect` 與 `psycopg.Connection.connect` 是兩個獨立符號（`is` 為 False）。"""
    import psycopg

    _seal(importlib.import_module(SEAL_SAMPLE_MODULE), monkeypatch)
    entry = psycopg.connect if call == "module" else psycopg.Connection.connect
    with pytest.raises(SideEffectReached):
        entry(_DEAD_DSN)


def test_seal_surface_matches_audit_tool() -> None:
    """盤點工具與本測試各有一份 seal，兩邊漂移就會重演 CLIHG1-R1-01 那種單邊漏封。"""
    audit_path = (REPO_ROOT / "docs/research/DEV-CLI-HELP-GUARD1/audit_cli_help.py")
    spec = importlib.util.spec_from_file_location("_cli_help_audit_tool", audit_path)
    assert spec and spec.loader
    audit = importlib.util.module_from_spec(spec)
    # 先掛進 sys.modules：工具裡的 @dataclass 解析註解時會回查自己的模組
    sys.modules[spec.name] = audit
    try:
        spec.loader.exec_module(audit)
    finally:
        sys.modules.pop(spec.name, None)
    assert audit.io_target_labels() == _io_target_labels()
    assert audit.UNSEALED_MODULES == UNSEALED_MODULES
    assert audit.FROZEN_MODULES == FROZEN_MODULES


@pytest.mark.parametrize("flag", ["--help", "-h"])
@pytest.mark.parametrize(("script", "module", "func"), GUARDED_ENTRIES)
def test_help_exits_zero_with_no_side_effects(
    script: str, module: str, func: str, flag: str,
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
) -> None:
    mod = _import_entry(module)
    _seal(mod, monkeypatch)
    monkeypatch.setattr(sys, "argv", [script, flag])

    with pytest.raises(SystemExit) as exc:  # SideEffectReached 會直接讓測試失敗
        getattr(mod, func)()

    assert exc.value.code == 0, f"{script} {flag} 應以 0 退出"
    assert script in capsys.readouterr().out, f"{script} {flag} 應印出含 prog 名稱的 usage"


@pytest.mark.parametrize(("script", "module", "func"), GUARDED_ENTRIES)
def test_unknown_flag_exits_nonzero_with_no_side_effects(
    script: str, module: str, func: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _import_entry(module)
    _seal(mod, monkeypatch)
    monkeypatch.setattr(sys, "argv", [script, "--zzz-not-a-real-flag"])

    with pytest.raises(SystemExit) as exc:
        getattr(mod, func)()

    assert exc.value.code not in (0, None), f"{script} 收到未知旗標應以非零碼退出"


@pytest.mark.parametrize(("script", "module", "func"), [
    p for p in GUARDED_ENTRIES
    if p.id in ("cpbl-anchor-career", "cpbl-backfill-season", "cpbl-live-game")
])
def test_missing_required_args_exit_nonzero(
    script: str, module: str, func: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """必填參數的入口：不帶參數要報 usage 並非零退出，不能落入預設值就開跑。"""
    mod = _import_entry(module)
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
    # cpbl-classify-pitches（GUARD2；docstring 三種形式 + 順序無關）
    ("cpbl.models.run_classify_pitches", ["2026", "D"], (2026, "D")),
    ("cpbl.models.run_classify_pitches", ["2025", "A"], (2025, "A")),
    ("cpbl.models.run_classify_pitches", ["D", "2026"], (2026, "D")),
]


@pytest.mark.parametrize(("module", "argv", "expected"), SNIFFING_FORMS,
                         ids=[f"{m.rsplit('.', 1)[-1]}({' '.join(a)})"
                              for m, a, _ in SNIFFING_FORMS])
def test_sniffing_parsers_preserve_semantics(module: str, argv: list[str], expected: tuple) -> None:
    mod = importlib.import_module(module)
    assert mod._parse_args(mod._parser().parse_args(argv).args) == expected


@pytest.mark.parametrize("module", ["cpbl.ingest.run_scrape_pitches",
                                    "cpbl.models.run_classify_pitches"])
def test_sniffing_parsers_reject_unrecognised_token(module: str) -> None:
    """事故的核心：舊版把無法辨識的 token 靜默略過，`--help` 就是這樣被吞掉的。"""
    mod = importlib.import_module(module)
    with pytest.raises(SystemExit) as exc:
        mod._parse_args(["zzz-not-a-real-value"])
    assert exc.value.code != 0


def test_build_sabr_rejects_half_given_year_range(monkeypatch: pytest.MonkeyPatch) -> None:
    """單給一個年份，舊版會靜默改跑「全量重建」——連 RE 矩陣／DER／wSB／勝率矩陣一起重算。

    docs/research/DATA-RULES-AUDIT1_REPORT.md 以 `cpbl-build-sabr <YEAR>` 單年形式記載，
    與程式的 `len(sys.argv) > 2` 判斷對不上。寧可炸掉也不要靜默做一件重得多的事。
    """
    mod = _import_entry("cpbl.models.run_build_sabr")
    _seal(mod, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["cpbl-build-sabr", "2026"])
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code not in (0, None)


def test_build_sabr_year_range_and_bare_forms_still_parse() -> None:
    parser = importlib.import_module("cpbl.models.run_build_sabr")._parser()
    assert (parser.parse_args([]).from_year, parser.parse_args([]).to_year) == (None, None)
    ns = parser.parse_args(["2026", "2026"])
    assert (ns.from_year, ns.to_year) == (2026, 2026)


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
