# DEV-RESOURCE-VOCAB-ALIGN1 資源與狀態詞彙對齊：文件宣告的欄位與 token 必須在機器上真的存在　〔T2〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：—
- DB：db_scope=none
- 服務的原始目標：宣告出來的東西要真的被檢查，檢查不到時要響，而不是靜默通過
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DEV-RESOURCE-VOCAB-ALIGN1），不重複於此檔。

> 本檔於 2026-08-19 依現行 Issue body（跨家族查核「維持但條件」定稿：4 條驗收＋4 條驗證）重建；
> 第一版舊驗收條（含三句已被推翻的宣稱，見驗收條 2）已汰除。

## 核心痛點

- **痛點**：文件與慣例在用的詞彙，機械面不存在或直接被拒，於是照文件寫的人不會收到任何錯誤，只是永遠不被檢查

## 驗收條件

- [ ] 機械替換 12 處：docs/DATABASE_CONTRACT.md 行 20(×2)/21/22/32/46 共 6 處、docs/AI_RUNBOOK.md:415 共 2 處、docs/tasks/DATA-INCOMPLETE-BOX-INGEST1.md:16,22、docs/tasks/OPS-PROD-SYNC-SEQ-COLLISION1.md:19,22——一律 db:<env>:cpbl → db:<env>:schema，不得以刪除達成歸零。⚠️ DATABASE_CONTRACT §2 表格列數不得減少、§3 的 db_resources yaml 區塊必須保留：那三列正是本卡引為權威的環境定義。⚠️ 射程排除兩處（封閉集合逐字排除，不是語意判準）：docs/ROADMAP.md:283 的 token 是「對缺陷的描述」而非用法，原句「db:<env>:cpbl 被 wfcli 的 grammar 拒收」在修完後仍然為真，替換反而製造假話；docs/tasks/DEV-RESOURCE-VOCAB-ALIGN1.md:18,19 見下一條
- [ ] docs/tasks/DEV-RESOURCE-VOCAB-ALIGN1.md 依現行 Issue body 重建，不做 token 替換。⚠️ 該檔停在本卡第一版的舊驗收條，:17,18,19 含三句已被推翻的宣稱（「17 筆 db token、dev×2」實為 19 筆 dev×4；「既有卡面不可改」錯，wfcli amend 改得動；「規劃中狀態欄無此選項」已於 2026-08-18 翻轉）。對過期文件做機械替換是問錯問題——這正是 canonical AI_WORKFLOW.md §4.1「寫進 spec 檔而不是卡面時無人檢查」的活標本，與 #136（spec 檔宣告 production+local 而 Issue body 宣告 db:prod:schema 加三張表，只有 body 被讀）同形
- [ ] ⚠️ 封存區逐位元不變（依跨家族查核 Finding 4 補回，blocking）：`git diff --quiet $BASE -- docs/control-plane/ docs/TASKS.md docs/archive/ docs/research/` 必須為空，且 **$BASE 必須是派工時釘住的 merge-base**，不得用 HEAD。⚠️ 實測 git diff --quiet HEAD 在執行者 commit 之後恆綠（未 commit 退出碼 1、已 commit 退出碼 0），比它取代的計數比對更弱。此條由查核者在合併結果上跑，不是交付者在交付當下跑。理由：全庫無 CODEOWNERS、無 hook、ci.yml 對 control-plane／archive／events.jsonl 零提及，砍掉本條後沒有任何東西守著封存唯讀且紅線 3 禁刪的 events.jsonl；廣域取代可靜默傷及 docs/control-plane/events.jsonl、docs/TASKS.md、docs/archive/
- [ ] ⚠️ 交付物須明寫修完仍然不成立的部分：(1) DATABASE_CONTRACT §3 的「同一 <environment, schema> 僅一個 migration writer」在 token 改對之後機械上仍為假——find_conflicts 是完全字串比對，db:local:schema 不支配 db:local:table:X；(2) 文件詞彙合法不代表互斥機制已具有階層語意。不寫這兩句，文件會從「非法且假」變成「合法且假」，本卡核心痛點在自己的修法裡復發。⚠️ 順帶記錄替換的副作用：db:local:cpbl 帶了「哪個 schema」的資訊而 db:local:schema 沒有，本專案只有一個 schema 故今日等價，但該規則連指名 schema 的能力都失去了

## 驗證

- [ ] 交付後逐檔驗 occurrence：DATABASE_CONTRACT.md 與 AI_RUNBOOK.md 的 db:<env>:cpbl 為 0、db:<env>:schema 分別為 6 與 2。輸出為腳本自動產生非人工聲明
- [ ] ROADMAP.md:283 逐位元不變（射程排除的證明）
- [ ] DATABASE_CONTRACT §2 表格列數與 §3 db_resources yaml 區塊前後對照，證明未因替換而減少
- [ ] 查核者在合併結果上跑封存區 diff（$BASE = 派工時釘住的 merge-base）並貼出輸出，期望為空。⚠️ 不得用 HEAD 當基線、不得由交付者在交付當下跑，兩者 commit 後皆恆綠
