# UX-PLAYER-IA2 球員頁 IA 修訂：role 拆標籤＋守備獨立層〔T3；⚪一般〕

- 需求：ruan6047　規劃：Claude（Opus 4.8）　分支：`ai/<執行者>/UX-PLAYER-IA2`
- 執行：待指派　查核：待指派（須 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2＋[`UX-PLAYER-IA2-BRIEF.md`](../design/UX-PLAYER-IA2-BRIEF.md)
- DB：`db_scope: none`（純前端；不動 API）　部署：是　環境：production
- 範圍：修訂 [`UX-PLAYER-IA1-DECISION.md`](../design/UX-PLAYER-IA1-DECISION.md) §1 凍結項（該檔 §7 已記修訂）
- Discovery／Design：需求方走查上線版後提出；Brief 方向已於 2026-07-20 核可

## 目標與驗收

- [ ] **role 切換鈕移除**，改攤為標籤頁：雙棲＝`打擊｜投球｜分項與對戰｜守備｜生涯`；純打者無「投球」頁、純投手無「打擊」頁。
- [ ] **守備獨立成同級標籤層**（自生涯層移出），內容與 UX-PLAYER-FIELDVIZ1 上線版一致。
- [ ] **總覽／分項與對戰／生涯在雙棲時兩身分上下堆疊**（主身分在上，各有身分小標），不使用任何隱性 role 狀態。
- [ ] **守位身分圖僅在多守位（≥2 守位）時渲染**——單一守位時等於重畫表格一列，無增值。
- [ ] **舊連結相容**：`?sec=approach` 導向主身分內容頁；`?role=` 仍接受但僅在未給 `?sec=` 時決定落點，不再控制全頁。
- [ ] 依層延後載入維持，無跨層重複請求；鍵盤 ←/→ 正常；375px 不橫捲。

## 驗證與依賴

- 驗證：純函式測試（標籤組成、舊參數相容、堆疊判定）、五情境瀏覽器走查（雙棲／純打者／純投手／退役／二軍）、375px、`tsc`、`build:check`、`ruff`、`pytest`。
- 依賴：UX-PLAYER-SECTIONS1、UX-PLAYER-FIELDVIZ1（皆 🏁完成且已上線）。
- 預估範圍：M（層結構重排＋堆疊渲染＋參數相容）。
- 非目標：不改 API、不動守備價值卡的統計口徑、不重啟分區熱區圖（研究已否決）。
