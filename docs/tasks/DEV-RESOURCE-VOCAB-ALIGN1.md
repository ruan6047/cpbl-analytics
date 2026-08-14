# DEV-RESOURCE-VOCAB-ALIGN1 資源與狀態詞彙對齊：文件宣告的欄位與 token 必須在機器上真的存在　〔T2〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：—
- DB：db_scope=none
- 服務的原始目標：宣告出來的東西要真的被檢查，檢查不到時要響，而不是靜默通過
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DEV-RESOURCE-VOCAB-ALIGN1），不重複於此檔。

## 核心痛點

- **痛點**：文件與慣例在用的詞彙，機械面不存在或直接被拒，於是照文件寫的人不會收到任何錯誤，只是永遠不被檢查

## 驗收條件

- [ ] 環境詞彙收斂為單一組：現行 17 筆 db token 有 prod×5 / production×2 / local×8 / dev×2 四種寫法，其中 dev 不在契約的環境表內。須裁定唯一寫法並讓既有卡一致（既有卡面不可改，處置方式須一併提案）
- [ ] DATABASE_CONTRACT.md 的 db:<environment>:cpbl 不再出現：該 token 被 wfcli grammar db:[^:]+:(schema|table:.+) 直接拒收，全檔 line 20/21/22/32/38/46 皆在使用
- [ ] 文件不得再引用不存在的狀態或欄位：已知三處為 gate_evidence（無任何儲存）、🧭規劃中（交付狀態欄無此選項）、db:<env>:cpbl。須窮舉檢查而非逐一修補
- [ ] 本卡只做 cpbl 這側；wfcli grammar 是否放寬屬 ai-workflow repo，另行提 issue，不做成子卡

## 驗證

- [ ] 以 wfcli 實際欄位選項與 resources.py 的 grammar 為準做窮舉比對，輸出須為自動產生的清單而非人工聲明
