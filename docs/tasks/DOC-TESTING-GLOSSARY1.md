# DOC-TESTING-GLOSSARY1 Runbook 測試章節＋術語表 〔T2；⚪B2 權威文件〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code　分支：依認領時 worktree 慣例
- 執行：待指派（建議 MODEL_ROUTING L2；文件整併但指令須逐條實測）　查核：待指派（B2 獨立事實查核；須 ≠ 執行）
- Initiative：—　spec 基線：—
- DB：`none`（示例指令涉 CARD_ID 隔離測試 DB，唯讀既有慣例）
- 部署：否　環境：—　PR：—　Merge SHA：—
- 範圍（2026-07-26 流程審視實測產出）：
  1. `docs/AI_RUNBOOK.md` 新增「測試與驗證」章：python（`uv run pytest`，現況 479 tests／~9s、39/44 檔零 DB 依賴）、前端（`cd web && npm test`，165 tests／node:test）、DB 契約測試跑法（`ADV_SCHEMA_TEST_DATABASE_URL`／`EDITORIAL_TEST_DATABASE_URL` 的 CARD_ID 隔離 namespace、誰／何時必跑——現況三個 skipif 測試在任何環境都未曾執行，等同死碼且製造覆蓋率錯覺）、bug 卡「先紅後綠」留證慣例。Runbook 現況 22K 字無任何測試章節。
  2. `docs/reference/GLOSSARY.md`：收錄判準＝「同一詞兩處定義不一致」或「新執行者會腦補錯」——island、PA、kind A–E、outcome scope、wf（walk-forward）、GO=FO 語意、幽靈島、保留賽、delay_kind 等；每詞附 SSoT 出處（taxonomy JSON／`docs/reference/` 規則庫／卡片），既有文件改引用、不留第二份定義。不做全字典。
- Discovery：—　Design：Design Gate N/A；純文件

## 驗收條件

- [ ] Runbook 測試章節內指令逐條實測可跑；DB 契約測試至少附一次真實執行證據（CARD_ID 隔離 DB）。
- [ ] GLOSSARY 每詞恰一個 SSoT 連結；判準外的詞不收。
- [ ] `CLAUDE.md`／相關文件指向新章節與詞條，不新增重複定義。

## 驗證

- [ ] B2 獨立事實查核：查核者抽 3 條指令重跑、抽 3 個詞條對照 SSoT 出處。

## Log

- 2026-07-26T17:10:00+08:00 claim by Claude Fable 5@Claude Code（需求方派工）；worktree doc-testing-glossary1-execution。
- 2026-07-26T17:35:00+08:00 handoff → 🔍待查核；SHA b214418；DB 契約測試首次真實執行（editorial 16／advanced 3 passed）；kind_code DB 實證定案並發現 winprob_val E scope 誤標（另卡建議）；證據見 handoff event。

- 2026-07-26T16:15:00+08:00 register by Claude Fable 5@Claude Code（依 ruan6047 指示開卡；源自流程審視會話實測證據）。
