# DEV-REVIEW-PREFLIGHT-GATE1 Discovery：把前置查核關卡變成機器可讀的 preflight 宣告

> 卡片：[`../tasks/DEV-REVIEW-PREFLIGHT-GATE1.md`](../tasks/DEV-REVIEW-PREFLIGHT-GATE1.md)　規劃：Claude Fable 5@Claude Code　日期：2026-07-31
> 承接 [`DEV-REVIEW-INDEP-FIELD1-discovery.md`](DEV-REVIEW-INDEP-FIELD1-discovery.md)（🏁完成，iteration 1 已通過查核）。
> **Q1／Q3 沿用前份答案；Q2／Q4 由需求方 2026-07-31 重新裁定（見四），取代前份答案。**
> 基線：工作樹原為 main `063d12d`，2026-07-31 稽核時 fast-forward 至 `37431a0`
> （WF-21 審核契約採用後）；盤點另附 `81bcd4d` 的對照。**契約以 v1.0 為準。**
>
> ⚠️ **§一–§六 是路線改寫「之前」的紀錄，刻意保留不刪。** 2026-07-31 對抗式質詢後改採
> 「前置關卡＝preflight 條件」，`gate_id`／gate 狀態機／`review-correction` 全部不再需要。
> **轉折理由、哪些結論作廢、哪些仍然成立 → §七；改寫後的待驗證假設 → §八。**

## 一、前提核對（先修正，再往下走）

需求方 2026-07-31 列了六項前提。逐項核對後，**四項成立、一項只在更窄的路徑上成立、
一項描述的是已被修正的舊版本**。往下的設計以核對後的事實為準。

**1／2 雙重狀態來源——成立。** 卡面 `review_gates`（應然）與 event log
`closes_review_round`（實然）確實各自宣告「多關卡」這件事。前份 Discovery 已察覺並提出
「切開維度、互不為事實來源」，但那個分工的代價是**沒有一邊知道完整答案**：卡面知道有幾關
不知道跑到哪，事件知道跑了幾筆不知道那是哪幾關。

**3／4 終局 REJECT 可被重開、且被錯標為已通過——成立，但路徑比「latest-wins」窄。**
現行 main 已經要求更正必須以 `corrects_event_id` 指名對象，**裸的**
`closes_review_round: false` 不會重開已終結的一輪（`GATE1` iteration 1 就是因此被退回）。
仍然成立的是：**追加一筆指名該 REJECT 的更正即可重開**，且更正之間仍 latest-wins。
2026-07-31 直接呼叫 `_assert_no_review_supersedes_handoff()` 實測，守衛放行，並輸出：

```
### 本輪已通過的中繼關卡（**不代表本輪查核已結束**）
#### 跨家族查核者　2026-07-31T00:00:00+08:00
- 結論：REJECT（3 blocking）
```

錯標確實發生。

**5 非布林欄位只驗最後一筆——不成立（現行實作已正確），但相鄰有一個真的缺口。**
`_closes_review_round()` 在 `_assert_no_review_supersedes_handoff()` 裡對該卡**每一筆**
review 呼叫（含前幾輪），`tests/test_review_prompt.py` 也有
`test_malformed_field_on_earlier_review_is_not_masked` 與
`test_malformed_field_in_previous_round_still_fails_loud` 兩條覆蓋。實測三個情境：同輪較早
malformed 布林 ✓ fail loud、上一輪 malformed 布林 ✓ fail loud、**上一輪 malformed
`corrects_event_id`（int）✗ 靜默通過**。真正沒被驗的是 `corrects_event_id` 的跨輪型別。
新契約的「本輪每一筆 review／correction 逐筆全驗」把它一併蓋掉。

**6 「宣稱只有 5 張、`TEAM-STYLE1` 是錯誤 ID」——描述的是 iteration 0，已於 iteration 1 修正。**
`git show 8a2a502` 的原文確實寫「另掃出 **5 張**……`UX-ENTITY-LINKS1`、`UX-ENTITY-LINKS2`、
`TEAM-STYLE1`、`DEV-REVIEW-PROMPT-GATE1`、本卡」——**5 張、錯 ID、且混進兩張只是引用他卡
文字的卡**，三項全中。但 `46304f9`（iteration 1，已合併並通過查核）已改為腳本窮舉，
數字變成 **14 張**、ID 更正為 `UX-TEAM-STYLE1`、兩張引文命中被顯式列為排除項。
本次以**獨立寫的**腳本在同一個 `81bcd4d` 重跑，A/B/D 實質命中 **14 張且清單逐張相同**
（見三）。「至少 9 張」這個下限成立，但現有紀錄已經比它更完整。

