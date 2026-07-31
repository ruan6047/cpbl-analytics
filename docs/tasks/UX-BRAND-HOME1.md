# UX-BRAND-HOME1 站名品牌化與首頁門面升級〔T3；🟦前端〕

- 需求：ruan6047（2026-07-31 以 `grilling` skill 對抗式質詢，15 項決定逐一定案）　規劃：本卡 spec　分支：`ai/<執行者>/UX-BRAND-HOME1`
- 執行：待指派（建議 L2；已知模式的前端與 metadata 改動，設計決策已由需求方定案，執行者不需重做取捨）　查核：待指派（建議 L2；≠ 執行）
- Initiative：`INIT-PRODUCT-UX`　spec 基線：`PRODUCT_UX_BLUEPRINT` v0.2 §5.1／§8.4、`UI_UX_SYSTEM` v1
- review_independence: [human, cross_family]
- DB：`db_scope: none`
- 部署：是（前端）　環境：生產　PR：—　Merge SHA：—
- 範圍：`web/src/app/layout.tsx`、`web/src/app/page.tsx`、`web/src/app/globals.css`、`web/src/app/icon.svg`（新）、`web/src/app/opengraph-image.*`（新）、`web/src/app/manifest.ts`（新）、`web/src/app/methodology/page.tsx`、上述 10 個缺 metadata 的頁面、`src/cpbl/api/routers/daily.py`（statline 欄位）、`web/src/lib/api.ts`（型別）、`tests/`（`daily/summary` 契約測試）、`docs/PRODUCT_UX_BLUEPRINT.md` 與 `docs/design/UI_UX_SYSTEM.md` 的 H1、`README.md`
- Discovery：不適用——問題與解法已於 2026-07-31 的對抗式質詢中收斂，15 項決定全部有明確結論，無待驗證假設。
- Design：**Design Gate 已由需求方本人完成**（本卡的品牌命名、配色語意、mark 形式、hero 結構、免責落點皆為需求方逐項裁定）。Stage 2 交付後另有**本地人工審**作為第二道 Design Gate，見〈驗證〉。

## 問題陳述

需求方的原始抱怨是「首頁完成度過低、版本跟其他 UI 不一致」，並希望站名帶入個人 ID、整體「像個產品而不是範例」。查證後，這句抱怨底下其實是三個性質不同的問題，而**最直覺的那個診斷是錯的**：

**首頁不是沒做完，是刻意做薄的。** blueprint §5.1 白紙黑字要求首頁移除十套榜單，`UI_UX_CONFORMANCE.md:22` 也把 `/` 評為 🟢「無明顯偏離」。需求方在質詢中確認：抱怨的是**品牌與視覺完成度**，不是資訊量。本卡因此**不動 §5.1 的資訊預算**，`/predict` 下架後的資訊架構維持原案。

真正的成因有三處，都不在「內容多寡」：

**其一，品牌識別是零。** 全站四種站名字串並存——header `CPBL 分析`、layout title `CPBL 分析 | Ruan Dev`、footer `© CPBL Analytics.`、首頁 title 又覆寫成 `CPBL 分析 | 中華職棒數據視覺化`，canonical 文件則寫 `CPBL Analytics`。更根本的是 `web/public` 目錄**不存在**，沒有 favicon、沒有 OG image、沒有 manifest，`metadata` 也沒有 `openGraph`／`twitter`——分享到任何社群平台出來都是無預覽圖的裸連結，瀏覽器分頁是預設地球圖示。這些是「看起來像範例」最客觀的證據，而且與設計品味無關。

**其二，wordmark 在排版上沒有字體識別。** `layout.tsx:14` 載入 Outfit，`globals.css:67` 把它綁到 `--font-mono`，而 body 用 `system-ui`（`globals.css:114`）。**Outfit 並非沒被使用——實測 `font-mono` 161 處、`tabular-nums` 144 處，全站表格數字都靠它**（變數名叫 mono 但 Outfit 是幾何無襯線體，這是既有的命名誤導，本卡不處理）。真正缺的是：Outfit 沒有任何 display 用途的綁定，所以 header wordmark 走的是 body 的 `system-ui`；而 Outfit 只載 `subsets: ["latin"]`，中文本來也拿不到它。結論是 **wordmark 必須是英文才吃得到字體識別**，這也是 wordmark 定為英文、中文全名退到 h1 與 OG 的原因。

