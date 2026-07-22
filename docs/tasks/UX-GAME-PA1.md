# UX-GAME-PA1 逐打席與逐球脈絡探索器〔T3；⚪一般〕

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`ai/<執行者>/UX-GAME-PA1`
- 執行：待指派　查核：待指派（須 ≠ 執行）
- Initiative：INIT-GAME-RECAP　spec 基線：v1.3
- DB：`db_scope: read`
- 部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：見 [`GAME_RECAP_PRODUCT_SPEC.md`](../GAME_RECAP_PRODUCT_SPEC.md) §5、§6.3、§7、§9
- Discovery：需求方 2026-07-16 確認逐打席理解是核心功能
- Design：spec v1.1 與 Design Brief 待需求方核可；實作前須補行動版與桌機互動 prototype
- current-state：📥Backlog；已由 Coordinator 註冊，等待 PA／WP API 與賽事總覽

## 目標

讓一般球迷從任何關鍵轉折理解「當時發生什麼」，並讓進階數據迷在同一脈絡下查看逐球、好球帶與 TrackMan；資料晚到或球場無設備時，保留基本打席分析而不顯示錯誤資料。

## 驗收條件

- [ ] 選定打席固定顯示局數、上下半局、比分、出局、壘況、投手、打者、結果、事件描述、WP 前後值、WPA 與受益隊。
- [ ] 逐球依 canonical `pa_id` 延遲載入，球序、球數、判定、球種、球速與進壘位置順序正確；不再以投手×打者×局數於前端近似匹配。
- [ ] `available`、`advanced_pending`、`no_equipment`、`source_missing`、`mapping_failed` 各有不同提示；任何狀態都不把未知說成零或沒有發生。
- [ ] 進階站 `SkipTrackman=true` 可作官方 skip 的正證據；`false` 僅代表未標示 skip，禁止直接映射成 `available`／`no_equipment=false`。
- [ ] 可在「全部打席／得分打席／高影響打席」間切換；高影響依 `abs(WPA)`，並明示不等同球員能力。
- [ ] 從打席可延伸到球員頁與投打對決；ML-SIM1 結果對照若未納入首版，不顯示空入口。

## 驗證

- [ ] 元件／整合測試涵蓋同局重複投打對戰、換投、代打、無逐球、晚到與 mapping failure。
- [ ] 375 px 使用打席卡與前後切換不需精準點擊；所有控制具 44×44 px 觸控區、鍵盤焦點與語意標籤。
- [ ] 瀏覽器確認曲線、轉折卡、時間軸與打席詳情選取狀態一致。
- [ ] API 首屏不傳整場不必要的 tracking payload；以瀏覽器 network evidence 確認延遲載入與錯誤退化。
- [ ] `cd web && npx tsc --noEmit`、`npm run build:check` 及相關測試通過。

## 依賴與交付

- 依賴：`GAME-RECAP-PA1`、`GAME-RECAP-WP-API1`、`UX-GAME-RECAP1`。
- 與 `UX-MATCHUP1/2` 僅建立深連結，不重做其查詢與統計洞察。
- 預估範圍：M；ML-SIM1 真實／模擬對照若加入，須另開整合卡。

## Log

- 2026-07-16 proposed by GPT-5@Codex → 待 Coordinator 註冊 lifecycle event。
- 2026-07-16 Coordinator register → 已寫入 lifecycle event／Ledger；依賴未解除前不得 claim。
