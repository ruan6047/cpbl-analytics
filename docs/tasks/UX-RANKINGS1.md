# UX-RANKINGS1 打者與投手排行減法〔T3；⚪一般〕

- 需求：ruan6047　規劃：GPT-5@Codex＋Fable-5　分支：`ai/<執行者>/UX-RANKINGS1`
- 執行：待指派　查核：待指派（須 ≠ 執行）
- Initiative：INIT-PRODUCT-UX　spec 基線：PRODUCT_UX_BLUEPRINT v0.2
- DB：`db_scope: read`　部署：是　環境：production　PR：—　Merge SHA：—
- 範圍：[`PRODUCT_UX_BLUEPRINT.md`](../PRODUCT_UX_BLUEPRINT.md) §5.5–§5.6
- Discovery：排行是高頻入口但現況欄位密度過高　Design：需求方核可 6–8 個預設欄位與角色切換

## 目標與驗收

- [ ] `/batters`、`/pitchers` 以主指標＋最多 6–8 欄呈現，完整欄位由使用者切換或展開；不混入 projection／未過 gate 的 Stuff+。
- [ ] 375 px 顯示排名、球員、球隊、主指標與最多 2 個支持指標，不把水平捲動當唯一方案。
- [ ] 年份、資格門檻、排序與球員 deep-link 保留，改版前後歷史查詢結果零退化。

## 需求方 review 迭代定案（2026-07-21，ruan6047）

執行後由需求方人工審查（本地環境走查），追加下列定案，皆已實作於交付：

- **識別欄合併**：隊名改為球員名前的隊徽 icon；守位（打者）/角色（投手）標籤併入球員名欄
  （stack 於名下），移除獨立欄。
- **加值指標**：新增 OPS+（打者）/ERA+（投手），僅一軍、league-only（沿 `trend.py` 聯盟基準，
  非球場校正）；後端 leaders API 即時補算。仍不混 projection、Stuff+ 未過 gate 不採。
- **角色切換**（§5.5）：`/batters`↔`/pitchers` 分段切換，保留一/二軍與年份。
- **打者加「打席」欄**（第 8 欄，桌機）；投手「局數」為同等樣本量欄。
- **小樣本門檻**：以率值欄排序時，達規定打席/局數者排名在前並計名次，未達者置底、灰階、
  名次「–」，**全體清單保留**；bar 色階用達標者值域並 clamp [0,1]。計數欄排序不套門檻
  （全員排名，符合棒球慣例）。

## 驗證與依賴

- 驗證：表格／排序測試、375 px 與鍵盤走查、歷史年份對照、`tsc`、`build:check`。
- 依賴：可與 UX-PLAYER-IA1 平行；與 UX-NAV-IA1 協調「球員」預設入口。
- 預估範圍：M。
