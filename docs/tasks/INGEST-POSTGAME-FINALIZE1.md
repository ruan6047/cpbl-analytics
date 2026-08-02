# INGEST-POSTGAME-FINALIZE1 依官方可用性補齊完賽資料〔T3；⚪一般〕

- review_independence: `cross_family_or_human`
- 需求：ruan6047（2026-08-03 會話裁定）　規劃：GPT-5@Codex　分支：依認領時 worktree 慣例
- 執行：待指派（建議 L3；ingest、排程與資料正確性）　查核：待指派（跨家族或人工；≠ 執行）
- Initiative：—　spec 基線：—
- DB：`db_scope: write`（本機既有 `cpbl` 比賽／box／逐打席資料的冪等 ingest；`migration_phase: none`）
- 部署：是　環境：本機排程＋既有 production 同步　PR：—　Merge SHA：—
- 範圍：依 [`OPS-POSTGAME-OBSERVE1`](OPS-POSTGAME-OBSERVE1.md) 的核可結果實作；不得先行假設延遲門檻。
- Discovery：`docs/research/OPS-POSTGAME-OBSERVE1_RESULTS.md`（完成後引用其實測 p50／p95、例外與建議節點）
- Design：待需求方核可（觸發條件、重試節點／上限、終止條件、suspended／和局策略與 production 同步範圍）
- owner、worktree、iteration、最後交接、阻塞與交付／部署 current-state 見 [`../TASKS.md`](../TASKS.md) Ledger；歷史寫入 adapter event log。

## 背景

每日 refresh 在上午執行，因此當日夜間完賽資料通常要到隔日才進 PostgreSQL。live snapshot
可先呈現比分與部分事件，但不是賽後可追溯的權威資料，且可能尚無勝敗投、救援、完整 box
或最終 official correction。需要一個受限、可觀測、以官方可用性為準的本機補齊機制。

這不是把 live snapshot 當賽後資料來源：賽後 PostgreSQL 仍須由既有官方逐場擷取器寫入，
並保留後續官方改判的冪等更新能力。

## 驗收條件

- [ ] 僅在官方回報 final 後將特定比賽放入本機補齊佇列；重試節點、最大等待時間與停止條件必須採用 `OPS-POSTGAME-OBSERVE1` 的核可實測結論，不得硬編 10／30／60 分鐘門檻。
- [ ] 每次嘗試只擷取該場既有官方正式資料來源，沿用既有參數化、冪等 upsert 與本機爬取規範；不得從 VPS 直接爬官網，也不得觸發整日或整季全量爬取。
- [ ] 完成判定至少要求 final 比分、逐打席終局資料與完整打擊／投球 box 已可寫入；非和局還須有勝投與敗投。救援投手只在官方應有時驗證，和局或無救援不得被判為缺失。
- [ ] 佇列須有單場去重與鎖定、可安全重跑、可觀測的嘗試紀錄；失敗不得中斷既有每日 refresh。資料仍不完整時維持 unknown／未就緒，不得猜測勝敗投或覆寫較新的官方資料。
- [ ] 完成後透過既有 production 同步流程同步必要資料表，並對帳本機／production 的場次、比分、決策與 box 完整度。
- [ ] 既有 `INGEST-PA-DAILY1` 的 TM Gate3 觀測窗與 refresh 資源衝突在 claim 時須先解決；窗內不得修改其既有 refresh 鏈。

## 驗證

- [ ] 以離線 fixture 測試佇列去重、退避、失敗隔離、和局／無救援與 unknown decision；確認不會在完成條件前宣稱賽後資料已就緒。
- [ ] 以真實完賽場次做一次端對端補齊與一次冪等重跑，保留官方回應時間、寫入筆數及完整度對帳證據。
- [ ] production 同步後以唯讀 API／DB 對帳，並在部署 handoff 中列出受影響表、重試政策與回滾方式。
- [ ] `uv run ruff check`、`uv run pytest`、相關 refresh 檢查與 `git diff --check` 全綠。

## 邊界與依賴

- **硬前置**：`OPS-POSTGAME-OBSERVE1` 結果已完成，且需求方已完成本卡 Design Gate；此前不可 claim。
- 不變更 canonical PA 的語意或把 PA build 偷渡進本卡；該責任仍在 `INGEST-PA-DAILY1`。
- 不以 UI 補字或推測處理 unknown decision；前端用詞修正若需進行，另開獨立卡以避免混入 ingest 排程風險。
- 不新增 migration，除非 Discovery 證明既有 `refresh_log` 無法承載最小可觀測性；若需 schema 變更，必須回到 Design Gate 補充核可。

## Log

- 2026-08-03 依 ruan6047 指示註冊；受唯讀觀測與 Design Gate 雙重前置，尚未 claim。
