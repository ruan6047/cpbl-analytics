# 任務看板 (Task Board)

> 進度追蹤。規則見 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)。**git commit trailer 為單一事實來源**，本檔為人類可讀總覽；衝突以 git 為準。
> 狀態：`📥Backlog → ⏳待執行 → 🔨執行中 → 🔍待查核 → ✅通過 → 🏁完成`／`↩退回`
> **只留活卡**：卡片一旦 🏁完成 或 📥封存，整段移到 [`archive/TASKS_ARCHIVE.md`](archive/TASKS_ARCHIVE.md)（Ledger 列一併移），本檔保持精簡省 AI 讀取算力。

---

## Ledger 總表（活卡）

| 卡ID | 功能 | 需求 | 規劃 | 執行(model@tool) | 查核(model@tool) | 分支 | 紅線 | 狀態 |
|---|---|---|---|---|---|---|---|---|
| UX-1 | 全站頁面 UI/UX 重新設計（傘卡） | ruan6047 | Fable-5@Claude Code | —（子卡執行） | —（子卡查核） | — | ⚪ | 🔨子卡執行中（spec v5 已核可 07-11） |
| UX-5A | 戰績頁（`/standings`）換裝 | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | ⏳待執行（待 UX-5B 搬遷落地後換裝） |
| UX-5C | 首頁 hub 完整版（各頁關鍵訊息總集） | ruan6047 | 待小 spec | 待指派 | 待指派 | — | ⚪ | 📥Backlog（**壓到 UX-6〜9 完成後**重製） |
| UX-6 | 賽況群 `/games`、`/games/[sno]` | ruan6047 | Fable-5@Claude Code | Opus/Fable@Claude Code | 待指派 | `ai/opus/UX-6` | ⚪ | 🔨執行中（換裝+焦點+Box標籤頁+分析tab 已落地，待截圖驗收） |
| ML-PT2 | 球種細分 v2（MLB 標籤遷移） | ruan6047 | Fable-5@Claude Code | Fable-5@Claude Code | 待指派（建議人審 repertoires） | `ai/opus/UX-6` | 🔴統計紅線 | ✅Phase1/2/2.5＋採用 完成（97.1%>v1 94.2%），待查核+部署 |
| UX-7 | 球員/球隊頁 | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | ⏳待執行（通用層已齊，待派工） |
| UX-8 | 排行與紀錄群 | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | ⏳待執行（通用層已齊，待派工） |
| UX-9 | 週邊群 `/matchups`、`/venues` | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | ⏳待執行（通用層已齊，待派工） |
| UX-10 | 三頁互動模式重設計 | ruan6047 | 待各自小 spec | 待指派 | 待指派 | — | ⚪ | 📥Backlog（暫緩，不在本輪序） |

> 「待指派」＝ruan6047尚未派工。派工後把 model@tool 補實、狀態改 🔨。
> **依賴序**：(UX-2 🏁 / UX-3 🏁 / UX-4 🏁 / UX-4.5 🏁) 通用層已齊 → UX-5〜9 頁面層（大→小）已解鎖。UX-5 已拆 **UX-5B（hub v1＋搬遷，🏁 merge `e74853b`）→ UX-5A（戰績換裝）→ UX-5C（首頁完整版，壓 UX-6〜9 之後重製）**。UX-10 暫緩。

---

## 進行中／待辦卡

