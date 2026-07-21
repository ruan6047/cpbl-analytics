# UX-PLAYER-SCOPE1 球員頁本季／生涯全域範圍重整〔T3；⚪一般〕

- 需求：ruan6047　規劃：GPT-5@Codex　分支：`ai/<執行者>/UX-PLAYER-SCOPE1`
- 執行：待指派　查核：待指派（須 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：UX-PLAYER-IA2＋UX-MATCHUP2＋[`UX-PLAYER-SCOPE1-BRIEF.md`](../design/UX-PLAYER-SCOPE1-BRIEF.md)
- DB：`db_scope: none`（純前端；不動 API／SQL）
- 部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：[`UX-PLAYER-SCOPE1-BRIEF.md`](../design/UX-PLAYER-SCOPE1-BRIEF.md) §1–§7
- Discovery：2026-07-22 需求方走查＋1440px／390px 真實頁面複驗
- Design：2026-07-22 需求方核可「保留 Hero 雷達並由下方全域本季／生涯驅動；保留全部既有圖表，僅移除仰角 × 初速散點圖」
- owner、worktree、iteration、最後交接、阻塞與交付／部署 current-state 見 [`../TASKS.md`](../TASKS.md) Ledger；歷史寫入 adapter event log

## 目標與驗收

- [ ] 建立唯一全域 `scope=season|career`，同步控制 Hero headline／能力雷達、內容導覽、資料載入與全頁模組；移除 Hero 與分項內重複 scope state。
- [ ] scope、role、view、level 分軸且 URL 可分享；雙棲以可見 role 控制取代長內容上下堆疊，單一身分不顯示多餘控制。
- [ ] 本季與生涯互斥渲染；生涯不再先經過本季總覽，退役預設生涯、二軍保留一／二軍鏡頭。
- [ ] 除 `LaEvScatter` 外，現有球員頁圖表與互動全數保留並依 Brief migration map 歸位；同步移除該圖孤兒程式與頁尾說明。
- [ ] UX-MATCHUP2 的共用 MatchupExplorer、fail-closed、coverage／credibility／baseline 與 deep-link 零退化。
- [ ] 舊 `?sec=`／`?role=` deterministic 相容；返回／前進、鍵盤 tabs、loading／空態與 375px 正確。

## 驗證、依賴與資源

- 驗證：純函式狀態／legacy migration 測試、web tests、`npx tsc --noEmit`、`npm run build:check`、真實瀏覽器 1440px／375px 六情境走查。
- **硬依賴／序列化**：`UX-MATCHUP2` 已合併 main，但仍持有 `file:web/src/app/players/[id]/` lease；本卡在其 release／釋放 local lock 前不得 claim。執行分支須從包含 merge `bc15ba1` 的 main 建立。
- 預定 resources：`file:web/src/app/players/[id]/`、`file:web/src/components/la-ev-scatter.tsx`；不 claim `web/src/components/matchups/`。
- 可平行：`MATCHUP-DATA2`（API）、`UX-PA-SIM-MATCHUP1`（限 `/matchups` 與共用模擬 UI）、TrackMan ingest／OAA validation；任何一方若擴張至上述 resources，先重新協調。
- 預估範圍：M–L（跨模組 IA、URL migration、資料載入與 responsive 驗證）。
- 非目標：不改 API／SQL／統計公式，不改圖表視覺語言，不新增 OAA／Stuff+／PA 模擬入口，不在本卡部署。

## Log

- 2026-07-22 register：需求方核可設計硬限制並要求開卡；衝突稽核確認 UX-MATCHUP2 為唯一硬資源阻塞，故註冊為 Backlog、不 claim。