**其三，20 個頁面裡有 11 個沒有 title metadata**（`/batters`、`/games`、`/games/[sno]`、`/people/[kind]/[name]`、`/pitchers`、`/players/[id]`、`/predict`、`/records`、`/standings`、`/teams/[code]`、`/umpires`），全部繼承 layout 那一句，也就是這些頁的瀏覽器分頁標題**完全相同**。這不只是觀感：跨頁重複 title 是明確的 SEO 負分，使用者開多分頁時也真的分不出哪個是哪個。根因是 layout 用純字串 title 而非 `title.template`。另外 `/matchups` 的 title 是 `投打對決`，**連站名後綴都沒有**。

## 品牌定案（需求方裁定，執行者不得自行更動）

**Wordmark**（header logo、title 後綴）：`Ruan's CPBL Lab`
**中文全名**（hero h1、OG、about、footer）：`Ruan's 中職數據實驗室`

中文全名用 `Ruan's ` 加半形空格接中文，**不改寫成「Ruan 的」**——需求方裁定：「的」會讓它讀起來像一句話而不是一個名詞。英文 wordmark 保留所有格撇號，中文全名同樣保留，兩者的 `Ruan's` 一致。

**wordmark 三段語意色**：`Ruan's` → `--color-accent`（本站身分）／`CPBL` → `--color-cpbl`（指涉聯盟）／`Lab` → `--color-ink`。

這是**延伸現有模式，不是修正違規**——現行 wordmark 已是雙段配色（`layout.tsx:47`：`CPBL` 用 `text-cpbl`、`分析` 用 `text-accent`），語意本就成立。新命名多出 `Lab` 一段，故補上第三個角色。

要留意的是**比例而非對錯**：`--color-cpbl` 在設計系統 §2.1 的定義是「CPBL 品牌藍」、§9.1 補述為「聯盟層級用途，非隊色」。新 wordmark 以 `Ruan's`（accent）起首，聯盟藍在整個 lockup 中的視覺權重下降，本站身分的權重上升——這對一個必須維持非官方聲明的站是正確方向。三段各自有成立的語意，符合 §1-3「顏色必有語意、禁裝飾用色」。

**Logo mark**：本壘板五角形內嵌 `R`，SVG 手刻，深淺兩態，作為 favicon、header wordmark 前的圖標與 OG 圖主視覺。選它的判準是 **16px 下必須仍可辨識**——好球帶九宮格的意象雖然更貼近本站差異化，但 3×3 網格在 favicon 尺寸會糊成一塊，故否決。

**OG 圖**：mark ＋ wordmark ＋ 純色或漸層背景，**不加九宮格紋理**（社群動態牆通常只有 300–400px 寬，紋理在該尺寸下是雜訊且與前景搶注意力）。

## Stage 1｜確定性交付

一次寫完即可驗收，無設計迭代。

**品牌字串統一**：`layout.tsx` 的 wordmark（三段語意色）、footer、metadata；移除 `page.tsx` 對站名的重複覆寫。

**title 系統**：`layout.tsx` 改用 `title: { default, template }`。靜態 6 頁（`/batters`、`/games`、`/pitchers`、`/records`、`/standings`、`/umpires`）補 `export const metadata`；動態 4 頁（`/games/[sno]`、`/players/[id]`、`/teams/[code]`、`/people/[kind]/[name]`）補 `generateMetadata` **並帶實體名**（球員名、比分或對戰、隊名、人物名）——這是本批改動 SEO 收益最大的部分，不可簡化成固定字串。`/matchups` 的裸 title 改為只寫頁名、由 template 補後綴。`/methodology`、`/venues`、`/venues/[venue]` 移除硬編的 `| CPBL 分析` 後綴，改吃 template。`/predict` 是 7 行 stub/redirect，**不處理**。

**首頁 title 必須用 `absolute`。** `template` 會對所有設了 title 的頁面串接後綴，首頁若寫 `title: "Ruan's 中職數據實驗室"` 會被渲染成 `Ruan's 中職數據實驗室 | Ruan's CPBL Lab`——同一個字串出現兩次 `Ruan's`。首頁必須用 `title: { absolute: "…" }` 繞過 template，且該字串須自行含關鍵字（現行首頁 title 的「中華職棒數據視覺化」不可無故丟失，見〈SEO 風險〉）。反過來，若首頁**完全不設** title 則會落到 `default`，同樣丟失關鍵字——兩條路都不能無意識地走。

