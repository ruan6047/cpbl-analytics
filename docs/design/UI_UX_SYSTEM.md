# CPBL Analytics — UI/UX 設計系統（canonical）

> **狀態**：v1 draft（UX-DESIGN-SYSTEM1，執行者 Opus 4.8）。方向已經需求方 ruan6047 於 2026-07-24 sign-off；**規格內容待跨家族查核**（🔍）。
> **定位**：全站**視覺／元件層的單一事實來源 [single source of truth]**。以球員個人頁旗艦（`web/src/app/players/[id]/` + `web/src/components/*`）為 100% 基準，把已落地的設計語言**逆向抽出、明確化**。
> **本檔性質**：**描述現況＋明確化**，不推翻球員頁已定案語言。本卡不改 `globals.css`／元件碼；標「建議」者為未來遷移目標，非本卡執行。
> **配套文件**：逐頁差距見 [`UI_UX_CONFORMANCE.md`](UI_UX_CONFORMANCE.md)；token hygiene 修復見 [`../tasks/UX-TOKEN-HYGIENE1.md`](../tasks/UX-TOKEN-HYGIENE1.md)。

---

## 0. 定位與邊界（vs 產品藍圖）

本規格與 [`../PRODUCT_UX_BLUEPRINT.md`](../PRODUCT_UX_BLUEPRINT.md) v0.2 **職責互補、不重疊**。衝突時**產品層優先**，本規格只描述「如何視覺化地達成 blueprint 的要求」。

| 擁有者 | 擁有的決策 |
|---|---|
| **PRODUCT_UX_BLUEPRINT（產品/IA）** | 頁面回答什麼問題、資訊預算數字（§3.1：5–8 欄／Top 3／導覽 5+1）、指標語意與 ML 採用矩陣（§6）、freshness/availability 文案分類（§8.1/§8.2）、行動版鐵則（§8.3）、編輯資料邊界（§8.5） |
| **本規格（視覺/元件）** | 設計 token、元件長相與狀態、tab/table/badge 語彙、深色約定、斷點與 mobileHide **機制**、圖表視覺規範 |

> **雙重事實防呆**：blueprint 的數字**一律以「引用節次」表示，不在本規格複述**（避免 drift）。例如「精簡欄的欄數上限」屬 blueprint §3.1，本規格只定「精簡/完整切換的機制與長相」。

---

## 1. 設計原則（延續 `globals.css` UX-2 八原則）

`globals.css` 頂部已存在 8 條全站原則（驗收時逐條對照）；本規格予以明確化，不新增、不推翻：

1. **快速理解優先**：預設只給結論層，細節漸進揭露；數字不裸列（配 PR 條／色階／趨勢／均值對照）；每區塊回答一個問題（5 秒測試）。
2. **三層底色，不新增灰階**：`paper → surface → surface-2`，分界一律 `border-line`。禁第四層灰或自定色票。
3. **顏色必有語意，禁裝飾用色**：`accent`＝行動/焦點、隊色＝身分、`up/down`＝數據好壞、`amber`＝狀態警示。同一語意全站同色。
4. **誠實 UX**：預測附基準對照；資料缺口顯式標注；不做假精確（該 `—` 就 `—`，不補 0）。
5. **一致元件語彙**：同概念全站同長相；新頁面先找既有元件，**禁平行發明**。
6. **行動端一等公民**：375px 無橫向溢出＝鐵則（blueprint §8.3）；寬表 sticky 首欄或卡片化；觸控 ≥44px。
7. **動效節制**：只在入場/狀態變化動；受 `prefers-reduced-motion` 約束。
8. **感知效能**：skeleton/empty/error 三態統一；圖表 lazy；切換不塌陷（CLS）。

---

## 2. 設計 Token

> 唯一事實來源＝`web/src/app/globals.css` 的 `@theme`。tsx **禁硬編 hex**，一律走 `bg-/text-/border-/fill-/stroke-` 工具類或 `var(--…)`。授權例外白名單見 §2.8。

### 2.1 色彩

**結構三層底 + 分界**

| Token | 淺色 | 深色 | 用途 |
|---|---|---|---|
| `--color-paper` | `#f5f7fa` | `#0a1626` | 頁底 |
| `--color-surface` | `#ffffff` | `#101f33` | 卡面 |
| `--color-surface-2` | `#eef2f7` | `#1a2c44` | 卡內強調 / 圖表格線 / 空態底 |
| `--color-line` | `#e2e8f0` | `#24374f` | 卡片與區塊分界 |
| `--color-line-strong` | `#cbd5e1` | `#3a5170` | 圖表軸線 / 較強分隔 |

**文字三級**

| Token | 淺色 | 深色 | 用途 |
|---|---|---|---|
| `--color-ink` | `#0a2540` | `#e8eef6` | 主要文字 / 圖表主資料 |
| `--color-muted` | `#5b6b7a` | `#a1b2c6` | 次要文字 / 軸刻度 |
| `--color-faint` | `#94a3b8` | `#7c90a8` | 三級文字 / 參考線 / 未知隊 |

**語意色**

| Token | 淺色 | 深色 | 語意（唯一用途） | 禁用 |
|---|---|---|---|---|
| `--color-accent` | `#d62839` | `#ff5a6a` | 行動 / 焦點 | 不當裝飾、不當數據好壞的「好」 |
| `--color-up` | `#1d6fb8` | `#4a9fe0` | **數據佳（藍）** | 不當品牌色 |
| `--color-down` | `#d62839` | `#ff5a6a` | **數據差（紅）** | — |
| `--color-amber` | `#b45400` | `#fb923c` | 狀態警示／次級身分（延賽、保留、二軍、獎項） | 不當一般強調 |
| `--color-cpbl` | `#1b4da1` | `#5a8fe0` | CPBL 品牌藍 | 不當數據好壞 |

> ⚠️ **語意反直覺，文件顯式標注**：本專案 `up=藍 / down=紅`，與金融慣例「漲綠跌紅」相反——這是棒球資料語境的刻意選擇（藍=好），後續卡**禁**改回綠/紅。
> ⚠️ **`accent` 與 `down` 共色**（`#d62839`）：兩者語意不同（行動 vs 數據差）但目前共用同一 hex；視為**待觀察風險**，若未來需區分再拆 token（見 [`UX-TOKEN-HYGIENE1.md`](../tasks/UX-TOKEN-HYGIENE1.md)）。

**圖表分類序列 / 好球帶 / 身分**（詳見 §6）

