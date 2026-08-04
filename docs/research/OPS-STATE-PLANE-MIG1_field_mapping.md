# OPS-STATE-PLANE-MIG1 — Task 1：Ledger 欄位 ↔ GitHub Project 欄位／Label 對照表

> **範圍**：本文件只涵蓋卡面 Task 1（欄位結構驗證與定案）。Task 2（`scripts/state_plane_migrate.py` 遷移腳本
> 與 38 卡對帳）與 Task 3（凍結卡處置與 cutover）在需求方核可本文件的結構凍結前不得動工。
> **測試時間**：2026-08-04T21:52:31+0800　**測試者**：Claude Sonnet 5@Claude Code
> **測試環境**：一次性測試 Project `wf22-field-validation-test`（owner `ruan6047`，number `2`）；
> 已於測試完成後關閉並刪除（見文末「測試 Project 建立與清理紀錄」）。**未修改**既有 Project #1
> （`@ruan6047's untitled project`）、**未建立**任何 repo Issue、**未修改**任何 repo 的 labels。

## 結論摘要（先講原則）

Ledger 現有 10 欄＋新制 3 欄（服務的原始目標／鏈深／資源宣告），**13 項中 12 項可由 GitHub Projects v2
custom fields（TEXT／NUMBER／DATE／SINGLE_SELECT）完整表達，實測全部通過**；唯一有實質表達力缺口的是
**「最後交接」**——Project 的 `DATE` 型別 [scalar] 在 API 層**靜默截斷時分秒與時區**，只保留日期，這對需要
精確排序 handoff 先後順序的既有慣例是真實損失，不得直接遷移，需替代方案（見下）。「資源宣告」機制上可
表達（三種可行方案，各有取捨），但**最適解需要需求方對「機械比對資源互斥」這個下游需求的優先序做一次
裁決**，不是純技術問題。

意外之喜：實測發現 GitHub Projects v2 的 GraphQL schema 實際存在**未被 `gh` CLI 曝露、也未見於官方公開文件
的第五種型別 `MULTI_SELECT`**，且直接以 GraphQL mutation 驗證可正常建立與讀寫——這解決了「資源宣告」原本
最大的表達力疑慮（多值清單），但有使用風險（見「意外發現」節）。

## 對照表（核心交付）

| Ledger／新制欄位 | 建議 Project 型別 | 實測 | 表達力判定 |
|---|---|---|---|
| 卡ID | `TEXT` | ✅ 建立＋寫入＋讀回 `OPS-STATE-PLANE-MIG1` | 完全表達 |
| Initiative | `TEXT`（可選 `SINGLE_SELECT`，見備註） | ✅ 寫入＋讀回 `WF-22` | 完全表達 |
| 級別（Tier） | `SINGLE_SELECT`（T0/T1/T2/T3/T4） | ✅ 建立 5 選項＋寫入＋讀回 `T3` | 完全表達，天生封閉列舉 |
| 功能 | `TEXT` | ✅ 寫入＋讀回中文長句 | 完全表達 |
| owner | `TEXT` | ✅ 寫入＋讀回全形括號／分號／斜線混排文字 | 完全表達（**非**內建 Assignees，見備註） |
| 分支／worktree | `TEXT` | ✅ 寫入＋讀回 `branch @ path` 複合字串 | 完全表達 |
| iteration | `NUMBER` | ✅ 寫入 `0`，讀回 `0.0`（底層為 Float） | 完全表達，小整數無虞 |
| 交付狀態 | `SINGLE_SELECT`（8 值，含尚未啟用的 🚨已升級） | ✅ 建立 8 選項（含 emoji）＋寫入＋讀回 `🚧進行中` | 完全表達，**但需與既有慣例的行內附註文字拆分**（見缺口節） |
| 部署狀態 | `SINGLE_SELECT`（4 值） | ✅ 建立 4 選項＋寫入＋讀回 `—不適用` | 完全表達，**同上需拆分附註** |
| 最後交接 | `DATE` | ⚠️ 寫入完整 ISO-8601 datetime，**讀回被截斷成純日期** | **表達力缺口**（見下節，需替代方案） |
| 服務的原始目標 | `TEXT` | ✅ 寫入＋讀回含中文引號「」的長句 | 完全表達 |
| 鏈深 | `NUMBER` | ✅ 寫入 `0`，讀回 `0.0` | **完全表達**（與卡面示例「如鏈深入 body 結構化區塊」相反的結論，見備註） |
| 資源宣告 | `TEXT`（基準）／`MULTI_SELECT`（意外發現，備選）／body 結構化區塊（機械比對用） | ✅ 三種都實測成功 | 可表達，**方案選擇需需求方裁決**（見缺口節） |

