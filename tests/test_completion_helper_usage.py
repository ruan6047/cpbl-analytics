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

⚠️ **allowlist 的構造性限制**：以「檔案 → 允許筆數 ＋ 承接卡號」記錄，且比對是**精確
相等**。少一筆（有人清掉了）會紅，逼 allowlist 縮小；多一筆（有人新寫）也會紅。
每一項都必須帶卡號，沒有卡號的項目在 :func:`test_allowlist_entries_carry_a_card`
就被擋下——一個什麼都放行、或放行了卻沒人負責清掉的 allowlist 等於沒有守衛。
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


@dataclass(frozen=True)
class Allowed:
    count: int
    card: str          # 承接卡號，格式 ``#<issue>``
    note: str = ""


# ---------------------------------------------------------------------------
# allowlist
#
# ⚠️ 這裡**只能**放「已經存在、且已有承接卡負責清掉」的手寫條件。新寫的一律修掉，
# 不要往這裡加。每一項的 count 是**精確**筆數，比對不相等即紅。
# ---------------------------------------------------------------------------
# ⚠️ **承接卡歸屬待 PM 裁定**：DEV-COMPLETION-CONDITION-GUARD1（#153）派工時指定
# 「B 群 7 處必須進 allowlist、每項填卡號」，但派工包同時載明**承接卡尚未開立**。
# 本檔一律先歸屬 **#90 DATA-TIE-REMEDY1**（OPEN）——那是 `cpbl.completion` 模組 docstring
# 自己指名的兩代判準切換負責卡（鏈端 Phase 2、非鏈端切新判準），不是隨手填的佔位；
# PM 開出承接卡後請整批換號。
#
# ⚠️ 另：實際掃描結果**遠多於派工包所列的 B 群 7 處**——A 群修掉後仍有 17 檔 22 處。
# 差額來自判準改為「字面存在性」（乙案）：原盤點的「9 處無界線候選」是舊啟發式的產物，
# 另外 13 處（自帶手寫日期界線者）在乙案下同樣是手寫條件，同樣違規。詳見交付報告。
_CARD = "#90"

ALLOWLIST: dict[str, Allowed] = {
    # --- B 群（派工包點名的 7 處；非 refresh 鏈，應改用新判準 with_evidence） ---
    "src/cpbl/api/routers/people.py": Allowed(1, _CARD, "B群；ORDER BY game_date DESC LIMIT 15，假完成場直接佔第一名"),
    "src/cpbl/api/routers/teams.py": Allowed(1, _CARD, "B群"),
    "src/cpbl/api/routers/venues.py": Allowed(1, _CARD, "B群"),
    "src/cpbl/models/pa_sim.py": Allowed(1, _CARD, "B群"),
    "src/cpbl/models/pitch_type.py": Allowed(1, _CARD, "B群"),
    "src/cpbl/models/special_records.py": Allowed(1, _CARD, "B群；同檔另有 _DONE 已走 with_evidence"),
    "src/cpbl/models/winprob.py": Allowed(1, _CARD, "B群"),

    # --- 每日 refresh 鏈（自帶手寫日期界線；依 completion.py docstring 屬 Phase 2 才切） ---
    "src/cpbl/ingest/cpbl_gamelog.py": Allowed(2, _CARD, "refresh 鏈目標場清單；等 #53 G4 Phase B"),
    "src/cpbl/ingest/cpbl_pitch_tracking.py": Allowed(1, _CARD, "refresh 鏈目標場清單；等 #53 G4 Phase B"),

    # --- 非鏈端、但不在派工包盤點內（乙案下才浮現） ---
    "src/cpbl/api/routers/recap.py": Allowed(1, _CARD, "coalesce() 包裝的變體，原盤點正則掃不到"),
    "src/cpbl/api/team_focus.py": Allowed(1, _CARD, "自帶手寫日界，乙案下仍違規"),
    "src/cpbl/api/team_hotzone.py": Allowed(1, _CARD, "自帶手寫日界；同檔另有 with_evidence 呼叫端"),
    "src/cpbl/models/winprob_strength.py": Allowed(4, _CARD, "自帶手寫日界，乙案下仍違規"),
    "src/cpbl/models/winprob_val.py": Allowed(2, _CARD, "自帶手寫日界，乙案下仍違規"),

    # --- 補集寫法（`= 0`＝「未開打」）：同一判準的另一面 ---
    "src/cpbl/api/routers/daily.py": Allowed(1, _CARD, "= 0 補集；同檔完成判定本身已走 is_completed_game"),
    "src/cpbl/api/routers/info.py": Allowed(1, _CARD, "= 0 補集"),
    "src/cpbl/models/matchup.py": Allowed(1, _CARD, "= 0 補集"),
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


def test_allowlist_entries_carry_a_card() -> None:
    """allowlist 每一項都必須帶承接卡號——沒有卡號＝沒有人負責清掉＝永久逃生門。"""
    bad = {p: a.card for p, a in ALLOWLIST.items() if not re.fullmatch(r"#\d+", a.card or "")}
    assert not bad, f"allowlist 項目缺少或格式錯誤的卡號（需 #<issue>）：{bad}"
    assert all(a.count > 0 for a in ALLOWLIST.values()), "allowlist 不得有 count<=0 的空項目"


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
    print(f"TOTAL {len(found)}")
    for path, n in sorted(group_by_file(found).items()):
        print(f"{n:3d}  {path}")
