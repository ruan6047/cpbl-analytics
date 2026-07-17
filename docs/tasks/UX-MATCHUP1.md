# UX-MATCHUP1 `/matchups` 查詢式頁面重製〔T4；🔴統計／ML〕

- 需求：ruan6047　規劃：GPT-5@Codex（`matchups-redesign.md`）　分支：`ai/<執行者>/UX-MATCHUP1`
- 執行：待指派　查核：待指派（跨模型家族或人工，且 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2＋ML-MATCHUP1
- DB：`db_scope: read`
- 部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：消費已核可的資料與統計洞察，提供 query-driven 對戰頁；基礎實績是 hero，洞察卡只作加值層。

## 驗收條件

- [ ] 沒有洞察時仍可查詢樣本與基礎實績；通過閘門才顯示 baseline 差、credibility 與 coverage，禁止「天敵」確定語氣。
- [ ] 覆蓋率不足、先驗無法估計、候選未過 credibility、C–E 無 baseline 四種 fail-closed 狀態各有獨立版面與文案。
- [ ] 年度／career／range、隊伍／個人、coverage 與 sample_scope 不混淆；375 px、鍵盤與 deep-link 可用。

## 驗證與依賴

- 驗證：四種空狀態 fixture、角色翻轉／低樣本／C–E 契約、瀏覽器走查、T4 獨立查核、`tsc`、`build:check`。
- 依賴：MATCHUP-DATA1、ML-MATCHUP1 已結案；完成後才能 claim UX-MATCHUP2、UX-PA-SIM-MATCHUP1。
- 預估範圍：M。

## Log

- 07-15 WF-12 遷移：維持 Backlog。
- 2026-07-17 baseline v0.2 → fail-closed 改為常態版面，洞察卡不再是 hero。
