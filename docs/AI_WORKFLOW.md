# AI 協作工作流（cpbl-analytics 採用）

> **2026-08-04 新治理全面生效（WF-22 Wave 0/1/2 完結）**：作業狀態唯一事實來源＝
> **GitHub Issues＋user Project #4「cpbl-analytics 任務看板」**；唯一狀態寫入通道＝
> ai-workflow repo 的 **`wfcli`**（`cli/`）。`docs/control-plane/events.jsonl` 與
> `docs/TASKS.md` 投影**已封存唯讀**（終筆 `8271d7c`）——不得再追加事件或重建 Ledger。
> 決策（開卡／派工／merge／結案）＝需求方本人；機械寫入＝PM 祕書 session 專責。
> **canonical v2（2026-08-05）為唯一權威正文**；
> [`research/WORKFLOW-REVIEW-2026-08-04.md`](research/WORKFLOW-REVIEW-2026-08-04.md) 為決議沿革紀錄。

> **完整規則見 canonical（submodule）：[`../.ai-workflow/AI_WORKFLOW.md`](../.ai-workflow/AI_WORKFLOW.md)**（唯一權威來源；規則改動在 [ruan6047/ai-workflow](https://github.com/ruan6047/ai-workflow)）。既有專案升級依 [`../.ai-workflow/MIGRATION.md`](../.ai-workflow/MIGRATION.md)。
> 本專案任務看板見 **GitHub Issues＋[user Project #4「cpbl-analytics 任務看板」](https://github.com/users/ruan6047/projects/4)**（[`TASKS.md`](TASKS.md) 為 2026-08-04 cutover 的封存快照，唯讀、不再是投影），控制平面見 [`CONTROL_PLANE_CONTRACT.md`](CONTROL_PLANE_CONTRACT.md)，新卡範本索引見 [`TEMPLATES.md`](TEMPLATES.md)，資料庫與部署操作分別見 [`DATABASE_CONTRACT.md`](DATABASE_CONTRACT.md) 與 [`AI_RUNBOOK.md`](AI_RUNBOOK.md) §7。模型選擇見 [`MODEL_ROUTING.md`](MODEL_ROUTING.md)。

## 核心鐵律（速查）

1. **變更分級 + 部署閘門**：依 canonical T0–T4 按風險、範圍、可逆性選閘門；T2 以上程式碼（A 類）每卡開分支，每卡／卡族有獨立 worktree；只有已審核合併至 `main` 的提交可部署。
2. **實作／審核分離**：同一張卡的執行與查核須由不同經手者；查核發現缺陷以 PR review／event 留 finding，原執行者在原分支修正，查核者不得改 source branch。卡面／baseline／SHA／依賴等 preflight 失敗不建立 review、不增加 iteration；第三個可計數實質退回先進 escalation checkpoint，只有重複根因、舊 finding 未修或需求方裁定才轉 `🚨已升級`（canonical [`review-escalation.md`](../.ai-workflow/templates/review-escalation.md)）。有效但不計數的 review 仍可閉合 finding；同 attempt finding 衝突須以 `review-correction` 裁決，epoch 切換須有需求方明示授權。查核結論統一用 `APPROVE | REQUEST_CHANGES`（`core_pain_resolved` 與 `self_run` 必填——**無 `self_run` 的 APPROVE 無效**，canonical §5.2）；舊的自由文字 `REJECT` 不得用於 WF-21 baseline 後新事件。**查核第一判準＝核心痛點是否消失，具否決權**（canonical §5.1）。
3. **紅線獨立性**：安全、金流、統計／ML、資料正確性、資安部署與 production migration 一律 T4；review 必換模型家族或人工，且須附實測證據與必要 sign-off。
4. **Discovery → Design → Plan**：T3/T4 先確認問題、證據與成功條件；使用者可見的 T3/T4 卡必過 Design Gate，純技術 T3/T4 卡必記錄 Design Gate `N/A` 理由；大型工作以 Initiative 管理 spec 基線、依賴、里程碑與變更。
5. **聯邦式控制平面**：GitHub remote coordination 管 task、review、lease、CI；local resource lock 管 worktree／port／container；event log 是歷史，Ledger 是投影，不可各自手改。
6. **留痕**：T0/T1 commit 至少 `Requested-by`、`Implemented-by`；T2 以上實作 commit 再加 `Planned-by`；merge、PR 結案或 B2 權威文件核可再加 `Reviewed-by`。
7. **驗證與封存**：先讀再說、不虛構 API／表／指令；secrets 永不進 git；交付須附改動、原因與實測。需部署的卡僅在驗證成功後可 `🏁完成`，失敗／回滾不得封存。
8. **卡範圍與鏈式停損**：一根問題一張卡（卡內多個窄寫入授權）；每卡必填「服務的原始目標」，鏈深硬上限＝原始目標下 2 層，全域問題脫鏈獨立卡（canonical §2.11–2.12／§3.2–3.3）。
9. **三級閘門**：Initiative／不可逆 T4 同步 grilling；T3 核心痛點三問批註放行；T2+ 前提逐條附實查證據（canonical §3.1）。
10. **資源與 worktree**：派工前寫入集交集檢查（`file:`／`db:` 宣告；**merge 後 file 資源即釋放**、`📦已合併` 仍佔活卡）；worktree 註冊制＋doctor 對帳（canonical §4.4–4.5）。
11. **派工包六條**：範圍外發現回報 PM 禁 spawn_task／不停等背景通知／禁 `gh pr update-branch`／詭異數據人工判讀＋新聞佐證四約束（僅定性、官方數值權威、URL＋日期、第三方泛化）／trailer 連續單一區塊／CLI 探索紅線（[`dispatch-package.md`](../.ai-workflow/templates/dispatch-package.md)）。**本專案當前仍有副作用的 CLI 入口：`cpbl-refresh-recent`（連 `--help` 都會觸發每日鏈）；此限制仍在，但 Gate 3 已於 2026-08-03 提前收窗並解除 G4 凍結，修正 `--help` 行為的前置條件已滿足**（[`INGEST-GAME-TM-REFACTOR1-G4.md`](tasks/INGEST-GAME-TM-REFACTOR1-G4.md) L21、L362）。

決策（開卡／派工／merge／結案）＝需求方本人；機械寫入、派工包組裝與查核詞產製＝PM 祕書 session（canonical §1.1，Coordinator 職責由該 session 承擔）。同一卡的執行者不得兼任查核者：一般卡查核以新 context／session 為獨立即可，紅線卡須換模型家族或人工審核。

---

## 入口路由稽核（`DOC-ENTRY-ROUTING1` #140，2026-08-19）

### 入口文件指向清單（機械抽取，非人工聲明）

下表由 `CLAUDE.md` 機械抽取全部文件指向並逐一驗存在性，是該卡驗收條 3 的可稽核產物。
**重跑方式**：對 `CLAUDE.md` 抽 markdown link 與反引號路徑，存在性以 `git ls-files` 判定
（**不可用檔案系統**——`.venv/`、`data/`、`artifacts/` 等禁 commit 目錄會被本機工具生成，
用 `os.path.exists` 會把它們誤判為實存）。

<!-- 由 CLAUDE.md 機械抽取（markdown link ＋ 反引號路徑）；共 25 個指向：
     16 個 git 已追蹤，9 個不在本 repo 且已逐一查證非壞路由。
     存在性以 git ls-files 判定，不用檔案系統——.venv/ 等禁 commit 目錄會被本機工具生成。 -->

| 指向 | CLAUDE.md 行 | 存在性 | 備註 |
|---|---|---|---|
| `.ai-workflow/AI_WORKFLOW.md` | 5 | — 不在本 repo | submodule 內容；主 checkout 實存（本 worktree 未 init） |
| `.venv/` | 213 | — 不在本 repo | 禁 commit 清單（git 未追蹤；uv 會在本機生成） |
| `00X_description.sql` | 121 | — 不在本 repo | migration 檔名慣例，非實檔 |
| `_browser.py` | 189 | ✅ git 已追蹤 | 解析為 `src/cpbl/ingest/_browser.py`；最後改動 2026-07-04 |
| `apps/subprojects/cpbl-analytics/` | 14 | — 不在本 repo | 主站掛載路徑，非本 repo |
| `artifacts/` | 213 | — 不在本 repo | 禁 commit 清單（git 未追蹤） |
| `data/` | 213 | — 不在本 repo | 禁 commit 清單（git 未追蹤） |
| `discovery-brief.md` | 221 | — 不在本 repo | canonical `templates/` 內容；主 checkout 實存 |
| `docs/AI_RUNBOOK.md` | 3,224 | ✅ git 已追蹤 | 最後改動 2026-08-19 |
| `docs/AI_WORKFLOW.md` | 5 | ✅ git 已追蹤 | 最後改動 2026-08-19 |
| `docs/CPBL_SITE_MAP.md` | 175,190 | ✅ git 已追蹤 | 最後改動 2026-07-30 |
| `docs/DATABASE_CONTRACT.md` | 5 | ✅ git 已追蹤 | 最後改動 2026-08-19 |
| `docs/MODEL_ROUTING.md` | 5 | ✅ git 已追蹤 | 最後改動 2026-08-19 |
| `docs/ROADMAP.md` | 6 | ✅ git 已追蹤 | 最後改動 2026-08-14 |
| `docs/SUB_PROJECT_GUIDE.md` | 167 | — 不在本 repo | CLAUDE.md 明標「主站」；PersonalWebsite repo 內實存 |
| `docs/TASKS.md` | 5 | ✅ git 已追蹤 | 最後改動 2026-08-05 |
| `docs/reference/GLOSSARY.md` | 222 | ✅ git 已追蹤 | 最後改動 2026-08-10 |
| `features/outcome.py` | 145 | ✅ git 已追蹤 | 解析為 `src/cpbl/features/outcome.py`；最後改動 2026-08-05 |
| `https://github.com/users/ruan6047/projects/4` | 5 | — 不在本 repo | 外部 URL（本卡新增） |
| `ingest/_browser.py` | 181 | ✅ git 已追蹤 | 解析為 `src/cpbl/ingest/_browser.py`；最後改動 2026-07-04 |
| `migrations/` | 121 | ✅ git 已追蹤 | 最後改動 2026-08-08 |
| `models/matchup.py` | 95 | ✅ git 已追蹤 | 解析為 `src/cpbl/models/matchup.py`；最後改動 2026-08-05 |
| `models/outcome.py` | 137 | ✅ git 已追蹤 | 解析為 `src/cpbl/models/outcome.py`；最後改動 2026-06-26 |
| `models/outcome_gbm.py` | 96 | ✅ git 已追蹤 | 解析為 `src/cpbl/models/outcome_gbm.py`；最後改動 2026-08-05 |
| `train.py` | 132 | ✅ git 已追蹤 | 解析為 `src/cpbl/models/train.py`；最後改動 2026-08-05 |

**核對深度（誠實界定）**：本表證明的是**存在性**與**最後改動時間**。
「CLAUDE.md 對每份文件的描述是否仍為真」只做到**章節層級**核對——即確認被描述的主題
確實構成該檔的章節（例：`AI_RUNBOOK.md` 確有指令速查／資料流／同步／API 與 web 地圖／
陷阱各章），**未逐條核對其內容與現實相符**。逐條核對等同重驗整份 Runbook，不在本卡射程。
本輪唯一被判為**假**並已修正的描述是「活卡 Ledger 見 `TASKS.md`」（該檔已於 2026-08-04 封存）。

### 本卡明確「不做」的四項與理由

依「流程會不會執行」判準逐項查證，四項皆**無受害者或不屬本卡射程**，故不做：

1. **`wfcli doctor` 對 cutover 後 cpbl 的失能** — 流程確有要求，但修正點在上游
   `ai-workflow` repo，不在本卡宣告的五個檔案內。
2. **`.wfcli.json` 缺失** — 原判「3 張 smoke 卡不在板是漏 `--repo` 所致」經查為**誤**：
   那些是拋棄式 smoke 卡，本就不該在板，故無受害者。
3. **卡面缺四個標頭欄位** — `card.render_issue_body` 根本不輸出這四欄，屬上游結構性
   drift，非本專案文件問題。
4. **卡面標題兩種格式混用** — 實測 **0 張**解不出 `card_id`，無受害者。
