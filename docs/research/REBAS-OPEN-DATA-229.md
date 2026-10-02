# #229 野球革命 Open Data：對帳、補缺與產品資料源可用性

研究基準：2026-10-03；本專案 `7a3e3df3d0cded390150b365670274935c570425`。本報告只裁定目前證據支持的用途，不建立匯入管線。野球革命資料稱 REBAS；以下「官方端」是本機 `cpbl` 資料庫中由中職官網、官方進階資料與本專案建置器取得的資料，並非線上全量狀態。

## 結論

| 用途 | 判定 | 直接證據與邊界 |
|---|---|---|
| 有界的**外部對帳** [external cross-check] | **Go，限人工／離線研究** | 2024 例行賽固定抽樣 12／360 場均可由日期＋主客隊唯一找出官方候選，比分、球場、場次序號獨立核對均一致；六隊 6／6 唯一。G30 Box 球員 35／35、首末 10 筆打席 10／10 唯一。可用於定位差異，不能把 REBAS 當裁判或覆寫官方資料。 |
| 補缺 [gap filling] | **目前 No-go** | 本次未證明任何「官方現有資料缺失、REBAS 有獨立且可信內容」的具體場次／欄位。逐球與 PA 粒度雖有潛在補缺候選，人工紀錄來源、身分鍵與語意未跨場核實；不能由 schema 存在推論可補缺。 |
| 產品資料源／自動匯入 [product source / ingestion] | **No-go，停止本卡匯入路線** | 單場 ID 對照不能推出跨場／跨年穩定交叉鍵 [crosswalk]；PA 無 `playerId`，賽事 `seq` 無官方共用鍵；沒有證實現有來源之外可用的增量，發布也不是即時承諾。符合 #229「唯一對應或可用增量未證即停」條件。後續若要重啟，需另案由需求方決定範圍與採用標準。 |

此處 No-go 是**證據不足以採用**，不是斷言野球革命資料錯誤或永久無價值。G30 全場有 3／83 筆打席前比分欄位不同，已知官方 `pre_state` 可能帶事件後比分，不能直接判任一方錯。

## 來源、範圍、版本與授權

