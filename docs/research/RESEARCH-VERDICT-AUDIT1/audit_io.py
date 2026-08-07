"""本卡三支腳本共用的輸出／驗證入口。

存在理由是 R1 查核 finding `AUDIT1-R1-001`：一張以「窮舉可重現」為第一驗收條件的稽核卡，
在乾淨 worktree 順序重跑時必須逐位重現，否則那條驗收條件是空的。兩件事因此定成紀律：

1. **artifact 內不放 wall-clock 時戳，也不放 `repo_head`。**
   時戳會讓每一次重跑都把 worktree 弄髒，於是「重跑後 worktree 髒了」不再是訊號——
   真正的差異被雜訊蓋掉。R1 那個 bug 就是這樣被掩蓋的（`M verdict_scan.json` 看起來
   跟平常一樣，其實母體已經從 64 變成 70）。provenance 改由交付 commit 承擔，
   寫在 `VERDICTS.md` 與 commit message，不寫進可重生的檔案裡。

2. **每支腳本都要有 `--check`。** 查核者不必寫任何檔案就能驗證交付內容確實出自腳本；
   不符即 exit 1 並印出第一處差異。
"""

from __future__ import annotations

import difflib
import sys
from pathlib import Path


def emit(path: Path, text: str, *, check: bool) -> bool:
    """寫出（或驗證）一份產物。回傳 True 代表相符／已寫出。"""
    if not check:
        path.write_text(text, encoding="utf-8")
        return True
    if not path.exists():
        print(f"CHECK FAIL: {path.name} 不存在", file=sys.stderr)
        return False
    current = path.read_text(encoding="utf-8")
    if current == text:
        return True
    print(f"CHECK FAIL: {path.name} 與腳本重生成的內容不符", file=sys.stderr)
    diff = difflib.unified_diff(
        current.splitlines(), text.splitlines(), "committed", "regenerated", lineterm="", n=1
    )
    for i, line in enumerate(diff):
        if i >= 20:
            print("  …（差異已截斷）", file=sys.stderr)
            break
        print(f"  {line}", file=sys.stderr)
    return False


def finish(ok: bool, *, check: bool) -> int:
    if check:
        print("CHECK OK：交付內容與腳本重生成結果逐位相同" if ok else "CHECK FAILED",
              file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1
