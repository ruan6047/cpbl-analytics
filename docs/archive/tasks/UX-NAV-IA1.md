# UX-NAV-IA1 方案 B 導覽與全域球員搜尋〔T3；⚪一般〕

- 需求：ruan6047　規劃：GPT-5@Codex＋Fable-5　分支：`ai/opus-4-8/UX-NAV-IA1`
- 執行：Opus-4.8@Claude Code　查核：待指派（須 ≠ 執行）
- worktree：`.claude/worktrees/ux-nav-ia1-execution-08c218`
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2
- DB：`db_scope: read`　部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：[`PRODUCT_UX_BLUEPRINT.md`](../PRODUCT_UX_BLUEPRINT.md) §4、§5.5、§12
- Discovery：需求方已核可方案 B　Design：需求方 2026-07-17 核可；球員預設排行與紀錄室桌機位置由 prototype 決定

## 目標與驗收

- [ ] Header 呈現今日／賽程／戰績／球員／對戰＋更多；更多收納紀錄室、球場、方法，不建立 `/players` 或 `/explore`。
- [ ] 全域球員搜尋可鍵盤操作、具 loading／empty／error 狀態，選定後直達 `/players/[id]`；「球員」直達排行並可切換打者／投手。
- [ ] 375 px 與桌機保留年份、月份月曆、紀錄室等歷史入口；完成球員預設排行與紀錄室桌機位置 prototype 決策。

## 驗證與依賴

- 驗證：元件測試、鍵盤／螢幕閱讀器與 375 px 瀏覽器走查；`npx tsc --noEmit`、`npm run build:check`。
- 依賴：無；與所有修改 `layout.tsx`、header、nav 的卡序列化。
- 預估範圍：M；包含原候選 `UX-MORE-NAV1`，不再另開重疊卡。

## Design 決策（需求方 2026-07-17 於執行 session 定案）

1. §12-3 「球員」導覽固定進 `/batters`：行為可預測、deep-link 穩定、SSR 無閃爍；角色切換留在排行介面內。不採「記住上次角色」（href 無法在 SSR 決定）。
2. §12-2 紀錄室桌機維持在「更多」：完全照 §4.1 表格，桌機與行動版 IA 一致。
3. 舊「賽事預測」暫收「更多」：符合 §4.1「不競爭主要導覽位置」與 §7.1 replacement before removal；首頁替代品（`UX-GAME-HOME1`）未上線前不切斷唯一入口，移除由 `DEP-PREDICT-LEGACY1` 負責。
4. ~~「方法」暫不列入導覽，本卡只交付 `/methodology` 的 anchor map，待 `UX-MODEL-METHOD1` 建立頁面時才加導覽項~~
   → **iteration 2 推翻**：查核 P1 指出此舉未經基線修訂即偏離驗收；需求方 2026-07-17 裁決由本卡建立 `/methodology` 骨架頁並將「方法」加入「更多」。

## Log

- 2026-07-17 實作 by Opus-4.8@Claude Code：新增 `lib/nav.ts`（方案 B 導覽模型與 `isNavActive`／`isMoreActive`）、`lib/methodology-anchors.ts`（§5.14 五段 anchor map）、`lib/player-search-filter.ts`（roster → 搜尋項、二刀流合併、空 query 不回結果）。header 常駐全域球員搜尋（combobox／listbox、↑↓ 移動、Enter 直達、Escape 收合、`aria-activedescendant` 同步、loading／empty／error＋重試四態）；桌機新增「更多」下拉；行動端面板置入搜尋並改為主要／更多兩組。
- 既有缺陷修正（本卡範圍內必要）：行動端選單面板原為 `<header>`（`backdrop-blur-md`）的 fixed 子元素，backdrop-filter 會為 fixed 後代建立 containing block，面板被夾成 header 高度。實測本機與**生產站 <https://cpbl.ruan-ruan.com> 同為 49px 且 nav 連結 `elementFromPoint` 全部被頁面內容蓋住（不可點）**，屬既有 bug 非本卡引入。改以 `createPortal` 掛到 `document.body`、依實際 header 底緣定位；修正後面板 375×739、8 個連結全部可點、觸控高度 44px。連帶移除已失準且無其他用途的 `--header-height`（宣告 57px，實際 65→73px）。
- 自測：`npm test` 23 passed（新增 nav 10／player-search-filter 7／methodology 3）、`tsc --noEmit` 通過、`npm run build:check` 通過、`uv run ruff check` 通過、`uv run pytest` 255 passed、`workflow_ledger.py --check` 通過。
- 瀏覽器實測（本機 dev，API :4001／web :3000）：桌機 1280 導覽為今日／賽程／戰績／球員／對戰＋更多；搜尋「林」→ ↓↓ → Enter 直達 `/players/0000003339`（林哲瑄），且個人頁「球員」仍 `aria-current="page"`。375 px 面板搜尋「王柏融」→ 直達 `/players/0000000935`，面板自動關閉、body 捲動鎖復原。error 態以攔截 roster request 實測，重試後恢復 8 筆結果；empty 態顯示「找不到符合的球員」。768 px 無擠壓；乾淨載入 console 無錯誤與 hydration 警告。
- 未觸及：`/predict` 頁面本體、`/methodology` 頁面（分屬 `DEP-PREDICT-LEGACY1`、`UX-MODEL-METHOD1`）；`db_scope: read`，未動 DB、未部署。

### iteration 2（2026-07-17，回應查核退回 @ `2e32734`）

**P1 未交付「方法」導覽與 `/methodology` 路由 — 已修正（部分不同意，依需求方裁決執行）。**

