"""DEV-COMPLETION-CONDITION-GUARD1：手寫完成場判定的封閉集合守衛。

**服務的原始目標**：新寫一處未經 :mod:`cpbl.completion` 的完成場條件，要在**構造上**
被發現，而不是靠人記得。#113 修過三處就結案，`api/routers/daily.py` 那第四處不在它的
清單上、至今仍在——把清單從 3 改成 9 仍然是列舉，下一個第 10 處一樣沒人會知道。

**判準＝只認 canonical helper（需求方 2026-08-20 裁定，乙案）**，是**字面存在性**，
不是語意啟發式：``src/`` 內任何手寫的「兩個比分欄相加後與數字比較」都算違規，
合法用途一律走 :func:`cpbl.completion.completed_games_sql` 或
:func:`cpbl.completion.completed_games_sql_with_evidence`。

⚠️ **為什麼不用「鄰近有沒有日期界線」那種啟發式**：PM 逐處查證時它實測產生 2 個假警報
（``run_refresh_recent`` 的 ``_completed_snos`` 與 ``_recent_counts`` 以
``game_date = ANY(days)`` 提供等價界線，啟發式看不到），而假警報是守衛的死因；
更根本的是它是**開放集合**——下一個人用 ``BETWEEN``、``IN (...)``、或先在 Python 過濾，
一樣逃得掉。誤傷的正確處置是「請改走 helper」，不是讓守衛去猜這段安不安全。

**什麼結果會推翻這個守衛**（先講出來再寫，見 vacuous-check-and-vacuous-evidence）：

* 在 ``src/`` 任何一支檔案新寫一行 ``home_score + away_score > 0`` 而
  :func:`scan_violations` 不回報它 → 守衛無效。**開發過程實際發生過一次**：初版逐行
  掃描漏掉「把條件拆成兩行字串字面」的寫法，改成以 ast 讀字串字面（相鄰字面已由
  parser 合併）才補上，見 :func:`test_condition_split_across_source_lines_is_caught`。
* 把 ``src/`` 的手寫條件全部改成 helper 呼叫後守衛仍紅 → 守衛誤傷。
* allowlist 裡放著一個已經不存在的項目而測試仍綠 → allowlist 變成永久逃生門。

以上三者分別由 :func:`test_injected_condition_is_caught`、
:func:`test_helper_call_sites_are_not_caught`、
:func:`test_allowlist_counts_are_exact`（**精確相等**，不是「≤」）釘住。

⚠️ **allowlist 的構造性限制**：以「檔案 → 精確筆數 ＋ 標記」記錄，比對是**精確相等**。
少一筆（有人清掉了）會紅，逼 allowlist 一起縮小；多一筆（有人新寫）也會紅。

標記分兩種，**不是同一件事**（:data:`PENDING` / :data:`REVIEWED`）：確實是完成判定、
待遷移的必須指名承接卡；逐處讀過、**不是**完成判定的（例如「還沒開打」「即將到來」的
候選撈取）標成已審視且**不得**帶卡號。少了後面這一種，承接卡做完之後那幾處還會留在
allowlist 裡，被下一個人誤讀成「遷移沒做完」——標記本身就是交接資訊。

⚠️ 承接卡的資源宣告必須真的涵蓋該檔案。曾誤填 ``#90 DATA-TIE-REMEDY1``：它的資源宣告
只有 ``db:local:table:game_completion_evidence``、一個 ``.py`` 都沒有，結案時不會碰任何
一處，allowlist 於是**永不縮小**——一個指向不會來的人的卡號，和沒有卡號是同一件事。
"""

from __future__ import annotations

import ast
import io
import re
import subprocess
import tokenize
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

# canonical 模組本身**必須**含有這個字面（它就是那份定義），故是唯一的結構性豁免。
CANONICAL_MODULE = SRC_ROOT / "cpbl" / "completion.py"

# 一個「比分項」：允許表別名（``g.``）、``coalesce(x, 0)`` 與 Python 的 ``(x or 0)`` 兩種
# 補值寫法。這三種是 repo 內實際出現過的形狀，逐一列出而不是靠萬用比對。
_SCORE_TERM = (
    r"(?:coalesce\(\s*|\(\s*)?"
    r"(?:\w+\.)?"
    r"(?:home|away|visiting)_score"
    r"(?:\s*,\s*0\s*\)|\s+or\s+0\s*\))?"
)