> 這一項不影響設計方向：即使數字已修正，**盤點必須可重跑**這條紀律仍是本卡的紅線，
> 腳本因此納管進 repo 而不是留在某次對話裡。

## 二、gate 模型新引入的五個問題

前份 Discovery 的 Q1（值域含順序）與 Q3（欄位與〈查核〉欄的分工）沿用不重開；
**Q2／Q4 已由需求方 2026-07-31 重新裁定（見四）**。有序清單升級為帶 `gate_id` 的 gate
之後，多出五個問題：

**G1：`gate_id` 為什麼非要不可？** 因為位置索引不穩定。卡面若插入一關，「第 2 關」的所指
就變了，而事件已經寫死「第 2 關通過」。`gate_id` 讓「哪一關」與清單長度、順序解耦。
代價是命名紀律：`gate_id` 一旦被快照過就不得改名或改語意（要換語意就換 id）。
盤點顯示現實用到四種關卡（Plan Gate、需求方人工審／Design Gate、終局查核、資料紅線複核），
慣用值 `plan`／`design`／`final`／`data` 足以覆蓋，不強制。

**G2：卡面被就地改寫怎麼辦？** 這是本卡相對前份 Discovery 的**主要新增**。前份把卡面
定義為「靜態要求，生命週期內基本不變」——實測不成立：`UX-LIVE-GAME1` 的〈Design〉欄在
2026-07-30 從「Design Gate 待需求方核可」被改成「2026-07-30 需求方核可 live-only v1」，
**要求本身消失**；盤點腳本在 `81bcd4d` 命中它、在 HEAD 不命中，差異就是這一張。
〈查核〉欄同樣兼記要求與結果（前份 Q3 已證），〈Design〉欄也是（`UX-PLAYER-SCOPE1`）。
**結論：卡面不能當歷史的事實來源。** 解法是 handoff 快照——寫入當下把 `review_gates`
複製進事件，該輪之後只讀快照。這也讓「卡面 vs 事件誰為準」這個前份必須靠文件約束的
問題**在資料層消失**：卡面管未來的輪次，快照管已發生的輪次。

**G3：跨輪繼承要不要支援？→ 定案：不支援（契約 v0.3 移除 `satisfied_by`）。**
實際流程兩種都有：`UX-ENTITY-LINKS2` 的兩關在**同一輪**（`REVIEW-007` 人工審 →
`REVIEW-008` 跨家族，中間沒有 handoff）；`UX-ENTITY-LINKS3` 的兩關中間**隔了一個 handoff**
（`REVIEW-005` → `HANDOFF-006` → `REVIEW-007`）。v0.2 為後者設計了 `satisfied_by`，
v0.3 移除，理由是**支撐案例在 gate 模型下自己消失了**：

LINKS3 中間那個 `HANDOFF-006` 的 actor 寫得很清楚——「Coordinator **轉交下一關**」。
它存在的唯一目的是把卡交給第二位查核者，而在 gate 模型裡**關卡靠 `gate_id` 推進，
不需要用 handoff 來「轉交」**。同樣的流程在新模型下就是 LINKS2 的形狀：一輪、兩筆 review、
兩個 `gate_id`。於是跨輪繼承的需求歸零。

代價與退路：真的出現「第一關通過後執行者又推了修正」時，新 handoff 會讓 pending 回到第一關，
需求方要重審一次。全庫歷史裡這種情形 **0 次**（LINKS3 那筆是轉交、不是重推）。
`satisfied_by` 是純新增欄位，屆時補上不需任何遷移——現在不做不是關門，是不為不存在的需求
付它的複雜度（該欄位要驗同卡、同 `gate_id`、`approve`、跨輪且不得回指更早的輪次）。

