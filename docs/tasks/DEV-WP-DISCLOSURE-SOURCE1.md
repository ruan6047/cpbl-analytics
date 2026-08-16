# DEV-WP-DISCLOSURE-SOURCE1 WP 對外揭露的數字改為由 artifact 單一來源產生，取代三份人工副本＋一條比對測試　〔T3〕

- 需求：ruan6047　規劃：Claude Fable 5@Claude Code (PM)
<!-- wf-routing:v1 -->
- 執行：待指派（建議 主力型；要動 resources 打包（wheel 與生產容器）、API 渲染路徑、以及讓前端改成消費 API——三個表面的接縫都在，任一處判斷錯就會讓對外揭露在生產上壞掉或空掉。）　查核：待指派（建議 主力型；改動可由既有比對器與前端測試機械驗證，且不涉統計判定本身；但查核者須能判斷「單一來源」是否真的成立，而不是把三份副本換成兩份。）
- Initiative：—　spec 基線：#100 WP-DISCLOSURE-SYNC1 的交付（含四項 2026-08-15 裁定）
- DB：db_scope=none
- 服務的原始目標：統計誠實——對外揭露的數字與其證據來源必須真的對得上
- owner、worktree、iteration、交付／部署狀態、最後交接、資源宣告與 Log
  current-state 見對應 GitHub Issue／Project item（卡ID：DEV-WP-DISCLOSURE-SOURCE1），不重複於此檔。

## 核心痛點

- **痛點**：WP 揭露的每一個數字目前有三份人工副本：docs/research 的 artifact、src/cpbl/api/routers/recap.py 的散文字串（例如「池化 1,826 場／138,949 打席」「+4.2~+6.0pt」「0.153 vs 0.245」）、以及 web/src/lib/methodology-content.ts 的第二份散文副本（前端不消費 API 的 wp_reliability，已 grep 確認）。三者靠 #100 建的比對器維持一致，而比對器證明的是「今天這三份同意」不是「只有一個數字」。#100 的發生原因正是這個結構：artifact 換版後兩份散文沒跟上，方法頁的「數字逐位對應 X」變成假的

## 驗收條件

- [ ] 揭露數字由單一來源產生：artifact 打包進 src/cpbl/resources/（既有前例 pa_transition_taxonomy.v1.json、team_style2_season_managers.json；pyproject.toml:86-87 已載明 wheel 與生產容器會帶上），API 以佔位符渲染散文而非硬編數字;前端不再持有第二份副本——methodology-content.ts 的數字改為消費 API 的 wp_reliability;⚠️ 散文中的判斷語句（例如「失準在校準而非資訊量」）不在 artifact 內，不得硬塞進資料層。本卡要拆的是「數字」不是「句子」，拆法須明寫界線;#100 建的比對器若因單一來源而變成恆真，須說明它還剩什麼作用或明確刪除——不得留一條永遠綠的測試假裝有守衛

## 驗證

- [ ] 變異檢驗：改 artifact 中的一個數字，API 回應與前端頁面須同時變動；改散文模板不得能改出與 artifact 不符的數字;生產容器內實測 artifact 讀得到（比照 pa_transition_taxonomy 的既有驗證方式）;uv run ruff check + uv run pytest + cd web && npm test + npx tsc --noEmit + npm run build:check;/api/info 與 recap 端點的路由快照 EXPECTED 同步
