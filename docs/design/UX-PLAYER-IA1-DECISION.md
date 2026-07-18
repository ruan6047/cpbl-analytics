# UX-PLAYER-IA1 球員頁 IA 骨架與 prototype 決策文件

> 狀態：**待需求方決策**（變體擇一＋遷移 map 核可）
> 日期：2026-07-18　執行：Fable-5　基線：PRODUCT_UX_BLUEPRINT v0.2 §5.7／§12
> Prototype：`npm run dev` 後開 `/dev/player-ia`（dev only，production 404）
> 本卡**不搬內容**；遷移實作屬後續 UX-PLAYER-SECTIONS1。

---

## 1. 四層 IA 骨架（凍結）

藍圖已核可四層；本文件凍結各層職責、命名與邊界：

| 層 | 導覽標籤 | 回答的問題 | 內容邊界 |
|---|---|---|---|
| L1 | `總覽` | 這位球員**現在**如何？ | 本季核心數據、相對聯盟位置（官方 PR 摘要）、特質、近期趨勢 |
| L2 | `打法`（打者）／`球路`（投手） | 他**靠什麼**？ | 逐球追蹤、擊球品質、球種位移與放球點（投手）、配球傾向 |
| L3 | `分項與對戰` | 在**什麼情境**表現如何？ | 對戰各隊、分項明細（A/C/E）、生涯時段分項、（未來）ML-MATCHUP1 洞察 |
| L4 | `生涯` | 他的**歷史**是什麼？ | 生涯彙總與逐年、SABR 推算逐年、守備、獎項與經歷 |

- **Hero 恆在層外**（所有變體）：身份徽章、效力／執教經歷、能力值卡摘要、role 切換。
- **資料說明頁尾恆在層外**：名詞解釋統一收頁尾（沿用現行）。
- L2 標籤**跟隨 active role**：打者＝「打法」、投手＝「球路」、雙棲隨切換即時改字。

### 1.1 角色顯示規則（凍結，沿用現行判定）

| 規則 | 內容 |
|---|---|
| role tab 出現 | `is_*`（本季一軍）／`was_*`（生涯曾任）／`farm_*`（本季二軍）任一為真即列該 role；僅一 role 時不顯示 tab |
| 預設 role | 有打擊 role 先打擊，否則投球（現行邏輯） |
| role 切換範圍 | 全域（L1–L4 同步換 role），切換**保留當前層** |
| 二軍球員 | `roster_level=二軍` → 本季鏡頭預設 D、L1/L2 顯示「二軍」badge |
| 退役／教練 | `roster_level=null` → **預設層＝生涯**；L1/L2/L3 本季模組顯示引導空態（不隱藏層，導覽仍四層可及） |

### 1.2 正常／空／錯誤狀態契約（凍結）

| 狀態 | 規則 | prototype 實證 |
|---|---|---|
| 正常 | 依層渲染模組 | 打者／投手／雙棲 fixture |
| 結構性空 | role 不適用的模組**不渲染**（打者無「球路位移」） | 郭天信 L2 無位移卡 |
| 資料空 | 模組保留、EmptyState **必附原因**：場地覆蓋不足／退役無本季／樣本不足 | 張偉聖 tracking 14 球警示、彭政閔本季空態引導 |
| 稀疏警示 | 逐球樣本 >0 但過少（<50 球）→ 顯示數字但加「僅供參考」警示 | 張偉聖 |
| 錯誤 | **模組獨立降級**（載入失敗＋重試），不阻塞其他模組與導覽 | `?state=error` 全情境 |

---

## 2. 遷移 map（請需求方核可）

現有球員頁 13 個模組（`web/src/app/players/[id]/`）逐一安置；**本卡零搬移**，下表為 UX-PLAYER-SECTIONS1 的實作依據。

