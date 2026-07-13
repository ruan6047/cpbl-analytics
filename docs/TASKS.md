# 任務看板 (Task Board)

> 進度追蹤。規則見 [`AI_WORKFLOW.md`](AI_WORKFLOW.md)。**git commit trailer 為單一事實來源**，本檔為人類可讀總覽；衝突以 git 為準。
> 狀態：`📥Backlog → ⏳待執行 → 🔨執行中 → 🔍待查核 → ✅通過 → 🏁完成`／`↩退回`
> **只留活卡**：卡片一旦 🏁完成 或 📥封存，整段移到 [`archive/TASKS_ARCHIVE.md`](archive/TASKS_ARCHIVE.md)（Ledger 列一併移），本檔保持精簡省 AI 讀取算力。

---

## Ledger 總表（活卡）

| 卡ID | 功能 | 需求 | 規劃 | 執行(model@tool) | 查核(model@tool) | 分支 | 紅線 | 狀態 |
|---|---|---|---|---|---|---|---|---|
| UX-1 | 全站頁面 UI/UX 重新設計（傘卡） | ruan6047 | Fable-5@Claude Code | —（子卡執行） | —（子卡查核） | — | ⚪ | 🔨子卡執行中（spec v5 已核可 07-11） |
| UX-5C | 首頁 hub 完整版（各頁關鍵訊息總集） | ruan6047 | 待小 spec | 待指派 | 待指派 | — | ⚪ | 📥Backlog（**壓到 UX-6〜9 完成後**重製） |
| UX-7 | 個人頁傘卡（Person Hub） | ruan6047 | Fable-5@Claude Code | —（子卡執行） | —（子卡查核） | — | ⚪ | 📋已拆 7A/7B/7C（07-12） |
| UX-7A | 球員頁換裝＋出手點＋PR 融入本季卡 | ruan6047 | Fable-5@Claude Code | Fable-5@Claude Code | Antigravity | `ai/fable/UX-7A` | ⚪ | ✅通過已 merge（`301f7f6`），待部署 |
| UX-7B | 球隊頁＋教練身分（coaches/managers） | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | ⏳待派工（吃 7A 換裝定調） |
| UX-7C | /people 命名空間（純教練/裁判個人頁） | ruan6047 | Fable-5@Claude Code | Fable-5@Claude Code | Gemini | `ai/fable/UX-7C` | ⚪ | ✅查核通過已 merge（`9c33f32`），待部署 |
| UX-8 | 排行與紀錄群 | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | ⏳待執行（通用層已齊，待派工） |
| UX-9 | 週邊群 `/matchups`、`/venues` | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | ⏳待執行（通用層已齊，待派工） |
| UX-10 | 三頁互動模式重設計 | ruan6047 | 待各自小 spec | 待指派 | 待指派 | — | ⚪ | 📥Backlog（暫緩，不在本輪序） |
| COACH-HIST | 歷年教練職務史（twbsball 經歷節） | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | ⚪ | 📥Backlog（7C 查核後可排） |
| UX-11 | 選手百分位數氣泡卡 | ruan6047 | Fable 複評 07-12 | —（併卡） | — | — | ⚪ | 🏁併入 UX-7 範圍 1（=既有三 PR 呈現整併+氣泡化，非新建） |
| UX-12 | 出手點 2D 分布圖 | ruan6047 | Fable 複評 07-12 | —（併卡） | — | — | ⚪ | 🏁併入 UX-7（位移半案 07-12 已上線，僅剩出手點） |
| ABILITY-2 | 能力值卡演算法升級（wSB/FIP/年代校正） | ruan6047 | Fable-5@Claude Code | 待指派 | 待指派 | — | 🔴 | ⏳待派工（07-13 評估採納開卡） |
| SPLITS-IP | 投手分項局數重算漏整數局（hotfix） | ruan6047 | —（bug 修復） | Fable-5@Claude Code | Antigravity | `ai/fable/SPLITS-IP` | 🔴 | ✅通過（已 merge，生產待同步） |
| ML-PT3 | 中職版球路品質指數 (CPBL Stuff+) | ruan6047 | 評估報告+Fable 勘誤 | 待指派 | 待指派 | — | 🔴 | 📥Backlog（**排 2026 季末**；勘誤見 PROPOSAL_EVALUATION.md 附錄） |
| ML-SIM1 | 互動式 H2H 對戰模擬器 v2 | ruan6047 | —（併卡） | — | — | — | 🔴 | 🏁併入 UX-10（ruan6047 07-12；predict 互動重設計一起出小 spec） |