# 完成條件家族：兩個比分項相加後與**任何數字**比較。運算子取封閉集合（含 ``= 0`` 這種
# 補集寫法——「未開打」與「已完成」是同一個判準的兩面，只擋一邊等於留一道門）。
FAMILY_RE = re.compile(
    rf"{_SCORE_TERM}\s*\+\s*{_SCORE_TERM}\s*(?:>=|<=|<>|!=|>|<|=)\s*-?\d+",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Violation:
    path: str          # 相對 repo root
    lineno: int
    text: str          # 命中的運算式原文


# allowlist 的兩種標記。⚠️ 缺了「已審視」這一種的話，承接卡做完後那幾處還會留在
# allowlist 裡，會被下一個人誤讀成「遷移沒做完」——標記本身就是交接資訊。
PENDING = "pending-migration"          # 是完成判定、待遷移；**必須**帶承接卡號
REVIEWED = "reviewed-not-a-defect"     # 逐處讀過、不是完成判定；**不得**帶卡號（沒有人要來改它）
STATUSES = (PENDING, REVIEWED)


@dataclass(frozen=True)
class Allowed:
    count: int
    status: str        # PENDING | REVIEWED
    card: str = ""     # PENDING 必填 ``#<issue>``；REVIEWED 必須留空
    note: str = ""     # 一律必填：PENDING 寫遷移方向，REVIEWED 寫「為什麼不是缺陷」


# ---------------------------------------------------------------------------
# allowlist
#
# ⚠️ 這裡**只能**放「已經存在、且已有承接卡負責清掉」的手寫條件。新寫的一律修掉，
# 不要往這裡加。每一項的 count 是**精確**筆數，比對不相等即紅。
# ---------------------------------------------------------------------------
# ⚠️ 這裡**只能**放「已經存在」的手寫條件，且必須擇一標記：
#
# * PENDING —— 確實是完成判定、待遷移，**必須**指名承接卡。卡的資源宣告要真的涵蓋
#   這支檔案，否則卡結案時不會碰它，allowlist 就永遠縮不掉。
#   （曾誤填 #90 DATA-TIE-REMEDY1：它的資源宣告只有
#   `db:local:table:game_completion_evidence`，一個 .py 都沒有 → 永不縮小。）
# * REVIEWED —— 逐處讀過、**不是**完成判定（例如「還沒開打」「即將到來」的候選撈取），
#   沒有承接卡也不該有。note 必須寫清楚為什麼。
#
# 新寫的一律修掉，不要往這裡加。count 是**精確**筆數，比對不相等即紅。

# ⚠️ 非鏈端（原 `_NONCHAIN = "#156"`，12 檔 16 處）已於 #156 全數遷移完畢，整桶移除。
# 常數一併刪掉而不是留著空著——留下一個沒有任何項目引用的卡號，下一個人得回頭查 issue
# 才知道那是「做完了」還是「漏填了」。allowlist 只記**還存在**的手寫條件。
# 每日 refresh 鏈：沿用舊判準，等 #53 G4 Phase B 之後的 Phase 2 才切
_CHAIN = "#157"         # DATA-COMPLETION-MIGRATE-CHAIN1（阻塞於 #53）

ALLOWLIST: dict[str, Allowed] = {
    # --- 每日 refresh 鏈待遷移（#157，阻塞於 #53 G4 Phase B）：2 檔 3 處 ---
    "src/cpbl/ingest/cpbl_gamelog.py": Allowed(2, PENDING, _CHAIN, "鏈端目標場清單；換判準＝換爬取母體"),
    "src/cpbl/ingest/cpbl_pitch_tracking.py": Allowed(1, PENDING, _CHAIN, "鏈端目標場清單；換判準＝換爬取母體"),

    # --- 已審視、不是完成判定：3 檔 3 處（無承接卡，也不該有） ---
    "src/cpbl/api/routers/daily.py": Allowed(
        1, REVIEWED, "",
        "`= 0` 只是 SQL 側便宜撈出的『比分為 0』候選；『其實已完成的是哪些』由同一支端點的 "
        "_completed（走 is_completed_game）判定，是刻意的兩段式設計，緊鄰註解自述"),
    "src/cpbl/api/routers/info.py": Allowed(
        1, REVIEWED, "",
        "指標語意是『今天排了幾場還沒打』，不是完成判定；且已刻意用 TAIPEI_TODAY_SQL"),
    "src/cpbl/models/matchup.py": Allowed(
        1, REVIEWED, "",
        "`= 0 AND game_date >= today`＝『即將到來的比賽』，語意是未來場不是完成場"),
}


# ---------------------------------------------------------------------------
# 掃描
# ---------------------------------------------------------------------------
def _docstring_ids(tree: ast.AST) -> set[int]:
    """module/class/function 的 docstring 節點 id。

    這是**位置性**規則（ast 的既定位置），不是語意猜測：SQL 一律活在一般字串字面裡，
    docstring 不會被送進 DB。排除它是為了不讓「解釋這個反模式的散文」變成假警報——
    `api/routers/daily.py` 的 `_completed` docstring 逐字寫著它**不再**自己寫一份，
    那正是我們要的行為，不該被守衛罵。
    """
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, holders):
            continue
        body = getattr(node, "body", None)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            ids.add(id(body[0].value))
    return ids


