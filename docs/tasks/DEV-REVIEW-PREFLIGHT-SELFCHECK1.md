# DEV-REVIEW-PREFLIGHT-SELFCHECK1 派審前自檢交接前提〔T2；🟡工具〕

- 需求：ruan6047（2026-08-01 指示，列為優先項目）　規劃／執行：Claude Opus 5@Claude Code　查核：須 ≠ 執行
- review_independence: [cross_family_or_human]
- Initiative：—　spec 基線：`REVIEW_GATE_CONTRACT.md` v1.0（沿用；本卡不改契約語意）
- DB：`db_scope: none`
- 部署：否　環境：—
- 資源：`file:scripts/review_prompt.py`、`file:tests/test_review_prompt.py`
- 範圍：僅上列兩檔
- Design：Design Gate N/A——無使用者可見介面。

## 問題陳述

`review_prompt.py` 產生查核提示詞前只擋「沒有 handoff event」與 handoff 缺欄位。其餘交接前提
要等**查核者進場後**才被發現，代價是查核者白跑、需求方多一次來回。

2026-08-01 的 `LIVE-SNAPSHOT-FIELDS1` 連續三輪 `PREFLIGHT_FAILED`，**沒有一輪是程式碼問題**，
且三項全部可由 event log ＋ git ＋ lease 檔機械判定：

| 輪次 | 查核者擋下的原因 | 機械判準 |
|---|---|---|
| 1 | 卡檔與三個 lifecycle 事件仍是 main 未提交變更 | 最新 handoff 所在 commit 已在 `origin/main` |
| 2 | 最新 handoff 指向舊 SHA，分支已前進至 `cef3eba` | `handoff.source_sha` ＝ `origin/<branch>` tip |
| 3 | 本機 lease 仍引用 `CLAIM-002`／期限 18:00／iteration 1 的 owner 與 resources | `lease.claim_event_id` ＝最新 handoff 的 `claim_event_id` |

共同根因是**衍生狀態沒跟著事件更新**：lease 是 event log 的本機投影，分支 tip 與 handoff SHA
必須互指。人工維護這些投影會漏，而它們全都算得出來。

本卡把這三項提前到產生提示詞的當下。**刻意只收斂為已實際發生過的三項**——其餘可機械檢查的
前提（卡檔追蹤狀態、Ledger 一致、review 後必須有新 handoff）留給
`DEV-REVIEW-PREFLIGHT-GATE1` 的 `--preflight` 重構一併處理，避免本卡膨脹。

## 驗收條件

- [ ] 產生提示詞前逐項檢查，任一項不通過即 fail loud 且**不產出提示詞**：
      (a) 最新 handoff 事件所在的 commit 已存在於 `origin/main`；
      (b) `handoff.source_sha` 等於 `origin/<handoff.branch>` 的 tip；
      (c) 本機 lease 存在且其 `claim_event_id` 等於最新 handoff 的 `claim_event_id`。
- [ ] 每項失敗訊息必須指出**具體差異值**（例：handoff SHA 與 remote tip 各是什麼）與**修復動作**，
      不得只說「不一致」。
- [ ] 檢查一律**唯讀**：不得自動修復，不得寫 event log／Ledger／lease。
- [ ] 無法判定時（無 remote ref、lease 根目錄不存在）明確輸出「判不出來」並 fail，
      不得靜默跳過或當成通過。
- [ ] 既有行為不回歸：合法交接仍照常產出提示詞，輸出內容逐字不變（以字串斷言鎖住）。

## 驗證

- [ ] 三項檢查各先跑紅再轉綠，fixture 以 `LIVE-SNAPSHOT-FIELDS1` 三輪的**真實事件序列**重建，
      證明本卡能擋下當時那三次 `PREFLIGHT_FAILED`。
- [ ] 「判不出來」案（無 remote ref／lease 根目錄不存在）各一個 fixture。
- [ ] `uv run ruff check` ＋ `uv run pytest` 全綠。

## 紅線

- 只做可機械判定的前提；人工前置關卡的宣告與驗證屬 `DEV-REVIEW-PREFLIGHT-GATE1`，
  本卡不碰 `review_preflight_gates`、不碰 `workflow_ledger.py`、不改任何契約文件。
- **不得自動修復**。工具擋下後由 Coordinator 決定怎麼補，避免把「投影沒同步」變成靜默自癒而失去留痕。
- 不得放寬既有的 fail loud；本卡只增加檢查，不減少。

## 依賴與排序

`DEV-REVIEW-PREFLIGHT-GATE1`（Backlog）同樣改 `scripts/review_prompt.py`，並將重構 preflight
輸出路徑。需求方 2026-08-01 裁定**本卡先行止血、該卡之後吸收**：GATE1 認領時應把本卡的三項
檢查併入其 `--preflight` 結構，屆時本卡的獨立實作可移除，但驗收條件與 fixture 須保留。

`DEV-REVIEW-DEACCEPT-TRAIL1`（Backlog）只動 `workflow_ledger.py`，與本卡無檔案衝突。

## Log

- 2026-08-01：`LIVE-SNAPSHOT-FIELDS1` 連續三輪 `PREFLIGHT_FAILED`（全非程式碼問題）後由需求方
  指示開卡並列為優先項目。原草案含六項檢查，經需求方裁定收斂為已實際發生的三項先行止血。