**備註（Initiative）**：本測試用 `TEXT`，因 Initiative 集合會隨時間新增、不是封閉列舉；若日後想要「依
Initiative 分組看板」的 UX，`SINGLE_SELECT` 也能表達（新選項可隨時追加），本 Task 1 未實測此分支，留給
Task 2 依實際看板需求決定，不影響結構凍結。

**備註（owner）**：內建 `Assignees` 欄位經 introspection 確認其 mutation（`addAssigneesToAssignable`）只接受
`assigneeIds: [ID!]`／`assignees: [String!]`，兩者皆指向**真實可解析的 GitHub 使用者／bot 帳號**，無法承載
Ledger 現有 owner 值域中的「待指派」「Claude Sonnet 5@Claude Code」（非真實 GitHub 帳號）等值。因此
`owner` 必須走自訂 `TEXT` 欄位，`Assignees` 至多是「owner 剛好是 `ruan6047` 本人時」的附加曝光，不是主表達
手段。

**備註（鏈深 vs 卡面示例）**：卡面 Task 1 描述舉例「表達力不足的欄位列明替代方案（如鏈深入 body 結構化
區塊）」，但實測顯示鏈深只是 0–2 的小整數，`NUMBER` 欄位毫無障礙。真正需要替代方案的是「資源宣告」（見
下）。這裡刻意指出示例與實測結論不一致，而非照抄示例，避免把舉例當結論腦補。

## 逐型別實測證據（GraphQL mutation／query 輸出摘要）

### 1. 欄位建立（`createProjectV2Field`，經 `gh project field-create` 包裝）

```text
--- 級別 (SINGLE_SELECT) ---
{"id":"PVTSSF_...","name":"級別","options":[
  {"id":"bca6179d","name":"T0"},{"id":"c50ce44e","name":"T1"},
  {"id":"ed765382","name":"T2"},{"id":"bd780a2b","name":"T3"},
  {"id":"140bb13d","name":"T4"}],"type":"ProjectV2SingleSelectField"}

--- 交付狀態 (SINGLE_SELECT，含 emoji 選項) ---
{"id":"PVTSSF_...","name":"交付狀態","options":[
  {"id":"3eaacaf8","name":"📥Backlog"},{"id":"9d6e718d","name":"💡需求"},
  {"id":"a8921fe4","name":"🚧進行中"},{"id":"28f823cb","name":"⏸阻塞"},
  {"id":"e555d10b","name":"🔍待查核"},{"id":"2710a741","name":"📦已合併"},
  {"id":"fb340e04","name":"🏁完成"},{"id":"262071d1","name":"🚨已升級"}],
  "type":"ProjectV2SingleSelectField"}

--- 部署狀態 (SINGLE_SELECT，含全形破折號) ---
{"id":"PVTSSF_...","name":"部署狀態","options":[
  {"id":"08150cc2","name":"—不適用"},{"id":"52bd148c","name":"⏸未部署"},
  {"id":"904707d4","name":"✅已驗證"},{"id":"35055b06","name":"🏁完成"}],
  "type":"ProjectV2SingleSelectField"}

--- iteration (NUMBER) / 鏈深 (NUMBER) / 卡ID・功能・owner・分支worktree・
    服務的原始目標・資源宣告 (TEXT) / 最後交接 (DATE) ---
全部回傳 {"id":"PVTF_...","name":"<欄位名>","type":"ProjectV2Field"}，
建立皆成功（13 個自訂欄位 + 專案預設 13 個內建欄位 = 26 個，遠低於下方查證的 50 欄位／專案上限）。
```