- `--chart-1..8`：分類序列（含球種色槽，固定序不 cycle）。
- `--zone-heart/shadow/chase/waste`：好球帶分區。
- `--status-import/loree/nagata`：洋將身分（本土/羅力條款/永田條款）。

**WCAG 對比稽核（標準公式計算；淺色前景 on `surface #fff`）**

| 前景 | 對比 | AA 一般（4.5） | 判定 |
|---|---|---|---|
| `ink #0a2540` | ~14.4:1 | ✅ | 主文字任意用 |
| `muted #5b6b7a` | ~5.6:1 | ✅ | 次文字可承載必要資訊 |
| `faint #94a3b8` | **~2.6:1** | ❌ | **僅限非必要/裝飾/大字**；不可承載必要文字（如唯一的名次數字若用 faint 需≥18.66px 或改 muted） |
| `accent #d62839` | ~4.7:1 | ✅（臨界） | 連結/焦點文字可用 |
| `up #1d6fb8` | ~5.0:1 | ✅ | 數據佳標注 |
| `amber #b45400` | ~5.3:1 | ✅ | 警示文字 |
| `paper #f5f7fa` on `ink` | ~13:1 | ✅ | active 標籤（見 §2.2） |

> `faint` 的低對比是**刻意的三級弱化**，但規格明訂：**唯一承載必要語意的文字不得用 `faint`**（例：`StatTile` 的名次在 `faint` 時只作「中段班」補充，非唯一資訊）。詳細抽驗清單見 `UI_UX_CONFORMANCE.md`「可及性」段。

### 2.2 深色模式約定（canonical，呼應記憶 `dark-mode-conventions`）

1. **預設淺色，不跟系統**：`:root { color-scheme: light }`；深色由 layout 無閃爍 inline script 於首繪前寫 `<html data-theme>`，`ThemeToggle` 掛載後同步。使用者手動切換才進深色。
2. **翻色機制**：`[data-theme="dark"]` 覆寫**同名 token** → 所有 `var()`/工具類自動換色，**元件無需寫深色分支**。新增顏色一律走 token 才能自動翻。
3. **active 標籤＝`bg-ink text-paper`**（pill/group 型）或 `border-ink`（underline 型）。**嚴禁 `text-white`**：淺色下 `paper≈白`，深色下 `ink=淺、paper=深`，用 `text-white` 會在深色出現「白底白字」。→ badges/toggles 一律 `text-paper`，非 `text-white`。
4. **圖表色一律走 `useChartTheme()`**（recharts）或 `fill-/stroke-` 工具類（raw SVG）——見 §6。
5. **刻意不翻轉的三類例外**（有既存技術理由，規格明列以免後續卡誤「修正」）：
   - `prColor` 發散色階（藍↔白↔紅，Baseball Savant 式）：端點語意跨主題恆等（藍=低、紅=高），翻轉會反轉語意。
   - `PR_CELL_TEXT`（色格上文字）：格底恆為淺色系，故固定深墨 `#0a2540` + 白 halo，不隨主題翻。
   - `chart-theme.ts` 固定語意常數盤（`BATTED_OUTCOME`/`ZONE_OUTCOME`/`PITCH_CALL`/`PA_KIND`/`GRADE_COLORS`/`MEDAL_COLORS`/`STATUS_COLORS`/`PIE_COLORS`）：飽和語意色深淺皆可讀。

### 2.3 字級（type）

**現況（描述）**：無 `@theme` 字級尺標，靠 Tailwind 預設 + 大量 arbitrary `text-[Npx]`（全站計 ~222 處：`text-[11px]`×127、`text-[10px]`×78、`text-[9px]`×11、`text-[13px]`×5、`text-[8px]`×1）。等寬數字一律 `font-mono tabular-nums`。

**建議收斂角色 scale（未來遷移目標，本卡不改碼）**：把現用離散值收斂成語意角色，供後續卡消滅 arbitrary values。

| 角色 | 建議值 | 現況對應 | 用途 |
|---|---|---|---|
| `display` | `text-2xl`+ / hero 專用 | hero 名字 | 球員/球隊名 |
| `h2 / section` | `text-lg`–`text-xl` | 區塊主標 | 卡片標題 |
| `stat-value` | `text-base`–`text-lg` `font-mono tabular-nums` | `StatTile`/`StatGrid` 數值 | 主數據 |
| `body` | `text-sm` | 內文 | 一般說明 |
| `caption` | `text-xs`（0.75rem） | `text-[11px]`/`text-[13px]` | 表格/次要標注 |
| `micro` | `text-[10px]`（0.625rem） | `text-[10px]` | 名次/pill/徽章 |

> **收斂原則**：`text-[11px]`／`text-[13px]` 建議合併入 `caption`（`text-xs`）；`text-[9px]`/`text-[8px]` **低於可讀下限，建議上調至 `micro`(10px) 或改用 icon**（可及性）。
> **強制界線**：新碼一律用角色（Tailwind 內建級距或未來 token）；既有 arbitrary values 由 `UX-DESIGN-CONFORM1` **漸進**收斂，非立即全違規。

### 2.4 間距（spacing）

**現況**：沿用 Tailwind 4pt 基準（`gap-1.5`/`gap-2`/`gap-3`/`p-4`/`px-3 py-2`…），無自定 `--spacing-*`。卡內距預設 `Card` 的 `p-4`（可覆寫）。

**建議角色（未來遷移目標）**：延續 8pt 概念（4px 為半步微調），命名密度角色——`tight`(gap-1.5)／`default`(gap-2~3)／`section`(mb-5~6)。本卡不新增 css 變數。

### 2.5 圓角（radius）

**現況（描述，直接可強制）**：

| 角色 | 值 | 出處 | 用途 |
|---|---|---|---|
| card | `0.75rem`（`rounded-xl`） | `.card` | 卡片、區塊容器、表殼 |
| control | `0.5rem`（`rounded-lg`） | select/button/`StatGrid` 格 | 控制項、內距格 |
| pill | `0.25rem`（`rounded`）～`rounded-full` | `Pill`/`StatusBadge`/tab pill | 標籤、切換膠囊 |
| badge | `size*0.22`（`LetterBadge`）/`rounded-md`（`TeamLogo`） | 徽章 | 隊色方塊 |

### 2.6 陰影 / border / elevation