### UX-1 全站頁面 UI/UX 重新設計  〔⚪（大卡：規劃後預期拆多張子卡，涉全站視覺）〕
- 需求：ruan6047（07-11）——**重新設計每個頁面的 UI/UX**。痛點：①頁面不統一 ②數據可視度不夠 ③頁面與區塊混亂；另 成績預測/賽事預測/裁判報告 三頁**操作模式與現實脫節**（抽出 UX-10 暫緩個別處理）。
- 規劃：Fable-5@Claude Code → spec 見 [`UX_REDESIGN_SPEC.md`](UX_REDESIGN_SPEC.md)（八原則＋UX-2〜9 拆卡＋深色模式決策點）
- 執行：子卡各自執行　查核：子卡各自查核（涉全站視覺，建議跨家族或人審驗收）
- 狀態：🔨 spec v5 **已核可**（07-11）；子卡進度：**UX-2／UX-3／UX-4／UX-4.5 🏁完成（已 archive）＝通用層全齊**、UX-5〜9 ⏳待執行（已解鎖待派工）、UX-10 暫緩。本傘卡隨子卡全數結案後移 archive　Commit：—
- 前置事實（規劃時必讀）：現行設計系統＝日間 Navy+白（memory `frontend-redesign`）；UI-2/3/4 剛完成運動風質感/微互動/響應式（`docs/archive/`）；UI-1 深色模式與 UI-5 對比頁在封存區可視需要復活併入
- Log：
  - 07-11 需求開卡 by ruan6047（Fable-5@Claude Code 代記）
  - 07-11 ruan6047 派規劃（原則先行、通用→個別、大→小）；規劃 by Fable-5@Claude Code 出 spec，🚦待核可
  - 07-11 ruan6047 補需求背景（三痛點）＋範圍裁示（三脫節頁暫緩）→ spec v2：痛點對應表、可視度量化下限、頁面解剖規範、UX-10 暫緩卡
  - 07-11 ruan6047 裁定深色模式併入 UX-2；模組化審計 by Fable-5 → 證實偏低（卡片殼 inline×46、手寫表格×22/9檔、skeleton=0、components 佔 28%），量化基準入 spec 作 UX-3 驗收對照
  - 07-11 ruan6047 澄清「可視度」＝快速理解（過多數據→判讀負荷），非易讀性 → spec v4：原則 1 重寫（漸進揭露/數字不裸列/每區塊一問題/5 秒測試＝頁面卡首要驗收）
  - 07-11 ruan6047 令重評需求 → 規劃自查（審計數字實測仍準；ruan6047 核可四修正）→ spec v5：UX-2 瘦身（全頁雙色系驗收下放頁面卡）、圖表色票 API 歸 UX-2、UX-3 client island 約束、5 秒測試盲測定義、table 勘誤 11 檔
  - 07-11 ruan6047 **核可 spec v5** → 規劃階段收尾；UX-2〜10 依依賴序開卡進 Ledger，待 ruan6047 派工執行
  - 07-11 **UX-2 🏁**（tokens/深色/圖表色票 API；Gemini-3.5-Flash@Antigravity 查核 → ✅ → archive）＋**UX-3 🏁**（元件/表遷移/三態/卡殼 sweep；Gemini-3.5-Flash@Antigravity 查核 → ✅ → archive）→ 通用層解鎖 **UX-4**
  - 07-11 **UX-4 🏁**（骨架導覽＋頁面解剖；Gemini-3.5-Flash@Antigravity 執行，merge `a9a8132` → archive `6f3c8d4`）＋**UX-4.5 🏁**（互動動效準則＋Tooltip；merge `b035c24`／標記 `52f3eaf`）→ **通用層全齊**，UX-5〜9 解鎖待派工（本次補搬 UX-4.5 進 archive，修正過期狀態）

---

> **UX-5 拆卡裁示（ruan6047 07-11）**：原「首頁（戰績）換裝」拆為 **UX-5B 首頁 hub v1＋搬遷**（🏁 已 merge，見 archive）→ **UX-5A 戰績頁換裝**（`/standings`）→ **UX-5C 首頁 hub 完整版**（壓 UX-6〜9 完成後重製，因各頁關鍵訊息長相隨那些頁換裝而定）。避免 hub 與戰績頁重複：hub 卡為「指路牌」（1 數字＋1 結論＋連往該頁），半季形勢面板為 UX-5A 專屬。