**視覺資產**：`app/icon.svg`（本壘板 mark，深淺兩態）、靜態 OG 圖 1200×630、`app/manifest.ts`、layout 補 `openGraph` 與 `twitter` metadata。

**字體綁定（純增量，不得搬移）**：新增 `--font-display: var(--font-outfit)` 並套用於 wordmark。**`--font-mono: var(--font-outfit), monospace` 這一行完全不動。** 把 Outfit 從 `--font-mono` 拔走會讓全站 161 處 `font-mono` 與 144 處 `tabular-nums` 的數字退化為系統 monospace，破壞所有表格的數字視覺——這是本卡最容易誤踩的破壞性改動。

**footer 改寫**：刪除「僅供學習與作品集用途」，改為中性免責——非官方獨立專案、與中華職棒大聯盟無隸屬關係、資料來源標注（cpbl-opendata MIT、cpbl.com.tw、stats.cpbl.com.tw）。**不寫死「非商業用途」**（需求方為 solopreneur 雙軌，寫死等於自設限，且爬蟲資料的商業使用本就是另一層次的風險，不該由一句 footer 預先承諾）。版權行改為 `© <年> Ruan's CPBL Lab`。加署名列：作者、`ruan-ruan.com`、GitHub repo。

**statline 資料併入 `daily/summary`**：在 `daily.py` 的 `daily_summary` 回應中新增 statline 欄位，**不讓首頁多打一次請求**（首頁請求數維持 2，保留 1 個 §8.4 配額）。三個口徑細節不可搞錯：(a) statline 是**全史涵蓋**，`games_indexed`／`seasons_covered` 須**不受 `kind_code`／`season` 參數影響**——否則切到二軍時全站場次數會跟著變，是明顯錯誤；(b) 模型指標沿用 `outcome_gbm` 寫進 `model_versions` 的同一份數據，與 `/api/info` 同源，不得各算各的；(c) `daily_summary` 現行契約是「DB 失效時讓錯誤上浮 500 而非回空陣列」（見其 docstring），新增欄位不得改變此行為。

**契約測試**：pytest 斷言 `daily/summary` 含 statline 欄位，且 `games_indexed`／`seasons_covered` 在不同 `kind_code` 下數值相同（守住上述 (a)）。模型指標為**可選欄位**——`model_versions` 空表時合法缺席（`info.py:79-88` 的 `try/except` 即此設計），測試須斷言「模型指標缺席時其餘欄位仍完整」，**不得斷言其必然存在**。

**文件改名**：`docs/PRODUCT_UX_BLUEPRINT.md` 與 `docs/design/UI_UX_SYSTEM.md` 的 H1、`README.md`。`UI_UX_SYSTEM.md` 是已 sign-off 的 canonical，標題變更須在該檔頂部狀態行留痕。

## Stage 2｜設計迭代（需人工審）

**卡片只鎖結構，文案與配色留給人工審迭代**，執行者不得把首版文案當定案。

**hero 重寫**（`page.tsx`）：h1 ＝ 中文全名 `Ruan's 中職數據實驗室`（品牌全名本身即含「中職數據」關鍵字，一個版位同時吃到品牌鄭重呈現與 SEO）；副標 ＝ 價值主張句；可信度 statline ＝ 三項來自 `/api/info` 的即時數字；CTA×2 維持；**搜尋框改為行動版顯示、桌機隱藏**（與 header 的 `hidden md:block` 相反，使兩種裝置各恰好一個，解決現行桌機雙搜尋框的冗餘）；加一層品牌視覺。

「非官方」聲明**只留 footer，不進 hero**——新命名的個人所有格開頭已承擔第一層辨識，非官方 fan site 的免責放 footer 是業界慣例。

**`/methodology` 加「關於本站與作者」段落**：為什麼做、資料從哪來、模型怎麼被驗證、作者是誰。**不開 `/about` 新頁**——導覽 5+1 是 blueprint §4.1 定案（需求方 2026-07-17 決策），動它屬產品層變更，與本卡定位衝突。

