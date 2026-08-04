# DEV-EVENT-REPAIR-ANCHOR1 schema-repair 的歷史證據不可偽造〔T3；🟡流程〕

- 需求：ruan6047（2026-08-03 依 `DEV-EVENT-SCHEMA-GUARD1` 的 `replan` 承諾拆卡）　規劃：GPT-5.6@Codex（2026-08-04 修訂 spec）　分支：`ai/<執行者>/DEV-EVENT-REPAIR-ANCHOR1`
- 執行：Claude Opus 5@Claude Code（需求方指定；**尚未認領**，建議 L3）　查核：待指派（建議 L2；跨家族，≠ 執行）
- Initiative：—　spec 基線：本卡 revision 2（取代 `3590b47` 的 revision 1）
- review_independence: [cross_family]
- DB：`db_scope: none`
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍：`scripts/workflow_ledger.py`、`tests/test_workflow_ledger.py`、`docs/CONTROL_PLANE_CONTRACT.md`；必要時 `.github/workflows/ci.yml` 僅為保證完整 Git 歷史。**動工前阻塞：** 現有 direct-main 流程沒有機械保證 post-commit `--check` 先於 push，須先由需求方裁定 enforcement model。
- Discovery：已完成。Design Gate N/A——純 control-plane 稽核契約，沒有使用者可見介面。

## 問題陳述

`schema-repair` 是 append-only event log 無法表達「壞 schema 行必須就地修正」時的唯一窄例外。現行 `_validate_schema_repair_event()` 只驗 `after == log 現況`，`before` 則完全由修復者宣告。

跨家族查核的 F005 已實證這不是理論缺口：對真實 `UX-LIVE-GAME1-REVIEW-008`，保持正確的 `after`，只把 `before.findings[0].status` 捏造成 `rejected`，驗證器仍接受。因此它能證明現在的結果，卻不能證明修復曾有必要。

本卡要建立的是**歷史證據 [historical evidence]**，不是再增加一個可任填的欄位：每筆未來 repair 必須可由 Git 的兩個相鄰 blob 重現「目標曾為 `before`，且在加入 repair 留痕的同一提交變成 `after`」。

## 設計決策

### 採用 Git 提交對 [commit pair]，不用 payload 內的 repair commit SHA

新的 `schema-repair` 必填 `anchor_parent_sha`。驗證器從目前 `HEAD` 可達的 `events.jsonl` 歷史中找出**最早包含該 repair event ID 且內容與現況完全相同**的提交，稱為 anchor commit；它必須：

- 只有一個 parent，且等於 payload 的 `anchor_parent_sha`；
- parent blob 的 `repaired_event_id` 精確等於 `before`；
- anchor commit blob 的同一 target 精確等於 `after`；
- anchor commit blob 的 repair event 與現行 repair event 完全相同。

`event_id` 必須在現行 log 與兩份 anchor blob 都唯一；若同 ID 出現兩次，歷史查找不猜哪一筆才是目標，直接 fail closed。

這避開自指問題：把 `repair_commit_sha` 寫進 repair event，會要求 event 在「包含自己」的 commit SHA 尚未生成前知道該 SHA；拆成兩個提交又讓修復提交在當下沒有稽核記錄。anchor commit 由歷史反推，而非由 payload 自我宣稱，因此一次提交可同時改 target、追加 audit event 與重建 Ledger。

操作上，Coordinator 在 parent `HEAD` 值已知時填 `anchor_parent_sha`，以顯式的 pending 模式生成 Ledger、提交一次，**提交後、push 前**必跑完整 `--check`；只有 post-commit 驗證成功才可推送。pending 模式只能服務這個「尚未有 anchor commit」的造提交階段，輸出必明示未完成歷史驗證；一般 `--check`、CI 與所有稽核指令不得接受 pending。

### 其他候選不採用

| 方案 | 不採用原因 | 失效邊界 |
|---|---|---|
| 不可變 repair manifest | 在沒有外部簽章的前提下只是第二份可改檔案，增加同步與分叉問題，未增加可信根。 | manifest 與 Git 不一致時沒有仲裁來源。 |
| 事件寫入時內容雜湊 | 對存量無效，且 hash 自己仍可隨事件就地改寫；它可作為摘要，不能單獨證明歷史。 | 未預先帶 hash 的事件永久無法補證。 |
| 任意 Git parent | 只要挑一份可配合的舊 blob，就仍能替合法事件捏造 before。 | 無法證明修復就在該 parent 之後發生。 |