**G4：第二意見複審怎麼歸類？** 現行 schema 分不出它與多關卡。`gate_id` 讓它們天然分開：
**同 `gate_id` ＝ 第二意見，不同 `gate_id` ＝ 多關卡**，不必讀任何中文。
草案的處置是「已完成 gate 的再次 approve 幕等、任何 gate 的 `request_changes` 終結本輪」，
理由是這吻合 `LIVE-GAME-BACKEND1` 的實際處置（APPROVE 後複審翻 REJECT，卡確實退回、
狀態轉 `⏸阻塞`）。若希望複審不得推翻已通過的 gate，須另立規則（契約 §8.3）。

**G5（iteration 2 新增）：關卡不一定發生在某一輪之內。** 這是重檢 `OPS-LIVE-SHADOW1` 時
撞出來的，也推翻了「一輪 ＝ 一個 handoff」這個隱含前提：

- **Plan Gate 型 3 張**：`OPS-LIVE-SHADOW1` 的 Plan Gate（`REVIEW-002` REQUEST_CHANGES →
  `REVIEW-004` APPROVE）發生在**第一次 handoff 之前**——那時還沒有任何一輪可以掛快照。
- **孤兒 review 7 張**：`ML-MATCHUP1`、`GAME-RECAP-PA1-BUILD1`、`UX-TEAM-SPLIT-SCOPE1` 等
  **整張卡從未寫過 handoff 事件**，review 直接跟在 claim 之後。

兩者在 snapshot 模型下都無處掛快照。**處置是修流程不是修 schema**（契約 §5.3）：

`OPS-LIVE-SHADOW1` 的 Plan Gate 之所以在 handoff 之前，成因是「Plan 不算交付」這個習慣——
但它有卡面修訂當 `source_sha`、有 evidence、有查核者，**它就是一次 handoff**。所以規則是
**Plan Gate 先寫 handoff 再送查核**，Plan Gate 這一關照樣進 `review_gates`
（例 `[plan=cross_family, final=cross_family]`），在它自己那一輪完成。
孤兒 review 同理：**cutover 後不得再出現沒有對應 handoff 的 review**。
既有 10 張屬歷史，不回填、不改寫。

> iteration 2 初稿曾把 G5 當成「`satisfied_by` 非做不可」的證據，那是推論太快：
> 這兩種形態要的是「查核必須有一輪可依附」這條**流程規則**，不是一個讓關卡跨輪飄移的欄位。

## 三、可重現盤點（iteration 2：真正輸出分類與計數）

腳本 [`../../scripts/review_gate_inventory.py`](../../scripts/review_gate_inventory.py)，
完整未刪節輸出 [`review-gate-inventory-2026-07-31.md`](review-gate-inventory-2026-07-31.md)。
iteration 1 的版本只印原始命中行、數量靠人數；iteration 2 依需求方 2026-07-31 指示改為
**腳本自己分類並計數**，並補上兩個先前沒有的信號：

- **信號 E（`## Plan Gate`／`## Design Gate` 章節標題）**——iteration 1 沒有它，
  **整張 `OPS-LIVE-SHADOW1` 因此在視野外**：它的兩關寫在章節標題與驗收條目裡，
  〈查核〉欄與〈Design〉欄都看不出來。這是本次確認的**第五種語式**。
- **信號 F（〈查核〉欄與正文互相矛盾）**——`UX-TEAM-HOTZONE1`、`UX-TEAM-RECORDS1` 的
  〈查核〉欄寫「跨模型家族或人工」，正文卻寫「交 AI 查核」。**同一張卡的兩處要求不同**。

HEAD（`37431a0`：母體 123 張卡、892 筆事件、172 筆 review、177 輪）：**命中 32 張，實質 30 張**。

**需求方要求的三種流程分開計數**（不得寫成同一種）：

- **人工審 → 跨家族查核**：3 張——`UX-DESIGN-CONFORM1`、`UX-ENTITY-LINKS1`、`UX-ENTITY-LINKS2`。
- **人工審 → 一般 AI 查核（未要求跨家族）**：3 張——`UX-TEAM-HOTZONE1`、`UX-TEAM-RECORDS1`、
  `UX-TEAM-STYLE1`。前兩張同時是信號 F（自我矛盾），第三張的〈查核〉欄只寫
  「≠ 執行；T3 一般查核」，**完全看不出驗證段要求先人工審**。
