# OPS-POSTGAME-OBSERVE1 完賽正式資料發布延遲觀測〔T2；⚪一般〕

- review_independence: `context`
- 需求：ruan6047（2026-08-03 會話裁定）　規劃：GPT-5@Codex　分支：依認領時 worktree 慣例
- 執行：待指派（建議 L2；官方端點量測與證據整理）　查核：待指派（新 context；≠ 執行）
- Initiative：—　spec 基線：—
- DB：`db_scope: read`（本機／production 唯讀證據；不得寫入 `cpbl` schema）
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍：唯讀觀測，於此簡述。
- Discovery：—（T2）
- Design：Design Gate N/A（只量測既有官方資料的可用時間，不改產品、排程或寫入行為）
- owner、worktree、iteration、最後交接、阻塞與交付／部署 current-state 見 [`../TASKS.md`](../TASKS.md) Ledger；歷史寫入 adapter event log。

## 背景

2026-08-02 的 238 場在官方標示完賽後，live snapshot 已有 7:0、327 個事件與 MVP，
但勝／敗投、救援投手與 PostgreSQL 的賽後 box／livelog 尚未到齊。現行本機每日 refresh
於 10:10 執行；若要縮短賽後資料空窗，不能臆測官方延遲，也不能以密集重試碰撞官網反爬。

本卡先量測正式來源在「官方完賽」後各欄位實際首次可用的延遲，為
`INGEST-POSTGAME-FINALIZE1` 的觸發與退避策略提供基線。

## 驗收條件

- [ ] 對至少 10 場不同完賽比賽做唯讀觀測；從官方首次回報 final 的時間開始，在 t=0、2、5、10、15、20、30 分鐘取樣。每個來源／欄位在每個樣本點至多請求一次，不得以輪詢替代既有 live worker。
- [ ] 每個樣本記錄絕對時間、比賽識別、來源回應狀態，以及 final 比分、逐打席終局事件、打擊 box、投球 box、勝投、敗投與救援投手的可用性；和局／無救援情境須明確標為「不適用」，不可誤判缺資料。
- [ ] 產出可重跑的觀測程式與結果報告，至少含各欄位首次可用時間、樣本數、p50／p95、失敗或異常回應；結果檔置於 `docs/research/OPS-POSTGAME-OBSERVE1_RESULTS.md`。
- [ ] 以實測結果提出有限、低頻的候選重試節點與停止條件；不得在報告完成前改動 `cpbl-refresh-recent`、launchd、production 同步或任何正式資料表。

## 驗證

- [ ] 離線測試涵蓋時間戳與「可用／不適用／缺失」判定，並確認程式不會執行寫入 SQL。
- [ ] 以真實完賽場次完成至少 10 個樣本的結果報告；列出請求數與來源錯誤，證明未超過本卡取樣預算。
- [ ] `uv run ruff check` 與相關 `uv run pytest` 全綠；`git diff --check` 乾淨。

## 邊界與依賴

- 不補抓、不回填、不修改前端空態，也不修改每日 refresh 鏈；這些屬後續卡。
- 不從 VPS 爬取官網；遵守 `docs/AI_RUNBOOK.md` 的本機爬取與冷卻紀律。
- 此卡可與 `INGEST-PA-DAILY1` 的 TM Gate3 觀測窗並行，因為不碰其 refresh 資源。
- `INGEST-POSTGAME-FINALIZE1` 不得在本卡結果完成並經需求方 Design Gate 核可前 claim。

## Log

- 2026-08-03 依 ruan6047 指示註冊；尚未 claim，先以觀測決定賽後補抓門檻。
