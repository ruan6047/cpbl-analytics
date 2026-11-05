# #393 原驗收5：連線標籤與Mac入口防誤觸

這是808之後的獨立候選，只補原PLAN的切換契約；本候選不建立真標記、不停用launchd、不修改主checkout或實際連線。

## jobs 的 application_name 有效設定點

`cpbl.db.pool()` 把 `settings.database_url` 原樣交 `ConnectionPool`，沒有另外覆寫application_name；
`_configure` 只處理既有時區及API時限，不改標籤。由WP5僅在jobs服務的受保護 `DATABASE_URL`
明設唯一的 libpq `application_name=cpbl-jobs`：URI query參數或keyword DSN皆可，保留原身份／host／DB／schema。
例如URI使用 `…?application_name=cpbl-jobs`；已有query則作一個query參數，不保留相反的重複application_name。
不得把此jobs專用覆寫套到主站/API共用env。

既有 `PGAPPNAME=cpbl-jobs` 是libpq在未顯式給application_name時的fallback，jobs.py也只為未設值補預設；
因此只看到env不能證明實際DSN沒覆成別名。這不需修改DB角色／schema／SQL，也不需修改db.py。
標籤不是排他權限或唯一writer證據，WP7核發後的pg_stat_activity取樣仍另留實際收據。

## Mac舊入口的候選guard

共用標記固定在 `$HOME/Library/Application Support/cpbl-analytics/mac-jobs-disabled`。
它不依repo相對logs或當前worktree定位，所以同一Mac使用者在其他工作樹呼叫舊入口也看到同一標記。
入口只查存在，不讀內容、不建立／移除；一般檔、目錄或symlink（含dangling）存在都拒跑，退出78並印明示救援方式。

覆蓋原六工作入口：scrape-daily.sh、postseason-evening.sh、weekly-box-revisions.sh、weekly-game-pitches.sh、
schedule-watchdog.sh及alert_watch.py舊CLI；另涵蓋可直接手動同步的refresh-cpbl-prod.sh。
guard位於help/參數解析之後、舊業務初始化／受保護.env讀取／log與lock／Docker/DB/HTTP/healthchecks/launchd之前。
`--help` 仍零業務成功退出；原Linux `--jobs` 及daily的既有jobs專用入口在此前分流，Linux jobs.py直接入口不因Mac標記停用。
這是指定舊入口的防誤觸，並非所有Python CLI的DB授權機制；直接執行其他維護CLI仍須原租用。

標記存在時，只接受單次明示環境 `CPBL_MAC_RESCUE=1` 才允許原入口繼續；不自動刪標記、不bootstrap或啟動其他工作。
此flag只表達明示救援，不代替writer／DB／服務租用。只在核定的單次手動救援使用，
不得寫進.env、plist、常駐環境或launchctl setenv，避免重新允許自動工作。

## 生效、回復與未驗

標記未建立時，入口維持原預設，候選本身不會停掉Mac的首度取得。
只有WP6／替代新路徑正式驗證、原切換前提滿足且WP7明核切換後，核定actor才可建立私有父目錄0700／標記0600，
再依原計畫停用六launchd並留證據；建立標記及bootout的具體次序／退出／排他，由同次切換租用明列，本文件不先操作。
原計畫回復為先確認VPS jobs停止／無衝突writer，經回復授權才移除標記並bootstrap原plist；
不得在VPS尚活躍時僅靠救援flag讓兩端並寫。
本機只用假HOME與業務邊界樁核拒跑／明示救援，沒有執行真舊工作、建立真marker或讀真launchd；不代替切換後唯一writer取樣。
