# Control-plane Contract — cpbl-analytics

> 共同不變量見 canonical [`../.ai-workflow/AI_WORKFLOW.md`](../.ai-workflow/AI_WORKFLOW.md) §4.1。本檔將跨人協作狀態與本機資源鎖分離；不得填入 token、secret 或個資。

## Adapter 邊界

| 範圍 | 實作 | 事實來源／用途 |
|---|---|---|
| Remote coordination | GitHub protected `main` + `ruan6047` 操作的 PR／Actions | 唯一 lifecycle writer；task、review、lease、CI |
| Local resource | `/private/tmp/cpbl-analytics-control-plane/<CARD_ID>/lease.json` 原子目錄鎖 | worktree、port、container、DB namespace 暫時互斥；僅 telemetry |
| Event store | [`events.jsonl`](control-plane/events.jsonl) 的 append-only Git history | 不可覆寫 lifecycle 歷史 |
| Ledger projection | `uv run python scripts/workflow_ledger.py --write` | [`TASKS.md`](TASKS.md) current-state；禁止手改 |

## Event、claim 與 WIP

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
  1. **可改欄位為正面表列，白名單之外一律禁止**（機器可讀，非文字約定）：
     事件層僅 `counts_toward_escalation`；finding 層僅 `severity`／`status`／`finding_class`／
     `attribution`。**不得新增或移除 finding。** 其餘全部禁止，包含但不限於
     `review_result`／`evidence`／`disposition`／`actor`（判定與歸屬）、
     `blocking`／`accepted`／`root_cause_id`（finding 的實質判定）、
     `source_sha`／`attempt_id`／`escalation_epoch`／`preflight_passed`／`event_id`／`card_id`
     （身分與目標）——動它們是改寫歷史，不是修復格式。
     > 本項初版寫「列舉值、推導布林、**缺漏的必填欄位**」，第三項無界限：跨家族查核實測可藉
     > 「補缺漏欄位」之名補入或重定義 `source_sha`／`attempt_id`／`escalation_epoch`／
     > `preflight_passed`／`accepted`／`blocking`／`root_cause_id`，並可把 `review_result` 改成
     > `APPROVE`（schema 驗證只查列舉值，不查語意）。故改為正面表列。
  1b. **修復 diff 須以工具驗證，不得只靠人工閱讀 commit**：
     `workflow_ledger.diff_schema_repair(before, after)` 回傳逾越白名單的欄位路徑，
     **非空即為不合法的修復**。查核者應以此複驗，而非逐行讀 commit message。
  2. **修復事由須就地留痕**：於被修欄位所屬的 `disposition`／`evidence` 前綴加註
     `[schema 修復 YYYY-MM-DD：原 X=… 非合法值，已改為語意等價的 Y；判定內容未變。]`。
  3. **commit message 須說明**修了哪些欄位、為何無法以追加事件修復、以及原始壞行仍保留於哪個 commit。
  4. **不得 force-push**：修復是一個新 commit，git 歷史保留原始壞行。
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
  - **已發生兩次**：2026-07-26 `INGEST-RECORDS-HR1`（non-ff merge `b8b89bc` 被線性化，實際落地 `78713dc`，見該卡 NOTE 事件）、2026-07-29 `DEV-TRAILER-GUARD-SCOPE1`（merge `cb97be1a` 成 orphan，見 `MERGE-CORRECTION-008`）。第一次已記錄卻未修本契約，故複發。
  - **改用 `--ff-only` 的理由**：落後時**明確失敗**而非靜默改寫歷史，由人決定如何處理（rebase 純 event commit、或 `--rebase=merges` 保留拓樸）。fail-loud 優於 fail-silent。
  - **已壓平且已推送時不得重寫 `main`**：改寫已推送的共用歷史比帳面錯誤嚴重得多。正確處置是追加 `merge-correction` 事件，記錄 orphan SHA、實際落地 SHA、內容等價性驗證，以及 `Reviewed-by` attestation 的補位。
- claim concurrency key 為 `cpbl-analytics:<CARD_ID>`；共享資源逐項宣告 `file:*`、`port:*`、`container:*`、`db:*`。預設 lease 4 小時；到期回收前檢查 worktree 與未提交變更，禁止靜默移除。
- WIP limit：agent 4、review queue 3（2026-07-24 自 2／2 上調，以吸收 BUILD1 執行期間的 lane-independent 前端批次；批次清空後回檢，非 lane-independent 卡不得靠此上調繞過車道互斥）；達上限停止新 claim，優先完成 review／release。

## 交付→查核→合併慣例（2026-07-25 定案）

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
  只豁免「誰按下 merge」，不豁免查核。
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

## 權限與事故處理

- 只有 protected `main` 的部署 workflow 可操作 production；外部協作者可提交 PR／review evidence，不可自行 claim、release、merge 或改寫 event log。
- GitHub 不可用時停止 claim／handoff／merge／release；本機鎖不可推進 card state。恢復後由 Coordinator 對帳並補 telemetry。
- claim、handoff、review、merge、release 後執行 `git worktree list`、檢查 local leases，並跑 `uv run python scripts/workflow_ledger.py --check`。