中文欄位名稱（卡ID、級別、分支／worktree…）與 emoji／全形符號選項名稱**全部原樣建立成功**，無編碼問題。

### 2. 欄位值寫入＋讀回（draft item，非 repo Issue；`updateProjectV2ItemFieldValue` + `fieldValueByName`）

以 `docs/tasks/OPS-STATE-PLANE-MIG1.md` 卡面實際內容建立一個 **draft issue item**（型別
`DraftIssue`，無 repo 掛載，滿足「不得建立 Issue」邊界）寫入全部 13 個欄位，最終一次 GraphQL query 讀回：

```json
{
  "f1_卡ID": "OPS-STATE-PLANE-MIG1",
  "f2_Initiative": "WF-22",
  "f3_級別": "T3",
  "f4_功能": "任務狀態面遷移至 GitHub Issues/Projects",
  "f5_owner": "待指派（建議 L2；GraphQL／gh 已知模式，對帳紀律要求高，欄位表達力疑義升 L3）",
  "f6_分支worktree": "ai/claude-sonnet-5/OPS-STATE-PLANE-MIG1 @ .claude/worktrees/ops-state-plane-mig1-execution",
  "f7_iteration": 0.0,
  "f8_交付狀態": "🚧進行中",
  "f9_部署狀態": "—不適用",
  "f10_最後交接": "2026-08-04",
  "f11_服務的原始目標": "消除「worktree 過期狀態快照造成錯誤評估、撞卡不可靠、看板缺席」（根因三）",
  "f12_鏈深": 0.0,
  "f13_資源宣告_TEXT": "file:scripts/state_plane_migrate.py\nfile:docs/CONTROL_PLANE_CONTRACT.md\ndb_scope: none"
}
```

13 個欄位中文／全形字元、中文引號「」、多行字串（資源宣告的 `\n`）**全部逐字元精確往返**，僅
`f10_最後交接` 出現非預期截斷（下節詳述）。`f7`／`f12` 讀回 `0.0` 而非 `0`，確認 `NUMBER` 底層是
`Float` scalar（見 introspection 節），對 iteration／鏈深這類小整數計數不構成問題，但非嚴格整數型別，
純屬治理面的極小備註。

### 3. 「最後交接」表達力缺口的直接證據

先以 `gh project item-edit --date` 送完整 ISO-8601 時間戳，**gh CLI 本身**因 Go `time.Parse` 用
`"2006-01-02"` layout 直接拒絕：

```text
$ gh project item-edit ... --date "2026-08-04T20:17:57+08:00"
parsing time "2026-08-04T20:17:57+08:00": extra text: "T20:17:57+08:00"
```

懷疑這只是 CLI 包裝層的限制，遂繞過 CLI 直接打 GraphQL mutation：

```graphql
mutation {
  updateProjectV2ItemFieldValue(input: {
    projectId: "PVT_..." itemId: "PVTI_..." fieldId: "PVTF_..."
    value: { date: "2026-08-04T20:17:57+08:00" }
  }) { projectV2Item { id } }
}
```

**API 層沒有報錯**（`{"data":{"updateProjectV2ItemFieldValue":{"projectV2Item":{"id":"PVTI_..."}}}}`），
但查回實際存值：

```graphql
query { node(id: "PVTI_...") { ... on ProjectV2Item {
  fieldValueByName(name: "最後交接") {
    ... on ProjectV2ItemFieldDateValue { date updatedAt }
  }
}}}
→ {"date":"2026-08-04","updatedAt":"2026-08-04T13:44:57Z"}
```

**確診**：`T20:17:57+08:00` 被**靜默丟棄**，只留日期部分；`date` scalar 的官方 introspection 描述為
`"An ISO-8601 encoded date string."`（對照 `DateTime` scalar 是 `"An ISO-8601 encoded UTC date string."`——
兩者是不同 scalar，`DATE` 自訂欄位只能綁前者）。`updatedAt` 雖然是完整 datetime，但那是 GitHub **系統管理**
的「這個欄位值最後被改動的時間」，不是我們業務語意上「這張卡最後交接的時間」，兩者概念不同，不能借用。

