# 隊伍比較摘要私有接收與一次性發布

Pi 保持既有 10:10 賽程／特徵的送件契約。摘要是該日鏈後續的獨立送件。
沿同來源／日期的 run_id，摘要根為 /incoming/team-comparison/<run_id>。
snapshot.json 使用原初始化格式 columns／data；response.json 綁
version、source_id、run_id、as_of、snapshot_sha256、snapshot_bytes。
通知最後原子移入 /incoming/team-comparison-notify/<run_id>.ready，欄位
version、run_id、response_sha256。

VPS 使用 python /app/jobs/jobs.py team-comparison-only --wait-lock SECONDS。
等鎖時間由核發決定，須落在 oneshot 停止線以內。單一送件只收一次。
既有 refresh.lock 防止和賽程／特徵同時寫。先驗原通知、兩檔及摘要身分。
使用原 plan、insert-only／current 更新 SQL 與 reconcile；驗證、寫入、全量對帳
皆在同一資料庫交易。既有較新指標不回撥，重入同一收據不再連 DB。
service、容器與退出依既有發布收據查核。

正式核發須綁：
- 原 VPS runtime 底圖、同版只讀 jobs.py、features_handoff.py、sync.py、
  teamcmp_handoff.py 的 bytes；features_handoff.py 是既有
  src/cpbl/features/handoff.py，teamcmp_handoff.py 是摘要子模組的 handoff.py。
- 原私有 DB 網路、原 state 及原 inbox。writer 須有摘要三表讀寫、必要表鎖及
  temp table 權限。CPBL_TEAMCMP_WAIT_LOCK_SECONDS 依當下與原 10:10 writer
  的交集與退出線核定。既有正式賽程／特徵的單元照原排程。
- 私有摘要收件及通知目錄。可先核 bytes，path 不啟用、enabled 標記不存在。
  首次啟用後核日內唯一新批次的 Pi 收據、VPS 發布與鎖釋放。
- 交接時等 Mac 自動摘要執行確退，才在其既有私有 Application Support 根
  建立 mac-team-comparison-external。Mac launchd 的摘要計算及正式同步會略過，
  其他同步照原入口，手動摘要仍由原權限使用。沒有正式 Pi／VPS 交接時不放此標記。
  回復時先停本 path，確認 writer、交易及鎖確退並交回寫入權，再依核發撤原自有標記。
