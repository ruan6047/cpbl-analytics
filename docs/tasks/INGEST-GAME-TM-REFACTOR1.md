# INGEST-GAME-TM-REFACTOR1 爬蟲管線重構：重構逐球爬蟲改以單場 API 為單位〔T4；🔴資料正確性紅線〕

> **狀態 📦已合併（Gate 1–3）**：Gate 1–2（單場 API adapter＋共用 parser＋對帳工具）與
> Gate 3（隔離 shadow harness＋9 天觀測）皆已 merge，碼已在生產但**處於 dormant**——
> `run_refresh_recent.py` 仍是逐球唯一正式 writer。Gate 3 觀測窗已於 2026-08-03 收窗、
> 凍結解除。**cutover 不在本卡**，由
> [`INGEST-GAME-TM-REFACTOR1-G4`](INGEST-GAME-TM-REFACTOR1-G4.md) 承接。

- 需求：ruan6047　規劃：待指派　分支：`ai/gpt-5-codex/INGEST-GAME-TM-REFACTOR1`（Gate 1–2）／`ai/sonnet-5/INGEST-GAME-TM-REFACTOR1-g3`（Gate 3）
- 執行：Gate 1–2 Claude Opus 4.8＋Gate 3 Claude Sonnet 5　查核：Gate 1–2 Gemini／Gate 3 Antigravity（Gemini 3.6 Flash），均跨家族
- worktree：`.claude/worktrees/ingest-game-tm-refactor1-g3-execution`（Gate 3）
- Initiative：`INIT-OFFICIAL-DATA1`　spec 基線：[`../research/OFFICIAL_DATA_GAP1_RESULTS.md`](../research/OFFICIAL_DATA_GAP1_RESULTS.md) §3.4
- DB：`db_scope: write`（實作階段：寫入 `cpbl.pitch_tracking`）　部署：是　環境：production

## 背景

我們在深層 API Payload 實測中發現，已完賽場次（如 2026-A-99）在官方進階站單場端點 `/api/proxy/v1/games/{year}-{kind}-{sno}` 中，其 `LiveLog` 陣列內部依然**保留著完整的 `Trackman` 逐球數據**（實測覆蓋率達 92.7%）。
現行的 `cpbl_pitch_tracking.py` 和 `run_refresh_recent.py` 是以「投手個人 acnt」為維度去請求其全賽季 logs API，這會導致以下工程缺陷：
1.  **API 請求次數極大**：每天更新近期賽事時，需為兩隊上場的所有投手分別呼叫一次 API。
2.  **漏損漏洞**：若投手在當日完賽後被下放二軍、改名（如象魔力改魔力藍）、或被註銷，個人 logs 爬取極易發生 acnt 對帳漏損，造成逐球數據永久缺漏。

## 目標

- **爬蟲管線重構**：
  重寫或擴充 `cpbl_pitch_tracking.py`，新增以比賽（`year, kind_code, game_sno`）為單位的爬取方法。直接打單場 API `/api/proxy/v1/games/{year}-{kind}-{sno}`，解析其中 `LiveLog` 內的所有 `Trackman` 逐球數據並進行 UPSERT。
- **共用 parser 契約**：
  個人 logs 與單場 API 必須共用同一個 pure parser；先合併 `INGEST-DEEP-TRACKMAN1` 的完整欄位契約，避免兩條 fetch path 各自維護欄位映射。
- **賽程來源影子對帳**：
  使用 `/api/proxy/v1/games/schedule?kindCode=&year=&month=` 保存原始 `GameStatus` 與 `SkipTrackman`，但 `SkipTrackman=false` 不得映射成 tracking available／complete。
- **刷新管線重構**：
  修改 `run_refresh_recent.py`，將近期逐球數據的刷新邏輯改為「以單場 ID 為單位」進行請求，替代原先的「以當日出賽投手為單位」之邏輯。
- **效能優化**：
  確認重構後可降低 80% 以上的 API 請求次數，並完全消除因球員名冊異動導致的逐球漏爬風險。

## 實作前提