### 4. 意外發現：`MULTI_SELECT`（schema 存在、`gh` CLI 未曝露、官方文件未收錄）

`gh project field-create --data-type` 只接受 `{TEXT|SINGLE_SELECT|DATE|NUMBER}`，但對
`ProjectV2FieldValue` input object 做 introspection 時發現還有 `multiSelectOptionIds` 欄位：

```graphql
query { __type(name: "ProjectV2CustomFieldType") { enumValues { name description } } }
→ TEXT, SINGLE_SELECT, MULTI_SELECT("Multi Select"), NUMBER, DATE, ITERATION
```

直接以 `createProjectV2Field(dataType: MULTI_SELECT, multiSelectOptions: [...])` 建立**成功**
（`__typename: "ProjectV2MultiSelectField"`），並以 3 個真實卡面資源值測試多選寫入＋讀回：

```graphql
mutation { updateProjectV2ItemFieldValue(input: {
  ... fieldId: "PVTMSF_..."
  value: { multiSelectOptionIds: ["00d9e4d3","1d117c7f","ab5a5ec4"] }
}) { projectV2Item { id } } }
→ 成功

query { ... fieldValueByName(name: "資源宣告_MULTISELECT測試") {
  ... on ProjectV2ItemFieldMultiSelectValue { value options { id name } } } }
→ {
    "value": "db_scope:none, file:scripts/state_plane_migrate.py, file:docs/CONTROL_PLANE_CONTRACT.md",
    "options": [
      {"id":"00d9e4d3","name":"db_scope:none"},
      {"id":"1d117c7f","name":"file:scripts/state_plane_migrate.py"},
      {"id":"ab5a5ec4","name":"file:docs/CONTROL_PLANE_CONTRACT.md"}
    ]
  }
```

多選值以**結構化清單**（各自獨立 `id`／`name`）回傳，理論上比 TEXT 分隔字串更適合「機械比對本卡寫入集
× 現役卡寫入集交集」（決議 §3 的資源互斥需求）。但風險見下節，不宜無保留採用。

### 5. Labels：Task 1 範圍內結構性無法實測

P3 前提原文期待「custom fields ＋ labels」共同表達，但操作邊界同時禁止「建立任何 repo Issue」與
「動既有 repo 的 labels」——而 Labels 是**repo-scoped 的 Issue／PR metadata**，對 draft item（無 repo
掛載）直接查詢會得到結構性的 `null`，不是我操作失誤：

```graphql
query { node(id: "PVTI_...") { ... on ProjectV2Item {
  fieldValueByName(name: "Labels") { ... on ProjectV2ItemFieldLabelValue { labels(first:10){nodes{name}} } }
}}}
→ {"fieldValueByName": null}
```

**如實記錄，不腦補**：這不代表「labels 表達力不足」，而是 Task 1 的邊界（禁建 Issue、禁動 labels）與
Labels 的資料模型（必須依附真實 Issue）互相矛盾，此組合**在 Task 1 內原理上不可測**。好消息是本次
13 欄映射**完全不依賴 labels 就能達成**（見上方對照表），labels 從「必要表達手段」降級為「錦上添花」，
不構成阻塞；但若需求方仍想驗證 labels 路徑（例如未來想用 label 做跨 repo 資源比對），建議 Task 2 開工
前先跑一個**單一 Issue 的最小 smoke test**（不算入 38 卡正式遷移），而不是直接假設它能用。

## 表達力缺口與替代方案（紅線：不得靜默丟欄）

### 缺口 1：最後交接（DATE 遺失時分秒＋時區）

- **原則**：能不能接受「看板只精確到天」是需求方的產品判斷，不是技術判斷——我只能列選項，不能替需求方
  決定精度要不要緊。
- **方案 A（推薦）**：`最後交接` 用 `TEXT` 存完整 ISO-8601 字串（`2026-08-04T20:17:57+08:00`），放棄
  Project 原生日曆挑選器與「依日期排序」UI 便利性，換取零精度損失、遷移腳本可直接字串比對。
- **方案 B**：`最後交接` 維持 `DATE`（供人眼看板一瞥用），另開 `最後交接_精確時間` 這個 `TEXT` 伴隨欄位
  存完整字串（機器讀這欄，人看那欄）。多一個欄位換取兩種消費者都滿足。
