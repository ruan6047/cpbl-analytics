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
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 卡面欄位錨點（tasks-card 範本）：「- Initiative：<父卡 ID／—>　spec 基線：<版本／—>」
_INITIATIVE_RE = re.compile(r"Initiative：\s*([A-Z][A-Z0-9\-]+)")
_BASELINE_RE = re.compile(r"spec 基線：\s*([^\s　]+)")


def _card_path(card_id: str) -> Path | None:
    """卡片檔路徑：活卡在 tasks/，父卡可能已封存在 archive/tasks/。"""
    for rel in (f"docs/tasks/{card_id}.md", f"docs/archive/tasks/{card_id}.md"):
        p = ROOT / rel
        if p.exists():
            return p
    return None


def baseline_check(card_id: str) -> str:
    """有 Initiative 父卡時產出 spec 基線一致性查核段（baseline-cascade §5）。

    無父卡（Initiative 欄為「—」或缺）回空字串——輸出不多任何段落。
    版本欄缺席時不靜默省略：明確標示「人工核對」。
    """
    path = _card_path(card_id)
    if path is None:
        return ""
    text = path.read_text(encoding="utf-8")
    m_init = _INITIATIVE_RE.search(text)
    if not m_init:
        return ""
    parent_id = m_init.group(1)
    m_child = _BASELINE_RE.search(text)
    child_ver = m_child.group(1) if m_child else None

    parent_path = _card_path(parent_id)
    parent_ver = None
    if parent_path is not None:
        m_parent = _BASELINE_RE.search(parent_path.read_text(encoding="utf-8"))
        parent_ver = m_parent.group(1) if m_parent else None

    lines = [
        "### spec 基線一致性（canonical baseline-cascade §5）",
        "",
        f"- Initiative 父卡：{parent_id}"
        + (f"（`{parent_path.relative_to(ROOT)}`）" if parent_path else "（**卡片檔不存在**）"),
    ]
    if parent_ver and child_ver:
        verdict = "一致" if parent_ver == child_ver else "**不一致——舊基線交付，直接退回**"
        lines.append(f"- 父卡當前 spec 基線：`{parent_ver}`；本卡卡面 spec 基線：`{child_ver}` → {verdict}")
    else:
        missing = "父卡" if not parent_ver else "本卡"
        lines.append(
            f"- {missing}的 spec 基線欄缺席，無法自動核對——**人工核對**：對照父卡「基線變更紀錄」"
            "與本卡範圍是否仍在當前基線內。"
        )
    lines.append(
        "- 本段為產生提示詞當下的快照；查核時以父卡**當前**檔案再核對一次，"
        "不一致即退回（不進 finding 協商）。"
    )
    return "\n".join(lines)


def latest_handoff(card_id: str) -> dict:
    ev = None
    events: list[dict] = []
    with open(ROOT / "docs/control-plane/events.jsonl", encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            if e.get("card_id") != card_id:
                continue
            events.append(e)
            if e.get("type") == "handoff":
                ev = e  # append-only → 最後一筆即最新
    if ev is None:
        sys.exit(f"錯誤：{card_id} 沒有 handoff event（尚未交付查核）。")
    _assert_no_review_supersedes_handoff(card_id, events)
    _assert_handoff_matches_branch_head(ev)
    return ev


def _assert_no_review_supersedes_handoff(card_id: str, events: list[dict]) -> None:
    """最新 handoff 之後若已有 review，代表這一輪查核已結束，拒絕再發提示詞。

    ML-PITCHER-SCORELESS1 的教訓：卡片已 `↩退回`、執行者尚未推修正，但本腳本
    只檢查「handoff SHA 是否等於分支 HEAD」——兩者當然還相等，於是照發提示詞。
    重跑指令就再派一位查核者去查同一份未修改的程式，得到逐字相同的 REJECT；
    實際發生三次，燒掉兩輪查核頻寬。

    這與該卡自己的缺陷同型：檢查了一個容易檢查的相關量（SHA 是否對得上），
    而不是真正該成立的性質（**現在到底還有沒有待查核的交付**）。
    退回後要再查核，必須先有新的 handoff event；那正是 iteration+1 的定義。
    """
    after = []
    seen_handoff = False
    for e in events:
        if e.get("type") == "handoff":
            after = []            # 新一輪開始，之前的 review 不再相關
            seen_handoff = True
        elif seen_handoff and e.get("type") == "review":
            after.append(e)
    if not after:
        return
    last = after[-1]
    sys.exit(
        f"錯誤：{card_id} 最新 handoff 之後已有 {len(after)} 筆 review，這一輪查核已結束，"
        "拒絕產生提示詞。\n"
        f"  最後一筆：{last.get('review_result', '?')}"
        f"（state_version {last.get('state_version')}，{last.get('occurred_at')}）\n"
        f"  目前交付狀態：{last.get('delivery_status')}\n"
        "  若為 REJECT：等執行者推修正並補新的 handoff event（iteration+1）再重跑本指令。\n"
        "  若為 APPROVE：接續 merge／結案流程，不需要再查核一次。")


def _assert_handoff_matches_branch_head(ev: dict) -> None:
    """handoff 的 source_sha 必須等於該分支當前 HEAD，否則拒絕產生提示詞。

    ML-OUTCOME-SIMPLE-LEAK2 iteration 4 的教訓：Coordinator 派了新 iteration 產生新 commit
    卻沒補 handoff，本腳本照讀最新 handoff 帶出過期 SHA，查核者被迫程序性 REJECT——
    整輪跨家族查核燒在一件機器兩秒可查的事上。此後「送審前 SHA 一致」由這裡強制，
    不靠 Coordinator 記得。分支不存在（已 merge 清理）或無法解析時同樣拒絕，
    請改以 merge 後流程處理而非對舊 handoff 產生提示詞。
    """
    branch, sha = ev.get("branch", ""), ev.get("source_sha", "")
    if not branch or not sha:
        sys.exit("錯誤：handoff 缺 branch 或 source_sha 欄位，無法核對，拒絕產生提示詞。")
    r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--verify", "--quiet",
                        f"refs/heads/{branch}"], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"錯誤：分支 {branch} 不存在（已 merge 清理？）。"
                 "已結案的卡不該再產生查核提示詞；未結案請先恢復分支。")
    head = r.stdout.strip()
    if head != sha:
        sys.exit(
            f"錯誤：handoff 的 source_sha 與分支 HEAD 不一致，拒絕產生提示詞。\n"
            f"  handoff source_sha：{sha}\n"
            f"  {branch} HEAD：{head}\n"
            "  成因通常是 push 了新 commit 卻沒補 handoff event——先補 handoff 再重跑本指令。")


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
    checklist = sections if sections else "（卡片無明列章節，依卡片全文與 spec 驗收）"
    baseline = baseline_check(card_id)
    if baseline:
        checklist += "\n\n" + baseline
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

{checklist}

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