- **分層優先靠 `border-line` + 底色三層**，陰影僅輔助。
- `.card` 陰影：淺色 `0 1px 2px rgb(10 37 64/.04), 0 1px 3px rgb(10 37 64/.06)`（navy 微陰影）；深色改深黑 `0 1px 2px rgb(0 0 0/.3), 0 1px 3px rgb(0 0 0/.4)`（淺陰影在深底不可見）。
- Hover 隊色光暈：`.card-hover-team`（`--hover-color` 邊框 + 20% color-mix 光暈）。
- **建議**：命名為單一 elevation 角色 `elevation-card`（深淺兩態），未來若需更高層級（modal/popover）再擴。

### 2.7 動效（motion）

| Token | 值 | 用途 |
|---|---|---|
| `--dur-fast` | `.15s` | 淡出/hover |
| `--dur-base` | `.3s` | 一般轉場/淡入 |
| `--dur-slow` | `.8s` | 勝率條伸展等強調 |
| `--ease-standard` | `cubic-bezier(.4,0,.2,1)` | 全站標準緩動 |

- 入場 ease-out、離場 ease-in（frontend-design 原則）。
- **一律受 `@media (prefers-reduced-motion: reduce)` 約束**（globals.css 已全域近乎關閉動畫）。
- 既有動畫：`animate-fade-in`/`animate-fade-out`/`animate-bar-grow`。

### 2.8 Hex owner 白名單（token 紀律）

實測全 `web/src` 硬編 hex **僅集中於 4 檔**（紀律良好，可強制）：

| 授權檔 | 內容 | 為何允許 hex |
|---|---|---|
| `lib/teams.ts` | 隊色身分（~40） | 身分色唯一來源，非 token（隊色隨歷史隊變動） |
| `lib/chart-theme.ts` | 圖表常數盤（~23） | 飽和語意色深淺皆可讀，刻意不隨主題翻（§2.2 例外 3） |
| `components/ui.tsx` | `prColor` 端點 + `PR_CELL_TEXT`（3） | 發散色階/色格文字，刻意不翻（§2.2 例外 1/2） |
| `app/layout.tsx` | 無閃爍 theme script（2） | 首繪前 inline，讀不到 CSS var |

> **強制規格**：以上 4 檔外，tsx/元件**禁**出現 `#RRGGBB`。新增顏色一律走 `@theme` token。（現況違規：`app/standings/page.tsx`、`components/matchup-card.tsx` 用 Tailwind 數字色階 `amber-100/500/700`、`amber-600`——見 `UI_UX_CONFORMANCE.md`。）

---

## 3. 元件模式與狀態

> 全站元件唯一來源 `components/ui.tsx`（+ 領域元件）。新頁面**先找既有元件，禁平行發明**（原則 5）。

### 3.1 卡片家族

| 元件 | 契約 | 狀態/變體 |
|---|---|---|
| `Card` | `.card` 唯一事實來源（surface 底 + border-line + rounded-xl + 微陰影）。`padding` 預設 `p-4` 可覆寫；`teamColor`/`hoverable` 啟用隊色 hover 光暈。**全站禁再手寫 `rounded-xl border border-line`** | default / hover（隊色）。例外：`DataTable`/`Leaderboard` 內建表殼、`<details>` 折疊、`game-board` ESPN 內部面板 |
| `StatTile` | 橫向一列（label 左、value+名次右），省縱向空間。名次 tone：前段班 `up`、後段班 `down`、其餘 `faint` | accent / rank |
| `StatGrid` | dl 網格（label 上 value 下、等寬數字），`cols` 2–5 | accent/muted tone |
| `Eyebrow` | 區塊小標（`text-[11px]` uppercase tracking-wider `faint`），每區塊點題（原則 1/5） | — |

### 3.2 徽章與標籤

| 元件 | 用途 | 備註 |
|---|---|---|
| `LetterBadge`/`TeamLogo`/`NameTag`/`TeamBadge`/`EraBadge` | 隊色方塊 + 對比字（避官方 logo 版權）。隊名解析走 `lib/teams.ts`（唯一身分來源） | `decorative` 旁已有隊名時設 `aria-hidden` 免螢幕閱讀器重複念 |
| `Pill` | 小標籤（tone `up`＝綠、`muted`＝灰）。`ActivePill`/`GonePill` 為預設實例 | 併入名字欄的守位/角色 chip 亦走此 |
| `StatusBadge` | **全站唯一場次狀態語彙**：`done`（完賽·中性）/`warn`（延賽·保留·amber）/`live`（進行中·accent）/`scheduled`（未開打·accent 淡）。`variant` solid（列表）/bare（月曆窄格） | 走語意 token，**禁** `amber-數字` |
| `Notice` | amber 警示橫幅（延賽/保留說明） | 走語意 token |

### 3.3 感知效能三態（原則 8，全站統一）

| 元件 | 用途 |
|---|---|
| `Skeleton` / `TableSkeleton` | 載入佔位（`animate-pulse`），切換不塌陷（CLS）。`TableSkeleton(rows,cols)` |
| `EmptyState` | 無資料（`py-8 text-center text-faint`）。**禁 ad-hoc「無資料」字串** |
| `ErrorState` | 載入失敗（`text-accent`） |

> **強制規格**：`載入中…`/`讀取中` 等 ad-hoc 字串一律改用三態元件。（現況違規：`app/umpires/page.tsx`、`app/games/[sno]/box-tabs.tsx` 逐球分頁——見 conformance。）
> **⚠️ freshness/availability 例外**（blueprint §8.1）：`unknown`/`pending`/`no_equipment`/`source_missing`/`source_error`／真正零值**不得共用同一空態文案**；此語意分類屬 blueprint，本規格只保證「視覺上用三態元件承載、不同語意給不同文字」。

### 3.4 資料密度與說明

| 元件 | 用途 |
|---|---|
| `PercentileBar` / `prColor` / `PR_GRADIENT` / `divBg` | Savant 式百分位發散色階（0 藍→50 灰→100 紅）。`divBg` 給 td 淡底 |
| `StatAbbr` / `METRIC_DESCRIPTIONS` | 進階指標名詞解釋 tooltip（首次出現白話解釋，blueprint §8.2） |
| `Tooltip` | 共用提示（原生 title 有延遲且觸控無效） |

---

## 4. 導覽・切換・選擇語彙（決策樹）