Git 提交對的失效邊界要照實保留：淺複製 [shallow clone]、離線、object 缺失、anchor 不可達或已推送 main 遭惡意歷史改寫時無法建立證據。前四者一律 fail closed；最後一項由 protected `main`／禁止 force-push 承擔，不把單人、非對抗威脅模型誤寫成密碼學保證。

### 鏈與存量規則

- 同一 `repaired_event_id` 允許多筆 repair，但只能形成**線性鏈**：後一筆 anchor parent 中 target 必須精確等於前一筆的 `after`，且每次仍各有自己的 parent／anchor blob 證據。不得有兩筆以同一歷史版本為 before 的分叉 repair。
- 這是刻意保留的二次修復路徑：若先前 repair 已令事件可 replay，之後因 schema 收緊或漏驗欄位才暴露另一個不合法值，仍能修 original target；不得以「只准一次」重新把 log 卡死。
- 一筆 anchor commit 可修多個 target，但每個 target 都必須各有一筆獨立 audit event。
- repair target 必須在 audit event 之前出現，且 type 不得是 `schema-repair`。這直接拒絕 repair→repair、前向參照與循環；不得用「留痕的留痕」逃避稽核。
- repair event 的現行內容必須等於它首次出現的 anchor blob。故它後來被就地改寫，即使 target 未變，也會失敗；既有 event diff guard 是第二道防線，不是此規則的替代品。
- `UX-BRAND-HOME1-REVIEW-007`／`322f69a` 是唯一 `legacy-unverifiable`：列進明確常數與稽核輸出，**不**補造 payload、不**宣稱**已錨定。
- 不新增第二個「repair baseline marker」。真實 log 現無 `schema-repair`，所有新 repair 都應受本規則約束；用 marker 區分又會重演「刪一行，整條守衛失效」的單點繞過。既有 `contract-baseline` 前 172 筆舊 review 維持原樣，因為本規則只檢查 `schema-repair`，不追溯重驗舊 review。

### 驗證層次與完整性輸出

Git I/O 不得放進 `render_ledger()`、`_validate_review_contract()`，也**不得隱式塞進現有 `_load_events(path)`**：後者被 baseline marker 負向測試用 `tmp_path` fixture 呼叫，若對任意 path 要 Git history，測試會因「取不到 Git」而非「marker 缺失」轉紅，失去判準。

因此分成兩個明確入口：`_load_events(path)` 維持「解析 JSON + `contract-baseline` 檔案層不變量」且不做 Git I/O；新的 production-only loader（名稱由執行者依現有慣例定）只接受 canonical `EVENTS_PATH`，在 `_load_events(EVENTS_PATH)` 成功後再做 blob resolver／anchor scan。CLI `--check`、audit 與 CI 必走 production-only loader；tmp fixture、`render_ledger(events)` 與一般純函式測試不走它。這不是「path 剛好相等就偷加行為」，而是可由 call site 看出的兩個契約。

`--write --prepare-schema-repair` 只允許明示 pending 的造提交階段；production `--check`、audit 與 CI 不得接受 pending。**但 pending 不能靠「提交後、push 前請記得跑」保證：目前 GitHub `main` 無 branch protection（2026-08-04 `gh api .../branches/main/protection` 回 404），CI 只在 push 後觸發，故它只能偵測、不能阻止壞 commit 已到 remote。** 在需求方裁定並落地 enforcement model 前，本卡不得認領實作。

新增唯讀 `--audit-schema-repairs --json`：輸出 `anchored`、`legacy_unverifiable`、`failed` 的 event ID／原因與總數；若 `failed > 0` exit 非零。它是唯一可用來宣稱完整性範圍的產物。直接呼叫純函式的 fixture 測試、未提交的 pending 工作樹，以及不在 `HEAD` 可達歷史中的 object 都不在 full validation 涵蓋內，必須在輸出或錯誤中明示，而不是靜默當成功。

## 執行計畫

本卡不拆新卡：三個切片共同修改同一個 event schema、同一個真實檔入口與同一份契約；拆開會造成任一中間狀態不是「可建立且可驗證 repair」的完整垂直路徑。每個切片仍可獨立驗證，Checkpoint 前不得 handoff。

### Task 1：保留 fixture loader，另建 production anchor loader（M）

保持 `_load_events(path)` 的 parsing／marker 契約不變，另建立 production-only anchor loader 與「首次出現 repair event」的 Git history 查找；擴充 schema payload 與既有 `_validate_schema_repair_event()`，但保留其 before→after 白名單與 `after == 現況` 檢查。

**驗收條件：**