以 [上游發行頁](https://github.com/rebas-tw/rebas.tw-open-data/releases)、[schema](https://github.com/rebas-tw/rebas.tw-open-data/tree/main/schema)、[README](https://github.com/rebas-tw/rebas.tw-open-data) 與 [LICENSE](https://github.com/rebas-tw/rebas.tw-open-data/blob/main/LICENSE) 為公開來源；發行說明範圍與本次實際下載驗證的範圍分開列。

| 發行標籤 | 發行說明涵蓋 | `published_at` UTC | 本次實檔檢查 |
|---|---|---|---|
| [`v0.1.0-2023.0`](https://github.com/rebas-tw/rebas.tw-open-data/releases/tag/v0.1.0-2023.0) | 2023 上半季例行賽 G1–G150 | 2024-07-03 08:58:22 | ZIP 逐場 150、合併 1；`seasonId=CPBL-2023-sk`，`seq=1…150` 無缺號 |
| [`v0.1.0-2023.1`](https://github.com/rebas-tw/rebas.tw-open-data/releases/tag/v0.1.0-2023.1) | 2023 下半季 G151–G300、季後挑戰賽、台灣大賽；說明特別指出合併檔名誤含 G150 | 2024-09-03 14:55:26 | 僅核對發行說明，未下載 |
| [`v0.1.0-2024`](https://github.com/rebas-tw/rebas.tw-open-data/releases/tag/v0.1.0-2024) | 2024 例行賽 G1–G360、季後挑戰賽、台灣大賽 | 2025-07-05 12:48:51 | **僅例行賽 ZIP**：逐場 360、合併 1，`seq=1…360` 無缺號，全部逐場物件等於合併檔對應物件；季後附件未查 |
| [`v0.1.0-2025`](https://github.com/rebas-tw/rebas.tw-open-data/releases/tag/v0.1.0-2025) | 2025 例行賽、季後挑戰賽、台灣大賽 | 2026-08-09 15:03:29 | **僅挑戰賽 ZIP**：逐場 4、合併 1；`seasonId=CPBL-2025-lX`，`seq=1…4` 無缺號 |

截至研究時發行頁未列 2026 年資料。上表只證明列出的發行與三個實檔的檢查；未核對其餘附件完整性。下載附件與 SHA-256 [SHA-256]：

| 發行／賽別 | 附件檔名 | SHA-256 |
|---|---|---|
| 2023 上半季 | `CPBL-2023-G1-G150-OpenData.zip` | `65f2f063010e6e0d8d2883af41a61eec30ba808f87cb07267bff40947eaf4b0d` |
| 2024 例行賽 | `CPBL-2024-OpenData.zip` | `1711009c9d3bac68ca13b2b68f409587fdce2deea3c9fbb5ad68131fccb1d19f` |
| 2025 挑戰賽 | `CPBL-2025-Challenge-OpenData.zip` | `ea721c2c4493d78ac98794e6e7ad35774e5be6e913b9342df6cf0232a32b4830` |

每場巢狀 JSON [JSON] 有 `game`、打者／投手 `Box`、打席 [plate appearance, PA]、`event`、`runner`。三附件中的頂層皆有 `seasonId`、`seq`、`date`、`stadium`、雙方 `TeamId`／隊名／逐局分數／Box／PA 清單；**沒有官方 `gameId`**。2024 例行賽 360／360 場的候選欄位 `seasonId`、`seq`、日期、球場、主客隊 ID／名稱／逐局分數皆非空；`date` 只有無時區標記的 `YYYY-MM-DD HH:MM`。合併檔計 11,334 Box 列、339 個不同 REBAS `playerId`（長度 4／5／6 碼）、27,600 PA；Box `playerId`／姓名為 11,334／11,334 非空，PA 打者／投手姓名 27,600／27,600 非空，**PA 中 `playerId` 鍵 0／27,600**。REBAS `playerId` 與官方 10 碼 Acnt 無共同命名空間證據。

| 實檔 | game | 打者 Box | 投手 Box | PA | event | runner | 欄位覆蓋例 |
|---|---:|---:|---:|---:|---:|---:|---|
| 2023 上半季 | 150 | 3,473 | 1,308 | 11,674 | 46,034 | 16,162 | PA `pitchCodes` 非空 11,660／11,674；投球 event `velocity` 非空 42,212／44,197，`coordX/Y` 各 44,033／44,197 |
| 2025 挑戰賽 | 4 | 103 | 39 | 318 | 1,189 | 439 | PA `pitchCodes` 非空 318／318；投球 event `velocity` 1,040／1,132，`coordX/Y` 各 1,132／1,132 |

上述「非空」僅指非 `null`／空字串／空容器，不保證數值有效或量測來源。兩附件 PA `homeWE`、`RE`、`WPA`、`RE24` 均為非空字串（11,674／11,674、318／318）；event 有投球、換人與跑壘事件，runner 無 `playerId`。上游 [README](https://github.com/rebas-tw/rebas.tw-open-data) 說明部分內容人工紀錄；[event schema](https://github.com/rebas-tw/rebas.tw-open-data/blob/main/schema/event.md) 指進壘點多依轉播畫面人工記錄。**不得把座標或球速直接當官方 TrackMan**。各年度 schema 同鍵不代表同口徑；2023 上半季發行曾追補 `pitchCodes`，因此版本與雜湊須固定。

授權為 [Open Data Commons Attribution License v1.0（ODC-By）](https://opendatacommons.org/licenses/by/1-0/)；§3.1 包含商業使用，§4.3 公開作品需可見的來源及授權告知，§4.2 公開傳遞原／衍生資料庫須保留聲明並提供授權資訊。上游 README 同時請有商業需求者聯繫；這句未明言撤銷 ODC-By。此為公開條文的研究解讀，個別內容權利及具體產品輸出仍需另核；三個 ZIP 未見另附 LICENSE 檔，未檢查其他附件是否有額外聲明。

發布時間分別落在資料年度之後；2023 上半季還有事後欄位追補。**沒有已驗的每日、每月或逐季更新承諾**，本研究不能量測野球革命相對本機官方 DB 的穩定延遲，也不能把附件當即時賽況來源。

## 本專案契約、資料增量與消費者

| 粒度／用途 | 本專案現況（基準 SHA 之程式／schema） | REBAS 候選；本次判斷 |
|---|---|---|
| 年度、球員、球隊 | [`migrations/001_init.sql`](../../migrations/001_init.sql) 的年度成績採 opendata 10 碼球員 ID；轉隊同年含隊別。 | REBAS 發行只見 2023–2025 部分賽別，不取代逐年歷史；其短 `playerId` 未證可轉換。 |
| 場次、逐局、事件 | [`002_games.sql`](../../migrations/002_games.sql) 主鍵 `(year,kind_code,game_season_code,game_sno)`，官網 `/schedule/getgamedatas`；[`016_game_log.sql`](../../migrations/016_game_log.sql) 官網逐局與 `game_livelog`。 | REBAS `seasonId`＋`seq`、逐局分數與事件屬可對帳重疊資料；12 場相合，但未證新的覆蓋。 |
| canonical PA、逐球 | [`066_game_recap_pa_expand.sql`](../../migrations/066_game_recap_pa_expand.sql)、[`068_pa_end_hitter.sql`](../../migrations/068_pa_end_hitter.sql)、[`069_pa_pitch_mappings_per_build.sql`](../../migrations/069_pa_pitch_mappings_per_build.sql) 定義 published build、PA 身分與逐球 mapping；[`018_pitch_tracking.sql`](../../migrations/018_pitch_tracking.sql) 收官方 TrackMan。 | REBAS PA／event／runner 有可能提供人工記錄的不同觀點，尤其缺設備球場，但來源獨立性、欄位與身分對接尚未驗到；本次**新增可用欄位／缺場數=未證**，不得寫作 0 或已補足。 |
| 衍生 RE24／勝率 | [`044_sabr_foundation.sql`](../../migrations/044_sabr_foundation.sql)、[`048_re24.sql`](../../migrations/048_re24.sql)、[`049_win_expectancy.sql`](../../migrations/049_win_expectancy.sql) 與 [`sabr.py`](../../src/cpbl/models/sabr.py)、[`winprob.py`](../../src/cpbl/models/winprob.py) 自算；49 號 migration 明示 REBAS 只作對照。 | 同名值是可能的外部對照，未證同口徑或比本地模型更準確；不能當產品替代值。 |

消費端已存在：[`games.py`](../../src/cpbl/api/routers/games.py) 的逐球與 `/winprob`、[`recap.py`](../../src/cpbl/api/routers/recap.py) 的 published PA 勝率、[`players.py`](../../src/cpbl/api/routers/players.py) 的 RE24，以及前端 [`game-live-page.tsx`](../../web/src/app/games/%5Bsno%5D/game-live-page.tsx) 勝率曲線與 [`key-plays.tsx`](../../web/src/app/games/%5Bsno%5D/recap/key-plays.tsx) 的 ΔRE24。現有逐球有設備球場覆蓋限制（[`AI_RUNBOOK.md`](../AI_RUNBOOK.md)），但「REBAS 有相同欄位」不是具體補缺證據。是否能補某場，需證明官方端確實缺、REBAS 該欄非空且可對應、資料來源及精度可用；本次沒有完成此三連驗證。

## 唯讀抽樣：場次、球隊、球員、打席

主分析以 2024 例行賽 ZIP 的合併檔 360 個唯一 `seq` 為母體，固定選 `seq % 30 == 0` 的 G30、G60、…、G360 共 12 場；不是隨機樣本。官方端本機 2024 `kind_code='A'` 候選全集 360 列（上下半季各 180）。先以 REBAS 全檔六個隊 ID／名稱與官方同年度六組隊碼／名稱提出暫時對照，再用**日期＋映射後主客隊**找候選；`seq` 沒有進入連結鍵。以比分、球場別名、`seq=game_sno` 作獨立交叉檢查。這能排除樣本內單用姓名或序號的假匹配，但不能證明跨年穩定。官方資料沒有可核對 REBAS 無時區開賽時間的欄位。

| 實體與分母 | 恰一候選 | 零候選 | 多候選 | 缺欄／差異 |
|---|---:|---:|---:|---|
| 2024 例行賽 12／360 固定場樣本 | 12 | 0 | 0 | 候選鍵缺欄 0；比分、球場別名、`seq` 對 `game_sno` 不符各 0 |
| 同年度六個 REBAS 隊 ID 對六組官方隊碼／名稱 | 6 | 0 | 0 | 隊名衝突 0；12 場側別／比分／球場交叉檢查衝突 0 |
| G30 Box 35 個不同 REBAS `playerId`（打者 26、投手 9） | 35 | 0 | 0 | 同場／主客／角色／同名提候選；背號、打者 PA/AB/H 或投手 BF/H、published PA 角色核對衝突 0 |
| G30 首 5 與末 5 筆 PA；G30 雙方清單共 83 | 10 | 0 | 0 | 候選鍵：局數、攻守、打者／投手姓名、打席前出局數；**不用列表序位作唯一鍵**。十筆比分相符。全 83 筆按順序對照，打席前比分差異 3；此 83 筆不是 83／83 無排序唯一候選證明 |

以下保留跨來源原始識別。主客碼以「客／主」列；官方鍵另含 `year=2024`。比分亦為客：主。表中候選數是符合日期＋雙方隊碼的**官方候選全集計數**。

| REBAS `seq` | `date` 原值 | REBAS 隊 ID 客／主 | 比分 | 官方 `(kind,season,sno)` | 官方隊碼客／主 | 候選數 |
|---:|---|---|---|---|---|---:|
| 30 | 2024-04-13 17:05 | 0MJKt / HCHks | 13:6 | A,1,30 | AAA011 / ACN011 | 1 |
| 60 | 2024-04-27 17:05 | LH4lt / 1zODE | 0:1 | A,1,60 | AKP011 / AJL011 | 1 |
| 90 | 2024-05-12 14:00 | 0MJKt / LH4lt | 3:4 | A,1,90 | AAA011 / AKP011 | 1 |
| 120 | 2024-05-26 17:05 | 0MJKt / 1zODE | 4:5 | A,1,120 | AAA011 / AJL011 | 1 |
| 150 | 2024-06-09 17:05 | LH4lt / HCHks | 3:4 | A,1,150 | AKP011 / ACN011 | 1 |
| 180 | 2024-06-23 17:05 | TPKQm / 1zODE | 2:4 | A,1,180 | AEO011 / AJL011 | 1 |
| 210 | 2024-07-18 18:35 | 0MJKt / 1zODE | 4:1 | A,2,210 | AAA011 / AJL011 | 1 |
| 240 | 2024-08-04 17:05 | TPKQm / HCHks | 5:6 | A,2,240 | AEO011 / ACN011 | 1 |
| 270 | 2024-08-18 17:06 | hThSB / 1zODE | 3:4 | A,2,270 | ADD011 / AJL011 | 1 |
| 300 | 2024-09-01 17:05 | hThSB / 0MJKt | 7:8 | A,2,300 | ADD011 / AAA011 | 1 |
| 330 | 2024-09-16 18:35 | HCHks / 0MJKt | 2:0 | A,2,330 | ACN011 / AAA011 | 1 |
| 360 | 2024-09-29 17:05 | TPKQm / 0MJKt | 2:3 | A,2,360 | AEO011 / AAA011 | 1 |

隊 ID 的一年內暫時映射（候選數均 1）：

| REBAS ID | 隊名原值 | 官方 2024 A 隊碼 |
|---|---|---|
| 0MJKt | 味全龍 | AAA011 |
| 1zODE | 樂天桃猿 | AJL011 |
| HCHks | 中信兄弟 | ACN011 |
| LH4lt | 台鋼雄鷹 | AKP011 |
| TPKQm | 富邦悍將 | AEO011 |
| hThSB | 統一7-ELEVEn獅 | ADD011 |

G30 打者／投手的單場映射如下；每列候選數均 1，背號及上述 Box 基本數據交叉核對均相合。**不得將此表當可重用的跨年 ID 對照表。**

| REBAS `playerId` | 姓名 | 側別／角色 | REBAS／官方背號 | 官方 Acnt | 候選數 |
|---|---|---|---|---|---:|
| ZvyKT | 張祐銘 | away batter | 34／34 | 0000005553 | 1 |
| elqzw | 吉力吉撈．鞏冠 | away batter | 4／4 | 0000003625 | 1 |
| u6XUJ | 李凱威 | away batter | 21／21 | 0000005540 | 1 |
| nm81R | 蔣少宏 | away batter | 63／63 | 0000005291 | 1 |
| 0pBZx | 郭嚴文 | away batter | 6／6 | 0000003343 | 1 |
| 3M1Jq | 拿莫．伊漾 | away batter | 57／57 | 0000005546 | 1 |
| KNmRt | 郭天信 | away batter | 2／2 | 0000005549 | 1 |
| dNaQr | 林孝程 | away batter | 1／1 | 0000005548 | 1 |
| nL5L | 陳思仲 | away batter | 44／44 | 0000006728 | 1 |
| Q1LR3 | 鄭鎧文 | away batter | 28／28 | 0000001240 | 1 |
| dFblH | 張政禹 | away batter | 25／25 | 0000005542 | 1 |
| pKHDZ | 石翔宇 | away batter | 72／72 | 0000000356 | 1 |
| MSMcB | 徐若熙 | away pitcher | 18／18 | 0000005543 | 1 |
| UtY4A | 羅華韋 | away pitcher | 68／68 | 0000001404 | 1 |
| FdIpf | 呂詠臻 | away pitcher | 40／40 | 0000005372 | 1 |
| tKyxK | 趙璟榮 | away pitcher | 42／42 | 0000006215 | 1 |
| C6A1j | 陳禹勳 | away pitcher | 5／5 | 0000000135 | 1 |
| yDdjY | 岳政華 | home batter | 92／92 | 0000005571 | 1 |
| Dvre5 | 岳東華 | home batter | 98／98 | 0000002291 | 1 |
| yvoBa | 陳子豪 | home batter | 1／1 | 0000000743 | 1 |
| c3PEk | 許基宏 | home batter | 74／74 | 0000001119 | 1 |
| 0uRxO | 詹子賢 | home batter | 39／39 | 0000002297 | 1 |
| BpLpN | 蘇緯達 | home batter | 96／96 | 0000000908 | 1 |
| b3UAW | 曾頌恩 | home batter | 32／32 | 0000005569 | 1 |
| AGbc | 王政順 | home batter | 61／61 | 0000002307 | 1 |
| Y1OFa | 林瑞鈞 | home batter | 75／75 | 0000005567 | 1 |
| paNxV | 高宇杰 | home batter | 65／65 | 0000002285 | 1 |
| pdZon | 周思齊 | home batter | 16／16 | 0000000853 | 1 |
| j33XE | 徐博瑋 | home batter | 97／97 | 0000007088 | 1 |
| rfEOE | 江坤宇 | home batter | 90／90 | 0000004636 | 1 |
| m1M26 | 陳俊秀 | home batter | 29／29 | 0000003609 | 1 |
| NjTQu | 魏碩成 | home pitcher | 14／14 | 0000005572 | 1 |
| NiqAD | 陳琥 | home pitcher | 62／62 | 0000000771 | 1 |
| 5ZFTZ | 李吳永勤 | home pitcher | 30／30 | 0000000773 | 1 |
| 5RDHC | 蔡齊哲 | home pitcher | 50／50 | 0000000778 | 1 |

G30 首末 10 筆 PA 的原始 REBAS 側內索引（0 起算）與官方 `pa_id`；每列候選數均 1。REBAS 的 `hitter_box_player_id` 是藉同場 Box 姓名提出的候選，**PA 本身沒有 `playerId`**。

| REBAS 側／側內索引 | 局／出局 | REBAS Box ID／打者／投手 | REBAS 客:主分 | 官方打者 Acnt／`pa_id` | 候選數 |
|---|---|---|---|---|---:|
| away/0 | 1／0 | ZvyKT／張祐銘／魏碩成 | 0:0 | 0000005553／`7db626dc-4f3e-5cb3-8cd6-0eb29237aa46` | 1 |
| away/1 | 1／0 | elqzw／吉力吉撈．鞏冠／魏碩成 | 0:0 | 0000003625／`67a65756-cc04-5c35-a202-c25f5b72d777` | 1 |
| away/2 | 1／1 | u6XUJ／李凱威／魏碩成 | 0:0 | 0000005540／`39854b5b-056c-5160-99ab-06f447eb86d8` | 1 |
| away/3 | 1／1 | nm81R／蔣少宏／魏碩成 | 0:0 | 0000005291／`bb97d723-55d5-5bc7-a17b-c732eacfd4a7` | 1 |
| away/4 | 1／2 | 0pBZx／郭嚴文／魏碩成 | 0:0 | 0000003343／`9848e0fc-b69a-5004-a075-f65b4bb601a0` | 1 |
| home/30 | 9／0 | 0uRxO／詹子賢／陳禹勳 | 13:4 | 0000002297／`e09a78f9-5e03-5f94-a055-90ae1b66b94c` | 1 |
| home/31 | 9／1 | BpLpN／蘇緯達／陳禹勳 | 13:4 | 0000000908／`b56f3698-9ba6-5f91-b1fc-67b1457b4687` | 1 |
| home/32 | 9／1 | b3UAW／曾頌恩／陳禹勳 | 13:4 | 0000005569／`501506b3-be4f-5b49-87e6-973f287acefd` | 1 |
| home/33 | 9／1 | Y1OFa／林瑞鈞／陳禹勳 | 13:6 | 0000005567／`72256cde-367e-54dd-841c-0f12923653f5` | 1 |
| home/34 | 9／2 | j33XE／徐博瑋／陳禹勳 | 13:6 | 0000007088／`c57deee7-0050-5bc5-a6ce-8b3d7995a79c` | 1 |

全場 83 筆是**依打席順序的欄位比對**；局數、攻守、打者、投手、出局數均一致，但有以下打席前比分差異（比分客：主）：

| 官方 `pa_index` | REBAS 打者 | REBAS 起點 | 官方 `pre_state` | 官方 `pa_id` |
|---:|---|---|---|---|
| 13 | 曾頌恩 | 0:0 | 0:2 | `d4b0353d-181d-51f0-8c5f-c2291c744b42` |
| 44 | 張政禹 | 3:2 | 4:2 | `71faf33a-6e54-5905-b8da-50b0e7746a9b` |
| 59 | 吉力吉撈．鞏冠 | 10:2 | 11:2 | `55c5a7c9-6b06-5eb5-a390-f455101b1e38` |

例如 `pa_index=13` 為全壘打，官方 [`recap.py`](../../src/cpbl/api/routers/recap.py) L23–26 明述官網起始事件比分可帶該事件得分後值；所以這 3 筆是**欄位時點差**，尚非任一來源的可歸責錯誤。未檢查另外 348 場、其他年度／季後賽、G30 之外的球員或 PA 無排序唯一性；單場 35 個 ID 同場相合，**不是**跨場／跨年穩定轉換。

## 衍生指標不能直接逐值相減

| 指標 | REBAS 公開說明／觀察 | 本專案算法與不能等同之處 |
|---|---|---|
| 得分期望與 RE24 [run expectancy, RE24] | [PA schema](https://github.com/rebas-tw/rebas.tw-open-data/blob/main/schema/PA.md) 的 `RE` 是打席前得分期望，`RE24` 為期望增加；壘況以 1／2／4 bit 編碼。附件有逐 PA 值，未提供完整版本化公式／歸屬規格。 | [`sabr.py`](../../src/cpbl/models/sabr.py) 以本地按 `span`／`kind_code` 的矩陣，打席中跑壘、非 PA 幽靈跑者、截斷事件與比分修正另分桶；末半局後態為 0。兩者母體、樣本門檻、事件歸屬未證相同；同名不是逐值比較許可。 |
| 主隊勝率 `homeWE`／本地 WP [win probability, WP] | REBAS PA 欄稱「結束打席前主場勝率」。野球革命聯盟係數頁的搜尋摘要稱近五年一軍類似局面之最終勝場占比；原頁無法完整讀取，亦未證 2024 附件用同版。和局、延長賽及缺格補法未公開核實。 | [`winprob.py`](../../src/cpbl/models/winprob.py) 用 2018–2025 A 半局剩餘得分分布與動態規劃 [dynamic programming, DP]；主隊 WP 為勝率加 0.5×和局率，含 12 局和局邊界。訓練窗、和局分母、空格補法與快照時點不能假設相同。現有 WP 的時間外驗證未通過（[`GAME-RECAP-WP-VAL1_RESULTS.md`](GAME-RECAP-WP-VAL1_RESULTS.md)），外部值也不能自動成為真值。 |
| 勝率增量 `WPA` [win probability added] | schema 只寫勝率增加；G30 客隊第 3→4 PA 主隊 `homeWE` 0.538→0.487，本筆 `WPA=+0.051`，與**進攻方視角**反號相容。僅是單場符號假說；未證兩 PA 之間沒有其他可歸屬事件，也未有全面公式。 | 本地 WP 函式是**主隊視角**；`recap` 的打席點先處理官網比分時點。比較前須依攻守轉視角，核對前後狀態、打席邊界、非 PA 事件及四捨五入。原始 `WPA` 不可直接與主隊 ΔWP 比大小或正誤。 |

因此本卡沒有給 RE24、WE、WPA 的「相等率」，沒有把差值當資料品質結論。若另案繼續，先固定兩邊版本／母體、打席前後快照、攻守與 runner 歸屬、和局與延長賽、球場與逐球可用性，再選可比較子集。

## 品質、更新、授權與維護成本的用途判斷

| 用途 | 品質與新鮮度 | 授權／歸屬 | 持續成本與可觀察停損 |
|---|---|---|---|
| 離線外部對帳 | 12 場和 G30 基本 Box／PA 對應支持**有限**對帳；3 個比分快照差異需保留雙方原值。其餘年份、賽別與投球座標來源未證。發布落後資料年度，非當日賽況。 | 研究引用須保留 REBAS 與原授權來源；公開展示若引用數值另滿足 ODC-By 可見標示。 | 可按特定疑點手動下載固定 ZIP／雜湊，再做雙端唯讀核對；如遇零／多候選或公式未知，只報差異，不判正誤。無需常駐管線。 |
| 補缺 | 尚無一個經證明的「本地缺而 REBAS 非空、可唯一接且來源足夠可信」例子；人工座標不可充當官方 TrackMan。 | 若公開產品使用，需設來源標示與原／衍生資料庫分發規則。 | 需逐年逐賽別身分映射、覆蓋率、版本、溯源與錯誤修正；在第一個具體缺口未成立前停止本卡補缺／匯入研究。 |
| 產品資料源 | 穩定 ID、PA／event 鍵、跨年／季後語意、更新服務水準均未證。 | ODC-By 條件須落在 UI/API 與再分發設計；個別內容權利另查。 | 需維護可回溯 crosswalk、發行差異處理、可用性閘門與回歸驗證；本卡未找到與成本相稱的已證增量，No-go。 |

**未驗事項與下一步裁定**：未知 2024 全 360 場跨來源唯一率、其他附件缺漏、跨場／跨年球員 ID 穩定性、同名／換人／轉隊／同日雙賽處理、PA 事件與官方逐球精確對齊、衍生公式／來源版本、公開產品使用的個別內容權利、線上實際讀者與更新承諾。若需求方未來指出具體受害場次或缺欄，可另案先固定一組賽別／年度與缺口，要求**跨來源唯一鍵＋獨立可用增量＋授權標示方案**三項都成立，再決定是否擴大；本卡不自動排實作。#222 的 DER 與跨頁新鮮度仍由其責任範圍處理。

## 可重做方法與資料邊界

公開附件重新下載時，先對照上表的 release 標籤／附件名稱與 SHA-256；若雜湊變動，視為**不同版本**，不可沿用本次計數。以下僅用 Python 標準庫讀 ZIP，不執行附件內容；合併檔只讀一次，逐場檔不再重複計數。列出固定樣本：

```bash
shasum -a 256 /tmp/cpbl229-rebas-assets/*.zip
python3 - <<'PY'
import json
from zipfile import ZipFile
p = '/tmp/cpbl229-rebas-assets/CPBL-2024-OpenData.zip'
with ZipFile(p) as z:
    assert z.testzip() is None
    names = z.namelist()
    assert all(not n.startswith('/') and '..' not in n.split('/') for n in names)
    games = json.loads(z.read('CPBL-2024-OpenData/CPBL-2024-OpenData.json'))
assert len(games) == 360 and {g['seq'] for g in games} == set(range(1, 361))
sample = [g for g in games if g['seq'] % 30 == 0]
for g in sample:
    print(g['seasonId'], g['seq'], g['date'],
          g['awayTeamId'], g['homeTeamId'],
          sum(map(int, g['awayScores'])), sum(map(int, g['homeScores'])))
PY
```

2023 上半季與 2025 挑戰賽的實體／非空計數：在 ZIP 內只選 `*-G*.json` 的逐場物件（跳過 `*-OpenData.json` 彙總檔），每場遍歷 `away/home` 的 `BatterBox`、`PitcherBox`、`PAList`，各 PA 遍歷 `events`，各 event 遍歷 `runners`。非空定義為值不屬 `None`、`''`、`[]`、`{}`；投球 event 的分母限 `pitchCode` 非空的事件。上述方法與雜湊可重算表內分母；原始探查輸出為本機可拋棄的 `/tmp/cpbl229-rebas-sample.json` 與 `/tmp/cpbl229-local-match.json`，**報告中的表格與方法不依賴這些暫存檔永久存在**。

官方端在本機 `cpbl` DB 以**唯讀交易**查候選全集，嚴禁把官方資料送外部服務。至少重跑下列查詢；同場 Box 與 PA 的 SQL 原文已列在本研究先行筆記 `research_notes/野球革命資料可用性/local_match_probe.md`，該筆記為未提交暫存，核心查詢一併記在此處：

```sql
BEGIN READ ONLY;
SHOW transaction_read_only;  -- 必須輸出 on
SELECT year,kind_code,game_season_code,game_sno,game_date,venue,
       home_team_code,home_team_name,away_team_code,away_team_name,
       home_score,away_score
FROM cpbl.games
WHERE year=2024 AND kind_code='A'
ORDER BY game_date,game_season_code,game_sno;
ROLLBACK;
```

在本地程序用 `(REBAS date[:10], 映射後 home/away code)` 過濾上述候選全集，記下 0／1／多候選與**候選原始列**；`seq` 只做事後核對。隊碼由兩端 2024 A 隊名提出候選，再用 12 場的日期、側別、比分及球場別名交叉核實。官方查得 360 列，並非查線上生產 DB。G30 Box／PA 查詢如下，需各自包在 `BEGIN READ ONLY` 與 `ROLLBACK` 中，且只用 published build；若查到多個 build，先依 `state='published'` 契約排除其他版本：

```sql
BEGIN READ ONLY;
SHOW transaction_read_only;
SELECT 'batter' AS role,hitter_acnt AS official_id,hitter_name AS name,
       visiting_home_type AS side_code,uniform_no,
       plate_appearances AS pa,at_bats AS ab,hits
FROM cpbl.batting_gamelog WHERE year=2024 AND kind_code='A' AND game_sno=30
UNION ALL
SELECT 'pitcher',pitcher_acnt,pitcher_name,visiting_home_type,
       uniform_no,plate_appearances,NULL::int,hits
FROM cpbl.pitching_gamelog WHERE year=2024 AND kind_code='A' AND game_sno=30;
ROLLBACK;

BEGIN READ ONLY;
SHOW transaction_read_only;
SELECT pa.pa_index,pa.pa_id,pa.state,pa.start_event_no,
       pa.hitter_acnt,h.name AS hitter_name,
       pa.start_pitcher_acnt,p.name AS pitcher_name,pa.pre_state,pa.result_action
FROM cpbl.game_plate_appearances pa
JOIN cpbl.game_recap_builds b ON b.build_id=pa.build_id AND b.state='published'
LEFT JOIN cpbl.players h ON h.id=pa.hitter_acnt
LEFT JOIN cpbl.players p ON p.id=pa.start_pitcher_acnt
WHERE pa.year=2024 AND pa.kind_code='A' AND pa.game_sno=30
ORDER BY pa.pa_index;
ROLLBACK;
```

G30 球員候選鍵為**同場、同側、同角色、同名**；背號及 Box 基本數據只作獨立核對，並確認 35 個官方 Acnt 都出現在 published PA 的相應角色欄位。PA 先依各側內清單與局數／攻守形成完整 83 筆檢查順序；首末各 5 筆的**無順序候選鍵**為局數、攻守、打者姓名、投手姓名、打席前出局數。每列須記錄候選全集與計數，並核對比分、壘況／出局與結果語意；這 10 筆只完成前述鍵及比分核查，**未把所有結果碼視為同義**。83 筆順序核對只用於發現差異，不代替 83 筆無順序唯一性證明。

**外部工具與資料聲明**：公開 GitHub Releases／API、上游 README／schema／LICENSE 與 ODC-By 網頁、三個公開 ZIP、`gh`／`wfx brief`、本地 Python／Git／唯讀 SQL。對外送出的是公開 URL／儲存庫識別及一般網頁請求；沒有上傳附件、憑證、個資、私有原始碼或本機資料庫內容。ZIP 在本機 `/tmp` 處理，未執行其中程式；未寫共享／正式 DB、未改程式或 schema、未刷新／同步／部署。
