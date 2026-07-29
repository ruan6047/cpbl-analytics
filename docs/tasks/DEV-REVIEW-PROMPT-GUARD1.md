# DEV-REVIEW-PROMPT-GUARD1 查核提示詞產生器的三處錯誤指引〔T2；🟡工具〕

- 需求：ruan6047（2026-07-29 為 `UX-ENTITY-LINKS2` 產生查核提示詞時實地發現）　規劃：本卡 spec　分支：`ai/<執行者>/DEV-REVIEW-PROMPT-GUARD1`
- 執行：待指派（建議 L2；已知模式的工具修正，三個判準已由需求方界定）　查核：待指派（建議 L2；≠ 執行。本卡改的是查核流程本身的工具，查核者須實跑產出物比對契約，不得只讀 diff）
- Initiative：—　spec 基線：—
- DB：`db_scope: none`
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍：`scripts/review_prompt.py`＋`tests/test_review_prompt.py`
- Discovery：—（T2，問題與判準已由需求方於卡面界定）
- Design：Design Gate N/A——無使用者可見介面，產出物只給查核者讀。
- owner、worktree、iteration、最後交接與交付／部署 current-state 見 [`../TASKS.md`](../TASKS.md) Ledger。

## 問題陳述

`scripts/review_prompt.py` 是查核提示詞的唯一產生器（`CONTROL_PLANE_CONTRACT.md`〈交付→查核→合併慣例〉：**不向執行者索取提示詞**）。它產出的東西看起來完整，但在特定情境下**悄悄給錯指引，而且不會報錯**——查核者照著做就會走進錯的環境、跑錯的指令、或用比卡面寬鬆的獨立性標準接下工作。

三處缺陷都是 2026-07-29 為 `UX-ENTITY-LINKS2`（前端卡、T2、分支 `ai/opus-5/UX-ENTITY-LINKS2`）產生提示詞時實地發現。

### 缺陷 1：叫查核者進駐執行者的 worktree（最嚴重）

現行輸出「進駐 worktree：`<執行者的 worktree 路徑>`（指令在此目錄執行）」。

這**直接違反** [`../HANDOFF_CONTRACT.md`](../HANDOFF_CONTRACT.md) §3 receiver acceptance checklist：該檔明訂「**查核環境隔離**：以 `git worktree add --detach <path> <完整SHA>` 建立獨立 detached worktree，`git status` 乾淨、`HEAD` 等於 `source_sha`。**不得在執行者的 worktree 上查核**」，§5 另給了指令與路徑慣例（`.claude/worktrees/<card-id小寫>-review`）。

在執行者 worktree 上查核會失去隔離：該目錄可能有未提交變更、分支可能已被執行者推進、查核者重跑產生的檔案會污染交付 artifact。**契約寫了、工具卻教相反的事**，而工具是實際被照著執行的那一份。

### 缺陷 2：重現指令硬編為 Python

現行輸出固定兩行 `uv run ruff check` / `uv run pytest -q`。對改動集中在 `web/` 的前端卡，這**完全是錯的指令**——`ruff` 與 `pytest` 掃不到任何前端改動，跑完全綠也證明不了任何事。正確是 `cd web && npm ci && npm run build:check && npm test`。

腳本應依 handoff 的**實際改動路徑**（或卡面範圍）判斷卡片型態（Python／前端／混合／純文件），輸出對應指令。

另有一個必須主動排除的坑：**本專案未設定 ESLint**（`web/` 下無任何 eslint 設定檔），`package.json` 的 `lint` 腳本是 `next lint`，跑下去會進**互動式初始化精靈**。查核者若把它當成「標準前端驗證指令」執行，得到的是一個卡住的 prompt，而非驗證失敗——提示詞應主動聲明不要跑，以免誤開 finding。

### 缺陷 3：獨立性要求只依 tier 推導，忽略卡面

現行 `indep` 只看 tier：T4 → 「跨模型家族或人工」，其餘 → 「新 context／session 即可」。

`UX-ENTITY-LINKS2` 是 T2，卡面〈查核〉欄卻寫「≠ 執行；**跨家族或人工**」——卡面比 tier 推導值嚴格。腳本產出的提示詞說「新 context／session 即可」，等於**用工具把需求方寫在卡面的要求稀釋掉**，而且沒有任何訊號顯示這件事發生了。

腳本應讀卡面〈查核〉欄，取「tier 推導值」與「卡面要求」的**較嚴者**。

## 共同結構（為什麼三件事放同一張卡）

三處都是同一型：**檢查／輸出一個容易取得的相關量，而非該成立的性質**。

