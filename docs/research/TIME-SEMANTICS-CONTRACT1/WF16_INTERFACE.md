# 時間語意 × ai-workflow 介面規範

> **給 [ai-workflow#16](https://github.com/ruan6047/ai-workflow/issues/16)（WF-ORCHESTRATION-RECONCILE1）
> 與 [ai-workflow#15](https://github.com/ruan6047/ai-workflow/issues/15)（WF-REVIEW-EVENT-MARKER-CONTRACT1）直接消費。**
>
> 來源：cpbl-analytics #123 TIME-SEMANTICS-CONTRACT1，權威定義見
> [`docs/TIME_SEMANTICS_CONTRACT.md`](../../TIME_SEMANTICS_CONTRACT.md)。
>
> **邊界（需求方 2026-08-10 明示）**：本檔只規範**時間語意側**——某個概念屬哪一型、
> 由哪個時鐘決定、允許哪些 API。**不設計也不修改** wfcli 的狀態機、事件格式、outbox
> 結構或 templates。欄位命名、marker 語法、schema 版本化一律屬 #15／#16 的權限。
> #123 對 ai-workflow repo 無任何寫入宣告。

---

## 1. 三個型別（速查）

| 型別 | 是什麼 | 時區 | 儲存／序列化 |
|---|---|---|---|
| `instant` | 事情發生的那一刻 | tz-aware，機器層一律 UTC | `timestamptz`／ISO-8601 帶 offset |
| `business_date` | 人說的「哪一天」 | `Asia/Taipei`（UTC+8，無日光節約） | `date`，無時分秒 |
| `season` | 球季年 | 由 `business_date` 導出 | `int` |

**時鐘位置規則**：`business_date` 的時鐘一律住在應用程式端，資料庫不得自取。
`as_of` 是 `business_date` 的**參數形式**，不是第四個型別。

**核心約束**：`business_date` 沒有時區可以加註。曆日不是被壓縮的時點，它對應一個
24 小時區間，而區間邊界取決於用誰的曆法。「全部存 UTC 再加註時區」是 `instant`
的解法，套到曆日上是型別錯誤。

---

## 2. 五類 #16 會撞到的問題

### 2.1 狀態機事件時戳 → `instant`

現行卡片 Log 寫成 `2026-08-10T14:38:55+08:00`，是帶台北 offset 的 instant，**合法**。

**規範**：渲染格式**全域固定一種**（統一 `Z` 或統一 `+08:00`，擇一即可，本卡不指定）。

**為什麼**：混用會讓**字串排序**與**時序排序**分岔。`2026-08-10T09:00:00Z` 與
`2026-08-10T14:00:00+08:00` 是同一時點，但字串比較會判前者較小。reconcile 靠時序
對帳，一旦兩種排序不一致，對帳結果取決於實作用了哪一種，且不會報錯。

**附帶規範**：比較與排序**一律在絕對時點上做**，不得對序列化字串做前綴比較。

### 2.2 逾時與退避 → `instant` 差值

GitHub `X-RateLimit-Reset` 是 Unix epoch 整數。

**規範**：轉成 tz-aware UTC，禁止落成 naive `datetime`。
naive 值在 UTC 容器與台北開發機上代表**不同的時點**，退避時間會差 8 小時。

**建議（非強制）**：純粹的「經過多久」量測用單調時鐘 [monotonic clock]，
不受 NTP 校時跳動影響。牆鐘差值只用於需要對外呈現的場合。

### 2.3 到期判定 → `business_date`

`review by`、卡片檢視日期、任何「這件事過期了沒」。

**規範**：以台北曆日判定。「今天是不是已經過了 2026-11-01」在台北 00:00–08:00
與 UTC 判定會差一天。

### 2.4 idempotency key 若含日期 → `business_date`，且必須明示時鐘來源

**這是 #16 最容易踩的一項。**

**規範**：key 內若含日期成分，該成分必須是 `business_date`，且由**明示傳入的
instant** 導出，不得取環境時鐘（`date.today()`／`CURRENT_DATE`／`new Date()`）。

**為什麼**：outbox 的去重前提是「同一個邏輯操作產生同一個 key」。若 key 取環境時鐘，
則同一次重送發生在跨日窗兩側時會產生**兩個不同的 key**，去重靜默失效——而這正是
outbox 存在的理由。UTC 容器上這個窗每天出現 8 小時。

**推論**：重送必須攜帶**原始操作的** `business_date`，不是重送當下的。

### 2.5 狀態機測試 → 適用時間語意契約 §6 全部規則

- 測試不得依賴環境時鐘；任何依賴「今天」的測試必須注入。
- CI 釘 `TZ=UTC`（與生產同一時區前提），**不得**釘 `Asia/Taipei`——那會讓 CI
  永遠無法重現 UTC 容器缺陷。
- 禁止 module-level 求值的「今天」。

**可重現案例**：cpbl-analytics `tests/test_daily_summary.py:23` 的
`_TODAY = date.today()` 取容器日組假資料，受測碼取台北日。UTC runner 上兩者一天
重合 16 小時、分岔 8 小時 → CI 綠 2/3、紅 1/3，**確定性而非 flaky**。
PR #122 的 15 個失敗即此因。

---

## 3. 給 #15 的附註

`wf-review-event:v1` 的 marker 若含任何時間欄位：

- 事件發生時刻 → `instant`，序列化格式與 §2.1 同一規則。
- 若含「哪一天」語意的欄位（如批次日、檢視日）→ `business_date`。
- fail-closed 規則若涉及「過期的 marker」，過期判定屬 §2.3。

**本卡不主張 marker 應否含時間欄位**，那是 #15 的裁量。

---

## 4. 待決問題（#123 刻意不裁定）

1. **序列化格式擇一**：統一 `Z` 或統一 `+08:00`。兩者皆滿足本契約；#16／#15 擇一後
   應寫回自身權威文件。#123 只要求「不得混用」。
2. **idempotency key 的日期成分是否必要**。#123 只規範「若有，則須為 business_date」，
   不主張應該有。
3. **單調時鐘的採用範圍**。§2.2 列為建議，未定為強制。
4. **ai-workflow 是否採用相同的守衛機制**（掃描器＋pytest 棘輪＋inline allowlist）。
   #123 的守衛設計見契約 §7，可複製但未強制。

---

## 5. 已消解的前提（請更新 #16 的漂移案例清單）

#16 的 spec 基線把 **PR #122 列為漂移案例來源之一**。經 #123 查證，#122 的 CI 紅
**不是編排漂移，是時間語意缺陷**（根因見 §2.5）。#123 已定案批次 1（測試注入化
＋ CI 釘 `TZ=UTC`）並經需求方裁決拆成獨立止血卡先行，落地後該症狀消失。

建議把 #122 從漂移案例清單移除，或改標註為「已歸因於時間語意，由 #123 批次 1 處理」，
避免為一個即將不存在的症狀設計恢復路徑。

已於 2026-08-10 依需求方指示轉達至
[ai-workflow#16 comment](https://github.com/ruan6047/ai-workflow/issues/16#issuecomment-5237388050)。
