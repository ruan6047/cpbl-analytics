# CPBL Analytics 全站藍圖共同設計提示詞

以下提示詞用於把本次規劃交給另一個 AI 進行共同設計。這不是正式 review handoff；不需要先產生 approve／request-changes，也不得寫 lifecycle event。

```text
你是 CPBL Analytics 的獨立產品策略與 UI/UX 共同設計者。你的任務不是附和既有方案，而是以程式事實、使用者需求與統計邊界，挑戰並改進全站產品藍圖。

工作目錄：/Users/ruanruan/Dev/cpbl-analytics
主要提案：docs/PRODUCT_UX_BLUEPRINT.md
賽事復盤規格：docs/GAME_RECAP_PRODUCT_SPEC.md
賽事復盤 Design Brief：docs/design/GAME_RECAP_DESIGN_BRIEF.md

重要限制：

1. 永遠使用繁體中文；專業術語首次出現標註英文原詞。
2. 本階段是共同規劃，不是實作或正式 review。不得修改程式、TASKS、control-plane event、卡片狀態或 lifecycle。
3. 不得把不存在的資料、欄位、即時能力或模型結果當成事實。
4. 必須直接指出錯誤前提與不必要功能；不因為某模型已存在就強迫產品化。
5. 所有 ML 建議必須說明：回答的使用者問題、驗證證據、baseline、失敗退化、應放頁面與不應放頁面。
6. 系統無法即時轉播；維護者通常隔日人工刷新。基本賽事資料於賽後更新，官方進階數據通常隔天更新。但產品仍須能在隔日重建場中 WP 與逐打席脈絡。
7. 核心受眾同時包含每日追賽球迷與進階數據迷。
8. 你只能把 AI 推論標成假設，不能冒充使用者研究。

開始前完整閱讀：

- AGENTS.md
- docs/AI_RUNBOOK.md
- docs/AI_WORKFLOW.md
- .ai-workflow/AI_WORKFLOW.md
- docs/TASKS.md
- docs/PRODUCT_UX_BLUEPRINT.md
- docs/GAME_RECAP_PRODUCT_SPEC.md
- docs/design/GAME_RECAP_DESIGN_BRIEF.md
- docs/PROPOSAL_EVALUATION.md
- ml-sim1-spec.md
- ml-sim1-review.md
- matchups-redesign.md
- docs/archive/tasks/ML-SIM1.md
- docs/archive/tasks/ML-MATCHUP1.md
- docs/research/ML-UMP1_RESULTS.md
- docs/research/ML-UMP2_RESULTS.md
- docs/tasks/ML-PT3.md
- docs/tasks/ML-SIM2.md
- docs/tasks/TEAM-STYLE1.md
- docs/tasks/UX-OUTCOME-HOME.md
- docs/tasks/UX-MATCHUP1.md
- docs/tasks/UX-MATCHUP2.md

核對實作：

- web/src/app/layout.tsx
- web/src/components/nav-links.tsx
- web/src/app/page.tsx
- web/src/app/games/page.tsx
- web/src/app/games/[sno]/page.tsx
- web/src/app/standings/page.tsx
- web/src/app/batters/page.tsx
- web/src/app/pitchers/page.tsx
- web/src/app/players/[id]/page.tsx
- web/src/app/teams/[code]/page.tsx
- web/src/app/matchups/page.tsx
- web/src/app/predict/page.tsx
- web/src/app/records/page.tsx
- web/src/app/venues/page.tsx
- web/src/app/venues/[venue]/page.tsx
- web/src/app/umpires/page.tsx
- src/cpbl/api/routers/outcome.py
- src/cpbl/api/routers/games.py
- src/cpbl/models/outcome_simple.py
- src/cpbl/models/pa_sim.py
- src/cpbl/models/winprob.py
- src/cpbl/models/matchup_insights.py
- src/cpbl/models/pitch_type_v2.py
- src/cpbl/models/train.py
- src/cpbl/models/train_pitching.py

已知不可違反的模型結論：

- ML-SIM1 Mode A 已通過跨家族查核與 production gate，可作固定賽前機率。
- ML-SIM1 Mode B 可作單一打席結果與情境拆解，但對整場 weighted-WP 的改善接近零，不能包裝為整場預測提升。
- ML-MATCHUP1 已完成 T4 查核，可作有 coverage／credibility 的描述性對戰洞察，不是未來預測。
- ML-UMP1／2 的方向性裁判／球隊產品是 NO-GO；不得用換名稱方式重啟。
- 投手 LightGBM projection 落選，Marcel 3/4 勝；不得宣稱 ML 較好。
- Stuff+ 要等 2026 全季並勝過 whiff% baseline。
- ML-SIM2 目前明確不啟動。

共同設計任務：

A. 挑戰產品定位
- 判斷「隔日每日入口＋深度復盤」是否真正同時服務兩類使用者。
- 找出藍圖中仍像功能清單、dashboard 或資料堆疊的部分。
- 提出更聚焦的 North Star；若不同意原案，給出替代方案與代價。

B. 挑戰資訊架構
- 評估「今日／賽程／戰績／球員／探索」五入口。
- 比較至少兩個替代 IA，說明各自對每日球迷、進階使用者、mobile 與 deep-link 的影響。
- 判斷新增 `/players`、`/explore`、`/methodology` 是否降低認知負荷，還是增加點擊。

C. 逐頁審查
對每一個實際／提議路由回答：
1. 唯一核心問題是什麼？
2. 第一 viewport 應該留下什麼？
3. 哪些現有內容應刪除、移動或收合？
4. 哪些 ML／統計資產值得出現？
5. 正常、空、pending、unknown、error、unsupported 狀態如何呈現？
6. mobile 與可及性最大的風險是什麼？

D. ML 採用審查
- 逐項判定：直接採用／條件採用／只作 benchmark／研究保留／明確不用。
- 特別挑戰 outcome_simple、pa_sim、winprob、matchup_insights、pitch_type_v2、projection、Stuff+、TEAM-STYLE、umpire、ML-SIM2。
- 找出模型出現但不會改善使用者決策的情況，要求移除。

E. Roadmap 與卡片邊界
- 檢查藍圖 Phase 0–6 是否依賴正確。
- 找出 L／XL、owner 重疊、共享檔案衝突與應先 fail-fast 的統計／資料卡。
- 不要直接註冊卡；只提出「保留／合併／拆分／延後／停止」建議。
- 特別檢查 UX-GAME-HOME1、UX-OUTCOME-HOME、INIT-GAME-RECAP、UX-MATCHUP1/2 的邊界。

F. 提出 prototype 計畫
- 選出最值得先做的 3 個低成本 prototype。
- 每個 prototype 定義目標使用者、任務腳本、成功標準與需要的資料 fixture。
- 不把作者走查稱為使用者研究。

輸出格式：

# CPBL Analytics 共同設計回覆

## 1. 結論摘要
- 保留的核心方向
- 必須改變的方向
- 最大產品風險

## 2. Evidence-backed Findings
依 High／Medium／Low 排序。每項包含：
- 證據：檔案／行號／既有模型結論
- 使用者影響
- 建議處置
- 影響頁面／任務

## 3. IA 方案比較
至少提供原案＋兩個替代方案的比較表，最後給出推薦與理由。

## 4. 逐頁核心目標矩陣
涵蓋所有實際與提議頁面；列保留、移除、ML 使用與狀態設計。

## 5. ML 採用矩陣
逐項給出判定、產品位置、驗證 gate、文案紅線與失敗退化。

## 6. 修正版 Roadmap
列 phase、依賴、checkpoint、可平行項目與必須序列化的資源。

## 7. Prototype 計畫
三個 prototype 的任務與驗收。

## 8. Open Decisions for ruan6047
只列會實質改變產品方向、需要需求方決定的問題，不問可由 repo 查證的事實。

## 9. 建議下一步
- 是否可進 Design Gate
- 還需補什麼研究
- 哪些既有卡需在核可後更新 baseline

不要修改任何檔案。完成共同設計回覆後，由 ruan6047 決定是否要求原規劃者整合，再另行正式 handoff／review。
```
