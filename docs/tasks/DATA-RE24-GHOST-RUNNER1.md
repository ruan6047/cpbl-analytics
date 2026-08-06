# DATA-RE24-GHOST-RUNNER1 sabr.build_re24 突破僵局跑者誤記打席修復　〔T3〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：UX-GAME-RECAP1 spike-report §7（d2960ce）＋全季窮舉歸類 artifact（49 筆清單）
- DB：db_scope=write
- 服務的原始目標：資料正確性——RE24 個人歸因僅計真實打席
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DATA-RE24-GHOST-RUNNER1），不重複於此檔。

## 核心痛點

- **痛點**：build_re24 把突破僵局上壘記成該跑者一個打席、每筆 +0.6356 RE24（2026/A 已 49 筆且持續累積）——汙染 batter/pitcher_re24 與球員頁 SABR 區線上可見值

## 驗收條件

- [ ] build_re24 排除突破僵局幽靈跑者列（判準沿 spike 窮舉歸類）；重建 batter/pitcher_re24 前後對照 49 筆差異全數可解釋
- [ ] 回歸：未歸類=0 釘成測試（spike 建議）；G4 凍結檔零 diff

## 驗證

- [ ] ruff+pytest；生產重建併下次部署批次