- [ ] F005 的 fabricated-before 攻擊在真實暫存 Git repo 中被拒絕，不只是在 mocked dict 中失敗。
- [ ] `tmp_path` 的缺／重複 `contract-baseline` marker 測試仍因 marker 專屬錯誤轉紅，不因 Git object 缺失轉紅。
- [ ] 缺 `anchor_parent_sha`、parent 不符、多 parent、重複 `event_id`、target 在任一 blob 不符、anchor event 內容不符、object 不可讀／不可達均由 production loader exit 非零。
- [ ] 同提交的「修 target + append repair event」在 post-commit `--check` 成功；未提交時只有顯式 pending 模式可寫 Ledger，且其輸出含 `PENDING`。

**驗證：** `uv run pytest tests/test_workflow_ledger.py -q`；測試內建立 temporary Git repository，實際建立 parent 與 anchor commit 後執行 CLI。

### Task 2：驗證線性 repair 鏈並產生稽核報告（M）

在同一 validator 建立 target 的線性 predecessor／successor、type／順序規則，並新增 `--audit-schema-repairs --json`。把 `322f69a` 的 legacy 例外做成最小、可測的固定清單，不把它偽裝為 anchor。

**驗收條件：**

- [ ] 同 target 的合法二次 repair（第二筆 before 等於第一筆 after）可通過；分叉 repair、repair 指向 repair、循環／前向參照、以及 repair event 後續被改寫，各有獨立負向測試。
- [ ] report 的 `anchored` 絕不包含 legacy；完整真實 log 的 report 機械列出 `legacy_unverifiable=[UX-BRAND-HOME1-REVIEW-007]`、`failed=[]`。
- [ ] CI 環境缺 Git 歷史時 fail，不得 `skip`；CI checkout 保持 `fetch-depth: 0`。本機缺 object 也不得把 `--check` 或 audit 說成成功。

**驗證：** `uv run pytest tests/test_workflow_ledger.py -q`；`uv run python scripts/workflow_ledger.py --audit-schema-repairs --json`；`uv run python scripts/workflow_ledger.py --check`。

### Task 3：在 enforcement model 成立後，寫入契約並做 mutation 驗證（S）

在需求方選定並驗證 enforcement model 後，更新 `CONTROL_PLANE_CONTRACT.md`，記錄單提交 repair 操作、pending／post-commit 次序、失效邊界、legacy 狀態與唯一完整性指令。把前卡三項教訓落成機器可測行為。

**驗收條件：**

- [ ] 移除／破壞 Git resolver 的呼叫、把 repair event payload 刪成缺欄、或把合法 target 偽裝成 repair，三種 mutation 都會使對應測試轉紅。
- [ ] 移除既有 `contract-baseline` marker 的既有負向測試仍轉紅；本卡不得把 172 筆 baseline 前 review 納入新驗證。
- [ ] 契約不宣稱 GPG 等級不可竄改，且明示 `--check`／audit 在歷史不可用時 fail closed。
- [ ] 以需求方核可的真實 remote path 證明 pending repair 無法在未通過 full `--check` 前抵達 protected main；若只剩 push 後 CI，必視為未達成本卡前置條件，不得以綠色 CI 補寫為預防。

**驗證：** `uv run ruff check`；`uv run pytest -q`；`uv run python scripts/workflow_ledger.py --check`；`uv run python scripts/workflow_ledger.py --audit-schema-repairs --json`。

### Checkpoint：交付獨立查核前

- [ ] Task 1–3 全部驗收完成，且 commit 後重跑，不接受只在未提交工作樹的測試結果。
- [ ] 查核者自行建立不同 event ID／欄位的 fabricated-before 攻擊，不能沿用執行者 fixture。
- [ ] 查核者自行修改 anchor event、建立合法第二次與分叉第二次 repair、嘗試 repair→repair、刪除 baseline marker，確認各自結果與錯誤原因正確。
- [ ] 查核者於 clean、full-history checkout 取得 audit JSON；它是交付中唯一的「完整性」宣稱依據。

## 非目標

- 不改 `DEV-EVENT-SCHEMA-GUARD1` 已建立的 review schema、白名單「非法→合法」語意或 baseline 前歷史。
- 不追溯補造 `before`，不把 legacy 改名為 anchored，也不新增外部簽章／manifest。
- 不處理 protected main 被惡意 force-push 的對抗式攻擊；這超出既定威脅模型。

## 紅線