- **方案 C（不推薦）**：接受精度損失，board 只看「哪一天」。既有 handoff 紀律要求同日多次交接時序清楚
  （canonical `HANDOFF_CONTRACT.md`、`source_sha` 嚴格遞增等機制皆隱含時序敏感），貿然接受會削弱既有
  對帳能力，**不建議**在需求方未明確承認「可犧牲同日排序」前預設此案。

### 缺口／裁決點 2：資源宣告（多值清單）

- **原則**：這裡不是「能不能表達」（三案都測試通過），是「要不要為了機械化的資源互斥比對，換取額外的
  維運成本與未來風險」——這是優先序判斷，需求方裁決。
- **方案 A**：`TEXT` 存換行分隔清單（本測試的基準做法）。優點：零額外欄位管理成本、任意字串（含未來
  才出現的檔案路徑）都能寫。缺點：程式要靠字串切分比對交集，正則錯誤或格式漂移風險由腳本自行承擔。
- **方案 B**：`MULTI_SELECT`（意外發現）。優點：交集比對是結構化 `option id` 相等比較，比字串解析可靠。
  缺點：①`gh` CLI 不支援建立，`state_plane_migrate.py` 須直接打 `gh api graphql`，工具鏈少一層保護；
  ②官方文件目前查無此型別記載（見下方「平台上限」查證），穩定性與長期支援沒有官方承諾；③single-select
  官方文件明載**每欄位上限 50 個選項**，multi-select 大機率共用同一 UI 元件與上限（本次未查得官方明文
  確認，如實標示「推定、非確認」）——而`file:*`路徑理論上隨專案成長無上限增加，用 MULTI_SELECT 硬扛
  「任意檔案路徑」這種開放集合，遲早撞到選項上限或造成選項清單無止盡膨脹、難以清理。
- **方案 C（推薦組合）**：**拆成兩層**——`db_scope`（`none`/`read`/`write`/`schema`/`data-migration`，
  `CONTROL_PLANE_CONTRACT.md` 已定義的**封閉**列舉）適合方案 B 的 `MULTI_SELECT` 或甚至 `SINGLE_SELECT`；
  `file:*`／`port:*`／`container:*`／`db:*` 這類**開放**、任意字串的資源路徑，維持在 Issue **body 的
  結構化區塊**（卡面既有慣例，格式已固定），由 `state_plane_migrate.py` 解析 body 文字做交集比對，
  不佔用 Project 欄位選項配額。Project 上的「資源宣告」欄位（`TEXT`）只放**摘要／人類可讀版**供看板一瞥，
  machine-of-record 是 body。

## 意外發現與操作陷阱

- **`gh project item-list --format json` 對中文欄位名稱的 JSON key 有編碼錯誤**：欄位「值」完整正確，但
  JSON 的**鍵名**（由中文欄位名稱轉換而來）出現 U+FFFD 替代字元亂碼（例如「資源宣告」鍵名被截斷成不可讀
  的 `���源宣告`）。這是 `gh` CLI（2.92.0）這個便利指令本身的問題，不是資料毀損——改用
  `gh api graphql` 搭配 `fieldValueByName(name: "...")` 逐欄位點名查詢，回傳完全正確。**`state_plane_migrate.py`
  若要程式化讀取欄位值，應直接打 GraphQL（`fieldValueByName` 或 `field { ... on ProjectV2FieldCommon { name } }`
  逐一比對），不要依賴 `item-list` 的 JSON 欄位名稱作為 key。**
- **新專案自帶 13 個內建欄位**：`Title`／`Assignees`／`Status`（內建 `SINGLE_SELECT`，預設
  `Todo`/`In Progress`/`Done`）／`Labels`／`Linked pull requests`／`Milestone`／`Repository`／
  `Reviewers`／`Parent issue`／`Sub-issues progress`／`Created`／`Updated`／`Closed`。其中 `Parent issue`
  ／`Sub-issues progress` 是 GitHub 原生的 Issue 階層關係（sub-issues 功能），與決議 §5「鏈式停損」的
  「鏈」概念高度相關——但這是 **Issue 層級**關係，不是 Project custom field，Task 1 範圍（禁建 Issue）
  無法實測，留給 Task 2 評估是否用原生 parent/child 取代或輔助「鏈深」欄位表達親代關係。
