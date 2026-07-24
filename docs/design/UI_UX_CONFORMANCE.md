# 逐頁 Conformance 差距清單（UI/UX 設計系統）

> **配套** [`UI_UX_SYSTEM.md`](UI_UX_SYSTEM.md)。以球員個人頁 `/players/[id]` 為 **100% 基準**，逐頁列偏離項與嚴重度，供 **`UX-DESIGN-CONFORM1`**（既有頁面對齊卡）消費。
> **本卡（UX-DESIGN-SYSTEM1）只列差距，不修頁面**（修復是後續對齊卡職責）。
> **證據**：以 grep 訊號 + 抽讀為基礎（非逐行全審）；標 ⚠️ 者建議 CONFORM 卡進場前逐檔複核。

## 嚴重度與檢核維度

- 🔴 **破壞一致性**：違反 canonical 鐵則（硬編 hex、白底白字、手刻已存在元件的平行發明）。
- 🟡 **中度**：token 未走語意（Tailwind 數字色階）、ad-hoc 三態、idiom 分歧、sub-legible 字級。
- 🟢 **微調/合規**：符合或僅極輕微。

**檢核維度**：① token 紀律（無 hex/無數字色階）② 三態元件 ③ tab/segment 語彙 ④ 表格/Leaderboard 契約 ⑤ 深色（禁 text-white 白底白字）⑥ 44px 觸控 ⑦ 圖表走 useChartTheme ⑧ 語意 badge。

---

## 逐頁對照

