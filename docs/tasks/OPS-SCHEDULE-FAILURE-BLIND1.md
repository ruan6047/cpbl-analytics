# OPS-SCHEDULE-FAILURE-BLIND1 排程失敗沒有任何觀測面，兩個排程同日失敗三天無人知　〔T2〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：2026-08-13 實測：launchctl list com.cpbl.weekly-box-revisions → LastExitStatus=256；logs/last-weekly-box-revisions.json result=failed；logs/refresh-20260810-101000.log overall exit=1 @ cc7d81e
- DB：db_scope=none
- 服務的原始目標：已經在跑的東西壞掉時要被發現，而不是等下一個人碰巧翻到
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：OPS-SCHEDULE-FAILURE-BLIND1），不重複於此檔。

## 核心痛點

- **痛點**：2026-08-10 當天每日鏈 refresh 硬失敗（overall exit=1，logs/refresh-20260810-101000.log）、週跑 box 深度重抓也失敗（LastExitStatus=256），兩者都寫了狀態檔與 log，但沒有任何一處會主動顯示它。三天後 2026-08-13 是 PM 為了別的事翻 launchctl list 才看到 com.cpbl.weekly-box-revisions 的 exit status 是 1。現況等於連『靠人記得看』都沒有——沒有人被指派去看，也沒有一個地方會冒出來。這直接違反藍圖 §0 目標 2 的判準『壞了會被發現；靠人記得看不算』

## 驗收條件

- [ ] 先盤點觀測面現況再提方案：目前有哪些狀態檔／log／端點承載排程結果（logs/last-*.json、/api/info 的 last_refresh 等），逐項說明它是否會讓失敗浮現。artifact 由指令輸出產生
- [ ] 方案必須指名『誰會看到』。依藍圖 §0 目標 2，沒有讀者的告警不算達成——若結論是靠人主動查，要說明何時查、由誰查，並承認這只是目標 3
- [ ] 必須驗證告警機制自己會響：刻意讓一個排程失敗，確認訊號真的出現。沒做過這件事的偵測器不算數
- [ ] 不得只處理週跑：每日鏈 2026-08-10 同樣硬失敗且同樣無人知，兩者都要涵蓋
- [ ] 本卡不修抓取邏輯——逐場失敗吞成 exit 0 屬 DATA-BOX-DEEP-SILENT-FAIL1（#131）射程，不得越界

## 驗證

- [ ] 以 2026-08-10 的真實失敗回放：若當時已有本卡的機制，失敗會在何時、以什麼形式、被誰看到
- [ ] uv run ruff check + uv run pytest；改動 /api/info 須同步路由快照 EXPECTED