| # | 現有模組 | 檔案 | 目標位置 | 備註 |
|---|---|---|---|---|
| 1 | PlayerHero（身份/tenure/獎項/能力雷達） | hero.tsx | **恆在**（層外） | `dataTab`（本季/生涯）切換保留於能力卡；退役者自動退生涯尺度 |
| 2 | Role Tabs（打擊/投球） | page.tsx＋parts.Tabs | **恆在**（hero 內） | 規則見 §1.1 |
| 3 | SeasonSection（本季成績卡＋官方進階 PR＋一/二軍切換） | season.tsx | **L1 總覽** | PR 只留摘要條；官方進階完整細項歸 L2（併 QualitySection） |
| 4 | TraitsChips（特質） | season.tsx | **L1 總覽** | |
| 5 | TrendVsSection・賽季走勢圖 | trend.tsx | **L1 總覽**（近期趨勢） | 逐場累積/滾動雙模式保留 |
| 6 | TrackingSection（落點/進壘點/紀律/熱區＋球種鏡頭） | tracking.tsx | **L2 打法/球路** | 球種鏡頭 state 內聚於 L2 |
| 7 | QualitySection（官方進階細項群組） | tracking.tsx | **L2 打法/球路** | 與 #3 的 PR 摘要分工：摘要看位置、細項看組成 |
| 8 | MovementSection（球種位移＋放球點） | tracking.tsx | **L2 球路**（投手 only） | 維持「推定球種」標注（藍圖 ML 紅線） |
| 9 | BattedMixSection（彈道散點/配球傾向/球種卡） | tracking.tsx | **L2 打法/球路** | |
| 10 | TrendVsSection・生涯時段分項 | trend.tsx | **L3 分項與對戰** | 時段＝一種分項 |
| 11 | TrendVsSection・對戰各隊表 | trend.tsx＋parts.VsTeamTable | **L3 分項與對戰** | |
| 12 | DetailSection・分項明細（本季/生涯、A/C/E） | detail.tsx＋parts.SplitsTable | **L3 分項與對戰** | 分類手風琴保留 |
| 13 | DetailSection・生涯逐年表 | detail.tsx＋parts.CareerTable | **L4 生涯** | |
| 14 | CareerSummary（彙總＋最佳單季＋里程碑） | season.tsx＋parts.BestSeasonGrid | **L4 生涯** | |
| 15 | SabrSection（RE24/wSB/捕手 RA9 逐年） | sabr.tsx | **L4 生涯** | 逐年性質歸生涯；保留「推算」標注 |
| 16 | FieldingSection（守備 本季＋生涯） | fielding.tsx | **L4 生涯** | 藍圖明定守備歸生涯；本季守備併同表首列 |
| 17 | 資料說明與名詞解釋 | page.tsx 頁尾 | **恆在**（頁尾） | |
| — | （未來）matchup_insights | ML-MATCHUP1 | L3 分項與對戰 | 顯示候選/PA/baseline/credibility/coverage，描述性 |
| — | （未來）pa_sim | — | **不進球員頁** | 藍圖：只在 /matchups 第二 tab |
| — | （未來）Stuff+／成績投影 | — | L2 球路／「下季展望」 | 過 gate 才開卡，不混當季實績 |

支援元件（parts.tsx 的 TenureChips、CompositionPie、PitchTypeToggle、Tabs）隨宿主模組走，無獨立安置問題。
**對帳**：`players/[id]/` 全部 21 個元件 export 均已安置——11 個區塊模組（Season/Traits/CareerSummary/Tracking/Quality/BattedMix/Movement/TrendVs/Sabr/Fielding/Detail）＋PlayerHero＋8 個支援元件＋selectAbility helper，無遺漏。

---

## 3. 三變體比較（prototype 實測）

三變體共用同一四層內容與 Hero，只差導覽機制。fixture：郭天信（打者）／羅戈（投手）／余德龍（雙棲）／張偉聖（二軍＋tracking 缺漏）／彭政閔（退役）。