| 路由 | blueprint | tab 語彙 | 三態 | token | 主要偏離項（證據） | 嚴重度 |
|---|---|---|---|---|---|---|
| `/players/[id]` | §5.7 | HierarchicalTabs + ContextSwitcher | ✅ 全 | ✅ | **基準**。零硬編 hex。少數 `text-white` 於 `hero`/`tracking`/`detail` 在飽和色塊上（對比 OK，屬 §2.2 用語一致性微瑕：應 `text-paper`） | **100%** 基準 |
| `/`（今日） | §5.1 | —（DailyHub） | ✅ `Card`+`ErrorState` | ✅ | 無明顯偏離 | 🟢 |
| `/games` | §5.2 | —（月曆） | ✅ `EmptyState` | ✅ | `text-white` 於 `bg-accent` 未讀數徽章/MVP（飽和底，合法對比）；**四軸（kind/year/隊伍篩選/月份）三 nav 分列、kind+year 手刻未用 `LevelYearNav`，未走 §4.3 一體式導引欄**（→ [`../tasks/UX-NAV-INTEGRATE1.md`](../tasks/UX-NAV-INTEGRATE1.md) Phase 3） | 🟡（多軸導引） |
| `/games/[sno]` | §5.3 | box-tabs（bespoke）+ `DataTable` | ⚠️ 部分：逐球分頁 `umpLoading` **ad-hoc「載入中…」** | ✅（`game-board` 為授權例外） | ad-hoc 載入態（`box-tabs.tsx:570`）；active toggle `bg-cpbl text-white`（應 `text-paper`）；4 處手刻 `rounded-xl border`（部分為內部面板，須複核） | 🟡 |
| `/standings` | §5.4 | —+`DataTable` | ⚠️ 未 import 三態 | 🔴/🟡 **Tailwind 數字色階** `bg-amber-100/500/700`、`text-amber-700`（`page.tsx:186/645/654/659`）取代語意 `--color-amber`；`bg-amber-500 text-white` 徽章 | 季後保送/淘汰標籤未走 `StatusBadge`/`amber` token；3 處手刻卡殼；**三軸控制（層級 `kind`/階段 `seg`/年度 `year`）散置＋孤立年度下拉，未走 §4.3 一體式導引欄**（→ [`../tasks/UX-NAV-INTEGRATE1.md`](../tasks/UX-NAV-INTEGRATE1.md) Phase 1） | 🟡（token + 多軸導引） |
| `/batters` | §5.6 | `RankRoleTabs`+`level-year-nav`（bespoke，active `bg-ink text-paper` ✅）+ `Leaderboard` | ✅（Leaderboard/DataTable 內建） | ✅ | **四軸（role/view/kind/year）兩 nav 分列，且 `AwardRaces`(獎項排行榜) 垂直堆疊在 `Leaderboard`(完整清單) 上→難讀**；未走 §4.3 一體式導引欄、view 未做分頁（→ [`../tasks/UX-NAV-INTEGRATE1.md`](../tasks/UX-NAV-INTEGRATE1.md) Phase 2） | 🟡（多軸導引 + 視圖堆疊） |
| `/pitchers` | §5.6 | 同 `/batters` | ✅ | ✅ | 同 `/batters` | 🟢 |
| `/teams/[code]` | §5.8 | `Tabs`（pill）+ `DataTable` | ✅（`parts` import 三態） | ✅ | 多軸整合 **N/A**：`searchParams` 僅 `code`、無 kind/year 散置、已用 canonical `Tabs`（→ [`../tasks/UX-NAV-INTEGRATE1.md`](../tasks/UX-NAV-INTEGRATE1.md) Phase 4 稽核確認、預期無改動） | 🟢 |
| `/matchups` | §5.9 | —+`EmptyState`；explorer 整合控制列 | ✅ | 🟡 **`text-amber-600`**（`matchup-card.tsx:89/91`）取代 `--color-amber`（先發投手文字） | 先發投手 amber 未走 token；多軸 explorer（role/kind/scope/年範圍/對手）**已有整合控制列**→align 共享軸（→ [`../tasks/UX-NAV-INTEGRATE1.md`](../tasks/UX-NAV-INTEGRATE1.md) Phase 4） | 🟡 |
| `/records` | §5.10 | `DataTable` | ✅（`emptyText`） | ✅ | 無明顯偏離 | 🟢 |
| `/venues`,`/venues/[venue]` | §5.11 | `DataTable` | ✅（`emptyText`） | ✅ | 多軸整合 **N/A**：無軸選擇器、清單/詳情（→ [`../tasks/UX-NAV-INTEGRATE1.md`](../tasks/UX-NAV-INTEGRATE1.md) Phase 4 稽核確認、預期無改動） | 🟢 |
| `/umpires` | §5.12 | bespoke toggle + `DataTable` | ⚠️ **ad-hoc「載入中…」**（`page.tsx:273`）；未 import 三態 | ✅ | active toggle `bg-cpbl text-white`（應 `text-paper`）；2 處手刻卡殼 | 🟡 |
| `/people/[kind]/[name]` | §5.13 | —+`EmptyState` | ✅ | ✅ | 無明顯偏離 | 🟢 |
| `/methodology` | §5.14 | —（prose） | —（靜態） | ✅ | 無明顯偏離 | 🟢 |
| `/predict` | §7（待替換） | —（**7 行 stub/redirect**） | n/a | n/a | blueprint §7「replacement before removal」——現況已縮為 stub；**視覺 scope 外**，替換由 §7 相關卡處理 | 🟢（n/a） |

---

## 跨頁面 cross-cutting 偏離

| 項目 | 證據 | 影響頁 | 嚴重度 |
|---|---|---|---|
| **arbitrary 字級 `text-[Npx]`** | 全站 ~222 處（`[11px]`×127、`[10px]`×78、`[9px]`×11、`[13px]`×5、`[8px]`×1） | 幾乎全站 | 🟡（技術債；`UI_UX_SYSTEM §2.3` 收斂角色，**新碼強制、既有漸進**） |
| **sub-legible 字級** `text-[8px]/[9px]` | 12 處 | 散見 hero/tracking/game-board | 🟡（可及性；建議上調 ≥10px 或改 icon） |
| **`text-white` 於 active toggle/badge** | `detail.tsx:50`、`box-tabs.tsx:619/623`、`umpires:197/201`、`game-board:285`、`standings:645` | 上列頁 | 🟢/🟡（多在飽和底，對比合法；屬 §2.2 用語一致性——應 `text-paper`；非「白底白字」實害） |
| **Tailwind 數字色階取代語意 token** | `standings`（amber-100/500/700）、`matchup-card`（amber-600） | standings、matchups | 🟡（違反 §2.8 hex/數字色階白名單） |
| **手刻 `rounded-xl border`（非 `Card`）** | box-tabs×4、standings×3、umpires×2、fielding×2、多元件×1 | 上列頁 | 🟢/🟡（部分為 `DataTable` 表殼/內部面板等授權情境，須 CONFORM 逐檔判別是否應改 `Card`） |

