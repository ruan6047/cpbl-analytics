"""DEV-CLI-HELP-GUARD1 盤點工具：掃描 pyproject `[project.scripts]` 全部入口的 --help 行為。

用法（repo 根目錄）：

    uv run python docs/research/DEV-CLI-HELP-GUARD1/audit_cli_help.py \
        --out docs/research/DEV-CLI-HELP-GUARD1/cli-help-audit.md

## 為什麼不能直接跑 CLI 驗證

本卡的起因就是「跑 `cpbl-scrape-pitches --help` 直接開了真實爬蟲並寫入 DB（+46 列）」。
所以盤點**嚴禁**以真跑爬蟲類 CLI 的方式取得答案。

## 取證方式：AST 靜態分類 + 密封探針（sealed probe）

1. **靜態分類**（`_classify`）：以 `ast` 解析入口函式與它在同模組內遞迴呼叫的 helper，
   判定解析方式為 `argparse` / `manual-argv` / `no-args`。純讀原始碼，零執行。

2. **密封探針**（`_probe`）：在**子行程**中 import 入口模組，把所有對外副作用出口
   全部換成會拋 `SideEffectReached` 的 stub，然後才呼叫 `main()`。三層封鎖：
   - 入口模組命名空間中「來自其他 `cpbl.*` 模組的 callable」（`migrate` / `conn` /
     `scrape_*` / `build_*` …）全部換 stub；
   - `cpbl.db.migrate` / `cpbl.db.conn` 於**來源模組**也換 stub，堵住函式內延遲 import；
   - `_IO_TARGETS` 列舉的 socket / subprocess / psycopg（同步**與非同步**）出口硬封鎖。

   封鎖範圍是**列舉**的，不是「全部」——見 `_IO_TARGETS`。這個區別是查核退回
   CLIHG1-R1-01 的結果：初版只封了 `psycopg.connect` 與同步 `ConnectionPool`，
   `psycopg.AsyncConnection.connect` 與 `AsyncConnectionPool` 是開的，於是「物理上
   不可能碰 DB」這句絕對宣稱並不成立。現在同步與非同步開口對齊，且 `_seal` 會回報
   實際封住的清單，讓「有沒有漏封」變成可驗證的事實而不是宣稱。
   即便如此，仍**不宣稱窮盡**：繞過這些 Python 層符號的路徑（ctypes、直接 syscall、
   未列舉的第三方 driver）不在封鎖範圍內。本專案的 ingest 入口只走 psycopg 與
   httpx/socket，故此封鎖面對本盤點是充分的。

   每個入口一個子行程，彼此隔離，模組 import 失敗（例如 macOS host 上的 LightGBM
   缺 libomp）也只影響該列。

判定碼：

| 碼 | 意義 |
|---|---|
| `SAFE` | `SystemExit(0)`，且沒有任何副作用出口被觸及 → 合格 |
| `SIDE_EFFECT` | 主流程被觸發（stub 被呼叫）→ **缺陷**：探索 CLI 就有副作用 |
| `EXIT_NONZERO` | `SystemExit(code != 0)`，無副作用 → 不會出事但 `--help` 語意錯 |
| `CRASH` | 其他例外（多半是 `int('--help')` ValueError），無副作用 → 同上，且訊息不可讀 |
| `NO_EXIT` | 正常返回且無副作用（罕見） |
| `IMPORT_ERROR` | 模組 import 失敗，探針無法取證（僅靜態分類可用） |
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import io
import json
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"

# 這些檔案由 INGEST-GAME-TM-REFACTOR1-G4 觀測凍結，本卡只盤點不修改。
FROZEN_MODULES = {
    "cpbl.ingest.run_refresh_recent",
    "cpbl.ingest.cpbl_pitch_tracking",
}

# 探針封印的豁免名單：這些模組本身就是護欄，沒有任何 I/O，封了會把「護欄有生效」誤判成
# 「主流程被觸發」。`cpbl.ingest._cli` 只做 argparse 物件組裝（無 import socket/psycopg/
# httpx，無檔案存取），且 socket／psycopg／subprocess 的硬封鎖仍然在位，故豁免它不可能
# 讓真實副作用漏網。
UNSEALED_MODULES = {"cpbl.ingest._cli"}

# 探針硬封鎖的 I/O 出口：(import 名, 擁有者屬性路徑（空字串＝模組本身）, 屬性名)。
#
# ⚠️ 這份清單與 `tests/test_cli_help_guard.py` 的同名常數必須逐項一致，由
# `test_cli_help_guard.py::test_seal_surface_matches_audit_tool` 擋住漂移——兩份
# 各寫一份 seal 而其中一份漏補，正是 CLIHG1-R1-01 那種洞的溫床。
#
# psycopg 的連線入口有數個彼此獨立的符號（`psycopg.connect` 不是
# `Connection.connect`，實測 `is` 為 False），非同步版又是另外一個；pool 亦分同步／
# 非同步／null 四個類別。少封任何一個，「探針碰不到 DB」就不成立。
#
# ⚠️ **socket 層封鎖擋不住 psycopg**：實測（打 127.0.0.1:1 無人監聽的埠）在
# `socket.socket.connect` / `create_connection` / `getaddrinfo` 全封的情況下，
# `psycopg.connect` 與 `psycopg.AsyncConnection.connect` **仍然照常發出連線**，
# 回的是 libpq 的 OperationalError 而不是 stub 的例外——連線由 libpq 在 C 層自己
# 做，根本不經過 Python 的 socket 模組。所以 psycopg 那幾個入口不是「多一層保險」，
# 而是唯一能擋住 DB 連線的地方；漏掉 async 版就是真的會連出去。
_IO_TARGETS = (
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


class SideEffectReached(RuntimeError):
    """探針 stub 被呼叫＝主流程真的會跑起來。"""


@dataclass
class Entry:
    script: str
    module: str
    func: str
    path: str
    parse_style: str
    argparse_seen: bool
    argv_seen: bool
    help_verdict: str
    help_detail: str
    dash_h_verdict: str
    bad_flag_verdict: str
    bad_positional_verdict: str
    frozen: bool
    seal_gap: list[str]


# ---------------------------------------------------------------- 靜態分類


def _module_path(module: str) -> Path:
    return SRC_ROOT.joinpath(*module.split(".")).with_suffix(".py")


def _classify(module: str, func: str) -> tuple[str, bool, bool]:
    """回傳 (parse_style, argparse_seen, argv_seen)，純 AST、不執行任何程式碼。"""
    tree = ast.parse(_module_path(module).read_text(encoding="utf-8"))
    defs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    module_imports_argparse = any(
        isinstance(n, ast.Import) and any(a.name == "argparse" for a in n.names)
        for n in ast.walk(tree)
    )

    seen: set[str] = set()
    argparse_seen = False
    argv_seen = False
    queue = [func]
    while queue:
        name = queue.pop()
        if name in seen or name not in defs:
            continue
        seen.add(name)
        for node in ast.walk(defs[name]):
            if isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name):
                    if node.value.id == "argparse":
                        argparse_seen = True
                    if node.value.id == "sys" and node.attr == "argv":
                        argv_seen = True
            if isinstance(node, ast.Import) and any(a.name == "argparse" for a in node.names):
                argparse_seen = True
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                queue.append(node.func.id)

    if argparse_seen:
        style = "argparse"
    elif argv_seen:
        style = "manual-argv"
    else:
        style = "no-args"
    return style, argparse_seen or module_imports_argparse, argv_seen


# ---------------------------------------------------------------- 密封探針


def io_target_labels() -> tuple[str, ...]:
    """`_IO_TARGETS` 的可讀標籤，供跨檔案一致性斷言使用。"""
    return tuple(f"{mod}.{owner + '.' if owner else ''}{attr}" for mod, owner, attr in _IO_TARGETS)


def _seal(entry_module) -> list[str]:
    """把所有副作用出口換成 stub。回傳**實際**封住的名字——漏封會直接反映在回傳值上。"""
    import importlib

    sealed: list[str] = []

    def _stub(label: str):
        def _raise(*_a, **_kw):
            raise SideEffectReached(label)

        return _raise

    # 1) 入口模組命名空間裡、來自其他 cpbl.* 模組的 callable
    for name in dir(entry_module):
        if name.startswith("__"):
            continue
        obj = getattr(entry_module, name)
        if not callable(obj):
            continue
        owner = getattr(obj, "__module__", "") or ""
        if owner in UNSEALED_MODULES:
            continue
        if owner.startswith("cpbl.") and owner != entry_module.__name__:
            setattr(entry_module, name, _stub(f"{owner}.{name}"))
            sealed.append(f"{entry_module.__name__}.{name}")

    # 2) cpbl.db 於來源模組封死（堵函式內延遲 import）
    import cpbl.db as _db

    for name in ("migrate", "conn", "pool"):
        setattr(_db, name, _stub(f"cpbl.db.{name}"))
        sealed.append(f"cpbl.db.{name}")

    # 3) 網路 / DB / 子行程硬封鎖——探針的最後一道保險（同步與非同步開口對齊）
    for mod_name, owner_path, attr in _IO_TARGETS:
        label = f"{mod_name}.{owner_path + '.' if owner_path else ''}{attr}"
        try:
            owner = importlib.import_module(mod_name)
            for part in filter(None, owner_path.split(".")):
                owner = getattr(owner, part)
            getattr(owner, attr)  # 先確認符號存在，不存在就別假裝封住了
            setattr(owner, attr, _stub(label))
        except (ImportError, AttributeError):
            continue  # 未封住就不列入 sealed——呼叫端據此得知有缺口
        sealed.append(label)
    return sealed


def _run_once(entry_module, func: str, argv: list[str]) -> tuple[str, str]:
    """跑一次密封後的 main()，回傳 (verdict, detail)。"""
    real_argv = sys.argv
    out, err = io.StringIO(), io.StringIO()
    sys.argv = ["prog", *argv]
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            getattr(entry_module, func)()
    except SideEffectReached as exc:
        return "SIDE_EFFECT", f"主流程觸及 {exc}"
    except SystemExit as exc:
        code = exc.code if exc.code is not None else 0
        first = (out.getvalue() or err.getvalue()).strip().splitlines()
        head = first[0][:90] if first else "(無輸出)"
        return ("SAFE" if code == 0 else "EXIT_NONZERO"), f"exit={code}｜{head}"
    except BaseException as exc:  # noqa: BLE001 — 盤點就是要記錄任何例外型別
        return "CRASH", f"{type(exc).__name__}: {str(exc)[:80]}"
    finally:
        sys.argv = real_argv
    return "NO_EXIT", "正常返回（未 exit）"


def _probe_child(module: str, func: str) -> None:
    """子行程入口：印出單一 entry 的四個 probe 結果 JSON。"""
    import importlib

    try:
        mod = importlib.import_module(module)
    except BaseException as exc:  # noqa: BLE001
        print(json.dumps({"import_error": f"{type(exc).__name__}: {str(exc)[:120]}"}))
        return
    sealed = _seal(mod)
    # 漏封哪個出口就誠實回報哪個——報告據此判斷「封鎖面完整」是不是事實。
    result: dict = {"seal_gap": [lb for lb in io_target_labels() if lb not in sealed]}
    for key, argv in (
        ("help", ["--help"]),
        ("dash_h", ["-h"]),
        ("bad_flag", ["--zzz-not-a-real-flag"]),
        ("bad_positional", ["zzz-not-a-real-value"]),
    ):
        verdict, detail = _run_once(mod, func, argv)
        result[key] = [verdict, detail]
    print(json.dumps(result, ensure_ascii=False))


def _probe(module: str, func: str) -> dict:
    proc = subprocess.run(  # noqa: S603 — 固定呼叫自己，無外部輸入
        [sys.executable, str(Path(__file__).resolve()), "--probe", f"{module}:{func}"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=120,
    )
    tail = [ln for ln in proc.stdout.strip().splitlines() if ln.startswith("{")]
    if not tail:
        return {"import_error": (proc.stderr.strip().splitlines() or ["(無輸出)"])[-1][:120]}
    return json.loads(tail[-1])


# ---------------------------------------------------------------- 報告


_STYLE_LABEL = {
    "argparse": "argparse",
    "manual-argv": "手寫 sys.argv",
    "no-args": "無參數（完全不讀 argv）",
}

_VERDICT_LABEL = {
    "SAFE": "✅ SAFE",
    "SIDE_EFFECT": "🔴 SIDE_EFFECT",
    "EXIT_NONZERO": "⚠️ EXIT_NONZERO",
    "CRASH": "⚠️ CRASH",
    "NO_EXIT": "⚠️ NO_EXIT",
    "IMPORT_ERROR": "❔ IMPORT_ERROR",
}


def collect() -> list[Entry]:
    scripts = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    entries: list[Entry] = []
    for script, target in sorted(scripts["project"]["scripts"].items()):
        module, func = target.split(":")
        style, argparse_seen, argv_seen = _classify(module, func)
        probe = _probe(module, func)
        if "import_error" in probe:
            verdicts = {k: ("IMPORT_ERROR", probe["import_error"]) for k in
                        ("help", "dash_h", "bad_flag", "bad_positional")}
        else:
            verdicts = probe
        entries.append(Entry(
            script=script,
            module=module,
            func=func,
            path=str(_module_path(module).relative_to(REPO_ROOT)),
            parse_style=style,
            argparse_seen=argparse_seen,
            argv_seen=argv_seen,
            help_verdict=verdicts["help"][0],
            help_detail=verdicts["help"][1],
            dash_h_verdict=verdicts["dash_h"][0],
            bad_flag_verdict=verdicts["bad_flag"][0],
            bad_positional_verdict=verdicts["bad_positional"][0],
            frozen=module in FROZEN_MODULES,
            seal_gap=list(probe.get("seal_gap", [])),
        ))
    return entries


def _head_sha() -> str:
    proc = subprocess.run(["git", "rev-parse", "HEAD"],  # noqa: S603,S607
                          capture_output=True, text=True, cwd=str(REPO_ROOT))
    return proc.stdout.strip() or "(unknown)"


def render(entries: list[Entry], note: str | None = None) -> str:
    total = len(entries)
    bad = [e for e in entries if e.help_verdict == "SIDE_EFFECT"]
    safe = [e for e in entries if e.help_verdict == "SAFE"]
    other = [e for e in entries if e.help_verdict not in ("SAFE", "SIDE_EFFECT")]
    gaps = sorted({lb for e in entries for lb in e.seal_gap})
    sealed_now = [lb for lb in io_target_labels() if lb not in gaps]
    lines = [
        "# DEV-CLI-HELP-GUARD1 — `[project.scripts]` 入口 `--help` 行為盤點",
        "",
        "> **本檔由指令產生，勿手改。**重新產生：",
        "> `uv run python docs/research/DEV-CLI-HELP-GUARD1/audit_cli_help.py "
        "--out docs/research/DEV-CLI-HELP-GUARD1/cli-help-audit.md`",
        "",
        f"掃描對象：`{_head_sha()}`" + (f"　—　{note}" if note else ""),
        "",
        "取證方式與判定碼定義見 `audit_cli_help.py` docstring。重點：盤點**未真跑任何爬蟲**——",
        "探針在子行程中把 `migrate`／`conn`／`scrape_*` 等副作用出口換成會拋例外的 stub，",
        "再對下列 I/O 出口硬封鎖，任何呼叫都會拋例外而不是真的送出去：",
        "",
        *[f"- `{lb}`" for lb in sealed_now],
        "",
        "封鎖面是**列舉**的，不是「全部」。本檔刻意不宣稱「物理上不可能碰 DB」——初版就是",
        "因為漏封 `psycopg.AsyncConnection.connect` 與 `AsyncConnectionPool` 而讓那句絕對",
        "宣稱不成立（查核 CLIHG1-R1-01）。繞過上列 Python 符號的路徑（ctypes、直接 syscall、",
        "未列舉的第三方 driver）不在封鎖範圍內；本專案 ingest 入口只走 psycopg 與 httpx/socket，",
        "故此封鎖面對本盤點充分。清單與 `tests/test_cli_help_guard.py` 由測試綁定，不得單邊漂移。",
        "",
        ("✅ 上列出口本次全部封鎖成功（探針自行回報，非人工聲明）。" if not gaps else
         "🔴 **封鎖不完整**，下列出口未封住，本報告的無副作用宣稱不成立："
         + "、".join(f"`{lb}`" for lb in gaps)),
        "",
        f"入口總數 **{total}**：✅ SAFE {len(safe)}／🔴 SIDE_EFFECT {len(bad)}／其他 {len(other)}。",
        "",
        "## 逐入口",
        "",
        "| console script | 解析方式 | `--help` | `-h` | 未知旗標 | 未知位置參數 | 模組 |",
        "|---|---|---|---|---|---|---|",
    ]
    for e in entries:
        flag = " 🧊" if e.frozen else ""
        lines.append(
            f"| `{e.script}`{flag} | {_STYLE_LABEL[e.parse_style]} | "
            f"{_VERDICT_LABEL[e.help_verdict]} | {_VERDICT_LABEL[e.dash_h_verdict]} | "
            f"{_VERDICT_LABEL[e.bad_flag_verdict]} | {_VERDICT_LABEL[e.bad_positional_verdict]} | "
            f"`{e.path}` |"
        )
    lines += [
        "",
        "🧊 ＝ INGEST-GAME-TM-REFACTOR1-G4 觀測凍結檔，本卡只盤點不修改。",
        "",
        "「未知位置參數」欄的 🔴 不必然是缺陷：`cpbl-scrape-field` 的位置參數就是自由格式的",
        "球場名，任何字串都是合法過濾條件，探針送的假值自然被當成球場名接受。",
        "",
        "## 本卡資源邊界",
        "",
        "DEV-CLI-HELP-GUARD1 的寫入集只有 `src/cpbl/ingest/`（扣掉兩個 G4 凍結檔）、",
        "`pyproject.toml`、`tests/test_cli_help_guard.py`。因此下列入口**刻意未修**，",
        "只在此列管、回報 PM：",
        "",
        "- 🧊 `cpbl-refresh-recent` — G4 觀測凍結檔，明文排除（`git diff` 零 diff 為驗收條件）。",
        "- `src/cpbl/models/` 與 `src/cpbl/features/` 下的入口 — 不在寫入集；",
        "  且 `DATA-TZ-BOUNDARY1` 卡正平行作業於 models/features，不得越界。",
        "",
        "`cpbl-train` / `cpbl-train-pitching` 在 macOS host 因 LightGBM 缺 `libomp` 而無法 import",
        "（CLAUDE.md 既知限制，需在容器內跑），探針取不到證據；兩者靜態分類皆為「無參數」，",
        "與同群 `cpbl-train-outcome` 等一致，可推定同屬 `--help` 直接開跑那一類。",
        "",
    ]

    if bad:
        lines += ["## 🔴 `--help` 會觸發主流程的入口（探索即副作用）", ""]
        for e in bad:
            lines.append(f"- `{e.script}` — {e.help_detail}"
                         + ("　**（G4 凍結檔，本卡不修）**" if e.frozen else ""))
        lines.append("")
    if other:
        lines += ["## ⚠️ `--help` 非零退出／例外的入口（無副作用，但語意錯）", ""]
        for e in other:
            lines.append(f"- `{e.script}` — {_VERDICT_LABEL[e.help_verdict]}：{e.help_detail}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--probe", help="內部用：子行程模式，格式 module:func")
    ap.add_argument("--out", type=Path, help="Markdown 輸出路徑（未給則印到 stdout）")
    ap.add_argument("--json", action="store_true", help="改輸出原始 JSON")
    ap.add_argument("--note", help="寫進報告抬頭的一行說明（例：這是修補前的基線）")
    args = ap.parse_args()

    if args.probe:
        module, func = args.probe.split(":")
        _probe_child(module, func)
        return

    entries = collect()
    text = (json.dumps([asdict(e) for e in entries], ensure_ascii=False, indent=2)
            if args.json else render(entries, args.note))
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"written: {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
