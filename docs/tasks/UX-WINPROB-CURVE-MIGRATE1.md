# UX-WINPROB-CURVE-MIGRATE1 WP 曲線遷移 canonical PA＋規則化解算器　〔T3〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：UX-GAME-RECAP1 第五輪交付報告（4c3544a）；ML-WP-ROLLWIN1（#95）若先行可併窗訓練升級
- DB：db_scope=read
- 服務的原始目標：一致性——單場頁 WP 單一來源
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：UX-WINPROB-CURVE-MIGRATE1），不重複於此檔。

## 核心痛點

- **痛點**：頁面 WP 曲線走 legacy /winprob（近似打席分組＋未參數化 2024+ 突破僵局規則），與事實流（canonical PA＋規則化解算器）存在 ≤0.7pt 落差——同頁兩套 WP 來源

## 驗收條件

- [ ] 曲線改吃事實流同源 WP；241/243/245 逐點對照差歸零；夾層與終場豁免沿 win-prob-display 單一擁有者

## 驗證

- [ ] npm test＋視覺對照
