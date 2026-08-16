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
4. **高後果必須 `--help` 安全**：判定為高後果的入口，其 argv 必須在主流程前被解析；
   既有不合格者具名列入 `HELP_SAFETY_ALLOWLIST` 並附理由。
   ⚠️ 這條被改過兩次，兩次都是「判準的**名字**承諾了一致性、**實作**沒有給」：
   先是只問「寫不寫 DB」而漏掉 `backup-prod-db.sh`，接著是名為「接觸遠端」卻只認 SSH
   而漏掉 HTTP（`R2-001`）。現在判準不再認得任何特定的危險名字，改問
   「入口的**呼叫路徑**抵不抵得到出口目錄裡的任一條出口」——見 `SINK_MODULES` 那一段。

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

# 不是「可執行入口」的檔案——具名列出，不用「副檔名不是 .py/.sh 就跳過」這種概括規則
# （概括會靜默吞掉未來真的該被盤點的入口；具名例外壞掉時看得見）。
#
# · README.md：本產生器自己的產物，不可執行。
# · schedule-registry.json：`schedule_watch.py` 讀的**純資料**（排程節奏宣告）。它沒有
#   shebang、不可執行，而且 JSON 語法上就放不下 `LIFECYCLE:` 註解——留在盤點面裡的話，
#   不變式 1（檔頭標記）在它身上**永遠不可能為真**。它被 CI 繫結（測試載入它）故推導
#   會判 `ci_guard` 並要求搬到 `scripts/ci/`，但那個結論的前提是「它是入口」，而它不是。
#   它必須與消費它的 `schedule_watch.py` 同目錄：後者刻意走系統 `/usr/bin/python3`、
#   不經 venv（見該檔隔離說明），所以拿不到套件資源，只能用相對路徑讀檔。
NON_ENTRY_BASENAMES = {"README.md", "schedule-registry.json"}

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

# ================================================ 出口目錄：不變式 4 的判準
#
# ⚠️ **這一段被改過兩次，兩次都是同一種病。**
#
# 第一次：判準問「這支會不會寫 DB」，`backup-prod-db.sh` 從縫隙掉出去——它對 DB
# 唯讀（`pg_dump`），但 `--help` 會 ssh 進生產跑整庫 dump、exit 0、`rm -f` 掉輪替
# 視窗最舊的那份。於是判準加寬成「寫 DB **或** ssh **或** rm -f」。
#
# 第二次（`DEV-SCRIPT-INVENTORY1-R2-001`）：加寬後的判準**名字**叫「接觸遠端」，
# **實作**只認 SSH——`confirm_live_schema.py` 的 `--help` 會把 `--help` 當成 game ID
# 拼進 URL 對 `stats.cpbl.com.tw` 發真實請求，還可能覆寫該卡凍結的 `request_log.json`
# （那份 artifact 逐字宣稱「本卡總共發出 1 次請求」），而判準看不到它。
#
# **第二次不能再用「加一條正則」修**，否則下一輪就是「高後果 ＋ HTTP ＋ 下一個」。
# 判準改成兩件事分開：
#
#   1. **出口是什麼**——由下面這張表定義。損害的定義是「這個行程對**外部世界**
#      造成的改變」，而一個 Python 行程能影響外部世界的通道是可窮舉的：DB driver、
#      網路、檔案系統的破壞性操作、以及把前三者外包出去的 shell。表裡每一條出口
#      只有兩種形狀：
#        (a) `SINK_MODULES`：**具名函式庫綁定**——import 了它、呼叫它，本身就是效果
#        (b) `RUNNER_PAYLOAD`：**泛用執行器的參數**——`subprocess`／`os.system` 本身
#            無害，效果由參數內容決定
#      寫 DB 從來就是 (b) 的一個實例（`cursor.execute(<寫入 SQL>)`），HTTP 是 (a) 的
#      一個實例。**新增一條出口＝在這張表加一列，不是再寫一套掃描。**
#
#   2. **入口碰不碰得到那個出口**——由 `reachable_effects()` 回答，而它就是 W1
#      （`writes_ast`）用的同一台 AST 呼叫圖引擎。`writes_ast` 現在是
#      `reachable_effects(rel) ∋ "db_write"` 的別名，兩者不可能再各自演化。
#
# ⚠️ **為什麼不掃 import 閉包**（W2 的射程，也是本函式改版前對 `.py` 用的射程）：
# `httpx` 在 `cpbl.*` 的相依圖裡到處都是，掃閉包會把「只 import 了一個常數」的
# 唯讀腳本判成打網路的。最刺眼的一支是 `check_splits_pa_split1_results.py`：它從
# `cpbl.ingest.cpbl_player_detail` 只 import 了 `APART_COMBOS` 這個 list 常數，
# 閉包法照樣判它打網路，呼叫圖法不命中。**誤判要靠 allowlist 消化，而每多一條
# allowlist 就離 `GATE_OVERRIDES` 近一步**——所以這裡要的是精確，不是寬。
#
# ⚠️ 兩法的差額**不寫死成數字**：數字會過期，而過期的數字就是下一個 `GATE_OVERRIDES`。
# 差額由 `tests/test_script_inventory.py::test_closure_method_is_measurably_less_precise`
# 每次 CI 現算並斷言，該測試同時印出當下的兩邊命中數。
#
# (a) 具名函式庫綁定：呼叫的**點名路徑**（經 import 還原）落在這些前綴下即是出口。
SINK_MODULES: dict[str, tuple[str, ...]] = {
    "http": (
        "httpx", "requests", "urllib.request", "urllib3", "aiohttp",
        "websockets", "playwright", "socket.socket", "socket.create_connection",
    ),
    "remote": ("paramiko", "fabric"),
    "fs_delete": ("shutil.rmtree", "os.remove", "os.unlink", "os.rmdir", "os.removedirs"),
}

# (b) 泛用執行器：`subprocess.run(...)`／`os.system(...)` 這類——效果由**參數內容**決定。
RUNNER_NAMES = frozenset({"run", "call", "check_call", "check_output", "Popen", "system", "popen"})