- 該成立的性質是「查核在隔離環境進行」，工具卻輸出了手邊現成的執行者 worktree 路徑。
- 該成立的性質是「跑得到這次改動的驗證指令」，工具卻輸出了寫死的預設值。
- 該成立的性質是「獨立性不低於卡面要求」，工具卻只算了 tier 這個容易算的分量。

與同批的 `DEV-TRAILER-GUARD-SCOPE1`、`DEV-VERIFY-TM-ASSERTS1`、`OPS-BACKUP-EMPTY1` 是同一族缺陷；症狀同樣是**在真正要它把關的情境靜默失效**。

## 紅線（違反即退回）

1. **不得以「查核者自己會知道」收場**。三處都必須由產出物本身承載正確指引；「反正查核者讀過契約」正是這張卡在修的東西。
2. **判不出來就要吵**。型態判定（缺陷 2）與卡面〈查核〉欄解析（缺陷 3）都可能遇到解析不出的輸入；此時**不得靜默退回預設值**，必須在提示詞裡明白標示無法判定與其原因，讓讀的人知道要自己決定。輸出比現況「錯得安靜」更差的東西即退回。
3. **獨立性只可升不可降**：任何情況下產出的獨立性要求不得低於 tier 推導值，也不得低於卡面〈查核〉欄的字面要求。卡面原文須原樣附在提示詞裡供人覆核，不可只留腳本的分類結論。
4. 不得順手改寫 `HANDOFF_CONTRACT.md`／`CONTROL_PLANE_CONTRACT.md` 的規則來遷就實作——本卡是工具對齊契約，不是契約對齊工具。

## 驗收條件

- [ ] 缺陷 1：產出物含建立 **detached 查核 worktree** 的可直接複製指令（`git worktree add --detach .claude/worktrees/<card-id小寫>-review <完整40字元SHA>`），並含 `HEAD` 等於 `source_sha`、工作區乾淨的自我驗證步驟與用畢清理指令。執行者 worktree 若仍出現在輸出中，須明確標示**僅供對照、不得進駐**。
- [ ] 缺陷 2：依改動路徑判定卡片型態並輸出對應指令——Python 卡 `uv run ruff check` ＋ `uv run pytest -q`；前端卡 `cd web && npm ci`＋`npm run build:check`＋`npm test`；混合卡兩組都出；純文件卡明講沒有標準重現指令、依卡面〈驗證〉走。
- [ ] 缺陷 2 附帶：前端指令區塊含「**不要跑 `npm run lint`**」的明確聲明與理由（未設定 ESLint、會進互動式精靈、不得據此開 finding），並提醒新建 worktree 無 `node_modules`，`npm ci` 不可略過（略過會使型別檢查全紅，是假象非缺陷）。
- [ ] 缺陷 3：讀卡面〈查核〉欄，輸出 tier 推導值與卡面要求的**較嚴者**，並附卡面原文。以 `UX-ENTITY-LINKS2`（T2＋卡面「跨家族或人工」）實測，輸出須為跨家族或人工。
- [ ] 三處的無法判定路徑都有明示輸出（紅線 2），且不會使腳本靜默改用預設值。
- [ ] `uv run ruff check` ＋ `uv run pytest` 全綠；`tests/test_review_prompt.py` 補上涵蓋三處的迴歸測試。

## 驗證

- [ ] 查核者對**至少三張型態不同的既有卡**實跑 `uv run python scripts/review_prompt.py <CARD_ID>`（例如前端卡 `UX-ENTITY-LINKS2`、Python 卡任一張已交付的 `INGEST-*`／`ML-*`、以及一張改動橫跨兩者者），逐張確認輸出的 worktree 指令、重現指令與獨立性要求三項皆正確。
- [ ] 查核者確認產出的 detached worktree 指令**可直接執行成功**（含路徑已存在時的處置說明），且執行後 `git rev-parse HEAD` 等於 handoff 的 `source_sha`。
- [ ] 查核者構造一張卡面〈查核〉欄缺席或寫法不在辨識清單內的情形，確認輸出走的是「明示無法判定」而非靜默預設。
- [ ] 查核者確認既有的四道拒絕產生提示詞的守衛（無 handoff、review 已 supersede、SHA 無法解析、SHA ≠ 分支 HEAD）與 spec 基線一致性段落未被本次改動破壞。

## 邊界

- 只動 `scripts/review_prompt.py` 與其測試；不改契約文件、不改 `workflow_ledger.py`、不改事件 schema。
- 卡片型態判定不必做到完美分類；紅線是**判不出來要講**，不是猜得準。
- 預估 S。

## Log

- 2026-07-29 register by Claude Opus 5@Claude Code（Coordinator，依 ruan6047 於 `UX-ENTITY-LINKS2` 查核提示詞產生時的實地發現）；iteration 0。三個缺陷與判準由需求方界定，卡面照錄。