- **Plan／Design Gate → 實作查核**：14 張。

實然（event log）：同輪多關卡 6 張、同輪第二意見 1 張、Plan Gate 型 3 張、
孤兒 review 7 張、跨輪關卡 1 張（`UX-ENTITY-LINKS3`）。

**逐張重檢需求方指定的 9 張**，結果與 iteration 1 的差異有三處：`OPS-LIVE-SHADOW1`
從**零命中**變成 Plan Gate 型（信號 E 補上）；`UX-TEAM-*` 三張從「與 LINKS 系列同一類」
細分為 human→一般 AI（`_target_of()` 判別後半段交給誰）；`UX-ENTITY-LINKS2` 的同輪兩筆
review 從「第二意見」更正為「多關卡」（`_actor_class()` 原本把
`GPT@Codex（…需求方轉錄…）` 判成 human——「需求方」講的是誰轉錄，不是誰查核）。

`81bcd4d` 對照仍收在附錄，A/B/D 實質命中與前份 Discovery 的 14 張清單逐張相同。

**分類本身是這次要消滅的東西。** 它讀「交 AI 查核」vs「交跨家族查核」、讀 actor 字串裡有沒有
`Gemini`，全是自由文字——`GUARD1` 三輪證明這條路不可靠，本次也親自踩到兩次
（上段的兩處更正）。因此腳本在 docstring、輸出抬頭與〈讀法〉三處都寫明：
**分類欄是建議、待人工確認，不得被守衛／preflight／gate 判定消費。**
它的用途是把要求搬進結構化欄位，搬完之後對那張卡就沒有用了。

另一個硬限制（**稽核後修正**）：WF-21 baseline 之後的 review 結論已是強制 enum；
之前的 172 筆裡 95 筆帶 `verdict` 但值域有七種、76 筆完全沒有、`review_result` 僅 65 筆有值。
所以問題是**baseline 前值域不一致**，不是「資料層不存在判定」——C2 因此只能拿
`delivery_status`（Ledger 投影欄）近似。詳見契約 §9.4。

## 四、需求方裁定（2026-07-31，ruan6047）

前份 Discovery 的 Q2／Q4 在本卡改由需求方直接定案，**取代前份的答案**（不是補充）：

**Q2 遷移策略**——新卡自 **cutover**（＝本卡合併之日）起強制填 `review_gates`；活卡
**不做一次性全面回填**，但**下一次 handoff 前必須補齊並由 preflight 驗證**；封存卡與
cutover 前的事件不回填、不改寫；Initiative 若不直接交付查核，**明示 `review_gates: []`**，
**不得用缺欄暗示不需查核**；**cutover 後缺欄一律 preflight fail**，不得退化成 tier 下限，
也不得回退成自由文字人工猜測。

> 這推翻了前份 Discovery 的 Q2 答案（「缺欄時明示＋以卡面原文為準」）。差別在**時機**：
> cutover 前是「沒有欄位可讀」，cutover 後是「該填而沒填」——後者是錯誤，不是缺省。
> 也因此本卡新增 **preflight**：驗證必須發生在 handoff 寫進 append-only log **之前**，
> 等到產生查核提示詞才發現缺欄，事件已經寫下去了。

**Q4 保證邊界**——`review_gates` 是「本輪要求什麼」的權威來源；handoff snapshot 是該輪
**不可變的流程基線**；review event 的 `gate_id` 是「完成哪一關」的留痕；工具**不能可信
驗證 reviewer 的真實模型家族或人類身分**，只顯示宣告與 actor 並**明講這是人工核對輔助、
不宣稱已自動驗證身分**；**欄位與舊〈查核〉自由文字衝突時以結構化欄位決定流程**，
自由文字只作說明、不影響 gate 判定。

> 末項是**行為變更**，不是措辭調整：現行 `review_prompt.py` 輸出「卡面〈查核〉欄原文
> （**以此為準**）」與「卡面若要求得比下限嚴……一律以卡面為準」，cutover 後兩句都必須改寫。
> 〈查核〉欄仍原文照登（人可讀），但不再是流程依據。已寫進
> `DEV-REVIEW-GATE-CONTRACT1` 的驗收條件並要求以字串斷言鎖住。
>
> 前份 Q4「工具驗不了真實身分、只能留痕」的結論**維持不變**，本次只是把它從 Discovery 的
> 建議升格為契約條文（§2.1），並明確禁止工具作出「已驗證」的表述。

