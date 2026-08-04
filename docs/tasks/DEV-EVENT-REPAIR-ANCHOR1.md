# DEV-EVENT-REPAIR-ANCHOR1 schema-repair 留痕的 before 未錨定歷史，可被捏造〔T3；🟡流程〕

- 需求：ruan6047（2026-08-03 依 `DEV-EVENT-SCHEMA-GUARD1` 的 `replan` 承諾拆卡）　規劃：GPT-5.6@Codex（2026-08-04 Plan Gate 核可）　分支：`ai/<執行者>/DEV-EVENT-REPAIR-ANCHOR1`
- 執行：待指派（建議 L3；需設計歷史錨定機制並處理鏈完整性，非單點修補）　查核：待指派（建議 L2；≠ 執行）
- Initiative：—　spec 基線：`DEV-EVENT-SCHEMA-GUARD1`（epoch 1，已交付 `fdd9e0f`）
- review_independence: [cross_family]
- DB：`db_scope: none`
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍：`scripts/workflow_ledger.py`、`docs/CONTROL_PLANE_CONTRACT.md`、`tests/test_workflow_ledger.py`；採 Git 雙錨定，不新增外部 manifest 或簽章基礎設施。
- Discovery：**已完成並經需求方核可**；決策與實作切片見〈Discovery 結論〉與〈核可的實作計畫〉。
- Design：Design Gate N/A——無使用者可見介面。

## 問題陳述

`DEV-EVENT-SCHEMA-GUARD1` 建立了 `schema-repair` 事件作為就地修復的留痕機制，並驗證其 payload 完整性。但**該留痕的可信度建立在一個未被驗證的欄位上**。

`_validate_schema_repair_event()` 要求 `after` 等於 log 中該事件的現況——這證明「修復結果存在」。但 **`before` 沒有任何錨點**：它由修復者自行填寫，沒有任何機制證明「所聲稱的原本非法狀態」曾經存在。

**跨家族查核實測（`DEV-EVENT-SCHEMA-GUARD1` F005）**：以真實的 `UX-LIVE-GAME1-REVIEW-008` 為 target，`after` 設為與真實 log 完全相同、僅偽造 `before.findings[0].status = "rejected"`，驗證器**接受**該 payload（`fabricated_before=NOT_BLOCKED`）。Coordinator 獨立重現確認。

**後果**：任何人都能為一筆**從未壞過**的合法事件補上一筆看似正當的 `schema-repair` 留痕。留痕機制因此無法作為稽核證據——它證明得了「現在長這樣」，證明不了「當初為什麼要改」。

## 為何獨立成卡而非在原卡續修

`DEV-EVENT-SCHEMA-GUARD1` 於三輪 REQUEST_CHANGES 後觸發 WF-21 升級檢查點，需求方核可 epoch 0→1、理由 `replan`，並在事件中明文承諾：**「epoch 1 內若再出現結構性 finding，應拆卡而非續修」**。

F005 屬結構性——它不是漏一個檢查，而是**留痕設計缺少歷史真實性的錨**，要解決需引入新的錨定機制並處理整條鏈的完整性（見 Discovery）。跨家族查核者亦獨立建議拆卡。兩邊一致，故依承諾執行。

**原卡的核心價值不受影響且已獨立成立**：真實檔 schema 守衛、baseline marker 存在性、白名單「非法→合法」語意、CI 對 event log diff 的強制執行——原始問題「壞資料寫入後永久卡住 ledger 而無人察覺」已解決。本卡處理的是後來才長出來的留痕可信度。

## Discovery 結論（2026-08-04 Plan Gate 核可）

### 1. `before` 的錨定：Git 雙錨定

採 **修復提交 [repair commit] + 直接父提交 [direct parent]**，不用單純的任意 Git parent。每筆新的 `schema-repair` 必填 `anchor_parent_sha` 與 `repair_commit_sha`；驗證器必須從兩個提交各讀一次 `docs/control-plane/events.jsonl`，並要求目標事件在前者**精確等於** `before`、後者**精確等於** `after`，且 `repair_commit_sha` 只有一個 parent、恰為 `anchor_parent_sha`。

這修正了「只寫一個 parent SHA 仍可挑選任意舊歷史來配合捏造 before」的漏洞。修復操作分兩個提交：第一筆只把壞目標由 `before` 改為 `after`；第二筆追加帶兩個 SHA 的稽核事件並重建 Ledger。第二筆可在本機已有第一筆提交時執行 `--write`／`--check`，不會形成「尚未提交所以無法驗證」的循環。

