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

## 4. 導覽與 Tab / Segment 語彙（決策樹）

**現況＝四種語彙並存，依語意角色分工**（刻意不合併：a11y 語意不同）。統一鐵則：**active＝`bg-ink text-paper`（pill/group）或 `border-ink font-semibold`（underline），禁 `text-white`；觸控 `min-h-11`(44px)**。

| 語彙 | 元件 | 何時用 | active 態 | a11y |
|---|---|---|---|---|
| **階層雙層** | `HierarchicalTabs` + `ContextSwitcher` | 頁內雙層資料範圍（scope + view，如球員頁本季/生涯 × 總覽/逐球/…） | group `bg-ink text-paper`；item `border-b-2 border-ink` | group（`aria-pressed`）+ tablist（`role=tab`）分離語意 |
| **情境切換** | `ContextSwitcher` | 情境軸（身分打/投、層級一/二軍），segmented 膠囊 | `bg-surface text-ink shadow-sm`（凸起感） | `role=group` + `aria-pressed` |
| **單層分頁** | `Tabs` | 單層 server-rendered 內容分頁（資料已在 props，切換不打 API） | pill `bg-ink text-paper` | `role=tablist/tab` |
| **路由切換 nav** | `RankRoleTabs` / `level-year-nav` | 跨路由導覽（`/batters ↔ /pitchers`、年度/層級），保留 query 脈絡 | pill `bg-ink text-paper` | `aria-current="page"`（連結非 tab） |

> **⚠️ open item（待查核裁定）**：`ContextSwitcher` active 用 `bg-surface text-ink shadow-sm`（而非通則的 `bg-ink text-paper`）——這是 segmented 控制的凸起慣例，**現況如此**，規格誠實描述而非強制統一。若查核方要求收斂，另開卡處理。
> **決策樹**：新頁面 → 頁內內容切換？→ 雙層用 `HierarchicalTabs`、單層用 `Tabs`；情境軸用 `ContextSwitcher`；跨路由用 `aria-current` 連結 nav（比照 `RankRoleTabs`）。**禁**再手刻第五種。

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

## 附錄：配套產物

- **逐頁 conformance 差距清單** → [`UI_UX_CONFORMANCE.md`](UI_UX_CONFORMANCE.md)（players=100% 基準；15 路由偏離項 + 嚴重度；供 `UX-DESIGN-CONFORM1` 消費）。
- **token/元件 hygiene 修復卡 spec** → [`../tasks/UX-TOKEN-HYGIENE1.md`](../tasks/UX-TOKEN-HYGIENE1.md)（chart-7/8 重複/深色缺定義、CVD 驗證、amber 數字色階、ad-hoc 載入態、sub-legible 字級——本卡只記錄，修復另卡執行）。
