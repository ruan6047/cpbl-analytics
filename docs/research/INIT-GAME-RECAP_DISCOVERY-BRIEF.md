# Discovery Brief — INIT-GAME-RECAP（單場賽況頁三態體驗）

> 2026-08-06 需求方同步 grilling 定案（Q1–Q8）。本 Initiative 由「隔日復盤」重定義為
> **單場賽況頁三態體驗（賽前／賽中／賽後）**，recap 為賽後態的主區塊。

## 問題與情境

- 使用者／利害關係人：**第一用戶＝需求方本人**；次要＝回顧型球迷。
- 觸發情境與現行流程：昨晚沒看比賽 → 早上看官網文字戰報＋自己翻 box score 拼湊勝負原因；
  單場頁（`games/[sno]`）現況＝進行中態最完整（ESPN 板）、完賽態僅雛形（decisions／
  highlights／MVP 幾塊散落於 721 行單一元件）、**賽前態幾乎空白**。
- 痛點與影響：單場頁是核心功能之一，但三態體驗不完整也不一致；賽後「為什麼輸贏」
  的因果鏈無處可看（賽況頁是時間軸流水帳，非因果敘事）。

## 目標與邊界

- 目標結果：**三分鐘內重建單場勝負因果鏈**（賽後態）；單場頁三態各有完整且一致的體驗。
- 成功條件：交付當下需求方人工驗收（既有 UX「先人工審再交查核」流程）；不設數字指標
  （第一用戶即需求方，行為判準自明）。**停損斷路器**：每張後續子卡開卡前必答
  「上一張的產出你自己有在用嗎」，答不出來不開卡。
- 非目標：
  - 編輯資料管道（人工敘事／標注）——用了之後真想要再獨立提案，不預設掛點。
  - WPA 排序（既有禁令：WP 校準 No-Go，見 sabr 記憶錨點）。
  - recap 區塊重複內嵌 WP 曲線（曲線在同頁下方既有位置保留）。
  - 賽中即時 recap（進行中態＝現行 ESPN 板，不動）。
  - 多場總覽 digest 於單場頁（歸首頁狀態列）；季後賽專頁（另案）。
  - 球迷暱稱於 recap 正式文案（暱稱僅限賽況頁焦點區既有用法）。

### 三態設計原則（Q8 定案）：恆定骨架＋主區塊置換

| 區位 | 賽前 | 賽中 | 賽後 |
|---|---|---|---|
| 頂部記分條（恆定） | 隊徽＋先發投手＋開賽時間 | live 比分＋局數壘況 | 終場比分＋致勝方式 |
| 主區塊（置換） | 對戰卡（先發近況／兩隊近十場／勝率預測） | ESPN 板（現行不動） | **recap 五塊** |
| 恆定尾部 | 預告資訊 | box tabs／逐球 | box tabs／WP 曲線／逐球（下移保留） |

recap 五塊：①結論行（比分＋致勝方式＋一句事實句）②關鍵打席 3–5（|ΔRE24| 選取、
時間序呈現、帶局面脈絡）③得分半局事實鏈 ④兩隊表現行（吸收既有 decisions／highlights／
MVP 雛形）⑤跳入點（探索器／逐球）。

### 架構定案

- **全即時算、每日鏈零改動**（G4 凍結不受影響）：PA 序列 × `run_expectancy` 矩陣查表
  算逐打席 ΔRE24（單場 ~70–80 打席，毫秒級）＋ game_detail（致勝方式）＋ gamelog
  （MVP／投手線）；前端 ISR／快取，歷史場次快取永久有效。
- 完賽判定＝`cpbl.completion.is_completed_game`（REMEDY1 canonical helper 首個新消費者）。
- **單一底層服務「單場打席事實流」**（每打席＝局面狀態＋結果＋ΔRE24）：live 態
  Recent Plays、賽後態 recap、#79 探索器**三消費者共用**，不各自重建打席邏輯
  （前科：leaders 自建勝敗序列與 special_records 分歧）。live 頁換底不換臉、行為不變
  為驗收條件。
- 歷史覆蓋隨 livelog 免費（A 軍 2018+），主要服務面＝當季。
- **雙源打席事實流（2026-08-06 需求方修訂）**：官方來源當晚即全有，延遲純屬
  我方爬取排程——服務取數雙源：**DB livelog＝權威源**；該場未入庫時退
  **live worker final snapshot＝當晚後備源**（worker 整場輪詢、終場即握完整
  livelog；ΔRE24 只需打席結果不需 TrackMan）。效果＝**當晚賽後即完整 recap**，
  隔日官方資料入庫自動切回權威源（「隔日確認異動」因即時算而免費）。零新
  DB writer、零鏈改動＝G4 凍結無涉。原分級渲染降級為極端 fallback（snapshot
  亦缺才簡版）。相關卡 #73／#57＝相關非阻塞。

### 子卡與 wave（實作分波、設計一次過）

1. **#80（Wave 1，重定義）**：單場頁三態體驗——**一次設計**（Design Gate 過三態，
   結構規格依 `docs/design/UI_UX_SYSTEM.md`，先人工審）＋**完賽態實作**（底層打席
   事實流服務＋live Recent Plays 換底＋recap 五塊）。