# ⚠️ 這三條正則**只在執行器的參數上**跑，不對整份檔案跑。差別是決定性的：
# 對整檔跑會讓 docstring 裡寫著 `rm -rf` 的說明變成「這支會刪檔」。
REMOTE_REACH_RE = re.compile(r"(\bssh\b|\bscp\b|\brsync\b[^\n]*:|docker\s+exec\s+prod)")
IRREVERSIBLE_FS_RE = re.compile(r"\brm\s+-[a-z]*[rf]")
HTTP_CLI_RE = re.compile(r"(?<![\w-])(curl|wget)(?![\w-])")

RUNNER_PAYLOAD: dict[str, re.Pattern[str]] = {
    "remote": REMOTE_REACH_RE,
    "fs_delete": IRREVERSIBLE_FS_RE,
    "http": HTTP_CLI_RE,
}

# `db_write` 的出口是 `cursor.execute(<寫入 SQL>)`——形狀同 (b)，只是執行器是 DB
# cursor、payload 正則是 `MUTATING_SQL_RE`。列在這裡是為了讓「出口目錄」真的是**一張**表。
EXECUTOR_PAYLOAD: dict[str, re.Pattern[str]] = {"db_write": MUTATING_SQL_RE}

# 不變式 4 的射程＝這些效果任一可達。`db_write` 走 W1／W2 交叉複算的**裁定結果**
# （見 `_adjudicate`），不在這裡重算——否則人工裁定會被靜默繞過。
HIGH_CONSEQUENCE_EFFECTS = ("db_write", "http", "remote", "fs_delete")

EFFECT_LABELS = {
    "db_write": "寫 DB",
    "http": "對外發出網路請求",
    "remote": "接觸遠端／生產主機",
    "fs_delete": "不可逆刪檔（rm -f／-rf／rmtree）",
}

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
    """單一 Python 檔的函式呼叫圖與**直接**出口點。

    `effects` 取代了舊的 `mutating: set[str]`：同一張圖現在承載所有出口，
    而不是只承載「寫 DB」這一種。`"<module>"` 這個 key 代表模組層（含 `__main__` 區塊）。
    """

    effects: dict[str, set[str]] = field(default_factory=dict)  # 函式 → 直接命中的效果
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


def _dotted_call(func: ast.expr) -> list[str] | None:
    """`a.b.c(...)` → `['a','b','c']`；被呼叫的不是點名路徑（例如 `f()()`）回 None。"""
    parts: list[str] = []
    node: ast.expr = func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return list(reversed(parts))


def _resolve_dotted(parts: list[str], imports: dict[str, str]) -> str:
    """把點名路徑經 import 還原成完整模組路徑。

    `import httpx` ＋ `httpx.Client(...)` → `httpx.Client`；
    `from urllib.request import urlopen` ＋ `urlopen(...)` → `urllib.request.urlopen`。
    """
    origin = imports.get(parts[0])
    if origin is None:
        return ".".join(parts)
    mod, sym = origin.split(":", 1)
    base = mod if sym == "*" else f"{mod}.{sym}"
    return ".".join([base, *parts[1:]])


def _sink_effects(dotted: str) -> set[str]:
    """規則 (a)：還原後的點名路徑落在具名函式庫前綴下 → 該效果。"""
    return {
        effect for effect, prefixes in SINK_MODULES.items()
        if any(dotted == p or dotted.startswith(p + ".") for p in prefixes)
    }


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
        # ⚠️ payload 要看得到**函式區域**的組裝，不能只看模組層常數：
        # `ssh_cmd = ["ssh", ..., VPS]` 這個 repo 裡兩支 ssh 腳本都是這個形狀，
        # 只看模組層常數會漏掉它們。實測納入區域常數對 `db_write` 的判定零影響。
        local_sql: dict[str, str] = dict(const_sql)
        for node in body:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign):
                    text = _sql_from_node(sub.value)
                    for target in sub.targets:
                        if isinstance(target, ast.Name):
                            local_sql[target.id] = local_sql.get(target.id, "") + "\n" + text

        def payload(call: ast.Call, first_only: bool) -> str:
            args = call.args[:1] if first_only else list(call.args)
            text = "\n".join(_sql_from_node(a) for a in args)
            for a in args:
                if isinstance(a, ast.Name):
                    text += "\n" + local_sql.get(a.id, "")
            return text

        for node in body:
            for sub in ast.walk(node):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub is not node:
                    continue
                if not isinstance(sub, ast.Call):
                    continue
                name = _call_name(sub)
                if name:
                    bucket.add(name)

                found: set[str] = set()
                parts = _dotted_call(sub.func)
                if parts:                                   # 規則 (a)：具名函式庫綁定
                    found |= _sink_effects(_resolve_dotted(parts, graph.imports))
                if name in EXECUTE_ATTRS and sub.args:      # 規則 (b)：DB cursor payload
                    text = payload(sub, first_only=True)
                    found |= {e for e, rx in EXECUTOR_PAYLOAD.items() if rx.search(text)}
                if name in RUNNER_NAMES:                    # 規則 (b)：泛用執行器 payload
                    text = payload(sub, first_only=False)
                    found |= {e for e, rx in RUNNER_PAYLOAD.items() if rx.search(text)}
                if found:
                    graph.effects.setdefault(owner or "<module>", set()).update(found)

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


def _effects_of_symbol(symbols: dict[str, frozenset[str]] | dict[str, set[str]],
                       sym: str) -> set[str]:
    """符號 → 效果，且**類別要算上它的方法**。

    ⚠️ 實測抓到的假陰性：`from cpbl.ingest.live_game_worker import StatsLiveSource`
    綁的是裸類別名，而效果記在 `StatsLiveSource.__init__`（`httpx.Client(...)` 在
    建構式裡）。只比對裸名 → `cpbl-live-worker` 被判成不打網路，而它其實會。
    """
    found = set(symbols.get(sym, ()))
    prefix = sym + "."
    for key, effs in symbols.items():
        if key.startswith(prefix):
            found |= set(effs)
    return found