## 五、需求方裁定（2026-07-31 第二批，ruan6047 採納規劃者建議）

五項未決全數定案，寫入契約 v0.3 §8：

1. **卡 ID 用後繼卡**，不 reopen 兩張已結案封存的卡——`state_version` 接在 release 之後會
   逼著回頭改 Ledger 與封存索引，而歷史沒有錯。
2. **`satisfied_by` 不做**（見 G3、G5）。
3. **第二意見維持可推翻已通過的 gate**：規則要吻合已經在跑的處置
   （`LIVE-GAME-BACKEND1` APPROVE 後複審翻 REJECT，卡確實退回）；反方向會讓第一個 APPROVE
   鎖死結論。
4. **`review_result` 不結構化**：`gate_result` 已承載判定，106 筆缺值是歷史不追。
   多一個必填欄位只是增加寫事件的摩擦，而摩擦正是這批卡片一直在製造的問題。
5. **順序對調為 CONTRACT1 → DECLARE1**：legacy 相容讓守衛可先無害落地（合併當下全庫沒有
   snapshot、100% 走 legacy、行為零變更），DECLARE1 一合併就自動生效，**中間沒有空窗**；
   反過來會讓「卡面已帶 gate、守衛仍用舊邏輯」的空窗期繼續誤擋多關卡的卡。

**另加 release 後追蹤（非驗收條件）**：`closes_review_round` 在全庫 887 筆事件裡用過 **0 次**
——前一張卡建好的機制從未被使用。本契約更大，重蹈的風險是真的。因此 DECLARE1 合併後
第一個月追蹤「新寫的 handoff 是否 100% 帶 snapshot」：preflight 若真的擋在寫入路徑上，
這個數字必然是 100%；不是就代表有人繞過 preflight 手寫事件——那是**早期訊號**，
不必等半年後才發現又是死欄位。

## 六、待驗證假設（路線改寫前，部分已被 §八 取代）

- 信號證明的是「**至少**這些張」。iteration 1 說「已知四種語彙、不能排除第五種」，
  iteration 2 **就找到了第五種**（`## Plan Gate` 章節，整張 `OPS-LIVE-SHADOW1` 因此曾在
  視野外）。這條假設現在的版本是：**已知六種語式，同樣不能排除第七種**。
  遷移回填須由需求方逐張確認，**不得把腳本輸出當成完整宣稱**。
- **分類（三種流程）本身也是自由文字判讀**，本次即在兩處自我修正（`UX-TEAM-*` 的
  「交 AI」與 `UX-ENTITY-LINKS2` 的 actor 誤判）。分類**只用於規劃**，
  已在腳本三處寫明不得被判定消費。
- 「`gate_id` 命名紀律成本低」基於現實只用到四種關卡的觀察，**未實際試填**。
- **「不繼承」的代價未被歷史驗證過**：全庫沒有「第一關通過後執行者又推修正」的實例，
  所以「重審一次」這個代價**沒有真實樣本**。若 cutover 後這種情形頻繁出現，
  `satisfied_by` 是純新增欄位，補上不需遷移。
- **前份把「Design Gate 算不算一關」界定為另一張卡的範圍，本卡收回來**：G5 的 Plan Gate
  型（3 張）與盤點的 14 張 Plan／Design Gate 宣告顯示，把它排除在 `review_gates` 之外就
  表達不了 `OPS-LIVE-SHADOW1` 這種卡。契約 §5.3 因此把 `plan`／`design` 納入慣用 `gate_id`。
  **未驗證的是回填成本**：14 張中多數已封存（不動），活卡那幾張仍須逐張裁定。
- 快照會讓 handoff 事件變大（每輪多一個小陣列）。887 筆事件的規模下不成問題，未量測。

## 七、路線轉折：從「gate 狀態機」到「preflight 條件」（2026-07-31）

### 觸發