> 「待指派」＝ruan6047尚未派工。派工後把 model@tool 補實、狀態改 🔨。
> **依賴序**：(UX-2 🏁 / UX-3 🏁 / UX-4 🏁 / UX-4.5 🏁) 通用層已齊 → UX-5〜9 頁面層（大→小）已解鎖。UX-5 已拆 **UX-5B（hub v1＋搬遷，🏁 merge `e74853b`）→ UX-5A（戰績換裝）→ UX-5C（首頁完整版，壓 UX-6〜9 之後重製）**。UX-10 暫緩。

---

## 進行中／待辦卡

### UX-1 全站頁面 UI/UX 重新設計  〔⚪（大卡：規劃後預期拆多張子卡，涉全站視覺）〕
- 需求：ruan6047（07-11）——**重新設計每個頁面的 UI/UX**。痛點：①頁面不統一 ②數據可視度不夠 ③頁面與區塊混亂；另 成績預測/賽事預測/裁判報告 三頁**操作模式與現實脫節**（抽出 UX-10 暫緩個別處理）。
- 規劃：Fable-5@Claude Code → spec 見 [`UX_REDESIGN_SPEC.md`](UX_REDESIGN_SPEC.md)（八原則＋UX-2〜9 拆卡＋深色模式決策點）
- 執行：子卡各自執行　查核：子卡各自查核（涉全站視覺，建議跨家族或人審驗收）
- 狀態：🔨 spec v5 **已核可**（07-11）；子卡進度：**UX-2/3/4/4.5/5B/5A/6 🏁完成（已 archive）**、UX-7〜9 ⏳待執行、UX-5C 📥（壓 UX-6〜9 後）、UX-10 暫緩。本傘卡隨子卡全數結案後移 archive　Commit：—
- 前置事實（規劃時必讀）：現行設計系統＝日間 Navy+白（memory `frontend-redesign`）；UI-2/3/4 完成運動風質感/微互動/響應式（`docs/archive/`）
- Log：
  - 07-11 需求開卡；派規劃 → spec 迭代 v2〜v5（痛點對應/可視度=快速理解/模組化審計/盲測定義），ruan6047 **核可 spec v5**
  - 07-11〜12 UX-2/3/4/4.5 🏁（通用層全齊）→ UX-5B/5A 🏁 → UX-6＋ML-PT2 🏁（截圖驗收＋Gemini 查核＋merge `66a5752`＋push）；詳 archive
  - 07-12 **歸檔切割修復**（Fable）：Gemini 歸檔時本卡被截斷（位元組級損毀）且 UX-6 孤兒內容殘留，已重建（archive 副本完整，無資料損失）

> **UX-5 拆卡裁示（ruan6047 07-11）**：UX-5B hub v1＋搬遷（🏁）→ UX-5A 戰績換裝（🏁）→ **UX-5C 首頁 hub 完整版**（壓 UX-6〜9 完成後重製）。hub 卡＝「指路牌」，避免與戰績頁重複。

### UX-7 個人頁傘卡（Person Hub）  〔⚪一般〕
- 需求：ruan6047（07-11 開卡；07-12 擴「球員頁→個人頁」；07-12 令拆子卡）　規劃：Fable-5@Claude Code
- **共同前提（三子卡皆讀）**：
  - 資料現實（07-12 實測）：教練 `coaches` 72 名（year/team/pos/背號；47/72 ex-player 可同名 join players）；總教練 `managers` 90 era（W/L/T/勝率/冠軍，wiki）；裁判 30 名（`game_detail` 執法＋`pitch_tracking` 好球帶）；領隊/啦啦隊無資料源（PERSON-2 backlog：person_dim/領隊/啦啦隊，先查證官網有無名單）。
  - 架構裁定：URL 甲案雙軌（有 acnt→`/players/[id]` 不動；無 acnt→`/people/[kind]/[name]`，kind=coach|umpire）；頁面模型=單頁多身分（hero 身分 chips）。
  - 橫切驗收：新端點同步 pytest EXPECTED；`ruff`+`pytest`+`tsc`+`build:check` 綠；雙色系 375/1280 截圖。
- 依賴序：**7A 先行**（換裝定調）→ **7B**（教練身分掛進球員頁，避免同檔衝突）；**7C 獨立**（新路由，可與 7A 平行）。
- 狀態：📋已拆 7A/7B/7C　Commit：—
- Log：
  - 07-11 spec v5 核可後開卡；07-12 擴需求「球員頁→個人頁」＋研究裁定（甲案雙軌/單頁多身分）；07-12 複評 PROPOSAL_EVALUATION → A/B 收編；07-12 ruan6047 令拆三子卡（量大）