- **Number 底層是 `Float` 不是 `Int`**：`ProjectV2FieldValue` input object 的 `number` 欄位型別為
  `Float`（GraphQL introspection 確認）。`iteration`／`鏈深` 這類小整數計數不受影響，但代表 schema
  層不會擋小數輸入（例如誤填 `1.5`），這是資料衛生的極小備註，非阻塞。
- **`Assignees` 需要真實 GitHub 帳號**：`addAssigneesToAssignable` mutation 的 `assigneeIds`／`assignees`
  皆指向可解析的使用者／bot，無法承載「待指派」「Claude Sonnet 5@Claude Code」這類 Ledger 現有值，
  已在對照表備註說明。

## 平台上限（官方文件查證，非猜測）

- **單一 Project 總欄位數上限 50**（含系統欄位）：GitHub 官方文件〈About issue fields in projects〉
  明文「Projects support up to 50 fields in total. Issue fields and system fields count toward this
  limit.」。本次 13 系統 + 13 自訂 + 1 個 multi-select 測試 = 27，遠低於上限；正式遷移（13 個自訂 +
  沿用系統欄位）同樣無虞。
- **單一 single-select 欄位上限 50 個選項**：GitHub 官方文件〈About single select fields〉明文
  「Single select fields can contain up to 50 options.」。本次「交付狀態」8 選項、「部署狀態」4 選項、
  「級別」5 選項，遠低於上限，無虞。
- **multi-select 選項上限**：官方公開文件目前**查無**明文記載（甚至未提及 multi-select 型別本身存在），
  推定與 single-select 共用同一元件與上限，但**這是推定、非確認**——如實標示，供「資源宣告」方案 B／C
  的風險評估使用，不當作已驗證事實。

## 測試 Project 建立與清理紀錄

```text
$ gh project create --owner "@me" --title "wf22-field-validation-test" --format json
{"id":"PVT_kwHOAvJcys4BfW_w","number":2,"owner":{"login":"ruan6047"},
 "title":"wf22-field-validation-test","url":"https://github.com/users/ruan6047/projects/2", ...}

# ...13 個自訂欄位建立、1 個 draft item 建立、13+1 欄位寫入與讀回、1 個 MULTI_SELECT 意外驗證...

$ gh project close 2 --owner "@me" --format json
{"closed":true,"fields":{"totalCount":27},"id":"PVT_kwHOAvJcys4BfW_w","items":{"totalCount":1}, ...}

$ gh project delete 2 --owner "@me"
(exit code 0)

$ gh project list --owner "@me" --format json
{"projects":[{"number":1,"title":"@ruan6047's untitled project","fields":{"totalCount":13},
              "items":{"totalCount":0}, ...}],"totalCount":1}
```

清理後 `gh project list` 恢復成測試前的基準狀態（僅 Project #1，13 個內建欄位、0 items），確認測試
Project 已完整移除、且**從未修改** Project #1。全程**未建立任何 repo Issue**、**未修改任何 repo 的
labels**。

## 建議與後續

1. **可以結構凍結的部分**：13 項中 12 項（除「最後交接」外）+「資源宣告」的基準 `TEXT` 方案，直接照
   對照表定案即可，無爭議。
2. **需需求方裁決的兩點**（見上方兩節）：
   - 最後交接要不要接受精度損失（方案 A／B／C 三選一，推薦 A 或 B）。
   - 資源宣告要不要為機械化資源互斥比對投入額外維運成本（方案 A／B／C 三選一，推薦 C：db_scope 走
     select 型欄位、開放式檔案路徑留在 body 結構化區塊）。
3. Labels 若需求方仍想在 Task 2 驗證，建議先跑單一 Issue smoke test，不要直接併入 38 卡正式遷移對帳。
4. `WF-22-CLI1`（常駐 CLI）依賴本文件的結構凍結；凍結前不得動工，本卡也不得逕自進入 Task 2。