def _external_effects(graph: _ModuleGraph) -> dict[str, set[str]]:
    """本地名 → 它從 `cpbl.*` 帶進來的效果。"""
    external: dict[str, set[str]] = {}
    for local, origin in graph.imports.items():
        mod, sym = origin.split(":", 1)
        if not mod.startswith("cpbl"):
            continue
        symbols = _module_effects(mod)
        if sym == "*":
            # `import cpbl.x`：拿不到用了哪個符號，退回整個模組的聯集（保守，
            # 精確度降回閉包等級）。實測全庫只有 1 處走這條。
            for effs in symbols.values():
                external.setdefault(local, set()).update(effs)
        else:
            effs = _effects_of_symbol(symbols, sym)
            if effs:
                external.setdefault(local, set()).update(effs)
    return external


def _propagate(graph: _ModuleGraph, external: dict[str, set[str]]) -> dict[str, set[str]]:
    """沿呼叫圖把效果往呼叫者傳，直到不動點。"""
    effects = {fn: set(effs) for fn, effs in graph.effects.items()}
    changed = True
    while changed:
        changed = False
        for fn, called in graph.calls.items():
            acc = set(effects.get(fn, set()))
            for name in called:
                # 本檔內建構一個類別：`Foo()` 的效果記在 `Foo.__init__` 底下
                acc |= _effects_of_symbol(effects, name)
                acc |= external.get(name, set())
            if acc != effects.get(fn, set()):
                effects[fn] = acc
                changed = True
    return effects


@cache
def _module_effects(module: str, _depth: int = 0) -> dict[str, frozenset[str]]:
    """`cpbl.*` 模組的符號 → 它可達的效果集合。"""
    rel = _src_module_path(module)
    if rel is None or _depth > 6:
        return {}
    graph = _graph_of(rel)
    external: dict[str, set[str]] = {}
    for local, origin in graph.imports.items():
        mod, sym = origin.split(":", 1)
        if not mod.startswith("cpbl"):
            continue
        symbols = _module_effects(mod, _depth + 1)
        if sym == "*":
            for effs in symbols.values():
                external.setdefault(local, set()).update(effs)
        else:
            effs = _effects_of_symbol(symbols, sym)
            if effs:
                external.setdefault(local, set()).update(effs)

    effects = _propagate(graph, external)
    # ⚠️ **再匯出**：`game_tm_shadow` 只是 `from cpbl.ingest.cpbl_pitch_tracking import _client`，
    # 自己一行 httpx 都沒有，但 `game_tm_shadow._client` 確實會建連線。不補這一步，
    # `replay_schedule_branches.py`（`with _client() as client:` 打六個月賽程 API）
    # 會被判成零效果——實測抓到的假陰性。
    for local, effs in external.items():
        effects.setdefault(local, set()).update(effs)
    return {fn: frozenset(effs) for fn, effs in effects.items() if effs}


def reachable_effects(rel: str, entry_fns: tuple[str, ...] = ("main",)) -> frozenset[str]:
    """入口的**呼叫路徑**可達哪些出口。不變式 4 與 W1 共用的唯一一台引擎。

    ⚠️ 與 import 閉包（W2 的射程）的差別是決定性的：閉包問「相依圖裡有沒有」，
    這裡問「這個入口跑起來碰不碰得到」。`httpx` 在 `cpbl.*` 相依圖裡到處都是，
    閉包法會把只 import 了一個常數的唯讀腳本判成打網路的。
    """
    graph = _graph_of(rel)
    external = _external_effects(graph)
    effects = _propagate(graph, external)

    found = set(effects.get("<module>", set()))
    reach = set(graph.module_calls)
    for fn in entry_fns:
        found |= effects.get(fn, set())
        reach |= graph.calls.get(fn, set())
    seen: set[str] = set()
    while reach:
        name = reach.pop()
        if name in seen:
            continue
        seen.add(name)
        found |= effects.get(name, set())
        found |= external.get(name, set())
        reach |= graph.calls.get(name, set())
    return frozenset(found)