- 不同意的部分：藍圖 §9 Phase 0 給本卡的字面範圍是「方案 B 導覽、全域球員搜尋、「更多」與 **methodology deep-link map**」，而 `/methodology` 頁本體是 [`UX-MODEL-METHOD1`](UX-MODEL-METHOD1.md) 驗收第 1 項；由本卡建頁會與該卡 owner 邊界重疊。
- 同意的部分：查核者「若要延後，須先正式修訂並重新核可基線」是對的。需求方的決策我只寫進本卡 Log，未回寫藍圖基線，違反 canonical §3「禁止只在子卡內靜默改方向」。這是本卡的實質程序缺失。
- 需求方 2026-07-17 裁決：由本卡建立 `/methodology` **骨架頁**並將「方法」加入「更多」。已實作 `web/src/app/methodology/page.tsx`：五個段落（賽前勝率／場中 WP／打席結果分布／對戰 credibility／推定球種）**直接由 `METHODOLOGY_SECTIONS` 產生**，anchor 因此無法與 badge 連結漂移；`MORE_NAV` 加入「方法」，路徑一致性由 `nav.test.ts` 守住。
- **骨架頁不含任何回測數字、baseline 或版本**：未經查核的數字比空白更糟（CLAUDE.md ML 紅線）。頁面以 Notice 明示「本頁目前只有骨架…請勿將此頁視為模型已通過驗證的依據」。各段實際內容仍屬 `UX-MODEL-METHOD1` 驗收範圍，本卡不代填。
- 遺留風險（交由需求方／查核者判斷）：本卡部署後，production 會出現一個五段皆為「內容建置中」的頁面，直到 `UX-MODEL-METHOD1` 完成。

**P2 commit trailer 不完整 — 不同意，未修改，理由如下。**

- canonical §6 原文：「T0／T1 的直接 commit 至少記錄 `Requested-by` 與 `Implemented-by`；T2 以上的**實作** commit 必加 `Planned-by`」。
- 被點名的 `d53be1c` 是 control-plane claim、`2e32734` 是卡片 Log，依 canonical §0 分類表均為 **B1 記錄文件（T0）**，非實作 commit，現有兩個 trailer 已符合規則。
- 本卡真正的實作 commit 是 `27db0e6`，其 `Requested-by`／`Planned-by`／`Implemented-by` 三者齊全（已複查）。
- P2 似將「卡片 tier = T3」套用到 B1 記錄 commit。需求方 2026-07-17 裁決維持現狀、不改寫已推送歷史（避免已審 SHA 失效）。若原意確為「T3 卡的所有 commit 都需三個 trailer」，應修訂 ai-workflow canonical §6 文字（另卡），而非在本卡補簽。

**iteration 2 自測**：`npm test` 24 passed（nav 新增「方法路徑與 METHODOLOGY_PATH 一致」「方法不佔主要導覽」，移除已失效的「方法不進導覽」）、`tsc --noEmit`、`build:check`（`/methodology` 靜態產生 1.73 kB）、`ruff`、`pytest` 255 passed 全通過。瀏覽器實測：`/methodology#matchup-credibility` deep-link 命中且未被 sticky header 遮蔽；頁面 5 個 `h2[id]` 與 `METHODOLOGY_SECTIONS` 完全一致；桌機「更多」下拉含方法且在該頁標 `aria-current="page"`、「更多」按鈕同步作用中；375px 面板 9 個連結全部可點。

### 結案（2026-07-17）

- reviewed SHA `f6c8aa2` 以 non-fast-forward merge 合併為 `d22f5da`（trailer 含 Reviewed-by: GPT-5@Codex），cpbl CI run `29556096801` 全綠。
- 主站 submodule 部署提交 `ddd642b`：主站 CI run `29556135963` 全綠、Deploy run `29556263509`（Deploy to VPS）成功，13:05:50+08:00 完成。
- production smoke test（17:10+08:00）：`/` 200、`/api/info` status=running；`/methodology` 200 且五段 `h2[id]`（pregame／winprob／pa-sim／matchup-credibility／pitch-type）與 `METHODOLOGY_SECTIONS` 一致；導覽含「更多」與全域球員搜尋；`/records`、`/venues` 200。
- 本地／遠端分支 `ai/opus-4-8/UX-NAV-IA1`、execution worktree 與 lease 均已清除；卡片封存。結案留痕因 Codex session 額度用盡由 Claude Fable 5 接續補記。

## 查核重點

- 確認導覽與 §4.1 表格一致，且未建立 `/players`／`/explore`；「更多」暫留「賽事預測」的理由（§7.1 順序）已於 iteration 1 查核接受。
- iteration 2 新增：`/methodology` 骨架頁不得含任何未經查核的模型數字；確認五段 anchor 由 `METHODOLOGY_SECTIONS` 產生而非手寫；確認本卡未侵入 `UX-MODEL-METHOD1` 的內容驗收（只有骨架與 anchor，無 baseline／版本）。
- iteration 2 的 P2 為執行者不同意並保留原狀，請直接就 canonical §6「實作 commit」的定義裁定，勿只看卡片 tier。
- 確認 portal 修正未破壞焦點陷阱、Escape 關閉與路徑改變自動收合；面板在 `md` 以上不應出現（已加 `md:hidden`）。
- 確認搜尋僅為導航用途，未混入模型或排名語意（§5.5「ML 使用：無」）。
- 已知限制：roster 只含本季名單（退役／歷史球員無法由搜尋抵達），且結果上限 8 筆時打者先於投手，常見姓氏（如「林」）需再輸入才會出現投手。此為沿用既有 `/api/v1/players/roster` 契約，未在本卡擴大範圍。