def _string_nodes(tree: ast.AST, skip_ids: set[int]) -> list[tuple[ast.AST, str]]:
    """回傳 (節點, 文字)：**相鄰字串字面已由 parser 合併成單一節點**。

    這是「跨行拆寫」擋得住的關鍵——`"AND home_score + "` 接 `"away_score > 0"` 在原始碼
    是兩行、逐行掃描抓不到（實測會漏），但 ast 看到的是同一個 Constant。
    f-string 的 `{...}` 以 NUL 佔位，避免把被運算式隔開的兩段誤黏成一個條件。
    """
    out: list[tuple[ast.AST, str]] = []
    # f-string 的內層 Constant 由 JoinedStr 整段代表，不可再各自算一次（會重複計數）
    inner = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in skip_ids and id(node) not in inner:
                out.append((node, node.value))
        elif isinstance(node, ast.JoinedStr):
            parts = []
            for v in node.values:
                parts.append(v.value if isinstance(v, ast.Constant)
                             and isinstance(v.value, str) else "\x00")
            out.append((node, "".join(parts)))
    return out


def _comment_lines(source: str) -> set[int]:
    skip: set[int] = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                skip.update(range(tok.start[0], tok.end[0] + 1))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return skip


def scan_file(path: Path) -> list[Violation]:
    """掃一支檔案，兩趟。

    第一趟掃**字串字面**（走 ast，相鄰字面已合併，故跨行拆寫照樣抓）；第二趟逐行掃
    **其餘程式碼**，接住 Python 端的 `(home_score or 0) + (away_score or 0) > 0` 這類寫法。
    第二趟跳過第一趟已涵蓋的字串行與註解／docstring，避免同一處被數兩次——allowlist
    是**精確筆數**比對，重複計數會讓它整個失準。
    """
    source = path.read_text(encoding="utf-8")
    try:
        rel = path.relative_to(REPO_ROOT).as_posix()
    except ValueError:   # tmp_path 等 repo 外的樣本（可證偽性自測用）
        rel = path.as_posix()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    out: list[Violation] = []
    covered: set[int] = set()
    for node, text in _string_nodes(tree, _docstring_ids(tree)):
        lo = getattr(node, "lineno", 1)
        hi = getattr(node, "end_lineno", lo) or lo
        covered.update(range(lo, hi + 1))
        for m in FAMILY_RE.finditer(text):
            out.append(Violation(rel, lo, " ".join(m.group(0).split())))

    skip = covered | _comment_lines(source)
    for node in ast.walk(tree):   # docstring 的行範圍（其節點已被 skip_ids 排除）
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            skip.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))

    for lineno, line in enumerate(source.splitlines(), 1):
        if lineno in skip:
            continue
        for m in FAMILY_RE.finditer(line):
            out.append(Violation(rel, lineno, " ".join(m.group(0).split())))
    return sorted(out, key=lambda v: (v.lineno, v.text))


def scan_violations(root: Path = SRC_ROOT) -> list[Violation]:
    """掃出 ``root`` 底下所有手寫的完成條件（canonical 模組除外）。"""
    out: list[Violation] = []
    for path in sorted(root.rglob("*.py")):
        if path.resolve() == CANONICAL_MODULE.resolve():
            continue
        out.extend(scan_file(path))
    return out


