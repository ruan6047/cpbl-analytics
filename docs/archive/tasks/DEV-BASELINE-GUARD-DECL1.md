# DEV-BASELINE-GUARD-DECL1 spec 基線守衛只認宣告值，說明文字不再放行〔T2；🟡流程〕

- review_independence: [cross_family]
- 需求：ruan6047（2026-08-03 於 `INGEST-PLAYER-BIO-GAP2` preflight 退回後指示開卡）　規劃：本卡 spec　分支：`ai/opus-5/DEV-BASELINE-GUARD-DECL1`
- 執行：Claude Opus 5@Claude Code（L2；判定邏輯窄、輸入空間可窮舉，重點在變異檢驗而非設計取捨）　查核：待指派（跨家族；≠ 執行）
- Initiative：—　spec 基線：—
- DB：`db_scope: none`
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍：`tests/test_task_card_sections.py`、`scripts/review_prompt.py`（含 `baseline_check()` 的同型誤報）
- Discovery：—（T2；缺陷與重現由需求方於卡前實測給定，見〈問題陳述〉）
- Design：Design Gate N/A——無使用者可見介面。
- owner、worktree、iteration、最後交接、阻塞與交付／部署 current-state 見 [`../../TASKS.md`](../../TASKS.md) Ledger；歷史寫入 adapter event log。

## 問題陳述

`tests/test_task_card_sections.py::test_initiative_children_baseline_matches_parent_version`
以 `child_vers & parent_vers` 取交集判定子卡基線是否等於父卡當前版本，但版本 token 是從
**整個欄位（含括號說明文字）**抽出來的。於是宣告值填錯，只要說明文字裡提到父卡當前版本，
交集就非空而放行。

需求方 2026-08-03 的實測重現（父卡 `INIT-OFFICIAL-DATA1` 當前 `spec 基線：v1`，
寫在 `docs/tasks/INGEST-PLAYER-BIO-GAP2.md` 第 6 行）：

- `spec 基線：v2（v1 範圍過窄，見背景節）` → **通過**（應該要紅）
- `spec 基線：v2（範圍過窄，見背景節）` → 失敗（正確）
- `spec 基線：v1（＝父卡當前版本）` → 通過（正確）

實際後果：同日 `INGEST-PLAYER-BIO-GAP2` 與 `INGEST-SPLITS-IMPORT-RESTATE1` 兩張卡都把
「spec 基線」誤當成「這張卡自己的 spec 修訂號」而填 v2（canonical `baseline-cascade.md` §5
定義是**父卡當前版本**）。守衛全綠放行，最後由 `INGEST-PLAYER-BIO-GAP2` 的獨立查核者以
`PREFLIGHT_FAILED` 擋下（`INGEST-PLAYER-BIO-GAP2-PREFLIGHT-FAILED-005`），燒掉一輪送審。
卡面已於 `13351c7` 修回 v1，守衛本身未修。

**這是同型缺陷的第三次**，一次比一次細：

1. 只擋哨兵值「—」→ 填卡名（`UX-TEAM-SPLIT-SCOPE1`）照過。
2. 改為抽版本 token 比對 → 取樣範圍多含了不該算數的敘述，說明文字即可放行（本卡）。

共同形狀是 `DOC-CARD-SPEC-RULES1` 已經記過的那條：**檢查哨兵值的缺席，不等於檢查該成立的
性質；而檢查性質時，取樣範圍本身也是性質的一部分。**

## 順帶查出的同型誤報（同一份欄位、兩份各自的解讀）

`scripts/review_prompt.py` 的 `baseline_check()` 另寫一份抽取（`[^\s　]+`，取到第一個空白為止），
方向相反地誤報：卡面正確寫 `v1（＝父卡當前版本）` 時，它抽出整串當版本、與父卡 `v1` 比字串不等，
印出「**不一致——舊基線交付，直接退回**」。以修復前的程式對全庫 65 張有父卡的卡面實測，
**30 張（≈半數）得到這個假警報**——凡欄位在版本後還有任何文字（複合基線 `＋`／`、`、括號說明、
文件連結）一律中招。剛被修回 v1 的兩張卡本來也在其中——`00b9ab4`（2026-08-03T19:45，與本卡
並行落地）因此把兩張卡的註記整個拿掉、只留裸 token 以繞過誤報，並在 commit message 記下
「同一條 canonical 規則有兩套實作，已併入既有的守衛 follow-up 追蹤」。本卡即該 follow-up；
修好之後兩種寫法都成立，那個變通不再是必要的（本卡不回改卡面）。

