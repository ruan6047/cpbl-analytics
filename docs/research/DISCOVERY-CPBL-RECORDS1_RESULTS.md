# DISCOVERY-CPBL-RECORDS1 主站紀錄資料價值與穩定鍵 Discovery 結果

> 稽核日期：2026-07-24（Asia/Taipei，白天 11:24–12:10）<br>
> 範圍：`www.cpbl.com.tw` 六個未爬頁面（`/stats/hr`、`/standings/history`、`/standings/special`、
> `/stats/toplist`、`/teamhistory`、`/stats/mvp`）。<br>
> 性質：唯讀 Discovery；單一 Playwright session、白天、低頻（6 次 GET + 10 次 POST，
> 全程 <10 分鐘），未寫入官網、本機或 production DB。spec 基線：
> [`OFFICIAL_DATA_GAP1_RESULTS.md`](OFFICIAL_DATA_GAP1_RESULTS.md) §3.6。

## 1. 結論

逐頁 Go/No-Go（詳見 §3）：

| 路由 | 決策 | 一行理由 |
|---|---|---|
| `/stats/hr` | **GO**（後續可開 ingest 卡） | 逐轟事件級資料；穩定鍵可重跑（跨年/同場多轟/改名/季後賽四項抽查全過），且 `HomeRunType`（場內/首打席/代打/再見/滿貫）與 `Citizenship` 是既有資料沒有的新維度 |
| `/standings/history` | GO（canonicalization oracle，非新爬蟲） | 歷年戰績含上下半季/H2H/主客場，與 opendata／`cpbl_standings` 重算結果對帳，不建第三份 public truth |
| `/standings/special` | GO（regression oracle，非新爬蟲） | 內容是隊級條件戰績（紅土/草皮/先得分/先被得分/一分差/延長賽），可驗證自算特殊戰績；**修正 spec 基線**：非「連勝/單月」個人紀錄 |
| `/stats/toplist` | **NO-GO（修正）** | **修正 spec 基線**：實測是當季 top-5 快照（h3「2026年 單項排行榜」），非生涯累計；深度低於既有 `/season/*-leaders`，純重複 |
| `/teamhistory` | GO（一次性校驗，非新爬蟲） | 純 SSR 無 AJAX，單次 GET 即可校驗 `team_dim` 硬編歷史，無需 token/POST |
| `/stats/mvp` | **GO（修正，小規模）** | **修正 spec 基線**：實測是「單月 MVP」（1998/2~3 月起共 203 期，投手+打者各一），與 `games.mvp_acnt`（單場）及 `cpbl_awards`（僅年度五分類）皆不重複，是真正新資料，但規模小（≈400 筆獎項列） |

**三項修正 spec 基線的判斷**（`OFFICIAL_DATA_GAP1_RESULTS.md` §3.6 是唯讀初判，未實際 POST 驗證內容）：
1. `/stats/toplist` 不是「生涯累計 Top 榜」，是當季 top-5，NO-GO 由「重複但可能有用」改為「純重複」。
2. `/standings/special` 不是「連勝、單月等」，是隊級條件式戰績splits，regression oracle 結論不變但描述需修正。
3. `/stats/mvp` 不是「單場 MVP 名單」，是「單月 MVP」award，預設 NO-GO **不成立**——與現有兩個資料源（`games.mvp_acnt`、`cpbl_awards`）均不重複；但規模小，不足以單獨開 T3/T4 ingest 卡，建議併入既有 `cpbl_awards` 擴充或列為低優先 backlog。

主站仍有 HiNet 挑戰成本；六頁皆屬**低頻／一次性**價值（無日更需求），**不建議**加入每日 Playwright refresh——與 spec 基線建議一致。

## 2. 方法與證據界線

- 單一 Playwright session（`cpbl.ingest._browser`），白天 11:24 啟動，依序 GET 6 頁 → 對 5 個
  已確認 action endpoint 各發 1–2 次代表性 POST（`/stats/hr` 額外測 4 種情境）。全程共
  16 次請求，符合白天／低頻／單次 session 紅線（`CPBL_SITE_MAP.md` §2）；未觸發挑戰重載，
  未執行第二輪冷啟動。
- 原始回應存 scratchpad（不入 repo）：`page_*.html`（GET）、`hr_*.html`／`history_*.html`／
  `special_*.html`／`toplist_*.html`／`mvp_*.html`（POST 回應）。
