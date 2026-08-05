"""DATA-TZ-BOUNDARY1：日期界線時區用點盤點（**唯讀**，artifact 由本腳本產生）。

    uv run python scripts/data_tz_boundary1.py inventory
    uv run python scripts/data_tz_boundary1.py window     # DB 端雙時區日界差示範

背景（AUDIT1 C12）：DB ``SHOW timezone`` = UTC，而球季作息與 game_date 全是台北日。
台北 00:00–07:59 這段，``CURRENT_DATE`` 仍停在前一日 → 日期界線整批偏移一天。

**方向不對稱**（本卡實測補正 AUDIT1 的「range 一律無害」說法）：

* ``<= CURRENT_DATE``（上界／「不含未來」）：UTC 落後 → 收得**更少** → 保守，不會誤納。
* ``>= CURRENT_DATE``（下界／「今天起的未來」）：UTC 落後 → 收得**更多** →
  把昨天的場次也算成「未來待打」，方向**不保守**。
* ``= CURRENT_DATE``（精確等值）：直接指向錯誤的一天，晨間 8 小時全錯。

分類為機器判定：Python 用 ``tokenize``＋``ast`` 精確排除註解與 docstring，
SQL 用 ``--`` 前綴，避免把說明文字誤計為程式用點。
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import os
import re
import subprocess
import tokenize
from datetime import UTC, datetime
from typing import Any

OUT_DIR = "docs/research/DATA-TZ-BOUNDARY1"

# 本卡授權可改的寫入集（與 DEV-CLI-HELP-GUARD1 互斥）
IN_SCOPE_PREFIXES = (
    "src/cpbl/api/", "src/cpbl/models/", "src/cpbl/features/", "src/cpbl/completion.py")
# G4 觀測凍結＋平行卡佔用：只記錄不改
CHAIN_FROZEN_PREFIX = "src/cpbl/ingest/"

# 掃描對象含 TAIPEI_TODAY_SQL：已修正的用點必須在盤點裡「看得見」，
# 否則修好的點只會從清單消失，artifact 就無法自證修復（只能證明「不見了」）。
_TOKEN_RE = re.compile(
    r"CURRENT_DATE|CURRENT_TIMESTAMP|\bnow\s*\(\s*\)|TAIPEI_TODAY_SQL", re.I)
_TAIPEI_RE = re.compile(r"AT TIME ZONE\s+'Asia/Taipei'|TAIPEI_TODAY_SQL")


def _now_iso() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def _dump(obj: Any, out: str | None) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    if out:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print(f"written: {out} ({len(text)} bytes)")
    else:
        print(text)


def _nonexec_lines_py(src: str) -> set[int]:
    """回傳「非執行語意」的行號集合：``#`` 註解 ＋ docstring 覆蓋的行。

    用 tokenize／ast 而非字串啟發式——說明文字裡的 CURRENT_DATE 不該被算成用點。
    """
    out: set[int] = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                out.add(tok.start[0])
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef
                          | ast.AsyncFunctionDef):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            out.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return out


# Python 端「談論 CURRENT_DATE」而非「使用」它的痕跡（分析腳本自己的正規式／輸出鍵）
_META_MARKERS = re.compile(
    r"re\.search|re\.match|not in line|in line\b|out\[|Counter\(|usage|_RE\s*=|str\(r\[")


def _classify(line: str) -> str:
    """依界線方向分類——方向決定 UTC 落後是保守還是過度納入。"""
    if _TAIPEI_RE.search(line):
        return "already_taipei"
    # DDL 預設值：純寫入時戳，不參與日期比較
    if re.search(r"DEFAULT\s+(CURRENT_TIMESTAMP|CURRENT_DATE|now\s*\(\s*\))", line, re.I):
        return "timestamp_write"
    # 函式預設參數（如 completed_games_sql(as_of_sql="CURRENT_DATE")）：語意由呼叫端決定
    if re.search(r"def\s+\w+\s*\(.*CURRENT_DATE", line, re.I) or \
       re.search(r"as_of_sql\s*[:=].*CURRENT_DATE", line, re.I):
        return "default_parameter"
    # 分析腳本在「談論」這個字串，不是在下界線
    if _META_MARKERS.search(line):
        return "meta_reference"
    # 視窗位移（CURRENT_DATE - N／- %s::int）先判，否則會被上下界規則吃掉
    if re.search(r"CURRENT_DATE\s*[-+]\s*\S", line, re.I) or \
       re.search(r"\S\s*[-+]\s*CURRENT_DATE", line, re.I):
        return "window_offset"
    if re.search(r"[<>]=?\s*\(?\s*CURRENT_(DATE|TIMESTAMP)", line, re.I):
        return ("upper_bound" if re.search(r"<=?\s*\(?\s*CURRENT_", line, re.I)
                else "lower_bound")
    if re.search(r"CURRENT_(DATE|TIMESTAMP)\s*[<>]=?", line, re.I):
        # 反向寫法：CURRENT_DATE >= x 等價於 x <= CURRENT_DATE
        return ("lower_bound" if re.search(r"CURRENT_\w+\s*<=?", line, re.I)
                else "upper_bound")
    if re.search(r"=\s*CURRENT_(DATE|TIMESTAMP)", line, re.I):
        return "exact_equality"
    if re.search(r"\bnow\s*\(\s*\)", line, re.I):
        return "timestamp_write"
    return "unclassified"


def _zone(path: str) -> str:
    if path.startswith(CHAIN_FROZEN_PREFIX):
        return "chain_frozen"
    if path.startswith(IN_SCOPE_PREFIXES):
        return "in_scope"
    if path.startswith("migrations/"):
        return "migrations"
    if path.startswith("scripts/"):
        return "scripts"
    if path.startswith("tests/"):
        return "tests"
    return "other"


# 各分類的時區敏感度判定（方向決定 UTC 落後的效果）
SENSITIVITY = {
    "exact_equality": ("敏感-高", "直接指向錯誤的一天；台北 00:00–07:59 全錯"),
    "lower_bound": ("敏感-中", "UTC 落後使下界過度納入——昨天的場次被算成「今天起」"),
    "window_offset": ("敏感-中", "整個視窗連動位移一天"),
    "upper_bound": ("無害-保守", "UTC 落後只會晚 8 小時納入，永不誤納未來場"),
    "timestamp_write": ("無害", "純寫入時戳（trained_at/fetched_at/DEFAULT），不參與日期界線比較"),
    "already_taipei": ("已修正", "已用 Asia/Taipei 模式"),
    "default_parameter": ("敏感-低", "helper 預設參數；實際語意由呼叫端傳入值決定"),
    "meta_reference": ("無害", "分析腳本在談論這個字串（正規式／輸出鍵），非日期界線用點"),
    "unclassified": ("待人工判讀", "未落入既有規則，需人工看上下文"),
}


def cmd_inventory(args: argparse.Namespace) -> dict:
    files = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                           check=True).stdout.split()
    hits = []
    for path in files:
        if not path.endswith((".py", ".sql")):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        if not _TOKEN_RE.search(src):
            continue
        nonexec = _nonexec_lines_py(src) if path.endswith(".py") else set()
        for i, line in enumerate(src.splitlines(), 1):
            if not _TOKEN_RE.search(line):
                continue
            is_comment = (i in nonexec) or (path.endswith(".sql")
                                            and line.lstrip().startswith("--"))
            category = "comment_or_string" if is_comment else _classify(line)
            sens, why = SENSITIVITY.get(category, ("說明文字", "註解／docstring，非程式用點"))
            hits.append({
                "file": path, "line": i, "zone": _zone(path),
                "category": category, "sensitivity": sens, "rationale": why,
                "code": line.strip()[:160],
            })

    def tally(key):
        out: dict[str, int] = {}
        for h in hits:
            out[h[key]] = out.get(h[key], 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    executable = [h for h in hits if h["category"] != "comment_or_string"]
    sensitive = [h for h in executable
                 if h["sensitivity"].startswith("敏感")]
    return {
        "generated_at": _now_iso(),
        "db_timezone_note": "DB SHOW timezone = UTC；game_date 語意為台北日。",
        "direction_asymmetry": (
            "AUDIT1 C12 把 range 一律視為無害，本卡實測補正：只有**上界**（<=）"
            "在 UTC 落後時是保守的；**下界**（>=）方向相反，會把昨天算進「今天起」。"),
        "total_occurrences": len(hits),
        "executable_occurrences": len(executable),
        "by_category": tally("category"),
        "by_zone": tally("zone"),
        "by_sensitivity": tally("sensitivity"),
        "sensitive_total": len(sensitive),
        "sensitive_in_scope": sorted(
            f"{h['file']}:{h['line']}" for h in sensitive if h["zone"] == "in_scope"),
        "sensitive_chain_frozen_record_only": sorted(
            f"{h['file']}:{h['line']}" for h in sensitive if h["zone"] == "chain_frozen"),
        "sensitive_outside_write_set": sorted(
            f"{h['file']}:{h['line']}" for h in sensitive
            if h["zone"] not in ("in_scope", "chain_frozen")),
        "needs_human_review": [h for h in executable
                               if h["category"] == "unclassified"],
        "hits": hits,
    }


def cmd_window(args: argparse.Namespace) -> dict:
    """DB 端證明「雙時區日界差窗口」存在——餵定值時刻，不依賴執行當下的牆鐘。"""
    from cpbl.db import conn

    with conn() as c, c.cursor() as cur:
        cur.execute("SHOW timezone")
        tz = cur.fetchone()[0]
        cur.execute("""
            SELECT ts::text,
                   (ts AT TIME ZONE 'UTC')::date::text,
                   (ts AT TIME ZONE 'Asia/Taipei')::date::text
            FROM (VALUES (timestamptz '2026-08-05 00:00+08'),
                         (timestamptz '2026-08-05 03:00+08'),
                         (timestamptz '2026-08-05 07:59+08'),
                         (timestamptz '2026-08-05 08:00+08'),
                         (timestamptz '2026-08-05 21:00+08')) v(ts)
        """)
        rows = [{"taipei_wallclock": a, "utc_date": b, "taipei_date": cdt,
                 "differs": b != cdt} for a, b, cdt in cur.fetchall()]
    return {
        "generated_at": _now_iso(),
        "db_timezone": tz,
        "divergence_window_taipei": "00:00–07:59",
        "samples": rows,
        "window_exists": any(r["differs"] for r in rows),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("inventory", help="全庫日期界線用點盤點")
    p.add_argument("--out", default=f"{OUT_DIR}/inventory.json")
    p.set_defaults(func=cmd_inventory)

    p = sub.add_parser("window", help="DB 端雙時區日界差示範")
    p.add_argument("--out", default=f"{OUT_DIR}/tz_window.json")
    p.set_defaults(func=cmd_window)

    args = ap.parse_args()
    _dump(args.func(args), args.out)


if __name__ == "__main__":
    main()