1.  **數據無縫對接**：
    重構後的單場 API 寫入，其入庫欄位與 schema 必須與既有的 `cpbl.pitch_tracking` 完美對接（包含 PK `year, kind_code, game_sno, pitcher_acnt, pitch_cnt`），不可產生資料庫衝突或欄位損毀。
2.  **不破壞無設備球場語意**：
    若單場 API 回傳之球場無 Trackman 設備（`Trackman=null`），維持既有語意，直接不收或略過。
3.  **不直接切換 canonical schedule**：
    至少 30 場逐列等價對帳＋14 天 shadow run；延期、保留賽、0–0 與場次 ID 未全過前，主站仍是比分／事件語意 canonical。

## 非目標

- **不開發即時 LiveGame 管線**：本卡僅針對完賽後的增量刷新與歷史回填，不涉及即時逐球直播頁面（LiveGame）的開發。

## Gate 與驗證

- **Plan Gate**：
  確認重構後的解析程式在 `pytest` 單元測試中，對已完賽場次能正確還原出與投手 Logs 相同數量的逐球列（進行數據等價性核對）。
- **驗證方案**：
  *   對帳：利用 2026-A-99 等場次，比較舊版投手 logs 爬取出的 Rows 數量與新版單場 API 爬取出的 Rows 數量，確認完全一致（差額數為 0 或僅為無設備事件）。
- **T3 查核**：
  通過 `ruff check` 與 `pytest`，並在本機測試跑一次 `run_refresh_recent.py`，監測 httpx 請求次數的減少幅度與回應時間。

## Log

- 2026-07-21 由 `ruan6047` 指示正式註冊為 📥Backlog。
- 2026-07-22 官網缺口稽核修訂：加入共用 parser、schedule shadow 與 `SkipTrackman` 單向語意；納入 `INIT-OFFICIAL-DATA1`。
- 2026-07-22 流程勘誤：本卡切換官方逐球寫入來源，屬資料正確性紅線，依 canonical 由 T3 升為 T4。
- 2026-07-24 iteration 1（Gate 1–2）跨家族 review APPROVE 於 `931df9f`（Gemini），`--no-ff` merge `887a8c7`。新增能力：`cpbl_pitch_tracking.scrape_game_pitches`＋CLI `cpbl-scrape-game-pitches`＋`scripts/reconcile_game_tm.py`；與逐投手 logs 共用 pure parser `parse_pitches`。**不觸碰正式 writer 與 `pitch_tracking` schema**（紅線守衛：`run_refresh_recent.py` 對 main 的 diff 為空）。
- 2026-07-24 iteration 2（Gate 3）跨家族 review APPROVE 於 `1922292`（Antigravity／Gemini 3.6 Flash），`--no-ff` merge `a3bbb2c`。新增能力：migration 065 四張隔離 `cpbl.game_tm_shadow_*` 表＋`game_tm_shadow.py`＋CLI `cpbl-shadow-game-tm`；shadow 只 import 既有 parser／fetch，現行投手維度爬蟲仍為唯一正式 writer。設計與對帳基準見 [`../research/GAME_TM_SHADOW_OBSERVATION.md`](../research/GAME_TM_SHADOW_OBSERVATION.md)。
- 2026-07-29 碼隨主站 submodule bump `b974b10` → `537d7f7` 進入生產（非該次部署新增，`1922292` 早已在生產）；因未 cutover，生產行為不變。
- 2026-08-03 需求方裁示 Gate 3 觀測窗於**第 9 天**（`run_id=14`）提前結案、凍結範圍解除。原 14 天為寫卡時無理由的保守預設；第 3 天後未再出現新種類差異，資訊增益歸零。晉升條件 1–3 達成（12 次 run 非零差異全數收斂為兩類良性模式、**無任何一筆物理欄位不一致**；延期／保留／未開打分支改以全季 320 筆賽程回放窮舉取證）。詳見 shadow 文件 §3.2 與 §5。
- 2026-08-03 條件 4（cutover＋跨家族查核＋需求方 production sign-off）另開 [`INGEST-GAME-TM-REFACTOR1-G4`](INGEST-GAME-TM-REFACTOR1-G4.md) 承接，本卡不再擴充範圍。