- 本機 DB 交叉比對：`docker exec cpbl-analytics-db-1 psql`（既有共用容器，唯讀查詢
  `players`、`batting_gamelog`、`venue_dim`），未寫入、未 migrate。

## 3. 逐頁詳情

### 3.1 `/stats/hr` — 歷年全壘打明細（GO）

| 項目 | 事實 |
|---|---|
| 過挑戰頁 | `/stats/hr`（GET，Playwright 過 HiNet） |
| token | B 型（hidden input `__RequestVerificationToken`，隨表單 body 提交，與 `recordall`／`yearaward` 同型） |
| 主 action | POST `/stats/hraction`（`ExecAction=Q`、`IndexOfPages=0` + 下列篩選欄） |
| 輔助 action | POST `/stats/gethroptsaction`（下拉選項來源，未深入） |
| 參數值域 | `KindCode`：`A/C/E/G/B/D/D9/F/H/X`（比現行假設的 A/C/D/E 多出 `B`一軍明星賽、`G`一軍熱身賽、`D9`二軍業餘、`F`二軍總冠軍賽、`H`未來之星邀請賽、`X`國際交流賽——**回填 `CPBL_SITE_MAP.md` §4c 待實測項**）；`Year`：下拉完整涵蓋 `1990–2026`（37 個選項，與 opendata 回填起點一致，非截斷範圍）；`FieldNo`：11 個現行球場代碼（**不含歷史球場**，見下方陷阱）；`HitterTeamNo`/`PitcherTeamNo`：`team_dim` 同碼（`AAA011`…）；`HomeRunType`：`1`場內／`2`首局首打席／`3`代打／`4`再見／`5`滿貫；`Citizenship`：`0`本國／`1`外國 |
| 回傳 | HTML 表格片段（同 B 型模式），單次查詢回傳**該年+賽別全部列**，未見分頁截斷（1997 A 480 列、2019 A 514 列皆一次到齊） |
| 資料粒度 | 逐轟事件：年度、**場次**（= `games.sno` 同編號體系）、**局數**（inning，未分上下半局）、日期、場地（文字，直接對上 `venue_dim.venue`）、打者+acnt、打者球隊（純文字無連結）、投手+acnt、投手球隊（純文字）、打點（該轟 RBI，可反推陽春/兩分/三分/滿貫）、備註（如「再見全壘打」，`HomeRunType` 篩選可交叉驗證） |
| 穩定鍵 | `(year, kind_code, 場次, 局數, hitter_acnt)` **不足唯一**（見 §4 1997 場次112 反例）；加 `pitcher_acnt` 後在全部 5 個抽樣集合（1584 列）**零碰撞** |
| 重複來源 | 無；既有 `game_livelog`／`batting_gamelog.home_runs` 只有計數與逐球座標，**沒有** `HomeRunType`（場內/代打/再見/滿貫分類）與跨場一致的「大事紀」敘事視角 |
| 反爬成本 | 與其他 `/stats/*` 頁同型（B 型 token），複用 `cpbl_stats`／`cpbl_awards` 既有 Playwright 基礎設施即可，無新增反爬難度 |

### 3.2 `/standings/history` — 歷年球隊戰績（GO，canonicalization）

- token B 型；POST `/standings/historyaction`（`Kindcode`+`Year`，另有 `/standings/gethistoryoptsaction` 供下拉選項）。
- `Kindcode` 值域比現行假設更廣：`A/C/E/G/D/D9/F/X`（`/standings/special` 額外多一個 `H`未來之星）。
- 回傳：上/下半季戰績表（出賽數/勝-和-敗/勝率/勝差/對戰隊六隊 H2H/主場戰績/客場戰績），與 `cpbl_standings`（`/standings/season`，僅本季）**同 schema、歷年皆可查**——可直接拿來對帳 opendata／`team_standings` 重算值，不必另建 canonical。

### 3.3 `/standings/special` — 隊級條件戰績（GO，regression oracle；修正描述）

- token B 型；POST `/standings/specialaction`（`Kindcode`+`Year`）。
- 實測內容是**球隊對戰戰績 splits**：紅土戰績／草皮戰績／先得分戰績／先被得分戰績／一分差戰績／延長賽戰績（勝-和-敗），**不是**個人連勝/單月排行——spec 基線描述有誤，但「regression oracle」結論不變：可與記憶 `special-records-feature`（自算隊級特殊戰績）的先得分/一分差/延長賽等維度直接對帳。

