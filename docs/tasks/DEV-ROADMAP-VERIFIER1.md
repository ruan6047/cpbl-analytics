# DEV-ROADMAP-VERIFIER1 ROADMAP §3 歸屬驗證器、其回歸測試與事故 manifest　〔T2〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：母卡 DOC-CPBL-ROADMAP1（#130）R1 finding CPBL-ROADMAP1-R1-03 與 R2 finding R2-001／R2-002 @ 9319be56a1e1b628475a1228ff8fb7f8e17ecdbb；R1 共同設計基線 8 見 #130 issuecomment-5284078990
- DB：db_scope=none
- 服務的原始目標：ROADMAP §3 的「清單由指令產生」不得再是宣稱——工具要存在、要限定在它宣稱的範圍內、且失效方向要保守
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DEV-ROADMAP-VERIFIER1），不重複於此檔。

## 核心痛點

- **痛點**：DOC-CPBL-ROADMAP1（#130）的 R1 finding R1-03 要求「新增版本化唯讀完整性驗證器與測試」與「新增 incident manifest 並由 ROADMAP 引用」，但 #130 的 resource-claims 只有 file:docs/ROADMAP.md。執行者在 9319be5 直接交付三個新檔，被 R2-001 判為越界（canonical §3.2：遇授權缺口要停下回報，不得以無碰撞自行擴權）。需求方 2026-08-14 裁定拆卡：三個檔移到本卡並獨立宣告資源，#130 縮回純文件。另 R2-002 已證實 cards_in_roadmap() 對全檔逐行套 regex、未定位 §3，§3 以外任何合法格式的卡 ID 表格列都會造成假失敗——該缺陷隨檔案一併移入本卡修復

## 驗收條件

- [ ] 修復 R2-002：解析限定在 §3「現行排程」標題起至下一個同級標題止；§3 以外的合法卡 ID 表格列必須被忽略，且未知歸屬／重複／雙向差集的 fail-closed 行為不得因此放寬
- [ ] 新增回歸測試釘住邊界：至少含 (a) §3 外表格列被忽略 (b) §3 內表格列仍被讀到 (c) §3 標題不存在時的行為須明確定義並測試（fail closed 或明確錯誤，不得靜默回空集）
- [ ] 沿用既有 11 條測試不得退步；SCHEMA_VERSION 因解析規則變更須遞增，並說明為何遞增
- [ ] 變異檢驗一律在臨時副本上做，不得改動版控檔——查核者與執行者的工作區必須全程乾淨
- [ ] 不得修改 docs/ROADMAP.md（那是 #130 的宣告資源）。§3 措辭的調整由 #130 自行處理

## 驗證

- [ ] 以母卡 #130 分支上的 docs/ROADMAP.md 實跑 --check，並注入 §3 內／§3 外兩種卡 ID 表格列，證明前者被抓、後者被忽略；artifact 由指令輸出產生
- [ ] uv run ruff check + uv run pytest；貼 pwd 與 git rev-parse HEAD 自證位置