### UX-7A 球員頁換裝＋出手點＋PR 融入本季卡（範圍 v3）  〔⚪一般〕
- 需求：ruan6047（07-12 校正＋07-13 補四項回饋）　規劃：Fable-5@Claude Code（v3 07-13）　分支：`ai/<執行者>/UX-7A`
- 執行：Fable-5@Claude Code（ruan6047 07-13 派工）　查核：Antigravity（ruan6047 07-13 指派）
- **範圍 v3（07-13 重規劃；取代 07-12 修訂版）**：
  1. **換裝對齊**（原範圍①不變）：`/players/[id]` 對齊新語彙＋補缺口（Eyebrow/三態/StatAbbr 名詞解釋鋪設；P1/P2 基礎上）
  2. **能力值卡雷達說明**（新）：現況只有軸名掛原生 SVG `<title>`（延遲、觸控無效、雷達面 hover 無反應）。改：①卡片標題旁 info 提示（沿 `components/tooltip.tsx`）說明**這是自製指標**——生涯 rate 的全聯盟百分位 PR（母體門檻 打者 AB≥300／投手 IP≥100）、S–G 等級純由 PR 換算、非遊戲官方數值；②軸組成（成分指標＋權重＋PR）改自訂 tooltip，hover 即顯、觸控可點（compact 對戰卡模式不動）
  3. **本季成績排版重整＋PR 融入**（新；取代 07-12 修訂版③補列案）：現況左「本季成績」tiles＋右「官方進階 · 百分位 PR」兩卡並列，且 secondary 17 顆小 tiles 過密。改：①主指標 tile 有官方 `_pr` 者（ba/obp/slg/whiffp…對映 `lib.ts ADV`）直接在 tile 內融入 PR（prColor 迷你條＋PR 數字，語彙沿 PercentileBar：數值＋PR＋長度＋定義 tooltip）；②官方 PR 柱狀圖區只留 tiles 未涵蓋的指標、去重（F3 高相關成對取一）；③secondary 計數 tiles 分組降密度。F1 紅線：**官方 `_pr` 優先，官方沒有的不自算**（要自算必標注）
  4. **球種複合名正規化：AB 標注去方向**（07-13 需求澄清後改版）：v2 臨界複合名帶方向（top1/top2），同一對球種出現兩標籤（滑球/卡特 530 球 vs 卡特/滑球 349 球等 5 組方向對），全域標籤 24 種過多。改：後端 `tracking.py` `PT_EXPR` 輸出層把複合名**正規化為固定順序單一標注**（成分照 `PT_ORDER` 排序，如一律「卡特/滑球」），比照指叉變速/滑曲球既有正名精神；「較偏哪個」的方向資訊移 tooltip（或捨棄，執行時定）；DB `pitch_type_pred_v2` **不動**（可逆）；前端 `PITCH_ALIAS`/色票補複合名→成分第一球種色。**否決「併入最相近球種」**：posterior<0.55 硬拗單一球種違反 v2「寧粗勿錯」誠實原則，且會污染單名球種的均速/位移統計。預期全域 24→19 標籤；跨家族小樣本複合群（n<100 或僅 1 投手，如 曲球/指叉 48 球）若仍嫌雜，執行時可個案評估收斂，但預設保留
  5. **進壘熱區區塊改名＋指標分角色**（新）：「進壘熱區 × 打擊成績」對投手語意錯置（是**被**打擊）且指標投打共用。改：①標題分角色——打者「好球帶熱區 · 打擊表現」、投手「進壘位置 · 壓制表現」（文案執行時微調，投手側禁再現「打擊成績」）；②投手指標重選：投球分佈%（各格佔比，看配球位置）＋揮空率＋被安打率＋被強擊球%，**刪「擊球仰角 AVG」**（對投手無讀法）；打者維持 ev/ba/hard/whiff，la 是否保留執行時看版面
  6. **出手點 2D**（原範圍③不變）：`rel_side`×`rel_height`（m；覆蓋 99.96%）散點 by 球種＋質心＋出手一致性；掛 MovementSection 旁、movement 端點擴欄；左投鏡像沿慣例；修 F4（1280 三欄擠爆→兩欄或上下堆疊）、F5（一致性用 cm、樣本過小顯「—」）
