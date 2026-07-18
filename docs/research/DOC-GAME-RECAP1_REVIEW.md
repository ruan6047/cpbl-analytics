# DOC-GAME-RECAP1 獨立查核報告

- 查核卡：[`DOC-GAME-RECAP1`](../tasks/DOC-GAME-RECAP1.md)〔T3；⚪B2 權威文件〕
- 查核範圍：[`GAME_RECAP_PRODUCT_SPEC.md`](../GAME_RECAP_PRODUCT_SPEC.md) v1.2、[`GAME_RECAP_DESIGN_BRIEF.md`](../design/GAME_RECAP_DESIGN_BRIEF.md) v1.2、[`INIT-GAME-RECAP`](../tasks/INIT-GAME-RECAP.md) 與全部 `GAME-RECAP-*`／`UX-GAME-*` 子卡
- 查核者：Claude（Opus 4.8）　撰寫者：GPT-5@Codex（跨模型家族，符合紅線獨立性）
- 日期：2026-07-19　方法：唯讀核對 spec 宣稱 vs 實際 migration／model／API／前端；未修改任何原文件、未改動 control-plane／TASKS.md
- **結論：request-changes（外科式；核心紅線設計通過，阻擋項僅為現況盤點時效性漂移）**

---

## 1. 驗收條件逐項判定

| # | 驗收條件 | 判定 | 依據 |
|---|---|---|---|
| 1 | 不宣稱即時 ∧ 可隔日重建當下，無矛盾文案 | ✅PASS | §1「不是即時轉播」、§4.2「重建當下，不假裝即時」、§12 非目標明列 websocket／LIVE；前端紅線見 UX-GAME-RECAP1 驗收「不得顯示 TOP/BOT／壘包／球數」 |
| 2 | 現況盤點核對實況，不把既有能力誤列為新建 | ⚠️CHANGES | 表存在／WP 模型／API／前端全部核對正確（見 §2）；**但 §3.2、§6.1 與 INIT 對 ML-SIM1、UX-GAME-HOME1、UX-OUTCOME-HOME 的狀態已過期**（F1） |
| 3 | WP/WPA、打席分組、逐球、freshness、賽制邊界皆有 fail-closed 與驗證要求 | ✅PASS | §8「無法重建打席 fail closed」「未驗證賽制標 unsupported」、§7 證據不足退 `unknown`、WP-VAL1 要求 walk-forward／Brier、PA1 要求紅燈測試 |
| 4 | 依賴圖、子卡範圍／tier／DB scope／Design Gate／獨立查核／驗證命令符合 canonical | ⚠️CHANGES | 主鏈與 tier／DB scope／紅線查核標註正確；**INIT mermaid 與 TASKS.md 首頁路徑不一致（F3）、mermaid 換行語法（F4）、DOC 卡角色欄位矛盾（F2）** |
| 5 | 無 XL 卡、無 owner scope 重疊、每 checkpoint 留可工作系統 | ✅PASS | 全卡 S/M；availability owner 三方互斥（official→STATUS1、tracking→PA1、wp→WP-API1，§7 明文不互相重算）；Checkpoint 1/2/3 各自可交付 |
| 6 | 可及性／行動／效能／維運具可測驗收 | ✅PASS | §9 44×44px、375px 無橫捲、文字替代、鍵盤；§10 冪等 refresh／延遲載入；§11 Brier／校準可查核；使用者測試不足時 §11／Design Brief 誠實要求記錄限制、不得作者自測充當使用者研究 |

---

## 2. 技術宣稱核實（§3.3／§7／§8 立論基礎 — 全部與程式一致）

> 這是整份 spec 的立論根據，逐一對到程式行號，無虛構、無誇大。