def writes_ast(rel: str, entry_fns: tuple[str, ...] = ("main",)) -> bool:
    """W1：從入口函式出發，AST 呼叫圖是否可達寫入 SQL。

    ⚠️ 這現在只是 `reachable_effects` 的一個投影。刻意不留第二份實作——
    「判準的名字承諾了一致性、實作沒有給」正是 `R2-001` 的成因。
    """
    return "db_write" in reachable_effects(rel, entry_fns)


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
    "docs/research/WP-DISCLOSURE-SYNC1/keyplay_garbage_time.py": (
        False, "唯讀量測：SELECT cpbl.games 與已 published 的打席，算兩種關鍵打席選法"
               "各自選中垃圾時間打席的場次數與 |ΔWP| 分布；唯一寫入是同目錄的 JSON "
               "artifact，不碰 DB"),
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
    "scripts/verify_deep_tm_backfill.py": (
        "判準加寬為「高後果」後**新納入射程**（對 DB 唯讀，但 `VPS` 是裸常數、"
        "任何參數都直接 ssh 進生產跑 psql；改用呼叫圖後另見 `urllib.request.urlopen` "
        "打生產 `/api/info`）。傷害低於同批（唯讀 SELECT），且檔頭"
        "`LIFECYCLE: oneshot` 明寫「不要跑」。去向：修行為需另卡，"
        "母卡 INGEST-DEEP-TM-BACKFILL1 已封存，與 sync_deep_tm_prod.py 同批處理"),
    # --- ⚠️ `confirm_live_schema.py` 與 `replay_schedule_branches.py` 曾在這張表上 ---
    #
    # 本輪 `R2-001` 修法把它們新納入射程後，執行者主張具名放行，判準是
    # 「一次性產物本來就沒人該跑，所以守衛買到的是對一個已被禁止的動作的保護」。
    # **需求方推翻**，三條理由都成立：
    #
    #   1. `--help` 不是「跑它」，是「想知道它是什麼」——那個前提不成立。本 repo 已有
    #      兩次 `--help` 觸發真實爬蟲的事故（`cpbl-scrape-pitches --help` 2026-08-05、
    #      `refresh-cpbl-prod.sh --help` 本週），這會是同形狀的第三次。
    #   2. 「標記＋位置就是防線」正是 `OPS-BACKUP-EMPTY1` 的教訓在修的病：
    #      **檢查看得見的標記，而非該成立的性質**（86 份 20-byte 空檔全部通過 `gzip -t`）。
    #      一行「不要跑」的註解是標記，守衛才是性質——而本輪的主要成果正是把判準從
    #      「命名危險」改成「問呼叫圖」，同一輪不該在隔壁主張註解可以當防線。
    #   3. 加守衛的代價有界（兩個過期行號，且實測不觸發任何檢查——見下），
    #      爬蟲節流升級的代價是整條每日鏈的可用性，且已經發生過。
    #
    # 兩支已改用 `argparse`（`.py` 走靜態判準看得見的那條路，不是 shell 的控制流），
    # 用法涵蓋「在做什麼／會寫什麼／怎麼呼叫」三段，故從本表撤除
    # （`test_invariant_4_allowlist_has_no_stale_entries` 會擋住殘留條目）。
    #
    # ⚠️ 唯一被推翻**不成立**的是執行者的成本論證：他主張加守衛會讓
    # `docs/research/TIME-SEMANTICS-CONTRACT1/inventory.json:84,96` 記的行號失準而付出代價。
    # 行號確實會失準（43/48 → 62/67），但實測**不觸發任何檢查**：引用完整性只認
    # `scripts/<name>.<ext>` 字面路徑，`docs/research/` 下的路徑根本不在觀測面內
    # （`literal_path_refs()` 對 `confirm_live_schema.py` 零命中），而該 JSON 的
    # `_ref_surface` 是 `scan`＝快照，本來就明載「過期是歷史事實不是缺陷」。
    # 成本比他當時估的更小，結論因此更清楚。
    "docs/research/INGEST-DEEP-TM-BACKFILL1/sync_deep_tm_prod.py": (
        "⚠️ **本輪射程內最危險的一支**：完全不看 argv，任何參數都直接 ssh 進生產跑 "
        "`COPY` ＋ `UPDATE cpbl.pitch_tracking`；`VPS` 是裸常數不可覆蓋、無 dry-run、無備份。"
        "已於 `dac8d8e` 移出 `scripts/`（＝瀏覽者不會再誤觸），"
        "但**檔案本身的行為沒變**。去向：修行為需另卡，母卡 INGEST-DEEP-TM-BACKFILL1 已封存"),
    # --- 排程用的 shell ---
    # `refresh-cpbl-prod.sh`／`scrape-daily.sh`／`weekly-game-pitches.sh` 原本在這張表上，
    # 需求方推翻「具名放行」的裁定改為提前處置：它們與 `sync_deep_tm_prod.py` 同級——
    # 探索動作即造成損害——而破壞半徑更大（前者 DROP 一張表，`refresh-cpbl-prod.sh` 是
    # 整條生產同步鏈）。三支已加 argv 守衛並由 `tests/test_shell_help_guard.py` 逐支釘住，
    # 故從本表撤除（`test_invariant_4_allowlist_has_no_stale_entries` 會擋住殘留條目）。
    #
    # `backup-prod-db.sh` 是**第四支**，但它從來沒進過這張表——因為舊判準（「寫入型」
    # ＝寫 DB）看不到它。實測它的 `--help` 會 ssh 進生產跑整庫 dump，然後 exit 0、
    # 產出備份、`rm -f` 掉輪替視窗最舊的那份。**清冊印得出警告，不變式卻擋不住**，
    # 這正是判準加寬為「高後果」的成因；該支已加守衛，同樣不列本表。
    "scripts/weekly-box-revisions.sh": (
        "無 argv 守衛，會直接跑 `cpbl-refresh-box-deep`（Playwright 打官網 + 寫本機 DB）。"
        "⚠️ **與同批三支同性質，本卡射程外**：它是 `#132` 的資源（該卡同時持有 "
        "`scripts/refresh_status.py` 與 `src/cpbl/api/routers/info.py`），本卡改它等於"
        "動另一張活卡的檔案。去向：`#132` 收工後比照同批三支補上守衛"),
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
    "docs/research/DEV-CLI-HELP-GUARD1/audit_cli_help.py": (
        "推導判 CI 繫結（`tests/test_cli_help_guard.py::test_seal_surface_matches_audit_tool` "
        "以硬編路徑載入它防兩份 seal 漂移），但它是 DEV-CLI-HELP-GUARD1 的**交付產物**、"
        "已住在自己卡的目錄裡。搬它要同時改 `tests/test_cli_help_guard.py` 的路徑常數與 "
        "`docs/research/DEV-CLI-HELP-GUARD1/cli-help-audit.md`——後者射程外"),
    "docs/research/TIME-SEMANTICS-CONTRACT1/scan_time_semantics.py": (
        "⚠️ **本卡掃出來的既有不一致**：`docs/TIME_SEMANTICS_CONTRACT.md:243` 給了重跑指令"
        "（`uv run python docs/research/…/scan_time_semantics.py --verify`），依推導規則屬常設工具，"
        "卻住在 research 卡目錄。判準與位置真的不符，但它是 TIME-SEMANTICS-CONTRACT1 的交付產物，"
        "搬它要改活契約——射程外。列為交付報告的待裁項"),
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
    for rel in _git_ls(SCRIPTS_GLOB) + _git_ls(RESEARCH_GLOB):
        if Path(rel).name in NON_ENTRY_BASENAMES or rel in POSITION_EXCEPTIONS:
            continue
        cls, _ = classify(rel)
        if position_ok(rel, cls):
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


def position_ok(rel: str, cls: str) -> bool:
    """位置是否符合分類。

    ⚠️ 一次性產物用**前綴**比對而非相等：`docs/research/<CARD>/cases/build_cases.py`
    在卡目錄底下再分一層子目錄，仍然是「住在自己卡的目錄裡」。初版用相等比對，
    把它判成位置不符——**偵測器自己的規則產生的假陽性**。
    """
    expected = expected_location(rel, cls)
    if not expected:
        return False
    current = str(Path(rel).parent) + "/"
    return current == expected or current.startswith(expected)


# ==================================================== `--help` 靜態安全性
#
# 判準沿用 `tests/test_cli_help_guard.py`：「argv 必須在主流程觸及任何 I/O 出口之前
# 被解析，未知旗標必須非零退出」。CLI 側該檔已用**執行期密封探針**證明；`scripts/`
# 側因本卡紅線不得執行任何腳本，改以**靜態**近似——限度誠實寫在清冊裡。