- 驗收：5 秒盲測＋雙色系 375/1280 截圖；PR 融入後無重複呈現；球種合併抽 1–2 名有卡特的投手驗 usage 加總與各視圖一致；投打各截一張熱區區塊；橫切驗收見傘卡
- 狀態：✅通過已 merge（`301f7f6`，trailers 完整），待部署　Commit：`301f7f6`
- **需求校正（ruan6047 07-12，仍有效）**：**氣泡方案正式否決**——PercentileBar 柱狀圖一列同時呈現「數值＋PR＋長度視覺＋定義 tooltip」，氣泡只剩 PR 圓圈＝資訊變少。**PR 呈現以官方 PR 柱狀圖語彙為準**。提案 A（原 UX-11）氣泡化結案否決；v3 範圍 3 的「融入」是把柱狀圖語彙帶進 tile，不是氣泡復活。
- **重做參考（Fable 審核 findings，07-12；避免二輪重蹈）**：
  - F1（高·雙重事實源）：卡片要求「官方 PR 收進氣泡」，首輪把官方 PR 區移除後**全部自算 PR**——但 `advanced_stats` 有 9 個官方 `_pr` 欄、`batting_current.ops_plus` 官方欄也存在（trend.py 另有滾動版=第三套）。同指標會與官方數字不一致。重做：氣泡直接用官方 `_pr`，官方沒有的才自算並標注
  - F2（高·誠實）：雷達被寫死 `selectAbility(..., "career")` 但旁邊本季/生涯 toggle 仍在且亮「本季」——標示與內容不符。固定生涯就同步改 toggle 語意
  - F3（中）：高相關指標成對佔位（截圖實證 ERA+ 92 與防禦率 92 同 PR）——每對取一
  - F4（中·版面）：位移/出手點/成績單 3 欄 grid 在 1280 擠爆，表格「放球點/一致性」欄被裁切
  - F5（低）：「已鏡像鏡像」typo；一致性建議 cm；單球群 variance null→coalesce 0 顯示 0.000 誤導，樣本過小應顯「—」
  - 好的部分可沿用：樣本門檻+未達門檻標注/骨架屏/出手點+一致性照卡實作/整併方向正確（氣泡視覺除外，已否決）
  - 流程：首輪未 commit 未推送即交審（§3.1 交接驗證未過）——二輪務必收尾再交
- Log：
  - 07-12 首輪還原＋需求校正（氣泡否決）；07-13 ruan6047 補四項回饋（雷達無說明/本季成績排版+PR 融入/球種標籤/熱區區塊名稱與指標）→ Fable 重規劃範圍 v3
  - 07-13 範圍 4 需求澄清：非「卡特併滑球」，是複合名方向重複（A/B vs B/A）造成標籤過多 → Fable 以實際分布評估（24 標籤、5 組方向對、單投手雙向僅 1 例），採 ruan6047 傾向的 AB 固定標注案、否決併入單一球種案（違反寧粗勿錯）
  - 07-13 雷達演算法優化另拆 ABILITY-2（wSB/FIP/年代校正；7A 只動雷達說明 tooltip 不動演算法）
  - 07-13 Fable 執行完畢（worktree `../cpbl-analytics-ux-7a`，5 commits）：
    - api×2：PT_EXPR 複合名正規化（實測 24→19 標籤、黃子鵬 滑球/橫掃 雙向 98+135 合併 233 ✓）；movement 擴 release（rel_side 實測 右投+0.56/左投-0.55→＋＝臂側統一、跨球種一致性加權 RMS、n<10 spread 誠實缺席、<2 穩定球種一致性顯「—」）
    - web×3：雷達 ? 方法論+軸組成自訂 tooltip（順修 ability.py「擊球initial速」typo）；本季 tile 融官方 PR（打者三圍條、投手無官方 _pr 不自算、右卡去重+brl 刪除、secondary 改表列）；熱區分角色（投手 投球分佈%/揮空/被安/被強擊，usage 格 13 區均勻基準+總數<30 不上色）+出手點卡（上下堆疊修 F4）+A/B 臨界球路標注+Skeleton 三態+OPS+/ERA+/K9 StatAbbr
    - 驗證：ruff ✓ pytest 20 ✓ tsc ✓ build:check ✓；截圖 王柏融（打者）/黃子鵬（投手，側投出手高 0.75–0.84m 合理）×深淺色×1280/375 無溢出；tooltip hover/點擊實測
  - 07-13 追加（ruan6047 回饋×2，待查核分支上補 commit）：①投手特色軸 info 說明＋打者 DH 指打說明（`907f040`；並評估出武器軸 ~50 下限統計缺陷 → ABILITY-2 範圍 6）②配球傾向改共用堆疊比例條（取代各卡自畫用量條；gap-px 段界解同色槽複合名相鄰不可分），截圖驗證 ✓
  - 07-13 收尾四項（Fable 盤點→ruan6047 圈選全做）：A 球種鏡頭 ≥20 球門檻（打者 19→10 顆按鈕）；B 散點複合名近空心（同色槽可分）；C PR 卡 Skeleton＋PercentileBar 定義換共用 Tooltip；D 配球傾向重排版（卡牆→明細表×依球數情境並排，一卡收完）。tsc/build 綠、截圖驗證 ✓
  - 07-13 **雷達刻度 bug 修復**（ruan6047 抓到：羅戈續航 78/B 畫到滿格）：未設 PolarRadiusAxis → recharts 半徑自動縮放到本人最大軸值，圖形「相對自己」vs 等級「絕對 PR」錯位；生涯卡看似正常純因最大值近 100。單人卡+對戰疊圖皆釘 domain=[0,100]（`c463c62`），羅戈頁截圖驗證 ✓
  - 07-13 Antigravity 審核通過：
    - Python/FastAPI 測試（ruff + pytest）與 Web/Next.js 靜態編譯型別檢查（tsc --noEmit + build:check）全數綠燈通過。
    - 對照 v3 範圍逐一實測：自訂雷達說明與軸 tooltip 觸控靈敏、本季 stat tile 成績完美融入官方 PR 條、複合名按優先序正規化合併並去方向、出手點 2D 鏡像及加權 RMS 一致性正確（低樣本時顯「—」）、好球帶分角色熱區指標與雙色窄幅布局無溢出。已完成驗證。

