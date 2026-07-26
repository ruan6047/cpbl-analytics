"""審核提示詞產生器：從 control-plane 最新 handoff event + 卡片檔自動生成查核提示詞。

用法（需求方在 repo 根目錄執行）：
    uv run python scripts/review_prompt.py <CARD_ID>            # 印到 stdout
    uv run python scripts/review_prompt.py <CARD_ID> | pbcopy   # 直接進剪貼簿貼給查核者

資料來源（零 AI 成本、永遠反映最新交接狀態）：
- docs/control-plane/events.jsonl：該卡最新 handoff event（分支、worktree、source_sha、
  tier、db_scope、執行者交付摘要）
- docs/tasks/<CARD_ID>.md：標題含「驗收」「驗證」「Gate」的章節原文

慣例（CONTROL_PLANE_CONTRACT.md「Review→merge 慣例」）：查核 APPROVE（零阻塞
findings）後 Coordinator 直接 merge，結果回傳執行者，部署另由需求方確認。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def latest_handoff(card_id: str) -> dict:
    ev = None
    with open(ROOT / "docs/control-plane/events.jsonl", encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            if e.get("card_id") == card_id and e.get("type") == "handoff":
                ev = e  # append-only → 最後一筆即最新
    if ev is None:
        sys.exit(f"錯誤：{card_id} 沒有 handoff event（尚未交付查核）。")
    return ev


def card_sections(card_id: str, wanted: tuple[str, ...]) -> str:
    path = ROOT / f"docs/tasks/{card_id}.md"
    if not path.exists():
        sys.exit(f"錯誤：找不到卡片檔 {path}")
    out: list[str] = []
    keep = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            heading = line[3:].strip()
            keep = any(token in heading for token in wanted)
        if keep:
            out.append(line)
    sections = "\n".join(out).strip()
    if not sections:
        print(
            f"警告：{card_id} 找不到可錨定的驗收章節"
            f"（標題須含：{', '.join(wanted)}）；review prompt 將退化為全文驗收。",
            file=sys.stderr,
        )
    return sections


def build_prompt(card_id: str) -> str:
    ev = latest_handoff(card_id)
    tier = ev.get("tier", "T3")
    redline = tier == "T4"
    db_scope = ev.get("db_scope", "none")
    worktree = ev.get("worktree", "")
    wt_abs = ROOT / worktree if worktree else ROOT
    sections = card_sections(card_id, ("驗收", "驗證", "Gate"))
    indep = ("跨模型家族（非執行者所屬家族）或人工" if redline
             else "新 context／session 即可（不得為執行者本人）")
    db_note = {
        "none": "本卡不涉 DB。",
        "read": "本卡 db_scope=read——你的所有查詢**必須唯讀**，嚴禁任何寫入。",
    }.get(db_scope, f"本卡 db_scope={db_scope}——寫入範圍以卡片宣告為準，逾越即 finding。")
    return f"""## {card_id} 獨立查核提示詞〔{tier}{'；🔴紅線' if redline else ''}〕

你是 cpbl-analytics 專案 **{card_id}** 的獨立查核者（{indep}）。
你的職責是對照目標與證據驗收：**發現缺陷只留 finding 退回，不得修改被審分支上的任何檔案**。

### 查核對象

- 功能：{ev.get('feature', '（見卡片）')}
- 分支：`{ev.get('branch', '?')}` @ **{ev.get('source_sha', '?')[:7]}**（完整 SHA {ev.get('source_sha', '?')}）
- 進駐 worktree：`{wt_abs}`（指令在此目錄執行）
- 卡片：`docs/tasks/{card_id}.md`

### 環境紅線

{db_note}

### 執行者交付摘要（handoff evidence 原文）

{ev.get('evidence', '（無）')}

### 卡面驗收條件（逐項核對）

{sections if sections else '（卡片無明列章節，依卡片全文與 spec 驗收）'}

### 基本重現指令

```
uv run ruff check
uv run pytest -q
```

（卡片與交付摘要中列出的專屬驗證指令一併重跑。）

### 產出格式

回覆 **APPROVE 或 REJECT**，附 findings 清單（每條含 severity／證據／建議處置）
與你實際重跑的指令與輸出摘要。依本專案慣例：**APPROVE（零阻塞 findings）後
Coordinator 將直接 merge** 並將結果回傳執行者，部署與後續另由需求方確認；
REJECT 則退回原執行者於原分支修正（iteration+1）。你的結論將由需求方轉錄為
review event（source_sha={ev.get('source_sha', '?')[:7]}）留痕。
"""


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("用法：uv run python scripts/review_prompt.py <CARD_ID>")
    print(build_prompt(sys.argv[1]))


if __name__ == "__main__":
    main()