> 分兩族：**切換族**（在少量已知選項間切換＝Tab/Segment，§4.1）與**選擇族**（從較多離散值/大集合中挑選＝Select/Menu/Combobox，§4.2）。球員頁的 tab 已是精修基準；本節把**其他頁會用到的選擇型控制**一併 codify，並把尚未建置的**混合下拉**列為 proposed（§4.3）。
> 統一鐵則：**active＝`bg-ink text-paper`（pill/group）或 `border-ink font-semibold`（underline），禁 `text-white`；觸控 `min-h-11`(44px)；overlay 一律 Esc + 點外部關閉、關閉後焦點歸還觸發鈕**。

### 4.1 切換族：Tab / Segment 四語彙（現況，依 a11y 語意分工）

| 語彙 | 元件 | 何時用 | active 態 | a11y |
|---|---|---|---|---|
| **階層雙層** | `HierarchicalTabs` + `ContextSwitcher` | 頁內雙層資料範圍（scope + view，如球員頁本季/生涯 × 總覽/逐球/…） | group `bg-ink text-paper`；item `border-b-2 border-ink` | group（`aria-pressed`）+ tablist（`role=tab`）分離語意 |
| **情境切換** | `ContextSwitcher` | 情境軸（身分打/投、層級一/二軍），segmented 膠囊 | `bg-surface text-ink shadow-sm`（凸起感） | `role=group` + `aria-pressed` |
| **單層分頁** | `Tabs` | 單層 server-rendered 內容分頁（資料已在 props，切換不打 API） | pill `bg-ink text-paper` | `role=tablist/tab` |
| **路由切換 nav** | `RankRoleTabs` / `level-year-nav` | 跨路由導覽（`/batters ↔ /pitchers`、年度/層級），保留 query 脈絡 | pill `bg-ink text-paper` | `aria-current="page"`（連結非 tab） |

> 選項多寡準則：**切換族適用 ~2–5 個選項**且需常駐可見；超過或值域大 → 改用選擇族（§4.2）。
> **⚠️ open item（待查核裁定）**：`ContextSwitcher` active 用 `bg-surface text-ink shadow-sm`（而非通則 `bg-ink text-paper`）——segmented 凸起慣例，**現況如此**，誠實描述而非強制統一。

### 4.2 選擇族：Select / Menu / Combobox（現況，可跨頁重用）

| 語彙 | 元件 | 何時用 | 樣式/行為 | a11y |
|---|---|---|---|---|
| **原生 Select** | `YearSelect`、`Leaderboard` 篩選 | 從**單一軸的多個離散值**選一（年份、隊別、分類篩選），選項 ~5–20 | `bg-surface-2` + `focus:border-ink`；**canonical 圓角＝`rounded-lg`（control）** | 原生 `<select>` + `aria-label` |
| **溢出「更多」Menu** | `nav-links` `MORE_NAV` | 主入口收納次要項（blueprint §4.1 的 **5+1**），或工具列 overflow | 觸發鈕 chevron `rotate-180`；面板 `rounded-xl border-line bg-surface p-1 shadow-lg` | `aria-haspopup="menu"` + `aria-expanded` + `aria-controls`；`role=menu`/`menuitem`；Esc/點外部關、焦點歸還 |
| **Modal 導覽** | `nav-links` 行動端 | 窄螢幕主導覽（375px 無頂欄空間） | `portal` 到 body、`backdrop-blur`、`animate-fade-in`、body scroll-lock | `role=dialog` + `aria-modal` + **focus trap** + Esc 關 |
| **Combobox（搜尋選擇）** | `SearchCombobox`、`PlayerSearch` | 從**大集合**（球員/對手）搜尋挑選 | debounce 250ms + **競態守衛**（採最後一次）；選定→chip 可清除；inline loading/error/empty | `role=combobox` + `aria-expanded/controls/activedescendant/autocomplete`；listbox/option；↑↓ Enter Esc |

> **⚠️ 現況不一致（→ hygiene）**：`YearSelect` 用 `rounded-full`、`Leaderboard` 篩選用 `rounded-lg`。**canonical 定為 `rounded-lg`（control 圓角，§2.5）**；`rounded-full` pill-select 僅工具列 chip 語境可留。收斂列入 [`UI_UX_CONFORMANCE.md`](UI_UX_CONFORMANCE.md) H8。
> **共通 overlay 契約**（Menu/Modal/Combobox 共用，新增時照抄）：Esc 關 + 點外部關 + 關後焦點歸還觸發鈕；面板 `shadow-lg`；`z` 高於 sticky nav；`backdrop-blur` 面板走 `bg-*/95`。

### 4.3 混合下拉（Hybrid：tabs + overflow dropdown）— **proposed，尚未建置**

> **問題**：頁內內容 tab 超過 ~5 項、或窄螢幕放不下時，現況 `HierarchicalTabs` 靠**水平捲動**（`overflow-x-auto`）容納——可用但可發現性差。你提到的「混合下拉選單」即此缺口：**前段常駐 tab + 尾段收進「更多▾」下拉**，或**窄螢幕整組 tab 塌陷為 `<select>`**。
> **狀態**：**現況無此可重用元件**（頂層 nav 的「主入口 + 更多」是同構但綁在 `nav-links`，未抽為 in-content 通用件）。故列 **proposed**，不謊稱現況。

**組合現有積木（不發明新互動）**：以 §4.1 `TabItems`（常駐段）＋ §4.2「更多 Menu」（溢出段）組合；或窄螢幕以 §4.2 原生 Select 承載整組。建議 API 草案（供實作卡）：

| prop | 型別 | 說明 |
|---|---|---|
| `items` | `{value,label}[]` | 全部分頁 |
| `value`/`onChange` | — | 受控選取 |
| `maxVisible` | `number` | 常駐 tab 數上限，其餘進「更多」 |
| `collapseTo` | `"menu" \| "select"` | 溢出/窄螢幕收納形式 |

**open questions（待需求方/實作卡定）**：① `maxVisible` 固定值或量測容器（container query）？② 溢出段的 active 項是否上移常駐？③ 窄螢幕塌陷門檻＝ §7 的 640px 或依 tab 數動態？④ 是否直接擴 `HierarchicalTabs` 而非新元件（避免第五種語彙）。
> **紀律**：本段為 `design-system` 的 **extend**（新模式提案），**須經需求方 sign-off 才實作**；未 sign-off 前，其他頁沿用 §4.1 水平捲動或 §4.2 Select。

### 4.4 決策樹（新頁面選控制項）

