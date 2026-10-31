# 排程時間線（launchd）

本文件說明本機 launchd 排程各自服務什麼事件、為什麼落在現在的時刻、占用哪些資源，以及任務什麼時候真的需要等排程。來源卡：[#400](https://github.com/ruan6047/cpbl-analytics/issues/400)。#393 把排程搬到 VPS 之後，改的也是這一份，不另開新檔。

## 0. 用途與單一來源規則

- **時刻只住一處**：launchd 的觸發時刻、間隔與 healthchecks 期限，一律以 `scripts/schedule-registry.json`（下稱 registry）為準；registry 以外的程式內時窗，以程式常數為準。
- **本文件不寫數值**：每個排程只寫 registry 欄位路徑（例：`jobs[label=com.cpbl.scrape-daily].cadence`）或常數名稱（例：`src/cpbl/ingest/postseason_evening.py::DAILY_GUARD`）。可以出現的數字只有研究量到的觀測值，而且必須附 R1／R2 的固定版本連結；那些是歷史證據，不是排程設定。
- **其他文件只引用本文件**：`docs/AI_RUNBOOK.md` 的排程段、`.wf/cpbl-local.md`、Claude 記憶都不再自己寫排程時刻。Runbook 中的程式內時窗屬於行為規格，保留原文（[#400 裁定 D3](https://github.com/ruan6047/cpbl-analytics/issues/400#issuecomment-6543888486)）。
- **證據來源**（固定版本）：
  - R1 排程實際分布：[R1_schedule_timing.md](https://github.com/ruan6047/cpbl-analytics/blob/10148f5f8e0494871c1d6041e606e31dbd894f1c/docs/research/SCHED-TIMING-400/R1_schedule_timing.md)，量測輸出 [R1_measurements.md](https://github.com/ruan6047/cpbl-analytics/blob/10148f5f8e0494871c1d6041e606e31dbd894f1c/docs/research/SCHED-TIMING-400/R1_measurements.md)（下文〔M#〕指它的節）
  - R2 排程卡住任務的案例：[R2_blocked_tasks.md](https://github.com/ruan6047/cpbl-analytics/blob/10148f5f8e0494871c1d6041e606e31dbd894f1c/docs/research/SCHED-TIMING-400/R2_blocked_tasks.md)
  - 優化項目 O1–O12：[PLAN_400.md §2](https://github.com/ruan6047/cpbl-analytics/blob/ad70a289875c68ee642878b82570695cb0402a2e/docs/research/SCHED-TIMING-400/PLAN_400.md)

**查現值**（只讀 registry，不執行任何 `cpbl-*` 或 `scripts/*.sh`；在 repo 根目錄執行）：

```bash
python3 -I -c "import json;[print(j['label'],j['cadence'],j.get('alert',{}).get('deadline',''),j.get('evening_alert',{}).get('fallback_deadline','')) for j in json.load(open('scripts/schedule-registry.json'))['jobs']]"
```

程式內時窗的現值（只讀原始碼）：

```bash
grep -nE '^(DAILY_GUARD|BLOCK_RELEASE_AT|NIGHT_START|EVENING_GRACE|FALLBACK_DEADLINE|FIRE_AT|FIRE_END|RETRY_AFTER) ' src/cpbl/ingest/postseason_evening.py scripts/alert_watch.py src/cpbl/ingest/starter_watch.py src/cpbl/ingest/starter_checkpoints.py
```

共用名詞：
- **refresh lock**：`/private/tmp/cpbl-analytics-refresh.lock`。每日鏈、兩個週跑、晚間鏈的 www／同步步驟共用；拿不到鎖的排程 job 退出碼 75、不等待、不搶佔。
- **本機 DB**：本機 PostgreSQL 容器（OrbStack）。容器沒開時，每日鏈 exit 127，週跑也會失敗。

---

## 1. 賽季

每個排程固定五欄：registry 欄位路徑、服務的事件、選這個時刻的理由、資源足跡、失敗或缺席時誰會看見。事件代號 E1–E6 見 R1 §3。

### 1.1 `com.cpbl.scrape-daily`（每日鏈）

- **registry 欄位**：`jobs[label=com.cpbl.scrape-daily].cadence`；外部期限 `.alert.schedule`、`.alert.grace_minutes`、`.alert.deadline`。
- **服務的事件**：前一晚的完賽、box／livelog、stats 累計與逐球入庫，並同步正式站（E1–E3）。開頭依日型閘門（`src/cpbl/ingest/daily_gate.py`，#364）分流 full／light／sync_only／skip；聯盟收官後略過已收官軍別的爬蟲（#391，`src/cpbl/season_close.py`）。
- **選這個時刻的理由**：時刻不受官方發布綁住。主要資料在終場後數分鐘到約半小時內就齊了（R1 §3 E2、E3〔M4〕），晚發布的 TrackMan 與賽後修訂以天、週計（E4、E5），每日鏈改到哪個時刻都抓不到它們，由週跑負責。實際約束有三個：Mac 醒著、本機 DB 容器開著、Runbook §3 的「時段紅線：勿改到深夜／凌晨」（官網深夜加嚴）（R1 §4.1）。
- **資源足跡**：取 refresh lock；連本機 DB；full／light 日爬 www（Playwright）與 stats，sync_only 日只同步；同步日寫正式站。skip 日只判日型就結束（R1 §4.1〔M2b〕）。日型與各型做什麼以 `daily_gate.py` 為準。
  - 正在忙的訊號：refresh lock 存在；`logs/last-launchd-status.json`（只由 launchd 更新）或 `logs/last-status.json` 的 `state=running`。
- **誰會看見失敗**：healthchecks check `daily`（registry `.alert`；失敗立即、缺席或延後在 `.alert.deadline`）；`schedule-watchdog` 依 `logs/schedule-history/com.cpbl.scrape-daily.jsonl` 判週期缺席。手動 fallback 不送 `daily` ping（Runbook §11.1）。

### 1.2 `com.cpbl.weekly-game-pitches`（逐球週跑）

- **registry 欄位**：`jobs[label=com.cpbl.weekly-game-pitches].cadence`。
- **服務的事件**：stats 逐球的晚發布與賽後修正（E4）；每週全季重跑一次，使修正最遲在一個週期內收斂（腳本檔頭）。
- **選這個時刻的理由**：晚發布以天計，時刻與官方事件無關。`cadence.weekday` 落在中職固定休兵日（沒有新完賽場），時刻只用來避開每日鏈，並與 box 週跑錯開（R1 §4.2〔M9〕）。
- **資源足跡**：取 refresh lock（忙碌即跳過，exit 75）；連本機 DB；連 stats（無反爬），不連 www。
  - 正在忙的訊號：refresh lock；`logs/last-weekly-pitches.json`。
- **誰會看見失敗**：`schedule-watchdog`（`logs/schedule-history/com.cpbl.weekly-game-pitches.jsonl`）。registry 沒有 healthchecks 段。

### 1.3 `com.cpbl.weekly-box-revisions`（box 週跑）

- **registry 欄位**：`jobs[label=com.cpbl.weekly-box-revisions].cadence`。
- **服務的事件**：www box 在賽後數天以上才出現的官方修正，也是 box、livelog、scoreboard 晚期修訂的主要觀測者（E5〔M6〕〔M7〕）。深抓窗的長度見 `run_refresh_box_deep` 模組 docstring。
- **選這個時刻的理由**：週頻率就是偵測延遲的上限，時刻本身與官方無關（R1 §4.3）。`cadence.weekday` 同逐球週跑落在休兵日；時刻與逐球週跑錯開，降低兩者撞鎖、其中一個整週跳過的機率（`scripts/weekly-box-revisions.sh` 檔頭）。
- **資源足跡**：取 refresh lock（忙碌即跳過，exit 75）；連本機 DB；連 www（Playwright）。
  - 正在忙的訊號：refresh lock；`logs/last-weekly-box-revisions.json`。
- **誰會看見失敗**：`schedule-watchdog`（`logs/schedule-history/com.cpbl.weekly-box-revisions.jsonl`）。registry 沒有 healthchecks 段。

### 1.4 `com.cpbl.schedule-watchdog`（缺席偵測）

- **registry 欄位**：`jobs[label=com.cpbl.schedule-watchdog].cadence`；plist 另有 RunAtLoad（registry `effective_from_evidence`）。
- **服務的事件**：判定其他登記 job「上一個週期跑了沒」。它判的是週期，不是時刻（`scripts/schedule_watch.py` 檔頭）。
- **選這個時刻的理由**：時刻不影響判定正確性，只決定「異常當天多久被看見」（R1 §4.4〔M10〕）。它不是用來等前面的排程跑完；若目標 job 仍在 running，依設計不指控，隔天再判。
- **資源足跡**：不取 refresh lock、不連 www、不連本機 DB（R1 §8）；讀 registry、plist、`launchctl`、狀態檔與歷史，送 macOS 通知。
  - 執行紀錄：`logs/schedule-watchdog/last-run.json`、`logs/schedule-history/com.cpbl.schedule-watchdog.jsonl`。
- **誰會看見失敗**：自己寫歷史供「開機了但偵測器沒跑」的自證；通知被專注模式擋下時，`logs/schedule-alert.json` 會印在每次 pytest header（registry `expected_installed_reason`）。

### 1.5 `com.cpbl.postseason-evening`（晚間鏈）

- **registry 欄位**：`jobs[label=com.cpbl.postseason-evening].cadence`（`kind=interval`，不做週期缺席判定）。
- **服務的事件**：A／E／C 有排定場的夜晚，官方完賽或新賽程要在同一晚反映到正式站（Runbook §10）。「一晚」的界線由 `postseason_evening.night_of` 決定，沿用 `DAILY_GUARD` 起點與 `BLOCK_RELEASE_AT`。
- **選這個時刻的理由**：固定間隔輪詢 stats，同步延遲主要由輪詢間隔構成。觀測：C 戰 stats 完賽在終場後約 3–6 分出現，正式站同步在終場後約 5–8 分完成（乾淨樣本 n=4，A 夜沒有樣本）（[R1](https://github.com/ruan6047/cpbl-analytics/blob/10148f5f8e0494871c1d6041e606e31dbd894f1c/docs/research/SCHED-TIMING-400/R1_schedule_timing.md) §3 E2〔M4〕、§4.5）。
- **資源足跡**：
  - `plan → quiet`（沒有排定場也沒有待辦）：不寫狀態檔、不連 DB、不連 stats、不取鎖，只短暫啟動一次 `uv run python -m cpbl.ingest.postseason_evening plan`（R1 §4.5；`scripts/postseason-evening.sh` 檔頭）。
  - 有事時：plan 連本機 DB 與 stats，不取鎖；www 抓取與同步步驟取 refresh lock、寫正式站（R1 §8）。進入 `DAILY_GUARD` 時段讓位每日鏈。
  - 正在忙的訊號：refresh lock；`logs/last-postseason-evening.json`、`logs/postseason-evening-state.json`。⚠️ 以「有沒有 postseason_evening 程序」判斷會誤命中 quiet 的短暫程序，前置核對以 lock 檔與狀態檔為準（PLAN O2、O4(a)）。
- **誰會看見失敗**：healthchecks check `evening`（由 alert-watch 武裝，見 1.6）；`schedule-watchdog` 只讀狀態檔的 `halted` 報 FAILED。

### 1.6 `com.cpbl.alert-watch`（本機告警 watcher）

- **registry 欄位**：`jobs[label=com.cpbl.alert-watch].cadence`；`.alert`（check `services`：`.alert.interval_seconds`、`.alert.confirmations`）；`.evening_alert`（check `evening`：`.evening_alert.deadline_after_start_minutes`、`.evening_alert.fallback_deadline`）。
- **服務的事件**：本機服務（DB／redis 容器、Docker daemon）停擺偵測；晚間鏈的武裝、成功與 halted 告警（#358）。晚間期限＝今晚最晚一場開賽加 `.evening_alert.deadline_after_start_minutes`；開賽時刻解析不到時退回 `.evening_alert.fallback_deadline`（R1 §4.5）。
- **選這個時刻的理由**：固定間隔觀測；`services` 只有在 Mac 完全醒著、兩次觀測之間沒睡、連續確認時才送 `/fail`，所以 Mac 睡著不誤報（registry `.alert.note`）。
- **資源足跡**：不取 refresh lock、不連 DB、不動容器、不改晚間鏈檔（Runbook §11.2）；讀 `pmset`、`sysctl`、`docker inspect`，對 healthchecks 送 ping 與 Management API 請求。
  - 狀態：`logs/alert-watch/state.json`；`logs/launchd-alert-watch.out.log`。
- **誰會看見失敗**：watcher 本身沒裝或壞掉時沒有遠端訊號；`schedule-watchdog` 報 `JOB_NOT_INSTALLED`，Mac 整天沒醒則由 `daily` 的沉默告警涵蓋（Runbook §11.2 殘餘風險）。

---

## 2. 休季

休季的行為都來自動作條件與收官判定，不靠 bootout（registry `_readme`；#365）。收官判定只在 `src/cpbl/season_close.py`（#391），會一直維持到開季切回（#392）。

| 排程 | 休季行為 | 告警語意 |
|---|---|---|
| `com.cpbl.scrape-daily` | 兩軍都收官時日型不探 stats，依有無未同步寫入走 `sync_only` 或 `skip`；狀態照寫成功（R1 §4.1〔M2b〕） | skip 日照樣送 `daily` 成功 ping；skip 日的正式站可用性回報由 #398 處理 |
| `com.cpbl.weekly-game-pitches` | 已收官的 kind 略過，狀態照寫成功（`scripts/weekly-game-pitches.sh`；依程式碼推論，尚無休季週期的實測，R1 §4.2、G1） | 照常寫歷史，watchdog 不會報缺席 |
| `com.cpbl.weekly-box-revisions` | 同上；深抓窗在二軍結束後已經空了（R1 §4.3〔M9〕、G1） | 同上 |
| `com.cpbl.schedule-watchdog` | 照常執行；skip 日照寫歷史，判定仍有意義（R1 §4.4） | 同賽季 |
| `com.cpbl.postseason-evening` | 每次喚醒都是 `plan → quiet`；Mac 整天醒著時的喚醒次數見 R1 §4.5〔M11〕；單次 quiet 的成本未量（G8） | 沒有排定場就沒有期限，`evening` 不武裝 |
| `com.cpbl.alert-watch` | 只送 `services` 心跳；evening 段不啟動（R1 §4.6〔M12〕） | 語意正確：服務心跳全年都該有 |

休季要人工指示更新時，依 Runbook §3〈聯盟收官〉的寫法（`DAILY_FORCE_FULL=1`、`CPBL_SEASON_CLOSE=open`），本文件不另寫指令。

---

## 3. 隱含耦合（改時刻或搬遷時必須一起改）

每日鏈的時刻至少和以下幾處耦合，改其中一處就要在同一個變更裡改其他處（PLAN O5）：

- plist `scripts/com.cpbl.scrape-daily.plist` 的 `StartCalendarInterval`（`schedule_watch.py` 會逐欄比對，不一致即 `REGISTRY_INVALID`）。
- registry `jobs[label=com.cpbl.scrape-daily].cadence`、`.alert.schedule`、`.alert.grace_minutes`、`.alert.deadline`。
- healthchecks 服務端的 `daily` 排程與 grace（需求方在 SaaS 端設定，本機核對不到；registry `.alert.note`）。
- `src/cpbl/ingest/postseason_evening.py::DAILY_GUARD`（晚間鏈讓位每日鏈的時段；它的起點也是 `night_of` 的「一晚」終點）。
- `scripts/alert_watch.py::NIGHT_START`（alert-watch 的「今晚」起點）。
- `scripts/refresh_status.py` 的 `check --deadline` 預設值（`check --scheduled` 判「今日排程未觸發」的期限）。

其他兩兩對應、要一起改的位置：

- 晚間告警期限：registry `.evening_alert.deadline_after_start_minutes`、`.evening_alert.fallback_deadline` 與 `scripts/alert_watch.py::EVENING_GRACE`、`FALLBACK_DEADLINE`。
- 兩個週跑：registry 各自的 `cadence` 與各自 plist 的 `StartCalendarInterval`；兩者的相對間隔是 box 週跑檔頭寫明的設計前提。
- 各腳本檔頭註解也寫了時刻（例：`scripts/weekly-box-revisions.sh`、`scripts/weekly-game-pitches.sh`）。不影響行為，但改時刻時要一起修，避免讀者被舊註解誤導。

registry 以外的程式內時窗（行為規格，不在 registry；Runbook §10 保留原文）：

- `src/cpbl/ingest/postseason_evening.py`：`DAILY_GUARD`、`BLOCK_RELEASE_AT`、`night_of`。
- `scripts/alert_watch.py`：`NIGHT_START`、`EVENING_GRACE`、`FALLBACK_DEADLINE`。
- `src/cpbl/ingest/starter_watch.py`：`FIRE_AT`、`FIRE_END`（#342 先發時點；旗標預設關）。
- `src/cpbl/ingest/starter_checkpoints.py`：`POINTS`、`RETRY_AFTER`（#292 先發查核；旗標預設關）。

---

## 4. 任務要不要等排程

原則：需求方已裁定「不要等排程時間」（[#344 6360646281](https://github.com/ruan6047/cpbl-analytics/issues/344#issuecomment-6360646281)）。R2 的等時刻型案例中，多數等的是每日鏈（R2 §3.2-1）；需求方多次以「沒比賽、資料不會變」質疑休季時的等待（R2 §3.3）。

**手動等價入口**（只引用 Runbook 現有寫法，本文件不新增指令）：

- 每日鏈：Runbook §3〈本機每日爬取〉的手動 fallback（直接跑 `scripts/scrape-daily.sh`，預設 `trigger=manual`）與 `launchctl kickstart -k gui/$(id -u)/com.cpbl.scrape-daily`；只差同步時依同節改用 `SKIP_SCRAPE=1` 的重試寫法。
- 兩個週跑：Runbook §3 各節的 `launchctl kickstart -k`。
- 晚間鏈、watchdog、alert-watch：Runbook 沒有列手動觸發入口，本文件不新增。

**手動觸發仍要遵守**：

- 資源租用：本機 DB、服務、排程都是共用資源（`.wf/cpbl-local.md`〈工作樹與共用資源〉）。
- 爬蟲紅線：失敗勿連續重跑，先冷卻再單次重試（CLAUDE.md〈爬蟲紅線〉；Runbook §3）。
- 日型閘門：手動觸發每日鏈同樣先判日型，skip 日只會跳過；休季要強制完整鏈須依 Runbook §3〈聯盟收官〉。
- 手動 fallback 不送 healthchecks `daily` ping（Runbook §11.1），驗收若需要外部告警的證據，要另外說明。

**只有以下情形才需要等排程**：

1. 驗收本身就是「排程自然執行後仍然正確」。
2. 步驟只由某條排程鏈執行（例：生產 migration、建置或同步由每日鏈套用）。這時要的是「那條鏈跑一次」，不是「等到那個時刻」；能不能以手動觸發同一條鏈代替，依該卡授權決定（R2 B3 即由需求方改成手動 kickstart）。

**判斷「排程正在忙」**：用 §1 各排程的「正在忙的訊號」（refresh lock、狀態檔 `state`），不要用固定時段。共同主 PM 窗口規則中的固定時段在避什麼，待共同主 PM 說明（[#400 裁定 D2](https://github.com/ruan6047/cpbl-analytics/issues/400#issuecomment-6543888486)）；本文件不改協調規則。

---

## 5. 未納入 launchd 的現況（只標記，不分析）

- VPS 的 `prod_cpbl_live_worker`：常駐容器，休季行為未查。
- `config/launchd/com.cpbl.lineup-announcements.plist`：未安裝，registry 沒有登記。
- 樹莓派取源（#393 WP3）：實測中，沒有排程。

---

## 6. 合理性結論與證據

2026 季 Mac 現行排程的合理性結論（賽季、休季分開，有日期的快照）見 [`docs/research/SCHED-TIMING-400/CONCLUSIONS.md`](research/SCHED-TIMING-400/CONCLUSIONS.md)。證據見 §0 列出的 R1、R2 固定版本。#393 搬遷後改寫本文件時，該結論檔保留為歷史快照，不跟著改。

---

## 7. 最後核對

- 日期：2026-10-31（#400 執行階段）。
- registry git blob：`47762ab8c5c91f09f97d90f61ed340cc05b5651a`（`git rev-parse HEAD:scripts/schedule-registry.json`）。registry 改版後，請重新核對 §1 的欄位路徑仍存在，並更新本節。