statline 具體選哪三個數字，於人工審時定案；候選為 `seasons_covered`、`games_indexed`、`outcome_model_accuracy` 對 `outcome_baseline_accuracy`（計算邏輯已存在於 `src/cpbl/api/routers/info.py:34-88`，本卡是把等價口徑接進 `daily/summary`）。Stage 1 的契約測試欄位清單隨此定案同步。

**§3.1 首屏預算的誠實記帳。** blueprint §3.1 規定第一個 viewport「1 個主要結論、最多 3 個支持證據、1 個主要下一步」。hero 的對應是：h1 ＝主要結論、statline 三項＝支持證據（**用滿上限，之後不得再加**）、CTA 收斂為 1 主 1 次。副標不計入（它是結論的說明句，非獨立證據）。

**需明白記錄的既有偏離**：現行 hero 已有兩顆對等的膠囊 CTA（`本季戰績`／`賽況與 Box`），嚴格讀 §3.1 的「1 個主要下一步」本就超出。本卡把它改為主次分明（主 CTA 實心、次 CTA 文字或外框）以貼近規則，但**不宣稱完全合規**——若人工審後仍維持兩顆對等按鈕，須在卡面 Log 記為已知偏離，不得靜默帶過。

## SEO 風險（規劃期低估，據實補記）

規劃階段只論述了改名的 SEO **好處**（`title.template` 消除跨頁重複 title、逐頁 title 帶實體名），**未計成本**。兩項成本必須寫在帳上：

**其一，h1 的關鍵字被稀釋。** 現行 h1 是「非官方中華職棒 [CPBL] 數據視覺化」，涵蓋「中華職棒」「CPBL」「數據視覺化」三組高意圖詞。新 h1 `Ruan's 中職數據實驗室` 加入了零搜尋量的品牌詞 `Ruan's`，並丟掉「中華職棒」與「視覺化」。對品牌搜尋是加分，對「CPBL 數據分析」「中職 統計」這類非品牌搜尋是**減分**。此為需求方明示裁定（h1 用品牌全名），本卡執行不變更，但**首頁 title（`absolute`）與 meta description 必須補回被丟掉的關鍵字**，作為部分補償。

**其二，全站 title 重構是站台層級變更。** 20 個頁面的後綴全換、10 頁新增 title，Google 需要時間重新索引，期間 SERP 標題與點擊率可能出現短期波動。這是可接受的一次性成本，但**不得在上線後把正常的波動誤判為本卡的缺陷**——上線後至少觀察兩週再評估。

## a11y 規範

- **Logo mark 的無障礙屬性**：作為 header wordmark 的裝飾圖示時須 `aria-hidden="true"`（文字本身已提供品牌名）；若在任何情境下單獨作為連結內容且無伴隨文字，則須 `role="img"` ＋ `aria-label`。兩種情境不得混用同一份 markup 而不做區分。
- **對比**：見紅線 6。深淺兩態皆須實測，不得只驗淺色。
- **OG 圖**：`opengraph-image` 須提供 `alt`。

## 非目標

- **不動 blueprint §5.1 的首頁資訊預算。** 不恢復十套榜單、不改首屏三項結構、不把 DailyHub 內容提前。
- **不開 `/about`、不動導覽 5+1。**
- **不動技術識別符**：repo 名 `cpbl-analytics`、DB schema `cpbl`、docker service 名、網域 `cpbl.ruan-ruan.com`。改這些風險巨大、對產品感零貢獻，且會炸掉 submodule 路徑、nginx 設定與每日爬蟲排程。
- **逐頁動態 OG 圖**（球員頁帶球員名、單場頁帶比分）**不做**，另開卡。理由是成本結構完全不同：`next/og` 的 satori 不吃系統字體，中文需自備 font buffer，完整 Noto Sans TC 有 5–8MB，要 subset 就得引進字體工具鏈——混進本卡會讓驗收標準糊掉。本卡的靜態 OG 圖以純英文迴避此問題，中文資訊由 `og:title`／`og:description` 文字欄位承載。
- **不處理 `/predict` stub。**

## 紅線

1. **hero 不得硬編任何會隨時間腐化的數字。** `games_indexed` 每天在長，今天寫死 9,350 三個月後就是錯的。在一個以「誠實 UX」為賣點、CLAUDE.md 明文「不做假精確」的網站首頁掛一個會過期的數字，是最糟的自打嘴巴。statline 一律取自 API。