開卡前的 WF-21 稽核發現整份規劃建立在過期基準（`063d12d`）上：`origin/main` 已到 `37431a0`，
WF-21 當日 10:41 全鏈落地。逐項比對後有四項衝突（契約 §9 表格），其中兩項是**寫下去就會被
`workflow_ledger.py --check` 擋掉**的硬衝突。

### 真正的分岔點

稽核時讀到 canonical 的一句話推翻了整個設計前提：**WF-21 的 preflight 必驗項已經包含
「規定在跨家族查核前完成的人工檢查」**。也就是說 canonical 已經替「前置關卡」選好了位置——
它是 **preflight 條件**，不是一次 review。

我原本的設計把前置關卡做成 review 事件（帶 `gate_id` 推進的狀態機），那是在跟 canonical
搶同一件事的定義權。改採 preflight 之後：

- `gate_id`、`gate_result`、gate 狀態機、`review-correction` 撞名 → **全部不必存在**。
- 兩個實測重現的 bug（終局 REJECT 可被更正重開、REJECT 被標成「已通過的中繼關卡」）→
  **隨 `closes_review_round` 一起移除而消失，不需要修**。
- 原本要拆的兩張卡 → **合成一張**，因為「守衛狀態機 vs 卡面宣告」那個切面消失了。

### 哪些結論作廢、哪些仍然成立

**作廢**：G1（`gate_id` 為什麼非要不可）、G3（跨輪繼承／`satisfied_by`）、G4（第二意見怎麼
歸類）——這三題都預設「關卡是 review 事件」，前提沒了，題目也沒了。G4 的實質答案由 WF-21 的
attempt 模型（同 SHA 多 reviewer 合併為一次）承接。

**仍然成立**：
- **§一的六項前提核對**（含「premise 5 不成立、真正的缺口是 `corrects_event_id` 跨輪型別」
  與「premise 6 描述的是已修正的 iteration 0」）。
- **G2（卡面會被就地改寫）** ——這是快照存在的理由，換成 preflight 之後仍然成立，只是快照的
  內容從「gate 序列」變成「前置關卡與其結果」。
- **G5（關卡不一定發生在某一輪之內）** ——處置從「`satisfied_by` 跨輪繼承」改成「Plan 本身就是
  一次交付，先寫 handoff 再送查核」，修流程不修 schema。
- **§三的盤點**（三型分類、五種語式、9 張指定卡的逐張結果）完全不受影響，只是用途改了：
  它現在是 preflight 缺欄時的**提示**來源，不再是設計論證的唯一依據。
- **§四的 Q2／Q4 裁定**（遷移策略、保證邊界五條）原封不動，只是「缺欄 fail」的把關者
  從虛構的 `review_gate_preflight.py` 換成 `review_prompt.py --preflight`。

### 這次踩到的兩個坑（不抹掉）

1. **記憶說 WF-21 已上線，我卻因為工作樹讀不到那些檔案而當成「還沒發生」。** 正確反應是先
   懷疑基準過期，而不是懷疑記憶。已寫成記憶 [[plan-against-fresh-origin-main]]。
2. **iteration 2 初稿把 G5 當成「`satisfied_by` 非做不可」的證據**，那是推論太快——那兩種
   形態要的是「查核必須有一輪可依附」這條流程規則，不是一個讓關卡跨輪飄移的欄位。

## 八、待驗證假設（路線改寫後）

- **`review_preflight_gates` 會不會又變成沒人填的死欄位**：`closes_review_round` 全庫用過 0 次
  是前車之鑑。本次的差別是 `--check` 會在 replay 時擋（事件是人手寫的，工具擋不住手寫），
  但那要等 cutover 後第一個月的追蹤才知道（契約 §8）。
- **「缺欄 fail」的回填成本未實測**：活卡 30 張中多數要補一行 `[]`，14 張宣告過 Design／Plan
  Gate 的卡多在封存區（不動），但活卡那幾張仍須需求方逐張裁定。
- **盤點證明的是「至少」**：已知六種語式（iteration 1 說五種、iteration 2 就找到第六種），
  不能排除第七種。任何回填都須逐張確認，不得把腳本輸出當完整宣稱。
- **分類本身是自由文字判讀**，本次即自我修正兩處；它只用於提示，已在腳本三處寫明不得被判定消費。