### SPLITS-IP 投手分項局數重算漏整數局（hotfix）  〔🔴資料正確性〕
- 需求：ruan6047（07-13「鋼龍對戰各隊局數怪怪的：全季 80 局、各隊加總不到一局」）　分支：`ai/fable/SPLITS-IP`（worktree `../cpbl-analytics-splitsfix`）
- 執行：Fable-5@Claude Code　查核：Antigravity（🔴 資料正確性建議跨家族或人審＋實測）
- **Root cause**：`splits_calc.calc_pitching_t1` 的 SQL 只取 `pg.inning_pitched_div3`（餘出局 0–2），漏了整數局 `inning_pitched_cnt`，而下游把 Counter 累加值當「總出局數」拆欄——投手 T1 全家族（主客/先發後援/月份/球場/vs各隊）局數只剩零頭，ERA/WHIP 連帶全錯；生涯 9999＝base＋本季合成也被污染。**Phase 1 上線起即存在**（生產同錯）。打者側無 IP 欄不受影響；harness 對照（run_verify_splits）為何沒抓到 → 查核時順帶確認（疑 harness 未比 IP 欄）
- **修復**：SQL 改 `(inning_pitched_cnt*3 + inning_pitched_div3) AS ip_outs`（一行）＋docstring 明定「Counter 內 IP＝總出局數」慣例；`cpbl-build-splits 2026` 重建 A/D＋生涯合成
- **驗證（本機已過）**：黃子鵬 vs 味全 1⅓→34⅓ 局（ERA 20.25→0.79）；全聯盟 92 名投手（IP≥10）vs-team 加總 vs 官方全季 **0 誤差**；生涯 9999 主+客=923 局≈官方生涯總和；ruff+pytest 20 綠
- **待辦**：merge 後生產要 ①部署新碼 ②照 Runbook §3 同步重跑生產 `cpbl-build-splits 2026`（derived 表，本機重建不自動到生產）
- 狀態：✅通過　Commit：分支 `ai/fable/SPLITS-IP`

### UX-7B 球隊頁＋教練身分  〔⚪一般〕
- 需求：ruan6047　規劃：Fable-5@Claude Code　分支：`ai/<執行者>/UX-7B`
- 執行：待指派（Sonnet 可：守門規則已明確）　查核：待指派（≠執行者）
- 範圍：
  1. `/teams/[code]` 換裝＋**教練團名單**（coaches by team：職務/背號；ex-player 連 `/players/[id]`、純教練連 `/people/coach/[name]`——7C 未上線前純教練暫不連結）＋**總教練歷代 era 卡**（managers：任期/W-L-T/勝率/冠軍）
  2. 球員頁**教練身分區塊**＋hero 身分 chips（球員｜教練｜總教練）：coaches 同名 join（歷年職務/隊/背號）＋managers era 戰績卡。**同名歧義守門（紅線）**：coach 名對到多個 player acnt → 不自動掛、記 needs_review，嚴禁腦補