### UX-5A 戰績頁（`/standings`）換裝  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 頁面層）　分支：`ai/<執行者>/UX-5A`
- 執行：待指派　查核：待指派（≠執行者，關鍵頁建議人審）
- 範圍/驗收：`/standings`（UX-5B 已搬遷、merge `e74853b`）換裝——
  - **主角區 Hero**：半季形勢/領先者＋季後賽線，本頁專屬勿與 hub 重複。
  - **欄位重規劃**（ruan6047 07-11）：砍**出賽數**（低值、由 W-T-L 可推）；**連勝連敗**改隊名旁**標籤**（綠連勝/紅連敗）不佔獨立欄；OPS/ERA/WHIP 漸進揭露；核心欄常駐＋L10 迷你視覺。手機減欄避免橫向捲（實測 768px 主表溢 167px）。
  - **對戰成績並排基本數據＝兩欄**（ruan6047 07-11，取代原「頁籤/收合」方向）：桌機左右並排、**以隊列對齊**（同列＝同隊：左讀戰績、右讀該隊對各隊 H2H），一屏同時看到，解「對戰矩陣壓底需垂直捲」；手機堆疊。對戰矩陣補 sticky 首欄。
  - **走勢圖**：折線尾端隊徽 direct labeling 取代 legend（隊徽＝隊色方塊+字母可原生 SVG，6 隊收斂需垂直錯位、右邊界留白、375px 退場——不適合不硬做）。
  - **含 5 表遷 DataTable**（自 UX-3 下放）。首要驗收＝5 秒盲測「誰領先」＋深淺雙色系截圖。
- 狀態：✅執行完成、驗證通過（`ruff` + `build:check` 綠、雙色系+手機截圖驗）；**待人審 + 部署閘門**（merge→main、F 資料同步生產、submodule bump 部署）　Commit：`7947af4`/`a67e0d8`（核心）、`1f0d9fc`/`f8f5e8b`（二軍總冠軍）、`1806d24`（docs）
- Log：
  - 07-11 自 UX-5 拆出（戰績頁純換裝）
  - 07-11 UX-5B merge 後，ruan6047 反映戰績頁痛點並定方向：基本數據手機顯示不完→減欄；出賽數低值→砍；連勝連敗→標籤化；對戰成績想更醒目→與基本數據並排兩欄、以隊列對齊；折線尾端補隊 icon（實測數據見範圍）
  - 07-11 Opus 執行：控制列整併為單一分頁列（全年/上半季/下半季/季後賽/戰績細項），頭部只留 一軍/二軍+年份、切頁不位移；二軍只有全年（DB 無二軍季後賽/半季資料，站上 E/C 僅一軍——見 CPBL_SITE_MAP L163）；歷年開放戰績細項；隊名旁加🏆總冠軍、砍全年龍頭；已淘汰標 E（非 ME）
  - 07-11 新增**季後賽淘汰賽 bracket**（seg=3）：依實際系列（E/C）呈現、參賽隊取自資料、讓一勝由勝隊 game 勝場反推；棒球計分表式逐場小比分（勝方標色、讓欄計入大比分）；現行制（2022+）僅用於當季預測。查證聯盟規章 60–63 + 賽制世代（2022 起不同半季冠軍才打挑戰賽，之前直接台灣大賽）→ 修正 2021 以前的錯誤結構。逐場比分本就在 games 表、不需爬
  - 07-11 二軍季後賽探查完成：官網 KindCode `F`＝二軍總冠軍賽（原 SITE_MAP 只列 A/C/D/E，補 F/B/G/X）。本機爬 F 2005–2025 入 games；前端二軍分頁＝全年+總冠軍（FarmChampion 單系列計分表、全年表加🏆）。Hero 依 ruan6047 指示移除、季後賽形勢改由「季後賽」分頁承載
  - 07-11 執行完成：`ruff`+`build:check` 綠。**待決部署閘門**：(a) merge ai/opus/UX-5A→main；(b) F 資料同步生產（pg_dump --clean 全 schema，需 SSH VPS，風險高）；(c) submodule bump→CI 部署（~12min）。G(2024 一軍30場)未知賽事、低優先待查

### UX-5C 首頁 hub 完整版  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：待小 spec　分支：`ai/<執行者>/UX-5C`
- 執行：待指派　查核：待指派（≠執行者）
- 範圍：重製 `/` hub——在 UX-5B v1（hero＋3 指路牌卡）基礎上擴充各頁關鍵訊息總集（更多卡＋更豐富摘要）。**刻意壓到 UX-6〜9 完成後**：各頁關鍵訊息的呈現形態會隨那些頁換裝而定，太早做會重工。屆時出小 spec 定卡片組合。
- 狀態：📥Backlog（gated on UX-6〜9）　Commit：—
- Log：
  - 07-11 ruan6047 令：UX-5B merge 後開此卡，等其他頁面完成再重製首頁