### 3.4 `/stats/toplist` — 當季單項排行榜（**NO-GO，修正**）

- token B 型；POST `/stats/toplistaction`（僅 `KindCode` 一個篩選，無 `Year`／生涯切換）。
- 頁面 `<h3>` 明示「**2026年** 單項排行榜」，回傳 10 類（ERA/W/SV/HLD/SO/AVG/H/HR/RBI/SB）**當季 top 5**。
- spec 基線誤判為「生涯累計 Top 榜」（該描述更符合既有 `run_scrape_legends` 涵蓋的 7 榜 top10，走 `/team/apart?year=9999`，與本頁無關）。既有 `/api/v1/season/batting-leaders`／`pitching-leaders` 已提供**遠多於 top 5** 的當季排行，本頁純重複且更淺，**NO-GO**。

### 3.5 `/teamhistory` — 球隊沿革（GO，一次性校驗）

- **無 AJAX**：單次 GET 即完整取得（title「球隊沿革」，年份×球隊時間軸資料已在初始 HTML，非 Vue 動態抓取）；無 token 需求，複雜度等同 `cpbl_coaches`（純 SSR 頁面解析）。
- 用途：一次性核對 `team_dim` 硬編歷史（隊名沿革/更名年份），官方源優先於現行硬編/第三方（`twbsball`）資料，不需排程。

### 3.6 `/stats/mvp` — 單月 MVP（**GO，修正，小規模**）

- token B 型；POST `/stats/mvpaction`（`VoteSid`，一個不透明字串 ID，非年份+月份組合，須先由頁面
  `<select name="VoteSid">` 或未探測的下拉 opts action 取得列表）。
- 頁面 title/導覽為「**單月MVP**」，非「單場 MVP」；VoteSid 選項回溯至 **1998年2~3月**，
  共 **203 期**（每期含投手 MVP＋打者 MVP 各一，含完整身高/體重/生日/初登場/當期關鍵數據卡）。
- **與 spec 基線預設 NO-GO 的前提不成立**：`games.mvp_acnt` 是逐場 MVP，`cpbl_awards`
  （`/stats/yearaward`）只有五類**年度**獎項（打擊/投手/金手套/最佳十人/其他），皆不含「單月」
  維度，本頁是三者都沒有的新資料。但規模小（≈400 列獎項卡），性質更接近榮譽/獎項而非
  逐場統計，建議**不獨立開卡**，未來若要收，併入 `cpbl_awards` 擴充（同一 Playwright
  session、同一 acnt 對齊模式）成本最低。

## 4. `/stats/hr` Event Identity 抽查（驗收要求）

四項情境皆以**同一 session** 內的真實回應驗證，證明可重跑：

| 情境 | 查詢 | 證據 |
|---|---|---|
| **跨年** | `Year=1997` vs `Year=2026`（皆 `KindCode=A`） | 1997 回 480 列、2026 回 180 列，欄位/token/回應 schema 完全一致，證明近 30 年資料走同一介面無需分年改版 |
| **同場多轟** | `Year=2026 KindCode=A`：場次3（2026/03/29 大巨蛋）局數1 陳晨威 vs 局數5 曾聖安；`Year=2023 KindCode=C`：場次5（2023/11/10 天母）局數2/5/7 三轟，其中局數2、7 皆朱育賢（同球員同場異局） | 同場多列共存且欄位一致，無互相覆寫 |
| **球員改名** | acnt `0000001606` 在本機 `batting_gamelog.hitter_name` 2018–2020 為「林祐樂」、2021 起改為「林岱安」；查 `/stats/hr?Year=2019` 該 acnt 顯示「**林祐樂**」（4 列） | 官網回傳的是**期間正確**（period-accurate）姓名快照，非即時 join 現名，與本機 `batting_gamelog.hitter_name` 逐字相符——證明改名不影響以 acnt 為主鍵的 event identity，顯示文字僅供人讀 |
| **季後賽** | `KindCode=C`（2023 台灣大賽，6 列，場次1/1/3/5/5/5＝系列賽內部場號）、`KindCode=E`（2023 季後挑戰賽，4 列） | 兩種賽別皆正常回傳且欄位一致；`場次` 在季後賽是系列內編號（非賽季累計編號），與現行 `games.sno` 的季後賽編號規則一致，join 時需依 `kind_code` 分流（既有慣例） |