1. **在 2–5 個已知選項間切換內容**？→ 切換族：雙層 `HierarchicalTabs`／單層 `Tabs`／情境軸 `ContextSwitcher`／跨路由 `aria-current` 連結 nav。
2. **從單一軸的多個離散值（~5–20）選一**？→ 原生 **Select**（`rounded-lg`）。
3. **從大集合搜尋挑選**？→ **Combobox**（`SearchCombobox` 模式）。
4. **主入口/工具列需收納次要項**？→ 「更多」**Menu**（blueprint §4.1 5+1）。
5. **內容 tab 過多/窄螢幕放不下**？→ 暫用 §4.1 水平捲動或 §4.2 Select；**混合下拉（§4.3）待 sign-off 後**。
6. **禁**再手刻第六種語彙——先查 §10.4 registry。

---

## 5. 表格與 Leaderboard 減法契約

### 5.1 兩種表格

| 元件 | 性質 | 用途 |
|---|---|---|
| `DataTable`（`table.tsx`） | 靜態 presentational（無 hook，可用於 server component） | 一般資料表；收斂全站 `<table>`：寬表橫向捲動保護 + 卡殼 + sticky 首欄 + 一致表頭 |
| `Leaderboard`（`leaderboard.tsx`） | 互動 client island（排序/篩選/欄切換） | 排行榜 |

共通：`dense` 密度、`sticky` 首欄（`.sticky-col`，行動端寬表鎖首欄）、`maxHeight` 垂直捲動 + sticky 表頭、`bare`（已在 Card 內免雙層邊框）。

### 5.2 Leaderboard `Col` 減法契約（呼應記憶 `rankings-column-reduction`）

`Col` 攜帶的旗標即**減法機制**（本規格擁有機制，**欄位是否 primary 由各排行卡依 blueprint §3.1/§5.6 資訊預算決定**，本規格不指定欄名）：

| 旗標 | 語意 | 判準（機制層） |
|---|---|---|
| `primary` | 精簡檢視顯示的欄 | 任一欄標 `primary` 才啟用「精簡/完整」切換；回答該排行核心問題所需最小欄集（**欄數上限見 blueprint §3.1**）。全無 `primary` 時顯示全部（向後相容降級） |
| `mobileHide` | `<640px` 隱藏 | 手機保留「排名 + 球員（隊徽併名）+ 主排序指標 + 1–2 支持」（**清單依 blueprint §5.6**）。實作：窄螢幕**移出 DOM**（非 `display:none`，避免 table 幽靈寬度造成假性水平捲動） |
| `teamKey` | 隊欄併入名字欄（名前加隊徽 icon） | 減欄手段之一 |
| `subChipKey` | 守位/角色併入名字欄（名下疊 `Pill`） | 減欄手段之一 |
| `chip` | 類別值（守位/角色）獨立欄渲染 `Pill` | 併入名字時改用 `subChipKey` |
| `rate` + `qualKey`/`qualMin` | 率值欄（AVG/OPS/ERA）排序時套規定門檻；未達者置底、灰階、不佔名次 | 避免小樣本灌爆榜首（1 打席 OPS 2.000） |
| `bar` + `lowerBetter` | Savant 式 inline 發散色條（依當前檢視 min–max） | 「越好越長越紅」；`lowerBetter` 反向 |
| `tone`/`link`/`tip` | 色調/連結/表頭說明 | — |

> **強制規格**：排行頁一律用 `Leaderboard`，**禁**手刻排序表。「主指標」隨當前 `sortKey` 動態變動（mobileHide 保留的是「當前主排序指標」，非靜態欄集）。

---

## 6. 圖表規範（對齊 `dataviz` skill + `chart-theme.ts`）

### 6.1 取色來源（唯一機制）

- **recharts**（顏色吃具體字串，不解析 CSS var）：一律 `useChartTheme()` 取色；`data-theme` 變動即重讀重繪。座標軸走 `chartAxis(ct)`、tooltip 走 `chartTooltip(ct)`。
- **raw SVG**（自繪）：`fill-/stroke-` 工具類或 `style={{fill:'var(--…)'}}`，交給 CSS 自動翻色。
- **tsx 內禁再硬編**這些 hex，一律 import `chart-theme.ts`。

### 6.2 色彩規則（dataviz 非協商項）

1. **分類色固定序、不 cycle**：`--chart-1..8` / `pitchColor()` 依固定球種色槽序指派；**第 9 系列不生成新色**，折入「其他」或改 small multiples。
2. **顏色跟實體不跟排名**：篩選改變系列數**不得重繪倖存者**（`Leaderboard` bar 依值域，非此規則約束；系列圖須遵守）。
3. **單軸**：**禁雙 y 軸**；不同尺度 → 兩圖/small multiples/共同基準指數化。
4. **序列 = 單一色相由淺到深；發散 = 兩色相 + 中性灰中點**（`prColor` 藍→灰→紅符合）。禁彩虹、禁中點放色相。
5. **文字穿文字 token**（ink/muted/faint），**不穿系列色**；系列色只在色塊/線上。
6. **狀態色保留**（`StatusBadge` 的 done/warn/live/scheduled）不重用為「系列 4」，且**配 icon+文字非色彩單獨**。

### 6.3 標記與可及性

- 細標記、2px 線、≥8px 點；資料端 4px 圓角錨定基線；重疊標記 2px surface 環。
- **≥2 系列必有 legend**（單一系列不需，標題已命名）；≤4 系列可直接標記（非每點都標數字）。
- 每張圖須有**文字替代列表**（blueprint §8.3）；大型 tracking 圖 lazy load。
- **建議（非本卡執行）**：`--chart-1..8` 分類序列**應跑 `dataviz` 的 `validate_palette.js`** 驗證色盲相鄰對分離（ΔE≥8）與淺色/深色對比；深色缺 `chart-7/8` 定義須補（見 `UX-TOKEN-HYGIENE1.md`）。

---

## 7. 響應式

| 斷點 | 語意 | 規則 |
|---|---|---|
| base（<640） | 手機 | **375px 無橫向溢出＝鐵則**（blueprint §8.3）。寬表 sticky 首欄或卡片化；`Leaderboard` 套 `mobileHide`（移出 DOM）；觸控 ≥44px（`min-h-11`） |
| `sm:`(640) | 大手機/小平板 | `Leaderboard` 恢復完整欄；`matchMedia('(max-width:639px)')` 為 mobileHide 界線 |
| `md:`(768) | 平板 | `HierarchicalTabs` 由直排轉橫排；controls 移右側加分隔線 |
| `lg:`(1024)+ | 桌機 | 完整密度 |