def group_by_file(violations: list[Violation]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for v in violations:
        counts[v.path] = counts.get(v.path, 0) + 1
    return counts


def render(violations: list[Violation]) -> str:
    return "\n".join(f"  {v.path}:{v.lineno}: {v.text}" for v in violations)


# ---------------------------------------------------------------------------
# 測試
# ---------------------------------------------------------------------------
def test_no_unallowlisted_handwritten_completion_condition() -> None:
    """``src/`` 內不得有 allowlist 以外的手寫完成條件。"""
    counts = group_by_file(scan_violations())
    offenders = [v for v in scan_violations() if v.path not in ALLOWLIST]
    assert not offenders, (
        "以下位置手寫了完成場判定，請改走 cpbl.completion 的 helper"
        "（鏈端沿用舊判準 completed_games_sql()；非鏈端用 "
        "completed_games_sql_with_evidence(alias)）：\n"
        + render(offenders)
        + "\n\n⚠️ 不要為了通關把它加進 allowlist——allowlist 只收「已有承接卡負責清掉」的既有項目。"
    )
    assert set(counts) <= set(ALLOWLIST)


def test_allowlist_counts_are_exact() -> None:
    """allowlist 的筆數必須與現況**精確相等**：只能縮小，不能膨脹也不能留殘骸。"""
    counts = group_by_file(scan_violations())
    drift = {
        path: (allowed.count, counts.get(path, 0))
        for path, allowed in ALLOWLIST.items()
        if counts.get(path, 0) != allowed.count
    }
    assert not drift, (
        "allowlist 與現況不符（格式：檔案 → (allowlist 筆數, 實際筆數)）：\n"
        + "\n".join(f"  {p}: {a} != {b}" for p, (a, b) in sorted(drift.items()))
        + "\n\n實際筆數變少＝有人清掉了，請把 allowlist 一起改小（或整項刪掉）；"
        "變多＝有人新寫了一處，請改走 helper。"
    )


def test_allowlist_entries_are_marked_and_attributed() -> None:
    """每一項都必須擇一標記；PENDING 必須帶卡號，REVIEWED 必須沒有卡號。

    兩邊都要擋：沒有卡號的 PENDING ＝ 沒有人負責清掉＝永久逃生門；帶了卡號的 REVIEWED
    ＝ 假裝有人要來改，承接卡結案時它還在，會被誤讀成遷移沒做完。
    """
    problems: list[str] = []
    for path, a in sorted(ALLOWLIST.items()):
        if a.status not in STATUSES:
            problems.append(f"{path}: status={a.status!r} 不在 {STATUSES}")
        if a.count <= 0:
            problems.append(f"{path}: count={a.count} 不得 <= 0")
        if not a.note.strip():
            problems.append(f"{path}: note 不得留空（PENDING 寫遷移方向，REVIEWED 寫為什麼不是缺陷）")
        if a.status == PENDING and not re.fullmatch(r"#\d+", a.card or ""):
            problems.append(f"{path}: PENDING 需要 #<issue> 格式的承接卡號，實得 {a.card!r}")
        if a.status == REVIEWED and a.card:
            problems.append(f"{path}: REVIEWED 不得帶卡號（沒有人要來改它），實得 {a.card!r}")
    assert not problems, "allowlist 標記/歸屬有問題：\n  " + "\n  ".join(problems)


def bucket_summary() -> dict[str, tuple[int, int]]:
    """回傳 {桶名: (檔數, 筆數)}，桶名為卡號或 REVIEWED——供交接時逐桶對帳。"""
    out: dict[str, list[int]] = {}
    for a in ALLOWLIST.values():
        key = a.card if a.status == PENDING else REVIEWED
        acc = out.setdefault(key, [0, 0])
        acc[0] += 1
        acc[1] += a.count
    return {k: (v[0], v[1]) for k, v in sorted(out.items())}


def test_bucket_totals_match_the_scan() -> None:
    """分桶加總必須等於實際掃描總數——桶內數字對、加總對不上一樣是帳錯了。"""
    files = sum(f for f, _ in bucket_summary().values())
    sites = sum(n for _, n in bucket_summary().values())
    found = scan_violations()
    assert (files, sites) == (len(ALLOWLIST), len(found)), (
        f"分桶加總 {files} 檔 {sites} 處 != 實際 {len(ALLOWLIST)} 檔 {len(found)} 處"
    )


# --- 可證偽性：守衛自己會不會失敗 -----------------------------------------
_INJECTION_SAMPLES = [
    "cur.execute('SELECT 1 FROM cpbl.games WHERE home_score + away_score > 0')",
    'cur.execute("... WHERE g.home_score+g.away_score>0 ...")',
    'sql = "WHERE away_score + home_score >= 1"',
    'sql = "WHERE home_score + away_score = 0"',
    'sql = "WHERE coalesce(home_score,0) + coalesce(away_score,0) > 0"',
    "done = (home_score or 0) + (away_score or 0) > 0",
]

# 跨行拆寫：逐行掃描抓不到（開發過程實測**確實漏掉**），靠 ast 把相鄰字串字面合併才擋得住。
_SPLIT_SAMPLES = [
    'def q(c):\n    c.execute(\n        "SELECT 1 FROM cpbl.games WHERE year=%s "\n'
    '        "AND home_score + "\n        "away_score > 0")\n',
    'def q(c):\n    c.execute(\n        "SELECT 1 FROM cpbl.games "\n'
    '        "WHERE home_score + away_score "\n        "> 0")\n',
    'def q(c):\n    c.execute(\n        f"SELECT 1 FROM cpbl.games WHERE year={y} "\n'
    '        "AND home_score + away_score > 0")\n',
]


def test_injected_condition_is_caught(tmp_path: Path) -> None:
    """注入一處新的手寫條件 → 必須被抓到（本測試的核心：守衛有能力失敗）。"""
    for i, snippet in enumerate(_INJECTION_SAMPLES):
        f = tmp_path / f"injected_{i}.py"
        f.write_text(f"def q():\n    {snippet}\n", encoding="utf-8")
        assert scan_file(f), f"未抓到注入樣本：{snippet}"


def test_condition_split_across_source_lines_is_caught(tmp_path: Path) -> None:
    """把條件拆成好幾行字串字面照樣要被抓到，而且**只算一處**（不得重複計數）。"""
    for i, snippet in enumerate(_SPLIT_SAMPLES):
        f = tmp_path / f"split_{i}.py"
        f.write_text(snippet, encoding="utf-8")
        hits = scan_file(f)
        assert len(hits) == 1, f"跨行樣本 {i} 命中 {len(hits)} 次（應為 1）：{hits}"


_INNOCENT_SAMPLES = [
    # 既有 8 個已採用 helper 的呼叫端形狀（此處取 api/routers/standings.py 與
    # ingest/run_refresh_recent.py 的實際寫法）
    'from cpbl.completion import completed_games_sql_with_evidence\n'
    '_DONE = completed_games_sql_with_evidence("games")\n',
    'sql = f"WHERE g.year = %s AND {completed_games_sql()}"\n',
    # 只讀比分、不做完成判定：不該被抓
    'sql = "SELECT home_score, away_score FROM cpbl.games"\n',
    'sql = "count(*) FILTER (WHERE home_score > away_score)"\n',
    'sql = "ORDER BY home_score+away_score DESC"\n',
]


def test_helper_call_sites_are_not_caught(tmp_path: Path) -> None:
    """已走 helper（以及純讀比分）的寫法不得被誤傷。"""
    for i, snippet in enumerate(_INNOCENT_SAMPLES):
        f = tmp_path / f"innocent_{i}.py"
        f.write_text(snippet, encoding="utf-8")
        assert not scan_file(f), f"誤傷了合法寫法：{snippet!r}"


def test_real_helper_call_site_is_clean() -> None:
    """真實檔案層級的不誤傷證明：``api/routers/standings.py`` 全檔走 helper，應零命中。"""
    target = SRC_ROOT / "cpbl" / "api" / "routers" / "standings.py"
    assert "completed_games_sql_with_evidence" in target.read_text(encoding="utf-8")
    assert scan_file(target) == []


def test_guard_runs_against_this_worktree() -> None:
    """釘住掃描根目錄＝本測試所在的那棵樹（避免「測在哪棵樹」的假象）。"""
    top = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert Path(top).resolve() == REPO_ROOT.resolve()
    assert SRC_ROOT.is_dir()


if __name__ == "__main__":
    found = scan_violations()
    print(render(found))
    print(f"TOTAL {len(found)} 處 / {len(group_by_file(found))} 檔")
    for path, n in sorted(group_by_file(found).items()):
        a = ALLOWLIST.get(path)
        tag = "未列入 allowlist" if a is None else (a.card if a.status == PENDING else REVIEWED)
        print(f"{n:3d}  {path:48s} {tag}")
    print("\n分桶：")
    for key, (f, n) in bucket_summary().items():
        print(f"  {key:22s} {f:3d} 檔 {n:3d} 處")
