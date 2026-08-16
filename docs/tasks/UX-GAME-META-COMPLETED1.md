# UX-GAME-META-COMPLETED1 單場頁 document title 對未開打的比賽宣稱 0：0　〔T2〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
<!-- wf-routing:v1 -->
- 執行：待指派（建議 主力型；改動小但跨 API 與前端兩個表面，且必須抵抗一個很自然的錯誤做法（在 TypeScript 裡重寫完成場判準）——那會製造本專案已明列的第三份判準副本。要能看出那個陷阱才做得對。）　查核：待指派（建議 主力型；可由端點回應與前端測試機械驗證；查核重點是「有沒有抄判準」，判定明確不需高階推理。）
- Initiative：—　spec 基線：#126 DAILY-MIXED-DAY-UX1 的 Design Gate 裁定（2026-08-16，issuecomment-5305331712）第五節
- DB：db_scope=read
- 服務的原始目標：不把未證實的東西說成事實
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：UX-GAME-META-COMPLETED1），不重複於此檔。

## 核心痛點

- **痛點**：web/src/lib/entity-metadata.ts:31 以 away_score != null && home_score != null 決定要不要把比分寫進 document title，而未開打的比賽在 DB 是 0/0 不是 NULL——於是延賽場的分頁標題渲染成「味全龍 vs 樂天桃猿 0：0」，對一場沒有打過的比賽宣稱了比數。判準是「有沒有值」不是「這場打完了」

## 驗收條件

- [ ] metadata 端點回傳 completed，前端消費它而非自行判斷;⚠️ 不得在 TypeScript 裡重寫完成場判準。cpbl.completion.is_completed_game() 是 canonical 實作，#126 已裁定 daily.py 改為呼叫它；本卡若在 TS 再抄一次，會是同一判準的第三份副本;未完成場的 title 不得出現任何比分。中性標題的措辭比照 #126 已核可的文案紀律——不得把未證實的原因說成事實;⚠️ 經官方 box 證實的 0:0 和局（全庫 5 場：2018/A/124、2021/A/256、2023/A/119、2023/A/175、2025/A/233）**應該**顯示 0：0，因為那是真的賽果。修法必須能區分這兩種 0:0，不得一律隱藏

## 驗證

- [ ] 以延賽場（例 2026/A/254）與經證實和局（例 2023/A/175）各取一次 title，前者不得含比分、後者必須含 0：0;變異檢驗：把 completed 判定改回 != null，測試須轉紅;cd web && npm test + npx tsc --noEmit + npm run build:check；改動 games 端點須同步路由快照 EXPECTED
