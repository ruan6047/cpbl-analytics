"""ML-PITCHER-SCORELESS2：對基線的「零可執行邏輯變更」是斷言出來的，不是人工聲明。

背景（見 `docs/research/ML-PITCHER-SCORELESS2_RESULTS.md` §4、
`docs/tasks/ML-PITCHER-SCORELESS2.md`）：memo 曾三次把「這輪 diff 只動了
docstring／註解」的宣稱寫死成具體行數——iteration 2 說 diff 為空（實測非空）、
iteration 3 說 `+25/-1`（實測 `+26/-1`，因為 iteration 3 自己又替 docstring
多加一行，18→19，文字沒跟著改）。行數是「本輪自己也在改的那份 diff」的產物，
每改一次 memo 就可能讓它自己失效——把 25 改成 26 治不好，下一次補一行註解又會破。

治法不是更新數字，是不再把「無邏輯變更」寫成人工維護的行數，改成本測試斷言：
比較 baseline 與現況兩份原始碼的 **AST**（剝除模組／函式／類別 docstring 後），
逐節點結構相同即代表零可執行邏輯變更。選 AST 而不是逐行過濾註解的理由：

- Python 剖析器本來就完全丟棄註解（`#` 開頭），不需要額外過濾規則、不會漏判
  註解變體（行內註解、多個 `#`、字串裡的 `#`……逐行 regex 容易踩的雷）。
- docstring 是唯一需要手動剝除的例外——它在語法上是一個 `Expr(Constant(str))`
  陳述式；剝除規則用的正是 `ast.get_docstring` 的判定條件：suite 的第一句是
  裸字串常數。
- `ast.dump()` 預設不含 `lineno`/`col_offset`，新增註解列造成的行號位移不會
  誤判成差異。

若 baseline commit 在目前 checkout 不可解析（shallow clone／未 fetch 到此段
歷史），測試**跳過並說明原因**——不代表「已驗證無變更」，只是本環境驗不了；
不靜默通過，也不因環境限制硬失敗。
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASELINE_SHA = "b974b10"
CHECK_DIRS = ("src", "scripts")

DOCSTRING_HOLDERS = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args],
                           capture_output=True, text=True, check=check)


def _baseline_available() -> bool:
    return _git("rev-parse", "--verify", "--quiet", f"{BASELINE_SHA}^{{commit}}",
                check=False).returncode == 0


def _changed_python_files() -> list[str]:
    out = _git("diff", "--name-only", BASELINE_SHA, "--", *CHECK_DIRS).stdout
    return [p for p in out.splitlines() if p.endswith(".py")]


def _source_at_baseline(path: str) -> str | None:
    """`path` 在基線是否存在；不存在（新增檔案）回 None。"""
    result = _git("show", f"{BASELINE_SHA}:{path}", check=False)
    return result.stdout if result.returncode == 0 else None


def _strip_docstrings(tree: ast.AST) -> ast.AST:
    """剝除 Module/FunctionDef/AsyncFunctionDef/ClassDef suite 開頭的裸字串常數陳述式。

    判定條件與 `ast.get_docstring` 相同：suite 的第一句是 `Expr(Constant(value=str))`。
    這是唯一需要手動處理的「合法語法但不影響執行」節點——其餘註解在剖析階段已被
    Python 剖析器完全丟棄，AST 裡本來就不存在，不需要額外處理。
    """
    for node in ast.walk(tree):
        if isinstance(node, DOCSTRING_HOLDERS):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:]
    return tree


def _ast_signature(source: str) -> str:
    tree = _strip_docstrings(ast.parse(source))
    return ast.dump(tree, annotate_fields=True, include_attributes=False)


@pytest.fixture(scope="module", autouse=True)
def _require_baseline():
    if not _baseline_available():
        pytest.skip(f"基線 commit {BASELINE_SHA} 在此 checkout 無法解析"
                     "（shallow clone 或未 fetch 到此段歷史）——不代表無邏輯變更，"
                     "只是本環境驗不了，須換一個能看到完整歷史的環境重跑")


def test_src_and_scripts_have_no_executable_change_since_baseline():
    """`git diff b974b10 -- src scripts` 涉及的每個 .py 檔，AST（剝除 docstring）必須與基線相同。

    這條成立即等同於 RESULTS.md／卡面歷次宣稱的「零可執行邏輯變更、API payload
    與基線相同」——不再需要人工報行數，diff 內容本身自動驗證，行號漂移也不會
    讓斷言跟著漂移。
    """
    files = _changed_python_files()
    assert files, (
        f"git diff --name-only {BASELINE_SHA} 對 {CHECK_DIRS} 沒有變更檔案——"
        "若這是預期狀態（例如已完全回到基線），本測試的存在意義改變，"
        "應同步更新這裡的斷言範圍，不該讓空清單悄悄通過")

    mismatches: list[str] = []
    for path in files:
        baseline_source = _source_at_baseline(path)
        current_path = ROOT / path
        if not current_path.exists():
            mismatches.append(f"{path}：檔案已刪除，無基準可比，視為潛在邏輯變更")
            continue
        if baseline_source is None:
            mismatches.append(f"{path}：基線不存在此檔（新增檔案），AST 無基準可比，視為邏輯變更")
            continue
        current_source = current_path.read_text(encoding="utf-8")
        if _ast_signature(baseline_source) != _ast_signature(current_source):
            mismatches.append(f"{path}：剝除 docstring 後 AST 仍不同——存在可執行邏輯變更")

    assert not mismatches, (
        f"以下檔案相對基線 {BASELINE_SHA} 有可執行邏輯變更（非純 docstring／註解）：\n  "
        + "\n  ".join(mismatches))