### UX-6 賽況群  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 頁面層）　分支：`ai/<執行者>/UX-6`
- 執行：待指派　查核：待指派（≠執行者）
- 範圍/驗收：`/games`、`/games/[sno]`。**卡性質＝換裝對齊＋焦點三振/效率家族擴充（含新邏輯，非純換裝）**（ruan6047 07-12 裁定）。
  - **Part A 換裝（全做）**：A1 抽 `StatusBadge`（完賽/延賽/保留/未開打，全站唯一狀態語彙，`ui.tsx` 現無）→ list 收斂手刻兩套 pill；A2 amber 硬色 ×5 走 warn 語意 token（隊色/圖表色除外）；A3 emerald/sky（安打/保送）收斂進 `chart-theme`（比照 `PITCH_CALL`）；A4 detail 載入態 `EmptyState`→skeleton（記分條+linescore 骨架，防 CLS）+錯誤走 `ErrorState`；A5 延賽 banner 抽 `Notice/Callout`（warn）；A6 `Box Score`/`本場焦點`/`特殊紀錄`小標走 `Eyebrow`。
  - **B2′ 焦點擴充（投打跑家族，07-12 追加，含新判定邏輯）**：標準三振門檻 **10→8**；新增 ①**連續三振**（同投手連續 **≥5** 打席全三振，跨局；門檻可調）②**單局三振**（同投手單半局 3K 即標，含上壘後補 K，較寬版）③**三球關門**（效率局：半局內該投手投球數 **≤3** 且完成 3 出局，雙殺可壓縮球數，如雙殺+高飛＝2 球 3 出局，label 顯示實際球數）④**連續解決打者**（同投手 rolling 連續解決 **≥6** 名，無安打/四死/失誤上壘，跨局；「超過六上六下」，六上六下本身即入選，label 顯示連續數；與 ① 可並存，屬不同層）⑤**單局連續盜壘**（同一跑者單半局盜 **≥2** 壘包，二盜接三盜/含盜本）⑥**雙盜壘**（double steal，同球兩跑者同時盜成功）⑦**全打席上壘**（打者單場所有打席皆上壘＝安打/四死，失誤·野選破壞；**PA ≥4**，門檻可調；label「N 打席全上壘」；重用 livelog PA kind hit/walk/out）⑧**先發全員安打**（某隊 9 名先發打者＝`role_type`＝先發且棒次 1–9 各 ≥1 安，隊級 chip；重用 box `role_type`/`batting_order`/`hits`）⑨**萬磁王**（球迷用語：打者單場觸身球 **≥2**；重用 livelog 死球 kind 觸身；**落地時補進 memory `cpbl-fan-lingo`**，比照劇場/問天/魯閣）⑩**盜本壘**（單獨一次真盜本即成標；重用 `sabr.py:337` `_SBH_RE`＝`三壘跑者…盜壘回本壘得分`，只認真盜本、不含暴投/野選回來得分；與 ⑤「含盜本」部分重疊但獨立成標）。**注意：當局 2 失誤已存在＝煮粥**（`page.tsx:258` scoreboard `error_cnt≥2`，球迷用語），不重做（如需中性非暱稱版另議）。⑤⑥ 重用 `sabr.py:336` 現成盜壘 regex（`([一二三])壘跑者…(?:雙)?盜壘上([二三])壘`），非腦補。**注意：單場雙盜壘（SB≥2）已存在**（`page.tsx:278`「N 次盜壘」），不重做。全從 `data.livelog`/box 客戶端算（比照中計/煮粥），**無 migration/後端**；僅 2018+ 有逐打席故歷史場自然不顯示（誠實，與現況一致）。
  - **必聲明特例（不改、寫進 PR 免被當回歸）**：(a) detail 整頁 `"use client"`＝本質互動非「為互動翻頁」，維持；(b) `game-board.tsx:290` `ScoreLine` 手刻 `<table>`＝可點擊逐局比分導覽（每格 button+active+RHE 轉置雙列），欄定義式 `DataTable` 不適配，維持手刻+特例註記；(c) game-board 9 處 inline card shell 為 live board 特化面板（padding 不合 `Card`），保留+特例註記。
  - **不做（scope creep／低 ROI，已評估）**：B2 Game Leaders 摘要、B3 深連結 `?pa=`（可另開後續小卡）、打者vs投手生涯對戰史、黏頂即時比分列、OG 分享圖、傷兵/預測陣容（無資料源）。
  - 驗收：全站 grep 無 amber 硬色（games 群）；三態統一無 CLS；5 秒盲測（「今天誰贏」）＋深淺雙色系 375/1280 截圖；**焦點新標籤 ①–⑩（連續三振/單局三振/三球關門/連續解決≥6/單局連續盜壘/雙盜壘/全打席上壘/先發全員安打/萬磁王/盜本壘）各附 2018+ 實際觸發樣本逐項驗證判定**；`tsc`＋`build:check` 綠。**執行維持 Opus**：逐球序/連續判定錯了難察覺（非 ML 紅線故不動 Fable）。