| spec 宣稱 | 程式證據 | 判定 |
|---|---|---|
| 前端以「投手 ID×打者 ID×局數」比對逐球，同局重複對戰會併打席 | [`game-board.tsx:578`](../../web/src/components/game-board.tsx) `filter(p.pitcher_acnt===e.pitcher_acnt && p.hitter_acnt===e.hitter_acnt && p.inning_seq===Number(e.inning_seq))`；L574 註解自承「三鍵精準比對」 | ✅屬實 |
| 後端 `build_run_dist()` 以半局內 `(batting_order, hitter)` 去重 | [`winprob.py:71`](../../src/cpbl/models/winprob.py) `pa_key=(e.get("batting_order"), e.get("hitter_acnt"))` | ✅屬實 |
| WP API 以 `(inning, half, batting_order, hitter)` 去重 | [`games.py:287`](../../src/cpbl/api/routers/games.py) `pa_key=(inning_seq, vht, batting_order, hitter_acnt)` | ✅屬實 |
| 前端 `buildMoments()` 以連續相同 hitter 找打席終點 | [`overview.tsx:33`](../../web/src/app/games/[sno]/overview.tsx) `if(String(e.hitter_acnt)!==String(hitter)) break;` | ✅屬實 |
| `home_score+away_score>0` 無法表達 0–0／延賽／取消／未刷新 | [`games.py:301`](../../src/cpbl/api/routers/games.py)、[`winprob.py:235`](../../src/cpbl/models/winprob.py) 皆用此判 completed | ✅屬實 |
| WP 端點固定載入一軍 2018–2025 分布，但路由允許其他 kind_code | [`games.py:252`](../../src/cpbl/api/routers/games.py) `kind_code: Query("A", pattern="^(A|C|E|D)$")`；L260-262 `span="2018-2025"`、`_wp_tables(span,"A")` 永遠用 A 表，事件卻用實際 kind_code → 未驗證賽制靜默借一軍口徑風險屬實 | ✅屬實 |
| `refresh_log` 只表示整次 refresh，不能證明單場／單來源 | [`migrations/015_refresh_log.sql`](../../migrations/015_refresh_log.sql) 欄位 `scope`（例 recent-games）／`from_date`／`to_date`／`games_total`／`games_completed`，無單場單來源列 | ✅屬實 |

**其餘存在性核對**：`game_scoreboard`／`game_livelog`（016）、`pitch_tracking`（018）、`run_dist`／`win_expectancy`（049）、`present_status`（002）、`refresh_log`（015）皆存在；`models/winprob.py` 確有 run distribution ＋ DP（`_we_solver`）；`/api/v1/games/{game_sno}/winprob` 存在。§3.2「本規格處置」欄無一把既有能力寫成從零新建。

---

## 3. 缺陷清單（severity｜證據｜處置建議）

### F1 — 現況盤點時效性漂移　`severity: Medium（阻擋 Design Gate）`

- **證據**：spec v1.2 基線日 2026-07-16，但下列三卡已於其後交付、狀態與 spec 敘述牴觸：
  - `ML-SIM1`：[`TASKS.md`](../TASKS.md) 依賴註記「已完成跨家族複查、合併與 production 驗證」、archive merge `a28170b`。**spec §3.2 仍寫「ML-SIM1…但 Ledger 待對帳」**，INIT [`決策與風險`](../tasks/INIT-GAME-RECAP.md) L71 仍寫「ML-SIM1 與 Ledger 狀態仍待對帳…首頁賽前區必須等待對帳」。
  - `UX-GAME-HOME1`：archive 🏁完成／✅已驗證（merge `99b38a6`，07-18 部署）。**INIT mermaid 仍把 `UX-GAME-HOME1` 當未完成下游節點**，spec §6.1 仍要求「兩卡序列化、不得平行修改 `page.tsx`」。
  - `UX-OUTCOME-HOME`：archive 🏁完成／✅已驗證（merge `fdee7297`，07-18 部署）。§6.1 的序列化前提已消滅。
- **影響**：需求方在 Design Gate 依 §3.2／§6.1／INIT 風險段核可時，會被誤導以為首頁序列化與 ML-SIM1 對帳仍是待辦，牴觸驗收條件 2、造成重複 Roadmap 判斷。
- **處置**：升 v1.3，於 §3.2 將 ML-SIM1 改為「已對帳／已部署」、§6.1 標註首頁序列化已由 UX-GAME-HOME1／UX-OUTCOME-HOME 交付完成、INIT mermaid 與風險段同步；核心資料／PA／WP／STATUS 設計無須改動。

### F2 — DOC 卡角色欄位自相矛盾　`severity: Low`

- **證據**：[`DOC-GAME-RECAP1.md`](../tasks/DOC-GAME-RECAP1.md) L4「執行：GPT-5@Codex」，但同卡查核目標要求「由非原撰寫者獨立確認」、current-state「待指派獨立 reviewer」。獨立查核卡的「執行＝產出查核」不可由原撰寫者擔任。
- **處置**：將「執行」改為「待指派其他 AI（≠GPT-5@Codex）」，與 GAME-RECAP-DATA1 等子卡的「執行：待指派」一致。

