# Handoff Contract — cpbl-analytics

> 通用不變量見 canonical [`../.ai-workflow/AI_WORKFLOW.md`](../.ai-workflow/AI_WORKFLOW.md) §4.1；
> 本檔由 [`templates/handoff-contract.md`](../.ai-workflow/templates/handoff-contract.md) 建立（WF-20）。
> event store、Ledger 投影與 lifecycle 寫入規則見 [`CONTROL_PLANE_CONTRACT.md`](CONTROL_PLANE_CONTRACT.md)——
> **本檔不建立第二個狀態來源**，只規範 handoff 這一類事件的欄位與接收驗證。
>
> ⚠️ **本檔為 B2 權威文件，尚未經獨立校讀**（canonical §0：B2 需獨立事實查核／校讀）。
> 建立者為 `DEV-TRAILER-GUARD-SCOPE1` 的查核者，非本專案 Coordinator；請於下一次 handoff 前完成校讀。

## 0. Baseline（不追溯）

**生效起點：`DEV-TRAILER-GUARD-SCOPE1-HANDOFF-ACCEPTED-004`（2026-07-29T14:29:47+08:00）**，
即本專案第一個 `handoff-accepted` 事件。依 [`MIGRATION.md`](../.ai-workflow/MIGRATION.md) 的 baseline 機制：

- 該事件**之前**的 150 筆 `handoff` 無 receiver acceptance、部分使用縮寫 `source_sha`，屬升級前遺留，**不回填、不重寫**。
- 該事件**之後**的所有 handoff 適用本契約全文。

## 1. 不變量

- handoff 是 remote lifecycle event。聊天訊息、PR 留言、worktree 內的筆記只可作通知，**不可作狀態**。
- sender 必須**先 push** `source_sha` 指向的 commit；`source_sha` 固定為**完整 40 字元 SHA**，
  不接受 branch name、短 SHA 或未提交工作區。
  （2026-07-29 `DEV-TRAILER-GUARD-SCOPE1-HANDOFF-003` 使用 7 字元縮寫 `23d4a82`，
  因處於 baseline 邊界且可唯一解析而受理；自 baseline 起不再受理。）
- receiver 驗證通過後才寫 `handoff-accepted`；**此事件才轉移 owner**。
  驗證失敗寫 `⏸阻塞` 或 findings，**不得自行修正 sender 的內容**。
- lease 過期、baseline 不一致或證據不足時不得接受。
- 本專案**不使用** tmux／本機 queue／daemon 作為 handoff 通道（見 §4）。

## 2. Handoff event payload

本專案沿用 `CONTROL_PLANE_CONTRACT.md` §2 的既有 envelope，**不另起一套欄位**。
canonical 範本欄位與本專案欄位的對應如下：

- `from` → `actor`（寫入者，通常即交付方）
- `to` → `owner`（交付後的階段所有者；receiver 於 `handoff-accepted` 覆寫為自己）
- `next_stage` → 由 `delivery_status` 表達（`🔍待查核` ＝ review、`🔨執行中` ＝ implementation、`📦已合併` ＝ release）
- `summary` → `evidence` 首段
- `baseline` → `initiative` ＋ 卡片 spec 基線；無 Initiative 時填 `—` 並於 `evidence` 說明卡面即基線

自 baseline 起 handoff 事件**額外必填**（既有 envelope 未涵蓋、ledger 對未知欄位為寬容，已實測）：

```yaml
claim_event_id: <對應的有效 claim 事件 event_id>
```

缺 `claim_event_id`、`source_sha` 非 40 字元、或欄位無法解析者，**receiver 一律拒收**，不得自行腦補補齊。

## 3. Receiver acceptance checklist

receiver 在寫 `handoff-accepted` 前必須逐項完成，並把結果寫進該事件的 `evidence`：

