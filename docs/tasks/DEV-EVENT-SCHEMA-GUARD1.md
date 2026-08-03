# DEV-EVENT-SCHEMA-GUARD1 event log 寫入端無 schema 把關，壞資料會永久卡住 ledger〔T3；🟡流程〕

- 需求：ruan6047（2026-08-02 於 `UX-BRAND-HOME1` 查核期間實際遭遇後授權開卡）　規劃：本卡 spec　分支：`ai/<執行者>/DEV-EVENT-SCHEMA-GUARD1`
- 執行：待指派（建議 L3；牽涉 control-plane 契約與工具的取捨，且必須在「不破壞 baseline 前既有事件」的約束下設計）　查核：待指派（建議 L2；≠ 執行）
- Initiative：—　spec 基線：—
- review_independence: [cross_family]
- DB：`db_scope: none`
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍：`scripts/workflow_ledger.py`、`docs/CONTROL_PLANE_CONTRACT.md`，視 Discovery 結論可能加 `.claude/hooks` 或新的寫入 helper 與對應測試
- Discovery：**本卡第一項交付是「該在哪一層把關、以及 malformed 的合法修復程序是什麼」的判斷**，不是直接改碼。
- Design：Design Gate N/A——無使用者可見介面。

## 問題陳述

`workflow_ledger.py` 的 schema 驗證**只在讀取端執行**（`_validate_review_contract` 於 `render_ledger` 時才跑），寫入端完全不設防。實際後果是：

**壞資料可以順利進檔案、被 commit、被 push，然後永久卡住 ledger。** 一旦 malformed 事件落地，`--write` 與 `--check` 每次都會在同一行拋出 `ValueError` 而中止，`docs/TASKS.md` 就停在最後一次成功重建的狀態——而 `TASKS.md` 是本專案宣告的「當前狀態事實來源」。

**而契約封死了 append-only 的修復途徑。** `CONTROL_PLANE_CONTRACT.md` 明文「型別驗證涵蓋該卡每一筆 review（**malformed 不得被後續事件掩蓋**）」。這句話對「語意更正」是正確的設計（避免用新事件洗掉舊判定），但它同時使得 **schema 層的錯誤無法用追加事件修復**——驗證器每次 replay 都會重新掃到那一行。契約既要求 append-only，又不提供 malformed 的合法修復程序，兩者在此情境下互鎖。

### 實際發生的事（2026-08-02，`UX-BRAND-HOME1` 查核期間）

Coordinator 寫入 `UX-BRAND-HOME1-REVIEW-007` 時，單一事件踩中四個欄位：

| 欄位 | 寫入值 | 合法值 |
|---|---|---|
| finding `status` | `rejected` | `open` / `resolved` / `withdrawn` |
| finding `finding_class` | `spec-staleness` | `implementation` / `authoritative-artifact` / `governance` / `coordination` / `environment` |
| finding `finding_class` | `documentation-mismatch` | 同上 |
| `counts_toward_escalation` | `true` | 須由結構化 findings 推導（此例應為 `false`） |

該事件通過了 `git commit`、`git push`，隨後 ledger 崩潰。**崩潰未被察覺的原因是記錄方把 `--write` 的 stderr 導向 `/dev/null`，並以無條件的 `echo "ledger ok"` 宣告成功**——`--check` 因 `&&` 短路從未執行。結果是連續兩次 commit（`5736302`、`596da1f`）帶著陳舊的 `TASKS.md` 上了 main，且期間 Ledger 對外顯示的交付狀態是錯的。

最終由需求方裁定**就地修復那一行**（`322f69a`）才解開；原始壞行保留在先前 commit 的 git 歷史中，未 force-push。

**這次能收拾，是因為壞資料寫入後四十分鐘內就被發現、且只有記錄方一人碰過。** 若在多 agent 並行下隔數日才發現，中間所有基於 Ledger 的判斷都會建立在錯誤狀態上。

## 非目標

- **不改 review 契約的語意規則**（`closes_review_round`、`corrects_event_id`、escalation 計數、finding 衝突裁決等）。本卡只處理「壞資料何時被擋下」與「已落地的壞資料如何合法修復」。
- **不回填、不重新解讀 baseline 前的既有事件。** 現況 `contract-baseline` 之前有 **172 筆** review 事件缺欄位（多為早期無結構化 findings 的格式），驗證器刻意跳過它們——任何新守衛**不得**讓這些歷史事件開始失敗。
- 不改 `review_prompt.py` 的提示詞產生邏輯。

## Discovery 必答（先答再改碼）