> **現況用 viewport 斷點（`matchMedia`）**；規格描述現況。**建議（未來）**：可重用元件遷 container query（Tailwind v4 `@container`）以脈絡無關，但非本卡範圍。

---

## 8. 可及性（WCAG，摘要）

- 對比：見 §2.1 表；**`faint` 不承載必要文字**；關鍵前景/背景組合的完整抽驗清單見 `UI_UX_CONFORMANCE.md`。
- 焦點：全域 `:focus-visible`（2px accent outline，滑鼠點擊不顯示、Tab 才顯示）。
- 跳過導覽：`.skip-link`。
- 觸控 ≥44px；減少動態 `prefers-reduced-motion`。
- 圖表非色彩單獨（§6.2.6）；圖表配文字替代（§6.3）。
- 徽章 `decorative` 免螢幕閱讀器重複念（§3.2）。
- **sub-legible 字級**（`text-[8px]/[9px]`）為可及性缺口，建議上調（§2.3）。

---

## 9. 球隊身分 UI 規範

> 唯一事實來源＝`web/src/lib/teams.ts`（§2.8 授權 hex owner）。**隊色＝身分語意**（原則 3），非裝飾、非 `--chart-*`、非結構 token。
> **邊界**：本節只擁「球隊**身分視覺語言**」；「球隊頁**顯示什麼資料/版面**」屬 blueprint §5.8，不在此。

### 9.1 隊色 = 身分（不進 @theme 的理由）

隊色**不放 `@theme` token**，因為它隨「歷史隊／改名／轉賣」變動，且一年可多隊——是**資料驅動的身分色**，不是全站語意色。故 `lib/teams.ts` 為其唯一 owner，tsx 一律 import，**禁**在元件硬編隊色 hex。

| 現役隊（`TEAMS`，key=team_code） | 色 | 字母 |
|---|---|---|
| 味全龍 `AAA011` | `#C8102E` | W |
| 中信兄弟 `ACN011` | `#C8A24A` | B |
| 統一7-ELEVEn獅 `ADD011` | `#E35A13` | L |
| 富邦悍將 `AEO011` | `#2A4B9B` | G |
| 樂天桃猿 `AJL011` | `#8E1537` | R |
| 台鋼雄鷹 `AKP011` | `#15543C` | T |

- `CPBL_BLUE #1B4DA1`＝聯盟品牌藍（**與 `--color-cpbl` 同值**；聯盟層級用途，非隊色）。
- 未知/已解散隊 fallback＝`#94a3b8`（＝`faint` 灰）＋字母 `?`。

### 9.2 解析三路徑（依資料手上有什麼）

| 手上資料 | 用 | 產出 |
|---|---|---|
| 隊名（中文，常見於排行/H2H） | `nameMeta(name)` / `colorFromName` | `{color, letter}`（含現役全名+簡稱+歷史隊+二軍後綴） |
| team_code | `teamColor` / `teamLetter` / `teamShort` | 經 `franchiseOf()` 解析（二軍 022→現役、歷史碼→現役 franchise） |
| 沿革各時期（隊名+碼） | `eraBadge(name, code)` | 歷史期用 `HISTORICAL` iconic 色、現役期用 franchise 色 |

- **二軍沿用母隊色**（`nameMeta` 去 `二軍` 後綴解析）。
- **改名/轉賣視為同隊**：`FRANCHISE` 映射（兄弟象→中信兄弟、俊國/興農/義大→富邦、第一金剛/La New/Lamigo→樂天）。
- **連結規則**：`isCurrentTeam()`／`teamPageCode()`——有現役 franchise（含歷史隊）才連球隊頁，已解散隊不連（配 `GonePill`）。

### 9.3 徽章元件（何時用哪個；見 §3.2）

避官方 logo 版權，一律**隊色方塊 + 對比字母**。文字色**一律走 `contrastText(hex)`**（YIQ 亮度啟發式，閾值 0.6→黃/金系回深墨 `#0A2540`、其餘白）——**禁**在元件硬編白/黑字。

| 元件 | 場景 |
|---|---|
| `LetterBadge` | 已有 `{color, letter}`（單一事實來源，各處禁再手寫此 span） |
| `TeamLogo` | 由隊名/碼解析徽章；`decorative` 旁已有隊名時 `aria-hidden` |
| `NameTag` / `TeamBadge` | 徽章 + 隊名（`NameTag` 走隊名解析、含歷史/二軍隊） |
| `EraBadge` | 沿革/歷史隊（iconic 色） |
| `Leaderboard` `teamKey` | 隊徽併入名字欄（減欄手段，§5.2） |

### 9.4 隊色 hover 與狀態

- **隊色 hover 光暈**：`--hover-color` CSS var + `.card-hover-team`（`Card` 的 `teamColor` prop 啟用）→ 邊框變隊色 + 20% `color-mix` 光暈。跨主題安全（color-mix 動態）。
- **現役/已解散**：`ActivePill`（綠）/`GonePill`（灰）。

### 9.5 球迷暱稱（`FAN_NICK`）— 趣味層，嚴格隔離

`FAN_NICK`（龍龍/爪爪/喵喵/邦邦/吱吱/啾啾，**非官方**，源自社群含自嘲）**僅供賽況焦點等趣味標籤**；**正式文案、排行、統計、標題一律禁用**（見記憶 `cpbl-fan-lingo`）。走 `fanNick(code)`，經 `franchiseOf` 解析母隊。

### 9.6 隊名顯示階梯

由長到短四階，依可用空間降階（動因：**統一7-ELEVEn獅** 9 字中英混排會撐破窄欄/chip，違反 375px 鐵則）。**判準：容器會換行/溢出就降一階；固定寬表格欄禁塞全稱。**

| 階 | 形式 | 統一 | 味全 | 中信兄弟 | 富邦 | 樂天 | 台鋼 | 資料狀態 |
|---|---|---|---|---|---|---|---|---|
| ① **全稱** | 官方全名 | 統一7-ELEVEn獅 | 味全龍 | 中信兄弟 | 富邦悍將 | 樂天桃猿 | 台鋼雄鷹 | ✅ `teamFullName()` |
| ② **三～四字名** | 隊＋吉祥物（去贊助商雜訊） | 統一獅 | 味全龍 | 中信兄弟 | 富邦悍將 | 樂天桃猿 | 台鋼雄鷹 | ⚠️ 需新欄 |
| ③ **一字簡稱** | 吉祥物/識別單字 | 獅 | 龍 | 象 | 邦 | 猿 | 鷹 | ⚠️ 需新欄 |
| ④ **ICON（隊徽）** | 隊色方塊＋字 | 〔L〕 | 〔W〕 | 〔B〕 | 〔G〕 | 〔R〕 | 〔T〕 | ✅ `LetterBadge` |