- 狀態：🔨執行中（`ai/opus/UX-6`；Part A＋焦點①–⑩＋Box中文 已落地綠燈，待視覺驗收）　Commit：—
- Log：
  - 07-11 spec v5 核可後開卡
  - 07-12 ruan6047 規劃定案：Part A 換裝全做＋B1 上/下一場導覽加碼；B2/B3 排除。實測盤點：games 群硬色（amber×5 狀態警示／emerald·sky×4 圖表語意）、inline card shell 13 處、手寫 table 1（ScoreLine 特例）、`Eyebrow/Skeleton/StatAbbr` 現用量 0
  - 07-12 ruan6047 追加焦點三振/效率家族並裁定併入本卡：8K 門檻、連續三振 ≥5、單局 3K（寬版）、三球關門（效率局，雙殺壓縮出局，如雙殺+高飛）。接受「純換裝盲測基準被稀釋」代價，PR 須明講含新判定邏輯＋逐球樣本驗證
  - 07-12 執行（Opus）落地：**Part A 全 6 項**（`StatusBadge`/`Notice` 新元件、amber→token、hit/walk→`chart-theme.PA_KIND`、載入 skeleton、Eyebrow 小標）＋**Box Score 表頭中文**（ruan6047 追加，用專案 2 字語彙 打數/安打/全打/被轟…）＋**焦點①–⑩＋8K**（`[sno]/page.tsx` 稀有成就插 `nGameLevel` 之後）。`tsc`＋`build:check` 綠、games 群無數字硬色。DB 抽樣驗證：③三球關門 game84-inn5（高飛+雙殺=3球3出局，`pitch_cnt` delta 正確）、⑤⑥⑩盜壘 regex（雙盜本抓名正確）、⑧先發全員安打 2025一軍 12 場。**待辦**：視覺雙色系 375/1280 截圖驗收、焦點優先序微調（splice 12）
  - 07-12 ruan6047 令：**B1 上/下一場導覽不做，刪除**（原「零新請求」前提不成立，取鄰場需額外資料源，ROI 不足）。UX-6 範圍收斂為 換裝＋焦點擴充
  - 07-12 ruan6047 追加 6 項並落地（Opus，`tsc`＋`build:check`＋`ruff` 綠）：①**選手名連結**（Box Score/MVP/決勝/先發 包 `PlayerLink`，逐打席除外，低調 hover 樣式）②**延賽資訊移入賽事資訊卡裁判下方**（`info` dl，歷史無總覽場走 `Notice` fallback）③**計分板再見/免打局 Ｘ**（主隊獲勝末局：未打＝Ｘ、再見得分＝分數後Ｘ；「有無打」以 livelog 半局為準，scoreboard 對未打局有 phantom 0 不可信；無 livelog 不套用）④**季後賽併入月曆**（calendar API `kind ANY`：A→[A,E,C]／D→[D,F]；前端 key 補 kind_code 防撞號＋季後賽標記 台灣大賽/季後挑戰賽/二軍季後）。E=一軍挑戰賽·C=台灣大賽·F=二軍季後（已抽樣確認）
  - 07-12 ruan6047 追加 **Box Score 標籤頁重構**（規劃→核可→落地，Fable）：官網式單隊分頁（客/主/分析）新元件 `box-tabs.tsx`——單隊全寬補欄（打者 棒次/守位/季AVG＝livelog 首事件推導；投手 面對打席/好球率＝PA島/『總球數−壞球』，界內球 is_ball/is_strike 皆 f 不能數 is_strike）＋分析 tab。逐打席 chips 欄裁定不做（純數字欄）。
  - 07-12 ruan6047 二輪修正分析 tab（Fable）：**原始統計數改比率指數、砍重複圖**——(a) C1 攻擊對比 recharts 蝴蝶條（負值堆疊+LabelList 不可控）→ **手刻 `CompareRows` 對比條**（中央分軸客左主右、列內 max 正規化、粗體=較佳方含 lowBetter 反向）；指標改「box 一眼看不出」：上壘率/長打率/得點圈打擊率（livelog 打席島首事件壘況+末事件判 AB/安，附 x/y 樣本）/得分效率（得分÷上壘人次）/三振率；(b) **C2 累計得分刪除**（與 linescore 重複）；(c) **C4 球速散點刪除**（投手類型不同跨投手比速無意義）→ 改**投手效率指數卡**：好球率/首球好球率/揮空率（`揮棒落空`/`擊出` content 重建）/每打席用球/單場 WHIP；(d) C3 投手用球堆疊條保留（好球=隊色、壞球=同隊 tint）。全從 gameLive payload 客戶端推導零新請求；`tsc`＋`build:check` 綠（detail 20.2kB）
  - 07-12 ruan6047 追加**擊球落點圖**（分析 tab 投手用球右側）——**已實作 ✅**（`ruff`+`tsc`+`build:check` 綠、detail 21.7kB；DB 抽驗每場 ~45–53 點、分類分布合理 33out/9·1b/5·2b/1·3b）。實作照下列規劃：
    - 資料：後端 `/games/{sno}/live` 加 `spray` 陣列（`pitch_tracking` WHERE game + `pitch_call='InPlay'` + hit_direction/distance 非空，~60列/場；`_batted_result(content)` 分類 hr/3b/2b/1b/out）。**先把 `_batted_result` 從 `routers/tracking.py` 抬升 `api/helpers.py`** 兩 router 共用（單一事實來源）；否決「擴 tracking SELECT+前端分類」（TS 重寫分類器=雙事實來源）
    - 前端：**重用既有 `components/spray-chart.tsx` 不改**（場地/牆深/HR推牆外/Barrel★/圖例開關/theme-safe 全備）；卡內客/主 chips 切換（預設客，同 Box 一次一隊哲學；點色=BATTED_OUTCOME 結果語意色不可換隊色）；`hitter_acnt`→side 用 batting box map；`Live` type 加 `spray?`
    - 空態三層：無設備（既有虛線文案）／TrackMan 延遲（EmptyState）／單隊 0 筆
    - 改動：helpers.py＋tracking.py＋games.py＋game-board.tsx(type)＋box-tabs.tsx；P2 可選 spray-chart 加 `<title>` tooltip＋`hideLegend`
    - 驗收：2026 TrackMan 場點數=SQL 筆數、HR 牆外；375px/深色；`ruff`+`tsc`+`build:check` 綠