1. **該在哪一層把關？** 候選：(a) 提供唯一的寫入 helper（如 `workflow_ledger.py --append`）並在其中驗證，但無法阻止有人直接 `>>` 檔案；(b) pre-commit hook 驗證 `events.jsonl` 的 diff；(c) CI 檢查；(d) 以上組合。**各自擋得住什麼、擋不住什麼要明寫**，不得宣稱單一手段涵蓋全部。
2. **malformed 的合法修復程序是什麼？** 契約現行文字使 schema 錯誤無法以追加事件修復。要新增哪一種機制？候選：允許 `schema-repair` 類型的就地修復並要求在 commit message 與該行留痕；或引入 `superseded_by` 讓驗證器跳過被取代的 malformed 事件。**兩者對 append-only 的侵蝕程度不同，須明確取捨並寫進契約。**
3. **fail loud 的粒度是否過粗？** 現行是「任一事件 malformed → 整個 ledger 無法重建」。是否應改為「該卡標記為不可投影、其餘卡照常」？這會降低單點故障的爆炸半徑，但也可能讓壞資料更久不被發現——**這是真實取捨，要選一邊並說明理由**。
4. **要不要同時擋「假的成功訊號」？** 本次事故的近因不是 schema 錯誤本身，而是**記錄流程遮蔽了 stderr 並自行 echo 成功**。這屬人／agent 的操作紀律，工具能做的有限——**明講哪一半守得住、哪一半守不住**，不得宣稱工具能涵蓋。

### Discovery 書面答案（iteration 1；需求方 2026-08-03 裁定）

**1. 該在哪一層把關 → 只加 pytest。**

查證發現缺口比開卡假設的更單純：`tests/test_workflow_ledger.py` 的 20+ 個測試**全部使用合成 fixture**；`tests/test_task_card_sections.py` 與 `test_review_prompt.py` 雖讀真實 `events.jsonl`，但**只做 `json.loads` 取欄位、從不呼叫驗證器**。**整條鏈上（pytest／CI／hook）無一處拿驗證器掃真實檔**——這正是壞事件能通過 commit→push→CI 的原因。實測重建當時的 `REVIEW-007` 丟給 `_validate_review_event`，立即拋 `finding status 不合法`，**證明一條測試即可擋下本次事故**。

各方案**擋得住什麼、擋不住什麼**（不宣稱單一手段涵蓋全部）：

| 方案 | 擋得住 | 擋不住 |
|---|---|---|
| **pytest（採用）** | 任何進入 repo 的 malformed 事件，於 CI 數分鐘內轉紅；**無法被個別 agent 繞過**（CI 不看本地行為） | 寫入當下的即時攔截——壞資料仍可能先進 commit，只是不再靜默 |
| pre-commit hook（未採用） | 壞資料進不了 commit | 無現成基礎設施需新建；`--no-verify` 可繞；新環境需安裝步驟 |
| 寫入 helper（未採用） | 走 helper 的寫入 | **直接 `>>` 檔案完全不受保護，而實際上每個 agent 都是這樣寫的**；反而可能讓人誤以為有保護 |

需求方裁定只加 pytest：它是唯一無法被繞過又不需新基礎設施的一層。代價（CI 在 push 後才跑）已知並接受——本次事故的實害不是「壞資料進了歷史」，而是**靜默 40 分鐘**，pytest 把那段縮到數分鐘。

**2. malformed 的合法修復程序 → 就地修復，留痕以獨立 `schema-repair` 事件承載。**

> ⚠️ **本答案經三輪查核修訂過兩次，以下是現行版本**；修訂原因見〈Log〉。原始答案寫「修復事由**就地留痕**」（寫進被修事件的 `evidence`／`disposition`），該寫法已作廢——它與「不得改動判定欄位」自相矛盾（跨家族查核 iteration 2 指出）。

已寫入 `CONTROL_PLANE_CONTRACT.md` 的 `schema-repair` 段，要求為：

1. **可改欄位為正面表列，且必須是「非法 → 合法」**。事件層僅 `counts_toward_escalation`（推導值，「合法」＝等於由 findings 推導的結果）；finding 層僅 `severity`／`status`／`finding_class`／`attribution`。不得增刪 finding。**白名單內亦不得改寫已合法的值**。
2. **留痕以獨立的 `type: "schema-repair"` 事件承載**，載明 `repaired_event_id`、逐欄位 before／after、以及無法以追加事件修復的理由。**不得**寫進被修事件本身的 `evidence`／`disposition`。
3. commit message 說明；4. 不得 force-push；5. **由 CI 強制驗證**（見下）。

