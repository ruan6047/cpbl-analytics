# UX-LIVE-TRACKMAN1 賽中逐球 TrackMan 顯示〔T3；⚪使用者可見功能〕

- 需求：ruan6047　規劃：OpenAI Codex　分支：`ai/<執行者>/UX-LIVE-TRACKMAN1`
- 執行：待指派（建議 L3；需同時維護 live 資料契約、來源不完整退化與既有賽況 UI）　查核：待指派（建議 L2；獨立 contract／瀏覽器查核，須 ≠ 執行）
- review_independence: [context]
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2、LIVE_GAME_PRODUCT_SPEC v1.1（Design Gate 核可後需更新 live TrackMan 邊界）
- DB：`db_scope: none`；只改既有 Redis canonical snapshot、API 疊加與前端呈現，不新增 PostgreSQL 寫入或 migration
- 部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：既有 `/games/[sno]` 的 live snapshot、逐打席區與分析區；保留官方已回傳的 TrackMan，資料存在時顯示，缺值時誠實退化。不新增直播頁、推播、逐球時間戳或守備員追蹤。
- Discovery：2026-08-01 需求方指示查核；官方進行中抽樣 `2026-A-235=127/148`、`2026-A-236=54/54`、`2026-A-237=0/59` 筆含 TrackMan。現有 worker 已取得原始 payload，但 `_LIVELOG_FIELDS` 丟棄 `Trackman`；前端非 final 時強制 `has_tracking=false`。
- Design：✅需求方於 2026-08-02 核可。唯一賽況頁 `/games/[sno]` 共用標準化逐球契約：賽中 Redis snapshot 為暫態權威、賽後 PostgreSQL 為可追溯權威。資料無法唯一映射打席即不渲染；同打席來源鎖定，模型資料不完整則整個打席降階為官方粗分類。逐球介面同步升級 live 與賽後：好球帶、判決、球種、球速，擊出球可展開初速／仰角／距離／滯空時間／擊球轉速；不做整場落點圖、推播、OAA 或賽中勝率。
- owner、worktree、iteration、最後交接、阻塞與交付／部署 current-state 見 [`../TASKS.md`](../TASKS.md) Ledger；歷史寫入 adapter event log

## 問題陳述

官方進階站在部分賽中場次已提供逐球 TrackMan [TrackMan]：球種、球速、轉速、進壘位置，以及擊球後的初速、仰角、飛行距離、滯空時間、擊球轉速與落點方位。現有 live worker 雖已擷取原始單場 payload，卻只保留文字事件；前端也一律隱藏賽中逐球視圖。因此資料已可用時，使用者仍只能看到文字賽況。

來源覆蓋並不一致：同一時段的進行中場次可為完整、部分或 0 筆 TrackMan。任何設計都必須以「每一球的實際 payload」判定可用性，不能以 `SkipTrackman=false` 或比賽狀態推斷。

## 決策（Design Gate 必答）

1. 建議在既有「逐打席」右側對戰卡中，僅於當前打席已有 TrackMan 球時顯示好球帶與逐球列表；列表顯示球數、判決、球種、球速，並可在擊球球上展開初速、仰角、距離、滯空時間與擊球轉速。
2. 建議分析頁的擊球落點圖在 live 時可增量顯示已到達的 InPlay 資料；未到達資料不畫、不以 0 補值，並維持「資料持續更新」提示。
3. 候選 UI 不顯示逐球時間、打席耗時、守備員位置／移動或 OAA [Outs Above Average]；官方 payload 未提供足以支持這些結論的資料。
4. payload 可能在後續 polling 補齊或修訂：採最新 official snapshot 覆蓋同一事件；event_count、tracking_count 或 source version 改變均重新取得完整 payload。stale／source error 保留 last-known-good 並停止宣稱即時。

## 驗收條件

