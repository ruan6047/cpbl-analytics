# LIFECYCLE: standing · 常設工具——這就是給你跑的；不要刪
"""DEV-SCRIPT-INVENTORY1：可執行入口清冊的**產生器**。

用途：把三個入口面（`scripts/**`、`docs/research/**/*.py`、`pyproject [project.scripts]`）
逐支盤出用途、性質、寫入面與 `--help` 安全性，產生 `scripts/README.md`。

    uv run python scripts/script_inventory.py            # 印到 stdout
    uv run python scripts/script_inventory.py --write     # 覆寫 scripts/README.md
    uv run python scripts/script_inventory.py --check     # 與已提交版本比對，不符即非零退出

本檔是**工具**不是偵測器：沒跑不代表壞掉，不需要排程呼叫者。偵測器是
`tests/test_script_inventory.py`，由 CI 在每個 PR 與 push main 執行。

## 本檔自身的安全性

只讀檔案系統與 `git ls-files`，**不 import psycopg、不開 socket、不連 DB**
（由 `tests/test_script_inventory.py::test_generator_itself_touches_no_io` 機械釘住）。

## 四條不變式（由偵測器執行，本檔只負責算出判定依據）

1. **檔頭標記不變式**：`scripts/**` 的每一支都必須在檔頭帶 `LIFECYCLE:` 標記，且標記
   內容必須等於機械推導出來的分類。新增腳本沒標＝ CI 紅。**這是驗收條件 2 要求的
   「檔案系統上可分辨」的載體**（`docs/research/<CARD-ID>/` 那 19 支靠位置本身分辨）。
2. **位置棘輪**：分類理應唯一決定位置（常設 → `scripts/` 頂層；CI 繫結 → `scripts/ci/`；
   一次性產物 → `docs/research/<CARD-ID>/`）。現況有既存不符者，逐支列入 `POSITION_DEBT`
   並附「為什麼本輪搬不動」；**該集合只能縮不能長**——新增的不符即 CI 紅。
3. **引用完整性**：**活檔案**裡的 `scripts/<name>.<ext>` 字面路徑必須指向存在的檔案。
   封存面（`docs/control-plane/**`、掃描器產物 JSON）只回報不強制，限度明載於清冊。
4. **寫入型必須 `--help` 安全**：判定為寫入型的入口，其 argv 必須在主流程前被解析；
   既有不合格者具名列入 `HELP_SAFETY_ALLOWLIST` 並附理由。

## ⚠️ 為什麼不變式 2 是「棘輪」而不是「硬不變式」

規劃階段的方案 A 是把 22 支一次性產物 `git mv` 進 `docs/research/<CARD-ID>/`。
**不變式 3 一建起來就否決了這個計畫**：實測 28 支該搬的裡有 **20 支**的活引用落在
本卡射程外——絕大多數是**凍結證據文件裡的重現指令**
（`docs/research/<CARD>_RESULTS.md` 的「重現方法：`uv run python scripts/x.py …`」）、
`src/` 的 4 處 docstring、以及 3 張活卡的 spec 檔。需求方裁定 4 已把這些面移出射程。

搬走而不同步，就是**親手弄壞歷史證據的重現指令**——那正是 PM 複驗在
`data_tie_remedy1.py` 的 `FROZEN_FILES` 上抓到的同一種傷害，只是機械掃描量出來是
**20 處而不是 2 處**。而只搬「免費的 8 支」會製造**更糟的假訊號**：一個只裝了
9 支中 3 支的 `scripts/ci/`，會讓留在 `scripts/` 的另外 6 支看起來像常設工具。

**所以本輪零搬動**，改以檔頭標記當可分辨載體，位置債逐支登記並上棘輪。
完整的 28 支債務清單見產出的清冊，供後續卡以正確射程執行。

## 寫入面：兩套獨立判準交叉複算

`W1`（AST call-graph）與 `W2`（正則 SQL 掃描）各自獨立判定，**不取聯集也不取交集**。
不一致者逐支落 `WRITE_ADJUDICATION` 人工裁定並附理由；出現未裁定的新不一致即 fail closed。
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
import tomllib
from collections import defaultdict
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README_PATH = ROOT / "scripts" / "README.md"

# ---------------------------------------------------------------- 入口面定義

SCRIPTS_GLOB = "scripts/**"
RESEARCH_GLOB = "docs/**/*.py"

# 本產生器與其產物不算「入口」：README.md 不可執行。
NON_ENTRY_BASENAMES = {"README.md"}

# --------------------------------------------------------------- 引用面分層
#
# 「被文件提到」是弱訊號——Discovery 實測 `g4_phase_a_metrics.py` 在 ROADMAP 的命中
# 其實是一則缺陷報告而非操作指令。所以只有**活的入口／契約／設計／術語文件**裡的
# **可執行指令列**才算「有人會手動跑它」。

LIVE_DOC_PREFIXES = (
    "CLAUDE.md",
    "AGENTS.md",
    "README.md",
    "docs/design/",
    "docs/reference/",
)
# `docs/` 頂層的 .md（契約、Runbook、ROADMAP…）也算活文件，但 docs/ 底下其餘子目錄
# （archive／control-plane／research／tasks／handoffs／incidents／discovery）是歷史痕跡。
LIVE_DOC_TOPLEVEL = "docs/"

HISTORICAL_DOC_PREFIXES = (
    "docs/archive/",
    "docs/control-plane/",
    "docs/research/",
    "docs/tasks/",
    "docs/handoffs/",
    "docs/incidents/",
    "docs/discovery/",
)

# 可執行指令列的引子。行內同時出現這些 token 之一與腳本路徑，才算「文件叫人跑它」。
COMMAND_TOKENS = ("uv run", "python3", "python ", "bash ", "sh ", "./", "docker exec")

# ------------------------------------------------------------------- 卡 ID
#
# ⚠️ 貪婪匹配是刻意的：`GAME-RECAP-PA1-FIX1` 不得被截成 `GAME-RECAP-PA1`
# （已知錯誤 5「卡 ID 前綴截斷」，回歸案例見偵測器）。
CARD_ID_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b")

# 大寫連字號 token 但不是卡 ID 的（型別、標準名、縮寫）。
CARD_ID_STOPWORDS = frozenset({
    "ISO-8601", "UTF-8", "READ-ONLY", "CI-BOUND", "NO-GO", "PR-", "T-SQL",
    "AI-", "UPSERT-", "E-R", "ON-CONFLICT", "SSH-", "DB-", "SQL-",
})

# --------------------------------------------------------- 寫入面：SQL 動詞
#
# ⚠️ 必須有 `\b` 詞界：`updated_at` / `created_at` / `deleted_flag` 是欄位名不是動詞
# （已知錯誤 3「子字串假陽性」的同型物，回歸案例見偵測器）。
MUTATING_SQL_RE = re.compile(
    r"\b(INSERT\s+INTO|UPDATE\s+\w|DELETE\s+FROM|TRUNCATE\b|DROP\s+(TABLE|INDEX|VIEW|SCHEMA)"
    r"|CREATE\s+(TABLE|INDEX|VIEW|SCHEMA|MATERIALIZED)|ALTER\s+TABLE"
    r"|REFRESH\s+MATERIALIZED|COPY\s+\w+.*\bFROM\b|SELECT\s+setval|\bsetval\s*\()",
    re.IGNORECASE,
)

# shell/plist 的寫入出口：**沒有 Python AST 可分析**，所以 W1 對它們結構性地不適用，
# 只有 W2 這一套判準。這一格沒有交叉複算——限度明載於清冊，不假裝有。
MUTATING_SHELL_RE = re.compile(
    r"\b(pg_restore|createdb|dropdb"
    r"|cpbl-(scrape|backfill|refresh|build|ingest|train|anchor|classify|reconcile|live)[a-z-]*)",
)

# 掃描器自身：本檔與偵測器的原始碼裡就寫著 SQL 動詞的**正則樣式**，會被自己的
# 字面掃描命中。repo 內已有先例（TIME-SEMANTICS-CONTRACT1 的掃描器同樣自我排除）。
#
# ⚠️ `tests/test_script_inventory.py` 必須在這裡，理由比「正則自我命中」更硬：
# 偵測器的 `FROZEN_POSITION_DEBT` 表把 21 支一次性產物的路徑寫成**字串常數**，
# 而 CI 繫結偵測正是靠「測試檔裡的字串常數命中腳本路徑」——於是那 21 支會被
# 判成 CI 繫結守衛。**偵測器的資料表反過來改變了它自己在檢查的分類。**
# `scripts/README.md` 同理：它是本掃描器的產物，裡面的路徑全來自掃描本身。
SELF_REFERENCE = frozenset({
    "scripts/script_inventory.py",
    "scripts/README.md",
    "tests/test_script_inventory.py",
})

EXECUTE_ATTRS = frozenset({"execute", "executemany", "copy"})


# ============================================================ 基礎：檔案列舉


def _git_ls(*patterns: str) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", *patterns],
        capture_output=True, text=True, check=True,
    ).stdout
    return sorted(p for p in out.splitlines() if p)


@cache
def _read(rel: str) -> str:
    try:
        return (ROOT / rel).read_text(encoding="utf-8", errors="replace")
    except (OSError, IsADirectoryError):
        return ""


@cache
def _tracked_files() -> tuple[str, ...]:
    return tuple(_git_ls())


def _is_live_doc(rel: str) -> bool:
    if rel.startswith(HISTORICAL_DOC_PREFIXES):
        return False
    if rel.startswith(LIVE_DOC_PREFIXES):
        return True
    # docs/ 頂層的 .md
    return (
        rel.startswith(LIVE_DOC_TOPLEVEL)
        and rel.count("/") == 1
        and rel.endswith(".md")
    )


# ====================================================== 卡 ID 抽取（貪婪）


def card_ids(text: str) -> list[str]:
    """從文字抽卡 ID。貪婪匹配，`-FIX1` / `-G4` 尾綴不得被截掉。"""
    seen: list[str] = []
    for m in CARD_ID_RE.finditer(text):
        token = m.group(0)
        if token in CARD_ID_STOPWORDS or token.startswith(tuple(CARD_ID_STOPWORDS)):
            continue
        if token not in seen:
            seen.append(token)
    return seen


# ================================================= 訊號 1：排程鏈（傳遞閉包）


@cache
def scheduled_entries() -> frozenset[str]:
    """由 plist 出發、沿 shell 呼叫傳遞展開的排程可達集合。"""
    reachable: set[str] = set()
    frontier: list[str] = []

    for rel in _git_ls("scripts/*.plist"):
        reachable.add(rel)
        frontier.extend(_referenced_script_paths(_read(rel)))

    while frontier:
        rel = frontier.pop()
        if rel in reachable or not (ROOT / rel).exists():
            continue
        reachable.add(rel)
        frontier.extend(_referenced_script_paths(_read(rel)))
    return frozenset(reachable)


_SCRIPT_BASENAME_RE = re.compile(r"(?<![\w./-])(?:[\w./-]*/)?([\w.-]+\.(?:sh|py))(?![\w])")


def _referenced_script_paths(text: str) -> list[str]:
    """從 shell/plist 文字裡找出它會呼叫的 `scripts/` 檔案（以 basename 對回）。"""
    known = {Path(p).name: p for p in _git_ls("scripts/*")}
    hits = []
    for m in _SCRIPT_BASENAME_RE.finditer(text):
        target = known.get(m.group(1))
        if target:
            hits.append(target)
    return hits


# ============================================ 訊號 2：活文件裡的可執行指令列


@cache
def livedoc_commands() -> dict[str, tuple[str, ...]]:
    """腳本路徑 → 活文件裡叫人跑它的指令列位置（`檔案:行號`）。"""
    targets = {p for p in _git_ls("scripts/*") if Path(p).suffix in {".py", ".sh"}}
    targets |= set(_git_ls(RESEARCH_GLOB))
    found: dict[str, list[str]] = defaultdict(list)

    for rel in _tracked_files():
        if not _is_live_doc(rel) or not rel.endswith(".md"):
            continue
        for lineno, line in enumerate(_read(rel).splitlines(), 1):
            if not any(tok in line for tok in COMMAND_TOKENS):
                continue
            for target in targets:
                if literal_path_in_line(target, line):
                    found[target].append(f"{rel}:{lineno}")
    return {k: tuple(v) for k, v in found.items()}


# ⚠️ 詞界：`scripts/foo.py` 不得命中 `scripts/foo.pyc`，也不得命中 `myscripts/foo.py`
# （已知錯誤 2「正則邊界」，回歸案例見偵測器）。
def literal_path_in_line(path: str, line: str) -> bool:
    return _path_pattern(path).search(line) is not None


@cache
def _path_pattern(path: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w./-]){re.escape(path)}(?![\w.-])")


# ================================================ 訊號 3：pytest 機械載入


def ci_binding_targets(src: str, known: set[str]) -> set[str]:
    """單一測試檔原始碼 → 它**機械載入**的腳本路徑集合。

    ⚠️ 只認 AST 節點（`Import`／`ImportFrom`／字串常數）。**註解與散文裡提到不算**
    ——已知錯誤 1「模組級誤標」：初版用正則掃全文，`# 這支的邏輯見 scripts/foo.py`
    這種註解會讓 `foo.py` 被誤標成 CI 繫結守衛，而分類錯了位置就跟著錯。
    回歸案例見 `tests/test_script_inventory.py`。
    """
    hits: set[str] = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return hits

    for node in ast.walk(tree):
        # (a) `from scripts.x import y` / `import scripts.x`
        mods: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.module:
            mods.append(node.module)
        elif isinstance(node, ast.Import):
            mods.extend(alias.name for alias in node.names)
        for mod in mods:
            if mod.startswith("scripts."):
                candidate = "scripts/" + mod[len("scripts."):].replace(".", "/") + ".py"
                if candidate in known:
                    hits.add(candidate)

        # (b) 字串常數裡的路徑片段（`spec_from_file_location`、`ROOT / "scripts" / name`）
        #     ——docstring 是 `ast.Constant`，所以額外排除「整個模組／函式的 docstring」。
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if "\n" in value:          # 多行字串＝散文，不是路徑
                continue
            for target in known:
                name = Path(target).name
                if value in {name, target} or value.endswith("/" + name):
                    hits.add(target)
    return hits


@cache
def ci_bindings() -> dict[str, tuple[str, ...]]:
    """腳本路徑 → 機械載入它的測試檔。"""
    known = set(_git_ls("scripts/*")) | set(_git_ls(RESEARCH_GLOB))
    found: dict[str, list[str]] = defaultdict(list)
    for rel in _git_ls("tests/*.py", "tests/**/*.py"):
        if rel in SELF_REFERENCE:
            continue
        for target in ci_binding_targets(_read(rel), known):
            found[target].append(rel)
    return {k: tuple(sorted(set(v))) for k, v in found.items()}


# ================================================== 寫入面 W1：AST call-graph


@dataclass
class _ModuleGraph:
    """單一 Python 檔的函式呼叫圖與直接寫入點。"""

    mutating: set[str] = field(default_factory=set)      # 本檔內直接含寫入 SQL 的函式
    calls: dict[str, set[str]] = field(default_factory=dict)   # 函式 → 呼叫的本地名稱
    imports: dict[str, str] = field(default_factory=dict)      # 本地名 → `模組:符號`
    module_calls: set[str] = field(default_factory=set)        # 模組層（含 __main__ 區塊）


def _sql_from_node(node: ast.AST) -> str:
    """把 AST 節點裡靜態可見的字串攤平（含 f-string 與字串相加）。"""
    parts: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            parts.append(sub.value)
    return "\n".join(parts)


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _build_graph(src: str, consts: dict[str, str] | None = None) -> _ModuleGraph:
    graph = _ModuleGraph()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return graph

    const_sql: dict[str, str] = dict(consts or {})
    for node in tree.body:
        if isinstance(node, ast.Assign):
            text = _sql_from_node(node.value)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    const_sql[target.id] = text

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                graph.imports[alias.asname or alias.name] = f"{node.module}:{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                graph.imports[alias.asname or alias.name] = f"{alias.name}:*"

    def scan(body: list[ast.stmt], owner: str) -> None:
        bucket = graph.calls.setdefault(owner, set()) if owner else graph.module_calls
        for node in body:
            for sub in ast.walk(node):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub is not node:
                    continue
                if not isinstance(sub, ast.Call):
                    continue
                name = _call_name(sub)
                if name:
                    bucket.add(name)
                if name in EXECUTE_ATTRS and sub.args:
                    arg = sub.args[0]
                    text = _sql_from_node(arg)
                    if isinstance(arg, ast.Name):
                        text += "\n" + const_sql.get(arg.id, "")
                    if MUTATING_SQL_RE.search(text):
                        if owner:
                            graph.mutating.add(owner)
                        else:
                            graph.mutating.add("<module>")

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scan(node.body, node.name)
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    scan(sub.body, f"{node.name}.{sub.name}")
        else:
            scan([node], "")
    return graph


@cache
def _src_module_path(module: str) -> str | None:
    for candidate in (
        f"src/{module.replace('.', '/')}.py",
        f"src/{module.replace('.', '/')}/__init__.py",
    ):
        if (ROOT / candidate).exists():
            return candidate
    return None


@cache
def _graph_of(rel: str) -> _ModuleGraph:
    return _build_graph(_read(rel))


@cache
def _module_is_mutating(module: str, symbol: str) -> bool:
    """`cpbl.*` 模組的某符號（或整個模組）是否可達寫入 SQL。"""
    return bool(_mutating_symbols(module) and (symbol == "*" or symbol in _mutating_symbols(module)))


@cache
def _mutating_symbols(module: str, _depth: int = 0) -> frozenset[str]:
    """模組內傳遞可達寫入 SQL 的函式名集合。"""
    rel = _src_module_path(module)
    if rel is None or _depth > 6:
        return frozenset()
    graph = _graph_of(rel)
    mutating = set(graph.mutating)

    # 跨模組：呼叫了其他 cpbl 模組的寫入函式
    external: set[str] = set()
    for local, origin in graph.imports.items():
        mod, sym = origin.split(":", 1)
        if not mod.startswith("cpbl"):
            continue
        if sym == "*":
            continue
        if _mutating_symbols(mod, _depth + 1) and sym in _mutating_symbols(mod, _depth + 1):
            external.add(local)

    changed = True
    while changed:
        changed = False
        for fn, called in graph.calls.items():
            if fn in mutating:
                continue
            if called & mutating or called & external:
                mutating.add(fn)
                changed = True
    return frozenset(mutating)


def writes_ast(rel: str, entry_fns: tuple[str, ...] = ("main",)) -> bool:
    """W1：從入口函式出發，AST 呼叫圖是否可達寫入 SQL。"""
    graph = _graph_of(rel)
    mutating = set(graph.mutating)

    external: set[str] = set()
    for local, origin in graph.imports.items():
        mod, sym = origin.split(":", 1)
        if not mod.startswith("cpbl"):
            continue
        if sym == "*":
            if _mutating_symbols(mod):
                external.add(local)
        elif sym in _mutating_symbols(mod):
            external.add(local)

    changed = True
    while changed:
        changed = False
        for fn, called in graph.calls.items():
            if fn in mutating:
                continue
            if called & mutating or called & external:
                mutating.add(fn)
                changed = True

    if "<module>" in mutating or graph.module_calls & (mutating | external):
        return True
    reach = set(graph.module_calls)
    for fn in entry_fns:
        reach |= graph.calls.get(fn, set())
    seen: set[str] = set()
    while reach:
        name = reach.pop()
        if name in seen:
            continue
        seen.add(name)
        if name in mutating or name in external:
            return True
        reach |= graph.calls.get(name, set())
    return False


# ================================================ 寫入面 W2：正則 SQL 掃描


@cache
def _import_closure(rel: str, _depth: int = 0) -> frozenset[str]:
    """檔案 ＋ 它傳遞 import 的 `src/cpbl/**` 模組檔。"""
    if _depth > 6:
        return frozenset({rel})
    files = {rel}
    graph = _graph_of(rel)
    for origin in graph.imports.values():
        mod = origin.split(":", 1)[0]
        if not mod.startswith("cpbl"):
            continue
        target = _src_module_path(mod)
        if target and target not in files:
            files |= _import_closure(target, _depth + 1)
    return frozenset(files)


def writes_sql(rel: str) -> bool:
    """W2：import 閉包內任一檔案的字串字面是否含寫入 SQL。不看呼叫圖。"""
    if rel in SELF_REFERENCE:
        return False
    if rel.endswith((".sh", ".plist")):
        return bool(MUTATING_SQL_RE.search(_read(rel)) or MUTATING_SHELL_RE.search(_read(rel)))
    for path in _import_closure(rel):
        if path not in SELF_REFERENCE and MUTATING_SQL_RE.search(_read(path)):
            return True
    return False


# ⚠️ 兩套判準不一致者的人工裁定。**不取聯集也不取交集。**
# key = 入口識別（腳本相對路徑，或 CLI 名稱）；value = (判定, 理由)
WRITE_ADJUDICATION: dict[str, tuple[bool, str]] = {
    # --- W1 否、W2 是：import 閉包裡有寫入 SQL，但入口的呼叫路徑到不了 ---
    "scripts/check_splits_pa_split1_results.py": (
        False, "純讀 artifact JSON 與 RESULTS.md 對數字，完全不開 DB"),
    "scripts/data_rules_audit1.py": (False, "唯讀稽核；凍結在舊判準供重現當初數字"),
    "scripts/data_tie_remedy1.py": (False, "唯讀；只讀 completion 與 games 算並列名次"),
    "scripts/dryrun_game_tm_fullseason.py": (False, "dry-run：只比對不寫入，卡面即以此為射程"),
    "scripts/g4_gate_report.py": (False, "唯讀 Gate 報表"),
    "scripts/g4_phase_a_metrics.py": (False, "唯讀觀測指標；凍結在舊判準"),
    "scripts/g4_redline1_probe.py": (False, "唯讀探針"),
    "scripts/ibb_ghost1_probe.py": (False, "唯讀探針"),
    "scripts/outcome_leak_compare.py": (False, "唯讀回測對照，產物落檔案不落 DB"),
    "scripts/outcome_simple_calibration_audit.py": (False, "唯讀校準稽核"),
    "scripts/pa_transition_taxonomy.py": (
        False, "docstring 明宣告唯讀（db_scope=read）；產物是 JSON 與 md，不物化 PA"),
    "scripts/reconcile_game_tm.py": (False, "唯讀對帳：比兩條 fetch path，不落表"),
    "scripts/verify_pa_build_fix1.py": (False, "唯讀驗證"),
    "scripts/verify_splits_pa_split1.py": (
        False, "開頭即 `SET TRANSACTION READ ONLY`，物理上寫不了"),
    "scripts/wp_bio_prior1.py": (False, "唯讀先驗分析"),
    "docs/research/ML-PITCHER-ER-REBUILD1/cases/build_cases.py": (False, "唯讀取樣落 JSON"),
    "docs/research/ML-WP-VAL-RESAMPLE1/bin_stability.py": (False, "唯讀重抽樣分析"),
    "docs/research/ML-WP-VAL-RESAMPLE1/census.py": (False, "唯讀普查"),
    "docs/research/ML-WP-VERDICT-ROBUST1/budget_trace.py": (False, "唯讀預算追蹤"),
    "cpbl-verify-splits": (False, "唯讀驗證入口"),
    "cpbl-research-umpire-impact": (False, "唯讀研究，產物落檔案"),
    "scripts/ability_snapshot.py": (
        False, "唯讀抽驗：呼叫 API helper `_ability_card` 取快照 dump 成 JSON；"
               "W2 命中的是 cpbl.api 閉包裡別條路徑的寫入"),
    "scripts/capture_player_ia_fixtures.py": (
        False, "唯讀：打 API 取 payload、截斷後落 web fixtures 檔"),
    "scripts/replay_schedule_branches.py": (
        False, "Gate 3 補證：對歷史賽程**回放**既有分類邏輯，只讀不落表"),
    "scripts/team_style2_manager_pairs.py": (
        False, "docstring 明寫「唯讀；描述性」——換教練混雜效應檢定"),
    "docs/research/ML-PITCHER-ER-REBUILD1/rebuild_er.py": (
        False, "docstring 明寫「本檔只讀 DB、只寫 JSON 到本目錄，不改任何既有模組、"
               "不寫任何表」；檔內 `cur.execute` 全是 SELECT"),
    "docs/research/ML-WP-VERDICT-ROBUST1/compare_verdicts.py": (
        False, "同一份資料同一份指標、只換判定規則的對照，不落表"),
    # --- ⚠️ W1 是、W2 否是**沒有**的；反過來這一支是 W1 的結構性盲點 ---
    "docs/research/INGEST-DEEP-TM-BACKFILL1/sync_deep_tm_prod.py": (
        True,
        "⚠️ **W1 的結構性偽陰性**：它以 `subprocess.run(['ssh', VPS, ... 'psql'], input=script)` "
        "把 `COPY cpbl.pitch_tracking_deep_staging` ＋ `UPDATE cpbl.pitch_tracking` 串進"
        "**生產** psql——寫入完全不經過 Python 的 DB cursor，AST 呼叫圖看不到。"
        "W2 掃字面才抓得到。這一支就是兩套判準必須並存的理由"),
}

# ⚠️ shell／plist 只有 W2 一套判準（W1 需要 Python AST）。這一格**沒有交叉複算**，
# 所以 W2 的誤判沒有第二個判準擋——逐支覆寫時理由要寫得比兩判準那格更硬。
SINGLE_CRITERION_OVERRIDE: dict[str, tuple[bool, str]] = {
    "scripts/backup-prod-db.sh": (
        False,
        "W2 命中的 `CREATE TABLE` 在 awk 樣式 `/^CREATE TABLE /{t++}` 裡——那是**數 dump "
        "裡有幾張表**的內容門檻驗證，不是建表。本腳本對 DB 唯讀（`pg_dump`），寫的是本機備份檔。"
        "⚠️ 仍是高後果操作：不看 argv、連生產、跑完整 dump"),
}

# 判定為寫入型但 `--help` 不安全的既有例外。**本輪不修它們的行為**（那會讓本卡從
# 盤點變成改一批腳本），改為具名列出＋理由＋去向。具名例外可讀，勝過偷偷放寬判準。
HELP_SAFETY_ALLOWLIST: dict[str, str] = {
    "cpbl-refresh-recent": (
        "#53 INGEST-GAME-TM-REFACTOR1-G4 Phase B 凍結資源，DEV-CLI-HELP-GUARD1／2 明文不改。"
        "`--help` 主流程觸及 cpbl.db.migrate，且它是每日鏈 scrape-daily.sh 的主要寫入者。"
        "去向：#53 Phase B 解凍後併入 test_cli_help_guard.py 的斷言範圍"),
    "scripts/rehearsal_backfill.py": (
        "完全不看 argv：任何旗標（含 --help）都直接 DROP/CREATE pitch_tracking_rehearsal。"
        "去向：本卡只標記；修行為需另卡，且該卡母卡 INGEST-DEEP-TM-BACKFILL1 已封存"),
    "scripts/rehearsal_pa_build.py": (
        "完全不看 argv，寫合成 year=2099 列。去向：同上，PA-DAILY 若啟動時一併處理"),
    "docs/research/INGEST-DEEP-TM-BACKFILL1/sync_deep_tm_prod.py": (
        "⚠️ **本輪射程內最危險的一支**：完全不看 argv，任何參數都直接 ssh 進生產跑 "
        "`COPY` ＋ `UPDATE cpbl.pitch_tracking`；`VPS` 是裸常數不可覆蓋、無 dry-run、無備份。"
        "已於 `dac8d8e` 移出 `scripts/`（＝瀏覽者不會再誤觸），"
        "但**檔案本身的行為沒變**。去向：修行為需另卡，母卡 INGEST-DEEP-TM-BACKFILL1 已封存"),
    # --- 排程用的 shell：launchd 以固定參數呼叫，但人手打 `--help` 會直接開跑 ---
    "scripts/refresh-cpbl-prod.sh": (
        "無 argv 守衛，`./scripts/refresh-cpbl-prod.sh --help` 會直接開始同步生產。"
        "去向：本卡不改排程腳本行為（那是改一批常設維運工具，不是盤點）"),
    "scripts/scrape-daily.sh": (
        "`ARGS=\"${1:-}\"` 把 `--help` 當成模式字串吞掉，然後跑完整每日爬取。去向：同上"),
    "scripts/weekly-box-revisions.sh": (
        "無 argv 守衛，會直接跑 `cpbl-refresh-recent` ＋ `cpbl-refresh-box-deep`。去向：同上"),
    "scripts/weekly-game-pitches.sh": (
        "無 argv 守衛，會直接跑 `cpbl-scrape-game-pitches`。去向：同上"),
}

# 分類的人工改判：機械推導錯的逐支列出＋理由。
# ⚠️ 偵測器會擋掉**過期的改判**（推導結果已等於改判值＝這條可以刪），避免重演
# `roadmap_lines.py` 的 GATE_OVERRIDES「硬編說明文字沒有到期與真實性來源」那個病。
CLASS_OVERRIDES: dict[str, tuple[str, str]] = {
    "scripts/script_inventory.py": (
        "standing",
        "本清冊的產生器：人需要重生清冊時跑它。推導會判 ci_guard（tests/test_script_inventory.py "
        "載入它），但那是同步偵測器不是它的唯一用途——與 pa_transition_taxonomy.py 同形狀。"
        "⚠️ 之所以沒有活文件指令，是因為入口文件 docs/AI_RUNBOOK.md 由 #140 持有，不在本卡射程"),
    "scripts/ability_snapshot.py": (
        "standing",
        "docstring 明寫「改前後各跑一次再 diff」＝重複執行義務，是能力值卡的回歸抽驗工具；"
        "無卡 ID 故不可能是卡片一次性產物。缺的是觸發器不是生命週期"),
    "scripts/review_gate_inventory.py": (
        "standing",
        "REVIEW_GATE_CONTRACT §6 引用它為可重現盤點、§225 宣告「納管＋測試」。"
        "⚠️ 該宣告未落實：實測無任何測試載入它，防護是名義上的"),
    "scripts/capture_player_ia_fixtures.py": (
        "product_pending",
        "訊號互斥且需求方已裁定不重裁：母卡 UX-PLAYER-IA1 已封存（＝一次性），"
        "但產物被 web/src/app/dev/player-ia/lib.ts 消費（＝有活的下游）。"
        "`/dev/player-ia` prototype 頁去留是產品取捨，位置不動"),
}

# 分類正確但**刻意不搬**的位置例外。具名＋理由，偵測器據此放行。
POSITION_EXCEPTIONS: dict[str, str] = {
    "scripts/verify_deep_tm_backfill.py": (
        "需求方裁定 3：它是活卡 DEV-VERIFY-TM-ASSERTS1（T2、Backlog）的射程本體，"
        "搬它等於改另一張活卡的資源路徑。例外具名可讀，勝過偷改別卡"),
    "scripts/data_rules_audit1.py": (
        "scripts/data_tie_remedy1.py 的 FROZEN_FILES 以**字面路徑**硬編它，"
        "而 CI 只 import `_streaks_for` 碰不到 `is_frozen`——搬走會讓守衛靜默回 False。"
        "凍結理由是「必須能重現當初的數字」，動它會讓歷史證據不可重現"),
    "scripts/g4_phase_a_metrics.py": (
        "同上：FROZEN_FILES 字面路徑成員判定，凍結理由是「判準一換觀測就不可比」"),
}

# 一次性產物的歸屬卡（決定 `docs/research/<CARD-ID>/` 的目標目錄）。
# 偵測器對任何缺歸屬的一次性產物 fail closed。
ONESHOT_HOME: dict[str, str] = {
    "scripts/check_scoreless_null_folding.py": "ML-PITCHER-SCORELESS1",
    "scripts/check_splits_pa_split1_results.py": "INGEST-SPLITS-PA-SPLIT1",
    "scripts/compare_runless_vs_er_streak.py": "ML-PITCHER-RUNLESS1",
    "scripts/data_rules_audit1.py": "DATA-RULES-AUDIT1",
    "scripts/data_tz_boundary1.py": "DATA-TZ-BOUNDARY1",
    "scripts/g4_gate_report.py": "INGEST-GAME-TM-REFACTOR1-G4",
    "scripts/g4_phase_a_metrics.py": "INGEST-GAME-TM-REFACTOR1-G4",
    "scripts/g4_redline1_probe.py": "INGEST-GAME-TM-REFACTOR1-G4",
    "scripts/ibb_ghost1_probe.py": "INGEST-SPLITS-IBB-GHOST1",
    "scripts/outcome_leak_compare.py": "ML-OUTCOME-LEAK1",
    "scripts/outcome_simple_calibration_audit.py": "ML-OUTCOME-SIMPLE-LEAK2",
    "scripts/reconcile_game_tm.py": "INGEST-GAME-TM-REFACTOR1",
    "scripts/reconcile_splits_recalc1.py": "INGEST-SPLITS-RECALC1",
    "scripts/rehearsal_backfill.py": "INGEST-DEEP-TM-BACKFILL1",
    "scripts/rehearsal_pa_build.py": "GAME-RECAP-PA1-BUILD1",
    "scripts/replay_schedule_branches.py": "INGEST-GAME-TM-REFACTOR1-G4",
    "scripts/report_pa_rebuild_fix1.py": "GAME-RECAP-PA1-FIX1",
    "scripts/restate1_reconcile.py": "INGEST-SPLITS-IMPORT-RESTATE1",
    "scripts/state_plane_migrate.py": "OPS-STATE-PLANE-MIG1",
    "scripts/team_style_vectors.py": "TEAM-STYLE1",
    "scripts/verify_deep_tm_backfill.py": "INGEST-DEEP-TM-BACKFILL1",
    "scripts/verify_pa_build_fix1.py": "GAME-RECAP-PA1-FIX1",
    "scripts/verify_splits_pa_split1.py": "INGEST-SPLITS-PA-SPLIT1",
}

CLASS_LABELS = {
    "standing": "常設工具",
    "ci_guard": "CI 繫結守衛",
    "oneshot": "一次性產物",
    "product_pending": "待產品裁定",
}

# 檔頭標記的一句話後果——讀者打開檔案第一眼看到的就是「能不能跑、能不能刪」。
CLASS_CONSEQUENCE = {
    "standing": "常設工具——這就是給你跑的；不要刪",
    "ci_guard": "CI 繫結守衛——不必手動跑，CI 會跑；刪了 CI 會紅",
    "oneshot": "卡片一次性產物——不要跑；刪除須需求方裁定",
    "product_pending": "待產品裁定——位置與去留都還沒定案，先不要動",
}

LIFECYCLE_TOKEN = "LIFECYCLE:"
# ⚠️ 必須認**整行形狀**而不是「這行有沒有出現 LIFECYCLE:」——本檔自己的 docstring 與
# 常數定義就含這個 token。初版用寬鬆比對，`--stamp` 當場把自己的原始碼吃掉 5 行。
# `·` 分隔符是刻意的：它讓「標記」與「提到標記」在正則上分得開。
LIFECYCLE_RE = re.compile(r"^\s*(?:#|<!--)\s*LIFECYCLE:\s*([a-z_]+)\s*·")
# 標記一律放檔案最前面（shebang 之後）：讀者開檔第一眼就看得到，且不受 docstring
# 長度影響。初版放在 module docstring 之後，5 支長 docstring 的檔案標記掉出掃描窗
# ——「產生器寫得出來、讀取器讀不回來」的靜默不一致，正是本卡在防的形狀。
LIFECYCLE_SCAN_LINES = 10


def lifecycle_marker(rel: str) -> str:
    """讀檔頭標記。回傳分類字串，沒有標記回空字串。"""
    for line in _read(rel).splitlines()[:LIFECYCLE_SCAN_LINES]:
        m = LIFECYCLE_RE.match(line)
        if m:
            return m.group(1)
    return ""


def marker_line(rel: str, cls: str) -> str:
    card = _card_of(rel)
    suffix = f"（{card}）" if card and cls in {"oneshot", "product_pending"} else ""
    body = f"{LIFECYCLE_TOKEN} {cls} · {CLASS_CONSEQUENCE.get(cls, '⚠️ 未分類')}{suffix}"
    ext = Path(rel).suffix
    if ext == ".plist":
        return f"<!-- {body} -->"
    return f"# {body}"


def _strip_existing_marker(lines: list[str]) -> list[str]:
    return [ln for ln in lines if not LIFECYCLE_RE.match(ln)]


def stamp(rel: str, cls: str) -> bool:
    """把檔頭標記寫進檔案（冪等）。回傳是否有變更。"""
    text = _read(rel)
    lines = _strip_existing_marker(text.splitlines())
    marker = marker_line(rel, cls)
    ext = Path(rel).suffix

    insert_at = 0
    if ext == ".plist":
        for i, ln in enumerate(lines[:5]):
            if ln.startswith("<?xml") or ln.startswith("<!DOCTYPE"):
                insert_at = i + 1
    else:
        # .py／.sh —— 放最前面（shebang 之後）。註解不是語句，擺在 module docstring
        # 之前不會讓 docstring 失效（`ast.get_docstring` 仍讀得到）。
        insert_at = 1 if lines and lines[0].startswith("#!") else 0

    new_lines = lines[:insert_at] + [marker] + lines[insert_at:]
    new_text = "\n".join(new_lines) + ("\n" if text.endswith("\n") else "")
    if new_text == text:
        return False
    (ROOT / rel).write_text(new_text, encoding="utf-8")
    _read.cache_clear()
    return True


# ⚠️ 位置債：分類正確、位置不符，但**本輪射程內搬不動**的逐支登記。
# value = 阻擋原因（引用完整性掃描實際找到的射程外活引用）。
# **這個集合只能縮不能長**：新增的位置不符即 CI 紅（偵測器的棘輪）。
def position_debt() -> dict[str, list[str]]:
    """回傳 {路徑: [射程外的活引用位置]}。"""
    refs = literal_path_refs()
    debt: dict[str, list[str]] = {}
    for rel in _git_ls(SCRIPTS_GLOB):
        if Path(rel).name in NON_ENTRY_BASENAMES or rel in POSITION_EXCEPTIONS:
            continue
        cls, _ = classify(rel)
        expected = expected_location(rel, cls)
        current = str(Path(rel).parent) + "/"
        if not expected or expected == current:
            continue
        blockers = sorted({
            loc for loc in refs.get(rel, ())
            if not _is_editable_in_this_card(loc)
            and _ref_surface(loc) not in {"sealed", "scan", "self"}
        })
        debt[rel] = blockers
    return debt


def _ref_surface(loc: str) -> str:
    """引用位置的面別，決定引用完整性**強制不強制**。

    - `sealed`：`docs/control-plane/**`，已於 `8271d7c` 封存唯讀，**永遠改不了**
    - `scan`：掃描器產物 JSON，是當時的快照，過期是歷史事實不是缺陷
    - `historical`：`docs/archive/**` 與卡片交付產物，屬凍結證據，**本卡射程外**
    - `fixture`：`tests/**`，測試裡的合成路徑；真實路徑壞掉 pytest 自己會紅（更強的機制）
    - `self`：掃描器自身的說明範例
    - `enforced`：其餘（`scripts/`、`src/`、活契約與設計文件）——**壞了就 CI 紅**
    """
    path = loc.rsplit(":", 1)[0]
    if path in SELF_REFERENCE:
        return "self"
    if path.startswith("docs/control-plane/"):
        return "sealed"
    if path.startswith("docs/research/") and path.endswith(".json"):
        return "scan"
    if path.startswith(("docs/archive/", "docs/research/")):
        return "historical"
    if path.startswith("tests/"):
        return "fixture"
    return "enforced"


def _is_editable_in_this_card(loc: str) -> bool:
    """需求方裁定 4：本卡射程只有 `scripts/` 與 `tests/`。"""
    return loc.rsplit(":", 1)[0].startswith(("scripts/", "tests/"))


def broken_enforced_refs() -> list[str]:
    """強制面裡指向不存在檔案的字面路徑。"""
    broken = []
    for path, locations in literal_path_refs().items():
        if (ROOT / path).exists():
            continue
        broken.extend(
            f"{loc} → {path}" for loc in locations if _ref_surface(loc) == "enforced")
    return sorted(broken)


# ============================================================== 分類推導


def derive_class(rel: str) -> tuple[str, str]:
    """位置無關的分類推導。回傳 (class, 判定依據)。

    ⚠️ 刻意不看檔案現在放在哪——否則位置不變式會變成恆真的廢話。
    """
    if rel in scheduled_entries():
        return "standing", "被已安裝排程（plist → shell 鏈）直接或間接呼叫"
    cmds = livedoc_commands().get(rel)
    if cmds:
        return "standing", f"活文件給出可執行指令：{cmds[0]}"
    ci = ci_bindings().get(rel)
    if ci:
        return "ci_guard", f"pytest 機械載入：{', '.join(ci)}"
    if _card_of(rel):
        return "oneshot", f"綁卡 {_card_of(rel)}，且無排程／CI／活文件指令"
    return "", "無任何訊號——fail closed，需具名改判"


@cache
def _card_of(rel: str) -> str:
    """腳本歸屬的卡 ID：優先取宣告表，其次取 module docstring 裡第一個卡 ID。"""
    if rel in ONESHOT_HOME:
        return ONESHOT_HOME[rel]
    parts = Path(rel).parts
    if len(parts) >= 3 and parts[0] == "docs" and parts[1] == "research":
        return parts[2]
    ids = card_ids(_docstring(rel))
    return ids[0] if ids else ""


@cache
def _docstring(rel: str) -> str:
    src = _read(rel)
    if rel.endswith(".py"):
        try:
            return ast.get_docstring(ast.parse(src)) or ""
        except SyntaxError:
            return ""
    # shell / plist：取開頭的註解區塊
    lines = []
    for line in src.splitlines()[:40]:
        stripped = line.strip()
        if LIFECYCLE_TOKEN in stripped:      # 標記是本檔產生的，不得回頭當成宣告來源
            continue
        if stripped.startswith("#") and not stripped.startswith("#!"):
            lines.append(stripped.lstrip("# ").rstrip())
        elif lines and not stripped:
            break
    return "\n".join(lines)


def classify(rel: str) -> tuple[str, str]:
    override = CLASS_OVERRIDES.get(rel)
    if override:
        return override[0], f"人工改判：{override[1]}"
    return derive_class(rel)


def expected_location(rel: str, cls: str) -> str:
    if rel in POSITION_EXCEPTIONS:
        return str(Path(rel).parent) + "/"
    if cls == "standing":
        return "scripts/"
    if cls == "ci_guard":
        return "scripts/ci/"
    if cls == "product_pending":
        return str(Path(rel).parent) + "/"
    home = ONESHOT_HOME.get(rel) or _card_of(rel)
    return f"docs/research/{home}/" if home else ""


# ==================================================== `--help` 靜態安全性
#
# 判準沿用 `tests/test_cli_help_guard.py`：「argv 必須在主流程觸及任何 I/O 出口之前
# 被解析，未知旗標必須非零退出」。CLI 側該檔已用**執行期密封探針**證明；`scripts/`
# 側因本卡紅線不得執行任何腳本，改以**靜態**近似——限度誠實寫在清冊裡。


SHELL_ARGV_GUARD_RE = re.compile(r"(getopts|--help\)|-h\s*\||usage\(\)|\bcase\s+\"?\$\{?1)")


def help_safety(rel: str) -> tuple[str, str]:
    """回傳 (狀態, 說明)。狀態 ∈ {safe, unsafe, n/a}。"""
    if rel.endswith(".plist"):
        return "n/a", "plist 是排程宣告，不是可打指令的入口"
    if rel.endswith(".sh"):
        # ⚠️ shell 沒有 argparse，但「打錯參數會不會照跑」的問題完全一樣：
        # `scrape-daily.sh --help` 會把 `--help` 當成 `$1` 吞掉並跑完整每日爬取。
        if SHELL_ARGV_GUARD_RE.search(_read(rel)):
            return "safe", "有明示的 argv 守衛（getopts／case $1／usage）"
        return "unsafe", "無 argv 守衛：未知參數會被吞掉或忽略，主流程照跑"
    src = _read(rel)
    if "argparse" not in src or "parse_args" not in src:
        return "unsafe", "無 argparse：任何旗標（含 --help）都會落進主流程"
    graph = _graph_of(rel)
    entry_calls = graph.calls.get("main", set()) | graph.module_calls
    if "parse_args" not in entry_calls and not any(
        "parse_args" in graph.calls.get(fn, set()) for fn in entry_calls
    ):
        return "unsafe", "有 argparse 但入口未在主流程前呼叫 parse_args"
    return "safe", "argparse 於主流程前解析 argv"


# ================================================== 引用完整性（不變式 2）


_LITERAL_PATH_RE = re.compile(r"(?<![\w./-])(scripts/[\w./-]+\.(?:py|sh|plist))(?![\w.-])")
# ⚠️ 分段路徑：`"scripts/" + name`、`ROOT / "scripts" / name` 這種無法靜態解析的形式
# 必須被**看見**並回報，不能因為正則抓不到就當作沒有（已知錯誤 4「分段路徑假陰性」）。
_SPLIT_PATH_RE = re.compile(r"""["']scripts/?["']\s*(?:\+|/|,)|["']scripts["']\s*(?:\+|/|,)""")