機械強制分兩層：`workflow_ledger.diff_schema_repair()` 判斷單次修復是否逾越白名單；`test_modified_events_obey_the_schema_repair_allowlist` 比對 `git merge-base` 與工作區的 event log 自動套用之；`_validate_schema_repair_event()` 則驗證 `schema-repair` 事件本身的 payload 完整性與 before/after 一致性。

未採 `superseded_by`，因其與契約「malformed 不得被後續事件掩蓋」直接衝突，且多一個可被濫用來掩蓋事件的機制。

**3. fail loud 的粒度 → 維持全檔。**

需求方裁定不改為逐卡隔離。理由：壞得夠明顯才會被修——本次正是因為整個 ledger 停擺才被察覺。逐卡隔離會讓 Ledger 在部分正確的狀態下繼續服務，壞資料可能更久不被發現。配上第 1 問的 pytest 後，「痛」的持續時間已從 40 分鐘縮到數分鐘，全檔粒度的代價已被抵銷。

**4. 能不能擋「假的成功訊號」→ 擋得住一半，另一半擋不住。**

本次事故的近因不是 schema 錯誤本身，而是記錄方以 `2>/dev/null` 遮蔽 `--write` 的錯誤、`--check` 因 `&&` 短路從未執行、再以無條件 `echo "ledger ok"` 宣告成功。

- **擋得住**：CI 跑的是同一條 pytest，**與本地 echo 了什麼完全無關**。只要壞資料進了 repo，CI 就會紅。這是 pytest 方案相對 hook 的關鍵優勢。
- **擋不住**：本地的自欺仍可發生——agent 仍可能對自己與需求方報告一個不存在的成功，只是這次會在 CI 轉紅時被戳破。**工具無法阻止「不看輸出就宣告成功」的操作習慣**，那屬人／agent 紀律，不在本卡可解範圍。

## 紅線

1. **不得讓 baseline 前的 172 筆既有事件開始失敗。** 任何守衛上線前必須以完整 `events.jsonl` replay 證明現況仍可重建。
2. **不得宣稱涵蓋了守不住的部分**（見 Discovery 第 1、4 問）。本專案已有同型教訓（`DOC-CARD-SPEC-RULES1`：檢查容易取得的相關量而非該成立的性質）。
3. **修復機制不得成為洗掉判定的後門。** 若採「就地修復」，必須限定僅能改機器可讀的分類欄位，且 `evidence`／`disposition` 等敘述欄位的原文不得被刪除；若採 `superseded_by`，必須無法用來取代語意判定。

## 驗收條件

- [ ] Discovery 四問有書面答案，第 1、4 問明列**涵蓋範圍與不涵蓋範圍**。
- [ ] 守衛落地並以**負向測試**證明有效：刻意寫入一筆 malformed 事件，證明它在預定的關卡被擋下（不是只看正常情況通過）。
- [ ] 完整 `events.jsonl` replay 通過，且 baseline 前事件數與現況一致（附指令輸出，不接受人工聲明）。
- [ ] malformed 的合法修復程序寫進 `docs/CONTROL_PLANE_CONTRACT.md`，並以本次 `REVIEW-007` 為範例說明。
- [ ] `uv run ruff check` ＋ `uv run pytest` 全綠（既有紅燈 `test_initiative_children_baseline_matches_parent_version` 屬 `UX-LIVE-TRACKMAN1`，不計入本卡）。

## 驗證

- [ ] 查核者以**自己構造的 malformed 事件**獨立驗證守衛會擋（不沿用執行者的測試案例）。
- [ ] 查核者確認 replay 證據可重現，附指令。
- [ ] 查核者確認契約新增的修復程序**不能用來改寫語意判定**（嘗試以該程序竄改一筆 `review_result` 或 `evidence`，應被規則或工具拒絕）。
- [ ] 查核通過前不得 merge main。

## 邊界

- 只動 control-plane 工具與契約文件，不動任何卡片內容、不動 `review_prompt.py`。
- 預估 M（Discovery 與取捨是主體，實作本身不大）。

## Log