# =========================================== shell 的 argv 守衛：canonical 控制流
#
# ⚠️ **這一段是量出來的，不是設計出來的。** 四支排程 shell 的守衛由同一個執行者
# 在同一天寫出（`4956546`、`3833638`），幾小時內就漂成**三個變體**：
#   · `backup-prod-db.sh` / `refresh-cpbl-prod.sh`：help 分支 ＋ `*)` 拒絕分支
#   · `weekly-game-pitches.sh`：同上，但拒絕訊息的第二行不同
#   · `scrape-daily.sh`：只有 help 分支（它有合法的位置參數 `fast`）
#
# 這與 `R2-001` 是同一種病的兩面：**名字承諾了一致性，實作沒有給**。
#
# 修法不是「四份寫一樣然後記得對齊」，是把兩件本來就不同性質的事拆開：
#
#   1. **`--help` 守衛**（控制流）——四支必須逐字相同。它只做一件事：認出 `-h/--help`、
#      印用法、exit 0。這是不變式 4 的錨點，也是靜態斷言 `if [ "$#" -gt 0 ]; then`
#      找的那一行。
#   2. **位置參數契約**（逐支不同）——「本腳本不接受位置參數」vs「只接受 fast」是
#      各腳本特有的事實，補救訊息（走環境變數 vs 用 `YEAR=`）也是。這一段**應該**
#      不一樣，共用反而是錯的；它排在守衛之後，各自負責。
#
# `scrape-daily.sh` 本來就是這個形狀（守衛只認 help，`fast` 由下方自己的檢查處理），
# 所以統一的方向是把另外三支的 `*)` 分支從守衛裡搬出來，而不是把 `fast` 塞進守衛。
#
# ⚠️ **刻意不做成 sourced library**（`. scripts/lib/argv_guard.sh`）：`source` 那一行
# 跑在守衛之前，函式庫路徑錯或檔案不見時腳本會死在印出用法之前——那正是守衛要防的
# 失敗模式。守衛必須實體留在檔案最前面、零執行期相依。
#
# ⚠️ 一致性由**本函式**保證，不是由一條額外的測試保證：`help_safety()` 現在只有在
# 控制流與 canonical 逐字相同時才給 `safe`。漂掉的守衛會失去 `safe`，於是掉進
# 不變式 4 的射程、需要具名放行——CI 直接紅。形狀沿用 `#138` 的
# `_SCHEDULE_SELECTION_KEYS`（一份來源、多個消費者派生），而不是靠人記得對齊。
SHELL_USAGE_SLOT = "<<<USAGE>>>"

SHELL_GUARD_CANONICAL = f"""usage() {{
  cat <<'EOF'
{SHELL_USAGE_SLOT}
EOF
}}

if [ "$#" -gt 0 ]; then
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
  esac
fi"""

_GUARD_OPEN = 'if [ "$#" -gt 0 ]; then'


def guard_control_flow(source: str) -> str | None:
    """抽出 shell 的守衛區段並把 usage 內容換成 slot。抽不出來回 None。

    回傳值就是要與 `SHELL_GUARD_CANONICAL` 逐字比對的東西：`usage()` 的**框架**
    （`cat <<'EOF'` … `EOF`）算控制流，heredoc 的**內容**不算。

    ⚠️ 收字串而不是路徑，是為了讓負控制能在**副本**上改壞控制流再問一次
    ——不然「改壞就會紅」只能用宣稱的。
    """
    lines = source.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln == "usage() {")
        guard = next(i for i, ln in enumerate(lines) if i > start and ln == _GUARD_OPEN)
        end = next(i for i, ln in enumerate(lines) if i > guard and ln == "fi")
    except StopIteration:
        return None

    block = lines[start:end + 1]
    try:
        body_start = block.index("  cat <<'EOF'") + 1
        body_end = block.index("EOF", body_start)
    except ValueError:
        return None
    return "\n".join(block[:body_start] + [SHELL_USAGE_SLOT] + block[body_end:])


def shell_guard_control_flow(rel: str) -> str | None:
    return guard_control_flow(_read(rel))


def help_safety(rel: str) -> tuple[str, str]:
    """回傳 (狀態, 說明)。狀態 ∈ {safe, unsafe, n/a}。"""
    if rel.endswith(".plist"):
        return "n/a", "plist 是排程宣告，不是可打指令的入口"
    if rel.endswith(".sh"):
        # ⚠️ shell 沒有 argparse，但「打錯參數會不會照跑」的問題完全一樣：無守衛時
        # `weekly-box-revisions.sh --help` 會直接開始對官網打整季請求並寫本機 DB。
        #
        # ⚠️ **這一條只看得到守衛長什麼樣，看不到它在哪**：位置由
        # `tests/test_shell_help_guard.py` 以假樁執行 ＋ 位置斷言證明，不在這裡。
        flow = shell_guard_control_flow(rel)
        if flow is None:
            return "unsafe", "無 argv 守衛：未知參數會被吞掉或忽略，主流程照跑"
        if flow != SHELL_GUARD_CANONICAL:
            return "unsafe", (
                "有守衛但控制流與 canonical 不符（script_inventory.SHELL_GUARD_CANONICAL）；"
                "逐字比對見 tests/test_shell_help_guard.py")
        return "safe", (
            "argv 守衛控制流與 canonical 逐字相同；"
            "零副作用由 tests/test_shell_help_guard.py 以假樁證明")
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
    high_consequence: bool       # 探索動作即造成損害＝不變式 4 的射程
    high_consequence_note: str
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
        hc, hcnote = high_consequence(rel, verdict)
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
            high_consequence=hc,
            high_consequence_note=hcnote,
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
        hc, hcnote = high_consequence(rel or "", verdict)
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
            high_consequence=hc,
            high_consequence_note=hcnote,
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