候選取捨：

| 方案 | 結論 | 失效邊界 |
|---|---|---|
| Git 雙錨定 | 採用；現有 protected `main` 與 Git 歷史足以服務「誤操作／AI 自我粉飾」威脅模型。 | 淺複製、離線、物件遺失或錨定提交不可達時 fail closed；已推送 main 遭惡意重寫不在本卡防護範圍。 |
| 不可變 manifest | 不採用；新增第二份可寫事實來源與保存／同步成本，卻沒有外部簽章時仍須信任寫入者。 | 若 manifest 與 Git 分叉，無可信仲裁者。 |
| 內容雜湊 | 不採用；必須在原始事件寫入時預先存在，不能誠實覆蓋存量，也無法單獨證明 hash 對應哪個歷史版本。 | 對既有事件不可用；hash 欄位可被與事件一起就地改寫。 |

### 2. 鏈完整性

- 同一 `repaired_event_id` 最多一筆 repair；首次修復後目標已合法，第二筆不是合法化而是改寫。
- 禁止 repair 指向 `schema-repair`；稽核事件本身是錨點，不能以遞迴「留痕的留痕」淡化它。
- `repaired_event_id` 必須在 repair 事件之前出現；再配合單次 target 規則，前向參照與循環皆 fail closed。
- 現行或歷史 blob 中 repair event 的內容與所宣告錨定提交不一致時 fail closed；其就地修改仍受既有 `test_modified_events_obey_the_schema_repair_allowlist` 的禁止欄位防線保護。

### 3. 存量事件

`UX-BRAND-HOME1-REVIEW-007`（`322f69a`）是唯一 `legacy-unverifiable`，不補造 `before`、不宣稱已錨定。掃描結果必分別列出 `anchored`、`legacy-unverifiable`、`failed`，故「所有 repair 已錨定」只能由掃描輸出產生，不能人工宣告。

### 4. 驗證分層

Git I/O 放在 `_load_events()` 所走的真實檔驗證路徑與 CLI `--check`／`--write`，不可塞進保持純函式的 `_validate_review_contract()` 或 `render_ledger()`。合成 fixture 可注入 resolver 測試錨定規則；所有正式 CLI／CI 路徑必帶真實 Git resolver。直接呼叫內部純函式的單元測試不涵蓋 Git object 可達性，這是刻意界線，不得拿來宣稱完整稽核。

## 核可的實作計畫

### Task 1：建立雙錨定驗證骨架（M）

**說明：** 在 `workflow_ledger.py` 建立可注入的 Git blob resolver，擴充 `schema-repair` payload，驗證 target 的 before／after、直接 parent 關係與 Git object 可達性。

**驗收條件：**

- [ ] 重現 F005：`after` 正確但 `before` 捏造時，驗證必失敗。
- [ ] 錨定 SHA 缺失、不可讀、非直接 parent、blob 內 target 不符皆 fail closed。
- [ ] 純函式層不引入 subprocess；真實檔 CLI 路徑確實呼叫 resolver。

**驗證：** `uv run pytest tests/test_workflow_ledger.py -q`，並以暫存 Git repo 走完整 before → repair → audit 提交流程。

**依賴：** 無。**檔案：** `scripts/workflow_ledger.py`、`tests/test_workflow_ledger.py`。

### Task 2：封鎖鏈與存量繞過（M）

**說明：** 以 Task 1 的 resolver 實作單次 target、禁止 repair→repair、循環／前向參照拒絕，以及唯一 legacy-unverifiable 清單與掃描分類。

**驗收條件：**

- [ ] 多次 repair、repair 指向 repair、循環、repair event 就地修改各有獨立負向測試。
- [ ] `UX-BRAND-HOME1-REVIEW-007` 僅列 `legacy-unverifiable`，測試證明未產生追溯 payload。
- [ ] 掃描輸出可重現且未把不可驗證項目算進 anchored。

**驗證：** `uv run pytest tests/test_workflow_ledger.py -q`，`uv run python scripts/workflow_ledger.py --check`。

**依賴：** Task 1。**檔案：** `scripts/workflow_ledger.py`、`tests/test_workflow_ledger.py`。

### Task 3：固化操作契約與端到端回歸（S）

**說明：** 更新 control-plane 契約為雙提交操作程序、失效邊界與掃描指令；以真實 event log replay 驗證既有 baseline 不受破壞。

**驗收條件：**

