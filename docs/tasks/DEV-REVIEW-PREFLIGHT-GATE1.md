# DEV-REVIEW-PREFLIGHT-GATE1 前置查核關卡改為 preflight 的機器可讀宣告〔T3；🟡工具＋流程〕

> ⚠ **本卡尚未 register**：規劃已定案（契約 [`../REVIEW_GATE_CONTRACT.md`](../REVIEW_GATE_CONTRACT.md) v1.0 §8 十二項裁定），
> 待需求方寫 register event 後即可認領。

- 需求：ruan6047（2026-07-31 指示重規劃 `DEV-REVIEW-PROMPT-GATE1` ＋ `DEV-REVIEW-INDEP-FIELD1`，同日對抗式質詢定案路線）　規劃：本卡 spec ＋ 契約 v1.0　分支：`ai/<執行者>/DEV-REVIEW-PREFLIGHT-GATE1`
- 執行：待指派（建議 L3；跨 `review_prompt.py`／`workflow_ledger.py`／三份契約文件的取捨，且要保住 baseline 前歷史零變更）　查核：待指派（建議 L2；≠ 執行）
- review_independence: [cross_family_or_human]
- review_preflight_gates: []
- Initiative：—　spec 基線：`REVIEW_GATE_CONTRACT.md` v1.0
- DB：`db_scope: none`
- 部署：否　環境：—　PR：—　Merge SHA：—
- 資源：`file:scripts/workflow_ledger.py`（與 `DEV-REVIEW-DEACCEPT-TRAIL1` 互斥，本卡先，該卡之後 rebase）、`file:scripts/review_prompt.py`
- 範圍：`scripts/review_prompt.py`、`scripts/workflow_ledger.py`、`scripts/review_gate_inventory.py`（納管）、`tests/test_review_prompt.py`、`tests/test_workflow_ledger.py`、`docs/CONTROL_PLANE_CONTRACT.md`、`docs/TEMPLATES.md`、`docs/HANDOFF_CONTRACT.md`、活卡按需回填
- Discovery：[`../discovery/DEV-REVIEW-PREFLIGHT-GATE1-discovery.md`](../discovery/DEV-REVIEW-PREFLIGHT-GATE1-discovery.md)
- Design：Design Gate N/A——無使用者可見介面。
- 前身：`DEV-REVIEW-PROMPT-GATE1`、`DEV-REVIEW-INDEP-FIELD1`（皆 🏁完成）。本卡廢止前者交付的 `closes_review_round`，並補上後者缺的那一半：**要求要能被 preflight 驗、被事件快照。**

## 問題陳述

WF-21 把 canonical 的流程改成「執行與自測 → **Review preflight** → 獨立查核」，而 preflight
的必驗項明文包含「規定在跨家族查核前完成的**人工檢查**」。

**canonical 要求驗這一項，卻沒有定義它要怎麼被宣告。** 現況這些前置關卡散在四種互不相交的
中文語式裡——正文順序語式、〈Design〉欄、`## Plan Gate` 章節標題，以及根本沒寫在該寫的地方
（`UX-TEAM-STYLE1` 的〈查核〉欄只寫「≠ 執行；T3 一般查核」，看不出驗證段要求先人工審）。
要驗就只能讀中文，而**從中文自由文字推流程門檻已被連續三輪打穿**（`DEV-REVIEW-PROMPT-GUARD1`）。

三項已證實的事實使這件事非做不可，數字與清單見契約 §1、§6，**本卡不重複**：卡面要求會被
就地改寫而消失（`UX-LIVE-GAME1`）；同一張卡的兩處要求會互相矛盾（2 張）；三種前置關卡流程
（human→跨家族、human→一般 AI、Plan/Design Gate→實作）在現實中都存在且不是同一種。

另一半是清理：`DEV-REVIEW-PROMPT-GATE1` 交付的 `closes_review_round`／`corrects_event_id`
在全庫 892 筆事件裡使用次數為 **0**，卻帶著兩個實測可重現的缺陷（終局 REJECT 可被一筆指名它
的更正重開；重開後那筆 REJECT 會被印在「已通過的中繼關卡」標題下）。前置關卡改走 preflight
之後這對欄位失去使用場景，**移除比修好**。

## 目標

一、卡面新增 `review_preflight_gates`（有序、`gate_id=requirement`、`[]` 表示沒有前置關卡）；
`review_independence` 沿用不動，兩者分工是「送審前要先完成什麼」vs「誰有資格做終局查核」。

二、`review_prompt.py` 新增 `--preflight`：驗卡面欄位與既有的機械條件，產生要寫進 handoff 的
`preflight_gates` 快照；未通過則產生 `preflight-failed` 內容（WF-21 既有型別）。

三、`workflow_ledger.py` 支援**多個 contract baseline 並存**，並在 `review-gate-v1` 之後強制
handoff 帶合法快照、review 不得再帶廢止欄位。

四、移除 `closes_review_round`／`corrects_event_id` 與守衛裡的中繼關卡邏輯。

五、三份契約文件同步，盤點腳本納管（用途改為 preflight 缺欄時的**提示**來源）。

規格逐條見 [`../REVIEW_GATE_CONTRACT.md`](../REVIEW_GATE_CONTRACT.md) §2–§5，**本卡不重複數字**。

## 紅線（違反即退回）

1. **不得從任何自由文字推斷流程門檻。** 盤點腳本的分類**只能**出現在缺欄 fail 訊息裡當提示，
   **不得**被 preflight 判定消費。
2. **baseline 前的歷史不得被重新解讀**：既有 892 筆事件的 `--check` 結果不得有任何一筆改變，
   須由腳本窮舉比對新舊兩版（差異數 0），不得以人工聲明承載。
