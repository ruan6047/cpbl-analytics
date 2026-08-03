# DEV-EVENT-REPAIR-ANCHOR1 schema-repair 留痕的 before 未錨定歷史，可被捏造〔T3；🟡流程〕

- 需求：ruan6047（2026-08-03 依 `DEV-EVENT-SCHEMA-GUARD1` 的 `replan` 承諾拆卡）　規劃：本卡 spec　分支：`ai/<執行者>/DEV-EVENT-REPAIR-ANCHOR1`
- 執行：待指派（建議 L3；需設計歷史錨定機制並處理鏈完整性，非單點修補）　查核：待指派（建議 L2；≠ 執行）
- Initiative：—　spec 基線：`DEV-EVENT-SCHEMA-GUARD1`（epoch 1，已交付 `fdd9e0f`）
- review_independence: [cross_family]
- DB：`db_scope: none`
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍：`scripts/workflow_ledger.py`、`docs/CONTROL_PLANE_CONTRACT.md`、`tests/test_workflow_ledger.py`，視 Discovery 結論可能新增 manifest 或 git 錨定機制
- Discovery：**本卡第一項交付是「用什麼錨定 `before`」的判斷**，不是直接改碼。三條候選路徑見〈Discovery 必答〉。
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

## Discovery 必答（先答再改碼）

1. **用什麼錨定 `before`？** 候選：(a) **git parent** —— `before` 必須等於該事件在指定 parent commit 的內容，驗證時以 `git show <sha>:events.jsonl` 取；(b) **不可變 repair manifest** —— 修復時另存一份簽章過的原始 blob；(c) **內容雜湊** —— 事件寫入時即記錄 hash，修復時比對。**各自在什麼情境下失效要明寫**（例：git 錨定在淺 clone／離線時取不到；hash 需要既有事件都已帶 hash，對存量事件不適用）。
2. **鏈完整性怎麼處理？** 至少四種型態需有明確規則：多次修復同一事件（後一筆的 `before` 應取自前一筆的 `after`？）、`repaired_event_id` 指向另一筆 `schema-repair`、循環引用、以及 **`schema-repair` 事件本身被就地修改**（誰驗證留痕的留痕？）。
3. **對存量事件如何處理？** 現行 log 已有一筆歷史修復（`UX-BRAND-HOME1-REVIEW-007`，`322f69a`），且無 `schema-repair` 事件。新機制上線後，存量狀態要視為「已錨定」「豁免」還是「標為不可驗證」？**不得為了讓數字好看而追溯補造留痕。**
4. **驗證要在哪一層？** 若採 git 錨定，驗證需要 subprocess 呼叫 git——放進 `_validate_review_contract`（純函式、無 IO）會破壞其語意，如同原卡把 baseline 守衛放進 `_load_events` 的取捨。**明講放哪、以及該層涵蓋不到的呼叫路徑。**

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
- [ ] `before` 錨定機制落地，並以**負向測試**證明：重現 F005 的攻擊（`after` 正確、`before` 捏造）必須被擋下。
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
- 預估 M～L（Discovery 與錨定機制設計是主體）。

## Log

- 2026-08-03 register by Claude Opus 5@Claude Code（依 ruan6047 裁定拆卡）；iteration 0。來源：`DEV-EVENT-SCHEMA-GUARD1` 第四輪跨家族查核的 `F005`——查核者以真實事件為 target、`after` 完全正確而僅偽造 `before`，驗證器接受該 payload。**該漏洞由原卡執行者在派工提示詞中主動列為「最可能中」的攻擊向量並刻意未修，以確認是否真的可行；查核者證實可行。** 拆卡依據為原卡 epoch 0→1 切換時記下的 `replan` 承諾（「epoch 1 內若再出現結構性 finding，應拆卡而非續修」），查核者亦獨立建議拆卡，兩邊一致。