2. **#81（Wave 1.5，併入本 Initiative）**：首頁賽事狀態列**雙態**（比賽中 live 列／
   平時昨日戰果列，每場一行消費 #80 結論 API）。
3. **賽前態（Wave 2，屆時開小卡）**：對戰卡主區塊（消費既有 matchup／outcome API）。
4. **#79（Wave 3）**：逐打席探索器，自 recap 關鍵打席連入，同底層服務。

歸屬邊界：#81 自 INIT-PRODUCT-UX 移入本 Initiative（重定義須保留 07-17 藍圖
「首頁點機率＋1 訊號」呈現決議）；單場頁範圍歸本 Initiative、全站系統性 UI 收斂
歸 INIT-PRODUCT-UX（#62），互不雙重認領。#54（LIVE 暫態逐球校正）正交無涉。

## 證據與假設

- 已知證據：`games/[sno]/game-live-page.tsx`（721 行）已含 `completed` 分支與雛形區塊；
  livelog 2026 全覆蓋（A 2018+）；`run_expectancy` 矩陣（REBAS 外驗）；game_detail
  致勝方式／MVP 欄既有；matchup／outcome API 既有；07-27 產品盤點定案 recap 脊柱
  ΔRE24 事實優先、禁 WPA 排序。
- 待驗證假設（#80 執行首步 spike）：
  1. 逐打席 ΔRE24 即時算正確性——同場加總對照 batter_re24 季彙總抽驗可吻合；
  2. 「一句事實句」模板生成可讀性——模板＋事實槽，人工審把關；
  3. 首頁 live 態沿用既有端點即足；
  4. 「後續成本低」前提成立與否繫於全即時算架構（已定案，spike 驗效能）；
  5. **live worker final snapshot 的 livelog 完整性**（含末打席、無截斷）——spike
     首步驗，不成立則退回分級渲染。已查實：TTL 48h（config:35，留存窗足）、
     snapshot 已保留 winning_pitcher／mvp（live_game_worker.py:352–355）；
     致勝方式同源 CurtGameDetailJson，snapshot 未留則補一行保留（worker 非凍結檔）；
  6. **canonical PA 切界核心可否 library 化跑在 snapshot 資料上**——能＝當晚與隔日
     零分歧；不能＝當晚版掛「暫定」標記（隔日權威源自動除），輕量切界嚴禁重刻
     幽靈島／末球錨定／9.15(b) 全套語意（那是 PA builder 的地雷區）。

### 端到端檢視補充（2026-08-06 全流程走查）

- **權威源路徑必吃 canonical PA 表**，不得從 raw livelog 重刻切界。
- **完賽觸發雙層**：頁面層＝snapshot.phase=final（當晚）；資料層＝is_completed_game
  （隔日）——現行 canShowPostgameConclusions 模式形式化進 spec。
- **二軍無 live worker**：D 卡 recap 僅隔日權威源，明寫預期。
- **保留賽**：final 不觸發、日期界線本就排除——沿現行顯示，設計注記。
- **快取切換**：暫定（短快取）→權威（長快取／ISR）revalidate 機制進 spec。

### 官方系統異常韌性（2026-08-06 需求方提問補查）

- 架構天生降級：隔日爬蟲失敗→snapshot 源續撐（TTL 48h）、冪等補爬自動切換；
  官方更正／改判→即時算零工序吸收；Redis 掛→live_cache 既有 DB 退化（當晚無
  recap＝降級非錯誤）。
- **當晚 mini 對帳閘門（新增，進 #80 spec）**：snapshot 屬 LIVE 暫態（#54 領域），
  暫定 recap 出手前驗內部一致性（livelog 推導比分＝snapshot 比分、打席數 vs box
  合理）——不過即不出暫定版、退簡版，fail-closed。
- **final 永不到殘局（新增）**：live API 中斷致 phase 卡 live——頁面停 stale live 態
  等隔日權威源；**嚴禁時間推斷硬切完賽**（present_status 教訓：狀態欄不得單獨
  當完成證據，REMEDY1 判準紅線同源）。
- 研究計畫：—（假設驗證併入 #80 執行首步）
- 驗證方法：需求方人工驗收（每 wave 交付）＋跨家族查核。
- 對抗式質詢：**2026-08-06 同步 grilling 真對話（Q1–Q8）已完成**。被推翻的前提：
  「recap＝新頁面」（改為賽況頁完賽態）、「數字化成功指標」（撤，改人工驗收＋
  斷路器）、「多場總覽入圈」（出圈歸首頁）；存活的擴充：三態一次設計（需求方
  主動擴圈）、#81 併入、單一底層服務（需求方點出同源）。
- 前提實查（T2+）：單場頁現況＝實讀 `game-live-page.tsx`（`completed` 分支行號
  191–556）；路由無獨立 live 頁＝實查 `web/src/app/games/`；RE 矩陣表＝
  `cpbl.run_expectancy`（migrations 既有）；完賽 helper＝`cpbl/completion.py`
  （main `0f05b92`+）。基準＝origin/main `ced3a2f`+。

## 決策

- 需求方確認：ruan6047／2026-08-06／同步 grilling 對話（本 session）＋Issue #60 留言。
- 結論：**進規劃**——#80 依本 brief 重定義後派工（設計先行、人工審後實作）。
