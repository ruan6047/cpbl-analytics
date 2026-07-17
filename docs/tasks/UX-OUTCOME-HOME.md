# UX-OUTCOME-HOME 可嵌入賽前勝率卡〔T4；🔴統計／ML〕

- 需求：ruan6047　規劃：GPT-5@Codex＋Fable-5　分支：`ai/<執行者>/UX-OUTCOME-HOME`
- 執行：待指派　查核：待指派（跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2
- DB：`db_scope: read`
- 部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：只交付 `PregameCard`、fixture 與文案紅線；首頁唯一 owner 是 UX-GAME-HOME1。

## 驗收條件

- [ ] 卡片只顯示點機率＋1 個主要訊號；首頁不顯示區間，完整賽事頁／方法頁固定稱「模型敏感度區間」。
- [ ] fixture 涵蓋 available、artifact missing、unsupported、pending、error；缺模型時不阻塞賽程卡，也不補 50% 假數字。
- [ ] 元件不抓首頁聚合資料、不決定區塊排序、不修改首頁文案；輸出 contract 可由 UX-GAME-HOME1 嵌入。

## 驗證與依賴

- 驗證：fixture／元件／文案紅線測試、375 px／鍵盤走查、T4 獨立查核、`tsc`、`build:check`。
- 依賴：ML-SIM1 已完成並通過 production gate；與 UX-GAME-HOME1 序列化共享檔。
- 預估範圍：S。

## Log

- 07-14 自首頁微調拆出，待派工。
- 2026-07-17 baseline v0.2 → 降級為 PregameCard 元件卡，首頁 owner 歸 UX-GAME-HOME1。
