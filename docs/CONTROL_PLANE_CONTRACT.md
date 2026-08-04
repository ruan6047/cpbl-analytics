# Control-plane Contract — cpbl-analytics

> 共同不變量見 canonical [`../.ai-workflow/AI_WORKFLOW.md`](../.ai-workflow/AI_WORKFLOW.md) §4.1。本檔將跨人協作狀態與本機資源鎖分離；不得填入 token、secret 或個資。
>
> **⚠️ B2 權威文件改版（OPS-STATE-PLANE-MIG1 Task 3，2026-08-04）：待獨立校讀。**
> 本次改版把卡狀態面／事件面的事實來源由 git（`events.jsonl` ＋ `TASKS.md` 投影）遷至
> **GitHub Issues ＋ Projects v2**（決議紀錄〈工作流檢討決議 7〉；結構凍結見
> `docs/research/OPS-STATE-PLANE-MIG1_field_mapping.md` 與 events.jsonl `a04a862`）。
> **cutover 已於 2026-08-04T23:47:31+08:00 宣告**（需求方 ruan6047；終筆封存事件
> `OPS-STATE-PLANE-MIG1-NOTE-004`，main `8271d7c`）：**§2 生效中**，`events.jsonl` 已
> 封存唯讀；§1 全段轉為**歷史參考**（逐字保留，供稽核與舊事件回溯解讀）。
> 本段文字修正由 PM 祕書依 MIG-1 收官查核 disposition 於 merge 時落款（祕書單寫入
> 通道職權；執行分支結構上不可能預載晚於自身提交的宣告）。

## §0 Adapter 邊界（雙軌現況）