- [ ] worker 的 canonical snapshot 以 additive、向後相容形式保存每筆 live event 的 TrackMan 必要欄位；資料缺失維持 `null`／缺欄，不得以 `0`、推算值或 `SkipTrackman=false` 補齊。
- [ ] `/games/[sno]` 在 live 時依實際逐球資料顯示好球帶、球種、球速與可用的擊球／落點資訊；TrackMan 為空的場次仍正常呈現比分、壘包、球數與文字事件，沒有空好球帶或「無設備」假結論。
- [ ] `hit_hang_time`、`hit_distance`、`hit_spin_rate`、落地方位與可信度的語意與既有 `cpbl.pitch_tracking` 一致；live 資料只作即時呈現，正式 PostgreSQL 回填仍走既有完成賽流程。
- [ ] 前端只向本站 API polling，不新增 browser 對官方站的請求；前景／背景／final／stale 行為維持既有 live polling 契約。
- [ ] 既有無 TrackMan、舊 Redis snapshot、`Trackman=null` 的非投球事件、換投／代打與同局重複投打對戰均不錯配、不拋錯。

## 驗證

- [ ] 以真實官方 payload fixture 覆蓋：live 有 TrackMan、live 全空、同場部分可用、擊球資料不完整、舊 snapshot 無新欄位、stale／source error；禁止以手寫欄位名 mock 取代來源 key。
- [ ] 先跑紅：還原 worker 對 `Trackman` 的濾除或前端 live 強制關閉時，新的 contract／component 測試必須失敗；修正後轉綠。
- [ ] 瀏覽器在 375px、768px、1440px 驗證有資料與無資料兩種場次；鍵盤可操作、`aria-live` 不因逐球更新過度播報、無水平溢出。
- [ ] `uv run ruff check`、`uv run pytest`、`cd web && npm test`、`npx tsc --noEmit`、`npm run build:check`、`git diff --check` 全數通過。
- [ ] production 驗證選一場 live 有 TrackMan 與一場 live 0 筆 TrackMan，記錄 snapshot 的 event／tracking count、畫面行為與 polling network evidence；不得只以完賽回填資料代替。

## 邊界與依賴

- 依賴：`LIVE-SNAPSHOT-FIELDS1` 已部署並以 production 實測確認 worker／web 使用相同 canonical snapshot 版本；若 live worker 尚未可用，不得以 browser 直連官方站繞過。
- 需在實作前更新或以 Design Gate 明確覆寫 `LIVE_GAME_PRODUCT_SPEC v1.1`「賽中不呈現 TrackMan」的既有產品邊界；未核可不得 claim。
- 不修改 `cpbl.pitch_tracking` schema、既有完賽爬取／回填、賽後逐打席 canonical `pa_id`，也不把 live 的近似投打配對宣稱為賽後精確 mapping。
- 不做逐球時間／節奏分析、守備員追蹤、OAA、賽中勝率或新的即時外部請求基礎設施。

## Log

- 2026-08-01T17:46:02+08:00 register by OpenAI Codex（依 ruan6047 指示）：官方 live payload 實測已證明部分進行中場次有 TrackMan，但覆蓋不穩定；先以 Backlog 卡保留可驗證範圍，等待需求方 Design Gate。
- 2026-08-02T12:32:41+08:00 correction by Claude Opus 5@Claude Code（依 ruan6047 指示修 CI 紅燈）：`spec 基線` 欄補上父卡 `INIT-PRODUCT-UX` 的當前版本 `PRODUCT_UX_BLUEPRINT v0.2`。父卡卡面與 `PRODUCT_UX_BLUEPRINT.md` 檔頂皆為 v0.2、未曾推進，故屬 baseline-cascade §5 註冊時漏填而非基線變更；範圍、決策與驗收條件不變。詳見 `CORRECTION-002`。
- 2026-08-02T13:38:04+08:00 Design Gate：需求方核可。核可內容以本卡 Design 行為準；賽中／賽後採同一賽況頁與元件，資料成熟度透過使用者語意揭露（不暴露儲存實作）。官方修訂直接覆蓋；螢幕閱讀器只播報狀態變更、不逐球播報。自家即時球種模型另列後續 T4 卡，不阻塞本卡先以官方 `TaggedPitchType` 粗分類上線。
