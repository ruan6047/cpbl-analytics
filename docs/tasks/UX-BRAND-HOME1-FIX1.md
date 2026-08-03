# UX-BRAND-HOME1-FIX1 description metadata 未隨品牌與副標收斂〔T2；🟦前端〕

- 需求：ruan6047（2026-08-03 上線後抽驗生產 metadata 時發現）　規劃：本卡 spec　分支：`ai/<執行者>/UX-BRAND-HOME1-FIX1`
- 執行：待指派（建議 L1；兩行文案替換，決策已由需求方定案）　查核：待指派（建議 L2；≠ 執行）
- Initiative：`INIT-PRODUCT-UX`　spec 基線：父卡 `UX-BRAND-HOME1`（已合併 `44deedf`、已部署驗證）
- review_independence: [cross_family_or_human]
- DB：`db_scope: none`
- 部署：是（前端）　環境：生產　PR：—　Merge SHA：—
- 範圍：`web/src/app/page.tsx`、`web/src/app/layout.tsx`、`web/src/app/methodology/page.tsx`（執行時發現第三處同型缺陷，見〈Log〉）
- Discovery：不適用——缺陷與修法皆已確定，文案由需求方定案。
- Design：Design Gate 已由需求方完成（兩句文案 2026-08-03 逐句核可）。

## 問題陳述

父卡 `UX-BRAND-HOME1` 收斂了站名、title 與 hero 副標，**但漏掉 `description` metadata**。上線後打生產抽驗才發現兩處殘留：

**其一，首頁 description 用的是需求方已否決的文案。** `page.tsx:12` 仍為「從最近賽事到下一場對戰，用可追溯的數據看懂中職。」——這正是人工審時被退回的那句，退回理由是「它在複述下方區塊的內容，副標應該講整個網站」。hero 副標已改為「用視覺化與數據分析，把棒球看得更懂。」，但 metadata 是**另一個字串**，沒有跟著改。

後果：分享到社群時，預覽卡的說明文字用的是被否決的框架，且與頁面上實際看到的副標不一致。生產實測 `<meta name="description">` 與 `<meta property="og:description">` 兩者皆為舊句。

**其二，「資料實驗室」與品牌名的「數據實驗室」用詞不一致。** `layout.tsx:13` 寫「非官方**資料**實驗室」，而站名是「Ruan's 中職**數據**實驗室」。同一個概念在品牌名與描述裡用了兩個詞——**這是父卡命名收斂的漏網，不只是文案微調**。父卡〈驗收條件〉只要求 `grep` 不再命中舊站名字串（`CPBL 分析`／`CPBL Analytics`／`Ruan Dev`），沒有涵蓋「語意同義但用詞不同」的情形，故三輪查核都沒抓到。

**順帶補上父卡自陳但未執行的 SEO 補償。** 父卡〈SEO 風險〉載明：新 h1 丟掉了「中華職棒」與「視覺化」，**「首頁 title（`absolute`）與 meta description 必須補回被丟掉的關鍵字」作為部分補償**。實際上只做了 title，description 沒做——本卡一併補齊。

## 定案文案（需求方 2026-08-03 逐句核可）

**`page.tsx:12`**

> 用視覺化與數據分析，把中華職棒 [CPBL] 的比賽、球員與歷史看得更懂——賽況復盤、進階數據與賽前勝率，非官方獨立專案。

結構與 hero 副標一致（手段 → 目的 → 範圍），並補回「中華職棒」與 `CPBL` 兩組關鍵字。

**`layout.tsx:13`**

> 中華職棒戰績、進階數據與賽事預測的非官方數據實驗室。

將舊用詞改為「數據實驗室」以對齊品牌名。**執行時發現同型缺陷共三處**：`layout.tsx:13` 之外，`methodology/page.tsx:349`（父卡新增的「關於本站與作者」段落）亦寫「可追溯的中職資料實驗室」，一併修正。**已知並接受的代價**：「數據」在同一句出現兩次（進階數據、數據實驗室）。曾評估把「進階數據」改為「進階指標」以避免重複，但「進階數據」是本站對應官方進階數據的既定用語，**為修辭去動既定術語不划算**——需求方裁定品牌一致性優先。