- [ ] **SHA 完整且已推送**：`git rev-parse <sha>` 解析成功，且 `git branch -r --contains <sha>` 顯示該 commit 已存在於遠端 ref。
- [ ] **本地與遠端分支 tip 一致**：`git rev-parse <branch>` ＝ `git rev-parse origin/<branch>` ＝ `source_sha`。
- [ ] **查核環境隔離**：以 `git worktree add --detach <path> <完整SHA>` 建立**獨立 detached worktree**，
      `git status` 乾淨、`HEAD` 等於 `source_sha`。不得在執行者的 worktree 上查核。
- [ ] **分支範圍合規**：`git diff --stat main...HEAD` **不含** `docs/control-plane/**` 與 `docs/TASKS.md`
      （`CONTROL_PLANE_CONTRACT.md`：執行分支不得攜帶 control-plane event）。
- [ ] **lease 有效**：`claim_event_id` 對應的 claim 未過期、未被回收。
- [ ] **baseline 一致**：與卡片／Initiative 的 spec 基線相符，或 handoff 已明確標記 blocked 並附基線變更事件。
- [ ] **evidence 齊全可讀**：sender 宣稱的測試／CI／實測結果存在且可重跑。
- [ ] **獨立性**：receiver ≠ 執行者；紅線卡另須**換模型家族**（canonical §5——同家族不同工具不算獨立）。

全數通過才追加 `handoff-accepted`，記錄完整 `source_sha`、actor、寫入當下時鐘的 `occurred_at` 與上述驗證結果；**之後才開始工作**。

## 4. Optional local tmux adapter

| 能力 | 本專案 | 限制 |
|---|---|---|
| 對每個 worktree 開 session | **不使用** | — |
| 收到 remote handoff 後喚醒 idle agent | **不使用** | — |
| 本機 inbox/outbox | **不使用** | — |
| 直接改 Ledger／lease／state | ❌ 禁止 | 只能由 lifecycle event ＋ `workflow_ledger.py --write` 產生 |

本專案為單機、單一人類 writer，agent session 直接讀 `docs/control-plane/events.jsonl` 取得未完成 handoff，
**不需要也不得引入本機 queue**。若未來導入，runtime 路徑必須 `.gitignore`，且只可引用 remote event。

## 5. 專案實作

- **Remote handoff writer**：階段所有者或 Coordinator，直接 commit `docs/control-plane/events.jsonl` 至受保護 `main`
  （非 GitHub Action；見 `CONTROL_PLANE_CONTRACT.md`）。
- **SHA 驗證命令**：
  ```bash
  git rev-parse <sha> && git branch -r --contains <sha>
  ```
- **查核 worktree 建立**：
  ```bash
  git worktree add --detach .claude/worktrees/<card-id小寫>-review <完整40字元SHA>
  ```
- **`handoff-accepted` writer 與授權**：receiver 本人；無需額外授權，但必須 ≠ 執行者。
- **查核提示詞**：`uv run python scripts/review_prompt.py <CARD_ID>`（見 `CONTROL_PLANE_CONTRACT.md`〈交付→查核→合併慣例〉）。
- **tmux launcher／wake-up**：不使用。
- **Runtime 路徑與 `.gitignore`**：不適用（無本機 queue）。
- **失敗、重試與人工介入**：拒收即寫 `⏸阻塞` 或 review REJECT，退回原執行者、原分支、`iteration + 1`；
  連續三次退回轉 `🚨已升級`，由需求方裁定（canonical §3、§5）。

## 6. 已知落差

- `claim_event_id` 為本契約新增的必填欄位，**baseline 之前的事件未帶**；`workflow_ledger.py` 目前不驗證此欄位，
  因此暫由 receiver 於 acceptance checklist 人工核對。**建議後續補進 ledger 的 `--check`**，
  否則這條規則本身就是「靠人記得」——正是 `DEV-TRAILER-GUARD-SCOPE1` 與 `DEV-VERIFY-TM-ASSERTS1` 兩張卡在修的病。