| 面向 | A・Tabs（單層渲染） | B・錨點長頁（scrollspy） | C・Hybrid（總覽常駐＋分層切換） |
|---|---|---|---|
| 導覽可見性 | ◎ 四 tab 恆在頂部，當前層明確 | ○ sticky nav＋scrollspy，捲動中段時仍知位置 | ◎ 總覽後 sticky 子導覽（3 tab） |
| 回到前文成本 | ✗ 切層即失前文，需切回再捲動 | ◎ 上下捲動即回，脈絡連續 | ○ 總覽永遠在上方，進階內容切換 |
| 行動版（375px） | ◎ 單層內容短、不迷路；4 tab 一行放得下 | △ 全模組串一頁仍長（≈現況問題的緩解版）；掃視快但易迷路 | ◎ 首屏=總覽結論；子層內容適中 |
| deep-link 穩定性 | ◎ `?layer=` query 不受渲染時序影響，reload 落點精準 | △ `#hash` 在 client 渲染完成前解析失敗，**需 mount 後補捲**（已實作）；正式版圖表 lazy-load 會使落點漂移 | ◎ `?sec=` 同 A；總覽區塊無法 deep-link 跳過 |
| 鍵盤 | ◎ WAI-ARIA tabs（←/→ 切層，已實證） | ◎ 原生連結 Tab/Enter | ◎ 同 A |
| 效能 | ◎ 只渲染 1/4 內容（現頁 22 個資料請求可延後 3/4） | ✗ 仍一次全渲染（=現況） | ○ 總覽＋1 子層 |
| 「預設只展開角色相關前三層結論」（藍圖減法） | ○ 需使用者主動切 | ✗ 全部攤開 | ◎ 天然符合：總覽=結論、進階=主動展開 |
| 實作成本 | 低 | 中（scrollspy＋補捲＋lazy 高度漂移處理） | 低-中 |

### Prototype 走查中的實證發現

1. **錨點 hash 首載不可靠**：`#approach` 直開時瀏覽器在內容渲染前就處理 hash，落點停在頁首；需 mount 後補 `scrollIntoView`（prototype 已補）。正式版模組高度受 lazy-load 圖表影響，落點會二次漂移——這是 B 案的固有稅。
2. **IntersectionObserver scrollspy 在瞬跳時漏更新**：改為確定性 scroll listener 才穩定。B 案的隱形維護成本例證。
3. **退役者在 tabs/hybrid 下體驗最好**：預設直落「生涯」層；B 案則仍從空蕩的本季區開始捲。
4. **雙棲 role 切換**在三變體都能保留當前層（`?role=` 與層參數獨立）。

## 4. 建議

**建議採 C・Hybrid**：

- 最符合藍圖減法原則（§3）「預設只展開與角色相關的結論」——總覽常駐回答第一問，進階三層主動展開。
- deep-link 用 query param，繼承 A 案的穩定性，避開 B 案的 hash 補捲稅。
- 行動版首屏即結論；「回到前文」的主要場景（看進階數據時想對照基本盤）由總覽常駐直接消解。
- 次選 A（若希望四層完全對等、實作最簡）；不建議 B（deep-link 脆弱＋等於保留現況長頁問題）。

## 5. 請需求方決策

- [ ] **變體**：A tabs／B 錨點／C hybrid（建議 C）
- [ ] **遷移 map**（§2）核可，或指出要調整的模組安置
- [ ] 凍結項（§1 骨架、角色規則、狀態契約）確認

核可後開 UX-PLAYER-SECTIONS1 執行遷移；該卡不得再改層結構。

## 6. 驗證紀錄

- fixture：`scripts/capture_player_ia_fixtures.py` 自本機 API 擷取真實回應（逐球截 400 筆）；五情境特徵已抽驗（二軍僅 14 逐球點、退役本季全空、雙棲雙 role）。
- 走查：三變體 × 五情境；375px 無水平溢出；tabs/hybrid 鍵盤 ←/→ 實測；deep-link `?layer=`／`?sec=`／`#hash` reload 實測。
- `uv run ruff check`＋`uv run pytest`（283 passed）＋`npm run build:check` 全數通過；prototype 路由 production `notFound()`。