**穩定鍵結論**：`(year, kind_code, 場次, 局數, hitter_acnt, pitcher_acnt)` 在 1584 列抽樣中零碰撞。
純用 `(year, kind_code, 場次, 局數, hitter_acnt)`（不含投手）在 1997 年資料中出現 1 組碰撞
（場次112 局數7：同打者「羅得」在同一局內對兩位不同投手各轟一支——顯示該半局有換投且打者
輪到兩次，真實存在但罕見），**必須含 `pitcher_acnt`** 才能唯一；若未來仍有理論上「同打者同局
同投手兩轟」的極端情境（未觀測到但邏輯上可能），需再加 `game_livelog` 逐球序列交叉核對。

## 5. 反爬成本與排程建議

- 六頁皆屬 `/stats/*`／`/standings/*`／`/teamhistory` 家族，token 型態與既有 `cpbl_stats`／
  `cpbl_awards`／`cpbl_standings` 完全相同（B 型 hidden input），**無新增反爬複雜度**，可直接
  複用 `_browser.py` 既有基礎設施。
- 六頁**皆非日更需求**：`/stats/hr`、`/stats/mvp` 是歷史事件流（新增速度＝比賽節奏，遠低於
  daily refresh 頻率）；`/standings/history`、`/standings/special`、`/teamhistory` 是歷年彙總／
  沿革，變動頻率是賽季結束或球隊更名等低頻事件。**建議一次性／賽季末低頻 audit**，
  不併入 `cpbl-refresh-recent` 每日流程，與 spec 基線建議一致。

## 6. 建議後續

- 產品價值與資料契約同時成立者僅 `/stats/hr`：具備新維度（`HomeRunType`／`Citizenship`）、
  穩定鍵可重跑、賽別/年份覆蓋完整，**可開後續 ingest 卡**（T3/T4 視 schema 影響而定），
  範圍建議限定：新表（如 `home_run_events`）以 `(year, kind_code, game_sno, inning,
  hitter_acnt, pitcher_acnt)` 為 natural key、`FieldNo`／`HomeRunType`／`Citizenship`
  篩選僅作抓取分批用（**不要**依賴 `FieldNo` 下拉窮舉，因不含歷史球場，見 §3.1；一律以
  `Year`×`KindCode` 全量查詢，讓歷史球場文字隨資料列自然帶出）。
- `/standings/history`、`/standings/special`、`/teamhistory` 建議以**一次性 script**（非
  ingest 模組）核對既有資料，發現差異才個別修；不建議常駐 CLI。
- `/stats/mvp` 列為低優先 backlog，暫不獨立開卡；若要收，建議併入 `cpbl_awards` 擴充分類
  （新增 `06` 單月MVP 類別）而非新模組。
- `/stats/toplist` 無後續。
- 順帶發現（超出本卡範圍，僅記錄）：導覽列另有「全記錄查詢」「紀錄特別報導」兩個未列入本卡
  範圍的頁面，未探測；`KindCode`/`Kindcode` 完整值域（`A/B/C/D/D9/E/F/G/H/X`）已比
  `CPBL_SITE_MAP.md` §4c 現行記載更完整，建議該檔案的「⚠️待實測」註記可依本報告更新。

## 7. 驗證基準（供後續 ingest 卡覆核）

- 穩定鍵：`(year, kind_code, game_sno, inning, hitter_acnt, pitcher_acnt)` 於任一年度全量
  查詢結果需 100% 唯一；若否，需回退加入 `game_livelog` 逐球序列或人工複核。
- 跨年：至少涵蓋 1990s（opendata 起點）、2010s、2020s 三個年代各一年，確認 schema 不變。
- 改名：以本機 `batting_gamelog.hitter_name`／`pitching_gamelog.pitcher_name` 找出
  `count(distinct name) > 1` 的 acnt 集合，逐一與 `/stats/hr` 對應年份顯示名核對，確認
  period-accurate 假設全體成立（本卡僅抽查 1 例）。
- 季後賽：`KindCode∈{C,E,F}` 場次編號需與對應 `games` 表（`kind_code` 分流）的系列內編號
  規則一致，不可直接當作賽季累計編號使用。
- 反爬：任何後續 ingest 開發與驗證，一律遵守白天／低頻／單一 session／失敗冷卻 15–20
  分鐘紅線，不得為了本卡的低優先資料擴大 Playwright 節流風險。
