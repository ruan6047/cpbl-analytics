# DATA-RULES-AUDIT1 規則語意對齊盤點（規章→資料判讀的偽陽偽陰審計）　〔T3〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code（PM 祕書）
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：—
- DB：db_scope=read
- 服務的原始目標：資料正確性——以規章條文為藍本產出「已驗證前提清單」，讓所有衍生計算的規則前提可引用可證偽
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DATA-RULES-AUDIT1），不重複於此檔。

## 核心痛點

- **痛點**：規則盲區已實證咬過四次（SCORELESS×2、幽靈島 281 席、完成場雙向失效）；同族候選五條未盤（裁定殘局計入、保留賽歸屬、突破僵局衍生、和局斷連、kind 差異），隱性累積

## 驗收條件

- [ ] 逐條映射：規章 §38（裁定階梯/紀錄歸屬）/§47-48（名次/加賽/和局不計）/§66（季後賽九局制）＋手冊 1.02/突破僵局 → 對應資料語意（completed 判定/splits 歸屬/PA build/RE24-WP/special_records streak/outcome 標籤）逐項驗證，附 SQL 或對帳證據
- [ ] 五候選＋233 項（0:0 和局判定缺口＋滿5局以上 box 補爬）逐一判定：乾淨/缺陷分流（缺陷各附修復提案，不修碼）
- [ ] 詭異數據標記待人工判讀交需求方（233 前例）；已驗證前提寫入 GLOSSARY 或 reference 提案

## 驗證

- [ ] 全部宣稱由指令輸出產生