2. **statline 任一 key 缺失 → 整條不渲染。** 不顯示 0、不顯示 `—`、不顯示占位。缺數字的可信度條反而傷可信度。

3. **前端不得假設任何欄位必然存在。** 模型指標在 `model_versions` 空表時**合法缺席**（`info.py:79-88` 的 `try/except` 是刻意設計，非 bug），此時 API 仍回 200。因此防線必須落在**前端逐欄位顯式檢查**，而不是靠後端測試保證。本卡的契約測試只能守「口徑一致」與「其餘欄位完整」，**守不住也不宣稱守得住模型指標的存在性**。

4. **首頁請求數不得增加。** 維持現行 2 個（`dailySummary` ＋ `officialStandings`），statline 併入 `dailySummary` 回應。blueprint §8.4 上限為 3，**本卡刻意不動用最後一個配額**，留給未來的季節性橫幅或其他動態內容。兩個請求須維持 `Promise.allSettled` 各自降級，任一失敗不得讓首頁 500。

5. **hero 不得使用隊色**（`UI_UX_SYSTEM` §9：隊色＝身分，首頁不屬任何一隊）；**零硬編 hex**（§2.8 token 紀律），品牌視覺一律走既有 token。若人工審認為現有 token 撐不起「品牌視覺層」，**正解是另開卡擴充 token，不是就地手寫 hex 或漸層**。

6. **`--color-accent` 在 `surface-2` 底色上只能用於大字。** 實測 `#d62839` on `#eef2f7` 對比 **4.42:1，未達 WCAG AA 的 4.5:1**（同色在 `surface` `#ffffff` 為 4.97:1、`paper` `#f5f7fa` 為 4.63:1，皆通過；深色模式 `#ff5a6a` on `#1a2c44` 為 4.65:1 通過）。hero 底色正是 `bg-surface-2`，故 wordmark 的 `Ruan's` 一段與任何 accent 文字**必須 ≥24px 或 ≥18.66px 粗體**（大字門檻 3:1）才合法；小字一律改用 `ink` 或 `cpbl`。此為既有設計系統議題，token 本身是否該調整移交 `UX-TOKEN-ACCENT-CONTRAST1`，本卡只約束用法、不動 token 值。

7. **statline 的性質須據實描述，不得為了通過資訊預算而美化。** 它**會隨資料成長而變動**（`games_indexed` 每天在長，這正是紅線 1 禁止硬編的理由），只是不回答「今天發生什麼」、不可點、不可篩選。它佔用 §3.1 首屏「最多 3 個支持證據」的全部額度——**這是記在帳上的消耗，不是額外贈品**。任何主張它「不佔預算」的說法都是錯的。

## 驗收條件