---

## Token / 元件 hygiene 缺口（屬改碼範疇，修復 → `UX-TOKEN-HYGIENE1`）

> 本卡紅線禁改 `globals.css`/元件碼，僅記錄。詳見 [`../tasks/UX-TOKEN-HYGIENE1.md`](../tasks/UX-TOKEN-HYGIENE1.md)。

| # | 缺口 | 位置 | 嚴重度 |
|---|---|---|---|
| H1 | `--chart-7`/`--chart-8` **重複定義**（`#f472b6/#d4a373` 後被 `#db2777/#a16207` 覆蓋，前者 dead） | `globals.css:56-59` | 🟢（dead code） |
| H2 | **深色模式缺 `--chart-7/8` 覆寫**（`[data-theme=dark]` 只到 chart-6）→ 深色退回淺色值，navy 底對比可能不足 | `globals.css:96-105` | 🟡 |
| H3 | **`--chart-1..8` 分類序列從未跑 CVD 相鄰對驗證**（dataviz 要求 ΔE≥8） | `globals.css` + `chart-theme.ts` | 🟡 |
| H4 | `zone-*`/`status-*` **語意在 `@theme` 與 `chart-theme.ts` 常數盤雙處定義** → 潛在 drift | `globals.css` + `chart-theme.ts` | 🟢 |
| H5 | Tailwind 數字色階 `amber-N` 應改語意 `amber` token | `standings`、`matchup-card` | 🟡 |
| H6 | ad-hoc「載入中…」應改三態元件 | `umpires`、`box-tabs` | 🟡 |
| H7 | sub-legible `text-[8px]/[9px]` 上調 | 散見 | 🟡 |
| H8 | `<select>` 圓角不一致（`YearSelect` `rounded-full` vs `Leaderboard` 篩選 `rounded-lg`）→ 統一 control `rounded-lg`（或明訂 pill-select 限工具列 chip） | `year-select.tsx`、`leaderboard.tsx` | 🟢 |
| H9 | 隊名階梯（`UI_UX_SYSTEM §9.6`，5 階）②三～四字名、④中文 1 字**無欄位** → 擴 `TeamMeta` 加 `name3`/`char1`（`char1` 僅供文字階；**⑤ICON 維持英文 `letter`，Design Gate 定案不改**）；③二字 `short` 於中信兄弟現為「兄弟」需改「中信」（母企業）。**資料擴充，非缺陷** | `lib/teams.ts` | 🟢 |

---

## 可及性抽驗清單（CONFORM 進場前逐項計算/實測）

- [ ] `faint #94a3b8` 承載必要文字之處（名次、單位）→ 確認非唯一資訊，否則改 `muted`（§2.1 對比 ~2.6:1）。**註**：2.6:1 亦**未達 AA-large 3:1**，故即使放大/加粗仍不合格——必要文字一律 `muted`，`faint` 僅留純裝飾/非必要。
- [ ] `amber/15` 底上的 `amber` 文字（`StatusBadge warn`）對比 → WCAG 計算。
- [ ] `white on accent #d62839`（~4.5:1 臨界）小字徽章 → 確認字級 ≥ 大字門檻或改色。
- [ ] 深色 `chart-7/8` 退回淺色值 on navy → 對比計算（H2）。
- [ ] `text-[8px]/[9px]` 全數點名 → 上調（H7）。
- [ ] 各圖表文字替代列表是否齊備（blueprint §8.3）。

---

## 摘要

- **強項**：token 紀律良好（app 頁面**零硬編 hex**）；三態/表格/徽章元件收斂度高；深色機制健全；多數頁 🟢。
- **主要待對齊**：① `standings`/`matchup-card` 的 Tailwind 數字色階 →語意 token；② `umpires`/`box-tabs` ad-hoc 載入態 →三態；③ 全站 arbitrary 字級收斂（漸進）；④ token hygiene（chart-7/8、CVD）另卡修。
- **無 🔴 級**跨頁破壞：現況一致性整體良好，偏離集中於少數頁的 token/三態用語。