3. **缺欄不得靜默放寬**：cutover 後缺 `review_preflight_gates` 一律 fail，不得退化成「所以沒有
   前置關卡」；沒有前置關卡就明寫 `[]`。
4. **不得新增任何 event type**：通過走 handoff 快照、未通過走 WF-21 既有的 `preflight-failed`。
5. **不得回填猜測的值**：語意不明或自我矛盾的卡標為待需求方裁定並暫不填；封存卡一律不動。
6. **不得碰 review 事件的 schema**：那是 WF-21 的地盤，本卡只讀不寫。

## 驗收條件

- [ ] 卡面 `review_preflight_gates` 的格式、`gate_id` pattern 與穩定性、值域、`[]` 語意、
      缺欄行為與回填程序寫進 `TEMPLATES.md`。
- [ ] `review_prompt.py --preflight`：合法卡面產生正確快照；`[]` 產生空快照並通過；欄位寫壞
      （值域外／pattern 不合／`gate_id` 重複／同卡多行）逐一 fail loud；**缺欄 fail 且訊息
      不得提供任何 fallback，但必須列出盤點找到的疑似前置關卡並標明「這是提示，不是判定」**。
- [ ] 前置關卡未完成時輸出 `preflight-failed` 的內容而非 handoff 快照；外部條件未滿足
      不得被歸成 preflight failure（依 canonical 轉 `⏸阻塞`）。
- [ ] `workflow_ledger.py` 支援多 baseline；`review-gate-v1` 之後的 handoff 缺／壞
      `preflight_gates` → fail loud；marker 重複出現 → fail loud；與 `review-escalation-v1`
      並存互不干擾。
- [ ] `closes_review_round`／`corrects_event_id` 自 `review_prompt.py` 移除；baseline 後的
      review 若仍帶這兩個欄位 → `--check` fail loud 並指向新契約。
- [ ] **保證邊界落地**：移除提示詞裡「卡面〈查核〉欄原文（**以此為準**）」與「卡面若要求得比
      下限嚴……一律以卡面為準」兩處措辭（〈查核〉欄仍原文照登但不再是流程依據）；輸出把宣告值
      與 actor 並列時**明寫工具無法驗證 reviewer 身分、這是人工核對輔助**。以字串斷言鎖住。
- [ ] 紅線 2 的窮舉證明：新舊兩版對全庫事件逐筆比對，差異 0，證據由腳本產生。
- [ ] `CONTROL_PLANE_CONTRACT.md` 換掉 `closes_review_round` 整段、`HANDOFF_CONTRACT.md`
      補 sender 跑 preflight 與快照的責任。
- [ ] `scripts/review_gate_inventory.py` 納管並補測試（信號 A／B／D／E／F 與 C1／C2／C3 各至少
      一個 fixture、引文標記、三型分類不互相污染、`--rev` 可重現）。
- [ ] `uv run ruff check` ＋ `uv run pytest` 全綠。

## 驗證

- [ ] 查核者以 `--rev 81bcd4d` 重跑盤點，確認與交付的輸出檔逐字相同。
- [ ] 查核者確認需求方指定重檢的 9 張卡在盤點報告中逐張出現且三型分類正確
      （human→跨家族 3、human→一般 AI 3、Plan Gate→實作 1，兩張 `DEV-REVIEW-*` 為引文命中）。
- [ ] 查核者自行構造「baseline 後 handoff 缺 `preflight_gates`」與「review 帶
      `closes_review_round`」，確認兩者都 fail loud。
- [ ] 查核者確認 baseline **前**的既有事件 `--check` 全綠且輸出與合併前逐字相同。
- [ ] 查核者確認提示詞輸出中**不存在**任何把自由文字當流程依據的措辭，且**不宣稱**已驗證
      reviewer 的模型家族或人類身分。
- [ ] 查核者抽驗回填的活卡：發現任何一張的值是推定而非需求方裁定，即退回。

## 邊界

- **不碰 review 事件 schema、不碰 WF-21 的 attempt／escalation 邏輯**；`_apply_finding_state`
  的缺口屬 `DEV-REVIEW-DEACCEPT-TRAIL1`，該卡於本卡合併後 rebase 接手。
- 不批次回填活卡、不動封存卡、不補歷史 handoff、不回填任何既有事件。
- **canonical 先不動**：`review_preflight_gates` 先在 adapter 落地驗證，之後再評估提 WF-22。
- 預估 M。

## Release 後追蹤（非驗收條件，契約 §8）

- 合併後第一個月追蹤「新寫的 handoff 是否 100% 帶 `preflight_gates`」。`--check` 會擋，
  所以不是 100% 就代表有人繞過驗證或事件根本沒寫進去。`closes_review_round` 在全庫用過 0 次，
  這個追蹤就是為了不重蹈。

## Log

- 2026-07-31 規劃 by Claude Fable 5@Claude Code。需求方指出 `DEV-REVIEW-PROMPT-GATE1` 與
  `DEV-REVIEW-INDEP-FIELD1` 形成雙重狀態來源，指示收斂成單一契約；規劃期間先後定案 Q2／Q4
  遷移與保證邊界、五項未決事項，並在開卡前的 WF-21 稽核中發現整份設計建立在過期基準上。
- 2026-07-31 **路線改寫**：對抗式質詢（12 題）後改採「前置關卡＝preflight 條件」，
  取代原本的「review 事件帶 `gate_id` 的 gate 狀態機」。`gate_id`、`gate_result`、gate 狀態機、
  `review-correction` 撞名全部不再需要；原規劃的兩張卡（`DEV-REVIEW-GATE-CONTRACT1`／
  `DEV-REVIEW-GATE-DECLARE1`，皆未 register）合併為本卡。十二項裁定見契約 §8，
  與 WF-21 的衝突稽核見 §9。