- [ ] 全站站名字串收斂為單一來源：`Ruan's CPBL Lab`（wordmark／title 後綴）與 `Ruan's 中職數據實驗室`（全名），`grep` 不再命中 `CPBL 分析`、`CPBL Analytics`、`Ruan Dev` 任一舊字串（docs 的歷史 Log 與封存卡除外）。
- [ ] wordmark 三段語意色落地：`Ruan's`＝accent、`CPBL`＝cpbl、`Lab`＝ink，`--color-cpbl` 在 wordmark 內只出現於 `CPBL` 三字。
- [ ] `title.template` 生效；**20 個 page.tsx 中，除 `/predict` stub 與 4 個 dev-only 頁外，其餘每一頁的 title 皆互不相同**（以建置後路由掃描證明，非人工聲明）。
- [ ] 4 個動態路由的 title 帶實體名（以實際路徑實測，非以程式碼推論）。
- [ ] `app/icon.svg`、OG 圖、`manifest.ts`、`openGraph`／`twitter` metadata 皆存在且生效；OG 圖以社群平台除錯工具或 meta 抓取實測，非僅確認檔案存在。
- [ ] 首頁 title 走 `absolute`，實測渲染結果**不含重複的 `Ruan's`**，且保留關鍵字。
- [ ] Outfit 實際套用於 wordmark（以 computed style 驗證，非以 CSS 原始碼推論）。
- [ ] **`--font-mono` 的綁定與行為零變更**：改動前後各抓一次任一表格數字的 computed `font-family` 並比對，須完全相同（非口頭聲明未破壞）。
- [ ] footer 免責改寫完成，「僅供學習與作品集用途」字串消失，非官方與無隸屬關係聲明存在，未出現「非商業用途」字樣；署名列三個連結皆可達。
- [ ] `daily/summary` 含 statline 欄位；`games_indexed`／`seasons_covered` 在 `kind_code=A` 與 `kind_code=D` 下數值相同（實測兩次呼叫比對）。
- [ ] 模型指標缺席時（以清空或 mock `model_versions` 模擬），`daily/summary` 仍回 200 且其餘欄位完整、首頁不崩、statline 依紅線 2 降級。
- [ ] 首頁請求數**仍為 2**（以 network 面板或 server log 實證），未新增第三個請求。
- [ ] hero 零硬編 hex、未使用任何隊色 token；accent 文字若出現在 `surface-2` 底上，字級 ≥24px 或 ≥18.66px 粗體（逐處列出並實測對比）。
- [ ] Logo mark 的 `aria-hidden`／`role="img"` 依情境正確；OG 圖有 `alt`。
- [ ] `/methodology` 「關於本站與作者」段落存在。
- [ ] 兩份 canonical 文件與 README 標題已改名，`UI_UX_SYSTEM.md` 狀態行留痕。
- [ ] `uv run ruff check` ＋ `uv run pytest` ＋ `cd web && npm test` ＋ `npm run build:check` 全綠。

## 驗證

- [ ] **Stage 2 完成後先給需求方本地人工審**（依既有 UX 卡紀律：UX 卡執行後先開本地環境給需求方審核，**通過才交 AI 查核**，不得直接 handoff）。文案與配色可能迭代 2–4 輪，每輪重跑自動化驗證。
- [ ] 人工審通過後交**跨模型家族**獨立查核者（`review_independence: [human, cross_family]`）。
- [ ] 查核者以真實瀏覽器實測深淺兩態的 wordmark、favicon、hero；**不得以 JS 合成點擊或程式化捲動後截圖作為 UI 行為證據**（既有教訓：該手法曾造成連四輪假通過）。
- [ ] 查核者以建置後路由掃描證明 title 互異，數字須可重現（附指令或腳本），不接受人工列舉。
- [ ] 查核者確認本卡未動 `/` 的資訊架構——DailyHub 與 MiniStandings 的內容與順序不變，僅 hero 區塊改寫。
- [ ] **查核通過前不得 merge main**；push 分支並保留 worktree 供查核者進駐。
- [ ] 排版迭代期間**不部署**，需求方滿意後一次上線。

## 邊界

- 前端 ＋ 一處 API 回應擴充（`daily_summary` 加 statline 欄位，唯讀查詢）＋ 文件 ＋ 契約測試。不動 DB schema、不動 ingest、不動 ML、**不新增 API 端點**。
- **移交**：`UX-TOKEN-ACCENT-CONTRAST1`（檢討 `--color-accent` 在 `surface-2` 上未達 AA，屬全站 token 議題，需獨立驗收）——需求方 2026-07-31 裁定另開卡，本卡只約束用法。
- 新 worktree 無 `web/node_modules`，執行與查核前皆須 `cd web && npm install`，否則 `tsc`／`build:check` 全紅是環境假象非缺陷。
- 預估 M（Stage 1 機械性但面廣；Stage 2 依人工審輪數浮動）。

## 上線後續（不在本卡程式碼範圍，需求方手動）

- **主站後台改 cpbl 專案的 `projects.title`。** 該顯示名是生產資料庫欄位（`apps/api/internal/model/models.go:23`），由 admin UI 維護，migrations 000001–000010 沒有 seed，故無法以程式碼變更涵蓋。不改的話會出現「主站叫 CPBL Analytics、點進去叫 Ruan's CPBL Lab」。**`slug` 不要動**，會改主站專案頁 URL 而自造 404。
- **GitHub repo description 目前是空的**（`ruan6047/cpbl-analytics`，PUBLIC），順手補上。

## Log

