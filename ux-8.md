# UX-8 排行與紀錄群

## Goal
讓 `/batters`、`/pitchers`、`/records` 共用一致且可快速掃讀的 DataTable 資訊架構。

## Tasks
- [x] 將 `Leaderboard` 的手刻表格改由 `DataTable` 渲染，保留排序、篩選、Tooltip 與數值條。
- [x] 統一打者／投手頁的頁首與區塊層級，讓領先者、篩選與完整排名在 5 秒內可辨識。
- [x] 將紀錄室的比賽、單季、生涯與球隊沿革重排為 `DataTable`，保留個人／球隊深連結。
- [x] 跑 `npx tsc --noEmit`、`npm run build:check` 與專案測試。
- [x] 以 375px／1280px、淺色／深色實測三頁，確認無橫向頁面溢出與 console error。

## Done When
- [x] 三頁資料表皆由 `DataTable` 提供表殼與響應式捲動。
- [x] 互動、名詞解釋、空態與鍵盤操作無回歸。
- [x] 程式驗證與四組視覺檔位均通過，卡片轉為待查核。

## Notes
不修改 API、資料庫或排行統計定義；UX-8 為一般 UI 卡，實作完成後需交由獨立 session 查核。
