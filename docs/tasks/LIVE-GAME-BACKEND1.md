# LIVE-GAME-BACKEND1 賽前情報與比賽中 live backend 〔T4；🔴資料正確性／production worker〕

- 需求：ruan6047　規劃：GPT-5.6@Codex　分支：`ai/<執行者>/LIVE-GAME-BACKEND1`
- 執行：待指派（建議 L3；跨來源時序觀測、production polling 與 fail-closed contract）　查核：待指派（L3；須跨模型家族或人工，且 ≠ 執行）
- review_independence: [cross_family_or_human]
- Initiative：INIT-OFFICIAL-DATA1　spec 基線：v1
- DB：`db_scope: write`；`db_namespace: LIVE-GAME-BACKEND1`；`db_resources: db:test:cpbl, cache:live-game`；`migration_phase: none`
- 部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：見 [`../LIVE_GAME_PRODUCT_SPEC.md`](../LIVE_GAME_PRODUCT_SPEC.md) §2–§4、§7
- Discovery：[`../LIVE_GAME_PRODUCT_SPEC.md`](../LIVE_GAME_PRODUCT_SPEC.md) §1–§2；需求方 2026-07-26 確認問題、前後端分卡與三段資料時序
- Design：Design Gate N/A；本卡為內部 ingestion／cache／API，但 public contract 定稿須與 `UX-LIVE-GAME1` Design Brief 對齊
- owner、worktree、iteration、最後交接、阻塞與 current-state 見 [`../TASKS.md`](../TASKS.md) Ledger

## 驗收條件

- [ ] 以至少三場一軍例行賽完成 T-30h／T-90m／T-60m／T-30m／START 觀測矩陣，確認預告先發、先發棒次／守位的 exact key path、逐隊 partial 語意與首次出現時間；時間窗口只能加密觀測，不能替代來源事實。
- [ ] 單一 production worker 由 stats 可連來源建立 canonical snapshot：具互斥、kill switch、jitter／backoff／request budget、last-known-good＋stale；`START` 以 10–15 秒為候選頻率，瀏覽器不得直打官方站，VPS 不得依賴回 404 的 `www`。
- [ ] 既有 status／live API 以 additive contract 回 canonical phase、raw status、兩隊預告先發與 lineup availability、freshness 與 TrackMan availability；`START`、延期、保留、未知狀態及來源錯誤均 fail closed，final 後停止 polling 並接回既有賽後完整抓取／對帳。

## 紅線（違反即退回）

- [ ] 不以比分是否非 0 判斷 `live`／`final`，不把未知 raw status 映射為 final。
- [ ] 不把 T-24h／T-60m 當公布保證；空陣列、null、partial、source error、stale 必須可區分，未知不得補成 0 或猜測球員。
- [ ] `SkipTrackman=false` 不得映射成 TrackMan available；賽中 0 筆不得映射成 no-equipment。
- [ ] 本卡不得新增 migration；若現有資料結構不足，先停下並另開 additive schema 卡。

## 驗證

- [ ] parser／state machine contract tests 覆蓋 `SCHEDULED → probable partial/full → lineup partial/full → START → FINISHED`、延期／保留、未知狀態、空陣列、schema drift、stale 與來源恢復。
- [ ] worker integration tests 證明單例鎖、停機、重啟續接、backoff、request budget、final 停止輪詢與不重複寫入；使用 `LIVE-GAME-BACKEND1` 隔離 DB/cache namespace。
- [ ] 至少一場真實 live shadow canary，留下兩次以上事件單調增加、stats vs 官方頁抽樣一致、VPS HTTP/latency、來源流量與 TrackMan 0 筆語意證據；不得用完賽 fixture 冒充 live 證據。
- [ ] `uv run ruff check`、`uv run pytest`、API route snapshot、fresh DB rehearsal 與 production kill-switch smoke test 通過；T4 查核者重跑狀態矩陣與 live canary。

## 依賴與範圍

- 可沿用 `INGEST-GAME-TM-REFACTOR1` 的單場 parser 與 `GAME-RECAP-STATUS1` 的 freshness 語意，但不得改寫其歷史資料契約。
- 與 `OPS-REMOTE-*` 的主站反爬路線分離；若預告先發只能由 `www` 取得，須先回到 Design Gate 決定 local relay，不得靜默擴張 production 權限。
- 完成 additive API contract 後才解除 `UX-LIVE-GAME1` claim 阻塞。

## Log

- 2026-07-26T17:29:30+08:00 register by GPT-5.6@Codex（依 ruan6047 指示開後端卡）。