## 非目標

- 不改 hero 副標（已於父卡定案並上線）。
- 不改 title、OG 圖、favicon、manifest 或任何父卡已驗證的產出。
- 不新增 `openGraph.description` 覆寫——現行 `og:description` 由 `description` 衍生，改一處即同步兩處，**不得為此新增第二個真相來源**。

## 紅線

1. **只改這兩個字串，不動任何其他 metadata 欄位。** 父卡剛通過三輪查核並上線，擴大範圍會讓本卡的驗收失焦。
2. **不得把「資料」批次替換成「數據」。** 全庫其他位置的「資料」多數是正確用法（資料來源、資料新鮮度、資料庫…），盲目取代會製造新錯誤。本卡只改 `layout.tsx:13` 這一處。

## 驗收條件

- [ ] `page.tsx:12` 與 `layout.tsx:13` 為上列定案文案，逐字相同。
- [ ] 全庫 `grep -rn "資料實驗室" web/src` 零命中。
- [ ] 建置後首頁的 `<meta name="description">` 與 `<meta property="og:description">` **兩者皆為新文案**（實測 HTML，非讀原始碼），且兩者一致（證明未新增第二個真相來源）。
- [ ] `git diff main...HEAD` 僅涉上列三檔；`page.tsx`／`layout.tsx` 僅動 description，`methodology/page.tsx` 僅動該一詞。
- [ ] 程式碼註解不得複述舊用詞——否則 `grep` 守衛會被自己的註解污染而永遠命中（本卡執行時已踩過並修正）。
- [ ] `cd web && npm test` ＋ `npm run build:check` 全綠。

## 驗證

- [ ] 查核者以建置後 HTML 實測兩個 meta 標籤，不接受原始碼推論。
- [ ] 查核者確認 diff 範圍未擴大（紅線 1）、未發生「資料」批次替換（紅線 2）。
- [ ] 查核通過前不得 merge main。
- [ ] 上線後打生產複驗兩個 meta 標籤。

## 邊界

- 兩行文案替換。預估 XS。
- 已知紅燈 `test_initiative_children_baseline_matches_parent_version` 屬 `UX-LIVE-TRACKMAN1`，不計入本卡。

## Log

- 2026-08-03 register by Claude Opus 5@Claude Code（依 ruan6047 指示）；iteration 0。來源：父卡上線後 Coordinator 打生產抽驗 metadata 時發現，**非查核者發現**——父卡三輪查核（含跨家族）皆未涵蓋 description，因〈驗收條件〉只要求舊站名字串零命中，對「語意同義但用詞不同」與「metadata 與畫面文案不一致」兩類問題沒有判準。「資料實驗室 vs 數據實驗室」由需求方指出。**可移交的教訓**：命名收斂類卡片的驗收條件不應只寫「舊字串零命中」，還需涵蓋同義詞與非畫面文案（metadata／OG／manifest）；是否寫回卡片規格慣例，可併入 `DOC-CARD-SPEC-RULES1` 評估。
- 2026-08-03 執行時發現**第三處同型缺陷**：`methodology/page.tsx:349` 的「可追溯的中職資料實驗室」——該段落正是父卡新增的「關於本站與作者」，與 `layout.tsx` 同一天寫入、同一個錯。開卡時只掃了 metadata 檔案，沒有先跑全庫 grep 就下了範圍，故卡面〈範圍〉原僅列兩檔。已擴為三檔並更新驗收條件。**這與本卡要修的是同一個病**：範圍憑印象界定而非先窮舉。另修正一處自傷——初版註解複述了舊用詞，會讓「全庫零命中」的 grep 守衛永遠失敗，已改為不複述。