- 2026-08-02 register by Claude Opus 5@Claude Code（依 ruan6047 授權開卡）；iteration 0。來源：`UX-BRAND-HOME1` 查核期間 Coordinator 寫入的 `REVIEW-007` 含四個不合法欄位，導致 ledger 自 `5736302` 起持續崩潰、`TASKS.md` 停在舊投影並隨兩次 commit 上了 main，最終由需求方裁定就地修復（`322f69a`）才解開。**開卡動機不是「有人寫錯」，而是「寫錯之後沒有合法的修法」**——契約的 append-only 與「malformed 不得被後續事件掩蓋」在 schema 層互鎖。附帶記錄近因：記錄方以 `2>/dev/null` 遮蔽錯誤並自行 `echo` 成功訊號，使崩潰隱形；此為操作紀律問題，工具能守的部分有限，見 Discovery 第 4 問。
- 2026-08-03 iteration 1 by Claude Opus 5@Claude Code：Discovery 四問完成並經需求方裁定（pytest／全檔 fail loud／就地修復），交付兩條真實檔守衛測試與契約的 `schema-repair` 段。**紅線 1 實證**：baseline 前 review 事件 **172 筆**（卡面〈非目標〉原記 173，該數含當時尚未修復的 post-baseline `REVIEW-007`，實際 pre-baseline 為 172）其 schema 皆不合法，完整 replay 仍通過，證明守衛未讓它們開始失敗。**負向測試以兩種方式做**：(a) 單元層注入非法 `status` 給 `_validate_review_event`；(b) 直接把缺陷注入**真實** `events.jsonl` 後跑 pytest，實測 `test_real_event_log_passes_schema_and_replay_contract` 轉紅、還原後恢復——證明守衛真的會因真實檔變壞而失敗，不是碰巧全綠。**流程自陳**：claim 事件初次曾誤寫於執行分支並 commit，違反「執行分支不得改動 control-plane」，發現後即 `reset --hard` 還原（未推送）並改於主 checkout 重寫。
- 2026-08-03 iteration 3 by Claude Opus 5@Claude Code：依跨家族查核第二輪 REQUEST_CHANGES 修正 F002／F003。**F002 三個子問題全部成立，且全是規劃者自己在提示詞裡請查核者攻擊的地方**——(a) 白名單只查欄位名，`attribution: executor → coordinator` 與 `status: open → withdrawn` 皆回傳合法，等於可用「修格式」之名改寫責任歸屬與 finding 狀態；已加上「**非法 → 合法**」條件，並為推導欄位 `counts_toward_escalation` 定義「合法＝等於由 findings 推導的結果」（否則 2026-08-02 那次正當修復會被誤判為改寫）。(b) **契約自相矛盾**：要求把修復留痕寫進 `evidence`／`disposition`，而同一份契約又禁止改動這兩欄——照契約做必定違反工具。已改為以獨立的 `schema-repair` 事件承載留痕；首例 `REVIEW-007` 於本規則成立前完成，其留痕留在 `disposition`，屬既成事實不回溯調整。(c) `diff_schema_repair()` 除自身測試外**沒有任何 consumer**，與「文字限制」無異；已新增 `test_modified_events_obey_the_schema_repair_allowlist`，比對 `git merge-base` 與工作區的 event log，對兩邊都存在但內容不同的事件強制套用白名單。**基準取 merge-base 而非 `origin/main` tip**——lifecycle 事件只落 main、執行分支通常落後，拿 tip 當基準會把「main 上較新的事件」誤判為分支刪除了它們（初版即如此，實測誤報多筆「遭刪除」）。**據實記載的不涵蓋**：直接在 main 上改寫已推送歷史（本測試以 merge-base 為基準，基準本身被改寫時無從察覺）、淺 clone／離線時 skip。F003 卡面兩處 173 → 172；Log 內記錄更正歷史的 173 屬正確保留。
- 2026-08-03 iteration 4 by Claude Opus 5@Claude Code：依跨家族查核第三輪修正 F002／F004。**F002 正是規劃者在提示詞中自陳「本輪最大的未驗證假設」的那一項**——iteration 3 發明了 `schema-repair` 事件型別、寫進契約，卻**從未實際寫一筆試過**，驗證器也完全不認識它；查核者造一筆缺全部 payload 的 `schema-repair`，完整 replay 仍通過，等於該規則毫無強制力。已新增 `_validate_schema_repair_event()`（payload 四欄齊備、目標存在、before→after 須通過白名單、after 須與 log 現況一致）、負向測試涵蓋五種缺陷型態，以及**正向端到端測試**——在真實 log 後附加一組合成卡片的 review → schema-repair 生命週期並完整 replay，同時作為「一筆合法的 schema-repair 長什麼樣」的可執行範例。過程中實測發現該型事件與其他事件共用同一份 envelope 要求、且 `state_version` 必須是該卡下一號——這兩點原本沒人知道，正因為沒有實際走過。**F004 Discovery 第 2 問答案過期**（仍寫「就地留痕」，與 iteration 3 改用獨立事件的程序衝突）已改寫，並在該答案上方標註「經三輪查核修訂過兩次」與原始版本作廢的理由——這正是規劃者在提示詞中提醒查核者注意的「Discovery 答案可能過期」，實際發生了。