def entry_effects(rel: str, writes: bool) -> frozenset[str]:
    """入口可達的出口集合。`db_write` 一律採 `writes`（W1／W2 交叉複算的裁定結果）。

    ⚠️ `.sh`／`.plist` 沒有 Python AST，呼叫圖引擎結構性不適用——退回對整份檔案跑
    同一張表的 payload 正則。**這一格的精確度比 `.py` 差**（守衛放在副作用之後仍
    會被看見），限度與 W1 對 shell 不適用是同一個結構性事實，明載於清冊。
    """
    found: set[str] = {"db_write"} if writes else set()
    if not rel or rel in SELF_REFERENCE:
        return frozenset(found)
    if rel.endswith(".sh"):
        text = _read(rel)
        found |= {e for e, rx in RUNNER_PAYLOAD.items() if rx.search(text)}
    elif rel.endswith(".py"):
        found |= reachable_effects(rel) - {"db_write"}
    # .plist 是排程宣告，不是可打的入口
    return frozenset(found)


def high_consequence(rel: str, writes: bool) -> tuple[bool, str]:
    """`--help` 走進主流程會不會造成損害。回傳 (判定, 理由)。

    判準 ＝「入口的呼叫路徑抵不抵得到 `HIGH_CONSEQUENCE_EFFECTS` 裡的任一出口」。
    出口是什麼由 `SINK_MODULES`／`RUNNER_PAYLOAD` 這張表定義，可達不可達由
    `reachable_effects()` 回答——**判準本身不再認得任何一個特定的危險名字**。
    """
    effects = entry_effects(rel, writes) & set(HIGH_CONSEQUENCE_EFFECTS)
    if not effects:
        return False, ""
    ordered = [e for e in HIGH_CONSEQUENCE_EFFECTS if e in effects]
    return True, "、".join(EFFECT_LABELS[e] for e in ordered)


@cache
def _cli_modules() -> dict[str, str]:
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return {name: rel for name, target in cfg["project"]["scripts"].items()
            if (rel := _cli_entry_module(target))}


def _entry_module(e: Entry) -> str:
    """入口 → 它的原始碼檔（CLI 走 pyproject 的 target 模組）。"""
    return _cli_modules().get(e.ident, "") if e.surface == "cli" else e.ident


# ⚠️ **對照組，不是判準。** 這是「把 HTTP 塞進 W2 的射程」那個修法會得到的結果，
# 留在這裡是為了讓「呼叫圖比較精確」這句話有一次現算的實測，而不是一個會過期的數字。
CLOSURE_HTTP_RE = re.compile(
    r"httpx|requests\.(get|post|put|delete)|urllib\.request|urlopen|aiohttp|playwright"
    r"|(?<![\w-])(curl|wget)(?![\w-])")


def closure_http_hits(entries: list[Entry]) -> list[str]:
    """對照組：改用 import 閉包掃 HTTP 會命中哪些入口（含已被寫入型涵蓋的）。"""
    hits = []
    for e in entries:
        rel = _entry_module(e)
        if not rel or not rel.endswith(".py"):
            continue
        closure = (p for p in _import_closure(rel) if p not in SELF_REFERENCE)
        if any(CLOSURE_HTTP_RE.search(_read(p)) for p in closure):
            hits.append(e.ident)
    return sorted(hits)