### UX-7 球員/球隊頁  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 頁面層）　分支：`ai/<執行者>/UX-7`
- 執行：待指派　查核：待指派（≠執行者，旗艦頁建議人審）
- 範圍/驗收：`/players/[id]`、`/teams/[code]`；旗艦頁（P1/P2 已做過一輪），對齊新語彙+補缺口。5 秒盲測（「這選手行不行」）＋雙色系截圖。
- 狀態：⏳待執行（通用層已齊，已解鎖待派工）　Commit：—
- Log：
  - 07-11 spec v5 核可後開卡

### UX-8 排行與紀錄群  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 頁面層）　分支：`ai/<執行者>/UX-8`
- 執行：待指派　查核：待指派（≠執行者）
- 範圍/驗收：`/batters`、`/pitchers`、`/records`；表格家族，一張卡統一模式（全數走 DataTable）。5 秒盲測＋雙色系截圖。
- 狀態：⏳待執行（通用層已齊，已解鎖待派工）　Commit：—
- Log：
  - 07-11 spec v5 核可後開卡

### ML-PT2 球種細分 v2（MLB 標籤遷移）  〔🔴紅線：統計/ML 正確性〕
- 需求：ruan6047（07-12，源自 PTT 文章 https://www.ptt.cc/bbs/Baseball/M.1783764883.A.6A9.html ）　規劃：Fable-5@Claude Code　分支：`ai/<執行者>/ML-PT2`
- 執行：待指派（Phase2 限 Fable）　查核：待指派（≠執行者，建議人審 repertoires）
- 背景：文章方法＝①軌跡反推位移（我們 v1 已有 `ivb_cm/hb_cm` 99.95% 覆蓋+`spin_rate`）②MLB Statcast 有標籤資料訓練模型套中職細分球種（我們 v1 只有逐投手 KMeans k=4+啟發式命名）。可取處只有②標籤遷移。
- **統計風險（必解，文章未解）**：(1) 速度域偏移——中職均速低 MLB ~8–10km/h，特徵必用「相對速度」（佔該投手速球均速比例）勿用絕對值；(2) 量測系統差 TrackMan vs Hawk-Eye——spin 用相對值或棄用、pfx 吋→cm、座標方向對齊；(3) 左投鏡像——`players.throws` 已驗證存在，訓練/推論統一鏡像；(4) 臨界球種抖動（文章實例：變速/指叉各半）。
- **架構＝cluster-then-label**（保 v1 資產）：保留 v1 逐投手 KMeans（羅戈重現/fastball agreement 94%），MLB 分類器（LightGBM/GMM）只對 **cluster 質心**命名（相對速度/IVB/HB/ext，鏡像後）→ 四縫/二縫/卡特/滑球/sweeper/曲球/變速/指叉；臨界 cluster 誠實輸出複合名（「變速/指叉」）。⚠️ v1 踩雷「固定 k=4 勿自動選 k」，v2 若放寬 k 先回查原因。
- 資料：pybaseball/Savant CSV 2023–25（~2M 球，篩掉 EP/KN 稀有種），一次性離線存 `data/`（gitignored），研究用途合規不散布。
- **驗收紅線（全贏才換）**：(a) tagged 二元 agreement ≥ v1 94%；(b) 羅戈球路重現；(c) 人工比對 5–10 名有公開球探資訊投手——**文章 6 名終結者當 free test set**（曾峻岳速球/滑球、林凱威 sweeper、鍾允華/李振昌臨界案例）；(d) `model_versions(task='pitch_type')` 落庫、v1/v2 欄並存對照，贏了才切前端。
- **執行序**：Phase1（低風險先行，⬇️Sonnet）＝D1 球員頁投手「球種位移圖」HB×IVB 散點（按球種著色+聯盟平均十字，資料全在庫不依賴 v2）＋D2 球種成績單（球種×均速/位移/轉速/使用率 vs 聯盟平均）；Phase2（🔴Fable、容器內）＝MLB 資料+特徵對齊+質心標籤器+驗收；Phase3（⬇️Haiku/Sonnet）＝全量重跑 `cpbl-classify-pitches`+前端換名。
- 狀態：✅Phase1/2/2.5＋採用 全完成（`ai/opus/UX-6` 分支）　Commit：`8288f34`＋採用 commit
- Log：
  - 07-12 ruan6047 提 PTT 文章要求研究；Fable 規劃完成（先不實作）。已驗證：`players.throws` 存在、位移特徵覆蓋 99.95%
  - 07-12 ruan6047 令執行 → **Phase1 落地 ✅**（Fable；`ruff`+`tsc`+`build:check` 綠）：後端 `/players/{id}/movement`（逐球 IVB×HB + 本人/聯盟各球種平均；**聯盟 HB 左投先鏡像右投視角再平均、回傳依本人慣用手翻回**）；前端 `MovementSection`（players 頁投手視角：HB×IVB 散點按球種著色 pitchColor+聯盟平均◆菱形+D2 成績單表 球數/使用率/均速/轉速/IVB/HB vs 聯盟，DataTable bare）。**實測命中文章觀察**：曾峻岳速球 151.6 vs 聯盟 144.7（文章「快非常多」✓）、羅戈四球種與 v1 一致、右投速球 HB 負/滑球正物理合理。**Phase2（MLB 標籤遷移，🔴Fable）未動**，照卡另開
  - 07-12 **Phase2 落地 ✅**（Fable）：`models/pitch_type_v2.py`＋migration 051（`pitch_type_pred_v2` 與 v1 並存）＋CLI `cpbl-classify-pitches-v2`。資料＝Savant pitch-movement leaderboard 2023–25（投手×球種聚合 7,225 列，免逐球 2M 下載）。**三個實測踩雷已修**：(1) Savant `break_x` 是無符號量值（R/L 四縫同號實證）→ 按球種物理方向恢復符號；(2) 加性錨移失敗（CPBL 位移為增益型偏差，羅戈滑球 delta 超出 MLB 曲球域）→ 改乘法對齊（每軸 FF 錨比值）；(3) QDA `reg_param` 在未標準化特徵上淹掉 ratio 軸（133km/h 被判四縫）→ StandardScaler 前置＋uniform priors。**驗收**：四縫口徑 94.56%＞v1 94.24% ✓；嚴格口徑（含伸卡）91.7%＜v1，但缺口=13 個伸卡群全為投手最快球（ratio 0.998）且大宗為黃子鵬（847球，下勾伸卡名家，v1 誤標變化球）→ 官方弱標籤缺陷非 v2 錯誤，證據已存 model_versions。free test set：羅戈✓ 林凱威 sweeper✓ 鍾允華✓ 曾峻岳✓ 李振昌✓ 林詩翔✓；朱承洋=v1 混群（指叉+滑球同群，質心 hb−2.1 中性）已知限制。**Phase3 前端切換未做**：gated on 需求方裁決伸卡證據是否採認
  - 07-12 ruan6047 裁決**採用 v2 為主**＋令執行 **Phase2.5 ✅**（Fable）：逐投手重分群 k=6（v2 質心命名使「多分安全」——同名子群自動合併，v1 釘 k=4 的前提失效）＋小群併最近質心；90 投手 40,467 球逐球重標。**嚴格口徑 97.1%／四縫口徑 98.0%，雙雙勝 v1 94.2%＝真·全贏**。李振昌速球拆出伸卡系（知名二縫投手✓）、林詩翔指叉拆指叉+變速、朱承洋查明為 gyro 滑球（質心 spin 2344 非指叉，文章樣本異季）。**採用落地**：`PT_EXPR` 改 v2 優先（arsenal/movement/pitch-mix/discipline/quality_by_pt 全自動切換）、game live tracking COALESCE v2、前端色票擴 8 槽（chart-7/8 深淺）＋`pitchColor` 按 top1 段對色（速球→四縫槽/變化球→faint 相容 fallback）＋`ptSort` 容納複合名排序。黃子鵬 API 抽驗=伸卡主戰✓

