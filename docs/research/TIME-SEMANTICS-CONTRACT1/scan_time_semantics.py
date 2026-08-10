"""TIME-SEMANTICS-CONTRACT1：時間語意用點盤點（**唯讀**，artifact 由本腳本產生）。

    uv run python docs/research/TIME-SEMANTICS-CONTRACT1/scan_time_semantics.py inventory
    uv run python docs/research/TIME-SEMANTICS-CONTRACT1/scan_time_semantics.py --verify

本腳本是**設計卡的盤點工具，不是守衛**。守衛（掃描器＋pytest 棘輪）是遷移批次 2
的交付物，屆時會把分類邏輯搬進 ``src/``／``tests/`` 並接上 CI。此處留在
``docs/research/`` 底下，因為本卡（T3 設計卡）的資源宣告只涵蓋兩個文件路徑。

## 分類軸

契約把時間切成 **3 個語意型別 ＋ 1 條時鐘位置規則**（見 ``docs/TIME_SEMANTICS_CONTRACT.md``）：

* ``instant``——絕對時點，一律 tz-aware UTC，存 ``timestamptz``。DB 端 ``now()``
  寫稽核欄合法（``timestamptz`` 存的是絕對時點，時區不參與）。
* ``business_date``——台北曆日。**時鐘一律住在 Python**，DB 不得自取；
  ``as_of`` 是它的參數形式，不是另一個型別。
* ``season``——球季年，由 business_date 導出。

嚴重度按**方向**分級，不按「在哪一層」——實測顯示層別幾乎不預測嚴重度：

======================= ================================================== ====
分類                    語意                                               級別
======================= ================================================== ====
``business_lower``      ``>= today``。UTC 落後會把**昨天**算成未來          P0
``business_exact``      ``= today``。直接指向錯的一天，晨間 8 小時全錯      P0
``business_label``      無比較運算的純標籤（如「今日賽事」）               P0
``season_derive``       ``today().year``。跨年那 8 小時給錯球季            P0
``business_upper``      ``<= today``。UTC 落後只會晚納入，方向保守；全庫    P1
                        實測差恰 1 場（DATA-TZ-COMPLETION-SKEW1，2026/D/119）
``business_db_taipei``  已用台北日，但時鐘仍住在 DB 端                     P2
``business_lower_window`` ``>= today - N``＝「近 N 天」窗口起點，非未來界線 P2
``business_binding``    綁到變數，方向取決於下游用法                       人工
``instant_naive``       naive ``datetime.now()``／``time.time()``           人工
``ts_ambient_clock``    TypeScript 無參數 ``new Date()``                    契約內
``instant_aware``       tz-aware 時點／``timestamptz`` 稽核欄寫入          合法
======================= ================================================== ====

P0＝產生**錯答案**，發現即修、不得進 allowlist。P1＝方向保守只是**遲答案**，
凍結不動但禁止新增，全部進 allowlist。P2＝不產生錯答案，屬「時鐘位置規則」的
遷移目標。

## 範圍（``scope`` 欄）

卡面範圍是 production／API／DB SQL／排程／測試，因此：

* ``in_scope``——``src/cpbl/``、``tests/``、``migrations/``、``scripts/*.sh``（排程）、
  ``.github/``、``web/``（Q1 定案：契約內、守衛外）。
* ``tooling``——``scripts/*.py``。一次性研究／稽核工具，其中的樣式多半是**偵測用
  regex 與說明文字**而非 runtime 語意。**逐筆保留在 artifact 裡**、只是不計入
  P0/P1 統計；不偷偷排除。
* ``self_reference``——本檔，以及 DATA-TZ-BOUNDARY1 的守衛測試
  ``tests/test_tz_boundary.py``（其字串常數是「斷言某樣式不存在」的偵測樣式，
  不是 runtime SQL；該卡自己也如此歸類）。走 ``git ls-files`` 必然掃到它們，
  **明確歸類而非排除**——否則盤點會在「工具入樹前 vs 入樹後」給出不同答案
  （DATA-TZ-BOUNDARY1 的 R1 查核實測過這個坑）。

## 分類的精確度界線（誠實聲明）

Python 側**時鐘呼叫**與**SQL 字串常數**都走 ``ast``：註解不進 AST、docstring 明確
排除，因此不會把說明文字誤計成用點。這是本盤點與逐行 grep 的關鍵差別。

但**方向**（upper／lower／exact／label）是啟發式：取 token 在同一個字串常數（或同
一行）內的前綴找比較運算子。因此 artifact 逐筆記錄 ``line_text``，任何一筆都可人工
複核；``needs_review`` 為 true 代表啟發式沒把握，**必須**人工裁定，不得直接採信。
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

OUT_DIR = Path("docs/research/TIME-SEMANTICS-CONTRACT1")
OUT_FILE = OUT_DIR / "inventory.json"

SELF_REFERENCE = (
    "docs/research/TIME-SEMANTICS-CONTRACT1/scan_time_semantics.py",
    # DATA-TZ-BOUNDARY1 的守衛測試：其字串常數是**偵測樣式**（斷言某樣式不存在），
    # 不是 runtime SQL。該卡自己也把它列為 SELF_REFERENCE_FILES，此處沿用同一判定。
    "tests/test_tz_boundary.py",
)

SUFFIX_LANG = {
    ".py": "python", ".sql": "sql", ".sh": "shell",
    ".ts": "ts", ".tsx": "ts", ".yml": "yaml", ".yaml": "yaml",
}

# 複合樣式**必須先比對**：它內含 now()，先佔位才不會被拆成兩筆。
_TAIPEI_SQL = re.compile(
    r"\(\s*now\(\)\s+AT TIME ZONE\s+'Asia/Taipei'\s*\)\s*::\s*date", re.I)
_SQL_TOKEN = re.compile(r"\bCURRENT_DATE\b|\bCURRENT_TIMESTAMP\b|\bnow\(\)", re.I)

# `>= CURRENT_DATE - 7`：token 後接減法＝窗口起點而非未來界線
_WINDOW_TAIL = re.compile(r"\s*-\s*")

_CLOCK_ATTRS = {"today", "now", "utcnow"}
_CLOCK_OWNERS = {"date", "datetime", "_date", "_dt"}

# 順序即優先權：`<=`／`>=`／`==` 必須先於裸 `=`，`<=` 必須先於 `<`。
_COMPARATORS = (("<=", "business_upper"), (">=", "business_lower"),
                ("==", "business_exact"), ("<", "business_upper"),
                (">", "business_lower"))

P0_KINDS = {"business_lower", "business_exact", "business_label", "season_derive"}
P1_KINDS = {"business_upper"}
MANUAL_KINDS = {"business_binding", "instant_naive", "ts_ambient_clock"}
# 已是台北日、但時鐘仍住在 DB：不產生錯答案，屬「時鐘位置規則」的遷移目標。
P2_KINDS = {"business_db_taipei", "business_lower_window"}


def _git_files() -> list[str]:
    """``git ls-files``＝**只列已追蹤檔**。

    ⚠️ 這一點曾實際咬過本卡（#123 查核 R1）：產生 artifact 時掃描器自身尚未
    ``git add``，於是它掃不到自己；``git add`` 之後多出 2 個字面命中，
    ``--verify`` 隨即失效。這就是 docstring「自指」節說的「工具入樹前 vs 入樹後
    給出不同答案」——寫下警告不代表免疫，所以此處改成**機械擋**。
    """
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True)
    files = [p for p in out.stdout.splitlines() if Path(p).suffix in SUFFIX_LANG]
    for required in SELF_REFERENCE:
        if Path(required).exists() and required not in files:
            raise SystemExit(
                f"中止：{required} 存在於工作樹但未被 git 追蹤。"
                f"\n掃描母體取自 git ls-files，未追蹤的檔案掃不到，"
                f"產出的 artifact 會在該檔入樹後立刻失效。"
                f"\n請先 `git add {required}` 再重跑。")
    return files


def _scope_of(path: str) -> str:
    if path in SELF_REFERENCE:
        return "self_reference"
    if path.startswith("scripts/") and path.endswith(".py"):
        return "tooling"
    if path.startswith("docs/"):
        return "tooling"
    return "in_scope"


def _area_of(path: str) -> str:
    for prefix in ("src/cpbl/api", "src/cpbl/ingest", "src/cpbl/models",
                   "src/cpbl/features", "src/cpbl", "tests", "scripts",
                   "migrations", "web", "docs", ".github"):
        if path.startswith(prefix):
            return prefix
    return "other"


def _classify_direction(prefix: str, *, assign_is_comparison: bool) -> tuple[str, bool]:
    """由 token **之前**的文字推斷比較方向。回傳 (分類, needs_review)。"""
    tail = prefix.rstrip()
    for op, kind in _COMPARATORS:
        if tail.endswith(op):
            return kind, False
    if tail.endswith("="):
        # 裸 `=`：SQL 是比較（`game_date = CURRENT_DATE`），Python 是賦值。
        if assign_is_comparison:
            return "business_exact", False
        return "business_binding", True
    return "business_label", True


def _dotted(node: ast.AST) -> str:
    parts: list[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


def _docstring_ids(tree: ast.Module) -> set[int]:
    """所有 docstring 節點的 id()——它們是說明文字，不是 runtime 字串。"""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def _sql_sites_in_text(path: str, line: int, text: str, line_text: str,
                       source: str) -> list[dict[str, Any]]:
    """在一段文字（SQL 字串常數或 .sql/.sh 的一行）內找時鐘 token。"""
    found: list[dict[str, Any]] = []
    taipei_spans: list[tuple[int, int]] = []
    for m in _TAIPEI_SQL.finditer(text):
        taipei_spans.append(m.span())
        direction, _ = _classify_direction(text[:m.start()], assign_is_comparison=True)
        found.append({"path": path, "line": line, "kind": "business_db_taipei",
                      "direction": direction, "token": "TAIPEI_TODAY_SQL",
                      "clock": "db", "source": source,
                      "line_text": line_text[:160], "needs_review": False})

    for m in _SQL_TOKEN.finditer(text):
        if any(s <= m.start() < e for s, e in taipei_spans):
            continue
        tok = m.group(0)
        prefix = text[:m.start()]
        if re.search(r"DEFAULT\s*$", prefix, re.I):
            kind, needs = "instant_aware", False
        elif tok.lower() in ("now()", "current_timestamp"):
            # now() 只有跟日期做**不等式**比較時才是 business；`x = now()` 是稽核欄寫入。
            direction, _ = _classify_direction(prefix, assign_is_comparison=False)
            if direction in ("business_upper", "business_lower"):
                kind, needs = direction, False
            else:
                kind, needs = "instant_aware", False
        else:  # CURRENT_DATE：SQL 裡的 `=` 是比較
            kind, needs = _classify_direction(prefix, assign_is_comparison=True)
            if kind == "business_lower" and _WINDOW_TAIL.match(text[m.end():]):
                # `>= CURRENT_DATE - N`＝「近 N 天」窗口起點，不是「今天起的未來」。
                # UTC 落後只會把窗口多往前開一天＝多做工，方向仍保守。
                kind, needs = "business_lower_window", False
        found.append({"path": path, "line": line, "kind": kind, "token": tok,
                      "clock": "db", "source": source,
                      "line_text": line_text[:160], "needs_review": needs})
    return found


def _scan_python(path: str, src: str, lines: list[str]) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return [{"path": path, "line": 0, "kind": "parse_error", "token": "",
                 "clock": "", "source": "", "line_text": "", "needs_review": True}]

    doc_ids = _docstring_ids(tree)
    found: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        lineno = getattr(node, "lineno", 0)
        line_text = lines[lineno - 1].strip() if 0 < lineno <= len(lines) else ""

        # (1) Python 端時鐘呼叫
        if isinstance(node, ast.Call):
            token = ""
            attr = ""
            if isinstance(node.func, ast.Attribute) and node.func.attr in _CLOCK_ATTRS:
                dotted = _dotted(node.func)
                owner = dotted.split(".")[-2] if "." in dotted else ""
                if owner in _CLOCK_OWNERS:
                    token, attr = f"{dotted}()", node.func.attr
            elif _dotted(node.func) == "time.time":
                token, attr = "time.time()", "time"

            if token:
                raw = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                if attr in ("now", "utcnow", "time"):
                    aware = attr == "now" and bool(node.args or node.keywords)
                    kind = "instant_aware" if aware else "instant_naive"
                    needs = not aware
                else:  # today()
                    end = node.end_col_offset or 0
                    if raw[end:end + 6].startswith(".year"):
                        kind, needs = "season_derive", False
                    else:
                        kind, needs = _classify_direction(
                            raw[:node.col_offset], assign_is_comparison=False)
                found.append({"path": path, "line": node.lineno, "kind": kind,
                              "token": token, "clock": "python", "source": "code",
                              "line_text": line_text[:160], "needs_review": needs})

        # (2) SQL 字串常數（**排除 docstring**——那是說明不是查詢）
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in doc_ids:
                continue
            found += _sql_sites_in_text(path, node.lineno, node.value,
                                        line_text, "py_string")
    return found


def _scan_lines(path: str, lines: list[str], source: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for i, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if stripped.startswith(("--", "#")):
            continue
        found += _sql_sites_in_text(path, i, raw, stripped, source)
    return found


def _scan_ts(path: str, lines: list[str]) -> list[dict[str, Any]]:
    """TypeScript：無參數 `new Date()` ＝ 取環境時鐘；有參數者是解析既有值，不計。"""
    found: list[dict[str, Any]] = []
    for i, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if stripped.startswith(("//", "*")):
            continue
        for _ in re.finditer(r"new Date\(\s*\)", raw):
            found.append({"path": path, "line": i, "kind": "ts_ambient_clock",
                          "token": "new Date()", "clock": "browser_or_ssr",
                          "source": "code", "line_text": stripped[:160],
                          "needs_review": True})
    return found


def scan() -> dict[str, Any]:
    sites: list[dict[str, Any]] = []
    for path in _git_files():
        lang = SUFFIX_LANG[Path(path).suffix]
        try:
            src = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lines = src.splitlines()

        if lang == "python":
            hits = _scan_python(path, src, lines)
        elif lang in ("sql", "shell", "yaml"):
            hits = _scan_lines(path, lines, lang)
        else:
            hits = _scan_ts(path, lines)

        scope = _scope_of(path)
        for h in hits:
            h["scope"] = scope
            h["area"] = _area_of(path)
        sites += hits

    sites.sort(key=lambda s: (s["path"], s["line"], s["token"]))
    in_scope = [s for s in sites if s["scope"] == "in_scope"]

    by_kind: dict[str, int] = {}
    by_area: dict[str, dict[str, int]] = {}
    for s in in_scope:
        by_kind[s["kind"]] = by_kind.get(s["kind"], 0) + 1
        by_area.setdefault(s["area"], {})
        by_area[s["area"]][s["kind"]] = by_area[s["area"]].get(s["kind"], 0) + 1

    by_scope: dict[str, int] = {}
    for s in sites:
        by_scope[s["scope"]] = by_scope.get(s["scope"], 0) + 1

    return {
        "generated_by": "docs/research/TIME-SEMANTICS-CONTRACT1/scan_time_semantics.py",
        "note": "統計只計 in_scope；tooling／self_reference 逐筆保留在 sites 內供複核。",
        "total_sites": len(sites),
        "by_scope": dict(sorted(by_scope.items())),
        "in_scope_total": len(in_scope),
        "in_scope_by_kind": dict(sorted(by_kind.items())),
        "in_scope_by_area": {k: dict(sorted(v.items())) for k, v in sorted(by_area.items())},
        "p0_count": sum(1 for s in in_scope if s["kind"] in P0_KINDS),
        "p1_count": sum(1 for s in in_scope if s["kind"] in P1_KINDS),
        "p2_count": sum(1 for s in in_scope if s["kind"] in P2_KINDS),
        "manual_count": sum(1 for s in in_scope if s["kind"] in MANUAL_KINDS),
        "needs_review_count": sum(1 for s in in_scope if s["needs_review"]),
        "sites": sites,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="時間語意用點盤點")
    ap.add_argument("cmd", nargs="?", default="inventory", choices=["inventory"])
    ap.add_argument("--verify", action="store_true",
                    help="重跑並與已提交的 inventory.json 比對，不一致則 exit 1")
    args = ap.parse_args(argv)

    result = scan()
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"

    if args.verify:
        if not OUT_FILE.exists():
            print(f"FAIL：{OUT_FILE} 不存在", file=sys.stderr)
            return 1
        if OUT_FILE.read_text(encoding="utf-8") != payload:
            print(f"FAIL：{OUT_FILE} 與現行工作樹掃描結果不一致", file=sys.stderr)
            return 1
        print(f"OK：{OUT_FILE} 與工作樹一致（in_scope {result['in_scope_total']} 筆）")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(payload, encoding="utf-8")
    print(f"寫入 {OUT_FILE}")
    print(f"  總命中 {result['total_sites']}（{result['by_scope']}）")
    print(f"  in_scope={result['in_scope_total']}  P0={result['p0_count']}  "
          f"P1={result['p1_count']}  待人工={result['manual_count']}")
    for kind, n in result["in_scope_by_kind"].items():
        print(f"    {kind:20s} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
