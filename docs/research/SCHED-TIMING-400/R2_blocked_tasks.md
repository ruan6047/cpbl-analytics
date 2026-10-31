# #400 研究 R2：排程卡住任務工作的實際案例

- 卡片：[#400](https://github.com/ruan6047/cpbl-analytics/issues/400)，規劃階段／研究子狀態
- 研究問題（唯一）：排程卡住任務工作的實際案例有哪些？分兩型：搶資源（A）、等時刻（B）。
- 支援的決定：規劃階段替優化項目標出「誰受害」與先後。
- 研究者：claude-opus-5-5（本機背景子代理），2026-10-31
- 非範圍：排程時間分布本身（另一位研究者負責）、方案選擇、對應到 #393。

## 1. 母體、方法、期間

- **母體**：`ruan6047/cpbl-analytics` 的 Issue 與 PR 留言，用 `gh api repos/.../issues/comments?since=2026-10-01T00:00:00Z` 全部取回，共 2,024 則。最早一則建立於 2026-10-01T03:11Z，最晚一則在 2026-10-31（本卡）。`since` 篩的是更新時間，但取回的留言建立時間全部 ≥ 10-01。
- **期間**：2026-10-01 到 2026-10-31。vNext 約在 10-08 起用（#417 結案），所以 10-01 到 10-07 的幾則屬於過渡期，表中會另外標明。**舊制 Project #4 期間（10 月以前）沒有查**。
- **篩選**：
  1. 用 regex 篩出兩類行的交集：(a) 跟排程有關的字（10:10、晚間鏈、postseason-evening、每日鏈、週跑、13:10、14:10、21:10、watchdog、排程、冷卻、節流），以及 (b) 表示被卡的字（避開、另排、改排、延後、錯開、卡住、跑完、順延、撞、擋、讓路、錯過、趕不上、持有、exit 75 等）。結果是 493 行。這些行我逐行讀完。
  2. 另外針對 13:10／14:10／週一／J3／J4／21:10、鎖被持有、讓路、節流＋排程等字補搜。
  3. 約 40 則候選留言讀了全文（`show.py`，每則讀前 2,500 字元），確認情境與原文。
- **限制**：沒有窮舉。regex 沒命中的留言可能還有案例，例如只寫「等明天再驗」而沒寫排程名的留言。卡面 body 與 `~/.wf-evidence` 沒有讀。下面的案例數只是**已確認的下限**，⛔ 不代表全部。

## 2. 案例清單

欄位：卡號＋留言、型態、卡住它的排程、等多久／改到哪個窗口（有記載才寫）、原文短引（< 15 字）。
「結果」只寫留言裡記載的事；括號標 *推論* 的是我從時戳推算的。

### 2.1 等時刻（B）：任務要等排程跑完才能驗收或往下做

| # | 卡／留言 | 卡住它的排程 | 等待／改排（有記載才寫） | 原文短引 |
|---|---|---|---|---|
| B1 | [#225](https://github.com/ruan6047/cpbl-analytics/issues/225#issuecomment-5956380124)（10-02，過渡期） | 10:10 每日鏈 | 規劃選擇不手動重跑，等 10/03 10:10 那次排程恢復同步；實際在 10:10–11:38 完成（[5965518389](https://github.com/ruan6047/cpbl-analytics/issues/225#issuecomment-5965518389)）。*推論：從規劃到完成約 19 小時；規劃文字自估手動跑「僅提早約10小時」* | 「讓10/03既有10:10排程完成」 |
| B2 | [#268](https://github.com/ruan6047/cpbl-analytics/issues/268#issuecomment-6162249090) → [6162265836](https://github.com/ruan6047/cpbl-analytics/issues/268#issuecomment-6162265836)（10-14） | 21:10 watchdog | 晚間 P1 啟用原本裁定延到 21:10 watchdog 判 OK、21:15 之後；約 2 分鐘後需求方撤回，改成部署後就啟用 | 「為什麼今天要等21:10」 |
| B3 | [#268](https://github.com/ruan6047/cpbl-analytics/issues/268#issuecomment-6160372179)（10-14） | 10:10 每日鏈 | 部署後生產的 075 只能靠每日鏈套用；需求方改成手動 kickstart 一次，不等隔天 10:10 | 「這只是為了方便自動更新」 |
| B4 | [#284](https://github.com/ruan6047/cpbl-analytics/issues/284#issuecomment-6182605162)（10-15） | 10:10 每日鏈 | 驗收改成資料層，在「今天 10:10 每日鏈跑完後」讀 log 與生產表（migration 076 由鏈套用） | 「今天 10:10 每日鏈跑完後」 |
| B5 | [#289](https://github.com/ruan6047/cpbl-analytics/issues/289#issuecomment-6189667552)（10-15） | 10:10 每日鏈 | 「資料更新後仍正確」最早 10/16 10:10 之後才能觀測，卡維持阻塞。*推論：從部署驗證 20:19 起約 14 小時* | 「最早要等 10/16 10:10」 |
| B6 | [#281→#300](https://github.com/ruan6047/cpbl-analytics/issues/281#issuecomment-6205288747)（10-16） | 10:10 每日鏈 | #300 的「資料更新後」證據原本要等 10:10；需求方裁定豁免。同一則也記下 #287 的 10:10 等待**不在豁免內** | 「每日刷新可以無視昨天又沒比賽」 |
| B7 | [#287](https://github.com/ruan6047/cpbl-analytics/issues/287#issuecomment-6205926002)（10-16） | 10:10 每日鏈 | 第 1 次合併的 production 077、建置與同步只在每日鏈跑，要到 10/16 10:10 之後才驗收 | 「每日鏈後驗收」 |
| B8 | [#285](https://github.com/ruan6047/cpbl-analytics/issues/285#issuecomment-6191924248)（10-15） | 10:10 每日鏈 | 資料更新後的正式站複驗列為未驗，等 10/16 10:10 | 「下一次每日更新」 |
| B9 | [#343](https://github.com/ruan6047/cpbl-analytics/issues/343#issuecomment-6283354608)（10-20） | 10:10 每日鏈 | 研究 3 從 10-21 10:10 之後才開始累積；收尾等最後一場賽後的 10:10 資料。需求方先問了一句 | 「需要等這麼久嗎」 |
| B10 | [#344](https://github.com/ruan6047/cpbl-analytics/issues/344#issuecomment-6357633744)（10-23） | 10:10 每日鏈 | S7＝隔天 10:10 每日鏈第一次寫入；S8 等鏈跑完才對帳。後來 S8 從固定的 11:00 改成「鏈跑完就開始」（[6360646281](https://github.com/ruan6047/cpbl-analytics/issues/344#issuecomment-6360646281)） | 「S7 是明天 10:10 的每日鏈」 |
| B11 | [#361](https://github.com/ruan6047/cpbl-analytics/issues/361#issuecomment-6365002609)（10-23）、[6405611622](https://github.com/ruan6047/cpbl-analytics/issues/361#issuecomment-6405611622)（10-26） | 10:10 每日鏈 | 本機寫完後，正式站由隔天 10:10 鏈整表帶上，之後才唯讀驗證；兩次都是這樣 | 「由 10/24 10:10 每日鏈」 |
| B12 | [#364](https://github.com/ruan6047/cpbl-analytics/issues/364#issuecomment-6372090848)（10-24） | 10:10 每日鏈 | 合併排在當天 10:10 鏈跑完、鎖不存在之後；結案要等隔天第一次真實執行 | 「今天 10:10 每日鏈跑完」 |
| B13 | [#382](https://github.com/ruan6047/cpbl-analytics/issues/382#issuecomment-6460020267)（10-28） | 晚間鏈＋10:10 每日鏈 | WP2 冷啟動段要等「今晚晚間鏈和明天 10:10」都正常，才去申請窗口。*推論：延後約 1 天，實際在 10/29 才跑*（[6486251407](https://github.com/ruan6047/cpbl-analytics/issues/382#issuecomment-6486251407)） | 「等今晚晚間鏈和明天 10:10」 |
| B14 | [#383](https://github.com/ruan6047/cpbl-analytics/issues/383#issuecomment-6488023293)（10-29）→ [6494213409](https://github.com/ruan6047/cpbl-analytics/issues/383#issuecomment-6494213409) | 10:10 每日鏈 | WP4-4 不手動 build，等 10/30 10:10；§5 原本也要隔日複查。需求方取消了隔日複查 | 「非賽季根本沒資料需要跑」 |
| B15 | [#357](https://github.com/ruan6047/cpbl-analytics/issues/357#issuecomment-6463316402)（10-28） | 10:10 每日鏈 | 驗收要等隔一次每日鏈（10/29 10:10）之後再復查 | 「隔一次每日鏈」 |
| B16 | [#353](https://github.com/ruan6047/cpbl-analytics/issues/353#issuecomment-6468179194)（10-28） | 10:10 每日鏈 | 合併窗口放在 10/29 10:10 每日鏈加 10:27 複查之後 | 「合併窗口在 10/29 10:10」 |
| B17 | [#293](https://github.com/ruan6047/cpbl-analytics/issues/293#issuecomment-6320896632)（10-21） | 晚間鏈、10:10 每日鏈 | 結案順序：晚間鏈跑到系列結束，最遲隔天 10:10 鏈完成後才停用並結案 | 「最遲隔日 10:10」 |

### 2.2 搶資源（A）：撞到排程執行中、鎖、冷卻，或被排程框住窗口

**A-1 實際撞上（執行當下真的被排程擋下）**

| # | 卡／留言 | 卡住它的排程 | 結果 | 原文短引 |
|---|---|---|---|---|
| A1 | [#342](https://github.com/ruan6047/cpbl-analytics/issues/342#issuecomment-6365156900)（10-23 20:42） | 晚間鏈（持有 refresh 鎖） | C-5 手動抓取＋同步放棄，零寫入；需求方裁定這次不計次（同時官網先發欄也還是空的） | 「refresh 鎖由晚間鏈持有」 |
| A2 | [#382](https://github.com/ruan6047/cpbl-analytics/issues/382#issuecomment-6459261744)（10-28 10:31） | 晚間鏈（每 5 分鐘） | WP1 探測被閘門 `other_www_process` 中止（已打 120 個請求，全部 200），改了探測器才重跑 | 「當成另一個在打 www 的程序」 |
| A3 | [#382 資料（#357 WP1）](https://github.com/ruan6047/cpbl-analytics/issues/382#issuecomment-6437102691)（10-27） | 晚間鏈 | WP1 在 15:55:27–15:55:57 暫停 30 秒 | 「一次 30 秒暫停」 |
| A4 | [#225](https://github.com/ruan6047/cpbl-analytics/issues/225#issuecomment-5956380124)（10-02，過渡期） | 10:10 每日鏈 | 先前觀測到「容器重建碰撞」：主站部署撞上同步。之後 09:50 起到該次 run 結束，暫停主站合併與手動 Deploy | 「已觀測到的容器重建碰撞」 |
| A5 | [#268](https://github.com/ruan6047/cpbl-analytics/issues/268#issuecomment-6159564327)（10-14） | 10:10 每日鏈 | 發布授權條件是 10:10 前完成；merge 在 10:29 才做，已逾時。主站 bump／Deploy 改到「當日 10:10 refresh 結束後」，期限延 1 天 | 「refresh 結束後開始」 |

**A-2 窗口被排程框住，造成改天或趕時間（有記載改到哪個窗口）**

| # | 卡／留言 | 卡住它的排程 | 改排 | 原文短引 |
|---|---|---|---|---|
| A6 | [#288](https://github.com/ruan6047/cpbl-analytics/issues/288#issuecomment-6219019795)（10-16 23:3x） | 21:00–21:15 晚間時段 | 部署要在 20:45 前開始（Deploy 約 12 分鐘，見 [#285 6191506358](https://github.com/ruan6047/cpbl-analytics/issues/285#issuecomment-6191506358)），已過就改到 10/17 | 「今晚已過 20:45 不能部署」 |
| A7 | [#288](https://github.com/ruan6047/cpbl-analytics/issues/288#issuecomment-6215711132)（10-16 20:3x） | 同上 | 為了趕 20:45 前開始，當下立刻上；趕不上就改 10/19 | 「要趕 20:45 前開始 Deploy」 |
| A8 | [#281](https://github.com/ruan6047/cpbl-analytics/issues/281#issuecomment-6191499973)／[6191522011](https://github.com/ruan6047/cpbl-analytics/issues/281#issuecomment-6191522011)（10-15） | 21:00–21:15 晚間時段 | #285 部署原本排在「今晚 21:15 後」，需求方兩次改掉 | 「沒必要等21:15」 |
| A9 | [#347](https://github.com/ruan6047/cpbl-analytics/issues/347#issuecomment-6309635764)（10-21 14:30） | 10:10 每日鏈（窗口起點）＋比賽日 15:00 | 續修改到隔天「10:10 之後到 15:00」的窗口 | 「今日窗口已過」 |
| A10 | [#349](https://github.com/ruan6047/cpbl-analytics/issues/349#issuecomment-6328833278)（10-22） | 10:10 每日鏈 | 原窗口是「每日鏈結束～12:30」；需求方要求現在做，改成「現在～09:45 硬停」，鎖最晚 09:50 釋放 | 「可以現在就處理嗎」 |
| A11 | [#361](https://github.com/ruan6047/cpbl-analytics/issues/361#issuecomment-6360640622)（10-23） | 21:00–21:15、10:10 每日鏈 | 窗口被切成主段（到 20:55）和備用段（21:15–22:30）；退路是交給隔天 10:10 鏈同步 | 「21:00–21:15 不持鎖」 |
| A12 | [#361](https://github.com/ruan6047/cpbl-analytics/issues/361#issuecomment-6405437598)（10-26） | 10:10 每日鏈 | 窗口分成甲（09:55 前）和乙（每日鏈結束後到 13:30） | 「每日鏈結束後至 13:30」 |
| A13 | [#355](https://github.com/ruan6047/cpbl-analytics/issues/355#issuecomment-6407612309)（10-26） | 10:10 每日鏈 | 每日鏈 10:24:40 結束，17 秒後才建 E2 庫。條件見 [6371965532](https://github.com/ruan6047/cpbl-analytics/issues/355#issuecomment-6371965532) | 「每日鏈 10:24:40 結束後」 |
| A14 | [#393](https://github.com/ruan6047/cpbl-analytics/issues/393#issuecomment-6530132279)（10-31） | 10:10 每日鏈 | WWW1A／B 起跑前要確認當日每日鏈已結束，窗口 11:00、11:30。那天的鏈是 10:10:03–10:10:05（[6538153300](https://github.com/ruan6047/cpbl-analytics/issues/393#issuecomment-6538153300)）。*推論：約 50 分鐘的空檔是窗口安排造成的，排程本身並沒有在跑* | 「任何一條鏈正在跑不開始」 |

**A-3 只有規則限制、沒有記載實際等待（窗口條件以排程為界）**

- 共同主 PM 的發布窗口規則：「避開 10:10–10:30 與 21:00–21:15」，比賽日 15:00 前完成。至少寫進以下卡的授權條件：#289 [6183831469](https://github.com/ruan6047/cpbl-analytics/issues/289#issuecomment-6183831469)、#293 [6183902650](https://github.com/ruan6047/cpbl-analytics/issues/293#issuecomment-6183902650)、#284 [6214435609](https://github.com/ruan6047/cpbl-analytics/issues/284#issuecomment-6214435609)、#285 [6191391962](https://github.com/ruan6047/cpbl-analytics/issues/285#issuecomment-6191391962)、#291 [6221861506](https://github.com/ruan6047/cpbl-analytics/issues/291#issuecomment-6221861506)、#316 [6229376038](https://github.com/ruan6047/cpbl-analytics/issues/316#issuecomment-6229376038)、#286 [6208458168](https://github.com/ruan6047/cpbl-analytics/issues/286#issuecomment-6208458168)（10-15～10-17）。
- 合併／FF 前要確認「refresh 鎖不存在、晚間鏈 tick 未執行」：#365 [6372117409](https://github.com/ruan6047/cpbl-analytics/issues/365#issuecomment-6372117409)、#342 [6408808806](https://github.com/ruan6047/cpbl-analytics/issues/342#issuecomment-6408808806)、#364/#365 [6361793611](https://github.com/ruan6047/cpbl-analytics/issues/343#issuecomment-6361793611)、#398 [6540849923](https://github.com/ruan6047/cpbl-analytics/issues/398#issuecomment-6540849923)（「避開 10:10～鏈結束」）。
- 本機 DB 寫入要持鎖，或確認晚間鏈沒有同時寫：#316 [6230240850](https://github.com/ruan6047/cpbl-analytics/issues/316#issuecomment-6230240850)；#361 寫入前等了一個晚間鏈 tick（20:34:09–10，數秒）[6365002609](https://github.com/ruan6047/cpbl-analytics/issues/361#issuecomment-6365002609)。
- 連 www 的窗口前提：#357 規定 10:05 前暫停、等每日鏈 succeeded 才恢復，晚間鏈在抓 www 時要等，11/02 14:10 週跑也一樣等（[6418380269](https://github.com/ruan6047/cpbl-analytics/issues/357#issuecomment-6418380269)）。#382 的前提是「非週一 14:10 週跑、晚間鏈窗口內不連 www」（[6436934294](https://github.com/ruan6047/cpbl-analytics/issues/382#issuecomment-6436934294)）。
- 窗口夾在兩次 10:10 之間：#383 是「當天 10:10 之後、下一次 10:10 之前，避開晚間鏈與週一 J3／J4」（[6468399932](https://github.com/ruan6047/cpbl-analytics/issues/383#issuecomment-6468399932)）；#353 E1 是「10/30 10:10 每日鏈開始前必須完成」（[6486738716](https://github.com/ruan6047/cpbl-analytics/issues/353#issuecomment-6486738716)）。#353 的 VPS 量測要避開 10:10–10:30、比賽日 18:00–23:30、21:00–21:15（[6347141249](https://github.com/ruan6047/cpbl-analytics/issues/353#issuecomment-6347141249)）。
- 過渡期：#222 [5952097034](https://github.com/ruan6047/cpbl-analytics/issues/222#issuecomment-5952097034)「避刷新鎖與每日鏈時段」；#237 [6053435661](https://github.com/ruan6047/cpbl-analytics/issues/237#issuecomment-6053435661)「避開每天 10:10」。

### 2.3 邊界案例（不計入上表）

- **#293 錯過 G2 窗口**（[6258816951](https://github.com/ruan6047/cpbl-analytics/issues/293#issuecomment-6258816951)）：合併窗口是「10:30–12:30」，起點由每日鏈決定。但錯過的原因是協調訊息沒送出（PM 失誤），不是排程。
- **#357 WP5 因冷卻延後**（[6460011439](https://github.com/ruan6047/cpbl-analytics/issues/357#issuecomment-6460011439)）：冷卻來自 #382 探測觸發的節流，**不是排程**。反過來，#382 觸發節流後，排程這一側被停掉：晚間鏈的兩個 www 旗標暫停（[#375 6460032466](https://github.com/ruan6047/cpbl-analytics/issues/375#issuecomment-6460032466)）。
- **#393 原提議 11/1 窗口**（[6543104540](https://github.com/ruan6047/cpbl-analytics/issues/393#issuecomment-6543104540)）：需求方問「現在都沒有任何比賽為什還要等？」。PM 更正說，那是執行者的提議，不是排程或賽事要求的等待。

## 3. 彙總

### 3.1 案例數（已確認的下限，未窮舉）

- 等時刻（B）：17 例，跨 16 張卡。
- 搶資源（A）：實際撞上 5 例（A1–A5）；窗口被框住、有記載改排 9 例（A6–A14）；只有規則限制的另外約 20 張卡。
- 邊界案例：3 例。

### 3.2 卡住任務的排程與時段（依案例數排序）

1. **10:10 每日鏈（`com.cpbl.scrape-daily`）——事實，最多。** 等時刻 17 例中 16 例跟它有關（B2 除外）。大多是「生產 migration、建置或同步只在每日鏈跑，所以驗收要等隔天 10:10」（B3–B8、B11、B14），或者把合併、驗收排在鏈之後（B10、B12、B16）。搶資源方面，A4、A5、A9、A10、A12–A14 都以它為窗口界線。卡住的時段是 **10:10 到鏈結束**：規則寫 10:10–10:30，實際結束時刻有 10:10:05（A14，skip 日）、10:24:40（A13）、11:38（B1）。
2. **晚間鏈（`com.cpbl.postseason-evening`）——事實，次多，而且是唯一有「執行當下真的撞上」紀錄的排程。** A1 被它持有的鎖擋下而放棄；A2 被閘門中止；A3 讓路 30 秒；另外 A11、B13、B17 也受它影響。有兩種卡法：持有 refresh 鎖，以及在打 www。
3. **21:00–21:15 晚間時段——事實（規則面）；歸因待查。** 實際造成改天的是 A6、A7，A8 是需求方推翻了這個限制。部署需要約 12 分鐘，所以實際截止是 **20:45**。留言把這段時間歸給「晚間鏈」（[6191499973](https://github.com/ruan6047/cpbl-analytics/issues/281#issuecomment-6191499973)），但晚間鏈是每 5 分鐘跑一次，這 15 分鐘具體在避哪個排程，我沒有查證（見缺口）。
4. **21:10 watchdog——事實，1 例**（B2），約 2 分鐘內就被需求方撤回。另外 #358 有「合併當日 21:10 前 bootstrap」這種期限型限制（[6461737813](https://github.com/ruan6047/cpbl-analytics/issues/358#issuecomment-6461737813)）。
5. **週一 13:10／14:10 週跑——查無實際卡住的案例。** 只出現在窗口前提裡（#382、#383、#357）。

### 3.3 跟「誰受害」有關的觀察

- **事實**：需求方本人至少 9 次質疑或推翻等排程的安排：B2「為什麼今天要等21:10」、B3、A8「沒必要等21:15」、B6、A10、B9「需要等這麼久嗎」、B14、#393「為什還要等」，以及跨卡原則「不要等排程時間」（[#344 6360646281](https://github.com/ruan6047/cpbl-analytics/issues/344#issuecomment-6360646281)、[#343 6360657935](https://github.com/ruan6047/cpbl-analytics/issues/343#issuecomment-6360657935)）。這是痛點原話「常常因為排程導致任務被卡住」的直接佐證。
- **推論**：其中 5 次的理由是「沒比賽、資料不會變」（B2、A8、B6、B14、#393）。也就是說，休季或無賽日時，排程本身沒事可做（skip，例如 A14 只跑了 2 秒），任務卻還照賽季規則等它或避開它。
- **事實**：受害的是兩種人。一種是要靠每日鏈把成果帶上正式站、才能驗收的卡（等時刻：#284、#287、#289、#361、#383 等）；另一種是要連 www 或寫本機 DB 的卡，跟晚間鏈搶資源（#342、#382、#357）。
- **事實（反方向）**：#398 的規劃查了主 checkout 的 `logs/launchd.err.log`，「refresh already running」「lock unavailable」都是 0 次（[6540849923](https://github.com/ruan6047/cpbl-analytics/issues/398#issuecomment-6540849923)）。在那份 log 的範圍內，排程沒有被任務的鎖擋過；目前的協調是任務單方面讓排程。*推論*：所以受害的一方集中在任務。

## 4. 缺口（查過仍不知道的事）

- 10 月以前（舊制 Project #4）沒有查；卡面 body、`~/.wf-evidence` 的窗口檔（例如 `RELEASE-WINDOW-1016-1018.md`）也沒有讀。
- 「21:00–21:15」具體在避哪個排程或步驟，留言裡只寫「晚間鏈」，沒有查證。
- 多數案例沒有記載實際等了多久；表中的時數都是從時戳推算的。
- 共同主 PM 核發窗口時「因為排程而拒絕或延後」的申請，多半在共同主 PM 的對話裡，沒有落到 GitHub，所以 A 型可能被低估。
- #357 規定「10:05 前暫停、等每日鏈 succeeded」，實際有沒有暫停、暫停多久，留言裡沒找到紀錄。
- regex 沒命中的留言可能還有案例；本文是下限。

## 5. 工具、資料來源與送出的資料

- 工具：`gh issue list`、`gh api`（GitHub REST，唯讀）、本機 python3 篩選腳本（放在 scratchpad）、`wfx brief`。
- 資料來源：`ruan6047/cpbl-analytics` 的 Issue 與 PR 留言（2026-10-01～10-31），以及本卡的 brief。
- 送出的資料：只有 GitHub API 的查詢參數（repo 名、`since` 時間、分頁）。沒有送出憑證、`.env`、DB 資料或原始碼。沒有連 cpbl.com.tw、stats、正式站或 VPS；沒有留言、改欄位、改 launchd、寫 DB 或 commit。