### UX-9 週邊群  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 頁面層）　分支：`ai/<執行者>/UX-9`
- 執行：待指派　查核：待指派（≠執行者）
- 範圍/驗收：`/matchups`、`/venues`；對齊新語彙即可，改動最小。5 秒盲測＋雙色系截圖。
- 狀態：⏳待執行（通用層已齊，本輪最後，已解鎖待派工）　Commit：—
- Log：
  - 07-11 spec v5 核可後開卡

### UX-10 三頁互動模式重設計（暫緩）  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：待各自小 spec　分支：`ai/<執行者>/UX-10-*`
- 執行：待指派　查核：待指派
- 範圍：`/projections`、`/predict`、`/umpires`——問題在**互動模型不在視覺**（predict 特徵子集探索器、projections 投影瀏覽、umpires 報告閱讀動線）。**不在本輪執行序**；屆時拆三張卡各出小 spec。本輪 UX-2/3/4 的 tokens/元件仍會套到這三頁（外觀統一），但不動互動模型。
- 狀態：📥Backlog（暫緩）　Commit：—
- Log：
  - 07-11 自 UX-1 抽出暫緩

### 開卡格式（範本）

```markdown
### <卡ID> <功能名>  〔⚪一般 或 🔴紅線：原因〕
- 需求：<誰>　規劃：<誰>　分支：`ai/<模型或工具>/<卡ID>`
- 執行：<model@tool>　查核：<model@tool 或 人審>
- 狀態：🔨執行中　Commit：—
- Log：
  - MM-DD <事件>
```

---

## 歷史

已完成／封存卡片（UI-1〜UI-5、LIVE-1、工作流建立前補記）→ [`archive/TASKS_ARCHIVE.md`](archive/TASKS_ARCHIVE.md)