def high_consequence_unsafe(entries: list[Entry]) -> list[Entry]:
    """不變式 4 的違反者：**高後果**且 `--help` 不安全。

    ⚠️ 判準原本是「寫入型且 `--help` 不安全」。`backup-prod-db.sh` 從那個形狀的
    縫隙掉出去：清冊逐支印著「⚠️ --help 不安全」，不變式卻不看它，因為它對 DB
    唯讀。**印得出警告不等於擋得住**——判準已加寬為高後果，理由見 `high_consequence`。
    """
    return [e for e in entries if e.high_consequence and e.help_state == "unsafe"]


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
    a("## 高後果必須 `--help` 安全（不變式 4）")
    a("")
    a("判定為**高後果**的入口，argv 必須在主流程前被解析。**既有不合格者具名列入 allowlist**。")
    a("")
    a(f"高後果 **{sum(1 for e in entries if e.high_consequence)}** 支"
      f"（其中非寫入型 **{sum(1 for e in entries if e.high_consequence and not e.writes)}** 支）。")
    a("")
    a("### 判準的形狀：出口目錄 ＋ 一台可達性引擎")
    a("")
    a("判準**不認得任何一個特定的危險名字**，它問兩件事：")
    a("")
    a("1. **什麼算出口** —— 由 `script_inventory.py` 的 `SINK_MODULES`／`RUNNER_PAYLOAD` "
      "**一張表**定義。損害＝這個行程對外部世界造成的改變，而通道是可窮舉的："
      "DB driver、網路、破壞性檔案操作、以及把前三者外包出去的 shell。"
      "每條出口只有兩種形狀：**(a) 具名函式庫綁定**（import 了它、呼叫它就是那個效果）與 "
      "**(b) 泛用執行器的參數**（`subprocess`／`os.system`／`cursor.execute` 本身無害，"
      "效果由參數內容決定）。寫 DB 一直都是 (b) 的一個實例，HTTP 是 (a) 的一個實例。")
    a("2. **這個入口碰不碰得到** —— 由 `reachable_effects()` 沿 AST 呼叫圖回答，"
      "而它就是 W1（`writes_ast`）用的**同一台引擎**；`writes_ast` 現在只是 "
      "`reachable_effects(rel) ∋ db_write` 的別名。")
    a("")
    a("| 效果 | 判準形狀 | 判定依據 |")
    a("|---|---|---|")
    for key in HIGH_CONSEQUENCE_EFFECTS:
        mods = SINK_MODULES.get(key, ())
        rx = RUNNER_PAYLOAD.get(key)
        shape = []
        if mods:
            shape.append("(a) 函式庫綁定：" + "、".join(f"`{m}`" for m in mods))
        if rx:
            shape.append(f"(b) 執行器參數：`{rx.pattern}`")
        if key == "db_write":
            shape.append("W1／W2 交叉複算的**裁定結果**（見寫入面那節），不在此重算")
        a(f"| `{key}`（{EFFECT_LABELS[key]}） | {'；'.join(shape)} | "
          f"呼叫路徑可達即成立 |")
    a("")
    a("> [!warning] **這條判準被改過兩次，兩次都是同一種病。**")
    a("> 第一次：只問「寫不寫 DB」，`backup-prod-db.sh` 掉出去——它 `pg_dump` 對 DB 唯讀，"
      "於是 `writes=False`、不變式根本不看它，但實測 `--help` 會 ssh 進生產跑整庫 dump、"
      "exit 0、產出備份、`rm -f` 掉輪替視窗最舊的那份。")
    a("> 第二次（`DEV-SCRIPT-INVENTORY1-R2-001`）：加寬後判準**名為**「接觸遠端」、"
      "**實作只認 SSH**，於是 `confirm_live_schema.py` 掉出去——它的 `--help` 會被當成 "
      "game ID 拼進 URL 對 `stats.cpbl.com.tw` 發真實請求。")
    a("> **兩次都不是「少寫了一條正則」，是「判準的名字承諾了一致性、實作沒有給」。**"
      "所以第二次的修法不是再加一條，是把「出口是什麼」與「碰不碰得到」拆開。")
    a("")
    a("> [!important] **為什麼不掃 import 閉包**（W2 的射程，也是本判準改版前對 `.py` 用的射程）。")
    # 兩邊都限 `.py`：閉包法結構性只適用於 Python，`.sh` 走的是另一格判準。
    py_entries = [e for e in entries if _entry_module(e).endswith(".py")]
    closure = set(closure_http_hits(py_entries))
    graph_http = {e.ident for e in py_entries
                  if "http" in entry_effects(_entry_module(e), e.writes)}
    a("> `httpx` 在 `cpbl.*` 相依圖裡到處都是，掃閉包會把只 import 了一個常數的唯讀腳本"
      "判成打網路的。**現算的差額**（每次重生清冊時重新量，不寫死；母體限 `.py` 入口 "
      f"{len(py_entries)} 支，`.sh` 沒有 import 圖故不在本對照內）："
      f"閉包法命中 **{len(closure)}** 支、呼叫圖法 **{len(graph_http)}** 支，"
      f"閉包法多出來的 **{len(closure - graph_http)}** 支即誤判面。")
    a("> 最刺眼的一支是 `check_splits_pa_split1_results.py`——它從 "
      "`cpbl.ingest.cpbl_player_detail` **只 import 了 `APART_COMBOS` 這個 list 常數**，"
      "閉包法照樣判它打網路。**誤判要靠 allowlist 消化，而每多一條 allowlist "
      "就離 `roadmap_lines.py` 的 `GATE_OVERRIDES` 近一步**——這裡要的是精確，不是寬。")
    a("")
    a("閉包法多判、呼叫圖法不判的 "
      f"{len(closure - graph_http)} 支：" + "、".join(f"`{i}`" for i in sorted(closure - graph_http)))
    a("")
    a("反向（呼叫圖判、閉包法不判）"
      f"{len(graph_http - closure)} 支"
      + ("：" + "、".join(f"`{i}`" for i in sorted(graph_http - closure)) if graph_http - closure
         else "——閉包法是呼叫圖法的**超集**，故精確度差額全在誤判方向。"))
    a("")
    a("> [!note] **限度**（逐條實測，不是宣稱）：")
    a("> - 出口若經由**型別靜態解析不了的值**抵達（`client.get(...)` 的 `client` 是傳進來的參數、"
      "`getattr` 呼叫、callback），呼叫圖看不到。本 repo 的慣用法是 `_client()` 先建再傳，"
      "建構點落在呼叫路徑上，故實測未產生假陰性——但這是**慣用法的性質，不是判準的保證**。")
    a("> - 跨模組只解析 `cpbl.*`；第三方套件內部的呼叫圖不展開。")
    a("> - `import cpbl.x`（不點名符號）退回整個模組效果的聯集，精確度降回閉包等級。")
    a("> - `.sh`／`.plist` 沒有 Python AST，退回對整份檔案跑同一張表的 payload 正則——"
      "**看得到出口在不在，看不到入口碰不碰得到**，與 W1 對 shell 不適用是同一個結構性事實。")
    a("")
    a("原則上本卡只加不變式、不改既有腳本行為（那會讓本卡從盤點變成改一批腳本），"
      "但需求方對**排程 shell** 推翻了這個處置：`refresh-cpbl-prod.sh`／`scrape-daily.sh`／"
      "`weekly-game-pitches.sh` 與 `sync_deep_tm_prod.py` **同級**——探索動作即造成損害——"
      "而破壞半徑更大（後者 DROP 一張表，`refresh-cpbl-prod.sh` 是整條生產同步鏈）。"
      "`backup-prod-db.sh` 是判準加寬後補上的第四支。"
      "四支皆已加 argv 守衛並不列下表，證明見 `tests/test_shell_help_guard.py`。")
    a("")
    a("### 一次性產物也要守衛（需求方裁定 2026-08-15：加守衛，不要留紀錄）")
    a("")
    a("`R2-001` 修法後新納入射程的兩支（`confirm_live_schema.py`、"
      "`replay_schedule_branches.py`）**已加 argv 守衛，不列下表**。")
    a("")
    a("執行者原本主張具名放行，理由是「一次性產物本來就沒人該跑，所以守衛買到的是"
      "對一個已被禁止的動作的保護」。**需求方推翻，三條理由：**")
    a("")
    a("1. **`--help` 不是「跑它」，是「想知道它是什麼」**——那個前提不成立。"
      "本 repo 已有兩次 `--help` 觸發真實爬蟲的事故"
      "（`cpbl-scrape-pitches --help` 2026-08-05、`refresh-cpbl-prod.sh --help` 2026-08 本週），"
      "這會是同形狀的第三次。`replay_schedule_branches.py --help` 抓的是六個月賽程，"
      "直接踩到 `CLAUDE.md` 爬蟲紅線第 2 條（連續冷啟動會讓節流升級）。")
    a("2. **「標記＋位置就是防線」正是本 repo 反覆在修的那個病。** "
      "`OPS-BACKUP-EMPTY1` 的教訓逐字是「檢查看得見的標記，而非該成立的性質」"
      "（86 份 20-byte 空檔每一份都通過 `gzip -t`）。"
      "一行寫著「不要跑」的註解是**標記**，守衛才是**性質**——"
      "而本輪的主要成果正是把不變式 4 的判準從「命名危險」改成「問呼叫圖」，"
      "同一輪不該在隔壁段落主張註解可以當防線。")
    a("3. **成本有界而傷害沒有。** 執行者當時舉的成本是"
      "「加守衛會讓 `docs/research/TIME-SEMANTICS-CONTRACT1/inventory.json:84,96` 記的行號失準」"
      "——行號確實移動了（43／48 → 80／85），但**實測不觸發任何檢查**："
      "引用完整性只認 `scripts/<name>.<ext>` 字面路徑，`docs/research/` 下的路徑"
      "不在觀測面內（該檔對 `confirm_live_schema.py` 零命中），"
      "而該 JSON 的引用面別是 `scan`＝快照，本表上方已明載「過期是歷史事實不是缺陷」。"
      "相對地，爬蟲節流升級的代價是整條每日鏈的可用性，且已經發生過。")
    a("")
    a("⚠️ 執行者有一點沒被推翻、也確實成立：**守衛擋不住真正的覆寫路徑**"
      "——帶一個合法 gid 跑 `confirm_live_schema.py`，一樣會覆寫 `request_log.json`。"
      "那是另一個威脅模型（刻意 vs 意外），守衛關掉的是會發生的那一個。"
      "剩下那條由檔頭標記與位置承擔，並已寫進該支的 `--help` 用法「會寫什麼」段。")
    a("")
    a("兩支的守衛走 `.py` 的判準（`argparse` 在主流程前 `parse_args`），不是 shell 的控制流；"
      "用法涵蓋「在做什麼／會寫什麼／怎麼呼叫」三段。"
      "執行期零請求由 `tests/test_script_inventory.py` 以**副本 ＋ 假 httpx 留痕**逐支證明，"
      "負控制（改回修法前的形狀）實測 `--help` 會走到 `httpx.Client()` ＋ `.get`。")
    a("")
    a("| 入口 | 理由與去向 |")
    a("|---|---|")
    for ident, reason in sorted(HELP_SAFETY_ALLOWLIST.items()):
        a(f"| `{ident}` | {_md_escape(reason)} |")
    a("")
    a("> [!note] 判準沿用 `tests/test_cli_help_guard.py`，不另立一套。")
    a("> CLI 側該檔以**執行期密封探針**證明（所有 I/O 出口 stub 化後才呼叫 `main()`）；")
    a("> `.py` 的 `scripts/` 側因本卡紅線**不得執行任何腳本**，改以**靜態**近似："
      "「有 argparse 且入口在主流程前呼叫 `parse_args`」。")
    a("> **限度**：靜態判準證明不了「parse_args 之後才有副作用」，只證明 argv 有被解析。")
    a("")
    a("### shell 的守衛：一份 canonical 控制流，四份 inline 逐字相同")
    a("")
    a("shell 沒有 argparse，判準原本是一條寬鬆正則（「有 `getopts`／`case $1`／`usage` "
      "就算 safe」）。**那條正則量不到一致性**，而一致性正是這裡出事的地方："
      "四支的守衛由同一個執行者在同一天寫出（`4956546`、`3833638`），"
      "**幾小時內就漂成三個變體**——兩支一種、`weekly-game-pitches.sh` 拒絕訊息不同、"
      "`scrape-daily.sh` 少一個分支。這與不變式 4 的兩次失敗是同一種病："
      "**名字承諾了一致性，實作沒有給**。")
    a("")
    a("修法是把兩件本來就不同性質的事拆開：")
    a("")
    a("| | 誰負責 | 要不要一致 |")
    a("|---|---|---|")
    a("| **`--help` 守衛**（控制流） | `script_inventory.SHELL_GUARD_CANONICAL` |"
      " ✅ 四份與 canonical **逐字相同**，不符即 CI 紅 |")
    a("| **位置參數契約**（拒絕與補救訊息） | 各腳本自己，排在守衛之後 |"
      " ❌ **應該**逐支不同——「不接受位置參數」vs「只接受 `fast`」、"
      "補救是環境變數 vs `YEAR=`，共用反而是錯的 |")
    a("| **`usage` 內容** | 各腳本自己 | ❌ 同上，且 `test_usage_bodies_are_pairwise_distinct`"
      " 釘住四份互不相同 |")
    a("")
    a("一致性由 `help_safety()` 本身保證，不是靠一條額外的測試："
      "**控制流與 canonical 不逐字相同就拿不到 `safe`**，於是掉進不變式 4 的射程、"
      "需要具名放行——CI 直接紅。形狀沿用 `#138` 的 `_SCHEDULE_SELECTION_KEYS`"
      "（一份來源、多個消費者派生），不是靠人記得對齊。")
    a("")
    a("> [!warning] **刻意不做成 sourced library**（`. scripts/lib/argv_guard.sh`）。")
    a("> `source` 那一行跑在守衛之前：函式庫路徑錯或檔案不見時，腳本會**死在印出用法之前**，"
      "而那正是守衛要防的失敗模式；它也會破壞「守衛必須是第一件事」的靜態錨點。"
      "守衛必須實體留在檔案最前面、零執行期相依，"
      "由 `test_guard_is_inline_not_sourced` 釘住。")
    a("")
    a("> [!note] **失效面**：canonical 只涵蓋「這個 repo 現行的那一種寫法」。"
      "`getopts` 風格的守衛在新判準下會被判 `unsafe`——這是刻意的取捨"
      "（一種寫法換來可逐字比對），代價是未來若真的需要第二種形狀，"
      "得先擴充 canonical 而不是各寫各的。"
      "另外，逐字比對證明的是**四份一樣**，不是**這一份是對的**；"
      "「對不對」由本節下方那組執行期證明（副本 ＋ 假樁）負責。")
    a("")
    a("四支的 `--help` 零外部呼叫、零檔案產出，由 `tests/test_shell_help_guard.py` 以"
      "**副本 ＋ 假樁**逐支證明，並釘住「守衛之前不得有副作用」；"
      "該檔的 `test_every_safe_shell_is_covered_here` 使「清冊判 safe 卻沒人證明」直接 CI 紅。")
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