- 2026-07-31 register by Claude Opus 5@Claude Code（依 ruan6047 指示）；iteration 0。來源：需求方以 `grilling` skill 發起對抗式質詢，15 項決定逐一定案。質詢過程中**推翻了需求方的原始診斷**——「首頁完成度過低」經查證為 blueprint §5.1 蓄意減法的結果、conformance 評為 🟢，需求方確認抱怨對象是品牌與視覺完成度而非資訊量，本卡範圍因此排除資訊架構。另**推翻了規劃者自己的兩項初步建議**：(a) 原建議站名保留 `CPBL Analytics`、個人僅做署名層，需求方裁定改為個人前置式 `Ruan's CPBL Lab`；(b) 原建議 hero h1 寫價值主張句，後改為品牌全名——因全名本身即含關鍵字，SEO 與品牌可共用同一版位。開卡查證另修正**兩項規劃期錯誤**：(1) 缺 title 的頁面數為 11（含 `/predict` stub）而非先前口頭所稱的 14——原判準誤用 `grep "title:"`，命中了 `records`／`standings`／`teams` 的資料結構欄位，改以 `export const metadata`／`generateMetadata` 為判準才正確；其中 4 個是需 `generateMetadata` 的動態路由，工作量與靜態頁不同。(2) 質詢過程中曾稱現行 wordmark「把聯盟品牌藍用在自站識別上、會強化官方誤認」，**該指控不成立**——`layout.tsx:47` 現行已是雙段配色（`CPBL`＝cpbl／`分析`＝accent），語意本就成立，新配色是延伸不是修正。卡面〈品牌定案〉已依實況改寫，避免執行者誤以為存在待修違規。
- 2026-07-31 **獨立 Design Gate 審查**（需求方委託外部 AI，審查對象為未執行的規劃）。九項攻擊點中六項成立，**其中兩項是規劃者完全漏掉的破壞性缺陷**，卡面依裁決改寫：
  - **字體（🔴 最嚴重）**：原卡要求「Outfit 從 `--font-mono` 改為 display」，這會破壞全站 161 處 `font-mono`／144 處 `tabular-nums` 的表格數字。原卡對此僅寫「若有其他消費者須確認不被破壞」，等於把查證推給執行者而自己沒查——實際一查就有 161 處。改為**純增量新增 `--font-display`，`--font-mono` 一行不動**。
  - **Metadata template（🔴）**：`template` 會對首頁的 title 串接後綴，產生 `Ruan's 中職數據實驗室 | Ruan's CPBL Lab` 的重複品牌詞；不設 title 又會落到 `default` 而丟關鍵字。原卡未規範，改為明訂 `absolute`。
  - **契約斷言寫不出來**：原紅線 3 要求 pytest 斷言 `/api/info` 必含 statline key，但 `info.py:79-88` 的 `try/except` 使 key 缺席是**合法行為**，該斷言在規格上不成立。審查者指出「防不住生產靜默壞掉」，實際問題比此更根本。改為前端逐欄位防禦，測試只守可守的部分並明示守不住的部分。
  - **statline 併入 `daily/summary`**：需求方裁定採納，首頁請求數維持 2、保留 §8.4 最後一個配額。附帶寫入口徑紅線（全史涵蓋不得受 `kind_code`／`season` 影響）。
  - **對比度**：審查者稱 accent on `surface-2` 為「4.65:1 勉強通過」，Coordinator 實算為 **4.42:1，未達 AA**——審查者方向對但數字錯且低估。改為紅線 6 約束用法，token 本身移交 `UX-TOKEN-ACCENT-CONTRAST1`（需求方裁定另開卡）。
  - **規劃者的內在矛盾**：原紅線 6 同時宣稱 statline「不隨日期變動」與紅線 1「`games_indexed` 每天在長」，自相打架，且該矛盾正是用來主張 statline 不佔 §3.1 預算的論證基礎。改為據實記帳：statline 佔滿首屏三個支持證據額度，並補記現行兩顆對等 CTA 本就偏離「1 個主要下一步」。
  - **SEO 成本**：原卡只寫好處未寫成本（h1 關鍵字稀釋、全站 title 重構的短期波動），新增〈SEO 風險〉節據實補記。
  - 需求方裁定**動態路由 `generateMetadata` 留在卡內**（審查者建議拆出，需求方認為拆出會變成永遠不做的 Backlog，且它是 SEO 收益最高的部分）。