- **資料現況（誠實，不腦補）**：`lib/teams.ts` 只有 ①全名、④英文 `letter`（W/B/L/G/R/T），另有 2 字 `short`（味全/兄弟/統一/富邦/樂天/台鋼，可作 ② 未就緒前的暫代）。**②的 3–4 字名、③的中文 1 字皆無欄位**——實作此階梯須擴 `TeamMeta`（加 `name3`/`char1`），屬資料/改碼任務（→ `UX-TOKEN-HYGIENE1` 或另卡），非現況。
- **ICON 是否需要？**：**建議保留**——ICON 的獨門價值是「隊色＋字」可在表格/對戰矩陣/圖例**靠顏色快速掃描辨隊**，純文字 ③ 失去色彩識別。惟需 Design Gate 裁定一個重疊：④現用**英文字母**，與 ③的**中文 1 字**並存，二選一：
  - **(a)** ④改用中文 1 字（龍/獅/象/邦/猿/鷹）→ 與 ③統一、對台灣使用者更直覺（傾向）。
  - **(b)** 維持英文字母 → ④走英文、③走中文，各司其職。

### 9.7 輔色（現況：無 per-team 輔色，一律由主色演算衍生）

**誠實現況**：`TeamMeta = {short, color, letter}`——**每隊僅定義一個主色（identity），全庫無 per-team 輔色/次色**。這是刻意的低維護選擇（Solopreneur-first：免蒐集/維護 6–12 組次色 hex）。

「輔色」需求一律**由主色演算衍生**（不新增 hex、維持 `lib/teams.ts` 單一 owner、跨主題安全）：

| 衍生用途 | 機制 | 現況出處 |
|---|---|---|
| on-color 文字（徽章字） | `contrastText(hex)`（YIQ 亮度→深墨/白） | `LetterBadge`/`TeamLogo` |
| hover 光暈 / 邊框 | `color-mix(in srgb, <隊色> 20%, transparent)` | `.card-hover-team`（`--hover-color`） |
| 淡底填色 | 主色 + opacity 修飾（比照 `amber/15`） | 狀態/標籤淡底慣例 |

> **禁**在元件硬編「第二隊色」。若未來確需**真實官方輔色**，屬**資料蒐集任務**（須查證各隊官方 VI 次色，非設計系統腦補），另開卡並一律寫入 `lib/teams.ts`（擴 `TeamMeta` 加 `color2`），本規格再據以補「主/輔色分工」段。

---

## 10. 公用元件模組化與模組邊界

> 落實原則 5「一致元件語彙／禁平行發明」的**結構性規則**：先定義「東西住哪裡」，再定義「何時抽共用」。

### 10.1 分層與模組邊界

| 層 | 路徑 | 內容 | 規則 |
|---|---|---|---|
| **純邏輯/資料** | `lib/*.ts` | 型別、fetch、格式化、身分色、圖表色、共用 Col、nav/methodology 內容、domain 計算 | **無 JSX**（型別除外）；可被 server/client 共用；**測試 co-located**（`*.test.ts`） |
| **UI primitives** | `components/ui.tsx` | Card/StatTile/StatGrid/Eyebrow/徽章/Pill/StatusBadge/Notice/三態/PercentileBar/StatAbbr | 全站原子；presentational、server-safe 優先 |
| **共用領域元件** | `components/*.tsx` | Leaderboard/DataTable/game-board/matchup-card/mini-standings/… | 跨頁重用；一律走 primitives 與 token |
| **功能子模組** | `components/<feature>/` | 如 `components/matchups/`（api/controls/explorer/insight/opponents-table/pair-card/…） | 複雜功能**成組收進子資料夾**（邏輯 + 元件 + 測試 + fixtures） |
| **頁面局部** | `app/**/*.tsx` | 如 `players/[id]/hero.tsx`、`season.tsx` | **僅該頁用**、不跨頁；一旦第二頁要用即上抽（§10.3） |

### 10.2 Server / Client 島式邊界（island architecture）

| 類型 | 例 | 規則 |
|---|---|---|
| **Presentational（server-safe）** | `DataTable`、`Card`、`table.tsx` | **無 hook、勿翻 `"use client"`**；可直接用於 server component |
| **Client island** | `Leaderboard`、`Tabs`、`HierarchicalTabs`、`useChartTheme` 消費端 | 互動/hook 隔離成**小島**；server 端把 server-rendered `ReactNode` 或**可序列化 props** 傳入 |

> **可序列化 props 鐵則**：跨 server→client 的設定用**可序列化物件而非函式**（如 `Col` 的 `link:{base,idKey}`、`chip`/`bar` 為布林旗標）——否則 server component 無法把它傳給 client 島。新增共用元件的 props 一律遵守。

### 10.3 抽取準則（頁面局部 → 共用）

出現以下訊號即上抽至 `components/`（或 `components/ui.tsx`），並在原碼註明「統一由此出」：

1. **同一 class 組合/區塊出現 3+ 次**（tailwind-patterns）。
2. **跨頁重用**（第二頁要用同概念）。
3. **屬設計系統元素**（徽章/狀態/卡片/三態等 §3 概念）。

> `ui.tsx` 既有註解即此準則的落地紀錄（例：LetterBadge「各處原本各自手寫此 span，統一由此出」）。**新頁面禁平行發明**：先查下方 registry。

### 10.4 單一事實來源 registry（新元件前先查此表）

| 概念 | canonical owner | 禁 |
|---|---|---|
| 卡殼 | `Card`（`.card`） | 手寫 `rounded-xl border border-line` |
| 隊徽/隊色 | `LetterBadge`/`TeamLogo` + `lib/teams.ts` | 手寫隊色 span、硬編隊色 hex |
| 場次狀態 | `StatusBadge`（done/warn/live/scheduled） | ad-hoc 狀態 pill、`amber-數字` |
| 載入/空/錯 | `Skeleton`/`EmptyState`/`ErrorState` | ad-hoc「載入中…」字串 |
| 靜態表 / 排行表 | `DataTable` / `Leaderboard` | 手刻 `<table>`/排序表 |
| 共用欄定義 | `lib/cols.ts`（`matchupCols`/`vsTeamCols`） | 各頁重寫相同 `Col[]` |
| tab/segment | §4 決策樹四語彙 | 第五種手刻 tab |
| 圖表色 | `lib/chart-theme.ts`（`useChartTheme`） | tsx 硬編圖表 hex |
| 格式化 | `lib/format.ts`（`fmtIP` 等） | 各頁重寫格式化 |
| 名詞解釋 | `StatAbbr`/`METRIC_DESCRIPTIONS` | 散寫 tooltip 定義 |

