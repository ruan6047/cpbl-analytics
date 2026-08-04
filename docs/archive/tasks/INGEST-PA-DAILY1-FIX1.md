# INGEST-PA-DAILY1-FIX1 sync_pa_build 首次生產同步因 ad-hoc id 漂移回滾　〔T3〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code（PM 祕書）
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：—
- DB：db_scope=write
- 服務的原始目標：每日鏈生產同步恆真——PA 家族 5 表 prod 與本機一致且對 id 漂移免疫
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：INGEST-PA-DAILY1-FIX1），不重複於此檔。

## 核心痛點

- **痛點**：首跑實測：source_revisions ON CONFLICT (id) 撞不到 08-03 ad-hoc 同步的同內容異 id 舊列→unique 約束爆→單交易全回滾；今日 10:10 daily run 會在同點斷（games/gamelog 已同步後、retrain/freshness 前）

## 驗收條件

- [ ] 修法落地（強烈建議比照 game_features 先例：prod 端 TRUNCATE 家族 5 表依 FK 序＋全量重灌；若另擇 content-key conflict 方案須論證 id 對齊如何保證）
- [ ] 有人值守重跑 SKIP_SCRAPE=1 WITH_DETAIL=1 全鏈端到端成功（備份→同步→retrain→freshness marker）
- [ ] prod 與本機 PA coverage 以正確 SQL（DISTINCT 修正版）逐 kind 相等
- [ ] 解釋本機 D published(169)>completed(164) 的 5 場異常並判定是否需處理

## 驗證

- [ ] 重跑輸出全文留痕＋兩端對帳 SQL 輸出
