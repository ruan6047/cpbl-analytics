---
schema_version: cpbl-incident-manifest/v1
---

# CPBL 事故 manifest

> 回應 `DOC-CPBL-ROADMAP1` R1 finding `CPBL-ROADMAP1-R1-03`：`docs/ROADMAP.md` 以真實事故
> 當論據，但引用的 runtime log 被 `logs/.gitignore` 排除，**在指定 `source_sha` 的唯讀
> worktree 中不存在**，查核者無法在受審快照裡重現。本檔記錄足以辨識與複核的錨點，
> **不提交完整 log**（runtime log 保持不入版控）。
>
> 每筆至少含：事件時間、原始檔保存位置與 SHA-256、關鍵退出碼／狀態。
> **本檔只記錄「事故發生過」的證據，不記錄「事故已修好」**——後者屬各卡的驗收。

## 為什麼 hash 而不是內容

log 含逐場抓取細節與 URL，體積大且每日產生；入版控會讓 repo 隨時間膨脹，且與
`logs/.gitignore` 的既有決定衝突。**SHA-256 讓「引用的是哪一份」可被驗證**——
持有原檔的人可自行比對，不持有的人至少知道自己缺什麼。

⚠️ **限制照實說**：hash 只證明「某人手上那份檔案與引用時相同」，**不證明檔案曾經存在於
任何共享位置**。原檔只在開發機。要更強的保證需要把 log 送到不可竄改的儲存，那超出本檔範圍。

---

## INC-2026-08-10-A｜每日 refresh 鏈硬失敗

- **時間**：2026-08-10 10:10 起跑，11:50:37+08:00 失敗結束
- **關鍵狀態**：`scrape exit=1`、`overall exit=1`
- **成因**：開發機當日網路中斷（`ERR_NETWORK_IO_SUSPENDED`／`ERR_NETWORK_CHANGED`／
  `Timeout 45000ms`），失敗於 `/team/fighting` 抓取
- **原始檔**：`logs/refresh-20260810-101000.log`（未入版控）
  - SHA-256：`bdee890aee5f706071b8c0d07dadf333caa0d89164e40d075804295aa440cae0`
  - 大小：7,879 bytes；mtime `2026-08-10T11:50:37+0800`
- **被誰引用**：`ROADMAP.md` §0 目標 2、附錄
- **相關卡**：`OPS-SCHEDULE-FAILURE-BLIND1`（#132）

## INC-2026-08-10-B｜週跑 box 深度重抓：31 場靜默漏抓而 exit 0

- **時間**：2026-08-10 14:11:35 起跑，14:32:17+08:00 結束
- **關鍵狀態**：`kind=A exit=1`（失敗於取 token 階段，硬失敗）；
  **`kind=D exit=0` 而該輪宣告 39 場、成功 8 場、失敗 31 場**（32 筆 `getlive 失敗` log 行、
  31 個相異 `sno`）；`overall exit=1` 僅因 A 段失敗
- **成因**：同 INC-2026-08-10-A 的網路中斷；`cpbl_gamelog.py:257` 的
  `except Exception` 將逐場失敗降為 `log.warning` 續抓，而結尾 `done:` 只計成功場，
  **不對帳函式第一行自己印出的目標場數**
- **資料後果**：31 場賽日 `2026-07-12`～`2026-08-09` 的賽後官方修正未進
  `cpbl.box_pitching_revisions`。其中 7 場（賽日 07-12～07-17）於下次週跑
  `2026-08-17` 時已掉出 `days_back=30` 窗
  - ⚠️ **「7 場」與「31 場皆未進快照」為 PM 自 log 推得，尚未逐場查證 DB**，
    已列為 `DATA-BOX-DEEP-SILENT-FAIL1`（#131）規劃階段的第一項待驗事實
- **原始檔**：
  - `logs/weekly-box-revisions-20260810-141135.log`（未入版控）
    SHA-256 `fc5a5c7429dbbf816ac719d20bb06419804c06c8ec34cf8b67f9c6e19b9ad227`，
    22,349 bytes，mtime `2026-08-10T14:32:17+0800`
  - `logs/last-weekly-box-revisions.json`（未入版控，狀態檔會被下次執行覆寫）
    SHA-256 `e4ca67091097ea875d3a56a86774bac20dc7c16d170733117bbe296dcc269548`，
    215 bytes，`{"result":"failed","exit_code":1,...}`
- **旁證**（獨立於 log，任何人可即時複核，但**只反映當下值、會被下次執行覆寫**）：
  `launchctl list com.cpbl.weekly-box-revisions` → `LastExitStatus = 256`（＝ exit 1）
- **被誰引用**：`ROADMAP.md` §0 目標 2、附錄
- **相關卡**：`DATA-BOX-DEEP-SILENT-FAIL1`（#131）、`OPS-SCHEDULE-FAILURE-BLIND1`（#132）

## INC-2026-08-13-A｜`2026/D/97` 續賽後 PA 衍生表未重建

- **時間**：賽事 2026-08-09 續賽完成；缺口於 2026-08-13 盤點時發現（歷時 4 日無人知）
- **關鍵狀態**：`games`／`pitching_gamelog`／`game_livelog` 均已自癒（比分 4:3 → 8:5、
  livelog 333 列），但 `cpbl.game_pa_events` 該場僅 **32 個相異 `pa_id`**
- **對照**：2026/A 近期完成場 livelog 245–305 列對應 65–84 個 PA；D/97 為 333 列對 32 個
- **非成因**：`run_refresh_recent.py:526` 已有 `_pa_build_step(..., include_farm=True)`，
  **不是未掛載**
- **原始檔**：無 log；證據為 DB 查詢，可即時重跑：

  ```sql
  SELECT count(DISTINCT pa_id) FROM cpbl.game_pa_events
   WHERE year=2026 AND kind_code='D' AND game_sno=97;
  ```

  ⚠️ **DB 會變**：補建之後此查詢即不再重現當時狀態。屆時以本條記錄為準。
- **被誰引用**：`ROADMAP.md` §1 L1、§3、附錄
- **相關卡**：**尚未開卡**

## INC-歷史｜本檔建立前的兩起，僅存二手記述

以下兩起被 `ROADMAP.md` §0 引用，但**本檔建立時已無可指認的原始檔**，故只記來源與限制，
**不得當成與上述三起同等強度的證據**：

- **分項重算誤計 83 筆／82 場**：來源為 `PA-SPLIT1` 卡的結案記述。錯誤已修復
  （`RECALC1`，`46aed5e`）。無本機 artifact 錨點。
- **逐球設備覆蓋告警響兩個半月無人讀**：來源為 `pitch-tracking-venue-coverage` 的記述
  （大巨蛋 06-02 起 15 場全零）。無本機 artifact 錨點。

## 維護

- **新增事故時**：由引用它的文件負責在此建檔，並在引用處指向 `INC-` 編號。
- **不得回填**：事故發生時沒留下的錨點，事後不得補造。無錨點就照上一節那樣標明。
- **hash 不得默默更新**：原始檔若被覆寫（例如狀態檔），**記下新 hash 並保留舊條目**，
  不要就地改掉——那會讓「引用的是哪一份」再次不可驗證。
