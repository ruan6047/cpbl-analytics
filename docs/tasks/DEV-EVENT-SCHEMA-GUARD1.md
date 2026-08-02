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
- **不回填、不重新解讀 baseline 前的既有事件。** 現況 `contract-baseline` 之前有 **173 筆** review 事件缺欄位（多為早期無結構化 findings 的格式），驗證器刻意跳過它們——任何新守衛**不得**讓這些歷史事件開始失敗。
- 不改 `review_prompt.py` 的提示詞產生邏輯。

## Discovery 必答（先答再改碼）

1. **該在哪一層把關？** 候選：(a) 提供唯一的寫入 helper（如 `workflow_ledger.py --append`）並在其中驗證，但無法阻止有人直接 `>>` 檔案；(b) pre-commit hook 驗證 `events.jsonl` 的 diff；(c) CI 檢查；(d) 以上組合。**各自擋得住什麼、擋不住什麼要明寫**，不得宣稱單一手段涵蓋全部。
2. **malformed 的合法修復程序是什麼？** 契約現行文字使 schema 錯誤無法以追加事件修復。要新增哪一種機制？候選：允許 `schema-repair` 類型的就地修復並要求在 commit message 與該行留痕；或引入 `superseded_by` 讓驗證器跳過被取代的 malformed 事件。**兩者對 append-only 的侵蝕程度不同，須明確取捨並寫進契約。**
3. **fail loud 的粒度是否過粗？** 現行是「任一事件 malformed → 整個 ledger 無法重建」。是否應改為「該卡標記為不可投影、其餘卡照常」？這會降低單點故障的爆炸半徑，但也可能讓壞資料更久不被發現——**這是真實取捨，要選一邊並說明理由**。
4. **要不要同時擋「假的成功訊號」？** 本次事故的近因不是 schema 錯誤本身，而是**記錄流程遮蔽了 stderr 並自行 echo 成功**。這屬人／agent 的操作紀律，工具能做的有限——**明講哪一半守得住、哪一半守不住**，不得宣稱工具能涵蓋。

## 紅線

1. **不得讓 baseline 前的 173 筆既有事件開始失敗。** 任何守衛上線前必須以完整 `events.jsonl` replay 證明現況仍可重建。
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