def literal_path_refs() -> dict[str, list[str]]:
    """全庫 `scripts/<name>.<ext>` 字面路徑 → 出現位置（`檔案:行號`）。"""
    refs: dict[str, list[str]] = defaultdict(list)
    for rel in _tracked_files():
        if rel.startswith(".ai-workflow") or _is_binary(rel):
            continue
        for lineno, line in enumerate(_read(rel).splitlines(), 1):
            for m in _LITERAL_PATH_RE.finditer(line):
                refs[m.group(1)].append(f"{rel}:{lineno}")
    return dict(refs)


def split_path_sites() -> list[str]:
    """靜態解析不了的分段路徑組裝點——列出來，不假裝不存在。"""
    sites = []
    for rel in _tracked_files():
        if not rel.endswith((".py", ".sh")) or _is_binary(rel):
            continue
        for lineno, line in enumerate(_read(rel).splitlines(), 1):
            if _SPLIT_PATH_RE.search(line):
                sites.append(f"{rel}:{lineno}")
    return sites


def _is_binary(rel: str) -> bool:
    return Path(rel).suffix in {".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".pdf"}


# ================================================================ 入口模型


@dataclass
class Entry:
    ident: str
    surface: str
    kind: str
    cls: str
    cls_reason: str
    location: str
    expected: str
    card: str
    purpose_declared: str
    writes_ast: bool | None      # None ＝ W1 對此入口不適用（shell／plist）
    writes_sql: bool
    writes: bool
    writes_note: str
    help_state: str
    help_note: str
    refs_live: tuple[str, ...]
    refs_ci: tuple[str, ...]
    scheduled: bool
    marker: str = ""


def _first_sentence(text: str, limit: int = 150) -> str:
    text = " ".join(text.strip().split())
    if not text:
        return ""
    for sep in ("。", ". ", "；"):
        if sep in text[:limit]:
            text = text[: text.index(sep) + (1 if sep == "。" else 0)]
            break
    return text[:limit].strip()


def _cli_entry_module(target: str) -> str | None:
    return _src_module_path(target.split(":")[0])


def build_entries() -> list[Entry]:
    entries: list[Entry] = []

    file_paths = [p for p in _git_ls(SCRIPTS_GLOB) if Path(p).name not in NON_ENTRY_BASENAMES]
    file_paths += _git_ls(RESEARCH_GLOB)

    for rel in sorted(set(file_paths)):
        cls, reason = classify(rel)
        w1 = writes_ast(rel) if rel.endswith(".py") else None
        w2 = writes_sql(rel)
        verdict, note = _adjudicate(rel, w1, w2)
        state, hnote = help_safety(rel)
        entries.append(Entry(
            ident=rel,
            surface="scripts" if rel.startswith("scripts/") else "research",
            kind=Path(rel).suffix.lstrip("."),
            cls=cls,
            cls_reason=reason,
            location=str(Path(rel).parent) + "/",
            expected=expected_location(rel, cls),
            card=_card_of(rel),
            purpose_declared=_first_sentence(_docstring(rel)),
            writes_ast=w1,
            writes_sql=w2,
            writes=verdict,
            writes_note=note,
            help_state=state,
            help_note=hnote,
            refs_live=livedoc_commands().get(rel, ()),
            refs_ci=ci_bindings().get(rel, ()),
            scheduled=rel in scheduled_entries(),
            marker=lifecycle_marker(rel),
        ))

    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    for name, target in sorted(cfg["project"]["scripts"].items()):
        rel = _cli_entry_module(target)
        w1 = writes_ast(rel) if rel else False
        w2 = writes_sql(rel) if rel else False
        verdict, note = _adjudicate(name, w1, w2)
        state, hnote = _cli_help_state(target)
        entries.append(Entry(
            ident=name,
            surface="cli",
            kind="cli",
            cls="standing",
            cls_reason="pyproject [project.scripts] 註冊的常設 CLI",
            location="pyproject.toml",
            expected="pyproject.toml",
            card="",
            purpose_declared=_first_sentence(_docstring(rel)) if rel else "",
            writes_ast=w1,
            writes_sql=w2,
            writes=verdict,
            writes_note=note,
            help_state=state,
            help_note=hnote,
            refs_live=(),
            refs_ci=(),
            scheduled=False,
        ))
    return entries


def _adjudicate(ident: str, w1: bool | None, w2: bool) -> tuple[bool, str]:
    """w1 為 None ＝ W1 對此入口結構性不適用（shell／plist 沒有 Python AST）。"""
    if w1 is None:
        ruling = SINGLE_CRITERION_OVERRIDE.get(ident)
        if ruling is not None:
            return ruling[0], f"⚠️ 單一判準覆寫（W2={w2}，W1 不適用）：{ruling[1]}"
        return w2, "⚠️ 單一判準（W1 不適用於 shell／plist，此格無交叉複算）"
    if w1 == w2:
        return w1, "兩判準一致"
    ruling = WRITE_ADJUDICATION.get(ident)
    if ruling is None:
        return False, "⚠️ 未裁定的判準不一致（偵測器會擋）"
    return ruling[0], f"人工裁定（W1={w1}／W2={w2}）：{ruling[1]}"


def stale_adjudications() -> list[str]:
    """兩判準現在已經一致、卻還留著裁定條目的——過期，該刪。

    ⚠️ 這是刻意加的：`roadmap_lines.py` 的 `GATE_OVERRIDES` 被 `#137` 判為缺陷的理由
    就是「硬編的逐卡說明文字，沒有到期或真實性來源」。本表不重演那個病。
    """
    stale = []
    for entry in build_entries():
        if entry.ident in WRITE_ADJUDICATION and entry.writes_ast == entry.writes_sql:
            stale.append(entry.ident)
        if entry.ident in SINGLE_CRITERION_OVERRIDE and entry.writes_ast is not None:
            stale.append(entry.ident)
    return sorted(set(stale))


def undecided_disagreements() -> list[str]:
    """兩判準不一致但沒有人工裁定的——fail closed。"""
    return sorted(
        e.ident for e in build_entries()
        if e.writes_ast is not None and e.writes_ast != e.writes_sql
        and e.ident not in WRITE_ADJUDICATION
    )


# CLI 側的 `--help` 安全性沿用 `tests/test_cli_help_guard.py` 的執行期證明，
# 不另立判準：被該檔涵蓋＝安全，被 FROZEN_MODULES 排除＝具名例外。
CLI_GUARD_PACKAGES = ("cpbl.ingest.", "cpbl.models.", "cpbl.features.")
CLI_GUARD_FROZEN = {"cpbl.ingest.run_refresh_recent", "cpbl.ingest.cpbl_pitch_tracking"}


def _cli_help_state(target: str) -> tuple[str, str]:
    module = target.split(":")[0]
    if module in CLI_GUARD_FROZEN:
        return "unsafe", "⚠️ --help 不安全（#53 凍結）；tests/test_cli_help_guard.py 明文排除"
    if module.startswith(CLI_GUARD_PACKAGES):
        return "safe", "tests/test_cli_help_guard.py 以執行期密封探針證明零副作用"
    return "unknown", "不在 test_cli_help_guard.py 的涵蓋套件內"


def write_capable_unsafe(entries: list[Entry]) -> list[Entry]:
    """不變式 3 的違反者：判定為寫入型且 `--help` 不安全。"""
    return [e for e in entries if e.writes and e.help_state == "unsafe"]


# ================================================================== 渲染


def _runnable(e: Entry) -> str:
    if e.ident in HELP_SAFETY_ALLOWLIST:
        return "⚠️ --help 不安全（具名例外）"
    if e.help_state == "unsafe":
        return "⚠️ --help 不安全"
    if e.help_state == "n/a":
        return "—"
    if e.help_state == "unknown":
        return "❔ 未涵蓋"
    return "✅ --help 安全"


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render() -> str:
    entries = build_entries()
    out: list[str] = []
    a = out.append

    a("# scripts/ 可執行入口清冊")
    a("")
    a("> [!warning] 本檔由 `scripts/script_inventory.py` **自動產生**，勿手改。")
    a("> 重新產生：`uv run python scripts/script_inventory.py --write`")
    a("> 同步偵測器：`tests/test_script_inventory.py`（CI 於每個 PR 與 push main 執行）。")
    a("")
    a("卡片：`DEV-SCRIPT-INVENTORY1`。射程＝三個入口面："
      "`scripts/**`、`docs/research/**/*.py`、`pyproject [project.scripts]`。")
    a("")

    # ---- 分類與位置的規則
    a("## 分類：四類，各自回答「能不能跑、能不能刪」")
    a("")
    a("| 分類 | 檔頭標記 | 應在的位置 | 可以刪嗎 | 可以跑嗎 |")
    a("|---|---|---|---|---|")
    a("| **常設工具** | `standing` | `scripts/` 頂層 | 不行 | **可以，這就是給你跑的** |")
    a("| **CI 繫結守衛** | `ci_guard` | `scripts/ci/` | 不行，刪了 CI 會紅 | **不必，CI 會跑** |")
    a("| **一次性產物** | `oneshot` | `docs/research/<CARD-ID>/` | 要需求方裁定 | **不要** |")
    a("| **待產品裁定** | `product_pending` | 不動 | 待裁 | 待裁 |")
    a("")
    a("分類推導**與檔案現在放在哪無關**（否則不變式會變成恆真的廢話）："
      "排程可達 → 常設；活文件給出可執行指令 → 常設；pytest 機械載入 → CI 繫結；"
      "綁卡且無上述訊號 → 一次性產物；**四項皆無 → fail closed，須具名改判**。")
    a("")

    # ---- 不變式 1：檔頭標記
    a("## 檔案系統上可分辨：檔頭標記（不變式 1）")
    a("")
    a("`scripts/**` 的每一支都在檔頭帶一行 `LIFECYCLE:`，內容必須等於機械推導出來的分類：")
    a("")
    a("```")
    a("# LIFECYCLE: oneshot · 卡片一次性產物——不要跑；刪除須需求方裁定（INGEST-DEEP-TM-BACKFILL1）")
    a("```")
    a("")
    a("**新增腳本沒標、或標錯 → CI 紅。** `docs/research/<CARD-ID>/` 那一面靠**位置本身**"
      "分辨，不需要標記。")
    a("")
    a("> [!note] 限度：檔頭標記 `ls` 看不到，要開檔才看得到。")
    a("> GitHub 在目錄列表直接渲染本檔（`scripts/README.md`），"
      "所以**瀏覽 `scripts/` 的人不必先知道清冊存在**——但在終端機 `ls` 的人仍看不出差別。")
    a("")

    # ---- 不變式 2：位置棘輪
    debt = position_debt()
    a("## 位置棘輪（不變式 2）——⚠️ 規劃階段的搬遷計畫被不變式 3 否決")
    a("")
    a("規劃階段的方案是把一次性產物 `git mv` 進 `docs/research/<CARD-ID>/`、"
      "CI 繫結守衛移入 `scripts/ci/`。**引用完整性掃描一跑就否決了它**：")
    a("")
    a(f"- 該搬的共 **{len(debt)}** 支；其中 **{sum(1 for b in debt.values() if b)}** 支的活引用"
      "落在本卡射程（`scripts/` ＋ `tests/`）之外")
    a("- 阻擋的引用絕大多數是**凍結證據文件裡的重現指令**"
      "（`docs/research/<CARD>_RESULTS.md` 的「重現方法：`uv run python scripts/x.py …`」），"
      "另有 `src/` 的 docstring 與 3 張活卡的 spec 檔")
    a("- 搬走而不同步 ＝ **親手弄壞歷史證據的重現指令**，"
      "與 `data_tie_remedy1.py` 的 `FROZEN_FILES` 被抓到的是同一種傷害")
    a(f"- 只搬「免費的 {sum(1 for b in debt.values() if not b)} 支」會製造**更糟的假訊號**："
      "一個只裝了部分成員的 `scripts/ci/`，會讓留在 `scripts/` 的其餘同類看起來像常設工具")
    a("")
    a("**所以本輪零搬動。** 位置債逐支登記如下，**這個集合只能縮不能長**"
      "——新增的位置不符即 CI 紅。後續卡以正確射程（含 `docs/research/`、`src/`、他卡 spec）執行時，"
      "本表就是工單。")
    a("")
    a("| 入口 | 分類 | 應在 | 射程外活引用（阻擋原因） |")
    a("|---|---|---|---|")
    for rel in sorted(debt):
        cls, _ = classify(rel)
        blockers = debt[rel]
        shown = "、".join(f"`{b}`" for b in blockers[:3])
        if len(blockers) > 3:
            shown += f"　…另 {len(blockers) - 3} 處"
        a(f"| `{Path(rel).name}` | {CLASS_LABELS.get(cls, '?')} | `{expected_location(rel, cls)}`"
          f" | {shown or '**無**——射程內可搬，但為避免部分搬動造成假訊號，本輪一併保留'} |")
    a("")

    # ---- 欄位語意
    a("## 欄位語意（哪些有機械讀者，哪些沒有）")
    a("")
    a("| 欄位 | 來源 | 過期時誰會知道 |")
    a("|---|---|---|")
    a("| `分類`／`檔頭標記` | 機械推導 | **CI**——集合漂移、標記與分類不符即紅 |")
    a("| `寫入` | W1 AST call-graph ＋ W2 正則 SQL 掃描交叉複算 | **CI**——新的判準不一致即紅 |")
    a("| `runnable` | 靜態 argv 守衛偵測（CLI 側沿用 `test_cli_help_guard.py` 的執行期證明） | **CI** |")
    a("| `purpose_declared` | module docstring 首句，機械抽取 | **CI**——與原始碼不符即紅 |")
    a("| `purpose_verified` | **人工維護** | ⚠️ **沒有機械讀者，會過期** |")
    a("")
    a("> [!warning] `purpose_verified` 是人工欄：**沒有任何機器分得出它是否還為真**。")
    a("> 改了函式本體而不動 docstring 與參數，本清冊不會響。"
      "本欄只保證「有人在某個時點讀過碼」，不保證「現在仍為真」。")
    a("")

    # ---- 三面計數
    counts = defaultdict(int)
    for e in entries:
        counts[e.surface] += 1
    a("## 計數對帳")
    a("")
    a(f"- `scripts/**`：**{counts['scripts']}**")
    a(f"- `docs/research/**/*.py`：**{counts['research']}**")
    a(f"- `pyproject [project.scripts]`：**{counts['cli']}**")
    a(f"- **三面總和：{sum(counts.values())}**")
    a("")
    by_cls = defaultdict(int)
    for e in entries:
        if e.surface != "cli":
            by_cls[e.cls] += 1
    a("檔案面分類分佈："
      + "、".join(f"{CLASS_LABELS.get(k, k or '未分類')} {v}" for k, v in sorted(by_cls.items())))
    a("")

    # ---- 寫入面交叉複算
    both = [e for e in entries if e.writes_ast is not None]
    single = [e for e in entries if e.writes_ast is None]
    disagree = [e for e in both if e.writes_ast != e.writes_sql]
    a("## 寫入面：兩套獨立判準交叉複算")
    a("")
    a("- **W1（AST call-graph）**：從入口函式沿呼叫圖走，是否**可達**一個含寫入 SQL 的函式。"
      "跨 `src/cpbl/**` 模組傳遞。")
    a("- **W2（正則 SQL 掃描）**：入口的 import 閉包內，是否**存在**含寫入 SQL 動詞的字串字面。"
      "不看呼叫圖。")
    a("")
    a("**不取聯集也不取交集**：聯集會把「只是 import 了一個含寫入函式的模組」誤判成寫入者；"
      "交集會漏掉「呼叫 `build_splits()` 但自己一行 SQL 都沒有」的真寫入者。"
      "不一致者逐支人工裁定，出現**未裁定的新不一致**即 CI 紅，"
      "**裁定條目過期**（兩判準已一致）也會 CI 紅——後者是刻意的，"
      "`roadmap_lines.py` 的 `GATE_OVERRIDES` 被 `#137` 判為缺陷的理由正是「沒有到期來源」。")
    a("")
    a(f"- 兩判準皆適用：**{len(both)}** 支，其中不一致 **{len(disagree)}** 支（全部已裁定）")
    a(f"- **只有一套判準：{len(single)}** 支（`.sh`／`.plist` 沒有 Python AST，W1 結構性不適用）"
      "——**這一格沒有交叉複算**，不假裝有")
    a(f"- 判定為寫入型：**{sum(1 for e in entries if e.writes)}** 支"
      f"（`scripts/**` {sum(1 for e in entries if e.writes and e.surface == 'scripts')}、"
      f"`docs/research/` {sum(1 for e in entries if e.writes and e.surface == 'research')}、"
      f"CLI {sum(1 for e in entries if e.writes and e.surface == 'cli')}）")
    a("")
    a("> [!important] **W1 有一個結構性盲點，而它剛好落在最危險的那支上。**")
    a("> `docs/research/INGEST-DEEP-TM-BACKFILL1/sync_deep_tm_prod.py` 把 "
      "`COPY` ＋ `UPDATE cpbl.pitch_tracking` 透過 "
      "`subprocess.run(['ssh', VPS, …'psql'], input=…)` 串進**生產**——")
    a("> 寫入完全不經過 Python 的 DB cursor，**AST 呼叫圖看不到**，只有 W2 掃字面抓得到。")
    a("> 這一支就是「為什麼要兩套判準」的答案。")
    a("")
    a("### 不一致清單（逐支人工裁定）")
    a("")
    a("| 入口 | W1 AST | W2 SQL | 裁定 | 理由 |")
    a("|---|---|---|---|---|")
    for e in sorted(disagree, key=lambda x: x.ident):
        ruling = WRITE_ADJUDICATION.get(e.ident)
        reason = ruling[1] if ruling else "⚠️ **未裁定**"
        a(f"| `{e.ident}` | {'寫' if e.writes_ast else '唯讀'} | {'寫' if e.writes_sql else '唯讀'}"
          f" | {'**寫**' if e.writes else '唯讀'} | {_md_escape(reason)} |")
    a("")
    a("### 單一判準（`.sh`／`.plist`，無交叉複算）")
    a("")
    a("| 入口 | W2 SQL | 裁定 | 說明 |")
    a("|---|---|---|---|")
    for e in sorted(single, key=lambda x: x.ident):
        ruling = SINGLE_CRITERION_OVERRIDE.get(e.ident)
        note = ruling[1] if ruling else "W2 單獨採信"
        a(f"| `{Path(e.ident).name}` | {'寫' if e.writes_sql else '唯讀'}"
          f" | {'**寫**' if e.writes else '唯讀'} | {_md_escape(note)} |")
    a("")

    # ---- 不變式 3：引用完整性
    refs = literal_path_refs()
    by_surface: dict[str, int] = defaultdict(int)
    broken: dict[str, list[str]] = defaultdict(list)
    for path, locs in refs.items():
        exists = (ROOT / path).exists()
        for loc in locs:
            surf = _ref_surface(loc)
            by_surface[surf] += 1
            if not exists:
                broken[surf].append(f"{loc} → {path}")
    a("## 引用完整性（不變式 3）")
    a("")
    a(f"全庫 `scripts/<name>.<ext>` 字面路徑共 **{sum(by_surface.values())}** 處。"
      "**只有 `enforced` 那一面強制**——其餘的過期是歷史事實不是缺陷：")
    a("")
    a("| 面別 | 處數 | 強制？ | 為什麼 |")
    a("|---|---:|---|---|")
    surface_why = {
        "enforced": ("✅ 強制", "`scripts/`、`src/`、活契約與設計文件——壞了就是現在的缺陷"),
        "historical": ("回報", "`docs/archive/**` 與卡片交付產物＝凍結證據，**本卡射程外**"),
        "sealed": ("回報", "`docs/control-plane/**` 已於 `8271d7c` 封存唯讀，**永遠改不了**"),
        "scan": ("回報", "掃描器產物 JSON 是當時的快照"),
        "fixture": ("不適用", "`tests/**` 的合成路徑；真實路徑壞掉 pytest 自己會紅（更強的機制）"),
        "self": ("不適用", "掃描器自身的說明範例"),
    }
    for surf in sorted(by_surface, key=lambda s: -by_surface[s]):
        enforce, why = surface_why.get(surf, ("?", ""))
        a(f"| `{surf}` | {by_surface[surf]} | {enforce} | {why} |")
    a("")
    for surf in ("enforced", "historical"):
        items = sorted(set(broken.get(surf, [])))
        if not items:
            continue
        label = "⚠️ **強制面**" if surf == "enforced" else "歷史面（僅回報）"
        a(f"**壞路徑——{label}（{len(items)}）**：")
        a("")
        for item in items:
            a(f"- `{item}`")
        a("")
    a("> [!important] 這條不變式是被 `scripts/data_tie_remedy1.py` 的 `FROZEN_FILES` "
      "逼出來的——它以**字面路徑**硬編兩支一次性產物，而 CI 只 import `_streaks_for` "
      "碰不到 `is_frozen`。搬走那兩支會讓守衛靜默回 `False`，零訊號。")
    a("> **現在搬走它們會讓 CI 紅**，這就是那個缺陷的修法。")
    a("")

    # ---- 不變式 4
    a("## 寫入型必須 `--help` 安全（不變式 4）")
    a("")
    a("判定為寫入型的入口，argv 必須在主流程前被解析。**既有不合格者具名列入 allowlist**"
      "——本輪只加不變式、不改既有腳本行為（那會讓本卡從盤點變成改一批腳本）。")
    a("")
    a("| 入口 | 理由與去向 |")
    a("|---|---|")
    for ident, reason in sorted(HELP_SAFETY_ALLOWLIST.items()):
        a(f"| `{ident}` | {_md_escape(reason)} |")
    a("")
    a("> [!note] 判準沿用 `tests/test_cli_help_guard.py`，不另立一套。")
    a("> CLI 側該檔以**執行期密封探針**證明（所有 I/O 出口 stub 化後才呼叫 `main()`）；")
    a("> `scripts/` 側因本卡紅線**不得執行任何腳本**，改以**靜態**近似："
      "「有 argparse 且入口在主流程前呼叫 `parse_args`」。")
    a("> **限度**：靜態判準證明不了「parse_args 之後才有副作用」，只證明 argv 有被解析。")
    a("")

    # ---- 逐支清冊
    for surface, title in (("scripts", "`scripts/**`"), ("research", "`docs/research/**/*.py`")):
        rows = [e for e in entries if e.surface == surface]
        a(f"## 清冊：{title}（{len(rows)}）")
        a("")
        a("| 入口 | 分類 | 位置 | 應在 | 寫入 | runnable | 卡 | purpose_declared | purpose_verified |")
        a("|---|---|---|---|---|---|---|---|---|")
        for e in sorted(rows, key=lambda x: (x.cls, x.ident)):
            verified = PURPOSE_VERIFIED.get(e.ident, "")
            misplaced = e.expected and e.expected != e.location
            a(f"| `{Path(e.ident).name}` | {CLASS_LABELS.get(e.cls, '⚠️未分類')}"
              f" | `{e.location}` | {'⚠️ `' + e.expected + '`' if misplaced else '✅'}"
              f" | {'**寫**' if e.writes else '唯讀'} | {_runnable(e)}"
              f" | {e.card or '—'} | {_md_escape(e.purpose_declared) or '—'}"
              f" | {_md_escape(verified) or '⚠️ 未查證'} |")
        a("")

    cli_rows = [e for e in entries if e.surface == "cli"]
    a(f"## 清冊：`pyproject [project.scripts]`（{len(cli_rows)}）")
    a("")
    a("| CLI | 寫入 | runnable | purpose_declared | purpose_verified |")
    a("|---|---|---|---|---|")
    for e in sorted(cli_rows, key=lambda x: x.ident):
        verified = PURPOSE_VERIFIED.get(e.ident, "")
        a(f"| `{e.ident}` | {'**寫**' if e.writes else '唯讀'} | {_runnable(e)}"
          f" | {_md_escape(e.purpose_declared) or '—'}"
          f" | {_md_escape(verified) or '⚠️ 未查證'} |")
    a("")

    # ---- 已知陷阱
    a("## 已知陷阱（疑似重複群組的裁定結果）")
    a("")
    for group, text in KNOWN_TRAPS:
        a(f"### {group}")
        a("")
        a(text)
        a("")

    # ---- 位置例外與觀測面
    a("## 位置例外（分類正確但刻意不搬）")
    a("")
    a("| 入口 | 理由 |")
    a("|---|---|")
    for ident, reason in sorted(POSITION_EXCEPTIONS.items()):
        a(f"| `{ident}` | {_md_escape(reason)} |")
    a("")

    a("## 觀測面限制")
    a("")
    a("- **「未找到消費者」不等於「沒有消費者」**：本清冊的觀測面只有 **git 追蹤檔案**。"
      "本機執行歷史、需求方手動操作、封存前的口頭流程都不在裡面。用詞一律「未找到」。")
    a("- **本輪零刪除**。已用盡的只標記，刪除是需求方的獨立裁定。")
    a("- 位置不變式證明的是「位置與分類一致」，**不是「分類是對的」**。"
      "分類含具名人工改判，機器只驗一致性不驗真假。")
    split_sites = split_path_sites()
    if split_sites:
        a(f"- **分段路徑**（`\"scripts/\" + name` 這類靜態解析不了的組裝）共 "
          f"{len(split_sites)} 處，引用完整性檢查涵蓋不到，逐處列出："
          + "、".join(f"`{s}`" for s in split_sites))
    a("")
    return "\n".join(out) + "\n"


# 疑似重複群組的裁定（Discovery 已完成，寫進清冊供讀者不必回頭翻卡）。
KNOWN_TRAPS: tuple[tuple[str, str], ...] = (
    ("TM 四支：不是重複，但參數不一致",
     "`reconcile_game_tm`（Gate 2：單場 API vs 逐投手 logs API）、"
     "`dryrun_game_tm_fullseason`（G4 Phase A：單場 API vs 正式表存量）、"
     "`verify_deep_tm_backfill`（本機 DB vs 生產 DB）、"
     "`sync_deep_tm_prod`（寫生產）——四個不同的對照兩端，零重疊。\n\n"
     "⚠️ **四支全部把年份釘死 2026**（前兩支是 argparse 預設，後兩支是 SQL 字面），"
     "且 `reconcile_game_tm` 預設 `--kind A`、`dryrun_game_tm_fullseason` 預設 `--kinds A D`"
     "——**對同一批資料的預設母體不同，而差異沒寫在任何一支的 docstring 裡**。"),
    ("`reconcile_*` 字首同時指涉唯讀對帳與破壞性重建",
     "`reconcile_game_tm` 與 `reconcile_scoreless_streak` 是**純唯讀**；"
     "`reconcile_splits_recalc1 --apply` 會**實際呼叫 `build_splits()` 重建 2018–2026 A/D**。"
     "檔名看不出這個差別——本清冊的「寫入」欄是唯一分得出來的地方。"),
    ("splits 三支：診斷 → 報告守衛 → 修復對帳，一條鏈的三段",
     "`verify_splits_pa_split1`（`SET TRANSACTION READ ONLY` 診斷）→ "
     "`check_splits_pa_split1_results`（把 RESULTS.md 的數字對回 artifact）→ "
     "`reconcile_splits_recalc1`（`--apply` 重建）。不是重複。"),
    ("無自責分三支：三個不同層",
     "`reconcile_scoreless_streak`（窮舉對帳，全史 2018+、A＋D）、"
     "`compare_runless_vs_er_streak`（逐人對照，預設只 2026 一軍——差異有寫在 docstring 裡）、"
     "`check_scoreless_null_folding`（AST 靜態掃描，完全不碰 DB）。\n\n"
     "⚠️ `check_scoreless_null_folding` 的 `TARGETS` 是**硬編三個檔案路徑**，"
     "新增的相關檔案不會自動納入，且它**未接上 pytest**——這個守衛從交付至今未被自動跑過。"),
    ("bio 兩支：寫入欄位零重疊",
     "`backfill_player_bio_gap1` 補 `country`／`birthday`；"
     "`backfill_player_bio_gap2` 補 `bats`／`throws`／`height_cm`／`weight_kg`／`debut`／"
     "`education`／`birthplace`／`draft`。不是重複，但檔名 `gap1`／`gap2` 看不出補的是不同欄位。"),
    ("三支自稱守衛但從未接上觸發器",
     "`check_scoreless_null_folding`、`check_splits_pa_split1_results`、`ibb_ghost1_probe` 的"
     " docstring 都自稱「防再犯守衛／不符即 exit 1」，但**沒有任何測試或排程載入它們**。"
     "它們的防護是名義上的——這是「告警沒有讀者等於沒有告警」在腳本層的同構物。"),
)

# ⚠️ 人工欄：沒有機械讀者，會過期。空白＝未查證，**不得靜默填 declared**。
PURPOSE_VERIFIED: dict[str, str] = {
    # --- scripts/ 常設工具 ---
    "scripts/refresh-cpbl-prod.sh": "本機爬完同步生產的主鏈；讀碼確認會呼叫 backup-prod-db.sh 與 verify_refresh_info.py",
    "scripts/scrape-daily.sh": "launchd 每日 10:10 觸發，呼叫 refresh-cpbl-prod.sh 並用 refresh_status.py 記狀態",
    "scripts/backup-prod-db.sh": "備整庫並驗內容門檻（OPS-BACKUP-EMPTY1 的產物，已是常設）",
    "scripts/refresh_status.py": "每日鏈的狀態記錄輔助，唯讀 JSON 檔",
    "scripts/verify_refresh_info.py": "同步後打 /api/info 驗證，唯讀",
    "scripts/workflow_ledger.py": "⚠️ 已於 33c7c3f 加拒絕執行守衛——TASKS.md 已封存，--write 會覆寫封存產物",
    "scripts/review_prompt.py": "查核提示詞產生器；AI_RUNBOOK:433 逐字給指令，18 commits",
    "scripts/roadmap_lines.py": "ROADMAP §1 線別歸屬的機械判定者，fail closed",
    "scripts/pa_transition_taxonomy.py": "canonical taxonomy 的產生器（唯讀）；產物勿手改，改了要重跑",
    "scripts/reconcile_scoreless_streak.py": "窮舉對帳；AI_RUNBOOK:380 寫「改動演算法後必跑」，義務靠人記得",
    "scripts/ability_snapshot.py": "能力值卡回歸抽驗；docstring 明寫改前後各跑一次再 diff",
    "scripts/review_gate_inventory.py": "⚠️ REVIEW_GATE_CONTRACT 宣告「納管＋測試」但實測無測試載入，宣告未落實",
    # --- CLI：高後果／訊號互斥 ---
    "cpbl-refresh-recent": "每日鏈主要寫入者，566 行；⚠️ --help 觸及 cpbl.db.migrate（#53 凍結）",
    "cpbl-research-umpire-impact": "632 行研究入口，零活引用；產物落檔案不落 DB",
    # --- CLI：9 支零活引用，觸發者是人 ---
    "cpbl-classify-pitches-v2": "手動觸發：球種細分 v2，未接排程（memory：二軍／生產未同步）",
    "cpbl-scrape-awards": "手動觸發：官方獎項，卡台灣 IP 需本機探查",
    "cpbl-scrape-coaches-history": "手動觸發：twbsball 隊史教練團，一次抓＋手動刷新",
    "cpbl-scrape-home-runs": "手動觸發：全壘打紀錄",
    "cpbl-scrape-legends": "手動觸發：退役／教練生涯分項",
    "cpbl-scrape-overseas": "手動觸發：旅外資料（twbsball query API）",
    "cpbl-scrape-retired": "手動觸發：退役名單",
    "cpbl-scrape-roster": "手動觸發：登錄名單",
}


# ================================================================== main


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="script_inventory",
        description="產生 scripts/README.md 可執行入口清冊（唯讀，不碰 DB、不連網）",
    )
    p.add_argument("--write", action="store_true", help="覆寫 scripts/README.md")
    p.add_argument("--check", action="store_true", help="與已提交版本比對，不符即非零退出")
    p.add_argument("--stamp", action="store_true",
                   help="把 LIFECYCLE 檔頭標記寫進 scripts/** 的每一支（冪等）")
    return p


def main() -> None:
    args = _parser().parse_args()
    if args.stamp:
        changed = 0
        for rel in _git_ls(SCRIPTS_GLOB):
            if Path(rel).name in NON_ENTRY_BASENAMES:
                continue
            cls, _ = classify(rel)
            if not cls:
                print(f"⚠️ {rel} 無法分類，跳過", file=sys.stderr)
                continue
            changed += stamp(rel, cls)
        print(f"已標記 {changed} 支")
        return
    rendered = render()
    if args.write:
        README_PATH.write_text(rendered, encoding="utf-8")
        print(f"已寫入 {README_PATH.relative_to(ROOT)}")
        return
    if args.check:
        current = README_PATH.read_text(encoding="utf-8") if README_PATH.exists() else ""
        if current != rendered:
            print("scripts/README.md 與產生器輸出不一致；"
                  "請執行 `uv run python scripts/script_inventory.py --write`", file=sys.stderr)
            raise SystemExit(1)
        print("scripts/README.md 與產生器輸出一致")
        return
    sys.stdout.write(rendered)


if __name__ == "__main__":
    main()