- 依賴：7A merge 後開工（同檔 `/players/[id]`，避免衝突）
- 驗收：同名守門有測試（構造同名 fixture）；教練團/era 卡雙色系截圖；橫切驗收見傘卡
- 狀態：⏳待派工　Commit：—

### UX-7C /people 命名空間（純教練/裁判個人頁）  〔⚪一般〕
- 需求：ruan6047　規劃：Fable-5@Claude Code　分支：`ai/<執行者>/UX-7C`
- 執行：待指派（建議 Opus：新命名空間+新端點）　查核：待指派（≠執行者）
- 範圍：
  1. 路由 `/people/[kind]/[name]`（kind=coach|umpire；中文名 URL-encode，同名以 kind 隔離，規模 25+30 可控；不建 person_dim）
  2. `/people/coach/[name]`：25 名非球員教練——職務史（coaches 歷年）＋若有 managers 戰績卡
  3. `/people/umpire/[name]`：裁判個人頁——執法場次、好球帶判定個人報告（自 umpires router 抽 per-name 查詢）、近期執法場列表（連 games）；順帶解 UX-10 裁判動線問題的一半。**樣本誠實**：執法場次少的裁判判定傾向顯示須帶樣本數（比照 TrackMan 覆蓋慣例）
  4. 新端點（如 `/api/v1/people/umpire/{name}`）入 pytest EXPECTED
- 依賴：無（新路由獨立，可與 7A 平行；7B 的純教練連結等本卡上線後補）
- 驗收：5 秒盲測「這主審好球帶偏不偏」；同名 kind 隔離驗證；橫切驗收見傘卡
- 狀態：✅Gemini 查核通過、已 merge `9c33f32`，待部署　Commit：分支 `ai/fable/UX-7C` 已推送；worktree `../cpbl-analytics-7c`（環境現成，審核可照 §3.1 進駐）
- Log：
  - 07-12 Fable 執行（worktree 首例）：people router 雙端點（教練=coaches+managers、同名唯一才回連球員頁；裁判=崗位場次+記分卡沿 umpires 常數+近期場）＋前端 /people/[kind]/[name]＋/umpires 名字連結入口。pytest 20 passed（EXPECTED 54→56）/ruff/tsc/build 綠；實資料抽驗 葉君璋/平野惠一/蔡豐澤、375 無溢出

### UX-8 排行與紀錄群  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 頁面層）　分支：`ai/<執行者>/UX-8`
- 執行：待指派　查核：待指派（≠執行者）
- 範圍/驗收：`/batters`、`/pitchers`、`/records`；表格家族，一張卡統一模式（全數走 DataTable）。5 秒盲測＋雙色系截圖。
- 狀態：⏳待執行（通用層已齊，已解鎖待派工）　Commit：—
- Log：
  - 07-11 spec v5 核可後開卡



### UX-9 週邊群  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：Fable-5@Claude Code（spec §B 頁面層）　分支：`ai/<執行者>/UX-9`
- 執行：待指派　查核：待指派（≠執行者）
- 範圍/驗收：`/matchups`、`/venues`；對齊新語彙即可，改動最小。5 秒盲測＋雙色系截圖。
- 狀態：⏳待執行（通用層已齊，本輪最後，已解鎖待派工）　Commit：—
- Log：
  - 07-11 spec v5 核可後開卡