- [ ] 契約明列 fail-closed、不可追溯補造、雙提交順序與不涵蓋範圍。
- [ ] 完整 replay 成功且 baseline 前事件數與現況一致。
- [ ] `ruff`、完整 `pytest`、Ledger `--check` 全綠。

**驗證：** `uv run ruff check`、`uv run pytest`、`uv run python scripts/workflow_ledger.py --check`。

**依賴：** Task 1、Task 2。**檔案：** `docs/CONTROL_PLANE_CONTRACT.md`、`scripts/workflow_ledger.py`、`tests/test_workflow_ledger.py`。

### Checkpoint：送獨立查核前

- [ ] 三個 Task 的驗收條件均已完成。
- [ ] 查核者另造一個未沿用執行者 fixture 的 fabricated-before 攻擊。
- [ ] 查核者對四種鏈型態逐一嘗試繞過，並確認掃描輸出沒有把 legacy 計入 anchored。

## 非目標

- 不改 `DEV-EVENT-SCHEMA-GUARD1` 已交付的守衛（真實檔 schema 驗證、baseline marker、白名單語意、CI diff 強制）——僅在其上補錨定。
- 不引入外部簽章基礎設施（GPG／sigstore 等）。單人專案，威脅模型是**誤操作與 AI 自我粉飾**，不是惡意攻擊者。
- 不追溯為存量事件補造留痕（見 Discovery 第 3 問）。

## 紅線

1. **不得以「難以驗證」為由放寬到形同無驗證。** 若某條路徑（如淺 clone）確實無法錨定，須 **fail closed 或明確 skip 並標記為不可驗證**，不得靜默通過。
2. **不得追溯補造 `before`。** 存量事件若無從錨定，就標為不可驗證——**捏造歷史來讓守衛通過，正是本卡要防的事**。
3. **完整性宣稱須由指令產生。** 「所有 repair 皆已錨定」這類宣稱須附可重現的掃描輸出。

## 驗收條件

- [ ] Discovery 四問有書面答案，第 1、4 問明列**涵蓋範圍與不涵蓋範圍**。
- [ ] `before` 錨定機制落地，並以**負向測試**證明：重現 F005 的攻擊（`after` 正確、`before` 捏造）必須被擋下；每筆新 repair 的 `before`／`after` 分別與直接相鄰的 Git 歷史 blob 相等。
- [ ] 鏈完整性四種型態各有測試：多次修復、repair 指向 repair、循環引用、repair 事件本身被修改。
- [ ] 存量事件的處置有明確規則與測試，且**未追溯補造任何留痕**。
- [ ] 完整 `events.jsonl` replay 通過，baseline 前事件數與現況一致（附指令輸出）。
- [ ] `uv run ruff check` ＋ `uv run pytest` 全綠。

## 驗證

- [ ] 查核者以**自己構造的捏造 before**獨立驗證會被擋（不沿用執行者的測試案例）。
- [ ] 查核者針對鏈完整性四型各自嘗試繞過。
- [ ] 查核者確認「不涵蓋」宣告誠實且完整。
- [ ] 查核通過前不得 merge main。

## 邊界

- 只動 control-plane 工具與契約文件，不動任何卡片內容。
- 不引入外部簽章／manifest、資料庫、production 操作或前端變更。
- 預估 M（已完成 Discovery；三個可獨立驗證的 S～M 切片）。

## Log

- 2026-08-03 register by Claude Opus 5@Claude Code（依 ruan6047 裁定拆卡）；iteration 0。來源：`DEV-EVENT-SCHEMA-GUARD1` 第四輪跨家族查核的 `F005`——查核者以真實事件為 target、`after` 完全正確而僅偽造 `before`，驗證器接受該 payload。**該漏洞由原卡執行者在派工提示詞中主動列為「最可能中」的攻擊向量並刻意未修，以確認是否真的可行；查核者證實可行。** 拆卡依據為原卡 epoch 0→1 切換時記下的 `replan` 承諾（「epoch 1 內若再出現結構性 finding，應拆卡而非續修」），查核者亦獨立建議拆卡，兩邊一致。
- 2026-08-04 replan by GPT-5.6@Codex；需求方 ruan6047 核可雙錨定方向並指定 Codex 為規劃者。決策由「任意 Git parent」收緊為 repair commit + direct parent：用兩份相鄰歷史 blob 證明 target 曾是 `before` 且被改為 `after`。不採 manifest／hash，理由與失效邊界載於本卡 Discovery 結論；存量 `UX-BRAND-HOME1-REVIEW-007` 固定標為 `legacy-unverifiable`，不追溯補造留痕。Plan Gate 已通過，待指派執行者。
