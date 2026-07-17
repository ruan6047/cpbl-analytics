# UX-NAV-IA1 方案 B 導覽與全域球員搜尋〔T3；⚪一般〕

- 需求：ruan6047　規劃：GPT-5@Codex＋Fable-5　分支：`ai/<執行者>/UX-NAV-IA1`
- 執行：待指派　查核：待指派（須 ≠ 執行）
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
