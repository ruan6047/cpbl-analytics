# UX-ORPHAN-SWEEP1 孤兒模組第二批：`matchup-card` 與 `lib/cols`（含文件對帳）〔T2；🟦前端〕

- 需求：ruan6047（2026-07-29 依 `UX-LEADERS-ORPHAN1` 次要交付的盤點結果指示開卡）　規劃：本卡 spec　分支：`ai/<執行者>/UX-ORPHAN-SWEEP1`
- 執行：待指派（建議 L2；刪除本身簡單，但須連帶對帳三份文件）　查核：待指派（建議 L2；≠ 執行）
- Initiative：`INIT-PRODUCT-UX`　spec 基線：—
- DB：`db_scope: none`
- 部署：是（前端；但**移除本身無 runtime 效果**）　環境：web　PR：—　Merge SHA：—
- 範圍：`web/src/components/matchup-card.tsx`、`web/src/lib/cols.ts`＋`docs/AI_RUNBOOK.md`、`docs/design/UI_UX_SYSTEM.md`、`docs/design/UI_UX_CONFORMANCE.md`
- Discovery：—（T2，事實已於開卡時查證）
- Design：**Design Gate N/A**——兩支皆不被任何頁面渲染，移除對使用者可見介面零影響。

## 事實（開卡時查證）

`UX-LEADERS-ORPHAN1` 的孤兒盤點掃出兩個真孤兒，經逐一查證確認無任何 import：

- **`web/src/components/matchup-card.tsx`（137 行，`export function MatchupCard`）**——失去引用於 `6e4a429`（2026-07-19，`feat(web): retire legacy prediction experience`，`/predict` 頁移除 375 行）。
- **`web/src/lib/cols.ts`（59 行，`export matchupCols` / `vsTeamCols`）**——失去引用於 `948bb21`（2026-07-18，`feat(web): rebuild /matchups as query-driven matchup explorer`）。新版 `/matchups` 只有 `page.tsx` 與 `matchups-client.tsx`，共用元件在 `components/matchups/`，皆不使用這支；`/batters`／`/pitchers` 用的 `Col` 型別在 `components/leaderboard.tsx`，也不是這支。

**它們與 `LeagueLeaders` 的差別在於：文件還在追蹤它們。** 這是本卡的重點，不是刪兩個檔。

## 這批孤兒有具體代價，而且已經發生了

`UX-LEADERS-ORPHAN1` 的論證是「下架後 11 天內被兩張卡改過兩次」。本卡有更精確的一例：

**`b023385`（2026-07-24，`fix(web): amber token + three-state loading (HYGIENE1 H5-H6)`）修改了 `matchup-card.tsx`**，把 Tailwind 數字色階 `amber-600` 改成語意 token `text-amber`——**那是對一個沒有任何使用者渲染的元件做規格對齊**。付出的是真實的執行與查核成本，換到的是零。

更糟的是**帳面現在同時錯兩層**：`UI_UX_CONFORMANCE.md` 仍把 `matchup-card` 的 amber 違規列為 **H5 🟡 未完成**，但 (a) 該違規已於 `b023385` 修掉、(b) 該檔根本不在產品裡。表格第 29 列還寫 `/matchups` 使用 `matchup-card.tsx:89/91`——`/matchups` 早已不引用它。**一份追蹤著不存在之物的規格，會讓下一個人再花一次工。**

## 待對帳的文件（刪檔之後必須同步，否則規格會指向不存在的檔案）

- `docs/AI_RUNBOOK.md:244`（`lib/` 地圖列 `cols.ts`）、`:245`（元件地圖列 `matchup-card`）。
- `docs/design/UI_UX_SYSTEM.md:172`（硬編色違規現況清單點名 `components/matchup-card.tsx`——**且該違規已修**）、`:520`（共用領域元件表）、`:552`（共用欄定義表列 `lib/cols.ts` 的 `matchupCols`／`vsTeamCols`）。
- `docs/design/UI_UX_CONFORMANCE.md:29`、`:46`、`:61`、`:91`（H5 與相關列）。

## 紅線

1. **刪碼與對帳必須同一個變更**。刪了檔卻留著指向它的設計系統文件，比不刪更糟——會製造一份指向不存在檔案的規格。
2. **不得順手把 H5 整條劃掉**。H5 涵蓋 `standings` 與 `matchup-card` 兩處；開卡時實測 `standings/page.tsx` 已無 `amber-[0-9]` 數字色階（`b023385` 一併修了），**但這需由執行者重新確認**——若 `standings` 那半確實也已完成，應改為關閉並註明完成 commit，而不是因為本卡刪了 matchup-card 就把整條抹掉。
3. **不得為了讓清單變乾淨而刪掉仍有使用者的東西**。`UX-LEADERS-ORPHAN1` 的掃描器曾把兩支 fixtures 誤報為孤兒（測試以帶副檔名的路徑引用），本卡兩支已逐一查證，**執行者仍須自行重驗**，不得只採信前卡結論。

## 驗收條件

- [ ] 兩支檔案移除，且全 `web/` 零殘留引用（含動態 import、字串路徑、barrel re-export 等 `rg` 直覺寫法會漏的形式）。
- [ ] 三份文件的對應條目同步更新：地圖移除該檔、共用欄定義表處置 `cols.ts` 那列、`UI_UX_SYSTEM.md:172` 的違規現況移除 `matchup-card`。
- [ ] `UI_UX_CONFORMANCE.md` 的 H5 依紅線 2 處置：`matchup-card` 那半註明「檔案已移除（本卡）」，`standings` 那半依實測結果關閉或保留，**兩者各自交代**。
- [ ] **差異為零的證明**：比照 `UX-LEADERS-ORPHAN1` 的做法（移除前後各建置一次、比對路由表逐行相同），證實兩支從未被打包。
- [ ] `npm run build:check` 21 routes 全通過、`npm test` 全過。

## 驗證

- [ ] 查核者以**不同於執行者**的搜尋判準獨立確認零引用。
- [ ] 查核者確認三份文件已無指向被刪檔案的字串（`rg 'matchup-card|lib/cols|cols\.ts' docs/` 應只剩歷史敘述，例如本卡與 `UX-LEADERS-ORPHAN1` 的 Log）。
- [ ] 查核者確認 H5 的 `standings` 那半沒有被本卡順手抹掉。

## 邊界

- 只處理這兩支與其文件對帳；**不擴張為全站死碼大掃除**。若執行過程再掃出新孤兒，出清單、開後續卡。
- 不改 `/matchups`、`/batters`、`/pitchers` 的任何行為。
- 預估 S。

## Log

- 2026-07-29 register by Claude Opus 5@Claude Code（Coordinator，依 ruan6047 指示）；iteration 0。來源：`UX-LEADERS-ORPHAN1` 次要交付的孤兒盤點。**開卡前另查出兩件前卡未涵蓋的事實**：(1) 三份文件仍在追蹤這兩支，刪碼必須連帶對帳；(2) `b023385` 曾對已無人渲染的 `matchup-card` 做 amber token 規格對齊，而 `UI_UX_CONFORMANCE` 至今仍把該違規列為未完成——**帳面同時錯兩層**。這使本卡的價值從「刪 196 行死碼」變成「止住一條會反覆消耗工時的假帳」。
