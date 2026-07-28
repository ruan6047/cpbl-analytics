#!/usr/bin/env python
"""窮舉「把缺值折成有效值」的寫法（ML-PITCHER-SCORELESS1 紅線 2 的守衛）。

## 為什麼是 AST 而不是 grep

iteration 10 用 grep 版本，查核者用合成反例實測漏抓四種形式：

    value if value is not None else 0    ← 條件運算式
    mapping.setdefault(key, 0)           ← setdefault 預設
    defaultdict(int)                     ← 容器層預設
    CASE WHEN value IS NULL THEN 0       ← SQL 端

**正則只看得到字面，AST 看得到語意結構**——這正是本卡一路上的同一個教訓：
檢查標記的存在或缺席，不等於檢查該成立的性質。grep 版另有兩個副作用：註解行會被
當成命中（噪音），以及巢狀括號會讓 `.get\\([^)]*, …` 提早斷掉（漏抓）。AST 兩者都沒有。

SQL 仍以字串樣式補足（AST 看不進 SQL 字串內部），只掃字串常數而非整份原始碼。

## 用法

    uv run python scripts/check_scoreless_null_folding.py

每一處命中都必須是下列之一，否則即為缺陷：
  (a) 已改為保留 None／未知並 fail-closed
  (b) 就地註解說明為何該處折疊無害（且說明要能被獨立驗證）

輸出供人工覆核，**不自動判定通過**——它的職責是讓「我掃過了」這句話可被覆核。

**刻意過度回報**：累加器（`defaultdict(int)`）、建巢狀 dict 的 `setdefault(k, {})`、
顯示用的 `x if x else 0` 都會被列出來。它們多半無害，但少列一個真的折疊比多列十個
無害樣態危險得多——iteration 10 的 grep 版正是因為想「精準」而漏抓。
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    "src/cpbl/api/scoreless.py",
    "src/cpbl/models/scoreless_streak.py",
    "scripts/reconcile_scoreless_streak.py",
]

# SQL 端的折疊（AST 看不進字串內部）
_SQL = re.compile(r"COALESCE|IFNULL|CASE\s+WHEN[^)]*?IS\s+NULL\s+THEN", re.I | re.S)

_FOLD_DEFAULTS = ("get", "setdefault", "pop")
_CONTAINER_FACTORIES = ("defaultdict",)


def _is_falsy_const(node: ast.AST) -> bool:
    """0 / '' / False / 0.0 / {} / [] / () —— 這些當預設值就是把「未知」折成「已知」。"""
    if isinstance(node, ast.Constant):
        return node.value in (0, "", False, 0.0) or node.value is None and False
    return isinstance(node, ast.Dict | ast.List | ast.Tuple | ast.Set) and not (
        getattr(node, "elts", None) or getattr(node, "keys", None))


class _Finder(ast.NodeVisitor):
    def __init__(self, path: str, src: str) -> None:
        self.path, self.lines = path, src.splitlines()
        self.hits: list[tuple[int, str, str]] = []

    def _add(self, node: ast.AST, kind: str) -> None:
        line = getattr(node, "lineno", 0)
        text = self.lines[line - 1].strip() if 0 < line <= len(self.lines) else ""
        self.hits.append((line, kind, text))

    def visit_BoolOp(self, node: ast.BoolOp) -> None:      # x or 0 / x or {}
        if isinstance(node.op, ast.Or) and any(_is_falsy_const(v) for v in node.values[1:]):
            self._add(node, "or-fallback")
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:         # a if cond else 0
        if _is_falsy_const(node.body) or _is_falsy_const(node.orelse):
            self._add(node, "conditional-fallback")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else (
            fn.id if isinstance(fn, ast.Name) else "")
        if name in _FOLD_DEFAULTS and len(node.args) >= 2:
            self._add(node, f".{name}(…, 預設)")
        elif name in _CONTAINER_FACTORIES and node.args:
            self._add(node, "defaultdict(工廠)")
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:   # SQL 字串內的折疊
        if isinstance(node.value, str) and _SQL.search(node.value):
            self._add(node, "SQL 折疊（COALESCE/IFNULL/CASE…IS NULL）")
        self.generic_visit(node)


def scan(path: Path) -> list[tuple[int, str, str]]:
    src = path.read_text(encoding="utf-8")
    finder = _Finder(str(path), src)
    finder.visit(ast.parse(src))
    return sorted(set(finder.hits))


def main() -> int:
    total = 0
    print("掃描（AST；SQL 以字串樣式補足）")
    for rel in TARGETS:
        path = ROOT / rel
        hits = scan(path)
        total += len(hits)
        print(f"\n=== {rel}：{len(hits)} 處 ===")
        for line, kind, text in hits:
            print(f"  {rel}:{line}  [{kind}]  {text}")
    print(f"\n總命中：{total}")
    print("\n每一處都必須是下列之一，否則即為缺陷：")
    print("  (a) 已改為保留 None／未知並 fail-closed")
    print("  (b) 就地註解說明為何該處折疊無害（且說明要能被獨立驗證）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