### ABILITY-2 能力值卡演算法升級（wSB/FIP/年代校正）  〔🔴紅線：統計正確性〕
- 需求：ruan6047（07-13「雷達圖製作時數據較少，評估優化」→ 採納 Fable 評估開卡）　規劃：Fable-5@Claude Code　分支：`ai/<執行者>/ABILITY-2`
- 執行：待指派（建議 Opus 實作）　查核：待指派（🔴 年代校正屬統計紅線，查核建議 Fable 或人審）
- 範圍（全在 `api/routers/ability.py` 的 SQL 與 `_COMPOSITE`，無 schema 變更）：
  1. **速度軸融入 wSB**：現行 `(SB+3B)/G` 太粗（三壘打摻長打/球場因素、盜壘不計成功率）。組成改 `[wSB rate（wsb/opp）0.6, (SB+3B)/G 0.4]`；`batter_wsb` 1990+ 全覆蓋，生涯/本季皆適用
  2. **壓制軸摻 FIP**：ERA 含守備與運氣。組成改 `[ERA 0.5, FIP 0.5]`；FIP 全史自算（HR/BB/SO/IP 齊，HBP 缺值年代容 0 沿 ingest 慣例），FIP 常數逐年聯盟校準（與 3 同一套聯盟均值 CTE）
  3. **年代校正 [era adjustment]**（🔴 本卡核心）：現行生涯 PR 把 1990 至今原始 rate 直接 `percent_rank`，跨年代系統性偏差（三振率逐年代升→老球員 contact PR 灌水；打高投低年代投手 ERA PR 被壓）。改：各 rate 先除以**該年聯盟均值**、按 PA/IP 加權彙總成 era-relative rate，再進 PR
  4. **本季投手武器軸摻官方 `whiffp_pr`**（誘揮空，官方欄現閒置；若採 6 主案併入固定三振軸）
  5. **捕手守備本季摻 `catcher_runs` RA9**（2018+，**僅本季 scope**）
  6. **投手特色軸（武器）統計修正**（07-13 追加，ruan6047 詢問後 Fable 評估）：
     - W1（🔴 刻度失真）：`GREATEST(k_pr, gb_pr, fb_pr)` 有數學下限——gb=GO/AO 與 fb=AO/GO 互為倒數，percent_rank 互補（gb_pr≈1−fb_pr）→ max 必 ≥~50。**2026 實測 61 名合格投手：最低 51.7、平均 80.5、無人 <50**，半個刻度永不使用、人人 A/S 級武器，鑑別度砍半
     - W2（語意）：飛球特化不必然是武器（被轟風險），風格≠能力，卻與三振（真技能）同軸計分
     - W3（既存 bug）：`AbilityRadarVS` 疊圖以主投軸名標軸、客投按 index 對位——兩投手 weapon_type 不同時，同一軸比較的是不同指標
     - **主案（建議）**：武器軸改固定「三振」軸（k_pr，季 scope 摻 whiffp_pr）——真技能、跨投手可比、VS 疊圖語意自然一致；滾地/飛球風格保留於 hero「XX型」signature 徽章＋info 說明（7A 已補），風格資訊不遺失。overall 重排受影響 → 照本卡回歸抽驗
     - 過渡：7A 已在 info/軸 tooltip 標注「特化程度非絕對優劣」（分支 `907f040`），修正前先誠實揭露
- **紅線約束**：2018+/2026-only 數據（RE24/livelog 好球率/TrackMan 衍生）**禁入生涯 PR 母體**——同池不同人組成不同即失去可比性；RE24/WPA 屬情境價值不進雷達（留 sabr 區塊）；OAA/framing 維持不做
- 驗收：改前後抽 5–10 名**跨年代**球員（含 90 年代、2016 打高投低、現役）PR 位移對照表人工判讀；`ruff`+`pytest`；前端 axisTitle tooltip 自動吃 components 標籤應零改動，7A 的 info 說明文案若已上需同步組成描述
- 依賴：與 UX-7A 平行可（7A 動前端 tooltip/版面、本卡動後端 ability.py，不同檔不衝突；先後皆可）
- 狀態：⏳待派工　Commit：—
- Log：
  - 07-13 ruan6047 提問「雷達圖數據較少時做的，有無優化方案」→ Fable 盤點庫內既有數據（batter_wsb 1990+/batter_re24 2018+/catcher_runs 2018+/livelog is_strike）出評估，ruan6047 裁定依建議開卡

### COACH-HIST 歷年教練職務史（twbsball 經歷節）  〔⚪一般〕
- 需求：ruan6047（07-12「教練從其他管道拿歷年教練團？」）　規劃：Fable-5@Claude Code　分支：`ai/<執行者>/COACH-HIST`
- 執行：待指派（Sonnet 可＋抽樣人驗；解析規則已列）　查核：待指派（≠執行者）
- **管道查證（07-12 實測）**：twbsball **無**逐年球隊條目（`2015年中信兄弟` 不存在，allpages 驗證）→ 改**人物中心**：個人條目「經歷」節有結構化教練職務＋精確起訖（林威助實測：`:*[[中華職棒]][[中信兄弟隊]][[總教練]]（[[2020年]]12月07日～[[2023年]]05月10日）`）。存取沿 `cpbl_overseas.py` 的 query API 模式（`action=query&prop=revisions`，UA+退避，無 Anubis 問題已驗證）。
- 範圍：
  1. 種子名單＝現任 coaches 72＋managers 90（去重）；爬個人條目經歷節（~150 頁，一次抓+手動刷新，照 wiki-data-sources 慣例）
  2. 解析教練職務行 → 新表 `coach_history(name, team_code, pos, from_date, to_date, source, needs_review)`（migration 冪等）
  3. **解析守則（不腦補）**：行格式變異（兼任/代理/客座 前綴保留進 pos）；日期粒度不一（年/年月/年月日，缺月日存年初/年末界）；隊名歷代對映 team_dim（兄弟象→中信兄弟等，對不上→needs_review）；**非職棒職務**（學校/業餘/國家隊）過濾出主表或另欄標注；解析失敗行一律 needs_review 人工檢
  4. 前端：7C 教練頁「教練職務」表改吃 coach_history（歷年時間軸）；7B 球員頁教練身分區塊同源
