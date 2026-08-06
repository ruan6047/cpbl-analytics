# ML-WP-ROLLWIN1 場中 WP 近年窗訓練修復（VAL1 §7 未試路徑）　〔T4〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：GAME-RECAP-WP-VAL1_RESULTS.md §7＋CAL1/STRENGTH1 No-Go 報告（嵌套時間外驗證紀律沿用）
- DB：db_scope=read
- 服務的原始目標：統計正確性——場中 WP 通過時間外校準門檻，解鎖 API 與 live 顯示
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：ML-WP-ROLLWIN1），不重複於此檔。

## 核心痛點

- **痛點**：場中 WP 中段時間外偏差 +4–6pt（主場優勢漂移），CAL1/STRENGTH1 兩修復皆 No-Go——但「近年窗訓練」直接針對漂移根源，A scope 從未試過；WP-API1 與 live WP（GAME-RECAP Wave 2）持續被鎖

## 驗收條件

- [ ] 近年窗（如 Y−3..Y−1）walk-forward 重跑 VAL1 harness，v2 門檻逐季判定；窗長選擇本身須時間外驗證（嵌套，禁池化自我吸收）
- [ ] 通過 scope 解鎖對應 WP-API1 範圍；不過則記死因入 §7

## 驗證

- [ ] uv run python -m cpbl.models.winprob_val 現成 harness；統計紅線 T4 跨家族查核