---

## 11. 動效與互動規範

> Token 見 §2.7。本節 codify **現況已存在的行為**（原則 7「動效節制」的落地），**不發明新動效/互動**。
> **實測現況**：全站 `animate-*` 僅 5 處、`disabled` 0 處——動效刻意稀少、控制項刻意不 disable。規格把此**克制**固化為規範。

### 11.1 動效 inventory（canonical closed set，禁發明新 keyframes）

| 類 | 機制 | token | 用途 |
|---|---|---|---|
| 入場 | `animate-fade-in`（`fadeIn`） | `--dur-base` | 內容/圖表進場 |
| 離場 | `animate-fade-out`（`fadeOut`） | `--dur-fast` | 提示/暫態離場 |
| 強調 | `animate-bar-grow`（`barGrow`） | `--dur-slow` | 勝率條伸展（狀態揭示） |
| 載入 | `animate-pulse`（Skeleton） | — | 三態 skeleton |
| Hover | `.card-hover-team`（border + `color-mix` 光暈 transition） | `--dur-base`/`--ease-standard` | 隊色卡 hover |
| 焦點/導覽 | `.skip-link` top transition、sticky nav `backdrop-blur` | `--dur-fast` | 跳轉/黏頂 |

> **新動效一律用既有 keyframe 或 `--dur-*`/`--ease-standard` token 組合**；禁新增裝飾性 keyframe、禁無限循環動畫（Skeleton `pulse` 例外）。

### 11.2 動效 taxonomy（何時動）

| 時機 | 允許 | 現況對應 |
|---|---|---|
| **入場** | ✅ ease-out（減速落定） | `fade-in` |
| **狀態變化** | ✅ 主題換色、hover 光暈、排序箭頭、expand | `useChartTheme` 重繪、`card-hover-team`、tab transition |
| **強調/揭示** | ✅ 克制用 | `bar-grow` 勝率條 |
| **載入** | ✅ skeleton pulse | `TableSkeleton` |
| **裝飾/閒置** | ❌ 禁無限裝飾動畫 | —（現況無） |

### 11.3 互動狀態矩陣（跨元件語彙）

| 狀態 | 視覺 | 備註 |
|---|---|---|
| default | 基底 token | — |
| **hover** | 提色/底色（`hover:text-ink`、`hover:bg-surface-2`、隊色光暈） | 主要互動 affordance（現況 hover 用最重） |
| **focus-visible** | 全域 2px `accent` outline（滑鼠點擊不顯示、Tab 才顯示） | 一律走 `:focus-visible`，禁個別覆寫掉 |
| **active/pressed** | `bg-ink text-paper`（toggle/tab，見 §4）；`aria-pressed`/`aria-selected`/`aria-current` | 語意態必配對應 ARIA |
| **expanded** | `aria-expanded`（`<details>`/完整欄切換） | disclosure 模式 |
| **loading** | 三態 `Skeleton`（§3.3） | 不塌陷（CLS） |
| **disabled** | **現況不使用**（0 處）——以隱藏/略過取代 disable（呼應誠實 UX/漸進揭露） | 若確需：`aria-disabled` + `opacity`/`muted`，非純色 |

### 11.4 鍵盤與焦點（a11y 互動）

- **Roving tabindex + 方向鍵**：`HierarchicalTabs`/`ContextSwitcher`/`TabItems` 以 `ArrowLeft/Right` 切換，`focus({ preventScroll: true })` 移焦不捲頁；`tabIndex` 僅 active 為 0。
- **ARIA 對應**：內容 tab→`role=tab`+`aria-selected`；情境/toggle→`role=group`+`aria-pressed`；跨路由→`aria-current="page"`；折疊→`aria-expanded`。
- **全域焦點環**：`:focus-visible`（§8）；`.skip-link` 跳主內容。
- **觸控**：互動元件 `min-h-11`（44px，§7）。

### 11.5 主題切換反應性（無閃爍 + 即時重繪）

- **無閃爍**：layout inline script 於**首繪前**寫 `<html data-theme>`；`ThemeToggle` 掛載前保留等寬佔位避免 CLS。
- **即時重繪**：`useChartTheme` 以 `MutationObserver` 監看 `data-theme`，一變即重讀 token 重繪 recharts（§6.1）。工具類/`var()` 元件則自動換色、無需 JS。
- **持久化**：`localStorage` 存偏好；無痕/封鎖時退化為本 session 生效。

### 11.6 圖表互動（對齊 dataviz）

- **hover 層預設有**：line/area 給 crosshair+tooltip；bar/dot/cell 給 per-mark hover tooltip；hit target 大於標記；filters 置於圖上方一列。
- **tooltip 走 `Tooltip` 元件**（原生 `title` 有延遲且**觸控無效** → 自繪）；容器樣式走 `chartTooltip(ct)` 隨主題換色。
- 唯一不需 hover 層者：無 plot 的純 stat tile。

### 11.7 克制預算（原則 7 明確化）

- 只在**入場 / 狀態變化 / 載入**動；**禁**閒置裝飾與無限動畫。
- **一律受 `prefers-reduced-motion` 約束**（globals.css 已全域近乎關閉動畫/轉場/scroll-behavior）。
- 只動 `transform`/`opacity`/`color`/`box-shadow`；切換**不塌陷**（CLS，§3.3 三態等高佔位）。

---

## 附錄：配套產物

- **逐頁 conformance 差距清單** → [`UI_UX_CONFORMANCE.md`](UI_UX_CONFORMANCE.md)（players=100% 基準；15 路由偏離項 + 嚴重度；供 `UX-DESIGN-CONFORM1` 消費）。
- **token/元件 hygiene 修復卡 spec** → [`../tasks/UX-TOKEN-HYGIENE1.md`](../tasks/UX-TOKEN-HYGIENE1.md)（chart-7/8 重複/深色缺定義、CVD 驗證、amber 數字色階、ad-hoc 載入態、sub-legible 字級——本卡只記錄，修復另卡執行）。