- 驗收：抽 10 名教練對照 twbsball 原頁人工核對；needs_review 比率報告；`ruff`+`pytest` 綠
- 依賴：7C merge 後（前端接點在 7C 的頁）
- 狀態：📥Backlog（ruan6047 07-12 裁定 a 案：先排 backlog，不疊進 7C 送審）　Commit：—
- Log：
  - 07-12 需求＋管道查證＋開卡（Fable）；twbsball 逐年球隊條目假設被否、人物中心路線實測可行

### UX-10 三頁互動模式重設計（暫緩）  〔⚪一般〕
- 需求：ruan6047（07-11）　規劃：待各自小 spec　分支：`ai/<執行者>/UX-10-*`
- 執行：待指派　查核：待指派
- 範圍：`/projections`、`/predict`、`/umpires`——問題在**互動模型不在視覺**（predict 特徵子集探索器、projections 投影瀏覽、umpires 報告閱讀動線）。**不在本輪執行序**；屆時拆三張卡各出小 spec。本輪 UX-2/3/4 的 tokens/元件仍會套到這三頁（外觀統一），但不動互動模型。
- **併入 ML-SIM1**（ruan6047 07-12）：H2H 對戰模擬器 v2（PROPOSAL_EVALUATION D 案）併進 predict 小 spec 一起規劃——蒙特卡羅/馬可夫打席模擬（pitch mix×打者對球種決策），🔴 紅線：輸出必附基準對照+不確定性（承賽果預測準則）、預計算用物化表非 Redis、禁裝飾動畫；umpires 部分注意 UX-7C 已先解掉裁判個人頁那半。
- 狀態：📥Backlog（暫緩）　Commit：—
- Log：
  - 07-11 自 UX-1 抽出暫緩

### UX-11 選手百分位數氣泡卡 (Percentile Player Cards)  〔⚪一般〕
- 需求：ruan6047（07-12）　規劃：Fable-5@Claude Code（見 PROPOSAL_EVALUATION.md）　分支：`ai/<執行者>/UX-11`
- 執行：待指派　查核：待指派
- 範圍/驗收：選手個人頁頂部百分位數（PR 0–99）紅藍氣泡指標卡。
- 狀態：📥Backlog（見 PROPOSAL_EVALUATION.md）　Commit：—
- Log：
  - 07-12 評估報告已完成

### UX-12 出手點與球路軌跡 2D 分布圖 (Release/Movement)  〔⚪一般〕
- 需求：ruan6047（07-12）　規劃：Fable-5@Claude Code（見 PROPOSAL_EVALUATION.md）　分支：`ai/<執行者>/UX-12`
- 執行：待指派　查核：待指派
- 範圍/驗收：選手頁 Release Point 2D 散點與信心區間圖（含 X/Y 坐標與左右手鏡像）。
- 狀態：📥Backlog（見 PROPOSAL_EVALUATION.md）　Commit：—
- Log：
  - 07-12 評估報告已完成

### ML-PT3 中職版球路品質指數 (CPBL Stuff+ Index)  〔🔴紅線：ML/統計正確性〕
- 需求：ruan6047（07-12）　規劃：Fable-5@Claude Code（見 PROPOSAL_EVALUATION.md）　分支：`ai/<執行者>/ML-PT3`
- 執行：待指派　查核：待指派
- 範圍/驗收：Stuff+ 隨機森林/LightGBM 模型研發與物理評分整合。
- 狀態：📥Backlog（見 PROPOSAL_EVALUATION.md）　Commit：—
- Log：
  - 07-12 評估報告已完成

### ML-SIM1 互動式 H2H 對戰模擬器 v2  〔🔴紅線：統計正確性〕
- 需求：ruan6047（07-12）　規劃：Fable-5@Claude Code（見 PROPOSAL_EVALUATION.md）　分支：`ai/<執行者>/ML-SIM1`
- 執行：待指派　查核：待指派
- 範圍/驗收：雙欄投打選取器，結合配球與揮空/選球熱熱圖，模擬對戰概率分布。
- 狀態：📥Backlog（見 PROPOSAL_EVALUATION.md）　Commit：—
- Log：
  - 07-12 評估報告已完成

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