1. **不得以任意 SHA、hash 或人工文字取代可重現的相鄰 blob 證據。** 那只會把 F005 從 `before` 欄位搬到另一個可任填欄位。
2. **不得把歷史／Git 取不到降級成成功或 pytest skip。** 錨定無法驗證時若仍放行，稽核報告會在最需要防護的環境說謊。
3. **不得用第二個 baseline marker 豁免未來 repair。** 前卡已證明單一 marker 被刪除可讓整條守衛消失；新機制必直接驗全部新 repair。
4. **不得以 repair 修 repair，亦不得補造 legacy；但不得禁止有前一份 anchor 證據的線性二次 repair。** 前兩者會自我洗白，後者則是避免未來 schema 收緊再次永久卡住 log 的必要逃生路徑。
5. **不得只測合成 dict。** 本缺陷的核心是 Git 歷史與提交順序；沒有真實暫存 repo 的紅／綠證據，等同再次設計未走過的機制。

## 驗收條件

- [ ] F005 的真實 Git repo 重現由綠轉紅；修正後合法單提交 repair 的 post-commit `--check` 轉綠。
- [ ] 每一筆新 repair 由 audit JSON 列為 anchored，且其 parent／anchor blob、repair event 本體、target before／after 都可由指令重現。
- [ ] 線性二次 repair 有正向測試；分叉二次、repair→repair、循環／前向、repair event 後改、缺 Git object 各有負向測試與非零 exit 證據。
- [ ] `322f69a` 只在 `legacy_unverifiable`，未在任何 schema-repair payload 或 anchored 計數出現。
- [ ] `contract-baseline` 前 172 筆 review 維持可 replay；marker 刪除的既有守衛仍失敗。
- [ ] `uv run ruff check`、`uv run pytest -q`、`workflow_ledger.py --check`、audit JSON 全部成功，且 audit 的 `failed=[]` 由指令輸出，不以人工聲明代替。

## 驗證

- [ ] 執行者先以 temporary Git repo 做合法路徑與 F005 兩個提交層證據，再寫 production code。
- [ ] 查核者以自己的 fixture 與 clean full-history checkout 重跑所有紅線攻擊。
- [ ] 查核者確認所有 pending 只能出現在未提交造提交階段，不能讓 production `--check`、audit 或需求方核可的 remote enforcement path 放行。
- [ ] 查核通過前不得 merge main。

## 邊界

- 只動本卡列出的 control-plane 工具、測試、契約與必要 CI checkout 設定；不動 API、資料庫或 production。
- 預估 M；由同一執行者依序完成，不與其他 control-plane writer 平行。
- **外部阻塞：** GitHub `main` 現無 branch protection，現有 direct-main lifecycle 與「CI 先通過才進 main」不相容。需求方必須裁定新 enforcement model；未裁定前不得開始 Task 1。
- 若實作發現「同提交 history discovery」無法在不新增可信根的情況下與 pending 流程共存，停止並回到本卡重新設計，不得私下退回兩提交或任意 SHA 方案。

## Log

- 2026-08-03 register by Claude Opus 5@Claude Code（依 ruan6047 裁定拆卡）；iteration 0。來源：`DEV-EVENT-SCHEMA-GUARD1` 第四輪跨家族查核的 F005——查核者以真實事件為 target、`after` 完全正確而僅偽造 `before`，驗證器接受該 payload。該漏洞由原卡執行者在派工提示詞中主動列為最可能攻擊向量、查核者證實可行。
- 2026-08-04 revision 1 by GPT-5.6@Codex：首次規劃採「payload 寫 repair commit SHA + 兩提交」；需求方隨後要求以本委託重新審視。該設計的問題是 audit event 不在 repair commit，無法驗自身內容，且第二個提交使修復曾短暫沒有稽核紀錄；故整份作廢，不留作執行依據。
- 2026-08-04 revision 2 by GPT-5.6@Codex（本 spec）：問題從「before 要填什麼」改問為「repair event 首次出現的提交能否同時證明 target transition 與 audit 本體未被後改」。採由 Git history 反推 anchor commit 的單提交方案；拒絕新 baseline marker、任意 SHA、manifest 與 hash。需求方指定 Claude Opus 5 後續執行；本次只更新 spec，未認領、未實作。
- 2026-08-04 revision 3 by GPT-5.6@Codex：依需求方動工前質詢修正三項。 (1) Git I/O 不再放進 `_load_events(path)`；分出 production-only loader，保住 tmp-path baseline marker 負向測試的錯誤語意。(2) 「一 target 一 repair」改為有 predecessor／successor 證據的線性鏈，允許日後 schema 收緊所需的二次修復、拒絕分叉與 repair→repair。(3) 實測 GitHub main branch protection API 為 404，CI 僅 push 後觸發，故 post-commit check 目前**不是機械守衛**；本卡標記為外部阻塞，等待需求方裁定 enforcement model。
