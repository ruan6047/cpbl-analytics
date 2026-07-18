# OPS-REMOTE-CRAWL1 遠端無人值守 crawler Discovery umbrella 〔T3；🔴外部服務／維運〕

- 需求：ruan6047　規劃：待指派　分支：`ai/<執行者>/OPS-REMOTE-CRAWL1`
- 執行：待指派　查核：待指派（須 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2
- DB：`db_scope: none`；不得讀寫 local／production DB
- 部署：否　環境：local＋VPS（僅經明確授權執行 probe）　PR：—　Merge SHA：—
- 範圍：見 [`../discovery/OPS-REMOTE-CRAWL1.md`](../discovery/OPS-REMOTE-CRAWL1.md)
- Discovery：[`../discovery/OPS-REMOTE-CRAWL1.md`](../discovery/OPS-REMOTE-CRAWL1.md)；需求方 2026-07-18 確認
- Design：Design Gate N/A；純技術網路可行性研究，不改使用者流程或公開介面
- owner、worktree、iteration、最後交接、阻塞與交付／部署 current-state 見 [`../TASKS.md`](../TASKS.md) Ledger；歷史寫入 adapter event log

## 目標與驗收

- [x] 核可安全 probe contract：opt-in、allowlist、單次請求、零 retry、零 DB、sanitized JSON；
  實作切到 `OPS-REMOTE-PROBE1`，本卡不直接寫 probe code。→ [`../discovery/OPS-REMOTE-CRAWL1_CONTRACTS.md`](../discovery/OPS-REMOTE-CRAWL1_CONTRACTS.md) §1
- [x] 核可候選路線、跨時窗取樣、冷卻／停止條件與證據強度；比較執行切到
  `OPS-REMOTE-ROUTE1`，任何 live probe 仍需 Coordinator 明確授權。→ §2
- [x] 以 Discovery Gate 決定是否允許隔離 shadow worker；未取得明確 GO＋需求方 sign-off，
  `OPS-REMOTE-WORKER1` 與 `OPS-REMOTE-CUTOVER1` 均不得 claim。→ §3：建議 HOLD，待需求方 sign-off。
- [x] 不部署遠端排程、不繞過 challenge、不採購代理、不修改 production 資料管線。→ §0、§4 紅線。

## 驗證與依賴

- 驗證：Discovery brief、probe schema／威脅邊界、候選路線與停止條件經獨立 T3 查核；
  程式與 live evidence 由各子卡負責。
- 依賴：OPS-REFRESH1 通過 T4 source review；live VPS probe 另需 Coordinator 明確授權。
- 研究計畫：[`../research/OPS-REMOTE-CRAWL1_PLAN.md`](../research/OPS-REMOTE-CRAWL1_PLAN.md)
- 預估範圍：S（umbrella／Gate）；執行拆為 `OPS-REMOTE-PROBE1 → OPS-REMOTE-ROUTE1 →
  OPS-REMOTE-WORKER1 → OPS-REMOTE-CUTOVER1`，跨卡計畫見
  [`../../ops-remote-crawler-rollout.md`](../../ops-remote-crawler-rollout.md)。

## Log

- 2026-07-18 註冊：OPS-REFRESH1 固定 SHA `38040bb` 已獲 Claude Sonnet 5 T4 APPROVE；
  依需求方指示另開 Discovery，不回頭修改已核准 source。
- 2026-07-18 規劃更新：需求方要求分階段推進並先留安全 DEBUG 介面；本卡改為 Discovery
  umbrella，新增四張依賴式子卡，禁止從 probe 直接跳到 production。
- 2026-07-19 執行（Claude Opus 4.8@Claude Code）：依需求方指示「可以依據規範執行」claim
  （`OPS-REMOTE-CRAWL1-CLAIM-003`, sv=3）。交付 [`../discovery/OPS-REMOTE-CRAWL1_CONTRACTS.md`](../discovery/OPS-REMOTE-CRAWL1_CONTRACTS.md)：
  probe 安全契約（§1）、路線／取樣／停止條件／證據強度（§2）、Discovery Gate 決策（§3，PROBE1 GO／
  ROUTE1 條件 GO／WORKER1・CUTOVER1 HOLD 待需求方 sign-off）。待 ≠ 執行者之獨立 T3 查核。
- 2026-07-19 併發註記：claim 當下與另一 agent（GPT-5@Codex）同秒寫 `events.jsonl`，我 append 的
  `CLAIM-003` 被對方 `git add docs/control-plane/events.jsonl` 夾帶進其提交 `8775a8a`（editorial claim）。
  事件內容、TASKS.md 投影與 `--check` 均正確且已上 origin；provenance 由事件 actor／evidence 欄與本 Log
  補記。屬 [[shared-main-checkout-discipline]] 所警示的逐檔 add 掃檔失誤，非資料錯誤。
