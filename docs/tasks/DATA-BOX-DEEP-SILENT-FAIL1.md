# DATA-BOX-DEEP-SILENT-FAIL1 逐場抓取失敗被吞成 exit 0，31 場靜默漏抓且其中 7 場即將永久錯過　〔T4〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
- 執行：待指派　查核：待指派
- Initiative：—　spec 基線：2026-08-10 週跑 log logs/weekly-box-revisions-20260810-141135.log 與狀態檔 logs/last-weekly-box-revisions.json @ cc7d81e
- DB：db_scope=write
- 服務的原始目標：抓取失敗不得以成功的形式收場；已宣告要抓的場次沒抓到必須讓人看得出來
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DATA-BOX-DEEP-SILENT-FAIL1），不重複於此檔。

## 核心痛點

- **痛點**：cpbl_gamelog.py:257 的 except Exception 把逐場抓取失敗降為 log.warning 後續抓，且結尾 done: 統計只計成功場、不對帳函式第一行自己宣告的目標場數。2026-08-10 週跑 kind=D 宣告 39 場、成功 8 場、失敗 31 場，仍 exit=0——看到 done:{games:8} 的人無從判斷 8 是目標還是 39 分之 8。同次 kind=A 因失敗發生在取 token 階段（逐場迴圈之前）而硬失敗 exit 1，整個 job 才顯示失敗；失敗落在哪個階段決定它是硬失敗還是靜默成功，這是巧合不是設計。該函式每日鏈也在用。已造成的資料缺漏：31 場賽日 2026-07-12～08-09 的賽後官方修正未進 box_pitching_revisions 快照，其中 7 場（07-12～07-17）於下次週跑 2026-08-17 時已掉出 days_back=30 窗，該路徑再也不會碰它們

## 驗收條件

- [ ] 硬截止 2026-08-17：在該日週跑前補抓 07-12～07-17 那 7 場，否則該路徑永久錯過。補抓方式與 days_back 由執行者提案、需求方核可後執行；不得自行連續重跑（爬蟲紅線：失敗後冷卻 15-20 分再單次重試）
- [ ] scrape_gamelogs 的回傳與結尾摘要必須對帳自己宣告的目標母體：至少回報 目標場數／成功／失敗，且失敗場號可列舉。done: 只印成功數屬缺陷
- [ ] 決定失敗語意：逐場失敗續抓仍可保留（單場失敗不該整批停），但整批的 exit code 必須反映有無失敗，或明確定義一個容忍門檻並寫出理由。不得維持現況的『有失敗也 exit 0』
- [ ] 每日鏈共用同一函式，改動必須同時評估對每日鏈的影響並在報告說明；不得只修週跑
- [ ] 不得為了讓數字好看而放寬對帳：補抓後仍抓不到的場次要列出來並說明原因

## 驗證

- [ ] 以 2026-08-10 的失敗情境回放：注入逐場失敗，確認新版會回報失敗場數且 exit code 反映失敗
- [ ] 補抓後對 31 場逐場確認 box_pitching_revisions 是否已有該場快照，artifact 由指令輸出產生
- [ ] uv run ruff check + uv run pytest；新增行為須有測試釘住