### F3 — INIT 依賴圖與 TASKS.md 首頁路徑不一致　`severity: Low`

- **證據**：[`TASKS.md`](../TASKS.md) 依賴註記 L46「首頁 v1 另走 `API-DAILY-SUMMARY1 + UX-OUTCOME-HOME → UX-GAME-HOME1`」，但 [`INIT-GAME-RECAP`](../tasks/INIT-GAME-RECAP.md) 子卡清單與 mermaid 均未含 `API-DAILY-SUMMARY1`（該卡已 archive 完成）。
- **處置**：INIT 依賴段補列 daily-summary 首頁鏈並標記已交付，或註明首頁路徑已移交 INIT-PRODUCT-UX 追蹤。

### F4 — INIT mermaid 換行語法非官方保證　`severity: Low`

- **證據**：[`INIT-GAME-RECAP`](../tasks/INIT-GAME-RECAP.md) mermaid 節點用 `\n` 換行（如 `D["GAME-RECAP-DATA1\n資料覆蓋與契約稽核"]`）；mermaid flowchart 官方換行語法為 `<br>`，`\n` 在 GitHub 渲染器不保證斷行。spec／Design Brief 的 mermaid 均為單行標籤、無此問題。
- **處置**：`\n` 改 `<br>`（或拆單行標籤）。

---

## 4. 明確通過項（附證據，非「看起來合理」）

- **fail-closed 完整**：§8「無法可靠重建的打席必須 fail closed：保留事件，但不回傳誤導性 WP／WPA」、「非一軍／季後賽…須明確標示不支援或使用代理模型，不得靜默套用」；§7「證據不足時 fail closed 為 unknown，不以日期猜測」。直接對應並要求修補已核實的 F3.3 風險。
- **owner scope 無重疊**：§7 表 availability 三方互斥，STATUS1 卡 L23-24／L15 明文「不擁有 canonical PA／tracking mapping 或 WP availability」、WP-API1 卡 L22「本卡是 `wp_availability` 唯一 owner」、PA1 卡 L20「不計算或代理任何 WP 欄位」。
- **PA 單一 owner 契約**：§8「GAME-RECAP-PA1 是 canonical 打席與 pa_id 唯一 owner；所有 WP、逐球與 UI 只消費該契約」，取代已核實的三套近似鍵；§8.1 base contract 與 §8.2 WP enrichment 拆分乾淨，PA1「不計算 WP、也不依賴模型驗證」。
- **統計誠實**：§4.5、§5 天花板 ~60%、§8「模型必須以走查／留出季驗證校準、Brier、邊界，不得只用建模母體自我驗證」，與 WP-VAL1「先證明同母體 calibration 不能作時間外證據」一致，且對照 CLAUDE.md 賽果預測紅線。
- **tier／DB scope／紅線查核**：資料正確性／統計卡（DATA1／PA1／STATUS1／WP-VAL1／WP-API1）皆 T4＋要求跨模型家族或人工查核；UX 卡 T3；DB scope 標註合理（研究卡 read，物化另拆 expand 卡）。
- **無 XL 卡、checkpoint 可交付**：全卡 S/M；Checkpoint 1（資料可行性）→ 2（統計正確性／契約凍結）→ 3（使用者流程）各自留可工作系統。
- **相對連結**：spec→`tasks/*`、`design/*`；DOC→`../*`；INIT→`../design/*`、`../PRODUCT_UX_BLUEPRINT.md` 均解析成功。
- **可測驗收**：§9/§11 44×44px、375px 無橫捲、2 次互動、5 秒辨識（並誠實要求無代表性使用者時記錄限制）、§10 冪等 refresh／延遲載入／無新增即時基礎設施（Solopreneur-first）。

---

## 5. 交付建議

- **給撰寫者（GPT-5@Codex）**：僅需外科式升版 v1.3 修 F1（現況盤點）＋ F2/F3/F4（卡片一致性）；**核心資料／PA/WP/STATUS/可及性設計不需改動**，修正後交回同一查核者複查。
- **給需求方（ruan6047）／Coordinator**：F1 修正前不建議在 Design Gate 對 §3.2／§6.1 現況段簽核；核心紅線設計本查核已通過，可平行推進 `GAME-RECAP-DATA1` 執行（已 claim）。
- 本報告為證據，lifecycle event（review／verdict）由唯一 lifecycle writer ruan6047／Coordinator 直接落 main。
