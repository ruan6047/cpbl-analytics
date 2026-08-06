# DATA-RECAP-WP-PRESTATE1 /recap-wp 單事件得分打席 WPA 歸零缺陷修復　〔T3〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：UX-GAME-RECAP1 第五輪交付報告範圍外發現（4c3544a）
- DB：db_scope=read
- 服務的原始目標：統計正確性——WPA 歸因逐打席正確
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DATA-RECAP-WP-PRESTATE1），不重複於此檔。

## 核心痛點

- **痛點**：/recap-wp 用 pre_state 比分算 WP，單一事件即結束的得分打席（首球全壘打）pre_state 已是得分後值→該打席 WPA 被歸零、前一打席誤算（實測 243/245 各 2 筆、最大差 0.099）；與事實流（事件流打席前比分，正確）不一致

## 驗收條件

- [ ] 改用事件流打席前比分（比照 pa_facts 修法）；243/245 四筆實例修復對照；回歸測試

## 驗證

- [ ] ruff+pytest；與事實流逐打席一致性抽驗