| 範圍 | 現行（§1，cutover 前生效） | 新狀態面（§2，cutover 後生效） |
|---|---|---|
| 卡狀態／事件面 | `events.jsonl` append-only Git history ＋ `TASKS.md` 投影 | GitHub Issue（單卡狀態）＋ Issue timeline／結構化 comment（事件） |
| 看板聚合 | 無（`TASKS.md` 表格） | user-level GitHub Project v2「cpbl-analytics 任務看板」（[#4](https://github.com/users/ruan6047/projects/4)），跨 repo 聚合＝多專案面板 v0 |
| 寫入通道 | `ruan6047` 為唯一 lifecycle writer，Coordinator 代行機械寫入 | **祕書單寫入通道**（決議 1）：僅 PM 祕書 session 可寫 Issue 狀態／comment／Project 欄位；其他 session（含執行者、查核者）唯讀，經需求方或祕書轉達 |
| Local resource | `/private/tmp/cpbl-analytics-control-plane/<CARD_ID>/lease.json` 原子目錄鎖 | 不變（本機資源鎖與遠端狀態面是兩層，cutover 不影響） |
| 程式碼 remote coordination | GitHub protected `main` + PR／Actions | 不變；程式碼面 branch protection／required checks 另立 `OPS-CODE-BRANCH-PROTECT1`（`OPS-CONTROL-PLANE-PR-GUARD1` 封存後的窄卡），與**卡狀態面**（本檔主題）是兩個不同關切 |
| Ledger projection | `uv run python scripts/workflow_ledger.py --write` → `TASKS.md` | 祕書每日 snapshot export 回 git（離線稽核用途，非事實來源） |
| events.jsonl 地位 | **唯一作業狀態事實來源** | **cutover 後封存唯讀**：不得刪除（紅線 3），歷史稽核仍在 git，但不再接受新 lifecycle event |

---

## §1 現行機制（cutover 前生效——這段落是實際還在跑的規則，未經需求方 cutover 宣告前不得視為已停用）

### Event、claim 與 WIP

- event 必填 canonical §4.1 欄位與投影欄位；同一卡 `state_version` 自 1 嚴格遞增。handoff、review、handoff-accepted、merge、release 固定 `source_sha` 與 evidence。
- WF-21 審核契約採用 [`review-escalation.md`](../.ai-workflow/templates/review-escalation.md)。於 canonical
  合併、`review_prompt.py` 已改產生 WF-21 互斥結果後，以獨立 `contract-baseline` lifecycle
  event 寫 `contract_baseline: review-escalation-v1`；只有該行**之後**的事件套用新欄位，
  既有事件不回填、不重新解讀。marker 只能出現一次且不得附在 review 等其他事件上。
  `workflow_ledger.py --check` 對 baseline 後的 `preflight-failed`、`review-invalid`、`review`、
  `review-correction`、`escalation-epoch-change` 與 `escalation-checkpoint` fail loud；review 必填
  deterministic `attempt_id`、epoch、結構化 findings 與推導後的 `counts_toward_escalation`。
  有效但不計數的 review／review-correction 仍更新 finding open set；同 attempt 的同 finding
  狀態衝突先標 pending，下一筆相關事件必須用 `review-correction` 裁決；未裁決才 fail loud，
  合法 correction 後完整 append-only replay 必須恢復通過。衝突與 checkpoint 同時 pending 時
  先允許 correction 清完衝突，再強制 checkpoint，兩閘不得互鎖。withdrawn、accepted=false
  或 open finding 降級為不可計數時，須將它移出 open set，並同步移除 unresolved carry、
  repeated-root 與「只由該 finding 支撐」之 target attempt 計數；resolved 未撤銷不得洗掉
  真實歷史。root 重診斷須遷移同 finding 在該 epoch 全部 attempt 的 occurrence。epoch 只能由
  需求方核可事件逐一遞增，review 不得自行跳號。
- **schema 壞損的修復程序（`schema-repair`；DEV-EVENT-SCHEMA-GUARD1）**：append-only 與上一段的
  「malformed 不得被後續事件掩蓋」在 **schema 層互鎖**——型別驗證涵蓋每一筆 review，故追加任何
  更正事件都救不了寫壞的那一行，`workflow_ledger.py` 會在每次 replay 重新崩潰、`docs/TASKS.md`
  永久停在舊投影。**此情形（且僅此情形）允許就地修復**，程序如下，四項缺一不可：
  1. **可改欄位為正面表列，且必須是「非法 → 合法」**（機器可讀，非文字約定）：
     事件層僅 `counts_toward_escalation`；finding 層僅 `severity`／`status`／`finding_class`／
     `attribution`。**不得新增或移除 finding。** 其餘全部禁止，包含但不限於
     `review_result`／`evidence`／`disposition`／`actor`（判定與歸屬）、
     `blocking`／`accepted`／`root_cause_id`（finding 的實質判定）、
     `source_sha`／`attempt_id`／`escalation_epoch`／`preflight_passed`／`event_id`／`card_id`（身分與目標）。
     **白名單內亦不得改寫已合法的值**——`status: open → withdrawn`、`attribution: executor → coordinator`
     都是改寫判定，不是修復格式；要改語意請走 review／review-correction。
     `counts_toward_escalation` 為推導值，其「合法」定義是**等於由結構化 findings 推導的結果**。
     > 兩次收緊的由來：初版寫「列舉值、推導布林、**缺漏的必填欄位**」，第三項無界限，可藉「補欄位」
     > 之名重定義 `source_sha`／`attempt_id`／`accepted`／`blocking`／`root_cause_id`；改為正面表列後，
     > 跨家族查核再指出「只查欄位名」仍可 `executor → coordinator` 改寫責任歸屬，故加上「非法 → 合法」條件。
  2. **修復事由以獨立事件留痕，不得寫進被修事件本身。**
     追加一筆 `type: "schema-repair"` 事件，載明 `repaired_event_id`、逐欄位的 before／after、
     以及無法用追加事件修復的理由。
     > **不得**在被修事件的 `evidence`／`disposition` 加註——那兩欄承載判定，屬第 1 項的禁止清單，
     > 契約若同時要求「在該處留痕」與「不得改動該處」即自相矛盾（跨家族查核指出，iteration 2 確實如此）。
     > 首例 `UX-BRAND-HOME1-REVIEW-007`（`322f69a`）於本規則成立前完成，其留痕寫在 `disposition`
     > 前綴，屬既成事實不回溯調整；本規則自 iteration 3 起適用。
  3. **commit message 須說明**修了哪些欄位、為何無法以追加事件修復、以及原始壞行仍保留於哪個 commit。
  4. **不得 force-push**：修復是一個新 commit，git 歷史保留原始壞行。
  5. **由 CI 強制驗證，不靠人工閱讀**：`tests/test_workflow_ledger.py::
     test_modified_events_obey_the_schema_repair_allowlist` 比對分支基底（`git merge-base`）
     與工作區的 event log，對兩邊都存在但內容不同的事件逐一套用
     `workflow_ledger.diff_schema_repair()`，違反白名單即 fail。
     **已知不涵蓋**：直接在 main 上改寫已推送的歷史（本測試以 merge-base 為基準，
     基準本身被改寫時無從察覺），以及取不到 merge-base 的環境（淺 clone／離線時 skip）。
  修復後必須 `--write` 與 `--check` 皆通過才算完成。**此程序不是 append-only 的例外通道**：
  凡能以追加事件表達的（語意更正、判定翻案、finding 狀態變更）一律不得走此路。
  2026-08-02 `UX-BRAND-HOME1-REVIEW-007` 為首例（四個非法欄位，`322f69a` 修復）。
- **`closes_review_round`（review 事件選填，布林）**：`false` 表示這一筆是**中繼關卡**（Design Gate、需求方本地人工審…），**本輪查核尚未結束**；缺席即視為終結本輪。卡面要求多道關卡時（例：`UX-ENTITY-LINKS2` 的「先本地人工審再交跨家族查核」），**前面各關的 review 事件必須帶 `false`**，否則 `review_prompt.py` 會判定本輪已結束而拒絕為後續關卡產生提示詞（DEV-REVIEW-PROMPT-GATE1）。
  - 判定採**存在終結本輪者即拒絕**：最新 handoff 之後只要任一筆 review 缺席本欄位或為 `true`，本輪即視為已結束。寫錯時（event log append-only 不得改寫）追加一筆更正用 review 事件：帶 `closes_review_round: false` 並以 **`corrects_event_id`**（review 事件選填，字串）指名**同輪內較早**被更正的那筆 review；被指名者的判定以更正事件的宣告為準（多次更正以最新一筆為準）。**未指名更正對象的 `false` 只代表它自己，不會重開已終局的一輪**——iteration 1 曾採「以最新一筆為準」，終局 REJECT 後追加任意 `false` 即可重開本輪、且該 REJECT 會被標成已通過的中繼關卡，查核退回修正（DEV-REVIEW-PROMPT-GATE1 iteration 1）。欄位非布林、更正對象不存在或指向自己時 `review_prompt.py` 一律 fail loud，且型別驗證涵蓋該卡每一筆 review（malformed 不得被後續事件掩蓋）。
  - 不得用 `delivery_status`、`owner` 或 `review_result` 的字面推斷此性質：實測 146 筆既有 review，最終 APPROVE 有 17 筆同樣停在 `🔍待查核`，且 owner 常寫成「（執行，交付待查核）」本身就含「查核」二字。**這個性質只由本欄位表達。**
- **卡面 `review_independence` 與本欄位的職權劃分（DEV-REVIEW-INDEP-FIELD1，2026-07-30）**：多關卡這件事在兩處各有表達，**不是取其一，是切開兩個維度**——
  - **卡面 `review_independence` ＝ 靜態要求（應然）**：這張卡**應該**有幾關、每關要什麼獨立性、順序為何。需求方的宣告，卡片生命週期內基本不變；改它就是改要求，須經需求方並留痕。欄位語意、值域與遷移程序見 [`TEMPLATES.md`](TEMPLATES.md)。
  - **event log `closes_review_round`／`corrects_event_id` ＝ 動態進度（實然）**：本輪**實際**跑到哪一關、每關誰查的、本輪結束沒。append-only，只增不改。
  - **互不覆寫、互不為事實來源**：卡面欄位**不參與**任何守衛放行判定（`review_prompt.py` 的守衛與中繼關卡段完全不讀它，否則「存在終結本輪者即拒絕」會被第二個來源污染）；event log **不參與**提示詞裡的獨立性要求陳述。
  - 兩者不一致時**各管各的維度、並列呈現，工具不仲裁**（一仲裁就回到「替需求方決定要求」）。三種形態：欄位宣告 N>1 關但本輪無中繼關卡事件 → 照登、**不擋**；欄位宣告單一關卡但事件有中繼關卡 → 以事件為實然放行並帶出中繼裁定；欄位缺席 → 明示缺欄＋以卡面原文為準，**不得回退成「所以只要新 context 就好」**。
  - **欄位是留痕，不是保證**：工具能驗「卡面宣告了什麼」，不能驗「實際查核者是否真的跨家族」——查核結論由需求方人工轉錄，actor 字串是人打的（既有事件就有兩筆自帶「待補正」），本專案沒有可信的查核者身分來源。提示詞把宣告值與最近一筆 review 事件的 actor **並列印出**屬**輔助判讀**，不得表述為保證，也不據此擋任何流程。
- **跨 writer handoff 另見 [`HANDOFF_CONTRACT.md`](HANDOFF_CONTRACT.md)**（canonical §4.1／WF-20）：T2 以上或任何 owner 變更，sender 須先 push **完整 40 字元** `source_sha`，receiver 完成驗證清單後才寫 `handoff-accepted` 並取得所有權。該檔只規範 handoff 類事件的欄位與接收驗證，**envelope、event store 與 Ledger 投影仍以本檔為準**，不構成第二個狀態來源。baseline 為 2026-07-29，不追溯既有 150 筆無 acceptance 的 handoff。
- `ruan6047` 是唯一 lifecycle writer；Coordinator 先追加 event，再建立／釋放 local lease，最後重建 Ledger。local telemetry 必填 `lifecycle=false`、`claim_event_id`，不得改 card state。
- **lifecycle event 一律直接 commit 至 `main`**（由 Coordinator 或其指示的階段所有者執行），並在同一 commit 以 `--write` 重建 Ledger，使 `TASKS.md` 恆為當前狀態。**執行分支不得改動 `docs/control-plane/**` 與 `docs/TASKS.md`**；~~push main 前先 `git pull --rebase`~~ → **push main 前先 `git pull --ff-only`**（2026-07-29 修正，理由見下）。分支 merge 時上述路徑若衝突，一律以 main 為準（2026-07-17 前的舊分支載有歷史事件 commit，屬過渡遺留，衝突同樣以 main 為準）。
- **⚠️ 不得在 `--no-ff` merge 之後執行 `git pull --rebase`**：`git rebase` **預設丟棄 merge commit**，會把剛建立的 merge 靜默壓平成線性歷史，且**不報錯**。後果是 merge event 記錄的 `source_sha` 指向一個不在 `main` 上的 orphan commit，`Reviewed-by` trailer 隨 merge commit 一併消失（canonical §6 要求 merge commit 帶此 trailer）。
  - **已發生至少三次**：2026-07-26 `INGEST-RECORDS-HR1`（non-ff merge `b8b89bc` 被線性化，實際落地 `78713dc`，見該卡 NOTE 事件）、2026-07-29 `DEV-TRAILER-GUARD-SCOPE1`（merge `cb97be1a` 成 orphan，見 `MERGE-CORRECTION-008`）、2026-08-04 `INGEST-SPLITS-IMPORT-RESTATE1` 一線（`481ca4c` 被線性化壓平至 `57ab9e1`，OPS-STATE-PLANE-MIG1 Task 3 resync 過程中實測發現，內容未受影響、`merge-correction` 事件留痕待補）。第一次已記錄卻未修本契約，故複發；本次改版仍未能根除，留給 Wave 2／`WF-22-CLI1` 評估是否需要工具層強制（例如 pre-push hook 偵測 orphan merge）。
  - **改用 `--ff-only` 的理由**：落後時**明確失敗**而非靜默改寫歷史，由人決定如何處理（rebase 純 event commit、或 `--rebase=merges` 保留拓樸）。fail-loud 優於 fail-silent。
  - **已壓平且已推送時不得重寫 `main`**：改寫已推送的共用歷史比帳面錯誤嚴重得多。正確處置是追加 `merge-correction` 事件，記錄 orphan SHA、實際落地 SHA、內容等價性驗證，以及 `Reviewed-by` attestation 的補位。
- claim concurrency key 為 `cpbl-analytics:<CARD_ID>`；共享資源逐項宣告 `file:*`、`port:*`、`container:*`、`db:*`。預設 lease 4 小時；到期回收前檢查 worktree 與未提交變更，禁止靜默移除。
- WIP limit：agent 4、review queue 3（2026-07-24 自 2／2 上調，以吸收 BUILD1 執行期間的 lane-independent 前端批次；批次清空後回檢，非 lane-independent 卡不得靠此上調繞過車道互斥）；達上限停止新 claim，優先完成 review／release。
- **⚠️ 已實測的共用 `.git` race（OPS-STATE-PLANE-MIG1 Task 3，2026-08-04）**：多個 session（Coordinator／執行者／不同卡的 worktree）共用同一個 `.git`（worktree 機制的設計），並行 `git fetch` 時 `refs/remotes/origin/main` 可能短暫消失（`git rev-parse origin/main` 回 `unknown revision`），重新 fetch 即恢復；不影響已落地的內容，純屬遠端追蹤 ref 更新的競態，**目前無工具層防護**，腳本／人工操作遇到此錯誤訊息時重試一次即可，不必視為資料損毀。

### 交付→查核→合併慣例（2026-07-25 定案）

canonical §2.1「實作與審核分離」不變：執行者不得查核或 merge 自己的變更。本節只固定
**查核之後**的操作分工，消除「每卡逐次請示」的往返。

- **查核提示詞由腳本產生，不向執行者索取**：`uv run python scripts/review_prompt.py <CARD_ID>`
  （可接 `| pbcopy`）。它讀該卡**最新 handoff event** 與卡片的驗收條件／驗證章節，
  自動帶入分支、`source_sha`、worktree、tier、`db_scope` 與獨立性要求。執行者只需把
  交付摘要寫進 handoff `evidence`（本來就是必填），不必另外產出提示詞。
- **APPROVE 即 merge，不再逐次請示**：查核回 APPROVE 且**零阻塞 finding**（INFO／
  非阻塞不算）時，Coordinator 直接以 `--no-ff` merge 並寫 merge＋release 事件，
  無須再向需求方請求合併授權。merge 者仍不得是該卡執行者；**例外依 canonical
  §2.1（WF-18）**：APPROVE／必要 sign-off 完成後、需求方明確授權時，執行者可代行
  merge 機械操作，merge commit 必帶 `Reviewed-by`、merge 事件必記授權來源——授權
  只豁免「誰按下 merge」，不豁免查核。**此慣例對程式碼 PR 的合併機制不變**（Issues/
  Projects 遷移只動卡狀態面，不動 git／PR 機制，見 §0 表格「程式碼 remote coordination」列）。
- **release 必以終態落地＋結案清單**（WF-18，canonical §0＋[`worktree-lifecycle.md`](../.ai-workflow/templates/worktree-lifecycle.md)）：
  免部署卡 release 即 `🏁完成`，需部署卡在部署 `✅已驗證` 前不得 release；結案
  五步（終態事件→卡檔封存→Ledger 重建→lease／分支清理→對帳三件套）缺一不可，
  **代 Coordinator 結案的查核者同樣適用**，無法完成即明確交回、不得停在中間態。
- **`occurred_at` 取寫入當下系統時鐘**（WF-18，canonical §4.1）：寫 event 前先
  `date "+%Y-%m-%dT%H:%M:%S+08:00"`，禁估算、遞增推定或沿用前值。
- **例外必須停下請示**（下列任一成立時，APPROVE 也不自動 merge）：查核含
  blocking／major finding；merge 有衝突或需 rebase 重驗；卡片 `db_scope` 為
  `schema`／`data-migration`；或卡面標記需求方 sign-off。
- **結果回傳原執行者**：merge 後由 Coordinator 將 merge_sha、findings 與後續待辦
  回傳原執行者；由**執行者**向需求方確認是否部署及其他後續（部署狀態轉態仍照
  `AI_RUNBOOK.md` §7，需求方裁定）。只有 preflight 通過、查核有效且結論為
  `REQUEST_CHANGES` 才退回原執行者、原分支並增加 iteration；`preflight-failed`、
  `review-invalid` 與外部阻塞不消耗 iteration 或 escalation 額度。
- **查核者重跑不得污染交付 artifact**：交付物含可重生成檔案（報告 JSON、快照）時，
  查核者重跑須以 `--out` 導向 scratch 路徑；若已覆寫，以 `git checkout -- <path>`
  還原受查版本後再繼續（受查 artifact 是已提交版本，不是重跑產物）。
- **基線版本查核防線**（WF-17，canonical [`baseline-cascade.md`](../.ai-workflow/templates/baseline-cascade.md)）：
  查核 Initiative 子卡時，核對卡面 `spec 基線` 版本＝父卡當前版本，不一致即退回
  （防舊基線交付）。`review_prompt.py` 自動帶入父卡當前基線版本屬工具層強化，
  因 `file:scripts/review_prompt.py` 由 OPS-PROCESS-GUARD1 認領互斥，
  待該卡結案後以 follow-up 落地；落地前由查核者手動核對。

### 權限與事故處理

- 只有 protected `main` 的部署 workflow 可操作 production；外部協作者可提交 PR／review evidence，不可自行 claim、release、merge 或改寫 event log。
- GitHub 不可用時停止 claim／handoff／merge／release；本機鎖不可推進 card state。恢復後由 Coordinator 對帳並補 telemetry。
- claim、handoff、review、merge、release 後執行 `git worktree list`、檢查 local leases，並跑 `uv run python scripts/workflow_ledger.py --check`。

---

## §2 新狀態面（cutover 後生效——目前是目標狀態的權威描述，尚未生效）

### 卡狀態與看板

- **卡狀態＝GitHub Issue**：每張活卡對應 repo `ruan6047/cpbl-analytics` 一個 Issue（一次性遷移由
  `scripts/state_plane_migrate.py` 建立，見對帳表 `docs/research/OPS-STATE-PLANE-MIG1_reconciliation.md`）。
  Issue open／closed 對應卡是否仍在途；body 含 spec 檔連結、遷移當下現況摘要、
  fenced JSON 資源宣告區塊（`db_scope`／`resources`，見 Task 1 對照表的取捨：資源宣告
  刻意不建 Project 欄位，因開放式檔案路徑會撞 single-select／multi-select 的選項配額，
  結構化 body 才是機器可讀又不佔額度的解法）。
- **看板＝Project v2「cpbl-analytics 任務看板」**：12 個凍結欄位（卡ID／Initiative／
  級別／功能／owner／分支worktree／iteration／交付狀態／部署狀態／最後交接／
  服務的原始目標／鏈深），型別與選項域見 Task 1 對照表；**最後交接用 TEXT 存完整
  ISO-8601（字典序即時序），不用原生 DATE 欄位**（DATE 型別實測會靜默截斷時分秒與
  時區，2026-08-04 Task 1 實測發現、需求方裁決採 TEXT 方案）。
- **祕書單寫入通道**（決議 1）：Issue 狀態轉換、Project 欄位寫入、disposition comment
  一律由 PM 祕書 session 執行；執行者／查核者對狀態面唯讀，需要轉態時經需求方或
  祕書代寫，不得自行操作 Issue／Project（避免決策與機械寫入分散、失去單一事實
  來源的可信度——這正是決議 1 要解決的「法理集權、實務失守」）。

### 審核契約：結構化 comment

- 審核結論以 **Issue 上的結構化 comment**（非事件，非 events.jsonl 條目）留痕，欄位對應
  §1 review 事件的核心語意（`review_result`／`findings`／`attempt_id`／`escalation_epoch`
  等）——**確切 schema 與型別驗證機制屬 Wave 2／`WF-22-CLI1` 實作範圍，本次改版只
  定調「結構化 comment 取代 events.jsonl review 事件」這個方向，不在此重新設計整套
  finding／escalation 計數細則**（那套規則歷經 WF-17／WF-18／WF-20／WF-21 多輪才成形，
  一次性遷移任務不適合順手重新發明）。
- **WF21-R-13 翻案／correction 概念併入**：§1 的 `review-correction` 事件（用
  `corrects_event_id` 指名並裁決同輪內較早的 review／finding 衝突）在新狀態面對應
  **一則新 comment 明確引用（回覆或指名）被更正的舊 comment**，同樣遵守「不得改寫
  已發表的 comment 本體」（GitHub comment 技術上可編輯，但契約層面視同 append-only，
  更正必須是新 comment，不得就地改字——與 events.jsonl append-only 精神一致）。此為
  `DEV-REVIEW-DEACCEPT-TRAIL1`（WF21-R-13，已封存）原始需求的收容處，該卡本身不再
  需要獨立事件載體。
- **不計數／中繼關卡等 §1 既有語意**（`closes_review_round`、`review_independence`
  職權劃分）**維持概念不變**，具體如何在 Issue comment 上表達（例如用固定前綴、
  label、或 comment 內結構化欄位標記）屬 Wave 2 實作細節，本次不預先鎖定格式。

### events.jsonl 的終局地位

> ✅ 本節條件已於 2026-08-04 `8271d7c` 觸發：終筆事件已寫入，封存生效。

- **cutover 宣告後，`events.jsonl` 封存唯讀**：不再接受任何新 lifecycle event（append
  也不行——封存即凍結內容，不是「只是變慢」）；**不得刪除**（紅線 3），檔案與其
  git 歷史永久保留供稽核。
- cutover 宣告**前**，本節（§2）不生效，`events.jsonl` 依 §1 規則繼續作為唯一事實
  來源正常運作、正常寫入。**Issue 建立≠切換**：即使 Issue／Project 已存在且資料
  正確（Task 2／3 已完成遷移＋resync），在需求方明示宣告 cutover 之前兩者是**影子
  關係**——Issue 側資料僅供可視化與驗證，任何撞卡／狀態判斷仍須以 `events.jsonl`
  為準（紅線 1）。
- cutover 宣告由需求方執行，宣告後由 PM 祕書寫入終筆封存事件（`docs/control-plane/
  events.jsonl` 最後一筆，標記封存原因與宣告來源），該事件之後本檔 §1 全段轉為
  historical reference，§2 轉為生效中的唯一機制。

### 已知待決（Wave 2／`WF-22-CLI1` 範圍，本次改版不產出，如實列出而非靜默略過）

- Issue open/closed 狀態與「交付狀態」欄位的同步策略（現況：🏁完成卡 Issue 維持 open、僅欄位標終態——dispose 刻意只處理 🛑已停止以避免不實留言；是否收斂由 Wave 2 決定）。

- 結構化 review comment 的確切 JSON schema／型別驗證機制（對應 §1 的 REQUIRED_FIELDS／
  FINDING_FIELDS／escalation 計數規則如何在 Issue comment 上重建）。
- WIP limit（agent 4／review queue 3）在新狀態面的機械執行機制（§1 靠人工對照
  `TASKS.md`；新狀態面理論上可用 Project 篩選視圖或祕書 CLI `doctor` 指令核對，
  但尚未實作）。
- claim concurrency（`file:*`／`port:*`／`container:*`／`db:*` 資源互斥）的機械比對——
  Task 1 已驗證 Issue body fenced JSON 可承載資源宣告，但「祕書派工時自動比對本卡
  寫入集 × 現役卡寫入集交集」（決議 3）的比對程式尚未寫，屬 `WF-22-CLI1` 範圍。
- schema-repair（§1 的就地修復程序）在 Issue comment 情境下的對應程序——GitHub
  comment 的編輯歷史與 events.jsonl 的 git 歷史特性不同，需要重新評估同一套四項
  紅線是否適用或需要調整。
- 祕書每日 snapshot export 回 git 的確切格式與路徑。