> **數字更正（iteration 1 查核 finding `DECL1-F002`）**：初版卡面與 handoff 寫 32 張，那是
> **rebase 到 `00b9ab4` 之前**的快照——當時那兩張卡仍寫 `v1（＝父卡當前版本）`，舊程式判不一致、
> 新程式判一致，故計入改變。`00b9ab4` 拿掉註記後，舊程式對它們也判一致，不再構成差異。
> 以交付 SHA 重跑為 **30 張（22「一致」＋8「人工核對」）**，查核者獨立重現同一數字。

兩處各寫一份解讀，正是這個誤報的來源，故本卡把抽取器**收斂為單一實作**
（`review_prompt.baseline_declaration()`），守衛與查核提示詞共用。

## 非目標

- 不改 canonical `baseline-cascade.md` §5 的語意，也不改「基線＝父卡當前版本」這個定義。
- 不放寬守衛：宣告值填卡名或文件連結（無版本 token）在 pytest 仍是硬紅，只有查核提示詞
  改成要求「人工核對」而非誤報「不一致」——提示詞是輔助判讀，硬閘門在 pytest。
- 不回填存量卡面。封存卡（如 `INGEST-SPLITS-PA-SPLIT1` 同樣把 v2 當自己的修訂號）不動。
- 不處理「卡片自己的修訂號該記在哪一欄」這個範本問題——`INGEST-PLAYER-BIO-GAP2` 已示範
  另記為「卡面修訂：rev2」，若要成為通則屬 `DOC-CARD-SPEC-RULES1` 的範圍。

## 驗收條件

- [ ] 判定只看**宣告值**：括號（全形／半形，含未閉合）內的說明文字與 markdown 連結目標
      排除在版本 token 抽取之外；每個宣告子句只取第一個 token（其後為敘述）。
- [ ] 問題陳述的三種寫法判定為 **紅／紅／綠**，且以實際卡面重現（不是只有單元測試）。
- [ ] **複合基線不誤傷**：`GAME_RECAP v1.3＋PRODUCT_UX_BLUEPRINT v0.2`、
      `PRODUCT_UX_BLUEPRINT v0.2、LIVE_GAME_PRODUCT_SPEC v1.1` 等既有寫法仍通過；
      修復前先掃過 `docs/tasks/` 與 `docs/archive/tasks/` 全部子卡確認無誤傷。
- [ ] **變異檢驗**：對抽取器逐一注入變異（不剝括號／子句取全部 token／不切複合子句／
      退回整段抽 token），證明新測試各自轉紅，未變異時全綠。
- [ ] `review_prompt.baseline_check()` 與守衛共用同一支抽取器，且前述 30 張假警報消失；
      真正不一致者（父卡 v1.3 vs 子卡 v1.2 等）仍判不一致。
- [ ] `uv run ruff check` ＋ `uv run pytest` 全綠。

## 驗證

- [ ] `uv run pytest -q -k "initiative_children_baseline"`。
- [ ] 三種寫法的紅／紅／綠重現：逐一寫入 `docs/tasks/INGEST-PLAYER-BIO-GAP2.md` 第 6 行後跑
      上述指令，附三次結果與還原後 `git diff` 為空的證據。
- [ ] 變異檢驗：附各變異的 pytest 失敗數與還原後全綠。
- [ ] 全庫掃描：以修復前後兩版 `baseline_check()` 對所有有父卡的卡面各跑一次，附判定差異表
      （由腳本輸出，不接受人工聲明）。
- [ ] `uv run ruff check` ＋ `uv run pytest`，**於 commit 之後執行**——`test_commit_trailers.py`
      在 commit 前會 skip，基線是 3 skipped，看到 4 skipped 即代表守衛被跳過。

## Log

- 2026-08-03 register／claim／handoff 見 event log。
