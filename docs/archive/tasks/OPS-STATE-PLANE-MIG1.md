# OPS-STATE-PLANE-MIG1 任務狀態面遷移至 GitHub Issues/Projects〔T3；🟡流程〕

- 需求：ruan6047（2026-08-04 工作流檢討決議 7＋Wave 1 派工批准）　規劃：Claude Fable 5@Claude Code（PM 祕書）
- 執行：待指派（建議 L2；GraphQL／gh 已知模式，對帳紀律要求高，欄位表達力疑義升 L3）　查核：待指派（新 context；≠ 執行）
- Initiative：WF-22（ai-workflow repo）　spec 基線：決議 v1（`docs/research/WORKFLOW-REVIEW-2026-08-04.md` @ `913223e`）
- 服務的原始目標：消除「worktree 過期狀態快照造成錯誤評估、撞卡不可靠、看板缺席」（根因三）
- DB：`db_scope: none`（不碰 cpbl 資料庫）
- 分支：`ai/<執行者>/OPS-STATE-PLANE-MIG1`　資源：`file:scripts/state_plane_migrate.py`、`file:docs/CONTROL_PLANE_CONTRACT.md`
- Discovery：已完成（2026-08-04 grilling ＝本卡 Discovery）。Design Gate N/A——純協作基礎設施，無產品使用者介面。

## 核心痛點（三問，需求方已批）

- **痛點**：worktree 讀到分支點的過期 TASKS.md 致錯誤評估；撞卡查詢 grep 級不可靠；看板缺席。
- **成功怎麼觀察**：任何 session 任何時刻讀到的卡狀態即時（API）；38 張活卡上 user-level Project 看板；快照每日落 git；凍結卡處置批示完成。
- **最大未驗證前提**：Projects v2 欄位表達力（見前提 P3）——執行首日驗證，不足即依阻塞發現協定回報，不得自行降級表達。

## 前提清單（逐條附實查證據）

- **P1 gh token 具 `project` scope**：✅ 2026-08-04 20:14 `gh auth status` scopes ＝ `gist, project, read:org, repo, workflow`。
- **P2 Projects v2 API 可用**：✅ 同日 `viewer.projectsV2` GraphQL 查詢成功（totalCount=1，既有空專案 #1「@ruan6047's untitled project」可徵用或另建，執行者裁量並記錄）。
- **P3 欄位表達力**：⚠️ 未驗證。Ledger 現有 10 欄（卡ID／Initiative／級別／功能／owner／分支worktree／iteration／交付狀態／部署狀態／最後交接）＋新制欄位（服務的原始目標／鏈深／資源宣告）需以 Project custom fields（text／single-select／number／date）＋labels 表達。**執行首日以測試欄位實測後才可動遷移。**
- **P4 遷移母體**：✅ 活卡 38 張（`docs/TASKS.md` @ `30747b1`），其中 7 張凍結流程卡待需求方逐張處置批示（建議表：決議紀錄 §6）。

## 執行計畫

### Task 1：欄位結構驗證與定案（S）

以測試 Project 實測 P3 全部欄位型別；產出「Ledger 欄位 ↔ Project 欄位／label」對照表落 git，交 PM 轉需求方核可後**結構凍結**（`WF-22-CLI1` 依賴此凍結）。表達力不足者列明替代方案（如鏈深入 body 結構化區塊），不得靜默丟欄。

### Task 2：遷移腳本與 38 卡對帳（M）

`scripts/state_plane_migrate.py`（一次性，正式常駐版歸 `WF-22-CLI1 snapshot`）：每卡建 Issue（body＝指向 git spec 檔＋現況摘要＋新制欄位），寫入 Project 欄位。產出對帳表（卡ID ↔ Issue#，38/38 全中）落 git；任何一筆不中即 fail，不得部分宣告。

### Task 3：凍結卡處置批示與 cutover（S）

- 凍結 7 卡在 Issue 上掛 disposition 提案 label（依決議紀錄 §6 建議表），由需求方逐張批示後執行（封存者關 Issue＋`git mv` 卡檔進 archive）。
- `docs/CONTROL_PLANE_CONTRACT.md` 改版指向新狀態面（B2：需獨立校讀）。
- **cutover 由需求方明示宣告**；宣告前 `events.jsonl` 仍是唯一作業狀態事實來源，宣告後由 PM 祕書寫入終筆封存事件（executor 分支不得碰 `docs/control-plane/**`——終筆由祕書落 main）。

## 紅線

1. **cutover 前雙軌以 events.jsonl 為準**：Issue 建立≠切換；未經需求方宣告不得停寫舊制。
2. **對帳 38/38 全中才可宣告完整**（完整性宣稱須由 artifact 自動產生，不得人工聲明）。
3. **不得刪除 `events.jsonl`**：封存唯讀，歷史稽核仍在 git。
4. 執行分支不得改動 `docs/control-plane/**` 與 `docs/TASKS.md`（現行契約仍有效）。

## 非目標

- 常駐 CLI 五指令（`WF-22-CLI1`）；canonical 文本改版（Wave 2）；自建 GUI（60 天後複評）。

## 驗收

- [ ] P3 對照表經需求方核可，結構凍結留痕。
- [ ] 38/38 對帳表由腳本輸出落 git；看板可視全部活卡。
- [ ] 凍結 7 卡處置批示完成並執行。
- [ ] 契約改版通過獨立校讀；cutover 宣告與終筆封存事件落 main。
- [ ] `uv run ruff check`＋`uv run pytest -q` 通過（遷移腳本含最小測試）。

## Log

- 2026-08-04 register by Claude Fable 5@Claude Code（PM 祕書，依需求方 Wave 1 批准「批准兩張」）；📥Backlog。
